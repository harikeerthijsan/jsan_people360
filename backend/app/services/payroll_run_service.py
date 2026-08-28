"""The monthly payroll calculation engine (Phase 4).

Five rules shape it.

**The snapshot is the source of truth.** The engine reads the Phase 3 payroll
inputs — never raw attendance or leave — and refuses to compute for an input
that is flagged or stale. An engine that quietly re-derived what the snapshot
already validated would make the snapshot a decoration.

**Configuration decides, the engine obeys.** Proration basis, rounding rule,
overtime multiplier, standard daily hours, per-component behaviour flags —
all come from Phases 1-3. Nothing here hardcodes "HRA = 40%" or a calendar
month; the one number the engine contributes is arithmetic.

**When it cannot be sure, it refuses.** A missing salary, records that leave
part of the period uncovered, two records claiming the same day, a zero-day
proration basis: each produces a ``requires_review`` record with a stated
reason and zero amounts. There is no code path that guesses.

**Every amount carries its derivation.** A record is its line items; each
line stores the basis it was computed on ("40% of basic · 15/31 calendar
days"). The final numbers are: quantize each line to the cent, sum, apply
the configured rounding to the sums, net = gross - deductions.

**Recalculation replaces, never accumulates.** A run's records are derived
rows: recalculating deletes and rebuilds them inside one transaction, and
the UNIQUE(run, employee) constraint makes duplication impossible even if
two requests race.

Component-value semantics, stated once: a fixed component's snapshot value is
its amount **per month**; a percentage component's value is a rate against
the compensation record's monthly basic or monthly gross. Mid-period salary
revisions split the period into segments, each priced from its own record.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.audit_log import AuditAction
from app.models.employee import Employee
from app.models.enums import (
    LOCKED_RUN_STATUSES,
    RECALCULABLE_RUN_STATUSES,
    PayrollAdjustmentStatus,
    PayrollDayBasis,
    PayrollExceptionSeverity,
    PayrollExceptionStatus,
    PayrollInputStatus,
    PayrollItemType,
    PayrollLineSource,
    PayrollPeriodStatus,
    PayrollRecordStatus,
    PayrollRunExceptionType,
    PayrollRunStatus,
    PercentageBasis,
    RoundingRule,
    SalaryCalculationType,
    SalaryComponentType,
)
from app.models.payroll import (
    EmployeeCompensation,
    PayrollAdjustment,
    PayrollConfiguration,
    PayrollEmployeeRecord,
    PayrollEmployeeSetting,
    PayrollInput,
    PayrollLineItem,
    PayrollRun,
    PayrollRunException,
)
from app.models.user import User
from app.repositories.payroll_repository import (
    EmployeeCompensationRepository,
    PayrollAdjustmentRepository,
    PayrollConfigurationRepository,
    PayrollEmployeeRecordRepository,
    PayrollInputRepository,
    PayrollLineItemRepository,
    PayrollPeriodRepository,
    PayrollReviewChecklistRepository,
    PayrollRunExceptionRepository,
    PayrollRunRepository,
    PayrollSourceReader,
)
from app.schemas.payroll import (
    EmployeeSummary,
    PayrollAdjustmentRead,
    PayrollCalculationResult,
    PayrollLineItemRead,
    PayrollPeriodRead,
    PayrollRecordDetail,
    PayrollRecordListParams,
    PayrollRecordRead,
    PayrollRunCreate,
    PayrollRunListParams,
    PayrollRunRead,
)
from app.services.audit_service import AuditService
from app.services.payroll_calendar import PeriodCalendar, dates_between, period_calendar
from app.utils.datetime import utc_now

logger = get_logger("services.payroll_run")

_CENT = Decimal("0.01")
_HUNDRED = Decimal("100")

_BASIS_LABELS = {
    PayrollDayBasis.CALENDAR_DAYS.value: "calendar days",
    PayrollDayBasis.WORKING_DAYS.value: "working days",
}


@dataclass
class _Line:
    item_type: str
    source: str
    component_id: uuid.UUID | None
    code: str
    name: str
    calculation_basis: str
    amount: Decimal
    original_amount: Decimal | None = None
    prorated: bool = False


@dataclass
class _ComponentTotal:
    """One component accumulated across salary segments."""

    component_id: uuid.UUID
    code: str
    name: str
    item_type: str
    proration_allowed: bool
    leave_impact: bool
    overtime_base: bool
    amount: Decimal = Decimal("0")
    monthly_reference: Decimal = Decimal("0")
    basis_parts: list[str] = field(default_factory=list)
    prorated: bool = False
    order: int = 0


#: How Phase 3 input-exception codes translate into reviewable run
#: exceptions: (type, severity). Severity is a review judgement, not an
#: engine one — critical is reserved for issues that produced no numbers.
_INPUT_EXCEPTION_MAP: dict[str, tuple[str, str]] = {
    "missing_check_in": (
        PayrollRunExceptionType.MISSING_ATTENDANCE.value,
        PayrollExceptionSeverity.WARNING.value,
    ),
    "missing_check_out": (
        PayrollRunExceptionType.MISSING_ATTENDANCE.value,
        PayrollExceptionSeverity.WARNING.value,
    ),
    "unresolved_regularization": (
        PayrollRunExceptionType.UNRESOLVED_CORRECTION.value,
        PayrollExceptionSeverity.ERROR.value,
    ),
    "unapproved_overtime": (
        PayrollRunExceptionType.UNAPPROVED_OVERTIME.value,
        PayrollExceptionSeverity.ERROR.value,
    ),
    "overtime_not_eligible": (
        PayrollRunExceptionType.UNAPPROVED_OVERTIME.value,
        PayrollExceptionSeverity.ERROR.value,
    ),
    "overtime_above_maximum": (
        PayrollRunExceptionType.UNAPPROVED_OVERTIME.value,
        PayrollExceptionSeverity.WARNING.value,
    ),
    "negative_leave_balance": (
        PayrollRunExceptionType.NEGATIVE_LEAVE_BALANCE.value,
        PayrollExceptionSeverity.WARNING.value,
    ),
    "invalid_leave_type": (
        PayrollRunExceptionType.INVALID_LEAVE.value,
        PayrollExceptionSeverity.ERROR.value,
    ),
    "overlapping_leave": (
        PayrollRunExceptionType.INVALID_LEAVE.value,
        PayrollExceptionSeverity.ERROR.value,
    ),
    "missing_compensation": (
        PayrollRunExceptionType.MISSING_SALARY.value,
        PayrollExceptionSeverity.CRITICAL.value,
    ),
}


class _Refusal(Exception):
    """Internal: the engine cannot compute this employee safely."""

    def __init__(self, reason: str, exception_type: str = PayrollRunExceptionType.OTHER.value) -> None:
        self.reason = reason
        self.exception_type = exception_type
        super().__init__(reason)


def user_name(user: User | None) -> str | None:
    """First-and-last display name, shared by every payroll presenter."""
    if user is None:
        return None
    return f"{user.first_name} {user.last_name}".strip()


def present_run(
    run: PayrollRun,
    exception_counts: tuple[int, int] = (0, 0),
    adjustment_count: int = 0,
) -> PayrollRunRead:
    """Shared presenter — the run pages, the approval queue and the history
    must agree on what a run looks like."""
    return PayrollRunRead(
        id=run.id,
        run_code=run.run_code,
        period=PayrollPeriodRead.model_validate(run.period),
        status=PayrollRunStatus(run.status),
        currency=run.currency,
        employee_count=run.employee_count,
        calculated_count=run.calculated_count,
        review_count=run.review_count,
        excluded_count=run.excluded_count,
        total_gross=run.total_gross,
        total_deductions=run.total_deductions,
        total_net=run.total_net,
        calculated_at=run.calculated_at,
        calculated_by_name=user_name(run.calculated_by),
        notes=run.notes,
        created_at=run.created_at,
        open_exception_count=exception_counts[0],
        open_critical_count=exception_counts[1],
        review_completed_at=run.review_completed_at,
        review_completed_by_name=user_name(run.review_completed_by),
        submitted_at=run.submitted_at,
        submitted_by_name=user_name(run.submitted_by),
        approved_at=run.approved_at,
        approved_by_name=user_name(run.approved_by),
        approval_comment=run.approval_comment,
        returned_at=run.returned_at,
        returned_by_name=user_name(run.returned_by),
        return_reason=run.return_reason,
        finalized_at=run.finalized_at,
        finalized_by_name=user_name(run.finalized_by),
        adjustment_count=adjustment_count,
    )


def present_adjustment(row: PayrollAdjustment) -> PayrollAdjustmentRead:
    """Shared presenter — record detail and the review screens must agree."""
    return PayrollAdjustmentRead(
        id=row.id,
        run_id=row.run_id,
        employee=EmployeeSummary.model_validate(row.employee),
        item_type=PayrollItemType(row.item_type),
        name=row.name,
        amount=row.amount,
        reason=row.reason,
        notes=row.notes,
        status=PayrollAdjustmentStatus(row.status),
        previous_net=row.previous_net,
        new_net=row.new_net,
        created_at=row.created_at,
        cancelled_at=row.cancelled_at,
        cancel_reason=row.cancel_reason,
    )


class PayrollRunService:
    """Creates payroll runs and computes their records."""

    def __init__(
        self,
        runs: PayrollRunRepository,
        records: PayrollEmployeeRecordRepository,
        lines: PayrollLineItemRepository,
        inputs: PayrollInputRepository,
        periods: PayrollPeriodRepository,
        config: PayrollConfigurationRepository,
        compensation: EmployeeCompensationRepository,
        reader: PayrollSourceReader,
        audit: AuditService,
        run_exceptions: PayrollRunExceptionRepository,
        adjustments: PayrollAdjustmentRepository,
        checklists: PayrollReviewChecklistRepository,
    ) -> None:
        self.runs = runs
        self.records = records
        self.lines = lines
        self.inputs = inputs
        self.periods = periods
        self.config = config
        self.compensation = compensation
        self.reader = reader
        self.audit = audit
        self.run_exceptions = run_exceptions
        self.adjustments = adjustments
        self.checklists = checklists

    # ==================================================================
    # Runs
    # ==================================================================
    async def list_runs(self, params: PayrollRunListParams) -> tuple[list[PayrollRunRead], int]:
        rows, total = await self.runs.search(params)
        counts = await self.run_exceptions.open_counts([row.id for row in rows])
        return [self._present_run(row, counts.get(row.id, (0, 0))) for row in rows], total

    async def get_run(self, run_id: uuid.UUID) -> PayrollRunRead:
        run = await self._require_run(run_id)
        counts = await self.run_exceptions.open_counts([run.id])
        return self._present_run(run, counts.get(run.id, (0, 0)))

    async def create_run(self, payload: PayrollRunCreate, *, actor_id: uuid.UUID) -> PayrollRunRead:
        period = await self.periods.get(payload.payroll_period_id)
        if period is None:
            raise NotFoundError("Payroll period")
        if period.status == PayrollPeriodStatus.CANCELLED.value:
            raise ConflictError(
                "A cancelled period cannot have a payroll run.", error_code="period_cancelled"
            )
        if await self.runs.by_period(period.id) is not None:
            raise ConflictError(
                "This period already has a payroll run. Recalculate it instead.",
                error_code="duplicate_run",
            )
        config = await self._require_config()
        run = await self.runs.add(
            PayrollRun(
                payroll_period_id=period.id,
                status=PayrollRunStatus.DRAFT.value,
                currency=config.currency,
                notes=payload.notes,
            ),
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.PAYROLL_RUN_CREATED,
            actor_id=actor_id,
            entity_type="payroll_run",
            entity_id=run.id,
            description=f"Created payroll run {run.run_code} for {period.name}",
        )
        return self._present_run(run)

    # ==================================================================
    # Calculation
    # ==================================================================
    async def calculate(
        self, run_id: uuid.UUID, *, actor_id: uuid.UUID, recalculation: bool
    ) -> PayrollCalculationResult:
        run = await self._require_run(run_id)
        if run.status in LOCKED_RUN_STATUSES:
            # The numbers an approver is looking at — or has approved, or
            # finalized — cannot move. The attempt itself goes on record,
            # and the audit row survives the request's rollback.
            await self.audit.record_failure(
                AuditAction.PAYROLL_LOCKED_MODIFICATION,
                actor_id=actor_id,
                entity_type="payroll_run",
                entity_id=run.id,
                description=(
                    f"Refused {'recalculation' if recalculation else 'calculation'} of "
                    f"{run.status} payroll run {run.run_code}"
                ),
            )
            error = ConflictError(
                "This run is locked — submitted, approved or finalized payroll cannot be " "recalculated.",
                error_code="run_locked",
            )
            error.preserve_writes = True
            raise error
        if run.status not in RECALCULABLE_RUN_STATUSES:
            raise ConflictError("This run can no longer be recalculated.", error_code="run_not_recalculable")
        existing = await self.records.for_run(run.id)
        if not recalculation and existing:
            raise ConflictError(
                "This run has already been calculated. Use recalculate.",
                error_code="already_calculated",
            )
        if recalculation and not existing:
            raise ConflictError(
                "Nothing to recalculate yet. Calculate the run first.",
                error_code="not_yet_calculated",
            )

        period = run.period
        config = await self._require_config()
        calendar = period_calendar(config, period.start_date, period.end_date)

        input_rows = await self.inputs.for_period(period.id)
        if not input_rows:
            raise ConflictError(
                "No payroll inputs exist for this period. Prepare inputs first.",
                error_code="inputs_not_prepared",
            )

        compensation_by_employee: dict[uuid.UUID, list[EmployeeCompensation]] = {}
        for comp in await self.reader.compensation_overlapping(period.start_date, period.end_date):
            compensation_by_employee.setdefault(comp.employee_id, []).append(comp)
        settings = {row.employee_id: row for row in await self.reader.all_employee_settings()}

        # Exception resolutions must survive a recalculation: snapshot them
        # before the regenerate, keyed by what the reviewer actually resolved.
        resolved_before: dict[tuple[uuid.UUID, str, str], PayrollRunException] = {
            (row.employee_id, row.exception_type, row.description): row
            for row in await self.run_exceptions.for_run(run.id)
            if row.status == PayrollExceptionStatus.RESOLVED.value
        }
        await self.run_exceptions.clear_for_run(run.id)

        # Idempotency: derived rows are replaced whole, inside this request's
        # transaction. UNIQUE(run, employee) backs it up against races.
        await self.records.clear_for_run(run.id)

        counts = {status.value: 0 for status in PayrollRecordStatus}
        total_gross = Decimal("0")
        total_deductions = Decimal("0")
        total_net = Decimal("0")
        stored_by_employee: dict[uuid.UUID, PayrollEmployeeRecord] = {}
        open_exceptions = 0
        open_critical = 0

        for input_row in input_rows:
            record, lines, exceptions = self._calculate_one(
                input_row=input_row,
                period_start=period.start_date,
                period_end=period.end_date,
                config=config,
                calendar=calendar,
                compensation=sorted(
                    compensation_by_employee.get(input_row.employee_id, []),
                    key=lambda comp: comp.effective_from,
                ),
                setting=settings.get(input_row.employee_id),
            )
            record.run_id = run.id
            stored = await self.records.add(record, actor_id=actor_id)
            stored_by_employee[stored.employee_id] = stored
            for order, line in enumerate(lines):
                await self.lines.add(
                    PayrollLineItem(
                        record_id=stored.id,
                        item_type=line.item_type,
                        source=line.source,
                        component_id=line.component_id,
                        code=line.code,
                        name=line.name,
                        calculation_basis=line.calculation_basis,
                        original_amount=line.original_amount,
                        prorated=line.prorated,
                        amount=line.amount,
                        sort_order=order,
                    ),
                    actor_id=actor_id,
                )
            seen: set[tuple[str, str]] = set()
            for exc_type, severity, description in exceptions:
                if (exc_type, description) in seen:
                    continue
                seen.add((exc_type, description))
                carried = resolved_before.get((input_row.employee_id, exc_type, description))
                row = PayrollRunException(
                    run_id=run.id,
                    employee_id=input_row.employee_id,
                    exception_type=exc_type,
                    severity=severity,
                    description=description,
                )
                if carried is not None:
                    row.status = PayrollExceptionStatus.RESOLVED.value
                    row.resolution = carried.resolution
                    row.resolution_notes = carried.resolution_notes
                    row.resolved_by_id = carried.resolved_by_id
                    row.resolved_at = carried.resolved_at
                else:
                    open_exceptions += 1
                    if severity == PayrollExceptionSeverity.CRITICAL.value:
                        open_critical += 1
                await self.run_exceptions.add(row, actor_id=actor_id)
            counts[stored.status] += 1
            total_gross += stored.gross_earnings
            total_deductions += stored.total_deductions
            total_net += stored.net_pay

        # Adjustments are additive review inputs, keyed by employee — they
        # survive the record rebuild and are re-applied to the fresh rows,
        # and the run's headline totals stay the sum of final pay.
        for adjustment in await self.adjustments.for_run(run.id, include_cancelled=False):
            target = stored_by_employee.get(adjustment.employee_id)
            if target is None or target.status == PayrollRecordStatus.EXCLUDED.value:
                continue
            if adjustment.item_type == PayrollItemType.EARNING.value:
                values = {"adjustment_earnings": target.adjustment_earnings + adjustment.amount}
                total_gross += adjustment.amount
                total_net += adjustment.amount
            else:
                values = {"adjustment_deductions": target.adjustment_deductions + adjustment.amount}
                total_deductions += adjustment.amount
                total_net -= adjustment.amount
            await self.records.update(target, values, actor_id=actor_id)

        # Rebuilt numbers invalidate prior sign-off: the checklist starts over.
        for item in await self.checklists.for_run(run.id):
            if item.completed:
                await self.checklists.update(
                    item,
                    {"completed": False, "completed_by_id": None, "completed_at": None},
                    actor_id=actor_id,
                )

        review = counts[PayrollRecordStatus.REQUIRES_REVIEW.value]
        await self.runs.update(
            run,
            {
                "status": (
                    PayrollRunStatus.REQUIRES_REVIEW.value
                    if review > 0
                    else PayrollRunStatus.CALCULATED.value
                ),
                "currency": config.currency,
                "employee_count": len(input_rows),
                "calculated_count": counts[PayrollRecordStatus.CALCULATED.value],
                "review_count": review,
                "excluded_count": counts[PayrollRecordStatus.EXCLUDED.value],
                "total_gross": total_gross,
                "total_deductions": total_deductions,
                "total_net": total_net,
                "calculated_at": utc_now(),
                "calculated_by_id": actor_id,
            },
            actor_id=actor_id,
        )
        await self.runs.session.refresh(run, ["calculated_by"])

        await self.audit.record_success(
            (AuditAction.PAYROLL_RUN_RECALCULATED if recalculation else AuditAction.PAYROLL_RUN_CALCULATED),
            actor_id=actor_id,
            entity_type="payroll_run",
            entity_id=run.id,
            description=(
                f"{'Recalculated' if recalculation else 'Calculated'} payroll run {run.run_code} "
                f"({run.period.name})"
            ),
            context={
                "employees": len(input_rows),
                "calculated": counts[PayrollRecordStatus.CALCULATED.value],
                "requires_review": review,
                "excluded": counts[PayrollRecordStatus.EXCLUDED.value],
            },
        )
        return PayrollCalculationResult(
            run=self._present_run(run, (open_exceptions, open_critical)),
            calculated=counts[PayrollRecordStatus.CALCULATED.value],
            requires_review=review,
            excluded=counts[PayrollRecordStatus.EXCLUDED.value],
        )

    # ==================================================================
    # Per-employee calculation
    # ==================================================================
    def _calculate_one(
        self,
        *,
        input_row: PayrollInput,
        period_start: date,
        period_end: date,
        config: PayrollConfiguration,
        calendar: PeriodCalendar,
        compensation: list[EmployeeCompensation],
        setting: PayrollEmployeeSetting | None,
    ) -> tuple[PayrollEmployeeRecord, list[_Line], list[tuple[str, str, str]]]:
        base = PayrollEmployeeRecord(
            employee_id=input_row.employee_id,
            payroll_input_id=input_row.id,
            currency=config.currency,
            calendar_days=input_row.calendar_days,
            working_days=input_row.working_days,
            eligible_days=input_row.eligible_days,
            present_days=input_row.present_days,
            paid_leave_days=input_row.paid_leave_days,
            unpaid_leave_days=input_row.unpaid_leave_days,
        )

        if input_row.status == PayrollInputStatus.EXCLUDED.value:
            base.status = PayrollRecordStatus.EXCLUDED.value
            base.exception_reason = input_row.exclusion_reason or "Excluded from payroll"
            return base, [], []

        # The Phase 3 input exceptions become reviewable run exceptions so
        # reviewers see *why* an input needed attention, graded by severity.
        exceptions: list[tuple[str, str, str]] = []
        for input_exception in input_row.exceptions:
            mapped = _INPUT_EXCEPTION_MAP.get(input_exception.code)
            if mapped is None:
                mapped = (
                    PayrollRunExceptionType.MISSING_INPUT.value,
                    PayrollExceptionSeverity.WARNING.value,
                )
            exceptions.append((mapped[0], mapped[1], input_exception.message))

        try:
            if input_row.status == PayrollInputStatus.REQUIRES_REVIEW.value or input_row.source_changed:
                raise _Refusal(
                    "The payroll input requires review — resolve its exceptions or re-prepare "
                    "inputs before calculating.",
                    PayrollRunExceptionType.MISSING_INPUT.value,
                )
            record, lines = self._compute(
                base=base,
                input_row=input_row,
                period_start=period_start,
                period_end=period_end,
                config=config,
                calendar=calendar,
                compensation=compensation,
                setting=setting,
            )
            return record, lines, exceptions
        except _Refusal as refusal:
            base.status = PayrollRecordStatus.REQUIRES_REVIEW.value
            base.exception_reason = refusal.reason
            base.gross_earnings = Decimal("0")
            base.total_deductions = Decimal("0")
            base.net_pay = Decimal("0")
            exceptions.append(
                (refusal.exception_type, PayrollExceptionSeverity.CRITICAL.value, refusal.reason)
            )
            return base, [], exceptions

    def _compute(
        self,
        *,
        base: PayrollEmployeeRecord,
        input_row: PayrollInput,
        period_start: date,
        period_end: date,
        config: PayrollConfiguration,
        calendar: PeriodCalendar,
        compensation: list[EmployeeCompensation],
        setting: PayrollEmployeeSetting | None,
    ) -> tuple[PayrollEmployeeRecord, list[_Line]]:
        # -- The eligible window and its salary segments ------------------
        window_from = max(period_start, input_row.joining_date or period_start)
        window_to = min(period_end, input_row.exit_date or period_end)
        if window_from > window_to:
            raise _Refusal("The employee has no eligible day inside this period.")
        window_dates = set(dates_between(window_from, window_to))

        if not compensation:
            raise _Refusal(
                "No compensation record covers this period. Assign a salary first.",
                PayrollRunExceptionType.MISSING_SALARY.value,
            )

        segments: list[tuple[EmployeeCompensation, set[date]]] = []
        for comp in compensation:
            seg_from = max(comp.effective_from, window_from)
            seg_to = min(comp.effective_to or window_to, window_to)
            if seg_from > seg_to:
                continue
            segments.append((comp, set(dates_between(seg_from, seg_to))))
        if not segments:
            raise _Refusal(
                "No compensation record is effective inside the eligible window. "
                "Check the salary effective dates.",
                PayrollRunExceptionType.MISSING_SALARY.value,
            )
        covered: set[date] = set()
        for _comp, seg_dates in segments:
            if covered & seg_dates:
                raise _Refusal(
                    "Two salary records claim the same day of this period. "
                    "Resolve the conflicting compensation records.",
                    PayrollRunExceptionType.INVALID_COMPENSATION.value,
                )
            covered |= seg_dates
        missing = window_dates - covered
        if missing:
            raise _Refusal(
                f"Salary records leave {len(missing)} day(s) of the eligible window uncovered "
                f"(from {min(missing).isoformat()}). Check the salary effective dates.",
                PayrollRunExceptionType.INVALID_COMPENSATION.value,
            )

        # -- Proration --------------------------------------------------------
        proration_basis = (
            setting.proration_override
            if setting is not None and setting.proration_override is not None
            else config.proration_basis
        )
        denominator = calendar.basis_days(proration_basis)
        if denominator <= 0:
            raise _Refusal(
                "The proration basis resolves to zero days for this period. "
                "Check the working-days and weekly-off configuration."
            )
        basis_label = _BASIS_LABELS[PayrollDayBasis(proration_basis).value]
        last_comp = segments[-1][0]

        # -- Components across segments ----------------------------------------
        totals: dict[str, _ComponentTotal] = {}
        order = 0
        for comp, seg_dates in segments:
            numerator = calendar.basis_days_in(proration_basis, seg_dates)
            factor = Decimal(numerator) / Decimal(denominator)
            is_last = comp is last_comp
            for row in comp.components:
                master = row.component
                monthly = self._monthly_amount(row.calculation_type, row.value, row.percentage_basis, comp)
                entry = totals.get(master.code)
                if entry is None:
                    entry = _ComponentTotal(
                        component_id=master.id,
                        code=master.code,
                        name=master.name,
                        item_type=(
                            PayrollItemType.EARNING.value
                            if master.component_type == SalaryComponentType.EARNING.value
                            else PayrollItemType.DEDUCTION.value
                        ),
                        proration_allowed=master.proration_allowed,
                        leave_impact=master.leave_impact,
                        overtime_base=master.overtime_eligible,
                        order=order,
                    )
                    totals[master.code] = entry
                    order += 1
                description = self._value_description(row.calculation_type, row.value, row.percentage_basis)
                if master.proration_allowed:
                    entry.amount += monthly * factor
                    if factor < 1:
                        entry.prorated = True
                        description += f" · {numerator}/{denominator} {basis_label}"
                elif is_last:
                    # Non-prorated components are paid once, at the value of
                    # the record in force at the end of the window.
                    entry.amount += monthly
                if is_last:
                    entry.monthly_reference = monthly
                if description not in entry.basis_parts:
                    entry.basis_parts.append(description)

        lines: list[_Line] = []
        for entry in sorted(totals.values(), key=lambda item: item.order):
            if entry.item_type != PayrollItemType.EARNING.value:
                continue
            lines.append(self._component_line(entry, len(segments) > 1))
        # -- Overtime -----------------------------------------------------------
        overtime_hours = input_row.approved_overtime_hours
        if overtime_hours > 0 and input_row.overtime_eligible and config.overtime_enabled:
            ot_base = sum(
                (entry.monthly_reference for entry in totals.values() if entry.overtime_base),
                Decimal("0"),
            )
            if ot_base <= 0:
                ot_base = (
                    last_comp.basic_salary
                    if config.overtime_basis == PercentageBasis.BASIC.value
                    else last_comp.monthly_gross
                )
            working_count = len(calendar.working_dates)
            if working_count <= 0 or config.standard_daily_hours <= 0:
                raise _Refusal(
                    "The overtime configuration resolves to a zero-hour month. "
                    "Check standard daily hours and the working-day configuration."
                )
            hourly = ot_base / (Decimal(working_count) * config.standard_daily_hours)
            amount = (hourly * config.overtime_multiplier * overtime_hours).quantize(_CENT, ROUND_HALF_UP)
            lines.append(
                _Line(
                    item_type=PayrollItemType.EARNING.value,
                    source=PayrollLineSource.OVERTIME.value,
                    component_id=None,
                    code="OVERTIME_PAY",
                    name="Overtime",
                    calculation_basis=(
                        f"{overtime_hours}h x {config.overtime_multiplier} x "
                        f"{hourly.quantize(_CENT, ROUND_HALF_UP)}/h"
                    ),
                    amount=amount,
                )
            )
            base.overtime_hours_paid = overtime_hours

        for entry in sorted(totals.values(), key=lambda item: item.order):
            if entry.item_type != PayrollItemType.DEDUCTION.value:
                continue
            lines.append(self._component_line(entry, len(segments) > 1))

        # -- Unpaid leave deduction ---------------------------------------------
        unpaid_days = input_row.unpaid_leave_days
        if unpaid_days > 0 and input_row.unpaid_leave_deduction:
            unpaid_basis = input_row.unpaid_leave_basis or config.unpaid_leave_basis
            unpaid_denominator = calendar.basis_days(unpaid_basis)
            if unpaid_denominator <= 0:
                raise _Refusal("The unpaid-leave basis resolves to zero days for this period.")
            deduction_base = sum(
                (
                    entry.monthly_reference
                    for entry in totals.values()
                    if entry.leave_impact and entry.item_type == PayrollItemType.EARNING.value
                ),
                Decimal("0"),
            )
            if deduction_base <= 0:
                deduction_base = last_comp.monthly_gross
            per_day = deduction_base / Decimal(unpaid_denominator)
            amount = (per_day * unpaid_days).quantize(_CENT, ROUND_HALF_UP)
            lines.append(
                _Line(
                    item_type=PayrollItemType.DEDUCTION.value,
                    source=PayrollLineSource.UNPAID_LEAVE.value,
                    component_id=None,
                    code="UNPAID_LEAVE",
                    name="Unpaid leave",
                    calculation_basis=(
                        f"{unpaid_days}d x {per_day.quantize(_CENT, ROUND_HALF_UP)}/d "
                        f"({_BASIS_LABELS[PayrollDayBasis(unpaid_basis).value]})"
                    ),
                    amount=amount,
                )
            )

        # -- Totals: line cents → sums → configured rounding --------------------
        gross = sum(
            (line.amount for line in lines if line.item_type == PayrollItemType.EARNING.value),
            Decimal("0"),
        )
        deductions = sum(
            (line.amount for line in lines if line.item_type == PayrollItemType.DEDUCTION.value),
            Decimal("0"),
        )
        rounded_gross = self._apply_rounding(gross, config)
        rounded_deductions = self._apply_rounding(deductions, config)

        base.status = PayrollRecordStatus.CALCULATED.value
        base.compensation_id = last_comp.id
        base.proration_basis = PayrollDayBasis(proration_basis).value
        base.gross_earnings = rounded_gross
        base.total_deductions = rounded_deductions
        base.net_pay = rounded_gross - rounded_deductions
        return base, lines

    def _component_line(self, entry: _ComponentTotal, split: bool) -> _Line:
        basis = "; ".join(entry.basis_parts)
        if split and entry.prorated:
            basis += " · split across salary revision"
        return _Line(
            item_type=entry.item_type,
            source=PayrollLineSource.COMPONENT.value,
            component_id=entry.component_id,
            code=entry.code,
            name=entry.name,
            calculation_basis=basis,
            amount=entry.amount.quantize(_CENT, ROUND_HALF_UP),
            original_amount=entry.monthly_reference.quantize(_CENT, ROUND_HALF_UP),
            prorated=entry.prorated,
        )

    @staticmethod
    def _monthly_amount(
        calculation_type: str, value: Decimal, percentage_basis: str | None, comp: EmployeeCompensation
    ) -> Decimal:
        if calculation_type == SalaryCalculationType.FIXED.value:
            return value
        reference = (
            comp.basic_salary if percentage_basis == PercentageBasis.BASIC.value else comp.monthly_gross
        )
        return value * reference / _HUNDRED

    @staticmethod
    def _value_description(calculation_type: str, value: Decimal, percentage_basis: str | None) -> str:
        if calculation_type == SalaryCalculationType.FIXED.value:
            return "Fixed monthly"
        return f"{value}% of {percentage_basis or 'gross'}"

    @staticmethod
    def _apply_rounding(amount: Decimal, config: PayrollConfiguration) -> Decimal:
        rule = config.rounding_rule
        if rule == RoundingRule.NEAREST_WHOLE.value:
            return amount.quantize(Decimal("1"), ROUND_HALF_UP)
        if rule == RoundingRule.NEAREST_HALF.value:
            return ((amount * 2).quantize(Decimal("1"), ROUND_HALF_UP) / 2).quantize(_CENT)
        if rule == RoundingRule.CUSTOM.value and config.rounding_precision:
            steps = (amount / config.rounding_precision).quantize(Decimal("1"), ROUND_HALF_UP)
            return (steps * config.rounding_precision).quantize(_CENT)
        return amount.quantize(_CENT, ROUND_HALF_UP)

    # ==================================================================
    # Reads
    # ==================================================================
    async def list_records(
        self, run_id: uuid.UUID, params: PayrollRecordListParams
    ) -> tuple[list[PayrollRecordRead], int]:
        await self._require_run(run_id)
        rows, total = await self.records.search(run_id, params)
        return [self._present_record(row) for row in rows], total

    async def record_detail(self, run_id: uuid.UUID, employee_id: uuid.UUID) -> PayrollRecordDetail:
        record = await self.records.for_run_employee(run_id, employee_id)
        if record is None:
            raise NotFoundError("Payroll record")
        return await self._present_detail(record)

    async def my_records(self, employee: Employee) -> list[PayrollRecordDetail]:
        rows = await self.records.for_employee(employee.id)
        visible = {
            PayrollRecordStatus.CALCULATED.value,
            PayrollRecordStatus.REVIEWED.value,
            PayrollRecordStatus.READY_FOR_APPROVAL.value,
        }
        return [await self._present_detail(row) for row in rows if row.status in visible]

    # ------------------------------------------------------------------
    # Presentation
    # ------------------------------------------------------------------
    async def _require_run(self, run_id: uuid.UUID) -> PayrollRun:
        run = await self.runs.get(run_id)
        if run is None:
            raise NotFoundError("Payroll run")
        return run

    async def _require_config(self) -> PayrollConfiguration:
        config = await self.config.singleton()
        if config is None:  # pragma: no cover - seeded by the migration
            raise NotFoundError("Payroll configuration")
        return config

    def _present_run(self, run: PayrollRun, exception_counts: tuple[int, int] = (0, 0)) -> PayrollRunRead:
        return present_run(run, exception_counts)

    def _present_record(self, record: PayrollEmployeeRecord) -> PayrollRecordRead:
        return PayrollRecordRead(
            id=record.id,
            run_id=record.run_id,
            employee=EmployeeSummary.model_validate(record.employee),
            status=PayrollRecordStatus(record.status),
            exception_reason=record.exception_reason,
            currency=record.currency,
            gross_earnings=record.gross_earnings,
            total_deductions=record.total_deductions,
            net_pay=record.net_pay,
            adjustment_earnings=record.adjustment_earnings,
            adjustment_deductions=record.adjustment_deductions,
            final_gross=record.gross_earnings + record.adjustment_earnings,
            final_deductions=record.total_deductions + record.adjustment_deductions,
            final_net=(
                record.gross_earnings
                + record.adjustment_earnings
                - record.total_deductions
                - record.adjustment_deductions
            ),
            calendar_days=record.calendar_days,
            working_days=record.working_days,
            eligible_days=record.eligible_days,
            present_days=record.present_days,
            paid_leave_days=record.paid_leave_days,
            unpaid_leave_days=record.unpaid_leave_days,
            overtime_hours_paid=record.overtime_hours_paid,
            proration_basis=(PayrollDayBasis(record.proration_basis) if record.proration_basis else None),
        )

    async def _present_detail(self, record: PayrollEmployeeRecord) -> PayrollRecordDetail:
        comp = (
            await self.compensation.get(record.compensation_id)
            if record.compensation_id is not None
            else None
        )
        adjustments = await self.adjustments.for_run(record.run_id, employee_id=record.employee_id)
        return PayrollRecordDetail(
            **self._present_record(record).model_dump(),
            period=PayrollPeriodRead.model_validate(record.run.period),
            structure_name=comp.structure.name if comp is not None else None,
            monthly_basic=comp.basic_salary if comp is not None else None,
            monthly_gross=comp.monthly_gross if comp is not None else None,
            annual_ctc=comp.annual_ctc if comp is not None else None,
            line_items=[PayrollLineItemRead.model_validate(item) for item in record.line_items],
            adjustments=[present_adjustment(row) for row in adjustments],
        )
