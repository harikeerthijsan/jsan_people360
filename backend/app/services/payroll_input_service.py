"""Payroll input preparation (Phase 3).

The bridge between the source modules and the future calculation engine.
Four rules shape it.

**Consume, never duplicate — and never write back.** Attendance, leave,
regularizations, balances and offboarding are read through
:class:`~app.repositories.payroll_repository.PayrollSourceReader`, a
SELECT-only surface. There is no code path here that modifies a source
record; the only thing an issue produces is an exception row and a
``requires_review`` status.

**Approved data only.** Leave counts only when the request is approved;
overtime counts as approved only when the configuration's approval
requirement is satisfied — through the existing regularization mechanism,
because attendance has no second approval concept and payroll must not
invent one. Everything else lands in the pending bucket, flagged.

**Inputs, not amounts.** Every number stored is a count of days or hours.
"Unpaid leave = 2 days, basis = working days" is this phase's entire answer;
turning that into money is explicitly a later phase's job.

**The snapshot is honest about time.** Each input records exactly which
source rows fed it (id + ``updated_at``) and a fingerprint over them. When
the sources move afterwards, change detection flips the input to
``requires_review`` rather than letting a later calculation quietly consume
stale numbers.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.audit_log import AuditAction
from app.models.employee import Employee
from app.models.enums import (
    ApprovalStatus,
    AttendanceStatus,
    EmploymentStatus,
    LeaveTreatment,
    PayrollDayBasis,
    PayrollEligibility,
    PayrollExceptionCategory,
    PayrollInputStatus,
    PayrollPeriodStatus,
    PayrollSourceType,
    RecordStatus,
    UnpaidLeaveTreatment,
)
from app.models.offboarding import OffboardingCase
from app.models.payroll import (
    EmployeeCompensation,
    PayrollConfiguration,
    PayrollEmployeeSetting,
    PayrollInput,
    PayrollInputException,
    PayrollInputSource,
    PayrollLeaveRule,
    PayrollPeriod,
)
from app.models.workforce import (
    AttendanceRecord,
    AttendanceRegularization,
    LeaveBalance,
    LeaveRequest,
)
from app.repositories.payroll_repository import (
    PayrollConfigurationRepository,
    PayrollInputExceptionRepository,
    PayrollInputRepository,
    PayrollInputSourceRepository,
    PayrollLeaveRuleRepository,
    PayrollPeriodRepository,
    PayrollSourceReader,
)
from app.schemas.payroll import (
    EmployeeSummary,
    PayrollChangeDetectionResult,
    PayrollExceptionRead,
    PayrollInputDetail,
    PayrollInputListParams,
    PayrollInputPrepareResult,
    PayrollInputRead,
    PayrollInputReview,
    PayrollInputSourceRead,
    PayrollPeriodRead,
    PeriodExceptionRow,
)
from app.services.audit_service import AuditService
from app.services.payroll_calendar import dates_between, period_calendar
from app.utils.datetime import utc_now

logger = get_logger("services.payroll_input")

#: Preparation is allowed only while the period can still change. Later
#: stages exist precisely so prepared data stops moving underneath them.
_PREPARABLE_STATUSES = frozenset({PayrollPeriodStatus.OPEN.value, PayrollPeriodStatus.PROCESSING.value})

_MINUTES_PER_HOUR = Decimal("60")
_CENT = Decimal("0.01")


@dataclass
class _Computed:
    """Everything preparation derives for one employee, before persistence."""

    employee: Employee
    values: dict[str, Any]
    exceptions: list[PayrollInputException] = field(default_factory=list)
    sources: list[tuple[str, uuid.UUID, datetime]] = field(default_factory=list)
    fingerprint: str = ""


class PayrollInputService:
    """Prepares, refreshes and reviews payroll inputs for a period."""

    def __init__(
        self,
        inputs: PayrollInputRepository,
        exceptions: PayrollInputExceptionRepository,
        sources: PayrollInputSourceRepository,
        reader: PayrollSourceReader,
        periods: PayrollPeriodRepository,
        config: PayrollConfigurationRepository,
        leave_rules: PayrollLeaveRuleRepository,
        audit: AuditService,
    ) -> None:
        self.inputs = inputs
        self.exceptions = exceptions
        self.sources = sources
        self.reader = reader
        self.periods = periods
        self.config = config
        self.leave_rules = leave_rules
        self.audit = audit

    # ==================================================================
    # Preparation
    # ==================================================================
    async def prepare(self, period_id: uuid.UUID, *, actor_id: uuid.UUID) -> PayrollInputPrepareResult:
        period = await self._require_period(period_id)
        if period.status not in _PREPARABLE_STATUSES:
            raise ConflictError(
                "Inputs can be prepared only while the period is open or processing.",
                error_code="period_not_preparable",
            )
        computed = await self._compute_all(period)

        existing = {row.employee_id: row for row in await self.inputs.for_period(period.id)}
        refreshed = bool(existing)
        now = utc_now()
        counts = {status.value: 0 for status in PayrollInputStatus}

        for item in computed:
            counts[str(item.values["status"])] += 1
            row = existing.pop(item.employee.id, None)
            if row is None:
                row = await self.inputs.add(
                    PayrollInput(
                        payroll_period_id=period.id,
                        employee_id=item.employee.id,
                        prepared_at=now,
                        prepared_by_id=actor_id,
                        **item.values,
                    ),
                    actor_id=actor_id,
                )
            else:
                await self.exceptions.clear_for_input(row.id)
                await self.sources.clear_for_input(row.id)
                await self.inputs.update(
                    row,
                    {
                        **item.values,
                        "prepared_at": now,
                        "prepared_by_id": actor_id,
                        "source_changed": False,
                        "reviewed_by_id": None,
                        "reviewed_at": None,
                        "review_note": None,
                    },
                    actor_id=actor_id,
                )
            for exception in item.exceptions:
                exception.input_id = row.id
                await self.exceptions.add(exception, actor_id=actor_id)
            for source_type, source_id, source_updated_at in item.sources:
                await self.sources.add(
                    PayrollInputSource(
                        input_id=row.id,
                        source_type=source_type,
                        source_id=source_id,
                        source_updated_at=source_updated_at,
                    ),
                    actor_id=actor_id,
                )

        # Inputs whose employee left the period's scope since the last run.
        removed = 0
        for stale in existing.values():
            await self.inputs.hard_delete(stale)
            removed += 1

        await self.audit.record_success(
            AuditAction.PAYROLL_INPUTS_PREPARED,
            actor_id=actor_id,
            entity_type="payroll_period",
            entity_id=period.id,
            description=f"Prepared payroll inputs for {period.name}",
            context={
                "prepared": len(computed),
                "ready": counts[PayrollInputStatus.READY.value],
                "requires_review": counts[PayrollInputStatus.REQUIRES_REVIEW.value],
                "excluded": counts[PayrollInputStatus.EXCLUDED.value],
                "removed": removed,
                "refreshed": refreshed,
            },
        )
        return PayrollInputPrepareResult(
            prepared=len(computed),
            ready=counts[PayrollInputStatus.READY.value],
            requires_review=counts[PayrollInputStatus.REQUIRES_REVIEW.value],
            excluded=counts[PayrollInputStatus.EXCLUDED.value],
            removed=removed,
        )

    async def detect_changes(
        self, period_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> PayrollChangeDetectionResult:
        """Recompute source fingerprints; flag inputs whose sources moved."""
        period = await self._require_period(period_id)
        rows = await self.inputs.for_period(period.id)
        fingerprints = await self._current_fingerprints(period)

        flagged: list[Employee] = []
        for row in rows:
            if row.status == PayrollInputStatus.EXCLUDED.value:
                continue
            if row.source_changed:
                # Already known-stale; re-flagging it every run is noise. The
                # flag clears only when the input is prepared again.
                continue
            fresh = fingerprints.get(row.employee_id, self._fingerprint([]))
            if fresh == row.source_fingerprint:
                continue
            await self.inputs.update(
                row,
                {"status": PayrollInputStatus.REQUIRES_REVIEW.value, "source_changed": True},
                actor_id=actor_id,
            )
            flagged.append(row.employee)

        if flagged:
            await self.audit.record_success(
                AuditAction.PAYROLL_INPUTS_FLAGGED,
                actor_id=actor_id,
                entity_type="payroll_period",
                entity_id=period.id,
                description=f"Source data changed after snapshot for {len(flagged)} input(s) "
                f"in {period.name}",
                context={"flagged": len(flagged)},
            )
        return PayrollChangeDetectionResult(
            checked=len(rows),
            flagged=len(flagged),
            flagged_employees=[EmployeeSummary.model_validate(e) for e in flagged],
        )

    async def review(
        self, input_id: uuid.UUID, payload: PayrollInputReview, *, actor_id: uuid.UUID
    ) -> PayrollInputRead:
        row = await self.inputs.get(input_id)
        if row is None:
            raise NotFoundError("Payroll input")
        if row.status != PayrollInputStatus.REQUIRES_REVIEW.value:
            raise ConflictError(
                "Only an input that requires review can be marked reviewed.",
                error_code="input_not_reviewable",
            )
        # ``source_changed`` deliberately survives a review: the reviewer
        # accepted the snapshot, but the fact that the sources moved after it
        # stays visible until the input is prepared again.
        await self.inputs.update(
            row,
            {
                "status": PayrollInputStatus.READY.value,
                "reviewed_by_id": actor_id,
                "reviewed_at": utc_now(),
                "review_note": payload.note,
            },
            actor_id=actor_id,
        )
        await self.inputs.session.refresh(row, ["reviewed_by"])
        await self.audit.record_success(
            AuditAction.PAYROLL_INPUT_REVIEWED,
            actor_id=actor_id,
            entity_type="payroll_input",
            entity_id=row.id,
            description=f"Reviewed payroll input for {row.employee.full_name} ({row.period.name})",
            context={"note": payload.note, "exception_count": row.exception_count},
        )
        return self._present(row)

    # ==================================================================
    # Reads
    # ==================================================================
    async def list_inputs(
        self, period_id: uuid.UUID, params: PayrollInputListParams
    ) -> tuple[list[PayrollInputRead], int]:
        await self._require_period(period_id)
        rows, total = await self.inputs.search(period_id, params)
        return [self._present(row) for row in rows], total

    async def input_detail(self, period_id: uuid.UUID, employee_id: uuid.UUID) -> PayrollInputDetail:
        row = await self.inputs.for_period_employee(period_id, employee_id)
        if row is None:
            raise NotFoundError("Payroll input")
        sources = await self.sources.for_input(row.id)
        base = self._present(row)
        return PayrollInputDetail(
            **base.model_dump(),
            exceptions=[PayrollExceptionRead.model_validate(item) for item in row.exceptions],
            sources=[PayrollInputSourceRead.model_validate(item) for item in sources],
        )

    async def period_exceptions(self, period_id: uuid.UUID) -> list[PeriodExceptionRow]:
        await self._require_period(period_id)
        rows = await self.exceptions.for_period(period_id)
        return [
            PeriodExceptionRow(
                employee=EmployeeSummary.model_validate(item.input.employee),
                category=item.category,
                code=item.code,
                message=item.message,
                source_type=item.source_type,
                occurred_on=item.occurred_on,
            )
            for item in rows
        ]

    async def my_inputs(self, employee: Employee) -> list[PayrollInputRead]:
        rows = await self.inputs.for_employee(employee.id)
        return [self._present(row) for row in rows]

    # ==================================================================
    # The computation itself
    # ==================================================================
    async def _compute_all(self, period: PayrollPeriod) -> list[_Computed]:
        config = await self._require_config()
        today = utc_now().date()

        calendar = period_calendar(config, period.start_date, period.end_date)
        off_dates = set(calendar.off_dates)
        holiday_dates = set(calendar.holiday_dates)
        working_dates = set(calendar.working_dates)
        calendar_days = calendar.calendar_days
        working_days = calendar.working_days

        attendance = self._group(await self.reader.attendance_between(period.start_date, period.end_date))
        regularizations = self._group(
            await self.reader.regularizations_between(period.start_date, period.end_date)
        )
        leaves = self._group(
            await self.reader.approved_leaves_overlapping(period.start_date, period.end_date)
        )
        balances = self._group(await self.reader.balances_for_year(period.start_date.year))
        cases_by_employee: dict[uuid.UUID, OffboardingCase] = {}
        for offboarding_case in await self.reader.offboarding_cases_until(period.end_date):
            current = cases_by_employee.get(offboarding_case.employee_id)
            if current is None or offboarding_case.last_working_day > current.last_working_day:
                cases_by_employee[offboarding_case.employee_id] = offboarding_case
        compensation: dict[uuid.UUID, EmployeeCompensation] = {}
        for comp in await self.reader.active_compensation():
            known = compensation.get(comp.employee_id)
            if known is None or comp.effective_from > known.effective_from:
                compensation[comp.employee_id] = comp
        settings = {row.employee_id: row for row in await self.reader.all_employee_settings()}
        rules = {
            rule.leave_type_id: rule for rule in await self.leave_rules.all_rules(include_inactive=False)
        }

        results: list[_Computed] = []
        for employee in await self.reader.employees_joined_by(period.end_date):
            case = cases_by_employee.get(employee.id)
            exited_before = case is not None and case.last_working_day < period.start_date
            if employee.employment_status == EmploymentStatus.INACTIVE.value and (
                case is None or exited_before
            ):
                # Historical leavers are not this period's business at all.
                continue

            base: dict[str, object] = {
                "eligibility": PayrollEligibility.ELIGIBLE.value,
                "exclusion_reason": None,
                "joining_date": employee.joining_date,
                "exit_date": None,
                "offboarding_status": case.status if case is not None else None,
                "calendar_days": calendar_days,
                "working_days": working_days,
                "weekly_off_days": len(off_dates),
                "holiday_days": len(holiday_dates),
            }

            setting = settings.get(employee.id)
            excluded_reason: str | None = None
            eligibility = PayrollEligibility.ELIGIBLE.value
            if setting is not None and setting.eligibility != PayrollEligibility.ELIGIBLE.value:
                eligibility = setting.eligibility
                excluded_reason = (
                    (setting.eligibility_reason or setting.eligibility).replace("_", " ").capitalize()
                )
            elif exited_before:
                eligibility = PayrollEligibility.NOT_ELIGIBLE.value
                excluded_reason = (
                    f"Exited before this period (last working day {case.last_working_day.isoformat()})"
                    if case is not None
                    else "Exited before this period"
                )

            if excluded_reason is not None:
                item = _Computed(
                    employee=employee,
                    values={
                        **base,
                        **self._zero_metrics(),
                        "status": PayrollInputStatus.EXCLUDED.value,
                        "eligibility": eligibility,
                        "exclusion_reason": excluded_reason,
                        "exit_date": case.last_working_day if case is not None else None,
                        "source_fingerprint": self._fingerprint([]),
                    },
                )
                results.append(item)
                continue

            item = self._compute_one(
                employee=employee,
                period=period,
                config=config,
                today=today,
                working_dates=working_dates,
                calendar_days=calendar_days,
                base=base,
                case=case,
                attendance=attendance.get(employee.id, []),
                regularizations=regularizations.get(employee.id, []),
                leaves=leaves.get(employee.id, []),
                balances=balances.get(employee.id, []),
                comp=compensation.get(employee.id),
                setting=setting,
                rules=rules,
            )
            results.append(item)
        return results

    def _compute_one(
        self,
        *,
        employee: Employee,
        period: PayrollPeriod,
        config: PayrollConfiguration,
        today: date,
        working_dates: set[date],
        calendar_days: int,
        base: dict[str, object],
        case: OffboardingCase | None,
        attendance: list[AttendanceRecord],
        regularizations: list[AttendanceRegularization],
        leaves: list[LeaveRequest],
        balances: list[LeaveBalance],
        comp: EmployeeCompensation | None,
        setting: PayrollEmployeeSetting | None,
        rules: dict[uuid.UUID, PayrollLeaveRule],
    ) -> _Computed:
        exceptions: list[PayrollInputException] = []

        def flag(
            category: PayrollExceptionCategory,
            code: str,
            message: str,
            *,
            source_type: str | None = None,
            source_id: uuid.UUID | None = None,
            occurred_on: date | None = None,
        ) -> None:
            exceptions.append(
                PayrollInputException(
                    input_id=uuid.uuid4(),  # replaced on persist
                    category=category.value,
                    code=code,
                    message=message,
                    source_type=source_type,
                    source_id=source_id,
                    occurred_on=occurred_on,
                )
            )

        # -- Joiner / leaver window -----------------------------------
        exit_date = (
            case.last_working_day
            if case is not None and period.start_date <= case.last_working_day <= period.end_date
            else None
        )
        eligible_from = max(period.start_date, employee.joining_date)
        if comp is None:
            flag(
                PayrollExceptionCategory.COMPENSATION,
                "missing_compensation",
                "No active compensation record covers this period. Assign one before payroll runs.",
            )
        else:
            effective_from = comp.effective_from
            if eligible_from < effective_from <= period.end_date:
                # §10: the salary effective date, not the joining date alone,
                # decides when pay can start.
                eligible_from = effective_from
        eligible_to = min(period.end_date, exit_date or period.end_date)
        window = (
            set(self._dates_between(eligible_from, eligible_to)) if eligible_from <= eligible_to else set()
        )
        eligible_days = len(window)
        window_working = working_dates & window

        # -- Attendance ------------------------------------------------
        rows = [r for r in attendance if r.attendance_date in window]
        present_days = sum(1 for r in rows if r.status == AttendanceStatus.PRESENT.value)
        half_days = sum(1 for r in rows if r.status == AttendanceStatus.HALF_DAY.value)
        late_days = sum(1 for r in rows if r.late_minutes > 0)
        early_exit_days = sum(1 for r in rows if r.early_exit_minutes > 0)
        for r in rows:
            if r.status not in (AttendanceStatus.PRESENT.value, AttendanceStatus.HALF_DAY.value):
                continue
            if r.check_in_at is None:
                flag(
                    PayrollExceptionCategory.ATTENDANCE,
                    "missing_check_in",
                    f"{r.attendance_date.isoformat()}: marked {r.status} with no check-in.",
                    source_type=PayrollSourceType.ATTENDANCE.value,
                    source_id=r.id,
                    occurred_on=r.attendance_date,
                )
            elif r.check_out_at is None and r.attendance_date < today:
                flag(
                    PayrollExceptionCategory.ATTENDANCE,
                    "missing_check_out",
                    f"{r.attendance_date.isoformat()}: checked in but never out.",
                    source_type=PayrollSourceType.ATTENDANCE.value,
                    source_id=r.id,
                    occurred_on=r.attendance_date,
                )
        approved_regularization_dates: set[date] = set()
        for reg in regularizations:
            if reg.attendance_date not in window:
                continue
            if reg.status == ApprovalStatus.PENDING.value:
                flag(
                    PayrollExceptionCategory.ATTENDANCE,
                    "unresolved_regularization",
                    f"{reg.attendance_date.isoformat()}: an attendance correction is awaiting a decision.",
                    source_type=PayrollSourceType.REGULARIZATION.value,
                    source_id=reg.id,
                    occurred_on=reg.attendance_date,
                )
            elif reg.status == ApprovalStatus.APPROVED.value:
                approved_regularization_dates.add(reg.attendance_date)

        # -- Leave ------------------------------------------------------
        paid_leave = Decimal("0")
        unpaid_leave = Decimal("0")
        leave_dates: set[date] = set()
        claimed_full_days: set[date] = set()
        for request in leaves:
            overlap_from = max(request.from_date, eligible_from)
            overlap_to = min(request.to_date, eligible_to)
            if overlap_from > overlap_to:
                continue
            request_dates = {d for d in self._dates_between(overlap_from, overlap_to) if d in working_dates}
            if not request_dates:
                continue
            factor = Decimal("1") if request.day_part == "full_day" else Decimal("0.5")
            days = Decimal(len(request_dates)) * factor

            leave_type = request.leave_type
            if leave_type.status != RecordStatus.ACTIVE.value:
                flag(
                    PayrollExceptionCategory.LEAVE,
                    "invalid_leave_type",
                    f"Approved leave uses the deactivated type {leave_type.name}.",
                    source_type=PayrollSourceType.LEAVE_REQUEST.value,
                    source_id=request.id,
                    occurred_on=overlap_from,
                )
            rule = rules.get(request.leave_type_id)
            treats_unpaid = (
                rule.treatment == LeaveTreatment.UNPAID.value if rule is not None else not leave_type.is_paid
            )
            if treats_unpaid:
                unpaid_leave += days
            else:
                paid_leave += days

            if factor == Decimal("1"):
                doubled = claimed_full_days & request_dates
                if doubled:
                    flag(
                        PayrollExceptionCategory.LEAVE,
                        "overlapping_leave",
                        f"Two approved leave requests both cover {min(doubled).isoformat()}.",
                        source_type=PayrollSourceType.LEAVE_REQUEST.value,
                        source_id=request.id,
                        occurred_on=min(doubled),
                    )
                claimed_full_days |= request_dates
            leave_dates |= request_dates

        for balance in balances:
            if balance.remaining < 0 and not balance.leave_type.allows_negative:
                flag(
                    PayrollExceptionCategory.LEAVE,
                    "negative_leave_balance",
                    f"{balance.leave_type.name}: balance is {balance.remaining} days.",
                )

        # -- Absence -----------------------------------------------------
        countable = {d for d in window_working if d <= today}
        attended = {r.attendance_date for r in rows}
        absent_days = len(countable - attended - leave_dates)

        # -- Overtime -----------------------------------------------------
        overtime_eligible = (
            setting.overtime_eligible
            if setting is not None and setting.overtime_eligible is not None
            else config.overtime_enabled
        )
        total_ot = Decimal("0")
        approved_ot = Decimal("0")
        pending_ot = Decimal("0")
        for r in rows:
            if r.overtime_minutes <= 0:
                continue
            hours = (Decimal(r.overtime_minutes) / _MINUTES_PER_HOUR).quantize(_CENT)
            total_ot += hours
            if config.overtime_max_hours is not None and hours > config.overtime_max_hours:
                flag(
                    PayrollExceptionCategory.OVERTIME,
                    "overtime_above_maximum",
                    f"{r.attendance_date.isoformat()}: {hours}h overtime exceeds the configured "
                    f"maximum of {config.overtime_max_hours}h.",
                    source_type=PayrollSourceType.ATTENDANCE.value,
                    source_id=r.id,
                    occurred_on=r.attendance_date,
                )
            if hours < config.overtime_min_hours:
                continue  # below the threshold: recorded in the total, paid never
            if config.overtime_approval_required and r.attendance_date not in approved_regularization_dates:
                pending_ot += hours
            else:
                approved_ot += hours
        if pending_ot > 0:
            flag(
                PayrollExceptionCategory.OVERTIME,
                "unapproved_overtime",
                f"{pending_ot}h of overtime has no approved attendance correction behind it.",
            )
        if total_ot > 0 and not overtime_eligible:
            flag(
                PayrollExceptionCategory.OVERTIME,
                "overtime_not_eligible",
                f"{total_ot}h of overtime was recorded, but this employee is not overtime-eligible.",
            )

        # -- Snapshot bookkeeping ------------------------------------------
        source_lines: list[tuple[str, uuid.UUID, datetime]] = [
            (PayrollSourceType.ATTENDANCE.value, r.id, r.updated_at) for r in attendance
        ]
        source_lines += [
            (PayrollSourceType.REGULARIZATION.value, reg.id, reg.updated_at) for reg in regularizations
        ]
        source_lines += [
            (PayrollSourceType.LEAVE_REQUEST.value, request.id, request.updated_at) for request in leaves
        ]
        fingerprint = self._fingerprint(source_lines)

        unpaid_deduction = (
            setting.unpaid_leave_deduction
            if setting is not None and setting.unpaid_leave_deduction is not None
            else config.unpaid_leave_treatment == UnpaidLeaveTreatment.DEDUCT.value
        )

        values: dict[str, Any] = {
            **base,
            "status": (
                PayrollInputStatus.REQUIRES_REVIEW.value if exceptions else PayrollInputStatus.READY.value
            ),
            "exit_date": exit_date,
            "eligible_days": eligible_days,
            "non_eligible_days": calendar_days - eligible_days,
            "proration_required": eligible_days < calendar_days,
            "present_days": present_days,
            "half_days": half_days,
            "absent_days": absent_days,
            "late_days": late_days,
            "early_exit_days": early_exit_days,
            "paid_leave_days": paid_leave,
            "unpaid_leave_days": unpaid_leave,
            "unpaid_leave_deduction": unpaid_deduction,
            "unpaid_leave_basis": (config.unpaid_leave_basis if unpaid_deduction else None),
            "overtime_hours": total_ot,
            "approved_overtime_hours": approved_ot,
            "pending_overtime_hours": pending_ot,
            "overtime_eligible": bool(overtime_eligible),
            "exception_count": len(exceptions),
            "source_fingerprint": fingerprint,
        }
        return _Computed(
            employee=employee,
            values=values,
            exceptions=exceptions,
            sources=source_lines,
            fingerprint=fingerprint,
        )

    async def _current_fingerprints(self, period: PayrollPeriod) -> dict[uuid.UUID, str]:
        """The fingerprint each employee's sources WOULD produce right now."""
        lines: dict[uuid.UUID, list[tuple[str, uuid.UUID, datetime]]] = defaultdict(list)
        for r in await self.reader.attendance_between(period.start_date, period.end_date):
            lines[r.employee_id].append((PayrollSourceType.ATTENDANCE.value, r.id, r.updated_at))
        for reg in await self.reader.regularizations_between(period.start_date, period.end_date):
            lines[reg.employee_id].append((PayrollSourceType.REGULARIZATION.value, reg.id, reg.updated_at))
        for request in await self.reader.approved_leaves_overlapping(period.start_date, period.end_date):
            lines[request.employee_id].append(
                (PayrollSourceType.LEAVE_REQUEST.value, request.id, request.updated_at)
            )
        return {employee_id: self._fingerprint(items) for employee_id, items in lines.items()}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _require_period(self, period_id: uuid.UUID) -> PayrollPeriod:
        period = await self.periods.get(period_id)
        if period is None:
            raise NotFoundError("Payroll period")
        return period

    async def _require_config(self) -> PayrollConfiguration:
        config = await self.config.singleton()
        if config is None:  # pragma: no cover - seeded by the migration
            raise NotFoundError("Payroll configuration")
        return config

    @staticmethod
    def _dates_between(start: date, end: date) -> list[date]:
        return dates_between(start, end)

    @staticmethod
    def _fingerprint(lines: list[tuple[str, uuid.UUID, datetime]]) -> str:
        canonical = "|".join(
            sorted(f"{source_type}:{source_id}:{updated_at}" for source_type, source_id, updated_at in lines)
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _group[RowT](rows: Sequence[RowT]) -> dict[uuid.UUID, list[RowT]]:
        grouped: dict[uuid.UUID, list[RowT]] = defaultdict(list)
        for row in rows:
            grouped[row.employee_id].append(row)  # type: ignore[attr-defined]
        return dict(grouped)

    @staticmethod
    def _zero_metrics() -> dict[str, Any]:
        return {
            "eligible_days": 0,
            "non_eligible_days": 0,
            "proration_required": False,
            "present_days": 0,
            "half_days": 0,
            "absent_days": 0,
            "late_days": 0,
            "early_exit_days": 0,
            "paid_leave_days": Decimal("0"),
            "unpaid_leave_days": Decimal("0"),
            "unpaid_leave_deduction": False,
            "unpaid_leave_basis": None,
            "overtime_hours": Decimal("0"),
            "approved_overtime_hours": Decimal("0"),
            "pending_overtime_hours": Decimal("0"),
            "overtime_eligible": False,
            "exception_count": 0,
        }

    def _present(self, row: PayrollInput) -> PayrollInputRead:
        return PayrollInputRead(
            id=row.id,
            period=PayrollPeriodRead.model_validate(row.period),
            employee=EmployeeSummary.model_validate(row.employee),
            status=PayrollInputStatus(row.status),
            eligibility=PayrollEligibility(row.eligibility),
            exclusion_reason=row.exclusion_reason,
            joining_date=row.joining_date,
            exit_date=row.exit_date,
            offboarding_status=row.offboarding_status,
            eligible_days=row.eligible_days,
            non_eligible_days=row.non_eligible_days,
            proration_required=row.proration_required,
            calendar_days=row.calendar_days,
            working_days=row.working_days,
            weekly_off_days=row.weekly_off_days,
            holiday_days=row.holiday_days,
            present_days=row.present_days,
            half_days=row.half_days,
            absent_days=row.absent_days,
            late_days=row.late_days,
            early_exit_days=row.early_exit_days,
            paid_leave_days=row.paid_leave_days,
            unpaid_leave_days=row.unpaid_leave_days,
            unpaid_leave_deduction=row.unpaid_leave_deduction,
            unpaid_leave_basis=(PayrollDayBasis(row.unpaid_leave_basis) if row.unpaid_leave_basis else None),
            overtime_hours=row.overtime_hours,
            approved_overtime_hours=row.approved_overtime_hours,
            pending_overtime_hours=row.pending_overtime_hours,
            overtime_eligible=row.overtime_eligible,
            exception_count=row.exception_count,
            source_changed=row.source_changed,
            prepared_at=row.prepared_at,
            reviewed_at=row.reviewed_at,
            reviewed_by_name=(
                f"{row.reviewed_by.first_name} {row.reviewed_by.last_name}".strip()
                if row.reviewed_by is not None
                else None
            ),
            review_note=row.review_note,
        )
