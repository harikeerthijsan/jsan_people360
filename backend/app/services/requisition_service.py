from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from openpyxl import Workbook
from sqlalchemy import func, select

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.requisition import (
    JobRequisition,
    Notification,
    RequisitionApproval,
    RequisitionAttachment,
    RequisitionHistory,
)
from app.repositories.requisition_repository import (
    ApprovalRepository,
    AttachmentRepository,
    HistoryRepository,
    NotificationRepository,
    RequisitionRepository,
)
from app.schemas.requisition import (
    AttachmentLink,
    DashboardStats,
    RequisitionCreate,
    RequisitionListParams,
    RequisitionUpdate,
)
from app.services.audit_service import AuditService
from app.utils.datetime import utc_now


class RequisitionService:
    def __init__(
        self,
        repo: RequisitionRepository,
        approvals: ApprovalRepository,
        attachments: AttachmentRepository,
        history: HistoryRepository,
        notifications: NotificationRepository,
        audit: AuditService,
    ) -> None:
        self.repo, self.approvals, self.attachments, self.history, self.notifications, self.audit = (
            repo,
            approvals,
            attachments,
            history,
            notifications,
            audit,
        )

    async def get(self, rid: uuid.UUID) -> JobRequisition:
        row = await self.repo.get(rid, include_deleted=True)
        if not row:
            raise NotFoundError("Job requisition")
        return row

    async def list(self, p: RequisitionListParams) -> tuple[Sequence[JobRequisition], int]:
        return await self.repo.search(p)

    async def create(self, p: RequisitionCreate, actor: uuid.UUID) -> JobRequisition:
        duplicate = await self.repo.find(
            JobRequisition.job_title.ilike(p.job_title),
            JobRequisition.business_unit_id == p.business_unit_id,
            JobRequisition.status.in_(["draft", "pending_approval", "approved", "open"]),
        )
        if duplicate:
            raise ConflictError(
                "A live requisition for this job and business unit already exists.",
                error_code="duplicate_requisition",
            )
        row = await self.repo.add(
            JobRequisition(**p.model_dump(), approvals=[], attachments=[], history=[]), actor_id=actor
        )
        await self._history(row, "created", None, "draft", actor)
        await self.audit.record_success(
            "requisition.created",
            actor_id=actor,
            entity_type="requisition",
            entity_id=row.id,
            description=f"Created {row.requisition_code}",
        )
        return row

    async def update(self, rid: uuid.UUID, p: RequisitionUpdate, actor: uuid.UUID) -> JobRequisition:
        row = await self.get(rid)
        if row.status not in {"draft", "rejected"}:
            raise ConflictError("Only draft or rejected requisitions can be edited.")
        await self.repo.update(row, p.model_dump(), actor_id=actor)
        await self._history(row, "updated", row.status, row.status, actor)
        await self.audit.record_success(
            "requisition.updated", actor_id=actor, entity_type="requisition", entity_id=row.id
        )
        return row

    async def submit(self, rid: uuid.UUID, actor: uuid.UUID) -> JobRequisition:
        row = await self.get(rid)
        if row.status not in {"draft", "rejected"}:
            raise ConflictError("This requisition cannot be submitted.")
        old = row.status
        now = utc_now()
        await self.repo.update(
            row,
            {"status": "pending_approval", "submitted_at": now, "current_approval_sequence": 1},
            actor_id=actor,
        )
        for seq, (role, user) in enumerate(
            (
                ("Hiring Manager", row.hiring_manager_id),
                ("Second approver", row.second_approver_id),
                ("HR", row.hr_approver_id),
            ),
            1,
        ):
            await self.approvals.add(
                RequisitionApproval(
                    requisition_id=row.id,
                    sequence=seq,
                    role_name=role,
                    approver_id=user,
                    status="pending" if seq == 1 else "waiting",
                ),
                actor_id=actor,
            )
        await self._history(row, "submitted", old, row.status, actor)
        await self._notify(
            row.hiring_manager_id,
            "Approval requested",
            f"{row.requisition_code} requires your approval",
            row,
            actor,
        )
        await self.audit.record_success(
            "requisition.submitted", actor_id=actor, entity_type="requisition", entity_id=row.id
        )
        return row

    async def act(
        self, rid: uuid.UUID, action: str, comments: str | None, actor: uuid.UUID
    ) -> JobRequisition:
        row = await self.get(rid)
        lifecycle = {
            "open": ({"approved", "on_hold"}, "open"),
            "hold": ({"open"}, "on_hold"),
            "resume": ({"on_hold"}, "open"),
        }
        if action in lifecycle:
            allowed, target = lifecycle[action]
            if row.status not in allowed:
                raise ConflictError(f"A {row.status} requisition cannot be moved to {target}.")
            return await self._terminal(row, target, action, comments, actor)
        if action == "cancel":
            return await self._terminal(row, "cancelled", action, comments, actor)
        if action == "close":
            if row.status not in {"approved", "open", "on_hold"}:
                raise ConflictError("Only an approved or open requisition can be closed.")
            row.closed_at = utc_now()
            return await self._terminal(row, "closed", action, comments, actor)
        if row.status != "pending_approval":
            raise ConflictError("This requisition is not awaiting approval.")
        approval = await self.approvals.get_by(requisition_id=row.id, sequence=row.current_approval_sequence)
        if not approval or approval.approver_id != actor:
            raise ConflictError(
                "This approval is assigned to another user.", error_code="not_current_approver"
            )
        if action == "approve":
            await self.approvals.update(
                approval, {"status": "approved", "comments": comments, "acted_at": utc_now()}, actor_id=actor
            )
            if approval.sequence == 3:
                row.approved_at = utc_now()
                result = await self._terminal(row, "approved", action, comments, actor)
                await self._notify(
                    row.created_by, "Requisition approved", f"{row.requisition_code} was approved", row, actor
                )
                return result
            row.current_approval_sequence = approval.sequence + 1
            next_ = await self.approvals.get_by(requisition_id=row.id, sequence=row.current_approval_sequence)
            if next_ is None:
                raise NotFoundError("Requisition approver")
            await self.approvals.update(next_, {"status": "pending"}, actor_id=actor)
            await self._notify(
                next_.approver_id,
                "Approval requested",
                f"{row.requisition_code} requires your approval",
                row,
                actor,
            )
        elif action in {"reject", "send_back"}:
            await self.approvals.update(
                approval, {"status": action, "comments": comments, "acted_at": utc_now()}, actor_id=actor
            )
            await self._terminal(row, "rejected" if action == "reject" else "draft", action, comments, actor)
        else:
            raise ValidationError("Unsupported workflow action")
        await self._history(row, action, "pending_approval", row.status, actor, comments)
        await self.audit.record_success(
            f"requisition.{action}", actor_id=actor, entity_type="requisition", entity_id=row.id
        )
        return row

    async def attach(self, rid: uuid.UUID, p: AttachmentLink, actor: uuid.UUID) -> RequisitionAttachment:
        row = await self.get(rid)
        if not await self.attachments.document_exists(p.document_id):
            raise NotFoundError("Document")
        item = await self.attachments.add(
            RequisitionAttachment(requisition_id=row.id, **p.model_dump()), actor_id=actor
        )
        await self._history(row, "attachment_uploaded", row.status, row.status, actor)
        await self.audit.record_success(
            "requisition.attachment.uploaded", actor_id=actor, entity_type="requisition", entity_id=row.id
        )
        return item

    async def dashboard(self) -> DashboardStats:
        s = self.repo.session

        async def count(*criteria: Any) -> int:
            value = await s.scalar(
                select(func.count())
                .select_from(JobRequisition)
                .where(JobRequisition.deleted_at.is_(None), *criteria)
            )
            return int(value or 0)

        async def grouped(column: Any) -> list[dict[str, Any]]:
            rows = (
                await s.execute(
                    select(column, func.sum(JobRequisition.openings))
                    .where(JobRequisition.deleted_at.is_(None))
                    .group_by(column)
                )
            ).all()
            return [{"label": str(k), "count": int(v)} for k, v in rows]

        trend_rows = (
            await s.execute(
                select(
                    func.extract("year", JobRequisition.created_at),
                    func.extract("month", JobRequisition.created_at),
                    func.sum(JobRequisition.openings),
                )
                .where(JobRequisition.deleted_at.is_(None))
                .group_by(
                    func.extract("year", JobRequisition.created_at),
                    func.extract("month", JobRequisition.created_at),
                )
                .order_by(
                    func.extract("year", JobRequisition.created_at),
                    func.extract("month", JobRequisition.created_at),
                )
            )
        ).all()
        trend = [
            {"label": f"{int(year):04d}-{int(month):02d}", "count": int(openings)}
            for year, month, openings in trend_rows
        ]

        today = date.today()
        return DashboardStats(
            total_open=await count(JobRequisition.status == "open"),
            pending_approvals=await count(JobRequisition.status == "pending_approval"),
            approved=await count(JobRequisition.status == "approved"),
            closed=await count(JobRequisition.status == "closed"),
            expired=await count(
                JobRequisition.target_joining_date < today,
                JobRequisition.status.notin_(["closed", "cancelled"]),
            ),
            upcoming_targets=await count(JobRequisition.target_joining_date >= today),
            by_business_unit=await grouped(JobRequisition.business_unit_id),
            hiring_trend=trend,
        )

    async def export(self, p: RequisitionListParams, fmt: str) -> tuple[bytes, str]:
        rows, _ = await self.repo.search(p.model_copy(update={"page": 1, "page_size": 100}))
        headers = ["Requisition", "Job title", "Status", "Priority", "Openings", "Target date"]
        data = [
            [r.requisition_code, r.job_title, r.status, r.priority, r.openings, str(r.target_joining_date)]
            for r in rows
        ]
        if fmt == "csv":
            text = io.StringIO()
            w = csv.writer(text)
            w.writerow(headers)
            w.writerows(data)
            return text.getvalue().encode(), "text/csv"
        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        for row in data:
            ws.append(row)
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    async def user_notifications(self, user_id: uuid.UUID) -> Sequence[Notification]:
        return await self.notifications.for_user(user_id)

    async def mark_notification_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> Notification:
        item = await self.notifications.get(notification_id)
        if item is None or item.user_id != user_id:
            raise NotFoundError("Notification")
        return await self.notifications.update(item, {"read_at": utc_now()}, actor_id=user_id)

    async def _terminal(
        self,
        row: JobRequisition,
        status: str,
        action: str,
        comments: str | None,
        actor: uuid.UUID,
    ) -> JobRequisition:
        old = row.status
        await self.repo.update(row, {"status": status, "current_approval_sequence": None}, actor_id=actor)
        await self._history(row, action, old, status, actor, comments)
        await self.audit.record_success(
            f"requisition.{action}", actor_id=actor, entity_type="requisition", entity_id=row.id
        )
        return row

    async def _history(
        self,
        row: JobRequisition,
        action: str,
        old: str | None,
        new: str | None,
        actor: uuid.UUID,
        comments: str | None = None,
    ) -> None:
        await self.history.add(
            RequisitionHistory(
                requisition_id=row.id, action=action, from_status=old, to_status=new, comments=comments
            ),
            actor_id=actor,
        )

    async def _notify(
        self,
        user: uuid.UUID | None,
        title: str,
        message: str,
        row: JobRequisition,
        actor: uuid.UUID,
    ) -> None:
        if user:
            await self.notifications.add(
                Notification(
                    user_id=user,
                    title=title,
                    message=message,
                    link=f"/requisitions/{row.id}",
                    notification_type="requisition",
                ),
                actor_id=actor,
            )
