from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.models.document import Document
from app.models.requisition import (
    JobRequisition,
    Notification,
    RequisitionApproval,
    RequisitionAttachment,
    RequisitionHistory,
)
from app.repositories.base import BaseRepository
from app.schemas.requisition import RequisitionListParams


class RequisitionRepository(BaseRepository[JobRequisition]):
    model = JobRequisition
    sortable = frozenset(
        {"created_at", "job_title", "requisition_code", "status", "priority", "target_joining_date"}
    )

    async def get(self, entity_id: uuid.UUID, *, include_deleted: bool = False) -> JobRequisition | None:
        stmt = (
            self._base_select(include_deleted=include_deleted)
            .where(JobRequisition.id == entity_id)
            .options(
                selectinload(JobRequisition.approvals),
                selectinload(JobRequisition.attachments),
                selectinload(JobRequisition.history),
            )
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def search(self, p: RequisitionListParams) -> tuple[Sequence[JobRequisition], int]:
        c: list[Any] = []
        if p.search:
            c.append(
                or_(
                    JobRequisition.job_title.ilike(f"%{p.search}%"),
                    JobRequisition.requisition_code.ilike(f"%{p.search}%"),
                )
            )
        for key in ("business_unit_id", "hiring_manager_id", "status", "priority"):
            value = getattr(p, key)
            if value is not None:
                c.append(getattr(JobRequisition, key) == value)
        if p.date_from:
            c.append(func.date(JobRequisition.created_at) >= p.date_from)
        if p.date_to:
            c.append(func.date(JobRequisition.created_at) <= p.date_to)
        if p.sort_by not in self.sortable:
            raise ValueError("Unsupported sort column")
        return await self.list(
            *c, offset=p.offset, limit=p.limit, order_by=p.sort_by, descending=p.sort_order == "desc"
        ), await self.count(*c)


class ApprovalRepository(BaseRepository[RequisitionApproval]):
    model = RequisitionApproval


class AttachmentRepository(BaseRepository[RequisitionAttachment]):
    model = RequisitionAttachment

    async def document_exists(self, document_id: uuid.UUID) -> bool:
        return (
            await self.session.scalar(
                select(Document.id).where(Document.id == document_id, Document.deleted_at.is_(None))
            )
            is not None
        )


class HistoryRepository(BaseRepository[RequisitionHistory]):
    model = RequisitionHistory


class NotificationRepository(BaseRepository[Notification]):
    model = Notification

    async def for_user(self, user_id: uuid.UUID) -> Sequence[Notification]:
        return await self.list(Notification.user_id == user_id, limit=100)
