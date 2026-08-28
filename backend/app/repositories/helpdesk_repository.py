"""Persistence for the helpdesk and for announcements.

Query shapes only. Which tickets a caller may reach is decided by
:mod:`app.services.scope_service` and passed in as ``visible_ids``.

Scoping a ticket is by *requester*, which has one consequence worth stating: an
agent working the HR queue needs ``employees:view_all`` to see the tickets
addressed to them, because a request from somebody outside their reporting line
is, by the platform's own rule, outside their scope. That is why the seeded HR
roles hold ``employees:view_all`` and a Manager does not — a manager sees their
team's requests and nobody else's, which is exactly what a manager should see.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.models.announcement import Announcement, AnnouncementAcknowledgement
from app.models.employee import Employee
from app.models.enums import (
    OPEN_TICKET_STATUSES,
    AnnouncementAudience,
    AnnouncementStatus,
    RecordStatus,
    TicketStatus,
)
from app.models.helpdesk import HelpdeskCategory, HelpdeskComment, HelpdeskHistory, HelpdeskTicket
from app.repositories.base import BaseRepository
from app.schemas.announcement import AnnouncementListParams
from app.schemas.helpdesk import TicketListParams
from app.utils.datetime import utc_now


def _scoped(stmt: Select[Any], visible_ids: Collection[uuid.UUID] | None) -> Select[Any]:
    """Narrow to tickets raised by (or for) employees the caller may see.

    ``None`` means unrestricted; an empty collection means the caller reaches
    nobody and gets an empty page rather than everybody's requests.
    """
    if visible_ids is None:
        return stmt
    if not visible_ids:
        return stmt.where(false())
    return stmt.where(
        or_(
            HelpdeskTicket.raised_by_id.in_(visible_ids),
            HelpdeskTicket.raised_for_id.in_(visible_ids),
        )
    )


class TicketCategoryRepository(BaseRepository[HelpdeskCategory]):
    model = HelpdeskCategory

    async def active(self) -> Sequence[HelpdeskCategory]:
        return await self.list(
            HelpdeskCategory.status == RecordStatus.ACTIVE.value,
            limit=200,
            order_by="name",
            descending=False,
        )

    async def all_categories(self) -> Sequence[HelpdeskCategory]:
        return await self.list(limit=200, order_by="name", descending=False)

    async def by_code(self, code: str) -> HelpdeskCategory | None:
        return await self.get_by(code=code.strip().upper())


class TicketRepository(BaseRepository[HelpdeskTicket]):
    model = HelpdeskTicket

    def _detailed(self) -> Select[tuple[HelpdeskTicket]]:
        return self._base_select().options(
            joinedload(HelpdeskTicket.category), selectinload(HelpdeskTicket.comments)
        )

    async def get_detailed(self, ticket_id: uuid.UUID) -> HelpdeskTicket | None:
        stmt = (
            self._detailed().where(HelpdeskTicket.id == ticket_id).execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def for_employee(self, employee_id: uuid.UUID) -> Sequence[HelpdeskTicket]:
        stmt = (
            self._base_select()
            .options(joinedload(HelpdeskTicket.category))
            .where(
                or_(
                    HelpdeskTicket.raised_by_id == employee_id,
                    HelpdeskTicket.raised_for_id == employee_id,
                )
            )
            .order_by(HelpdeskTicket.created_at.desc())
            .limit(200)
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def search(
        self, params: TicketListParams, *, visible_ids: Collection[uuid.UUID] | None = None
    ) -> tuple[Sequence[HelpdeskTicket], int]:
        stmt = _scoped(self._base_select().options(joinedload(HelpdeskTicket.category)), visible_ids)
        criteria: list[Any] = []

        if params.status is not None:
            criteria.append(HelpdeskTicket.status == params.status.value)
        if params.priority is not None:
            criteria.append(HelpdeskTicket.priority == params.priority.value)
        if params.queue is not None:
            criteria.append(HelpdeskTicket.queue == params.queue.value)
        if params.category_id is not None:
            criteria.append(HelpdeskTicket.category_id == params.category_id)
        if params.assigned_to_id is not None:
            criteria.append(HelpdeskTicket.assigned_to_id == params.assigned_to_id)
        if params.unassigned:
            criteria.append(HelpdeskTicket.assigned_to_id.is_(None))
        if params.open_only:
            criteria.append(HelpdeskTicket.status.in_([s.value for s in OPEN_TICKET_STATUSES]))
        if params.overdue:
            criteria.append(HelpdeskTicket.due_at.is_not(None))
            criteria.append(HelpdeskTicket.due_at < utc_now())
            criteria.append(HelpdeskTicket.first_responded_at.is_(None))
        if params.employee_id is not None:
            criteria.append(
                or_(
                    HelpdeskTicket.raised_by_id == params.employee_id,
                    HelpdeskTicket.raised_for_id == params.employee_id,
                )
            )
        if params.search:
            term = f"%{params.search.strip()}%"
            criteria.append(or_(HelpdeskTicket.ticket_code.ilike(term), HelpdeskTicket.subject.ilike(term)))

        stmt = stmt.where(*criteria)
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(HelpdeskTicket.created_at.desc())
                    .offset(params.offset)
                    .limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def counts_by(
        self, column: Any, *, visible_ids: Collection[uuid.UUID] | None = None, open_only: bool = True
    ) -> list[tuple[str, int]]:
        stmt = _scoped(
            select(column, func.count())
            .select_from(HelpdeskTicket)
            .where(HelpdeskTicket.deleted_at.is_(None)),
            visible_ids,
        )
        if open_only:
            stmt = stmt.where(HelpdeskTicket.status.in_([s.value for s in OPEN_TICKET_STATUSES]))
        rows = (await self.session.execute(stmt.group_by(column).order_by(func.count().desc()))).all()
        return [(str(label), count) for label, count in rows]

    async def counts_by_category(
        self, *, visible_ids: Collection[uuid.UUID] | None = None
    ) -> list[tuple[str, int]]:
        """Open tickets per category name -- needs a join, unlike the others."""
        stmt = _scoped(
            select(HelpdeskCategory.name, func.count(HelpdeskTicket.id))
            .select_from(HelpdeskTicket)
            .join(HelpdeskCategory, HelpdeskCategory.id == HelpdeskTicket.category_id)
            .where(
                HelpdeskTicket.deleted_at.is_(None),
                HelpdeskTicket.status.in_([s.value for s in OPEN_TICKET_STATUSES]),
            ),
            visible_ids,
        )
        rows = (
            await self.session.execute(
                stmt.group_by(HelpdeskCategory.name).order_by(func.count(HelpdeskTicket.id).desc())
            )
        ).all()
        return [(name, count) for name, count in rows]

    async def count_where(self, *criteria: Any, visible_ids: Collection[uuid.UUID] | None = None) -> int:
        stmt = _scoped(
            select(func.count()).select_from(HelpdeskTicket).where(HelpdeskTicket.deleted_at.is_(None)),
            visible_ids,
        )
        return int(await self.session.scalar(stmt.where(*criteria)) or 0)

    async def dashboard_counts(self, *, visible_ids: Collection[uuid.UUID] | None = None) -> dict[str, int]:
        now = utc_now()
        open_values = [s.value for s in OPEN_TICKET_STATUSES]
        return {
            "open": await self.count_where(HelpdeskTicket.status.in_(open_values), visible_ids=visible_ids),
            "unassigned": await self.count_where(
                HelpdeskTicket.status.in_(open_values),
                HelpdeskTicket.assigned_to_id.is_(None),
                visible_ids=visible_ids,
            ),
            "overdue": await self.count_where(
                HelpdeskTicket.status.in_(open_values),
                HelpdeskTicket.due_at.is_not(None),
                HelpdeskTicket.due_at < now,
                HelpdeskTicket.first_responded_at.is_(None),
                visible_ids=visible_ids,
            ),
            "waiting": await self.count_where(
                HelpdeskTicket.status == TicketStatus.WAITING_ON_EMPLOYEE.value,
                visible_ids=visible_ids,
            ),
            "resolved_today": await self.count_where(
                HelpdeskTicket.resolved_at.is_not(None),
                HelpdeskTicket.resolved_at >= now - timedelta(days=1),
                visible_ids=visible_ids,
            ),
            "reopened": await self.count_where(HelpdeskTicket.reopen_count > 0, visible_ids=visible_ids),
        }


class TicketCommentRepository(BaseRepository[HelpdeskComment]):
    model = HelpdeskComment

    async def public_for_ticket(self, ticket_id: uuid.UUID) -> Sequence[HelpdeskComment]:
        """Only what the requester may read. Internal notes never come back."""
        return await self.list(
            HelpdeskComment.ticket_id == ticket_id,
            HelpdeskComment.internal.is_(False),
            limit=500,
            order_by="created_at",
            descending=False,
        )


class TicketHistoryRepository(BaseRepository[HelpdeskHistory]):
    model = HelpdeskHistory

    async def for_ticket(self, ticket_id: uuid.UUID) -> Sequence[HelpdeskHistory]:
        return await self.list(
            HelpdeskHistory.ticket_id == ticket_id, limit=200, order_by="created_at", descending=True
        )


class AnnouncementRepository(BaseRepository[Announcement]):
    model = Announcement

    def _detailed(self) -> Select[tuple[Announcement]]:
        return self._base_select().options(selectinload(Announcement.acknowledgements))

    async def get_detailed(self, announcement_id: uuid.UUID) -> Announcement | None:
        stmt = (
            self._detailed()
            .where(Announcement.id == announcement_id)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def search(self, params: AnnouncementListParams) -> tuple[Sequence[Announcement], int]:
        stmt = self._base_select()
        criteria: list[Any] = []
        if params.status is not None:
            criteria.append(Announcement.status == params.status.value)
        if params.priority is not None:
            criteria.append(Announcement.priority == params.priority.value)
        if params.audience is not None:
            criteria.append(Announcement.audience == params.audience.value)
        if params.search:
            criteria.append(Announcement.title.ilike(f"%{params.search.strip()}%"))

        stmt = stmt.where(*criteria)
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(Announcement.created_at.desc())
                    .offset(params.offset)
                    .limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def live_for_employee(self, employee: Employee, *, limit: int = 50) -> Sequence[Announcement]:
        """Published, in-window announcements addressed to this person.

        The audience test is done in SQL rather than by fetching everything and
        filtering: an organization with three years of notices should not read
        all of them to render one dashboard card.
        """
        now = utc_now()
        targets = [
            employee.business_unit_id,
            employee.team_id,
            employee.work_location_id,
        ]
        audience_match = [Announcement.audience == AnnouncementAudience.ALL.value]
        for audience, target in (
            (AnnouncementAudience.BUSINESS_UNIT, employee.business_unit_id),
            (AnnouncementAudience.TEAM, employee.team_id),
            (AnnouncementAudience.LOCATION, employee.work_location_id),
        ):
            if target is not None:
                audience_match.append(
                    (Announcement.audience == audience.value)
                    & Announcement.target_ids.contains([str(target)])
                )
        del targets

        stmt = (
            self._detailed()
            .where(
                Announcement.status == AnnouncementStatus.PUBLISHED.value,
                Announcement.published_at.is_not(None),
                Announcement.published_at <= now,
                or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
                or_(*audience_match),
            )
            # Pinned first, then most recent. `desc()` on a boolean puts true
            # first in PostgreSQL, which is what "pinned to the top" means.
            .order_by(Announcement.pinned.desc(), Announcement.published_at.desc())
            .limit(limit)
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def due_to_publish(self) -> Sequence[Announcement]:
        """Scheduled announcements whose time has come.

        Read on demand rather than by a background job: the platform has no
        scheduler, and a notice that goes live the first time somebody looks at
        the dashboard after its publish time is close enough for an internal
        noticeboard. A real scheduler would call this too.
        """
        return await self.list(
            Announcement.status == AnnouncementStatus.SCHEDULED.value,
            Announcement.publish_at.is_not(None),
            Announcement.publish_at <= utc_now(),
            limit=100,
        )

    async def audience_size(self, announcement: Announcement) -> int:
        """How many employed people this notice reaches."""
        from app.models.enums import EMPLOYED_STATUSES

        stmt = (
            select(func.count())
            .select_from(Employee)
            .where(
                Employee.deleted_at.is_(None),
                Employee.employment_status.in_([s.value for s in EMPLOYED_STATUSES]),
            )
        )
        audience = AnnouncementAudience(announcement.audience)
        targets = [uuid.UUID(str(t)) for t in (announcement.target_ids or [])]
        if audience is AnnouncementAudience.BUSINESS_UNIT:
            stmt = stmt.where(Employee.business_unit_id.in_(targets))
        elif audience is AnnouncementAudience.TEAM:
            stmt = stmt.where(Employee.team_id.in_(targets))
        elif audience is AnnouncementAudience.LOCATION:
            stmt = stmt.where(Employee.work_location_id.in_(targets))
        return int(await self.session.scalar(stmt) or 0)

    async def recipient_user_ids(self, announcement: Announcement) -> Sequence[uuid.UUID]:
        """Login accounts to notify when this is published."""
        from app.models.enums import EMPLOYED_STATUSES

        stmt = select(Employee.user_id).where(
            Employee.deleted_at.is_(None),
            Employee.user_id.is_not(None),
            Employee.employment_status.in_([s.value for s in EMPLOYED_STATUSES]),
        )
        audience = AnnouncementAudience(announcement.audience)
        targets = [uuid.UUID(str(t)) for t in (announcement.target_ids or [])]
        if audience is AnnouncementAudience.BUSINESS_UNIT:
            stmt = stmt.where(Employee.business_unit_id.in_(targets))
        elif audience is AnnouncementAudience.TEAM:
            stmt = stmt.where(Employee.team_id.in_(targets))
        elif audience is AnnouncementAudience.LOCATION:
            stmt = stmt.where(Employee.work_location_id.in_(targets))
        return [row for row in (await self.session.execute(stmt)).scalars().all() if row]


class AcknowledgementRepository(BaseRepository[AnnouncementAcknowledgement]):
    model = AnnouncementAcknowledgement

    async def for_employee(
        self, employee_id: uuid.UUID, announcement_ids: Collection[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Which of these the employee has already confirmed, in one query."""
        if not announcement_ids:
            return set()
        rows = (
            await self.session.execute(
                select(AnnouncementAcknowledgement.announcement_id).where(
                    AnnouncementAcknowledgement.employee_id == employee_id,
                    AnnouncementAcknowledgement.announcement_id.in_(announcement_ids),
                    AnnouncementAcknowledgement.deleted_at.is_(None),
                )
            )
        ).scalars()
        return set(rows.all())

    async def count_for(self, announcement_id: uuid.UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(AnnouncementAcknowledgement)
                .where(
                    AnnouncementAcknowledgement.announcement_id == announcement_id,
                    AnnouncementAcknowledgement.deleted_at.is_(None),
                )
            )
            or 0
        )

    async def existing(
        self, announcement_id: uuid.UUID, employee_id: uuid.UUID
    ) -> AnnouncementAcknowledgement | None:
        return await self.get_by(announcement_id=announcement_id, employee_id=employee_id)

    async def with_names(self, announcement_id: uuid.UUID) -> Sequence[tuple[uuid.UUID, str, datetime]]:
        rows = (
            await self.session.execute(
                select(
                    AnnouncementAcknowledgement.employee_id,
                    Employee.first_name,
                    Employee.last_name,
                    AnnouncementAcknowledgement.acknowledged_at,
                )
                .join(Employee, Employee.id == AnnouncementAcknowledgement.employee_id)
                .where(
                    AnnouncementAcknowledgement.announcement_id == announcement_id,
                    AnnouncementAcknowledgement.deleted_at.is_(None),
                )
                .order_by(AnnouncementAcknowledgement.acknowledged_at.desc())
            )
        ).all()
        return [(row[0], f"{row[1]} {row[2]}", row[3]) for row in rows]
