from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.models.document import Document
from app.models.employee import Employee
from app.models.interview import (
    Interview,
    InterviewAttachment,
    InterviewFeedback,
    InterviewPanel,
    InterviewScheduleHistory,
    InterviewScore,
)
from app.repositories.base import BaseRepository
from app.schemas.interview import InterviewListParams


class InterviewRepository(BaseRepository[Interview]):
    model = Interview

    def detailed(self) -> Select[tuple[Interview]]:
        return self._base_select().options(
            selectinload(Interview.panels),
            selectinload(Interview.feedback).selectinload(InterviewFeedback.scores),
            selectinload(Interview.history),
            selectinload(Interview.attachments),
        )

    async def get_detailed(self, interview_id: uuid.UUID) -> Interview | None:
        stmt = self.detailed().where(Interview.id == interview_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def search(self, p: InterviewListParams) -> tuple[Sequence[Interview], int]:
        stmt = self.detailed()
        if p.interviewer_id:
            stmt = stmt.join(InterviewPanel).where(
                InterviewPanel.employee_id == p.interviewer_id, InterviewPanel.deleted_at.is_(None)
            )
        criteria: list[Any] = []
        if p.search:
            criteria.append(
                or_(
                    Interview.interview_code.ilike(f"%{p.search}%"),
                    Interview.interview_round.ilike(f"%{p.search}%"),
                )
            )
        for name in ("candidate_id", "status"):
            if value := getattr(p, name):
                criteria.append(getattr(Interview, name) == value)
        if p.date_from:
            criteria.append(Interview.starts_at >= p.date_from)
        if p.date_to:
            criteria.append(Interview.starts_at <= p.date_to)
        stmt = stmt.where(*criteria)
        total = int((await self.session.scalar(select(func.count()).select_from(stmt.subquery()))) or 0)
        stmt = stmt.order_by(Interview.starts_at.desc()).offset((p.page - 1) * p.page_size).limit(p.page_size)
        return (await self.session.execute(stmt)).scalars().unique().all(), total

    async def candidate_conflict(
        self,
        candidate_id: uuid.UUID,
        starts_at: datetime,
        ends_at: datetime,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        criteria: list[Any] = [
            Interview.candidate_id == candidate_id,
            Interview.status.in_(["scheduled", "rescheduled"]),
            Interview.starts_at < ends_at,
            Interview.ends_at > starts_at,
            Interview.deleted_at.is_(None),
        ]
        if exclude_id:
            criteria.append(Interview.id != exclude_id)
        return bool(await self.session.scalar(select(func.count()).select_from(Interview).where(*criteria)))

    async def panel_conflicts(
        self,
        employee_ids: Collection[uuid.UUID],
        starts_at: datetime,
        ends_at: datetime,
        exclude_id: uuid.UUID | None = None,
    ) -> set[uuid.UUID]:
        stmt = (
            select(InterviewPanel.employee_id)
            .join(Interview)
            .where(
                InterviewPanel.employee_id.in_(employee_ids),
                InterviewPanel.deleted_at.is_(None),
                Interview.deleted_at.is_(None),
                Interview.status.in_(["scheduled", "rescheduled"]),
                Interview.starts_at < ends_at,
                Interview.ends_at > starts_at,
            )
        )
        if exclude_id:
            stmt = stmt.where(Interview.id != exclude_id)
        return set((await self.session.execute(stmt)).scalars().all())

    async def employees_exist(self, employee_ids: Collection[uuid.UUID]) -> bool:
        count = await self.session.scalar(
            select(func.count())
            .select_from(Employee)
            .where(Employee.id.in_(employee_ids), Employee.deleted_at.is_(None))
        )
        return int(count or 0) == len(set(employee_ids))


class PanelRepository(BaseRepository[InterviewPanel]):
    model = InterviewPanel


class FeedbackRepository(BaseRepository[InterviewFeedback]):
    model = InterviewFeedback


class ScoreRepository(BaseRepository[InterviewScore]):
    model = InterviewScore


class ScheduleHistoryRepository(BaseRepository[InterviewScheduleHistory]):
    model = InterviewScheduleHistory


class InterviewAttachmentRepository(BaseRepository[InterviewAttachment]):
    model = InterviewAttachment

    async def document_exists(self, document_id: uuid.UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.id == document_id, Document.deleted_at.is_(None))
            )
        )
