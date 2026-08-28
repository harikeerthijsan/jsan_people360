"""Payroll review and adjustments (Phase 5).

The review layer sits between calculation (Phase 4) and approval (a later
phase) and never touches the engine's arithmetic. Its rules:

**Originals are evidence.** A record's calculated gross, deductions and net
are never edited. Every correction is an additive adjustment row with a
mandatory reason; final pay is derived (original + adjustments) wherever it
is displayed, so the trail from calculation to payout stays intact.

**Exceptions are resolved, never removed.** Resolving an exception records
who, when, and how — the row survives. Critical exceptions block review
completion outright; warnings and errors inform, they don't gate.

**Completion is earned.** "Review complete" requires every checklist item
ticked, zero open critical exceptions, and no record still marked
requires-review or adjustment-required. The readiness endpoint states each
unmet condition rather than failing opaquely.

**History only grows.** Cancelled adjustments stay visible with their cancel
reason; comments are append-only; the comparison against the previous period
highlights large moves but never rejects anything automatically — judgement
stays with the reviewer.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.audit_log import AuditAction
from app.models.enums import (
    DEFAULT_REVIEW_CHECKLIST,
    LOCKED_RUN_STATUSES,
    REVIEWABLE_RUN_STATUSES,
    PayrollAdjustmentStatus,
    PayrollExceptionSeverity,
    PayrollExceptionStatus,
    PayrollItemType,
    PayrollRecordStatus,
    PayrollRunExceptionType,
    PayrollRunStatus,
)
from app.models.payroll import (
    PayrollAdjustment,
    PayrollEmployeeRecord,
    PayrollReviewChecklist,
    PayrollReviewComment,
    PayrollRun,
    PayrollRunException,
)
from app.repositories.payroll_repository import (
    PayrollAdjustmentRepository,
    PayrollEmployeeRecordRepository,
    PayrollReviewChecklistRepository,
    PayrollReviewCommentRepository,
    PayrollRunExceptionRepository,
    PayrollRunRepository,
)
from app.schemas.payroll import (
    ChecklistItemRead,
    ChecklistItemUpdate,
    EmployeeSummary,
    PayrollAdjustmentCancel,
    PayrollAdjustmentCreate,
    PayrollAdjustmentRead,
    PayrollComparisonRow,
    PayrollExceptionResolve,
    PayrollReconciliation,
    PayrollRecordReviewMark,
    PayrollRunExceptionRead,
    ReviewCommentCreate,
    ReviewCommentRead,
    ReviewReadiness,
)
from app.services.audit_service import AuditService
from app.services.payroll_run_service import present_adjustment
from app.utils.datetime import utc_now

#: A net movement beyond this share of the previous net is "notable" in the
#: period-over-period comparison. Highlighted for the reviewer — never acted on.
_NOTABLE_NET_CHANGE = Decimal("0.20")

#: Record statuses a reviewer may set by hand. Everything else belongs to the
#: engine (calculated, requires_review, excluded) or to completion
#: (ready_for_approval).
_MARKABLE_STATUSES = frozenset(
    {PayrollRecordStatus.REVIEWED.value, PayrollRecordStatus.ADJUSTMENT_REQUIRED.value}
)
_MARKABLE_FROM = frozenset(
    {
        PayrollRecordStatus.CALCULATED.value,
        PayrollRecordStatus.REVIEWED.value,
        PayrollRecordStatus.ADJUSTMENT_REQUIRED.value,
    }
)


class PayrollReviewService:
    """Review workflow over calculated payroll runs."""

    def __init__(
        self,
        runs: PayrollRunRepository,
        records: PayrollEmployeeRecordRepository,
        exceptions: PayrollRunExceptionRepository,
        adjustments: PayrollAdjustmentRepository,
        checklists: PayrollReviewChecklistRepository,
        comments: PayrollReviewCommentRepository,
        audit: AuditService,
    ) -> None:
        self.runs = runs
        self.records = records
        self.exceptions = exceptions
        self.adjustments = adjustments
        self.checklists = checklists
        self.comments = comments
        self.audit = audit

    # ==================================================================
    # Exceptions
    # ==================================================================
    async def list_exceptions(
        self,
        run_id: uuid.UUID,
        *,
        status: PayrollExceptionStatus | None = None,
        severity: PayrollExceptionSeverity | None = None,
    ) -> list[PayrollRunExceptionRead]:
        await self._require_run(run_id)
        rows = await self.exceptions.for_run(
            run_id,
            status=status.value if status else None,
            severity=severity.value if severity else None,
        )
        return [self._present_exception(row) for row in rows]

    async def resolve_exception(
        self,
        run_id: uuid.UUID,
        exception_id: uuid.UUID,
        payload: PayrollExceptionResolve,
        *,
        actor_id: uuid.UUID,
    ) -> PayrollRunExceptionRead:
        run = await self._require_reviewable_run(run_id, actor_id=actor_id)
        row = await self.exceptions.get(exception_id)
        if row is None or row.run_id != run_id:
            raise NotFoundError("Payroll exception")
        if row.status == PayrollExceptionStatus.RESOLVED.value:
            raise ConflictError("This exception is already resolved.", error_code="exception_resolved")
        await self.exceptions.update(
            row,
            {
                "status": PayrollExceptionStatus.RESOLVED.value,
                "resolution": payload.resolution,
                "resolution_notes": payload.notes,
                "resolved_by_id": actor_id,
                "resolved_at": utc_now(),
            },
            actor_id=actor_id,
        )
        await self.exceptions.session.refresh(row, ["resolved_by"])
        await self._touch_review(run, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.PAYROLL_EXCEPTION_RESOLVED,
            actor_id=actor_id,
            entity_type="payroll_run_exception",
            entity_id=row.id,
            description=(
                f"Resolved payroll exception ({row.exception_type}, {row.severity}) "
                f"on run {run.run_code}: {payload.resolution}"
            ),
            context={"run_id": str(run.id), "employee_id": str(row.employee_id)},
        )
        return self._present_exception(row)

    # ==================================================================
    # Adjustments
    # ==================================================================
    async def list_adjustments(
        self, run_id: uuid.UUID, *, employee_id: uuid.UUID | None = None
    ) -> list[PayrollAdjustmentRead]:
        await self._require_run(run_id)
        rows = await self.adjustments.for_run(run_id, employee_id=employee_id)
        return [present_adjustment(row) for row in rows]

    async def create_adjustment(
        self,
        run_id: uuid.UUID,
        employee_id: uuid.UUID,
        payload: PayrollAdjustmentCreate,
        *,
        actor_id: uuid.UUID,
    ) -> PayrollAdjustmentRead:
        run = await self._require_reviewable_run(run_id, actor_id=actor_id)
        record = await self.records.for_run_employee(run_id, employee_id)
        if record is None:
            raise NotFoundError("Payroll record")
        if record.status == PayrollRecordStatus.EXCLUDED.value:
            raise ConflictError(
                "An excluded employee cannot receive adjustments.",
                error_code="record_excluded",
            )
        previous_net = self._final_net(record)
        if payload.item_type == PayrollItemType.EARNING.value:
            await self.records.update(
                record,
                {"adjustment_earnings": record.adjustment_earnings + payload.amount},
                actor_id=actor_id,
            )
        else:
            await self.records.update(
                record,
                {"adjustment_deductions": record.adjustment_deductions + payload.amount},
                actor_id=actor_id,
            )
        new_net = self._final_net(record)
        adjustment = await self.adjustments.add(
            PayrollAdjustment(
                run_id=run_id,
                employee_id=employee_id,
                item_type=payload.item_type,
                name=payload.name,
                amount=payload.amount,
                reason=payload.reason,
                notes=payload.notes,
                previous_net=previous_net,
                new_net=new_net,
            ),
            actor_id=actor_id,
        )
        await self._refresh_run_totals(run, actor_id=actor_id)
        await self._touch_review(run, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.PAYROLL_ADJUSTMENT_CREATED,
            actor_id=actor_id,
            entity_type="payroll_adjustment",
            entity_id=adjustment.id,
            description=(
                f"Added {payload.item_type} adjustment '{payload.name}' of {payload.amount} "
                f"on run {run.run_code}: {payload.reason}"
            ),
            context={
                "run_id": str(run.id),
                "employee_id": str(employee_id),
                "previous_net": str(previous_net),
                "new_net": str(new_net),
            },
        )
        return present_adjustment(adjustment)

    async def cancel_adjustment(
        self,
        run_id: uuid.UUID,
        adjustment_id: uuid.UUID,
        payload: PayrollAdjustmentCancel,
        *,
        actor_id: uuid.UUID,
    ) -> PayrollAdjustmentRead:
        run = await self._require_reviewable_run(run_id, actor_id=actor_id)
        adjustment = await self.adjustments.get(adjustment_id)
        if adjustment is None or adjustment.run_id != run_id:
            raise NotFoundError("Payroll adjustment")
        if adjustment.status != PayrollAdjustmentStatus.ACTIVE.value:
            raise ConflictError("This adjustment is already cancelled.", error_code="adjustment_cancelled")
        record = await self.records.for_run_employee(run_id, adjustment.employee_id)
        if record is not None:
            if adjustment.item_type == PayrollItemType.EARNING.value:
                await self.records.update(
                    record,
                    {"adjustment_earnings": record.adjustment_earnings - adjustment.amount},
                    actor_id=actor_id,
                )
            else:
                await self.records.update(
                    record,
                    {"adjustment_deductions": record.adjustment_deductions - adjustment.amount},
                    actor_id=actor_id,
                )
        await self.adjustments.update(
            adjustment,
            {
                "status": PayrollAdjustmentStatus.CANCELLED.value,
                "cancelled_by_id": actor_id,
                "cancelled_at": utc_now(),
                "cancel_reason": payload.reason,
            },
            actor_id=actor_id,
        )
        await self._refresh_run_totals(run, actor_id=actor_id)
        await self._touch_review(run, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.PAYROLL_ADJUSTMENT_CANCELLED,
            actor_id=actor_id,
            entity_type="payroll_adjustment",
            entity_id=adjustment.id,
            description=(
                f"Cancelled adjustment '{adjustment.name}' on run {run.run_code}: " f"{payload.reason}"
            ),
            context={"run_id": str(run.id), "employee_id": str(adjustment.employee_id)},
        )
        return present_adjustment(adjustment)

    # ==================================================================
    # Record review marks
    # ==================================================================
    async def mark_record(
        self,
        run_id: uuid.UUID,
        employee_id: uuid.UUID,
        payload: PayrollRecordReviewMark,
        *,
        actor_id: uuid.UUID,
    ) -> None:
        run = await self._require_reviewable_run(run_id, actor_id=actor_id)
        if payload.status.value not in _MARKABLE_STATUSES:
            raise ValidationError(
                "A record can only be marked reviewed or adjustment-required.",
                error_code="invalid_review_status",
            )
        record = await self.records.for_run_employee(run_id, employee_id)
        if record is None:
            raise NotFoundError("Payroll record")
        if record.status not in _MARKABLE_FROM:
            raise ConflictError(
                "Only calculated records can be marked — resolve the record's "
                "exceptions and recalculate first.",
                error_code="record_not_markable",
            )
        await self.records.update(record, {"status": payload.status.value}, actor_id=actor_id)
        await self._touch_review(run, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.PAYROLL_RECORD_REVIEW_MARKED,
            actor_id=actor_id,
            entity_type="payroll_employee_record",
            entity_id=record.id,
            description=(
                f"Marked payroll record as {payload.status.value} on run {run.run_code}"
                + (f": {payload.note}" if payload.note else "")
            ),
            context={"run_id": str(run.id), "employee_id": str(employee_id)},
        )

    # ==================================================================
    # Checklist
    # ==================================================================
    async def get_checklist(self, run_id: uuid.UUID) -> list[ChecklistItemRead]:
        await self._require_run(run_id)
        rows = await self._checklist_rows(run_id)
        return [self._present_checklist(row) for row in rows]

    async def update_checklist(
        self,
        run_id: uuid.UUID,
        item_key: str,
        payload: ChecklistItemUpdate,
        *,
        actor_id: uuid.UUID,
    ) -> list[ChecklistItemRead]:
        run = await self._require_reviewable_run(run_id, actor_id=actor_id)
        rows = await self._checklist_rows(run_id)
        target = next((row for row in rows if row.item_key == item_key), None)
        if target is None:
            raise NotFoundError("Checklist item")
        if target.completed != payload.completed:
            await self.checklists.update(
                target,
                {
                    "completed": payload.completed,
                    "completed_by_id": actor_id if payload.completed else None,
                    "completed_at": utc_now() if payload.completed else None,
                },
                actor_id=actor_id,
            )
            await self.checklists.session.refresh(target, ["completed_by"])
            await self._touch_review(run, actor_id=actor_id)
            await self.audit.record_success(
                AuditAction.PAYROLL_CHECKLIST_UPDATED,
                actor_id=actor_id,
                entity_type="payroll_run",
                entity_id=run.id,
                description=(
                    f"Checklist item '{target.label}' "
                    f"{'completed' if payload.completed else 'reopened'} on run {run.run_code}"
                ),
            )
        return [self._present_checklist(row) for row in rows]

    # ==================================================================
    # Completion
    # ==================================================================
    async def readiness(self, run_id: uuid.UUID) -> ReviewReadiness:
        run = await self._require_run(run_id)
        return await self._readiness(run)

    async def complete_review(self, run_id: uuid.UUID, *, actor_id: uuid.UUID) -> ReviewReadiness:
        run = await self._require_reviewable_run(run_id, actor_id=actor_id)
        if run.status == PayrollRunStatus.REVIEW_COMPLETE.value:
            raise ConflictError("The review is already complete.", error_code="review_complete")
        readiness = await self._readiness(run)
        if not readiness.can_complete:
            raise ConflictError(
                "The review cannot be completed yet — resolve the listed blockers first.",
                error_code="review_not_ready",
            )
        promoted = 0
        for record in await self.records.for_run(run_id):
            if record.status in (
                PayrollRecordStatus.CALCULATED.value,
                PayrollRecordStatus.REVIEWED.value,
            ):
                await self.records.update(
                    record,
                    {"status": PayrollRecordStatus.READY_FOR_APPROVAL.value},
                    actor_id=actor_id,
                )
                promoted += 1
        await self.runs.update(
            run,
            {
                "status": PayrollRunStatus.REVIEW_COMPLETE.value,
                "review_completed_at": utc_now(),
                "review_completed_by_id": actor_id,
            },
            actor_id=actor_id,
        )
        await self.runs.session.refresh(run, ["review_completed_by"])
        await self.audit.record_success(
            AuditAction.PAYROLL_REVIEW_COMPLETED,
            actor_id=actor_id,
            entity_type="payroll_run",
            entity_id=run.id,
            description=f"Completed review of payroll run {run.run_code}",
            context={"records_ready_for_approval": promoted},
        )
        return await self._readiness(run)

    # ==================================================================
    # Comments
    # ==================================================================
    async def list_comments(
        self, run_id: uuid.UUID, *, employee_id: uuid.UUID | None = None
    ) -> list[ReviewCommentRead]:
        await self._require_run(run_id)
        rows = await self.comments.for_run(run_id, employee_id=employee_id)
        return [self._present_comment(comment, author) for comment, author in rows]

    async def add_comment(
        self, run_id: uuid.UUID, payload: ReviewCommentCreate, *, actor_id: uuid.UUID
    ) -> ReviewCommentRead:
        run = await self._require_run(run_id)
        if payload.employee_id is not None:
            record = await self.records.for_run_employee(run_id, payload.employee_id)
            if record is None:
                raise NotFoundError("Payroll record")
        comment = await self.comments.add(
            PayrollReviewComment(run_id=run_id, employee_id=payload.employee_id, comment=payload.comment),
            actor_id=actor_id,
        )
        await self.comments.session.refresh(comment, ["employee"])
        rows = await self.comments.for_run(run_id)
        author = next((name for row, name in rows if row.id == comment.id), None)
        await self.audit.record_success(
            AuditAction.PAYROLL_REVIEW_COMMENTED,
            actor_id=actor_id,
            entity_type="payroll_run",
            entity_id=run.id,
            description=f"Commented on payroll run {run.run_code}",
            context=({"employee_id": str(payload.employee_id)} if payload.employee_id is not None else None),
        )
        return self._present_comment(comment, author)

    # ==================================================================
    # Reconciliation and comparison
    # ==================================================================
    async def reconciliation(self, run_id: uuid.UUID) -> PayrollReconciliation:
        run = await self._require_run(run_id)
        records = await self.records.for_run(run_id)
        original_gross = sum((r.gross_earnings for r in records), Decimal("0"))
        adjustment_earnings = sum((r.adjustment_earnings for r in records), Decimal("0"))
        original_deductions = sum((r.total_deductions for r in records), Decimal("0"))
        adjustment_deductions = sum((r.adjustment_deductions for r in records), Decimal("0"))
        adjustments = await self.adjustments.for_run(run_id)
        active = [a for a in adjustments if a.status == PayrollAdjustmentStatus.ACTIVE.value]
        return PayrollReconciliation(
            run_id=run.id,
            currency=run.currency,
            original_gross=original_gross,
            adjustment_earnings=adjustment_earnings,
            final_gross=original_gross + adjustment_earnings,
            original_deductions=original_deductions,
            adjustment_deductions=adjustment_deductions,
            final_deductions=original_deductions + adjustment_deductions,
            original_net=original_gross - original_deductions,
            net_adjustment=adjustment_earnings - adjustment_deductions,
            final_net=(original_gross + adjustment_earnings - original_deductions - adjustment_deductions),
            adjustment_count=len(active),
            cancelled_adjustment_count=len(adjustments) - len(active),
            total_adjustment_amount=sum((a.amount for a in active), Decimal("0")),
            employees_affected=len({a.employee_id for a in active}),
        )

    async def comparison(self, run_id: uuid.UUID) -> list[PayrollComparisonRow]:
        run = await self._require_run(run_id)
        previous = await self.runs.previous_run(run.period.start_date)
        previous_by_employee: dict[uuid.UUID, PayrollEmployeeRecord] = {}
        if previous is not None:
            previous_by_employee = {
                record.employee_id: record for record in await self.records.for_run(previous.id)
            }
        rows: list[PayrollComparisonRow] = []
        for record in await self.records.for_run(run_id):
            if record.status == PayrollRecordStatus.EXCLUDED.value:
                continue
            prior = previous_by_employee.get(record.employee_id)
            if prior is not None and prior.status == PayrollRecordStatus.EXCLUDED.value:
                prior = None
            current_gross = record.gross_earnings + record.adjustment_earnings
            current_deductions = record.total_deductions + record.adjustment_deductions
            current_net = current_gross - current_deductions
            if prior is None:
                rows.append(
                    PayrollComparisonRow(
                        employee=EmployeeSummary.model_validate(record.employee),
                        previous_gross=None,
                        current_gross=current_gross,
                        gross_difference=None,
                        previous_deductions=None,
                        current_deductions=current_deductions,
                        deduction_difference=None,
                        previous_net=None,
                        current_net=current_net,
                        net_difference=None,
                        notable=True,
                    )
                )
                continue
            previous_gross = prior.gross_earnings + prior.adjustment_earnings
            previous_deductions = prior.total_deductions + prior.adjustment_deductions
            previous_net = previous_gross - previous_deductions
            net_difference = current_net - previous_net
            notable = (
                abs(net_difference) > abs(previous_net) * _NOTABLE_NET_CHANGE
                if previous_net != 0
                else net_difference != 0
            )
            rows.append(
                PayrollComparisonRow(
                    employee=EmployeeSummary.model_validate(record.employee),
                    previous_gross=previous_gross,
                    current_gross=current_gross,
                    gross_difference=current_gross - previous_gross,
                    previous_deductions=previous_deductions,
                    current_deductions=current_deductions,
                    deduction_difference=current_deductions - previous_deductions,
                    previous_net=previous_net,
                    current_net=current_net,
                    net_difference=net_difference,
                    notable=notable,
                )
            )
        rows.sort(key=lambda row: (not row.notable, row.employee.full_name))
        return rows

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _require_run(self, run_id: uuid.UUID) -> PayrollRun:
        run = await self.runs.get(run_id)
        if run is None:
            raise NotFoundError("Payroll run")
        return run

    async def _require_reviewable_run(
        self, run_id: uuid.UUID, *, actor_id: uuid.UUID | None = None
    ) -> PayrollRun:
        run = await self._require_run(run_id)
        if run.status in LOCKED_RUN_STATUSES:
            # A submitted, approved or finalized run's numbers cannot move.
            # The attempt goes on record and survives the request's rollback.
            await self.audit.record_failure(
                AuditAction.PAYROLL_LOCKED_MODIFICATION,
                actor_id=actor_id,
                entity_type="payroll_run",
                entity_id=run.id,
                description=f"Refused review-phase change to {run.status} payroll run {run.run_code}",
            )
            error = ConflictError(
                "This run is locked — submitted, approved or finalized payroll cannot be changed.",
                error_code="run_locked",
            )
            error.preserve_writes = True
            raise error
        if run.status not in REVIEWABLE_RUN_STATUSES:
            raise ConflictError(
                "This run is not open for review — calculate it first.",
                error_code="run_not_reviewable",
            )
        return run

    async def _touch_review(self, run: PayrollRun, *, actor_id: uuid.UUID) -> None:
        """Any review activity — including on a completed review — puts the
        run in ``in_review``: what was signed off has changed."""
        if run.status != PayrollRunStatus.IN_REVIEW.value:
            await self.runs.update(run, {"status": PayrollRunStatus.IN_REVIEW.value}, actor_id=actor_id)

    async def _refresh_run_totals(self, run: PayrollRun, *, actor_id: uuid.UUID) -> None:
        """Keep the run's headline totals equal to the sum of final pay."""
        records = await self.records.for_run(run.id)
        gross = sum((r.gross_earnings + r.adjustment_earnings for r in records), Decimal("0"))
        deductions = sum((r.total_deductions + r.adjustment_deductions for r in records), Decimal("0"))
        await self.runs.update(
            run,
            {"total_gross": gross, "total_deductions": deductions, "total_net": gross - deductions},
            actor_id=actor_id,
        )

    async def _checklist_rows(self, run_id: uuid.UUID) -> list[PayrollReviewChecklist]:
        """Lazy-seed the default checklist so the gate and the screen always
        agree on what "all items" means."""
        rows = list(await self.checklists.for_run(run_id))
        if not rows:
            for order, (key, label) in enumerate(DEFAULT_REVIEW_CHECKLIST):
                rows.append(
                    await self.checklists.add(
                        PayrollReviewChecklist(run_id=run_id, item_key=key, label=label, sort_order=order),
                        actor_id=None,
                    )
                )
        return rows

    async def _readiness(self, run: PayrollRun) -> ReviewReadiness:
        open_critical = len(
            await self.exceptions.for_run(
                run.id,
                status=PayrollExceptionStatus.OPEN.value,
                severity=PayrollExceptionSeverity.CRITICAL.value,
            )
        )
        records = await self.records.for_run(run.id)
        requiring_review = sum(1 for r in records if r.status == PayrollRecordStatus.REQUIRES_REVIEW.value)
        adjustment_required = sum(
            1 for r in records if r.status == PayrollRecordStatus.ADJUSTMENT_REQUIRED.value
        )
        incomplete = [row.label for row in await self._checklist_rows(run.id) if not row.completed]
        return ReviewReadiness(
            can_complete=(
                bool(records)
                and run.status in REVIEWABLE_RUN_STATUSES
                and open_critical == 0
                and requiring_review == 0
                and adjustment_required == 0
                and not incomplete
            ),
            open_critical_exceptions=open_critical,
            records_requiring_review=requiring_review,
            records_adjustment_required=adjustment_required,
            incomplete_checklist_items=incomplete,
        )

    @staticmethod
    def _final_net(record: PayrollEmployeeRecord) -> Decimal:
        return (
            record.gross_earnings
            + record.adjustment_earnings
            - record.total_deductions
            - record.adjustment_deductions
        )

    @staticmethod
    def _present_exception(row: PayrollRunException) -> PayrollRunExceptionRead:
        return PayrollRunExceptionRead(
            id=row.id,
            run_id=row.run_id,
            employee=EmployeeSummary.model_validate(row.employee),
            exception_type=PayrollRunExceptionType(row.exception_type),
            severity=PayrollExceptionSeverity(row.severity),
            description=row.description,
            status=PayrollExceptionStatus(row.status),
            resolution=row.resolution,
            resolution_notes=row.resolution_notes,
            resolved_by_name=(
                f"{row.resolved_by.first_name} {row.resolved_by.last_name}".strip()
                if row.resolved_by is not None
                else None
            ),
            resolved_at=row.resolved_at,
            created_at=row.created_at,
        )

    @staticmethod
    def _present_checklist(row: PayrollReviewChecklist) -> ChecklistItemRead:
        return ChecklistItemRead(
            item_key=row.item_key,
            label=row.label,
            completed=row.completed,
            completed_by_name=(
                f"{row.completed_by.first_name} {row.completed_by.last_name}".strip()
                if row.completed_by is not None
                else None
            ),
            completed_at=row.completed_at,
        )

    @staticmethod
    def _present_comment(row: PayrollReviewComment, author_name: str | None) -> ReviewCommentRead:
        return ReviewCommentRead(
            id=row.id,
            run_id=row.run_id,
            employee=(EmployeeSummary.model_validate(row.employee) if row.employee is not None else None),
            comment=row.comment,
            author_name=author_name,
            created_at=row.created_at,
        )
