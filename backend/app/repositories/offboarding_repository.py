"""Persistence for resignation and offboarding.

Query shapes only. Which employees a caller may reach is decided by
:mod:`app.services.scope_service` and passed in as ``visible_ids``; this module
applies the filter it is given and never derives one of its own. A repository
that quietly filtered by the current user would be a repository whose results
depend on invisible state -- and the HR dashboard, the exports and the
notification fan-out all legitimately need the unfiltered query.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from datetime import date
from typing import Any

from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.orm import selectinload

from app.models.employee import Employee
from app.models.enums import (
    ACTIVE_OFFBOARDING_STATUSES,
    SETTLED_ACCESS_STATUSES,
    SETTLED_ASSET_STATUSES,
    SETTLED_TASK_STATUSES,
    TERMINAL_RESIGNATION_STATUSES,
    OffboardingCaseStatus,
    ResignationStatus,
)
from app.models.offboarding import (
    AccessClearance,
    AssetClearance,
    ExitDocument,
    ExitInterview,
    FinalSettlementTracking,
    HandoverRecord,
    OffboardingCase,
    OffboardingTask,
    Resignation,
    ResignationHistory,
)
from app.repositories.base import BaseRepository
from app.schemas.offboarding import OffboardingListParams, ResignationListParams


def _visible(stmt: Select[Any], column: Any, visible_ids: Collection[uuid.UUID] | None) -> Select[Any]:
    """Narrow to the employees the caller may see.

    ``None`` means unrestricted. An empty collection is the opposite and must
    not collapse into the same branch: it means the caller is entitled to
    nobody, and the honest answer is an empty page rather than everybody's
    separations. This is the same distinction
    :mod:`app.repositories.workforce_repository` draws, spelled the same way.
    """
    if visible_ids is None:
        return stmt
    return stmt.where(column.in_(visible_ids)) if visible_ids else stmt.where(false())


class ResignationRepository(BaseRepository[Resignation]):
    model = Resignation

    def _detailed(self) -> Select[tuple[Resignation]]:
        return self._base_select().options(selectinload(Resignation.history))

    async def get_detailed(self, resignation_id: uuid.UUID) -> Resignation | None:
        stmt = (
            self._detailed().where(Resignation.id == resignation_id).execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def live_for_employee(self, employee_id: uuid.UUID) -> Resignation | None:
        """The one resignation that is still running, if any.

        "Live" is the complement of the terminal set rather than a list of
        active statuses, so a status added later is live by default -- which is
        the safe direction: a new state that nobody remembered to add here would
        otherwise let an employee submit a second resignation.
        """
        stmt = (
            self._detailed()
            .where(
                Resignation.employee_id == employee_id,
                Resignation.status.notin_([s.value for s in TERMINAL_RESIGNATION_STATUSES]),
            )
            .order_by(Resignation.created_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def latest_for_employee(self, employee_id: uuid.UUID) -> Resignation | None:
        """The most recent resignation of any status -- what a completed exit shows."""
        stmt = (
            self._detailed()
            .where(Resignation.employee_id == employee_id)
            .order_by(Resignation.created_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def search(
        self,
        params: ResignationListParams,
        *,
        visible_ids: Collection[uuid.UUID] | None = None,
    ) -> tuple[Sequence[Resignation], int]:
        stmt = _visible(self._detailed(), Resignation.employee_id, visible_ids)
        criteria: list[Any] = []
        if params.status is not None:
            criteria.append(Resignation.status == params.status.value)
        if params.employee_id is not None:
            criteria.append(Resignation.employee_id == params.employee_id)
        if params.from_date is not None:
            criteria.append(Resignation.resignation_date >= params.from_date)
        if params.to_date is not None:
            criteria.append(Resignation.resignation_date <= params.to_date)
        if params.search:
            term = f"%{params.search}%"
            stmt = stmt.join(Employee, Employee.id == Resignation.employee_id)
            criteria.append(
                or_(
                    Resignation.resignation_code.ilike(term),
                    Employee.employee_code.ilike(term),
                    Employee.first_name.ilike(term),
                    Employee.last_name.ilike(term),
                )
            )
        stmt = stmt.where(*criteria)

        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(Resignation.created_at.desc()).offset(params.offset).limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def count_by_status(
        self, *statuses: ResignationStatus, visible_ids: Collection[uuid.UUID] | None = None
    ) -> int:
        stmt = _visible(
            select(func.count()).select_from(Resignation).where(Resignation.deleted_at.is_(None)),
            Resignation.employee_id,
            visible_ids,
        )
        stmt = stmt.where(Resignation.status.in_([s.value for s in statuses]))
        return int(await self.session.scalar(stmt) or 0)


class ResignationHistoryRepository(BaseRepository[ResignationHistory]):
    model = ResignationHistory


class OffboardingCaseRepository(BaseRepository[OffboardingCase]):
    model = OffboardingCase

    def _detailed(self) -> Select[tuple[OffboardingCase]]:
        return self._base_select().options(
            selectinload(OffboardingCase.tasks),
            selectinload(OffboardingCase.assets),
            selectinload(OffboardingCase.access_items),
        )

    async def get_detailed(self, case_id: uuid.UUID) -> OffboardingCase | None:
        stmt = self._detailed().where(OffboardingCase.id == case_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def for_resignation(self, resignation_id: uuid.UUID) -> OffboardingCase | None:
        stmt = self._detailed().where(OffboardingCase.resignation_id == resignation_id)
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def for_employee(self, employee_id: uuid.UUID) -> OffboardingCase | None:
        stmt = (
            self._detailed()
            .where(OffboardingCase.employee_id == employee_id)
            .order_by(OffboardingCase.created_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def search(
        self,
        params: OffboardingListParams,
        *,
        visible_ids: Collection[uuid.UUID] | None = None,
    ) -> tuple[Sequence[OffboardingCase], int]:
        stmt = _visible(self._detailed(), OffboardingCase.employee_id, visible_ids)
        criteria: list[Any] = []
        if params.status is not None:
            criteria.append(OffboardingCase.status == params.status.value)
        if params.employee_id is not None:
            criteria.append(OffboardingCase.employee_id == params.employee_id)
        if params.exiting_before is not None:
            criteria.append(OffboardingCase.last_working_day <= params.exiting_before)
        if params.pending_clearance:
            criteria.append(OffboardingCase.progress_percent < 100)
        if params.search:
            term = f"%{params.search}%"
            stmt = stmt.join(Employee, Employee.id == OffboardingCase.employee_id)
            criteria.append(
                or_(
                    OffboardingCase.case_code.ilike(term),
                    Employee.employee_code.ilike(term),
                    Employee.first_name.ilike(term),
                    Employee.last_name.ilike(term),
                )
            )
        stmt = stmt.where(*criteria)

        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(OffboardingCase.last_working_day.asc())
                    .offset(params.offset)
                    .limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def exiting_between(
        self, start: date, end: date, *, visible_ids: Collection[uuid.UUID] | None = None
    ) -> int:
        stmt = _visible(
            select(func.count())
            .select_from(OffboardingCase)
            .where(
                OffboardingCase.deleted_at.is_(None),
                OffboardingCase.last_working_day.between(start, end),
                OffboardingCase.status != OffboardingCaseStatus.CANCELLED.value,
            ),
            OffboardingCase.employee_id,
            visible_ids,
        )
        return int(await self.session.scalar(stmt) or 0)

    async def effective_last_working_day(self, employee_id: uuid.UUID) -> date | None:
        """The date after which this employee may no longer record new activity.

        Reads the case rather than the employee's status because the two answer
        different questions. ``employment_status`` becomes ``inactive`` when the
        offboarding is *completed*, which can be days after the person actually
        left; the last working day is the date the brief asks about. A cancelled
        case imposes no cut-off, because there is no separation any more.
        """
        stmt = (
            select(OffboardingCase.last_working_day)
            .where(
                OffboardingCase.employee_id == employee_id,
                OffboardingCase.deleted_at.is_(None),
                OffboardingCase.status != OffboardingCaseStatus.CANCELLED.value,
            )
            .order_by(OffboardingCase.last_working_day.desc())
            .limit(1)
        )
        last_working_day: date | None = await self.session.scalar(stmt)
        return last_working_day

    async def pending_clearance_count(self, *, visible_ids: Collection[uuid.UUID] | None = None) -> int:
        stmt = _visible(
            select(func.count())
            .select_from(OffboardingCase)
            .where(
                OffboardingCase.deleted_at.is_(None),
                OffboardingCase.status == OffboardingCaseStatus.IN_PROGRESS.value,
                OffboardingCase.progress_percent < 100,
            ),
            OffboardingCase.employee_id,
            visible_ids,
        )
        return int(await self.session.scalar(stmt) or 0)


class OffboardingTaskRepository(BaseRepository[OffboardingTask]):
    model = OffboardingTask

    async def for_case(self, case_id: uuid.UUID) -> Sequence[OffboardingTask]:
        return await self.list(
            OffboardingTask.case_id == case_id, limit=200, order_by="sequence", descending=False
        )

    async def outstanding_for_owner(self, owner_id: uuid.UUID) -> Sequence[OffboardingTask]:
        return await self.list(
            OffboardingTask.owner_id == owner_id,
            OffboardingTask.status.notin_([s.value for s in SETTLED_TASK_STATUSES]),
            limit=200,
            order_by="due_date",
            descending=False,
        )

    async def outstanding_count(self, case_id: uuid.UUID) -> int:
        return await self.count(
            OffboardingTask.case_id == case_id,
            OffboardingTask.status.notin_([s.value for s in SETTLED_TASK_STATUSES]),
        )


class HandoverRepository(BaseRepository[HandoverRecord]):
    model = HandoverRecord

    async def for_case(self, case_id: uuid.UUID) -> HandoverRecord | None:
        return await self.get_by(case_id=case_id)


class AssetClearanceRepository(BaseRepository[AssetClearance]):
    model = AssetClearance

    async def outstanding_count(self, case_id: uuid.UUID) -> int:
        return await self.count(
            AssetClearance.case_id == case_id,
            AssetClearance.status.notin_([s.value for s in SETTLED_ASSET_STATUSES]),
        )


class AccessClearanceRepository(BaseRepository[AccessClearance]):
    model = AccessClearance

    async def outstanding_count(self, case_id: uuid.UUID) -> int:
        return await self.count(
            AccessClearance.case_id == case_id,
            AccessClearance.status.notin_([s.value for s in SETTLED_ACCESS_STATUSES]),
        )


class ExitInterviewRepository(BaseRepository[ExitInterview]):
    model = ExitInterview

    async def for_case(self, case_id: uuid.UUID) -> ExitInterview | None:
        return await self.get_by(case_id=case_id)

    async def submitted_with_employees(
        self, *, offset: int, limit: int, visible_ids: Collection[uuid.UUID] | None = None
    ) -> tuple[Sequence[tuple[ExitInterview, Employee]], int]:
        stmt = _visible(
            select(ExitInterview, Employee)
            .join(Employee, Employee.id == ExitInterview.employee_id)
            .where(ExitInterview.deleted_at.is_(None), ExitInterview.submitted_at.is_not(None)),
            ExitInterview.employee_id,
            visible_ids,
        )
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            await self.session.execute(
                stmt.order_by(ExitInterview.submitted_at.desc()).offset(offset).limit(limit)
            )
        ).all()
        return [(row[0], row[1]) for row in rows], total


class ExitDocumentRepository(BaseRepository[ExitDocument]):
    model = ExitDocument

    async def for_case(self, case_id: uuid.UUID) -> Sequence[ExitDocument]:
        return await self.list(
            ExitDocument.case_id == case_id, limit=50, order_by="created_at", descending=False
        )

    async def for_employee(self, employee_id: uuid.UUID) -> Sequence[ExitDocument]:
        return await self.list(
            ExitDocument.employee_id == employee_id, limit=50, order_by="created_at", descending=False
        )


class SettlementRepository(BaseRepository[FinalSettlementTracking]):
    model = FinalSettlementTracking

    async def for_case(self, case_id: uuid.UUID) -> FinalSettlementTracking | None:
        return await self.get_by(case_id=case_id)


class OffboardingAnalyticsRepository:
    """Cross-table counters for the three dashboards.

    A plain object rather than a ``BaseRepository`` because none of these
    queries are about one model: they answer "how many separations are waiting
    on HR", which spans resignations, cases and their clearance rows.
    """

    def __init__(self, session: Any) -> None:
        self.session = session

    async def active_resignation_count(self, *, visible_ids: Collection[uuid.UUID] | None = None) -> int:
        stmt = _visible(
            select(func.count())
            .select_from(Resignation)
            .where(
                Resignation.deleted_at.is_(None),
                Resignation.status.notin_([s.value for s in TERMINAL_RESIGNATION_STATUSES]),
            ),
            Resignation.employee_id,
            visible_ids,
        )
        return int(await self.session.scalar(stmt) or 0)

    async def serving_notice_count(self, *, visible_ids: Collection[uuid.UUID] | None = None) -> int:
        stmt = _visible(
            select(func.count())
            .select_from(Resignation)
            .where(
                Resignation.deleted_at.is_(None),
                Resignation.status.in_([s.value for s in ACTIVE_OFFBOARDING_STATUSES]),
            ),
            Resignation.employee_id,
            visible_ids,
        )
        return int(await self.session.scalar(stmt) or 0)

    async def exit_interviews_pending(self, *, visible_ids: Collection[uuid.UUID] | None = None) -> int:
        """Open cases with no submitted interview behind them."""
        submitted = select(ExitInterview.case_id).where(
            ExitInterview.deleted_at.is_(None), ExitInterview.submitted_at.is_not(None)
        )
        stmt = _visible(
            select(func.count())
            .select_from(OffboardingCase)
            .where(
                OffboardingCase.deleted_at.is_(None),
                OffboardingCase.status == OffboardingCaseStatus.IN_PROGRESS.value,
                OffboardingCase.id.notin_(submitted),
            ),
            OffboardingCase.employee_id,
            visible_ids,
        )
        return int(await self.session.scalar(stmt) or 0)

    async def exit_documents_pending(self, *, visible_ids: Collection[uuid.UUID] | None = None) -> int:
        released = select(ExitDocument.case_id).where(
            ExitDocument.deleted_at.is_(None), ExitDocument.released.is_(True)
        )
        stmt = _visible(
            select(func.count())
            .select_from(OffboardingCase)
            .where(
                OffboardingCase.deleted_at.is_(None),
                OffboardingCase.status == OffboardingCaseStatus.IN_PROGRESS.value,
                OffboardingCase.id.notin_(released),
            ),
            OffboardingCase.employee_id,
            visible_ids,
        )
        return int(await self.session.scalar(stmt) or 0)

    async def settlement_pending(self, *, visible_ids: Collection[uuid.UUID] | None = None) -> int:
        stmt = _visible(
            select(func.count())
            .select_from(FinalSettlementTracking)
            .join(OffboardingCase, OffboardingCase.id == FinalSettlementTracking.case_id)
            .where(
                FinalSettlementTracking.deleted_at.is_(None),
                FinalSettlementTracking.status != "completed",
                OffboardingCase.status != OffboardingCaseStatus.CANCELLED.value,
            ),
            OffboardingCase.employee_id,
            visible_ids,
        )
        return int(await self.session.scalar(stmt) or 0)
