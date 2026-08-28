import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from app.models.offer import (
    Offer,
    OfferApproval,
    OfferSalaryComponent,
    OfferStatusHistory,
    OfferTemplate,
    OfferVersion,
)
from app.repositories.base import BaseRepository
from app.schemas.offer import OfferListParams


class OfferRepository(BaseRepository[Offer]):
    model = Offer

    def detailed(self) -> Select[tuple[Offer]]:
        return self._base_select().options(
            selectinload(Offer.salary_components),
            selectinload(Offer.versions),
            selectinload(Offer.approvals),
            selectinload(Offer.history),
        )

    async def get_detailed(self, oid: uuid.UUID) -> Offer | None:
        return (
            (
                await self.session.execute(
                    self.detailed().where(Offer.id == oid).execution_options(populate_existing=True)
                )
            )
            .scalars()
            .unique()
            .one_or_none()
        )

    async def search(self, p: OfferListParams) -> tuple[Sequence[Offer], int]:
        stmt = self.detailed()
        criteria: list[Any] = []
        if p.status:
            criteria.append(Offer.status == p.status)
        if p.candidate_id:
            criteria.append(Offer.candidate_id == p.candidate_id)
        if p.search:
            criteria.append(Offer.offer_code.ilike(f"%{p.search}%"))
        stmt = stmt.where(*criteria)
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        stmt = stmt.order_by(Offer.created_at.desc()).offset((p.page - 1) * p.page_size).limit(p.page_size)
        return (await self.session.execute(stmt)).scalars().unique().all(), total


class VersionRepository(BaseRepository[OfferVersion]):
    model = OfferVersion


class ApprovalRepository(BaseRepository[OfferApproval]):
    model = OfferApproval


class HistoryRepository(BaseRepository[OfferStatusHistory]):
    model = OfferStatusHistory


class ComponentRepository(BaseRepository[OfferSalaryComponent]):
    model = OfferSalaryComponent


class TemplateRepository(BaseRepository[OfferTemplate]):
    model = OfferTemplate
