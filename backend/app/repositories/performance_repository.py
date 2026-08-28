"""Persistence for the Performance Management module.

Query shapes only. Every rule about *whether* something may be written -- a
cycle that is still open, weightage that fits inside 100% -- belongs to the
service; this layer answers questions and stores rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.employee import Employee
from app.models.enums import (
    LIVE_GOAL_STATUSES,
    GoalStatus,
    PerformanceCycleStatus,
    ReviewStage,
    ReviewStatus,
)
from app.models.performance import (
    ContinuousFeedback,
    FinalReview,
    Goal,
    GoalProgress,
    GoalRating,
    ManagerReview,
    PerformanceCycle,
    PerformanceHistory,
    Recognition,
    SelfReview,
)
from app.repositories.base import BaseRepository
from app.schemas.common import PaginationParams
from app.schemas.performance import (
    CycleListParams,
    FeedbackListParams,
    GoalListParams,
    RecognitionListParams,
)


def _employee_name() -> ColumnElement[str]:
    """A person's display name, composed in SQL.

    ``Employee.full_name`` is a plain Python property, so it works on a loaded
    object but cannot appear in a GROUP BY or ORDER BY. Anything aggregating by
    name has to build it in the database instead.
    """
    return func.trim(Employee.first_name + " " + Employee.last_name)


class PerformanceCycleRepository(BaseRepository[PerformanceCycle]):
    model = PerformanceCycle

    async def search(self, params: CycleListParams) -> tuple[Sequence[PerformanceCycle], int]:
        stmt = self._base_select()
        if params.status is not None:
            stmt = stmt.where(PerformanceCycle.status == params.status.value)
        if params.financial_year:
            stmt = stmt.where(PerformanceCycle.financial_year == params.financial_year)
        if params.search:
            term = f"%{params.search}%"
            stmt = stmt.where(or_(PerformanceCycle.name.ilike(term), PerformanceCycle.cycle_code.ilike(term)))
        return await self._page(stmt, params, PerformanceCycle.start_date.desc())

    async def active(self) -> Sequence[PerformanceCycle]:
        stmt = self._base_select().where(PerformanceCycle.status == PerformanceCycleStatus.ACTIVE.value)
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def count_by_status(self, status: PerformanceCycleStatus) -> int:
        return await self.count(PerformanceCycle.status == status.value)

    async def _page(
        self, stmt: Select[Any], params: PaginationParams, order: Any
    ) -> tuple[Sequence[Any], int]:
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (await self.session.execute(stmt.order_by(order).offset(params.offset).limit(params.page_size)))
            .scalars()
            .unique()
            .all()
        )
        return rows, total


class GoalRepository(BaseRepository[Goal]):
    model = Goal

    def _detailed(self) -> Select[tuple[Goal]]:
        return self._base_select().options(selectinload(Goal.progress_updates), selectinload(Goal.ratings))

    async def detailed(self, goal_id: uuid.UUID) -> Goal | None:
        stmt = self._detailed().where(Goal.id == goal_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def search(self, params: GoalListParams) -> tuple[Sequence[Goal], int]:
        stmt = self._detailed()
        for column, value in (
            (Goal.cycle_id, params.cycle_id),
            (Goal.employee_id, params.employee_id),
            (Goal.project_id, params.project_id),
        ):
            if value is not None:
                stmt = stmt.where(column == value)
        if params.status is not None:
            stmt = stmt.where(Goal.status == params.status.value)
        if params.priority is not None:
            stmt = stmt.where(Goal.priority == params.priority.value)
        if params.search:
            term = f"%{params.search}%"
            stmt = stmt.where(or_(Goal.title.ilike(term), Goal.goal_code.ilike(term)))

        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(Goal.due_date.asc()).offset(params.offset).limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def for_employee_in_cycle(self, cycle_id: uuid.UUID, employee_id: uuid.UUID) -> Sequence[Goal]:
        stmt = (
            self._detailed()
            .where(Goal.cycle_id == cycle_id, Goal.employee_id == employee_id)
            .order_by(Goal.due_date.asc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def for_employees_in_cycle(
        self, cycle_id: uuid.UUID, employee_ids: Collection[uuid.UUID]
    ) -> Sequence[Goal]:
        """Every goal a group of people hold in one cycle.

        The set-shaped sibling of :meth:`for_employee_in_cycle`. A team screen
        needs all of them at once, and calling the singular version per employee
        turns one query into as many queries as the manager has reports.
        """
        if not employee_ids:
            return []
        stmt = (
            self._detailed()
            .where(Goal.cycle_id == cycle_id, Goal.employee_id.in_(employee_ids))
            .order_by(Goal.due_date.asc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def committed_weightage(
        self, cycle_id: uuid.UUID, employee_id: uuid.UUID, *, exclude_id: uuid.UUID | None = None
    ) -> Decimal:
        """Weightage already committed, excluding cancelled goals.

        ``exclude_id`` lets an edit ask "what would the total be without this
        goal's current value", which is the only way to re-weight a goal without
        tripping the 100% ceiling on its own existing share.
        """
        criteria: list[ColumnElement[bool]] = [
            Goal.cycle_id == cycle_id,
            Goal.employee_id == employee_id,
            Goal.deleted_at.is_(None),
            Goal.status.in_([status.value for status in LIVE_GOAL_STATUSES]),
        ]
        if exclude_id is not None:
            criteria.append(Goal.id != exclude_id)

        total = await self.session.scalar(select(func.coalesce(func.sum(Goal.weightage), 0)).where(*criteria))
        return Decimal(total or 0)

    async def find_duplicate_title(
        self, cycle_id: uuid.UUID, employee_id: uuid.UUID, title: str, *, exclude_id: uuid.UUID | None = None
    ) -> Goal | None:
        """Same person, same cycle, same title -- almost always a double submit."""
        criteria: list[ColumnElement[bool]] = [
            Goal.cycle_id == cycle_id,
            Goal.employee_id == employee_id,
            func.lower(Goal.title) == title.strip().lower(),
            Goal.deleted_at.is_(None),
        ]
        if exclude_id is not None:
            criteria.append(Goal.id != exclude_id)
        return (await self.session.execute(select(Goal).where(*criteria))).scalars().first()

    async def weighted_completion(self, cycle_id: uuid.UUID, employee_id: uuid.UUID) -> int:
        """Completion across the cycle, weighted by each goal's share.

        A goal worth 60% that is half done contributes more than a 5% goal that
        is finished, which a plain average would get backwards.
        """
        rows = (
            (
                await self.session.execute(
                    select(Goal.weightage, Goal.completion_percentage).where(
                        Goal.cycle_id == cycle_id,
                        Goal.employee_id == employee_id,
                        Goal.deleted_at.is_(None),
                        Goal.status.in_([status.value for status in LIVE_GOAL_STATUSES]),
                    )
                )
            )
            .tuples()
            .all()
        )
        weight_total = sum(Decimal(weight) for weight, _ in rows)
        if not weight_total:
            return 0
        achieved = sum(Decimal(weight) * Decimal(done) for weight, done in rows)
        return int(achieved / weight_total)

    async def count_by(self, column: Any, *criteria: ColumnElement[bool]) -> list[tuple[str, int]]:
        stmt = (
            select(column, func.count(Goal.id))
            .where(Goal.deleted_at.is_(None), *criteria)
            .group_by(column)
            .order_by(func.count(Goal.id).desc())
        )
        return [(row[0], int(row[1])) for row in (await self.session.execute(stmt)).all()]

    async def count_live(self, *criteria: ColumnElement[bool]) -> int:
        return await self.count(*criteria)


class GoalProgressRepository(BaseRepository[GoalProgress]):
    """Append-only. There is deliberately no update or delete."""

    model = GoalProgress

    async def for_goal(self, goal_id: uuid.UUID) -> Sequence[GoalProgress]:
        stmt = (
            select(GoalProgress)
            .where(GoalProgress.goal_id == goal_id)
            .order_by(GoalProgress.created_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()


class GoalRatingRepository(BaseRepository[GoalRating]):
    model = GoalRating

    async def for_goals(self, goal_ids: Sequence[uuid.UUID], stage: ReviewStage) -> Sequence[GoalRating]:
        if not goal_ids:
            return []
        stmt = select(GoalRating).where(GoalRating.goal_id.in_(goal_ids), GoalRating.stage == stage.value)
        return (await self.session.execute(stmt)).scalars().unique().all()


class SelfReviewRepository(BaseRepository[SelfReview]):
    model = SelfReview

    async def for_employee(self, cycle_id: uuid.UUID, employee_id: uuid.UUID) -> SelfReview | None:
        return await self.get_by(cycle_id=cycle_id, employee_id=employee_id)

    async def for_employees(
        self, cycle_id: uuid.UUID, employee_ids: Collection[uuid.UUID]
    ) -> Sequence[SelfReview]:
        """One cycle's self reviews for a group of people, in one query."""
        if not employee_ids:
            return []
        stmt = self._base_select().where(
            SelfReview.cycle_id == cycle_id, SelfReview.employee_id.in_(employee_ids)
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def count_submitted(self, cycle_id: uuid.UUID) -> int:
        return await self.count(
            SelfReview.cycle_id == cycle_id, SelfReview.status == ReviewStatus.SUBMITTED.value
        )


class ManagerReviewRepository(BaseRepository[ManagerReview]):
    model = ManagerReview

    async def for_employee(self, cycle_id: uuid.UUID, employee_id: uuid.UUID) -> ManagerReview | None:
        return await self.get_by(cycle_id=cycle_id, employee_id=employee_id)

    async def for_employees(
        self, cycle_id: uuid.UUID, employee_ids: Collection[uuid.UUID]
    ) -> Sequence[ManagerReview]:
        """One cycle's manager reviews for a group of people, in one query."""
        if not employee_ids:
            return []
        stmt = self._base_select().where(
            ManagerReview.cycle_id == cycle_id, ManagerReview.employee_id.in_(employee_ids)
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def count_submitted(self, cycle_id: uuid.UUID) -> int:
        return await self.count(
            ManagerReview.cycle_id == cycle_id, ManagerReview.status == ReviewStatus.SUBMITTED.value
        )

    async def average_by_reviewer(self, cycle_id: uuid.UUID | None) -> list[tuple[str, int]]:
        # One expression object, used in both the projection and the grouping.
        # Two structurally-equal instances render as two expressions and
        # PostgreSQL then rejects the ungrouped columns underneath them.
        reviewer_name = _employee_name()
        stmt = (
            select(reviewer_name, func.avg(ManagerReview.overall_rating))
            .join(Employee, Employee.id == ManagerReview.reviewer_id)
            .where(
                ManagerReview.deleted_at.is_(None),
                ManagerReview.overall_rating.is_not(None),
            )
            .group_by(reviewer_name)
        )
        if cycle_id is not None:
            stmt = stmt.where(ManagerReview.cycle_id == cycle_id)
        return [(row[0], int(row[1] or 0)) for row in (await self.session.execute(stmt)).all()]


class FinalReviewRepository(BaseRepository[FinalReview]):
    model = FinalReview

    async def for_employee(self, cycle_id: uuid.UUID, employee_id: uuid.UUID) -> FinalReview | None:
        return await self.get_by(cycle_id=cycle_id, employee_id=employee_id)

    async def for_employees(
        self, cycle_id: uuid.UUID, employee_ids: Collection[uuid.UUID]
    ) -> Sequence[FinalReview]:
        """One cycle's final ratings for a group of people, in one query."""
        if not employee_ids:
            return []
        stmt = self._base_select().where(
            FinalReview.cycle_id == cycle_id, FinalReview.employee_id.in_(employee_ids)
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def ranked(
        self, *, cycle_id: uuid.UUID | None, ascending: bool, limit: int
    ) -> list[tuple[Employee, FinalReview, PerformanceCycle]]:
        """Top or bottom performers, resolved to names in one query."""
        stmt = (
            select(Employee, FinalReview, PerformanceCycle)
            .join(Employee, Employee.id == FinalReview.employee_id)
            .join(PerformanceCycle, PerformanceCycle.id == FinalReview.cycle_id)
            .where(FinalReview.deleted_at.is_(None))
        )
        if cycle_id is not None:
            stmt = stmt.where(FinalReview.cycle_id == cycle_id)
        order = FinalReview.final_rating.asc() if ascending else FinalReview.final_rating.desc()
        stmt = stmt.order_by(order, Employee.first_name, Employee.last_name).limit(limit)
        return [tuple(row) for row in (await self.session.execute(stmt)).all()]

    async def rating_distribution(self, cycle_id: uuid.UUID | None) -> list[tuple[str, int]]:
        stmt = (
            select(FinalReview.final_rating, func.count(FinalReview.id))
            .where(FinalReview.deleted_at.is_(None))
            .group_by(FinalReview.final_rating)
            .order_by(FinalReview.final_rating)
        )
        if cycle_id is not None:
            stmt = stmt.where(FinalReview.cycle_id == cycle_id)
        return [(str(row[0]), int(row[1])) for row in (await self.session.execute(stmt)).all()]

    async def trend(self) -> list[tuple[str, int]]:
        """Average final rating per cycle, oldest first — the performance trend."""
        stmt = (
            select(PerformanceCycle.name, func.avg(FinalReview.final_rating))
            .join(PerformanceCycle, PerformanceCycle.id == FinalReview.cycle_id)
            .where(FinalReview.deleted_at.is_(None))
            .group_by(PerformanceCycle.name, PerformanceCycle.start_date)
            .order_by(PerformanceCycle.start_date)
        )
        return [(row[0], int(row[1] or 0)) for row in (await self.session.execute(stmt)).all()]


class RecognitionRepository(BaseRepository[Recognition]):
    model = Recognition

    async def search(self, params: RecognitionListParams) -> tuple[Sequence[Recognition], int]:
        stmt = self._base_select()
        if params.employee_id is not None:
            stmt = stmt.where(Recognition.employee_id == params.employee_id)
        if params.recognition_type is not None:
            stmt = stmt.where(Recognition.recognition_type == params.recognition_type.value)

        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(Recognition.awarded_on.desc()).offset(params.offset).limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def count_by_type(self) -> list[tuple[str, int]]:
        stmt = (
            select(Recognition.recognition_type, func.count(Recognition.id))
            .where(Recognition.deleted_at.is_(None))
            .group_by(Recognition.recognition_type)
        )
        return [(row[0], int(row[1])) for row in (await self.session.execute(stmt)).all()]


class FeedbackRepository(BaseRepository[ContinuousFeedback]):
    model = ContinuousFeedback

    async def search(self, params: FeedbackListParams) -> tuple[Sequence[ContinuousFeedback], int]:
        stmt = self._base_select()
        if params.employee_id is not None:
            # Either side of the exchange, so "my feedback" means given and received.
            stmt = stmt.where(
                or_(
                    ContinuousFeedback.to_employee_id == params.employee_id,
                    ContinuousFeedback.from_employee_id == params.employee_id,
                )
            )
        if params.category is not None:
            stmt = stmt.where(ContinuousFeedback.category == params.category.value)

        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(ContinuousFeedback.feedback_date.desc())
                    .offset(params.offset)
                    .limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total


class PerformanceHistoryRepository(BaseRepository[PerformanceHistory]):
    """Append-only, like the employment history it sits alongside."""

    model = PerformanceHistory

    async def for_employee(self, employee_id: uuid.UUID) -> Sequence[PerformanceHistory]:
        stmt = (
            select(PerformanceHistory)
            .where(PerformanceHistory.employee_id == employee_id)
            .order_by(PerformanceHistory.created_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()


class PerformanceAnalyticsRepository(BaseRepository[Goal]):
    """Cross-entity aggregates that do not belong to any single repository."""

    model = Goal

    async def completion_by_business_unit(self, cycle_id: uuid.UUID | None) -> list[tuple[str, int]]:
        from app.models.business_unit import BusinessUnit

        stmt = (
            select(BusinessUnit.name, func.avg(Goal.completion_percentage))
            .join(Employee, Employee.id == Goal.employee_id)
            .join(BusinessUnit, BusinessUnit.id == Employee.business_unit_id)
            .where(Goal.deleted_at.is_(None))
            .group_by(BusinessUnit.name)
            .order_by(BusinessUnit.name)
        )
        if cycle_id is not None:
            stmt = stmt.where(Goal.cycle_id == cycle_id)
        return [(row[0], int(row[1] or 0)) for row in (await self.session.execute(stmt)).all()]

    async def goals_with_employees(self, cycle_id: uuid.UUID | None) -> list[tuple[Goal, Employee]]:
        stmt = (
            select(Goal, Employee)
            .join(Employee, Employee.id == Goal.employee_id)
            .where(Goal.deleted_at.is_(None))
            .order_by(Employee.first_name, Employee.last_name, Goal.due_date)
        )
        if cycle_id is not None:
            stmt = stmt.where(Goal.cycle_id == cycle_id)
        return [tuple(row) for row in (await self.session.execute(stmt)).all()]

    async def employees_awaiting(self, cycle_id: uuid.UUID, stage: ReviewStage) -> int:
        """How many employees with goals have not yet had this stage submitted.

        Counted from *goals*, because an employee with no goals in the cycle has
        nothing to review and should not appear as outstanding work.
        """
        with_goals = (
            select(Goal.employee_id)
            .where(Goal.cycle_id == cycle_id, Goal.deleted_at.is_(None))
            .group_by(Goal.employee_id)
            .subquery()
        )
        review = SelfReview if stage is ReviewStage.SELF else ManagerReview
        submitted = (
            select(review.employee_id)
            .where(
                review.cycle_id == cycle_id,
                review.status == ReviewStatus.SUBMITTED.value,
                review.deleted_at.is_(None),
            )
            .subquery()
        )
        stmt = (
            select(func.count())
            .select_from(with_goals.outerjoin(submitted, submitted.c.employee_id == with_goals.c.employee_id))
            .where(submitted.c.employee_id.is_(None))
        )
        return int(await self.session.scalar(stmt) or 0)

    async def cycle_goal_totals(self, cycle_id: uuid.UUID | None) -> tuple[int, int]:
        """(assigned, completed) goal counts."""
        criteria: list[ColumnElement[bool]] = [Goal.deleted_at.is_(None)]
        if cycle_id is not None:
            criteria.append(Goal.cycle_id == cycle_id)
        assigned = int(await self.session.scalar(select(func.count(Goal.id)).where(*criteria)) or 0)
        completed = int(
            await self.session.scalar(
                select(func.count(Goal.id)).where(and_(*criteria, Goal.status == GoalStatus.COMPLETED.value))
            )
            or 0
        )
        return assigned, completed
