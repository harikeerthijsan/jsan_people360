"""Payroll approval and finalization (Phase 6).

The last mile of a payroll run, shaped by three rules.

**The state machine is the API.** There is no "set status" endpoint. Submit
works only on a completed review, approve and send-back only on a submitted
run, finalize only on an approved one — each its own permission, each
re-validating the gates rather than trusting that a screen already did.

**Approval is a recorded decision.** Every submit, approval, send-back and
finalization appends a trail row with its actor, its comment or reason, and
the totals the actor was looking at. A run that cycles through corrections
keeps every cycle. Nothing in the trail is updated or deleted.

**Finalization is the end of change.** Finalizing writes one immutable,
fully denormalized snapshot per employee — names, dates, line items,
adjustments, sign-off — locks the run against every mutation path, and
closes its period. If a salary, an attendance record or a leave changes
afterwards, the finalized payroll keeps saying what was actually paid; a
future correction is a controlled process of a later phase, never an edit.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError
from app.models.audit_log import AuditAction
from app.models.enums import (
    PayrollAdjustmentStatus,
    PayrollApprovalAction,
    PayrollExceptionSeverity,
    PayrollExceptionStatus,
    PayrollPeriodStatus,
    PayrollRecordStatus,
    PayrollRunStatus,
)
from app.models.payroll import (
    PayrollAdjustment,
    PayrollApproval,
    PayrollEmployeeRecord,
    PayrollFinalSnapshot,
    PayrollLineItem,
    PayrollRun,
)
from app.repositories.payroll_repository import (
    EmployeeCompensationRepository,
    PayrollAdjustmentRepository,
    PayrollApprovalRepository,
    PayrollEmployeeRecordRepository,
    PayrollFinalSnapshotRepository,
    PayrollPeriodRepository,
    PayrollReviewChecklistRepository,
    PayrollRunExceptionRepository,
    PayrollRunRepository,
)
from app.schemas.payroll import (
    ApprovalEmployeeSummary,
    ApprovalReviewSummary,
    PayrollApprovalDecision,
    PayrollApprovalRead,
    PayrollApprovalSummary,
    PayrollFinalizeRequest,
    PayrollReturnRequest,
    PayrollRunListParams,
    PayrollRunRead,
    PayrollSnapshotRead,
)
from app.services.audit_service import AuditService
from app.services.payroll_run_service import present_run, user_name
from app.utils.datetime import utc_now

#: Statuses a run passes through *after* review completion, in which the
#: completed review still stands.
_REVIEW_STANDS = frozenset(
    {
        PayrollRunStatus.REVIEW_COMPLETE.value,
        PayrollRunStatus.PENDING_APPROVAL.value,
        PayrollRunStatus.APPROVED.value,
        PayrollRunStatus.FINALIZED.value,
    }
)


class PayrollApprovalService:
    """Approval queue, decisions, and finalization over payroll runs."""

    def __init__(
        self,
        runs: PayrollRunRepository,
        records: PayrollEmployeeRecordRepository,
        exceptions: PayrollRunExceptionRepository,
        adjustments: PayrollAdjustmentRepository,
        checklists: PayrollReviewChecklistRepository,
        periods: PayrollPeriodRepository,
        compensation: EmployeeCompensationRepository,
        approvals: PayrollApprovalRepository,
        snapshots: PayrollFinalSnapshotRepository,
        audit: AuditService,
    ) -> None:
        self.runs = runs
        self.records = records
        self.exceptions = exceptions
        self.adjustments = adjustments
        self.checklists = checklists
        self.periods = periods
        self.compensation = compensation
        self.approvals = approvals
        self.snapshots = snapshots
        self.audit = audit

    # ==================================================================
    # Queue and history
    # ==================================================================
    async def queue(self, params: PayrollRunListParams) -> tuple[list[PayrollRunRead], int]:
        """Runs waiting for an approver, enriched with what the approver
        weighs: open exceptions and active adjustments."""
        forced = params.model_copy(update={"status": PayrollRunStatus.PENDING_APPROVAL})
        return await self._enriched_runs(forced)

    async def history(self, params: PayrollRunListParams) -> tuple[list[PayrollRunRead], int]:
        """Finalized runs, newest first — the read-only record of what was paid."""
        forced = params.model_copy(update={"status": PayrollRunStatus.FINALIZED})
        return await self._enriched_runs(forced)

    async def _enriched_runs(self, params: PayrollRunListParams) -> tuple[list[PayrollRunRead], int]:
        rows, total = await self.runs.search(params)
        run_ids = [row.id for row in rows]
        exception_counts = await self.exceptions.open_counts(run_ids)
        adjustment_counts = await self.adjustments.active_counts(run_ids)
        return [
            present_run(row, exception_counts.get(row.id, (0, 0)), adjustment_counts.get(row.id, 0))
            for row in rows
        ], total

    # ==================================================================
    # Approval summary
    # ==================================================================
    async def summary(self, run_id: uuid.UUID) -> PayrollApprovalSummary:
        run = await self._require_run(run_id)
        records = await self.records.for_run(run.id)
        exceptions = await self.exceptions.for_run(run.id)
        adjustments = await self.adjustments.for_run(run.id)
        active = [a for a in adjustments if a.status == PayrollAdjustmentStatus.ACTIVE.value]
        blockers = await self._approval_blockers(run, records)

        by_severity = {severity.value: 0 for severity in PayrollExceptionSeverity}
        for exception in exceptions:
            by_severity[exception.severity] += 1
        open_exceptions = sum(1 for e in exceptions if e.status == PayrollExceptionStatus.OPEN.value)

        return PayrollApprovalSummary(
            run=present_run(
                run,
                (await self.exceptions.open_counts([run.id])).get(run.id, (0, 0)),
                len(active),
            ),
            employees=ApprovalEmployeeSummary(
                included=sum(1 for r in records if r.status != PayrollRecordStatus.EXCLUDED.value),
                excluded=sum(1 for r in records if r.status == PayrollRecordStatus.EXCLUDED.value),
                with_adjustments=len({a.employee_id for a in active}),
                with_exceptions=len({e.employee_id for e in exceptions}),
            ),
            review=ApprovalReviewSummary(
                review_completed=run.status in _REVIEW_STANDS,
                reviewer_name=user_name(run.review_completed_by),
                critical_exceptions=by_severity[PayrollExceptionSeverity.CRITICAL.value],
                error_exceptions=by_severity[PayrollExceptionSeverity.ERROR.value],
                warning_exceptions=by_severity[PayrollExceptionSeverity.WARNING.value],
                open_exceptions=open_exceptions,
                adjustment_count=len(active),
            ),
            blockers=blockers,
            can_approve=run.status == PayrollRunStatus.PENDING_APPROVAL.value and not blockers,
            trail=[self._present_step(step) for step in await self.approvals.for_run(run.id)],
        )

    # ==================================================================
    # Workflow acts
    # ==================================================================
    async def submit(self, run_id: uuid.UUID, *, actor_id: uuid.UUID) -> PayrollRunRead:
        run = await self._require_run(run_id)
        if run.status != PayrollRunStatus.REVIEW_COMPLETE.value:
            raise ConflictError(
                "Only a run whose review is complete can be submitted for approval.",
                error_code="not_review_complete",
            )
        await self._require_no_blockers(run)
        await self.runs.update(
            run,
            {
                "status": PayrollRunStatus.PENDING_APPROVAL.value,
                "submitted_at": utc_now(),
                "submitted_by_id": actor_id,
            },
            actor_id=actor_id,
        )
        await self.runs.session.refresh(run, ["submitted_by"])
        await self._append_step(run, PayrollApprovalAction.SUBMITTED, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.PAYROLL_RUN_SUBMITTED,
            actor_id=actor_id,
            entity_type="payroll_run",
            entity_id=run.id,
            description=f"Submitted payroll run {run.run_code} ({run.period.name}) for approval",
            context={"employees": run.employee_count},
        )
        return present_run(run)

    async def approve(
        self, run_id: uuid.UUID, payload: PayrollApprovalDecision, *, actor_id: uuid.UUID
    ) -> PayrollRunRead:
        run = await self._require_run(run_id)
        if run.status != PayrollRunStatus.PENDING_APPROVAL.value:
            raise ConflictError(
                "Only a run submitted for approval can be approved.",
                error_code="not_pending_approval",
            )
        # The gates are re-checked at the moment of the decision — a screen
        # that showed a clean run ten minutes ago is not an authority.
        await self._require_no_blockers(run)
        await self.runs.update(
            run,
            {
                "status": PayrollRunStatus.APPROVED.value,
                "approved_at": utc_now(),
                "approved_by_id": actor_id,
                "approval_comment": payload.comment,
            },
            actor_id=actor_id,
        )
        await self.runs.session.refresh(run, ["approved_by"])
        await self._append_step(
            run, PayrollApprovalAction.APPROVED, actor_id=actor_id, comment=payload.comment
        )
        await self.audit.record_success(
            AuditAction.PAYROLL_RUN_APPROVED,
            actor_id=actor_id,
            entity_type="payroll_run",
            entity_id=run.id,
            description=f"Approved payroll run {run.run_code} ({run.period.name}): {payload.comment}",
            context={"employees": run.employee_count},
        )
        return present_run(run)

    async def send_back(
        self, run_id: uuid.UUID, payload: PayrollReturnRequest, *, actor_id: uuid.UUID
    ) -> PayrollRunRead:
        run = await self._require_run(run_id)
        if run.status != PayrollRunStatus.PENDING_APPROVAL.value:
            raise ConflictError(
                "Only a run submitted for approval can be returned for correction.",
                error_code="not_pending_approval",
            )
        await self.runs.update(
            run,
            {
                "status": PayrollRunStatus.RETURNED.value,
                "returned_at": utc_now(),
                "returned_by_id": actor_id,
                "return_reason": payload.reason,
            },
            actor_id=actor_id,
        )
        await self.runs.session.refresh(run, ["returned_by"])
        await self._append_step(
            run, PayrollApprovalAction.RETURNED, actor_id=actor_id, comment=payload.reason
        )
        await self.audit.record_success(
            AuditAction.PAYROLL_RUN_RETURNED,
            actor_id=actor_id,
            entity_type="payroll_run",
            entity_id=run.id,
            description=(
                f"Returned payroll run {run.run_code} ({run.period.name}) for correction: "
                f"{payload.reason}"
            ),
        )
        return present_run(run)

    async def finalize(
        self, run_id: uuid.UUID, payload: PayrollFinalizeRequest, *, actor_id: uuid.UUID
    ) -> PayrollRunRead:
        run = await self._require_run(run_id)
        if run.status != PayrollRunStatus.APPROVED.value:
            raise ConflictError("Only an approved run can be finalized.", error_code="not_approved")
        if await self.snapshots.for_run(run.id):
            raise ConflictError("This run already has final snapshots.", error_code="already_finalized")

        finalized_at = utc_now()
        await self.runs.update(
            run,
            {
                "status": PayrollRunStatus.FINALIZED.value,
                "finalized_at": finalized_at,
                "finalized_by_id": actor_id,
            },
            actor_id=actor_id,
        )
        await self.runs.session.refresh(run, ["finalized_by"])
        finalized_by = user_name(run.finalized_by)

        adjustments_by_employee: dict[uuid.UUID, list[PayrollAdjustment]] = {}
        for adjustment in await self.adjustments.for_run(run.id):
            adjustments_by_employee.setdefault(adjustment.employee_id, []).append(adjustment)

        records = await self.records.for_run(run.id)
        for record in records:
            await self.snapshots.add(
                await self._snapshot(
                    run,
                    record,
                    adjustments_by_employee.get(record.employee_id, []),
                    finalized_by=finalized_by,
                    finalized_at=finalized_at,
                ),
                actor_id=actor_id,
            )

        # The period locks with the run: no second normal run can ever be
        # opened for it, and the period screens show it closed.
        await self.periods.update(
            run.period, {"status": PayrollPeriodStatus.FINALIZED.value}, actor_id=actor_id
        )

        await self._append_step(
            run, PayrollApprovalAction.FINALIZED, actor_id=actor_id, comment=payload.comment
        )
        await self.audit.record_success(
            AuditAction.PAYROLL_RUN_FINALIZED,
            actor_id=actor_id,
            entity_type="payroll_run",
            entity_id=run.id,
            description=f"Finalized payroll run {run.run_code} ({run.period.name})",
            context={
                "employees": run.employee_count,
                "snapshots": len(records),
                "total_net": str(run.total_net),
            },
        )
        return present_run(run)

    # ==================================================================
    # Finalized reads
    # ==================================================================
    async def run_snapshots(self, run_id: uuid.UUID) -> list[PayrollSnapshotRead]:
        run = await self._require_run(run_id)
        if run.status != PayrollRunStatus.FINALIZED.value:
            raise ConflictError(
                "This run has not been finalized — its numbers may still change.",
                error_code="not_finalized",
            )
        rows = await self.snapshots.for_run(run.id)
        return [PayrollSnapshotRead.model_validate(row) for row in rows]

    # ==================================================================
    # Internals
    # ==================================================================
    async def _require_run(self, run_id: uuid.UUID) -> PayrollRun:
        run = await self.runs.get(run_id)
        if run is None:
            raise NotFoundError("Payroll run")
        return run

    async def _require_no_blockers(self, run: PayrollRun) -> None:
        blockers = await self._approval_blockers(run, await self.records.for_run(run.id))
        if blockers:
            raise ConflictError(
                "The payroll cannot be approved: " + " ".join(blockers),
                error_code="approval_blocked",
            )

    async def _approval_blockers(
        self, run: PayrollRun, records: Sequence[PayrollEmployeeRecord]
    ) -> list[str]:
        """Every reason this run may not be approved, stated for a human.

        Review completion already enforced most of these; they are re-derived
        here from the data rather than trusted, because the whole point of an
        approval gate is that it does not take anybody's word for it.
        """
        if not records or run.calculated_at is None:
            return ["The payroll has not been calculated."]
        blockers: list[str] = []
        if run.status not in _REVIEW_STANDS:
            blockers.append("The review has not been completed.")
        open_critical = len(
            await self.exceptions.for_run(
                run.id,
                status=PayrollExceptionStatus.OPEN.value,
                severity=PayrollExceptionSeverity.CRITICAL.value,
            )
        )
        if open_critical:
            blockers.append(f"{open_critical} critical exception(s) remain unresolved.")
        requiring = sum(1 for r in records if r.status == PayrollRecordStatus.REQUIRES_REVIEW.value)
        if requiring:
            blockers.append(
                f"{requiring} employee record(s) could not be calculated and still require review."
            )
        adjustment_required = sum(
            1 for r in records if r.status == PayrollRecordStatus.ADJUSTMENT_REQUIRED.value
        )
        if adjustment_required:
            blockers.append(
                f"{adjustment_required} record(s) are marked as needing an adjustment "
                "that has not been made."
            )
        incomplete = [row.label for row in await self.checklists.for_run(run.id) if not row.completed]
        if incomplete:
            blockers.append("Checklist items are incomplete: " + ", ".join(incomplete) + ".")
        gross = sum((r.gross_earnings + r.adjustment_earnings for r in records), Decimal("0"))
        deductions = sum((r.total_deductions + r.adjustment_deductions for r in records), Decimal("0"))
        if (
            run.total_gross != gross
            or run.total_deductions != deductions
            or run.total_net != gross - deductions
        ):
            blockers.append(
                "The run's totals do not reconcile with its employee records — recalculate first."
            )
        return blockers

    async def _append_step(
        self,
        run: PayrollRun,
        action: PayrollApprovalAction,
        *,
        actor_id: uuid.UUID,
        comment: str | None = None,
    ) -> None:
        await self.approvals.add(
            PayrollApproval(
                run_id=run.id,
                action=action.value,
                actor_id=actor_id,
                comment=comment,
                employee_count=run.employee_count,
                total_gross=run.total_gross,
                total_deductions=run.total_deductions,
                total_net=run.total_net,
            ),
            actor_id=actor_id,
        )

    async def _snapshot(
        self,
        run: PayrollRun,
        record: PayrollEmployeeRecord,
        adjustments: list[PayrollAdjustment],
        *,
        finalized_by: str | None,
        finalized_at: datetime,
    ) -> PayrollFinalSnapshot:
        comp = (
            await self.compensation.get(record.compensation_id)
            if record.compensation_id is not None
            else None
        )
        return PayrollFinalSnapshot(
            run_id=run.id,
            employee_id=record.employee_id,
            employee_code=record.employee.employee_code,
            employee_name=record.employee.full_name,
            period_name=run.period.name,
            period_start=run.period.start_date,
            period_end=run.period.end_date,
            pay_date=run.period.pay_date,
            status=record.status,
            exception_reason=record.exception_reason,
            currency=record.currency,
            structure_name=comp.structure.name if comp is not None else None,
            monthly_basic=comp.basic_salary if comp is not None else None,
            monthly_gross=comp.monthly_gross if comp is not None else None,
            annual_ctc=comp.annual_ctc if comp is not None else None,
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
            line_items=[self._line_payload(item) for item in record.line_items],
            adjustments=[self._adjustment_payload(a) for a in adjustments],
            approved_by_name=user_name(run.approved_by),
            approved_at=run.approved_at,
            finalized_by_name=finalized_by,
            finalized_at=finalized_at,
        )

    @staticmethod
    def _line_payload(item: PayrollLineItem) -> dict[str, Any]:
        return {
            "item_type": item.item_type,
            "source": item.source,
            "code": item.code,
            "name": item.name,
            "calculation_basis": item.calculation_basis,
            "original_amount": (str(item.original_amount) if item.original_amount is not None else None),
            "prorated": item.prorated,
            "amount": str(item.amount),
        }

    @staticmethod
    def _adjustment_payload(adjustment: PayrollAdjustment) -> dict[str, Any]:
        return {
            "name": adjustment.name,
            "item_type": adjustment.item_type,
            "amount": str(adjustment.amount),
            "reason": adjustment.reason,
            "status": adjustment.status,
            "cancel_reason": adjustment.cancel_reason,
            "created_at": adjustment.created_at.isoformat(),
        }

    @staticmethod
    def _present_step(step: PayrollApproval) -> PayrollApprovalRead:
        return PayrollApprovalRead(
            id=step.id,
            run_id=step.run_id,
            action=PayrollApprovalAction(step.action),
            actor_name=user_name(step.actor),
            comment=step.comment,
            employee_count=step.employee_count,
            total_gross=step.total_gross,
            total_deductions=step.total_deductions,
            total_net=step.total_net,
            created_at=step.created_at,
        )
