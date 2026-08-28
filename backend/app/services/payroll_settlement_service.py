"""Full & final settlement (Phase 8).

The settlement sits on top of offboarding — it never starts one — and reads
everything it needs from modules that already exist: the case's last working
day, the employee's compensation, finalized payroll for how far salary has
been paid, approved unpaid leave, recorded overtime, leave balances, asset
assignments and clearances. Three rules shape it.

**Computed figures come only from existing data; policy comes only from
approved adjustments.** Final salary, unpaid leave and overtime are derived
from records the application already holds, each stored as its own item
with its basis. Anything that needs a company decision — leave encashment,
a bonus, an asset recovery, an advance — is proposed as an adjustment with
a reason and counts only once an approver approves it. The service does not
invent an encashment formula or a statutory deduction.

**The settlement is its components.** Final earnings, approved encashments,
approved adjustments and final deductions are stored separately; the
settlement amount is their sum, never a number on its own.

**Settling is the end of change.** ``draft → under_review → approved →
settled``; every step is its own permission, approval requires a completed
review and no critical issue, and a settled settlement is read-only with
its whole detail frozen into a snapshot.
"""

from __future__ import annotations

import calendar as _calendar
import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.exceptions import ConflictError, NotFoundError
from app.models.audit_log import AuditAction
from app.models.employee import Employee
from app.models.enums import (
    EDITABLE_SETTLEMENT_STATUSES,
    SETTLEMENT_EARNING_TYPES,
    AssetReturnStatus,
    FinalSettlementStatus,
    OffboardingCaseStatus,
    PercentageBasis,
    SettlementAdjustmentStatus,
    SettlementAdjustmentType,
    SettlementItemCategory,
    SettlementStatus,
)
from app.models.offboarding import FinalSettlementTracking, OffboardingCase
from app.models.payroll_settlement import (
    FinalSettlement,
    FinalSettlementAdjustment,
    FinalSettlementItem,
)
from app.repositories.offboarding_repository import SettlementRepository as TrackingRepository
from app.repositories.payroll_repository import (
    EmployeeCompensationRepository,
    PayrollConfigurationRepository,
)
from app.repositories.payroll_settlement_repository import (
    FinalSettlementAdjustmentRepository,
    FinalSettlementItemRepository,
    FinalSettlementRepository,
    SettlementReader,
)
from app.schemas.payroll import EmployeeSummary
from app.schemas.payroll_settlement import (
    AssetPositionRow,
    EligibleExitRow,
    LeaveBalanceRow,
    MySettlement,
    SettlementAdjustmentCreate,
    SettlementAdjustmentDecision,
    SettlementAdjustmentRead,
    SettlementApproval,
    SettlementDetail,
    SettlementFinalize,
    SettlementIssue,
    SettlementItemRead,
    SettlementListParams,
    SettlementRead,
    SettlementReopen,
    SettlementUpdate,
    snapshot_payload,
)
from app.services.audit_service import AuditService
from app.services.payroll_calendar import period_calendar
from app.services.payroll_run_service import user_name
from app.utils.datetime import utc_now

_CENT = Decimal("0.01")
_ZERO = Decimal("0.00")
_UNCLEARED = {
    AssetReturnStatus.ASSIGNED.value,
    AssetReturnStatus.DAMAGED.value,
    AssetReturnStatus.LOST.value,
}
_CASE_STATUSES_FOR_SETTLEMENT = {
    OffboardingCaseStatus.IN_PROGRESS.value,
    OffboardingCaseStatus.COMPLETED.value,
}


class PayrollSettlementService:
    def __init__(
        self,
        settlements: FinalSettlementRepository,
        items: FinalSettlementItemRepository,
        adjustments: FinalSettlementAdjustmentRepository,
        reader: SettlementReader,
        compensation: EmployeeCompensationRepository,
        config: PayrollConfigurationRepository,
        tracking: TrackingRepository,
        audit: AuditService,
    ) -> None:
        self.settlements = settlements
        self.items = items
        self.adjustments = adjustments
        self.reader = reader
        self.compensation = compensation
        self.config = config
        self.tracking = tracking
        self.audit = audit

    # ==================================================================
    # Exiting employees and the settlement list
    # ==================================================================
    async def exits(self) -> list[EligibleExitRow]:
        cases = await self.reader.exit_cases()
        settlements = await self.settlements.for_cases([case.id for case, _ in cases])
        rows: list[EligibleExitRow] = []
        for case, resignation in cases:
            employee = await self._employee_of(case)
            if employee is None:
                continue
            settlement = settlements.get(case.id)
            eligible, reason = await self._eligibility(case, employee)
            period = await self.reader.period_containing(case.last_working_day)
            rows.append(
                EligibleExitRow(
                    employee=EmployeeSummary.model_validate(employee),
                    department=employee.team.name if employee.team is not None else None,
                    joining_date=employee.joining_date,
                    last_working_date=case.last_working_day,
                    exit_type="resignation" if resignation is not None else "exit",
                    exit_reason=resignation.reason if resignation is not None else None,
                    offboarding_case_id=case.id,
                    offboarding_status=case.status,
                    final_period_name=period.name if period is not None else None,
                    settlement_id=settlement.id if settlement is not None else None,
                    settlement_status=settlement.status if settlement is not None else "not_started",
                    eligible=eligible,
                    ineligibility_reason=reason,
                )
            )
        return rows

    async def list_settlements(self, params: SettlementListParams) -> tuple[list[SettlementRead], int]:
        rows, total = await self.settlements.search(params)
        return [self._read(row) for row in rows], total

    async def get(self, settlement_id: uuid.UUID) -> SettlementDetail:
        return self._detail(await self._require(settlement_id))

    # ==================================================================
    # Lifecycle
    # ==================================================================
    async def create(self, case_id: uuid.UUID, *, actor_id: uuid.UUID) -> SettlementDetail:
        case = await self.reader.case(case_id)
        if case is None:
            raise NotFoundError("Offboarding case")
        employee = await self._employee_of(case)
        if employee is None:
            raise NotFoundError("Employee")
        eligible, reason = await self._eligibility(case, employee)
        if not eligible:
            raise ConflictError(
                f"This employee is not eligible for settlement: {reason}",
                error_code="not_eligible",
            )
        if await self.settlements.by_case(case.id) is not None:
            raise ConflictError(
                "A settlement already exists for this offboarding case.",
                error_code="settlement_exists",
            )
        resignation = await self.reader.resignation(case.resignation_id) if case.resignation_id else None
        period = await self.reader.period_containing(case.last_working_day)
        settlement = FinalSettlement(
            id=uuid.uuid4(),
            settlement_code=await self._next_code(case.last_working_day, employee.employee_code),
            employee_id=employee.id,
            offboarding_case_id=case.id,
            resignation_id=case.resignation_id,
            status=FinalSettlementStatus.DRAFT.value,
            joining_date=employee.joining_date,
            last_working_date=case.last_working_day,
            exit_type="resignation" if resignation is not None else "exit",
            exit_reason=resignation.reason if resignation is not None else None,
            final_period_id=period.id if period is not None else None,
        )
        settlement = await self.settlements.add(settlement, actor_id=actor_id)
        await self._refresh(settlement)
        await self._calculate(settlement, actor_id=actor_id)
        await self._sync_tracking(case.id, SettlementStatus.IN_PROGRESS, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.SETTLEMENT_CREATED,
            actor_id=actor_id,
            entity_type="final_settlement",
            entity_id=settlement.id,
            description=f"Opened settlement {settlement.settlement_code} for {employee.full_name}",
            context={"employee_id": str(employee.id), "offboarding_case_id": str(case.id)},
        )
        return self._detail(settlement)

    async def update(
        self, settlement_id: uuid.UUID, payload: SettlementUpdate, *, actor_id: uuid.UUID
    ) -> SettlementDetail:
        settlement = await self._require_editable(settlement_id, actor_id=actor_id)
        values = payload.model_dump(exclude_unset=True)
        if values:
            await self.settlements.update(settlement, values, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.SETTLEMENT_UPDATED,
            actor_id=actor_id,
            entity_type="final_settlement",
            entity_id=settlement.id,
            description=f"Updated settlement {settlement.settlement_code}",
            context={"fields": sorted(values)},
        )
        return self._detail(settlement)

    async def calculate(self, settlement_id: uuid.UUID, *, actor_id: uuid.UUID) -> SettlementDetail:
        settlement = await self._require_editable(settlement_id, actor_id=actor_id)
        await self._calculate(settlement, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.SETTLEMENT_CALCULATED,
            actor_id=actor_id,
            entity_type="final_settlement",
            entity_id=settlement.id,
            description=f"Recalculated settlement {settlement.settlement_code}",
        )
        return self._detail(settlement)

    async def add_adjustment(
        self,
        settlement_id: uuid.UUID,
        payload: SettlementAdjustmentCreate,
        *,
        actor_id: uuid.UUID,
    ) -> SettlementDetail:
        settlement = await self._require_editable(settlement_id, actor_id=actor_id)
        adjustment = await self.adjustments.add(
            FinalSettlementAdjustment(
                settlement_id=settlement.id,
                adjustment_type=payload.adjustment_type.value,
                name=payload.name,
                amount=payload.amount,
                reason=payload.reason,
                notes=payload.notes,
            ),
            actor_id=actor_id,
        )
        await self._refresh(settlement)
        await self._calculate(settlement, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.SETTLEMENT_ADJUSTMENT_ADDED,
            actor_id=actor_id,
            entity_type="final_settlement",
            entity_id=settlement.id,
            description=(
                f"Proposed {payload.adjustment_type.value} '{payload.name}' of {payload.amount} "
                f"on settlement {settlement.settlement_code}: {payload.reason}"
            ),
            context={"adjustment_id": str(adjustment.id)},
        )
        return self._detail(settlement)

    async def decide_adjustment(
        self,
        settlement_id: uuid.UUID,
        adjustment_id: uuid.UUID,
        payload: SettlementAdjustmentDecision,
        *,
        actor_id: uuid.UUID,
    ) -> SettlementDetail:
        settlement = await self._require_editable(settlement_id, actor_id=actor_id)
        adjustment = await self.adjustments.get(adjustment_id)
        if adjustment is None or adjustment.settlement_id != settlement.id:
            raise NotFoundError("Settlement adjustment")
        if adjustment.status != SettlementAdjustmentStatus.PENDING.value:
            raise ConflictError("This adjustment has already been decided.", error_code="adjustment_decided")
        await self.adjustments.update(
            adjustment,
            {
                "status": (
                    SettlementAdjustmentStatus.APPROVED.value
                    if payload.approve
                    else SettlementAdjustmentStatus.REJECTED.value
                ),
                "decided_by_id": actor_id,
                "decided_at": utc_now(),
                "decision_note": payload.note,
            },
            actor_id=actor_id,
        )
        await self._refresh(settlement)
        await self._calculate(settlement, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.SETTLEMENT_ADJUSTMENT_DECIDED,
            actor_id=actor_id,
            entity_type="final_settlement",
            entity_id=settlement.id,
            description=(
                f"{'Approved' if payload.approve else 'Rejected'} adjustment '{adjustment.name}' "
                f"on settlement {settlement.settlement_code}" + (f": {payload.note}" if payload.note else "")
            ),
            context={"adjustment_id": str(adjustment.id)},
        )
        return self._detail(settlement)

    async def submit(self, settlement_id: uuid.UUID, *, actor_id: uuid.UUID) -> SettlementDetail:
        settlement = await self._require_editable(settlement_id, actor_id=actor_id)
        if settlement.status != FinalSettlementStatus.DRAFT.value:
            raise ConflictError("Only a draft settlement can be submitted.", error_code="not_draft")
        if settlement.calculated_at is None:
            raise ConflictError("Calculate the settlement before submitting it.", error_code="not_calculated")
        await self.settlements.update(
            settlement,
            {
                "status": FinalSettlementStatus.UNDER_REVIEW.value,
                "submitted_at": utc_now(),
                "submitted_by_id": actor_id,
            },
            actor_id=actor_id,
        )
        await self._refresh(settlement)
        await self._audit_step(AuditAction.SETTLEMENT_SUBMITTED, settlement, actor_id, "Submitted")
        return self._detail(settlement)

    async def complete_review(self, settlement_id: uuid.UUID, *, actor_id: uuid.UUID) -> SettlementDetail:
        settlement = await self._require_editable(settlement_id, actor_id=actor_id)
        if settlement.status != FinalSettlementStatus.UNDER_REVIEW.value:
            raise ConflictError("Only a submitted settlement can be reviewed.", error_code="not_under_review")
        await self._calculate(settlement, actor_id=actor_id)
        await self.settlements.update(
            settlement,
            {"review_completed_at": utc_now(), "review_completed_by_id": actor_id},
            actor_id=actor_id,
        )
        await self._refresh(settlement)
        await self._audit_step(AuditAction.SETTLEMENT_REVIEWED, settlement, actor_id, "Completed review of")
        return self._detail(settlement)

    async def approve(
        self, settlement_id: uuid.UUID, payload: SettlementApproval, *, actor_id: uuid.UUID
    ) -> SettlementDetail:
        settlement = await self._require_editable(settlement_id, actor_id=actor_id)
        if settlement.status != FinalSettlementStatus.UNDER_REVIEW.value:
            raise ConflictError("Only a submitted settlement can be approved.", error_code="not_under_review")
        if settlement.review_completed_at is None:
            raise ConflictError("Complete the review before approving.", error_code="review_incomplete")
        # Re-derive at the moment of decision: the gate takes nobody's word.
        await self._calculate(settlement, actor_id=actor_id)
        critical = [issue for issue in settlement.issues if issue.get("severity") == "critical"]
        if critical:
            raise ConflictError(
                "The settlement cannot be approved: "
                + " ".join(str(issue.get("message")) for issue in critical),
                error_code="approval_blocked",
            )
        await self.settlements.update(
            settlement,
            {
                "status": FinalSettlementStatus.APPROVED.value,
                "approved_at": utc_now(),
                "approved_by_id": actor_id,
                "approval_comment": payload.comment,
            },
            actor_id=actor_id,
        )
        await self._refresh(settlement)
        await self._sync_tracking(
            settlement.offboarding_case_id, SettlementStatus.READY_FOR_PROCESSING, actor_id=actor_id
        )
        await self._audit_step(
            AuditAction.SETTLEMENT_APPROVED, settlement, actor_id, "Approved", comment=payload.comment
        )
        return self._detail(settlement)

    async def reopen(
        self, settlement_id: uuid.UUID, payload: SettlementReopen, *, actor_id: uuid.UUID
    ) -> SettlementDetail:
        settlement = await self._require(settlement_id)
        if settlement.status != FinalSettlementStatus.APPROVED.value:
            raise ConflictError("Only an approved settlement can be reopened.", error_code="not_approved")
        await self.settlements.update(
            settlement,
            {
                "status": FinalSettlementStatus.DRAFT.value,
                "approved_at": None,
                "approved_by_id": None,
                "approval_comment": None,
                "review_completed_at": None,
                "review_completed_by_id": None,
                "submitted_at": None,
                "submitted_by_id": None,
            },
            actor_id=actor_id,
        )
        await self._refresh(settlement)
        await self._sync_tracking(
            settlement.offboarding_case_id, SettlementStatus.IN_PROGRESS, actor_id=actor_id
        )
        await self._audit_step(
            AuditAction.SETTLEMENT_REOPENED, settlement, actor_id, "Reopened", comment=payload.reason
        )
        return self._detail(settlement)

    async def finalize(
        self, settlement_id: uuid.UUID, payload: SettlementFinalize, *, actor_id: uuid.UUID
    ) -> SettlementDetail:
        settlement = await self._require(settlement_id)
        if settlement.status != FinalSettlementStatus.APPROVED.value:
            raise ConflictError("Only an approved settlement can be settled.", error_code="not_approved")
        settled_at = utc_now()
        await self.settlements.update(
            settlement,
            {
                "status": FinalSettlementStatus.SETTLED.value,
                "settled_at": settled_at,
                "settled_by_id": actor_id,
                "settlement_reference": payload.settlement_reference,
            },
            actor_id=actor_id,
        )
        await self._refresh(settlement)
        detail = self._detail(settlement)
        await self.settlements.update(
            settlement, {"final_snapshot": snapshot_payload(detail)}, actor_id=actor_id
        )
        await self._sync_tracking(
            settlement.offboarding_case_id,
            SettlementStatus.COMPLETED,
            actor_id=actor_id,
            reference=payload.settlement_reference or settlement.settlement_code,
            settled_on=settled_at.date(),
        )
        await self._audit_step(
            AuditAction.SETTLEMENT_FINALIZED,
            settlement,
            actor_id,
            "Settled",
            comment=payload.settlement_reference,
        )
        return detail

    # ==================================================================
    # Employee self-service
    # ==================================================================
    async def mine(self, employee: Employee) -> MySettlement:
        settlement = await self.settlements.latest_for_employee(employee.id)
        if settlement is None or settlement.status != FinalSettlementStatus.SETTLED.value:
            raise NotFoundError("Settlement")
        return MySettlement(
            settlement_code=settlement.settlement_code,
            status=FinalSettlementStatus(settlement.status),
            currency=settlement.currency,
            last_working_date=settlement.last_working_date,
            settled_at=settlement.settled_at,
            final_earnings=settlement.final_earnings,
            approved_encashments=settlement.approved_encashments,
            approved_adjustments=settlement.approved_adjustments,
            final_deductions=settlement.final_deductions,
            settlement_amount=settlement.settlement_amount,
            items=[self._item(item) for item in settlement.items],
            settlement_reference=settlement.settlement_reference,
        )

    # ==================================================================
    # Calculation
    # ==================================================================
    async def _calculate(self, settlement: FinalSettlement, *, actor_id: uuid.UUID) -> None:
        employee = settlement.employee
        lwd = settlement.last_working_date
        issues: list[dict[str, str]] = []
        items: list[FinalSettlementItem] = []

        case = settlement.offboarding_case
        if case.status not in _CASE_STATUSES_FOR_SETTLEMENT:
            issues.append(
                {
                    "severity": "critical",
                    "message": f"The offboarding case is {case.status.replace('_', ' ')}; it must be in progress or completed.",  # noqa: E501
                }
            )

        comp = await self.compensation.current_for_employee(employee.id)
        config = await self.config.singleton()
        period = await self.reader.period_containing(lwd)
        paid_through = await self.reader.paid_through(employee.id)

        if period is not None:
            window_start, window_end = period.start_date, period.end_date
        else:
            window_start = lwd.replace(day=1)
            window_end = lwd.replace(day=_calendar.monthrange(lwd.year, lwd.month)[1])
            issues.append(
                {
                    "severity": "warning",
                    "message": "No payroll period covers the last working date; the calendar month is used as the final period.",  # noqa: E501
                }
            )
        period_days = (window_end - window_start).days + 1
        salary_from = window_start
        if paid_through is not None and paid_through >= salary_from:
            salary_from = paid_through + timedelta(days=1)
        if paid_through is None:
            issues.append(
                {
                    "severity": "warning",
                    "message": "No finalized payroll exists for this employee; only the final period is settled here.",  # noqa: E501
                }
            )
        unpaid_days = max(0, (lwd - salary_from).days + 1) if salary_from <= lwd else 0

        daily_rate: Decimal | None = None
        final_earnings = _ZERO
        final_deductions = _ZERO
        order = 0
        if comp is None:
            issues.append(
                {
                    "severity": "critical",
                    "message": "No compensation record exists; the final salary cannot be computed.",
                }
            )
        else:
            daily_rate = (comp.monthly_gross / Decimal(period_days)).quantize(
                Decimal("0.0001"), ROUND_HALF_UP
            )
            if unpaid_days > 0:
                amount = (daily_rate * unpaid_days).quantize(_CENT, ROUND_HALF_UP)
                items.append(
                    FinalSettlementItem(
                        settlement_id=settlement.id,
                        category=SettlementItemCategory.EARNING.value,
                        code="FINAL_SALARY",
                        name="Final salary",
                        basis=f"{unpaid_days} day(s) from {salary_from:%d %b %Y} to {lwd:%d %b %Y} at {daily_rate}/day ({comp.monthly_gross}/{period_days} days)",  # noqa: E501
                        quantity=Decimal(unpaid_days).quantize(_CENT),
                        amount=amount,
                        sort_order=order,
                    )
                )
                order += 1
                final_earnings += amount

        # -- Unpaid leave inside the unpaid window ------------------------
        unpaid_leave_days = _ZERO
        if unpaid_days > 0:
            unpaid_leave_days = await self.reader.unpaid_leave_days(employee.id, salary_from, lwd)
            if unpaid_leave_days > 0 and daily_rate is not None:
                amount = (daily_rate * unpaid_leave_days).quantize(_CENT, ROUND_HALF_UP)
                items.append(
                    FinalSettlementItem(
                        settlement_id=settlement.id,
                        category=SettlementItemCategory.DEDUCTION.value,
                        code="UNPAID_LEAVE",
                        name="Unpaid leave",
                        basis=f"{unpaid_leave_days} day(s) x {daily_rate}/day",
                        quantity=unpaid_leave_days,
                        amount=amount,
                        sort_order=order,
                    )
                )
                order += 1
                final_deductions += amount

        # -- Overtime inside the unpaid window ------------------------------
        overtime_hours = _ZERO
        if unpaid_days > 0:
            minutes = await self.reader.overtime_minutes(employee.id, salary_from, lwd)
            overtime_hours = (Decimal(minutes) / Decimal(60)).quantize(_CENT, ROUND_HALF_UP)
        if overtime_hours > 0 and comp is not None and config is not None:
            if not config.overtime_enabled:
                issues.append(
                    {
                        "severity": "info",
                        "message": f"{overtime_hours} overtime hour(s) recorded, but overtime pay is disabled in payroll configuration.",  # noqa: E501
                    }
                )
            elif config.overtime_approval_required:
                issues.append(
                    {
                        "severity": "warning",
                        "message": f"{overtime_hours} overtime hour(s) recorded; overtime requires approval — add an approved adjustment if payable.",  # noqa: E501
                    }
                )
            else:
                cal = period_calendar(config, window_start, window_end)
                working_days = max(len(cal.working_dates), 1)
                base = (
                    comp.basic_salary
                    if config.overtime_basis == PercentageBasis.BASIC.value
                    else comp.monthly_gross
                )
                hourly = base / (Decimal(working_days) * config.standard_daily_hours)
                amount = (hourly * config.overtime_multiplier * overtime_hours).quantize(_CENT, ROUND_HALF_UP)
                items.append(
                    FinalSettlementItem(
                        settlement_id=settlement.id,
                        category=SettlementItemCategory.EARNING.value,
                        code="OVERTIME",
                        name="Overtime",
                        basis=f"{overtime_hours}h x {config.overtime_multiplier} x {hourly.quantize(_CENT, ROUND_HALF_UP)}/h",  # noqa: E501
                        quantity=overtime_hours,
                        amount=amount,
                        sort_order=order,
                    )
                )
                order += 1
                final_earnings += amount

        # -- Leave balances (read; encashment only by approved adjustment) --
        leave_summary: list[dict[str, object]] = []
        for balance, leave_type in await self.reader.leave_balances(employee.id, lwd.year):
            eligible = balance.opening_balance + balance.allocated
            leave_summary.append(
                {
                    "leave_type": leave_type.name,
                    "code": leave_type.code,
                    "is_paid": leave_type.is_paid,
                    "eligible": str(eligible),
                    "used": str(balance.used),
                    "remaining": str(balance.remaining),
                    "encashable": False,
                }
            )
        if any(Decimal(str(row["remaining"])) > 0 and bool(row["is_paid"]) for row in leave_summary):
            issues.append(
                {
                    "severity": "info",
                    "message": "Paid leave remains unused. No leave-encashment policy is configured; record any encashment as an approved 'leave encashment' adjustment.",  # noqa: E501
                }
            )

        # -- Assets (read; recovery only by approved adjustment) -------------
        clearances = {c.asset_id: c for c in await self.reader.clearances(case.id) if c.asset_id}
        approved_recovery = sum(
            (
                a.amount
                for a in settlement.adjustments
                if a.adjustment_type == SettlementAdjustmentType.ASSET_RECOVERY.value
                and a.status == SettlementAdjustmentStatus.APPROVED.value
            ),
            _ZERO,
        )
        assets: list[dict[str, object]] = []
        uncleared = 0
        seen: set[uuid.UUID] = set()
        for assignment, asset in await self.reader.open_assignments(employee.id):
            clearance = clearances.get(asset.id)
            return_status = clearance.status if clearance is not None else AssetReturnStatus.ASSIGNED.value
            if return_status in _UNCLEARED:
                uncleared += 1
            seen.add(asset.id)
            assets.append(
                {
                    "asset_name": asset.name,
                    "asset_tag": asset.asset_tag,
                    "assignment_status": "assigned",
                    "return_status": return_status,
                    "recovery_amount": None,
                    "recovery_approved": False,
                }
            )
            del assignment
        for clearance in await self.reader.clearances(case.id):
            if clearance.asset_id in seen:
                continue
            if clearance.status in _UNCLEARED:
                uncleared += 1
            assets.append(
                {
                    "asset_name": clearance.asset_name,
                    "asset_tag": clearance.asset_tag,
                    "assignment_status": "cleared" if clearance.status not in _UNCLEARED else "assigned",
                    "return_status": clearance.status,
                    "recovery_amount": None,
                    "recovery_approved": False,
                }
            )
        if uncleared and approved_recovery == 0:
            issues.append(
                {
                    "severity": "critical",
                    "message": f"{uncleared} asset(s) not returned or waived and no approved asset recovery recorded.",  # noqa: E501
                }
            )
        elif uncleared:
            issues.append(
                {
                    "severity": "warning",
                    "message": f"{uncleared} asset(s) not returned; an approved asset recovery of {approved_recovery} is recorded.",  # noqa: E501
                }
            )
            for row in assets:
                if row["return_status"] in _UNCLEARED:
                    row["recovery_amount"] = str(approved_recovery)
                    row["recovery_approved"] = True

        # -- Adjustments: approved ones become items --------------------------
        encashments = _ZERO
        adjustments_total = _ZERO
        pending = 0
        for adjustment in settlement.adjustments:
            if adjustment.status == SettlementAdjustmentStatus.PENDING.value:
                pending += 1
                continue
            if adjustment.status != SettlementAdjustmentStatus.APPROVED.value:
                continue
            is_earning = adjustment.adjustment_type in SETTLEMENT_EARNING_TYPES
            if adjustment.adjustment_type == SettlementAdjustmentType.LEAVE_ENCASHMENT.value:
                category = SettlementItemCategory.ENCASHMENT.value
                encashments += adjustment.amount
            elif is_earning:
                category = SettlementItemCategory.ADJUSTMENT.value
                adjustments_total += adjustment.amount
            else:
                category = SettlementItemCategory.DEDUCTION.value
                final_deductions += adjustment.amount
            items.append(
                FinalSettlementItem(
                    settlement_id=settlement.id,
                    category=category,
                    code=adjustment.adjustment_type.upper(),
                    name=adjustment.name,
                    basis=adjustment.reason,
                    quantity=None,
                    amount=adjustment.amount,
                    source="adjustment",
                    adjustment_id=adjustment.id,
                    sort_order=order,
                )
            )
            order += 1
        if pending:
            issues.append(
                {"severity": "critical", "message": f"{pending} adjustment(s) awaiting an approval decision."}
            )

        await self.items.clear_for(settlement.id)
        for item in items:
            await self.items.add(item, actor_id=actor_id)
        await self.settlements.update(
            settlement,
            {
                "compensation_id": comp.id if comp is not None else None,
                "final_period_id": period.id if period is not None else None,
                "currency": comp.currency if comp is not None else settlement.currency,
                "monthly_gross": comp.monthly_gross if comp is not None else None,
                "basic_salary": comp.basic_salary if comp is not None else None,
                "daily_rate": daily_rate,
                "paid_through": paid_through,
                "unpaid_salary_days": unpaid_days,
                "unpaid_leave_days": unpaid_leave_days,
                "overtime_hours": overtime_hours,
                "leave_summary": leave_summary,
                "assets": assets,
                "issues": issues,
                "final_earnings": final_earnings,
                "approved_encashments": encashments,
                "approved_adjustments": adjustments_total,
                "final_deductions": final_deductions,
                "settlement_amount": final_earnings + encashments + adjustments_total - final_deductions,
                "calculated_at": utc_now(),
            },
            actor_id=actor_id,
        )
        await self._refresh(settlement)

    # ==================================================================
    # Internals
    # ==================================================================
    async def _employee_of(self, case: OffboardingCase) -> Employee | None:
        from sqlalchemy import select

        from app.models.employee import Employee as _Employee  # local to avoid cycles at import

        stmt = select(_Employee).where(_Employee.id == case.employee_id)
        return (await self.reader.session.execute(stmt)).scalars().unique().first()

    async def _eligibility(self, case: OffboardingCase, employee: Employee) -> tuple[bool, str | None]:
        if case.status not in _CASE_STATUSES_FOR_SETTLEMENT:
            return False, f"Offboarding is {case.status.replace('_', ' ')}."
        if await self.compensation.current_for_employee(employee.id) is None:
            return False, "No compensation record exists for this employee."
        return True, None

    async def _require(self, settlement_id: uuid.UUID) -> FinalSettlement:
        settlement = await self.settlements.get(settlement_id)
        if settlement is None:
            raise NotFoundError("Settlement")
        return settlement

    async def _require_editable(self, settlement_id: uuid.UUID, *, actor_id: uuid.UUID) -> FinalSettlement:
        settlement = await self._require(settlement_id)
        if settlement.status not in EDITABLE_SETTLEMENT_STATUSES:
            await self.audit.record_failure(
                AuditAction.SETTLEMENT_LOCKED_MODIFICATION,
                actor_id=actor_id,
                entity_type="final_settlement",
                entity_id=settlement.id,
                description=f"Refused a change to {settlement.status} settlement {settlement.settlement_code}",  # noqa: E501
            )
            error = ConflictError(
                "This settlement is locked — an approved settlement must be reopened first, and a "
                "settled one cannot change.",
                error_code="settlement_locked",
            )
            error.preserve_writes = True
            raise error
        return settlement

    async def _refresh(self, settlement: FinalSettlement) -> None:
        await self.settlements.session.refresh(
            settlement,
            [
                "items",
                "adjustments",
                "employee",
                "offboarding_case",
                "final_period",
                "submitted_by",
                "review_completed_by",
                "approved_by",
                "settled_by",
            ],
        )

    async def _next_code(self, lwd: date, employee_code: str) -> str:
        base = f"FNF-{lwd:%Y%m}-{employee_code}"
        candidate, suffix = base, 2
        while await self.settlements.by_code(candidate) is not None:
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    async def _sync_tracking(
        self,
        case_id: uuid.UUID,
        status: SettlementStatus,
        *,
        actor_id: uuid.UUID,
        reference: str | None = None,
        settled_on: date | None = None,
    ) -> None:
        """Keep the offboarding module's settlement tracker in step, so the
        offboarding screens show where the settlement has got to."""
        record = await self.tracking.for_case(case_id)
        if record is None:
            record = await self.tracking.add(FinalSettlementTracking(case_id=case_id), actor_id=actor_id)
        values: dict[str, object] = {"status": status.value}
        if reference is not None:
            values["settlement_reference"] = reference
        if settled_on is not None:
            values["settlement_date"] = settled_on
        await self.tracking.update(record, values, actor_id=actor_id)

    async def _audit_step(
        self,
        action: str,
        settlement: FinalSettlement,
        actor_id: uuid.UUID,
        verb: str,
        *,
        comment: str | None = None,
    ) -> None:
        await self.audit.record_success(
            action,
            actor_id=actor_id,
            entity_type="final_settlement",
            entity_id=settlement.id,
            description=f"{verb} settlement {settlement.settlement_code}"
            + (f": {comment}" if comment else ""),
            context={"employee_id": str(settlement.employee_id), "status": settlement.status},
        )

    # ------------------------------------------------------------------
    # Presentation
    # ------------------------------------------------------------------
    @staticmethod
    def _item(item: FinalSettlementItem) -> SettlementItemRead:
        return SettlementItemRead(
            id=item.id,
            category=SettlementItemCategory(item.category),
            code=item.code,
            name=item.name,
            basis=item.basis,
            quantity=item.quantity,
            amount=item.amount,
            source=item.source,
        )

    @staticmethod
    def _adjustment(adjustment: FinalSettlementAdjustment) -> SettlementAdjustmentRead:
        return SettlementAdjustmentRead(
            id=adjustment.id,
            adjustment_type=SettlementAdjustmentType(adjustment.adjustment_type),
            is_earning=adjustment.adjustment_type in SETTLEMENT_EARNING_TYPES,
            name=adjustment.name,
            amount=adjustment.amount,
            reason=adjustment.reason,
            notes=adjustment.notes,
            status=SettlementAdjustmentStatus(adjustment.status),
            created_by_name=None,
            created_at=adjustment.created_at,
            decided_by_name=user_name(adjustment.decided_by),
            decided_at=adjustment.decided_at,
            decision_note=adjustment.decision_note,
        )

    def _read(self, settlement: FinalSettlement) -> SettlementRead:
        employee = settlement.employee
        return SettlementRead(
            id=settlement.id,
            settlement_code=settlement.settlement_code,
            employee=EmployeeSummary.model_validate(employee),
            department=employee.team.name if employee.team is not None else None,
            status=FinalSettlementStatus(settlement.status),
            currency=settlement.currency,
            joining_date=settlement.joining_date,
            last_working_date=settlement.last_working_date,
            exit_type=settlement.exit_type,
            exit_reason=settlement.exit_reason,
            final_period_name=settlement.final_period.name if settlement.final_period is not None else None,
            final_earnings=settlement.final_earnings,
            approved_encashments=settlement.approved_encashments,
            approved_adjustments=settlement.approved_adjustments,
            final_deductions=settlement.final_deductions,
            settlement_amount=settlement.settlement_amount,
            calculated_at=settlement.calculated_at,
            submitted_at=settlement.submitted_at,
            review_completed_at=settlement.review_completed_at,
            approved_at=settlement.approved_at,
            settled_at=settlement.settled_at,
            created_at=settlement.created_at,
        )

    def _detail(self, settlement: FinalSettlement) -> SettlementDetail:
        issues = [
            SettlementIssue(severity=str(i.get("severity")), message=str(i.get("message")))
            for i in settlement.issues
        ]
        critical = sum(1 for issue in issues if issue.severity == "critical")
        return SettlementDetail(
            **self._read(settlement).model_dump(),
            notes=settlement.notes,
            offboarding_case_id=settlement.offboarding_case_id,
            offboarding_status=settlement.offboarding_case.status,
            monthly_gross=settlement.monthly_gross,
            basic_salary=settlement.basic_salary,
            daily_rate=settlement.daily_rate,
            paid_through=settlement.paid_through,
            unpaid_salary_days=settlement.unpaid_salary_days,
            unpaid_leave_days=settlement.unpaid_leave_days,
            overtime_hours=settlement.overtime_hours,
            leave_summary=[LeaveBalanceRow.model_validate(row) for row in settlement.leave_summary],
            assets=[AssetPositionRow.model_validate(row) for row in settlement.assets],
            issues=issues,
            critical_issue_count=critical,
            items=[self._item(item) for item in settlement.items],
            adjustments=[self._adjustment(a) for a in settlement.adjustments],
            submitted_by_name=user_name(settlement.submitted_by),
            review_completed_by_name=user_name(settlement.review_completed_by),
            approved_by_name=user_name(settlement.approved_by),
            approval_comment=settlement.approval_comment,
            settled_by_name=user_name(settlement.settled_by),
            settlement_reference=settlement.settlement_reference,
            can_approve=(
                settlement.status == FinalSettlementStatus.UNDER_REVIEW.value
                and settlement.review_completed_at is not None
                and critical == 0
            ),
        )
