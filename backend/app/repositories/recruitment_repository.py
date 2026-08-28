from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.models.document import Document
from app.models.recruitment import (
    Candidate,
    CandidateDocument,
    CandidateSkill,
    CandidateSource,
    CandidateStageHistory,
    CandidateTalentPool,
    JobOpening,
    RecruiterNote,
    RecruitmentStage,
    TalentPool,
)
from app.repositories.base import BaseRepository
from app.schemas.recruitment import CandidateListParams


class OpeningRepository(BaseRepository[JobOpening]):
    model = JobOpening

    async def all(self) -> Sequence[JobOpening]:
        return await self.list(limit=500)


class CandidateRepository(BaseRepository[Candidate]):
    model = Candidate

    def _with_details(self) -> Select[tuple[Candidate]]:
        return self._base_select().options(
            selectinload(Candidate.skills),
            selectinload(Candidate.documents),
            selectinload(Candidate.stage_history),
            selectinload(Candidate.notes),
        )

    async def get_detailed(self, candidate_id: uuid.UUID) -> Candidate | None:
        return (
            (
                await self.session.execute(
                    self._with_details()
                    .where(Candidate.id == candidate_id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .unique()
            .one_or_none()
        )

    async def duplicates(self, email: str, mobile: str) -> Sequence[Candidate]:
        stmt = self._with_details().where(
            or_(func.lower(Candidate.email) == email.lower(), Candidate.mobile_number == mobile)
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def search(self, p: CandidateListParams) -> tuple[Sequence[Candidate], int]:
        stmt = self._with_details()
        criteria: list[Any] = []
        if p.search:
            term = f"%{p.search}%"
            criteria.append(
                or_(
                    Candidate.first_name.ilike(term),
                    Candidate.last_name.ilike(term),
                    Candidate.email.ilike(term),
                    Candidate.candidate_code.ilike(term),
                )
            )
        for name in ("source_id", "recruiter_id", "stage_id", "job_opening_id"):
            value = getattr(p, name)
            if value:
                criteria.append(getattr(Candidate, name) == value)
        if p.location:
            criteria.append(Candidate.current_location.ilike(f"%{p.location}%"))
        if p.experience_min is not None:
            criteria.append(Candidate.experience_years >= p.experience_min)
        if p.experience_max is not None:
            criteria.append(Candidate.experience_years <= p.experience_max)
        if p.notice_period_max is not None:
            criteria.append(Candidate.notice_period_days <= p.notice_period_max)
        if p.skill:
            stmt = stmt.join(CandidateSkill).where(CandidateSkill.name.ilike(f"%{p.skill}%"))
        stmt = stmt.where(*criteria)
        total = int(
            (await self.session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        )
        stmt = (
            stmt.order_by(Candidate.created_at.desc()).offset((p.page - 1) * p.page_size).limit(p.page_size)
        )
        return (await self.session.execute(stmt)).scalars().unique().all(), total


class SourceRepository(BaseRepository[CandidateSource]):
    model = CandidateSource


class StageRepository(BaseRepository[RecruitmentStage]):
    model = RecruitmentStage


class CandidateDocumentRepository(BaseRepository[CandidateDocument]):
    model = CandidateDocument

    async def document_exists(self, document_id: uuid.UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.id == document_id, Document.deleted_at.is_(None))
            )
        )


class SkillRepository(BaseRepository[CandidateSkill]):
    model = CandidateSkill


class StageHistoryRepository(BaseRepository[CandidateStageHistory]):
    model = CandidateStageHistory


class NoteRepository(BaseRepository[RecruiterNote]):
    model = RecruiterNote


class TalentPoolRepository(BaseRepository[TalentPool]):
    model = TalentPool


class PoolMemberRepository(BaseRepository[CandidateTalentPool]):
    model = CandidateTalentPool
