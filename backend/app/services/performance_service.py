"""Performance management business logic.

Three rules shape this module.

**A submitted review is never rewritten.** Self, manager and final reviews are
written once. Re-submitting is refused rather than silently overwriting, because
a rating someone disputes six months later has to still say what it said.

**Weightage is a budget.** An employee's live goals may total at most 100% of
their cycle. The check runs against everything *else* they hold, so editing a
goal's weight never trips over its own current value.

**Progress is appended, never edited.** The goal carries a denormalised
percentage for list screens; the trail of who reported what, and when, is the
record.
"""

from __future__ import annotations

import csv
import io as _io
import uuid
from collections.abc import Collection, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, cast

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.audit_log import AuditAction
from app.models.employee import Employee
from app.models.enums import (
    LOW_PERFORMANCE_RATING,
    TOTAL_WEIGHTAGE,
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
from app.models.requisition import Notification
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.performance_repository import (
    FeedbackRepository,
    FinalReviewRepository,
    GoalProgressRepository,
    GoalRatingRepository,
    GoalRepository,
    ManagerReviewRepository,
    PerformanceAnalyticsRepository,
    PerformanceCycleRepository,
    PerformanceHistoryRepository,
    RecognitionRepository,
    SelfReviewRepository,
)
from app.repositories.requisition_repository import NotificationRepository
from app.schemas.performance import (
    CycleListParams,
    FeedbackCreate,
    FeedbackListParams,
    FinalReviewSubmit,
    GoalCreate,
    GoalListParams,
    GoalProgressCreate,
    GoalRatingInput,
    GoalUpdate,
    ManagerReviewSubmit,
    PerformanceCycleCreate,
    PerformanceCycleUpdate,
    RecognitionCreate,
    RecognitionListParams,
    SelfReviewSubmit,
)
from app.services.audit_service import AuditService
from app.utils.datetime import utc_now

logger = get_logger("services.performance")

#: How many names the dashboard's leader boards carry.
LEADERBOARD_SIZE = 5

#: Cycle states that accept new goals and reviews.
_OPEN_CYCLE_STATUSES: frozenset[str] = frozenset({PerformanceCycleStatus.ACTIVE.value})


class PerformanceService:
    """Cycles, goals, reviews, recognition and feedback."""

    def __init__(
        self,
        cycles: PerformanceCycleRepository,
        goals: GoalRepository,
        progress: GoalProgressRepository,
        ratings: GoalRatingRepository,
        self_reviews: SelfReviewRepository,
        manager_reviews: ManagerReviewRepository,
        final_reviews: FinalReviewRepository,
        recognitions: RecognitionRepository,
        feedback: FeedbackRepository,
        history: PerformanceHistoryRepository,
        analytics: PerformanceAnalyticsRepository,
        employees: EmployeeRepository,
        audit: AuditService,
        notifications: NotificationRepository | None = None,
    ) -> None:
        self.cycles = cycles
        self.goals = goals
        self.progress = progress
        self.ratings = ratings
        self.self_reviews = self_reviews
        self.manager_reviews = manager_reviews
        self.final_reviews = final_reviews
        self.recognitions = recognitions
        self.feedback = feedback
        self.history = history
        self.analytics = analytics
        self.employees = employees
        self.audit = audit
        # In-app notifications. Optional so the service can be unit-tested with
        # plain fakes, and never allowed to fail a write -- see ``_notify``.
        self.notifications = notifications

    # ------------------------------------------------------------------
    # Cycles
    # ------------------------------------------------------------------
    async def list_cycles(self, params: CycleListParams) -> tuple[Sequence[PerformanceCycle], int]:
        return await self.cycles.search(params)

    async def get_cycle(self, cycle_id: uuid.UUID) -> PerformanceCycle:
        cycle = await self.cycles.get(cycle_id, include_deleted=True)
        if cycle is None:
            raise NotFoundError("Performance cycle")
        return cycle

    async def create_cycle(
        self, payload: PerformanceCycleCreate, *, actor_id: uuid.UUID | None = None
    ) -> PerformanceCycle:
        await self._assert_cycle_name_free(payload.name, payload.financial_year)

        cycle = await self.cycles.add(
            PerformanceCycle(**payload.model_dump(), status=PerformanceCycleStatus.DRAFT.value),
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.PERFORMANCE_CYCLE_CREATED,
            actor_id=actor_id,
            entity_type="performance_cycle",
            entity_id=cycle.id,
            description=f"Created performance cycle {cycle.name} ({cycle.financial_year})",
        )
        return cycle

    async def update_cycle(
        self, cycle_id: uuid.UUID, payload: PerformanceCycleUpdate, *, actor_id: uuid.UUID | None = None
    ) -> PerformanceCycle:
        cycle = await self.get_cycle(cycle_id)
        self._assert_cycle_editable(cycle)

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return cycle

        name = changes.get("name", cycle.name)
        year = changes.get("financial_year", cycle.financial_year)
        if (name, year) != (cycle.name, cycle.financial_year):
            await self._assert_cycle_name_free(name, year)

        # The stored dates and the submitted ones together have to remain
        # ordered, which a schema validating one request cannot see.
        self._assert_cycle_dates(
            {field: changes.get(field, getattr(cycle, field)) for field in _CYCLE_DATE_FIELDS}
        )

        await self.cycles.update(cycle, changes, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.PERFORMANCE_CYCLE_UPDATED,
            actor_id=actor_id,
            entity_type="performance_cycle",
            entity_id=cycle.id,
            description=f"Updated performance cycle {cycle.name}",
            context={"fields": sorted(changes)},
        )
        return cycle

    async def set_cycle_status(
        self, cycle_id: uuid.UUID, status: PerformanceCycleStatus, *, actor_id: uuid.UUID | None = None
    ) -> PerformanceCycle:
        """Move a cycle through draft → active → closed → archived."""
        cycle = await self.get_cycle(cycle_id)
        if cycle.status == status.value:
            raise ConflictError(f"This cycle is already {status.value}.", error_code="already_in_status")
        if status is PerformanceCycleStatus.CLOSED:
            await self._assert_ready_to_close(cycle)

        changes: dict[str, Any] = {"status": status.value}
        if status is PerformanceCycleStatus.CLOSED:
            changes["closed_at"] = utc_now()

        await self.cycles.update(cycle, changes, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.PERFORMANCE_CYCLE_UPDATED,
            actor_id=actor_id,
            entity_type="performance_cycle",
            entity_id=cycle.id,
            description=f"Performance cycle {cycle.name} moved to {status.value}",
            context={"status": status.value},
        )
        return cycle

    async def _assert_ready_to_close(self, cycle: PerformanceCycle) -> None:
        """A cycle closes only once every employee with goals has a final rating.

        Closing early would freeze people out of a rating they are entitled to,
        and the cycle cannot be reopened without rewriting history.
        """
        outstanding = await self.analytics.employees_awaiting(cycle.id, ReviewStage.MANAGER)
        finalised = await self.final_reviews.count(FinalReview.cycle_id == cycle.id)
        assigned, _ = await self.analytics.cycle_goal_totals(cycle.id)

        if assigned and not finalised:
            raise ConflictError(
                "No final ratings have been recorded for this cycle yet.",
                error_code="no_final_ratings",
            )
        if outstanding:
            raise ConflictError(
                f"{outstanding} employee(s) are still awaiting a manager review.",
                error_code="reviews_outstanding",
            )

    async def _assert_cycle_name_free(self, name: str, financial_year: str) -> None:
        clash = await self.cycles.find(
            PerformanceCycle.name == name,
            PerformanceCycle.financial_year == financial_year,
            include_deleted=True,
        )
        if clash is not None:
            raise ConflictError(
                f'A cycle called "{name}" already exists for {financial_year}.',
                error_code="duplicate_cycle",
            )

    @staticmethod
    def _assert_cycle_editable(cycle: PerformanceCycle) -> None:
        if cycle.deleted_at is not None:
            raise ConflictError("This cycle is archived.", error_code="record_archived")
        if cycle.status in {PerformanceCycleStatus.CLOSED.value, PerformanceCycleStatus.ARCHIVED.value}:
            raise ConflictError(
                "A closed cycle cannot be changed. Performance records are kept as they were.",
                error_code="cycle_closed",
            )

    @staticmethod
    def _assert_cycle_dates(values: dict[str, date]) -> None:
        if values["end_date"] <= values["start_date"]:
            raise ValidationError("The cycle must end after it starts.", error_code="invalid_dates")
        ordered = [
            values["self_review_deadline"],
            values["manager_review_deadline"],
            values["hr_review_deadline"],
        ]
        if ordered != sorted(ordered):
            raise ValidationError(
                "Review deadlines must run self, then manager, then HR.", error_code="invalid_dates"
            )

    # ------------------------------------------------------------------
    # Goals
    # ------------------------------------------------------------------
    async def list_goals(self, params: GoalListParams) -> tuple[Sequence[Goal], int]:
        return await self.goals.search(params)

    async def get_goal(self, goal_id: uuid.UUID) -> Goal:
        goal = await self.goals.detailed(goal_id)
        if goal is None:
            raise NotFoundError("Goal")
        return goal

    async def assign_goal(self, payload: GoalCreate, *, actor_id: uuid.UUID | None = None) -> Goal:
        cycle = await self.get_cycle(payload.cycle_id)
        self._assert_cycle_open(cycle)
        await self._assert_employee_exists(payload.employee_id)

        await self._assert_title_available(payload.cycle_id, payload.employee_id, payload.title)
        await self._assert_weightage_fits(payload.cycle_id, payload.employee_id, payload.weightage)
        self._assert_within_cycle(cycle, payload.start_date, payload.due_date)

        assigner = await self._employee_for_user(actor_id)
        goal = await self.goals.add(
            Goal(
                **payload.model_dump(),
                assigned_by_id=assigner.id if assigner else None,
                status=GoalStatus.NOT_STARTED.value,
                completion_percentage=0,
            ),
            actor_id=actor_id,
        )

        await self._record_history(
            goal.employee_id,
            cycle.id,
            "goal_assigned",
            f"Goal assigned: {goal.title} ({goal.weightage}%)",
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.GOAL_ASSIGNED,
            actor_id=actor_id,
            entity_type="goal",
            entity_id=goal.id,
            description=f"Assigned goal {goal.title!r}",
            context={"cycle": cycle.name, "weightage": str(goal.weightage)},
        )
        await self._notify(
            goal.employee_id,
            "Goal assigned",
            f'"{goal.title}" was assigned to you for {cycle.name}.',
            f"/performance/goals/{goal.id}",
            "goal_assigned",
        )
        # Reload before returning. A freshly constructed entity has no
        # ``progress_updates`` or ``ratings`` loaded, and serialising it would
        # trigger a lazy SELECT -- which under asyncio raises MissingGreenlet
        # rather than loading anything.
        return await self.get_goal(goal.id)

    async def update_goal(
        self, goal_id: uuid.UUID, payload: GoalUpdate, *, actor_id: uuid.UUID | None = None
    ) -> Goal:
        """Amend a goal. Refused once the manager review is in.

        A goal that has been rated is part of the evidence for that rating;
        re-weighting or re-scoping it afterwards would change what the score
        meant.
        """
        goal = await self.get_goal(goal_id)
        cycle = await self.get_cycle(goal.cycle_id)
        self._assert_cycle_open(cycle)
        await self._assert_not_reviewed(goal)

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return goal

        if "title" in changes:
            await self._assert_title_available(
                goal.cycle_id, goal.employee_id, changes["title"], exclude_id=goal.id
            )
        if "weightage" in changes:
            await self._assert_weightage_fits(
                goal.cycle_id, goal.employee_id, changes["weightage"], exclude_id=goal.id
            )

        start = changes.get("start_date", goal.start_date)
        due = changes.get("due_date", goal.due_date)
        if due < start:
            raise ValidationError("A goal cannot be due before it starts.", error_code="invalid_dates")
        self._assert_within_cycle(cycle, start, due)

        await self.goals.update(goal, changes, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.GOAL_UPDATED,
            actor_id=actor_id,
            entity_type="goal",
            entity_id=goal.id,
            description=f"Updated goal {goal.title!r}",
            context={"fields": sorted(changes)},
        )
        await self._notify(
            goal.employee_id,
            "Goal updated",
            f'"{goal.title}" was changed.',
            f"/performance/goals/{goal.id}",
            "goal_updated",
        )
        return await self.get_goal(goal.id)

    async def record_progress(
        self, goal_id: uuid.UUID, payload: GoalProgressCreate, *, actor_id: uuid.UUID | None = None
    ) -> Goal:
        """Append a progress report and roll the goal's headline figure forward."""
        goal = await self.get_goal(goal_id)
        cycle = await self.get_cycle(goal.cycle_id)
        self._assert_cycle_open(cycle)

        if goal.status == GoalStatus.CANCELLED.value:
            raise ConflictError(
                "This goal was cancelled; progress can no longer be recorded.",
                error_code="goal_cancelled",
            )

        await self.progress.add(GoalProgress(goal_id=goal.id, **payload.model_dump()), actor_id=actor_id)
        await self.goals.update(
            goal,
            {"completion_percentage": payload.completion_percentage, "status": payload.status.value},
            actor_id=actor_id,
        )

        if payload.status is GoalStatus.COMPLETED:
            await self._record_history(
                goal.employee_id,
                goal.cycle_id,
                "goal_completed",
                f"Goal completed: {goal.title}",
                actor_id=actor_id,
            )

        await self.audit.record_success(
            AuditAction.GOAL_PROGRESS_RECORDED,
            actor_id=actor_id,
            entity_type="goal",
            entity_id=goal.id,
            description=f"Progress on {goal.title!r}: {payload.completion_percentage}%",
            context={"status": payload.status.value},
        )
        return await self.get_goal(goal.id)

    async def _assert_not_reviewed(self, goal: Goal) -> None:
        existing = await self.ratings.for_goals([goal.id], ReviewStage.MANAGER)
        if existing:
            raise ConflictError(
                "This goal has already been rated by the manager and can no longer be changed.",
                error_code="goal_reviewed",
            )

    async def _assert_title_available(
        self, cycle_id: uuid.UUID, employee_id: uuid.UUID, title: str, *, exclude_id: uuid.UUID | None = None
    ) -> None:
        clash = await self.goals.find_duplicate_title(cycle_id, employee_id, title, exclude_id=exclude_id)
        if clash is not None:
            raise ConflictError(
                f'This employee already has a goal called "{clash.title}" in this cycle.',
                error_code="duplicate_goal",
            )

    async def _assert_weightage_fits(
        self,
        cycle_id: uuid.UUID,
        employee_id: uuid.UUID,
        weightage: Decimal,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        committed = await self.goals.committed_weightage(cycle_id, employee_id, exclude_id=exclude_id)
        if committed + weightage > TOTAL_WEIGHTAGE:
            remaining = TOTAL_WEIGHTAGE - committed
            raise ConflictError(
                f"That would take this employee past {TOTAL_WEIGHTAGE}% for the cycle. {remaining}% remains.",
                error_code="weightage_exceeded",
            )

    @staticmethod
    def _assert_within_cycle(cycle: PerformanceCycle, start: date, due: date) -> None:
        if start < cycle.start_date or due > cycle.end_date:
            raise ValidationError(
                f"Goal dates must fall inside the cycle ({cycle.start_date} to {cycle.end_date}).",
                error_code="outside_cycle",
            )

    @staticmethod
    def _assert_cycle_open(cycle: PerformanceCycle) -> None:
        if cycle.status not in _OPEN_CYCLE_STATUSES:
            raise ConflictError(
                f"This cycle is {cycle.status}. Only an active cycle accepts goals and reviews.",
                error_code="cycle_not_active",
            )

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------
    async def submit_self_review(
        self,
        cycle_id: uuid.UUID,
        employee_id: uuid.UUID,
        payload: SelfReviewSubmit,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> SelfReview:
        cycle = await self.get_cycle(cycle_id)
        self._assert_cycle_open(cycle)
        await self._assert_employee_exists(employee_id)

        existing = await self.self_reviews.for_employee(cycle_id, employee_id)
        if existing is not None and existing.status == ReviewStatus.SUBMITTED.value:
            raise ConflictError(
                "This self review has already been submitted.", error_code="already_submitted"
            )

        goals = await self.goals.for_employee_in_cycle(cycle_id, employee_id)
        if not goals:
            raise ConflictError("There are no goals to review in this cycle.", error_code="no_goals")
        self._assert_ratings_cover_goals(payload.goal_ratings, goals)

        review = existing or SelfReview(cycle_id=cycle_id, employee_id=employee_id)
        values = payload.model_dump(exclude={"goal_ratings"})
        values |= {"status": ReviewStatus.SUBMITTED.value, "submitted_at": utc_now()}

        if existing is None:
            for field, value in values.items():
                setattr(review, field, value)
            await self.self_reviews.add(review, actor_id=actor_id)
        else:
            await self.self_reviews.update(review, values, actor_id=actor_id)

        await self._store_ratings(payload.goal_ratings, ReviewStage.SELF, actor_id=actor_id)
        await self._record_history(
            employee_id,
            cycle_id,
            "self_review_submitted",
            f"Self review submitted for {cycle.name}",
            rating=payload.overall_rating,
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.SELF_REVIEW_SUBMITTED,
            actor_id=actor_id,
            entity_type="self_review",
            entity_id=review.id,
            description=f"Self review submitted for {cycle.name}",
        )

        manager_id = await self._reporting_manager_id(employee_id)
        if manager_id:
            await self._notify(
                manager_id,
                "Manager review due",
                f"A self review is ready for your assessment in {cycle.name}.",
                f"/performance/reviews/{cycle_id}/{employee_id}",
                "manager_review_due",
            )
        return review

    async def submit_manager_review(
        self,
        cycle_id: uuid.UUID,
        employee_id: uuid.UUID,
        payload: ManagerReviewSubmit,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> ManagerReview:
        cycle = await self.get_cycle(cycle_id)
        self._assert_cycle_open(cycle)
        await self._assert_employee_exists(employee_id)

        existing = await self.manager_reviews.for_employee(cycle_id, employee_id)
        if existing is not None and existing.status == ReviewStatus.SUBMITTED.value:
            raise ConflictError(
                "This manager review has already been submitted.", error_code="already_submitted"
            )

        # The manager assesses what the employee said about themselves, so the
        # self review has to be in first. Reversing the order would make the
        # self assessment a formality written after the fact.
        self_review = await self.self_reviews.for_employee(cycle_id, employee_id)
        if self_review is None or self_review.status != ReviewStatus.SUBMITTED.value:
            raise ConflictError(
                "The employee has not submitted their self review yet.",
                error_code="self_review_missing",
            )

        goals = await self.goals.for_employee_in_cycle(cycle_id, employee_id)
        self._assert_ratings_cover_goals(payload.goal_ratings, goals)

        reviewer = await self._employee_for_user(actor_id)
        if reviewer is None:
            raise ConflictError(
                "Only an employee record can submit a manager review.", error_code="reviewer_unknown"
            )

        review = existing or ManagerReview(
            cycle_id=cycle_id, employee_id=employee_id, reviewer_id=reviewer.id
        )
        values = payload.model_dump(exclude={"goal_ratings"})
        values["recommendation"] = payload.recommendation.value
        values |= {
            "reviewer_id": reviewer.id,
            "status": ReviewStatus.SUBMITTED.value,
            "submitted_at": utc_now(),
        }

        if existing is None:
            for field, value in values.items():
                setattr(review, field, value)
            await self.manager_reviews.add(review, actor_id=actor_id)
        else:
            await self.manager_reviews.update(review, values, actor_id=actor_id)

        await self._store_ratings(payload.goal_ratings, ReviewStage.MANAGER, actor_id=actor_id)
        await self._record_history(
            employee_id,
            cycle_id,
            "manager_review_submitted",
            f"Manager review submitted for {cycle.name}",
            detail=payload.recommendation.value,
            rating=payload.overall_rating,
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.MANAGER_REVIEW_SUBMITTED,
            actor_id=actor_id,
            entity_type="manager_review",
            entity_id=review.id,
            description=f"Manager review submitted for {cycle.name}",
            context={"recommendation": payload.recommendation.value},
        )
        return review

    async def finalise(
        self,
        cycle_id: uuid.UUID,
        employee_id: uuid.UUID,
        payload: FinalReviewSubmit,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> FinalReview:
        """HR's rating of record. Written once."""
        cycle = await self.get_cycle(cycle_id)
        self._assert_cycle_open(cycle)

        if await self.final_reviews.for_employee(cycle_id, employee_id) is not None:
            raise ConflictError(
                "This performance review has already been finalised.", error_code="already_finalised"
            )

        manager_review = await self.manager_reviews.for_employee(cycle_id, employee_id)
        if manager_review is None or manager_review.status != ReviewStatus.SUBMITTED.value:
            raise ConflictError(
                "The manager review has not been submitted yet.", error_code="manager_review_missing"
            )
        self_review = await self.self_reviews.for_employee(cycle_id, employee_id)

        finaliser = await self._employee_for_user(actor_id)
        review = FinalReview(
            cycle_id=cycle_id,
            employee_id=employee_id,
            finalised_by_id=finaliser.id if finaliser else None,
            final_rating=payload.final_rating,
            comments=payload.comments,
            # Copied, not joined: a goal cancelled next month must not change
            # what this rating was based on.
            self_rating=self_review.overall_rating if self_review else None,
            manager_rating=manager_review.overall_rating,
            goal_completion_percentage=await self.goals.weighted_completion(cycle_id, employee_id),
            finalised_at=utc_now(),
        )
        await self.final_reviews.add(review, actor_id=actor_id)

        await self._record_history(
            employee_id,
            cycle_id,
            "performance_finalised",
            f"Performance finalised for {cycle.name}: {payload.final_rating}/5",
            rating=payload.final_rating,
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.PERFORMANCE_FINALISED,
            actor_id=actor_id,
            entity_type="final_review",
            entity_id=review.id,
            description=f"Finalised {cycle.name} at {payload.final_rating}/5",
        )
        await self._notify(
            employee_id,
            "Performance finalised",
            f"Your {cycle.name} review has been finalised.",
            "/performance/history",
            "performance_finalised",
        )
        return review

    @staticmethod
    def _assert_ratings_cover_goals(ratings: Sequence[GoalRatingInput], goals: Sequence[Goal]) -> None:
        """Every live goal must be rated, and nothing else may be.

        A partial scorecard produces an overall figure that cannot be compared
        with anyone else's, which is the whole point of a rating scale.
        """
        expected = {goal.id for goal in goals if goal.status != GoalStatus.CANCELLED.value}
        supplied = {entry.goal_id for entry in ratings}

        missing = expected - supplied
        if missing:
            raise ValidationError(
                f"{len(missing)} goal(s) still need a rating.", error_code="incomplete_ratings"
            )
        unknown = supplied - expected
        if unknown:
            raise ValidationError(
                "A rating was supplied for a goal that is not in this cycle.",
                error_code="unknown_goal",
            )

    async def _store_ratings(
        self, entries: Sequence[GoalRatingInput], stage: ReviewStage, *, actor_id: uuid.UUID | None
    ) -> None:
        rater = await self._employee_for_user(actor_id)
        existing = {
            rating.goal_id: rating
            for rating in await self.ratings.for_goals([e.goal_id for e in entries], stage)
        }
        for entry in entries:
            if entry.goal_id in existing:
                await self.ratings.update(
                    existing[entry.goal_id],
                    {"rating": entry.rating, "comments": entry.comments},
                    actor_id=actor_id,
                )
                continue
            await self.ratings.add(
                GoalRating(
                    goal_id=entry.goal_id,
                    stage=stage.value,
                    rating=entry.rating,
                    comments=entry.comments,
                    rated_by_id=rater.id if rater else None,
                ),
                actor_id=actor_id,
            )

    # ------------------------------------------------------------------
    # Recognition and feedback
    # ------------------------------------------------------------------
    async def add_recognition(
        self, payload: RecognitionCreate, *, actor_id: uuid.UUID | None = None
    ) -> Recognition:
        await self._assert_employee_exists(payload.employee_id)
        awarder = await self._employee_for_user(actor_id)

        recognition = await self.recognitions.add(
            Recognition(
                **payload.model_dump(exclude={"recognition_type"}),
                recognition_type=payload.recognition_type.value,
                awarded_by_id=awarder.id if awarder else None,
            ),
            actor_id=actor_id,
        )
        await self._record_history(
            payload.employee_id,
            None,
            "recognition_received",
            f"Recognised: {payload.title}",
            detail=payload.recognition_type.value,
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.RECOGNITION_ADDED,
            actor_id=actor_id,
            entity_type="recognition",
            entity_id=recognition.id,
            description=f"Recognition {payload.recognition_type.value} for {payload.title!r}",
        )
        await self._notify(
            payload.employee_id,
            "Recognition received",
            payload.title,
            "/performance/recognition",
            "recognition_received",
        )
        return recognition

    async def list_recognitions(self, params: RecognitionListParams) -> tuple[Sequence[Recognition], int]:
        return await self.recognitions.search(params)

    async def add_feedback(
        self, payload: FeedbackCreate, *, actor_id: uuid.UUID | None = None
    ) -> ContinuousFeedback:
        await self._assert_employee_exists(payload.to_employee_id)
        author = await self._employee_for_user(actor_id)
        if author is None:
            raise ConflictError("Only an employee record can leave feedback.", error_code="author_unknown")
        if author.id == payload.to_employee_id:
            raise ValidationError(
                "Feedback is for someone else; use your self review to record your own view.",
                error_code="self_feedback",
            )

        feedback = await self.feedback.add(
            ContinuousFeedback(
                from_employee_id=author.id,
                to_employee_id=payload.to_employee_id,
                title=payload.title,
                description=payload.description,
                category=payload.category.value,
                visibility=payload.visibility.value,
                feedback_date=payload.feedback_date,
            ),
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.FEEDBACK_ADDED,
            actor_id=actor_id,
            entity_type="continuous_feedback",
            entity_id=feedback.id,
            description=f"Feedback ({payload.category.value}) recorded",
        )
        await self._notify(
            payload.to_employee_id,
            "Feedback received",
            payload.title,
            "/performance/feedback",
            "feedback_received",
        )
        return feedback

    async def list_feedback(self, params: FeedbackListParams) -> tuple[Sequence[ContinuousFeedback], int]:
        return await self.feedback.search(params)

    async def history_for(self, employee_id: uuid.UUID) -> Sequence[PerformanceHistory]:
        await self._assert_employee_exists(employee_id)
        return await self.history.for_employee(employee_id)

    # ------------------------------------------------------------------
    # Composite reads
    # ------------------------------------------------------------------
    async def employee_performance(self, cycle_id: uuid.UUID, employee_id: uuid.UUID) -> dict[str, Any]:
        """Everything the review screens need, in one round trip."""
        cycle = await self.get_cycle(cycle_id)
        employee = await self.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("Employee")

        goals = await self.goals.for_employee_in_cycle(cycle_id, employee_id)
        return {
            "employee": employee,
            "cycle": cycle,
            "goals": goals,
            "total_weightage": await self.goals.committed_weightage(cycle_id, employee_id),
            "goal_completion_percentage": await self.goals.weighted_completion(cycle_id, employee_id),
            "self_review": await self.self_reviews.for_employee(cycle_id, employee_id),
            "manager_review": await self.manager_reviews.for_employee(cycle_id, employee_id),
            "final_review": await self.final_reviews.for_employee(cycle_id, employee_id),
        }

    async def for_employees(
        self, employee_ids: Collection[uuid.UUID], *, cycle_id: uuid.UUID | None = None
    ) -> list[dict[str, Any]]:
        """One row per employee: goals, progress and review state in one cycle.

        The set-shaped read behind a team performance screen. It lives here
        rather than in the module that renders it for the reason every rule in
        this file lives here: what counts as a live goal, what weighted
        completion means, and which review comes before which are this module's
        answers, and a caller assembling them from repositories would be
        deciding them a second time.

        ``cycle_id`` defaults to the first active cycle. With no active cycle
        every row still comes back -- with nothing in it -- because a team
        screen that renders no people between cycles looks broken rather than
        empty.

        ``weighted_completion`` is asked per employee rather than derived from
        the goals already loaded here. It is a query per team member, which for
        a reporting line is a handful, and it is the only definition of the
        figure -- recomputing it locally would be a second one waiting to
        disagree.
        """
        ids = list(employee_ids)
        active = await self.cycles.active()
        cycle = await self.get_cycle(cycle_id) if cycle_id else (active[0] if active else None)

        if cycle is None or not ids:
            return [self._empty_performance(employee_id) for employee_id in ids]

        goals = await self.goals.for_employees_in_cycle(cycle.id, ids)
        by_employee: dict[uuid.UUID, list[Goal]] = {employee_id: [] for employee_id in ids}
        for goal in goals:
            by_employee[goal.employee_id].append(goal)

        self_reviews = {row.employee_id: row for row in await self.self_reviews.for_employees(cycle.id, ids)}
        manager_reviews = {
            row.employee_id: row for row in await self.manager_reviews.for_employees(cycle.id, ids)
        }
        final_reviews = {
            row.employee_id: row for row in await self.final_reviews.for_employees(cycle.id, ids)
        }

        rows: list[dict[str, Any]] = []
        for employee_id in ids:
            held = by_employee[employee_id]
            self_review = self_reviews.get(employee_id)
            manager_review = manager_reviews.get(employee_id)
            final_review = final_reviews.get(employee_id)

            submitted = ReviewStatus.SUBMITTED.value
            rows.append(
                {
                    "employee_id": employee_id,
                    "cycle_id": cycle.id,
                    "cycle_name": cycle.name,
                    "goals": len(held),
                    "goals_completed": sum(1 for goal in held if goal.status == GoalStatus.COMPLETED.value),
                    "goal_progress": await self.goals.weighted_completion(cycle.id, employee_id),
                    "self_review_status": self_review.status if self_review else None,
                    "manager_review_status": manager_review.status if manager_review else None,
                    # The final rating is the rating of record once it exists;
                    # before that the manager's is the most authoritative figure
                    # anybody has, and showing nothing would hide a review that
                    # has already been written.
                    "current_rating": (
                        final_review.final_rating
                        if final_review
                        else (manager_review.overall_rating if manager_review else None)
                    ),
                    "review_due": bool(
                        held
                        and self_review is not None
                        and self_review.status == submitted
                        and (manager_review is None or manager_review.status != submitted)
                    ),
                }
            )
        return rows

    @staticmethod
    def _empty_performance(employee_id: uuid.UUID) -> dict[str, Any]:
        return {
            "employee_id": employee_id,
            "cycle_id": None,
            "cycle_name": None,
            "goals": 0,
            "goals_completed": 0,
            "goal_progress": 0,
            "self_review_status": None,
            "manager_review_status": None,
            "current_rating": None,
            "review_due": False,
        }

    async def dashboard(self, cycle_id: uuid.UUID | None = None) -> dict[str, Any]:
        active = await self.cycles.active()
        scope = cycle_id or (active[0].id if active else None)

        assigned, completed = await self.analytics.cycle_goal_totals(scope)
        self_pending = await self.analytics.employees_awaiting(scope, ReviewStage.SELF) if scope else 0
        manager_pending = await self.analytics.employees_awaiting(scope, ReviewStage.MANAGER) if scope else 0

        top = await self.final_reviews.ranked(cycle_id=scope, ascending=False, limit=LEADERBOARD_SIZE)
        low = await self.final_reviews.ranked(cycle_id=scope, ascending=True, limit=LEADERBOARD_SIZE)

        return {
            "active_cycles": len(active),
            "goals_assigned": assigned,
            "goals_completed": completed,
            "goal_completion_percentage": int(completed * 100 / assigned) if assigned else 0,
            "self_reviews_pending": self_pending,
            "manager_reviews_pending": manager_pending,
            "reviews_pending": self_pending + manager_pending,
            "final_ratings": await self.final_reviews.count(
                *([FinalReview.cycle_id == scope] if scope else [])
            ),
            "top_performers": [self._rated(row) for row in top],
            # Only the genuinely low ones: the bottom of a strong cycle is not an alert.
            "low_performance_alerts": [
                self._rated(row) for row in low if row[1].final_rating <= LOW_PERFORMANCE_RATING
            ],
            "by_goal_status": await self._counts(Goal.status, scope),
            "by_priority": await self._counts(Goal.priority, scope),
        }

    async def analytics_overview(self, cycle_id: uuid.UUID | None = None) -> dict[str, Any]:
        return {
            "goal_completion": await self._counts(Goal.status, cycle_id),
            "business_unit_performance": await self.analytics.completion_by_business_unit(cycle_id),
            "manager_performance": await self.manager_reviews.average_by_reviewer(cycle_id),
            "rating_distribution": await self.final_reviews.rating_distribution(cycle_id),
            "goal_distribution": await self._counts(Goal.category, cycle_id),
            "performance_trend": await self.final_reviews.trend(),
        }

    async def _counts(self, column: Any, cycle_id: uuid.UUID | None) -> list[tuple[str, int]]:
        criteria = [Goal.cycle_id == cycle_id] if cycle_id else []
        return await self.goals.count_by(column, *criteria)

    @staticmethod
    def _rated(row: Any) -> dict[str, Any]:
        employee, review, cycle = row
        return {"employee": employee, "rating": review.final_rating, "cycle_name": cycle.name}

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    async def export(self, report: str, fmt: str, cycle_id: uuid.UUID | None = None) -> tuple[bytes, str]:
        """Render one report in the requested format.

        Sensitive detail is deliberately absent: these reports travel by email
        and land in shared drives, so they carry ratings and completion figures
        but never review commentary.
        """
        rows = await self._report_rows(report, cycle_id)

        if fmt == "csv":
            out = _io.StringIO()
            csv.writer(out).writerows(rows)
            # utf-8-sig so Excel opens accented names correctly.
            return out.getvalue().encode("utf-8-sig"), "text/csv"

        if fmt == "pdf":
            return self._pdf(report, rows), "application/pdf"

        book = Workbook()
        sheet = book.active
        sheet.title = report[:31]
        for row in rows:
            sheet.append(list(row))
        buffer = _io.BytesIO()
        book.save(buffer)
        return buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    async def _report_rows(self, report: str, cycle_id: uuid.UUID | None) -> list[list[Any]]:
        if report == "goal-completion":
            pairs = await self.analytics.goals_with_employees(cycle_id)
            return [
                ["Employee", "Employee ID", "Goal", "Weightage %", "Status", "Completion %", "Due"],
                *[
                    [
                        employee.full_name,
                        employee.employee_code,
                        goal.title,
                        str(goal.weightage),
                        goal.status.replace("_", " "),
                        goal.completion_percentage,
                        goal.due_date.isoformat(),
                    ]
                    for goal, employee in pairs
                ],
            ]

        if report == "employee-ratings":
            ranked = await self.final_reviews.ranked(cycle_id=cycle_id, ascending=False, limit=1000)
            return [
                ["Employee", "Employee ID", "Cycle", "Final rating", "Self", "Manager", "Goals %"],
                *[
                    [
                        employee.full_name,
                        employee.employee_code,
                        cycle.name,
                        review.final_rating,
                        review.self_rating,
                        review.manager_rating,
                        review.goal_completion_percentage,
                    ]
                    for employee, review, cycle in ranked
                ],
            ]

        if report == "recognitions":
            rows, _ = await self.recognitions.search(cast(RecognitionListParams, _AllRecognitions()))
            return [
                ["Employee ID", "Type", "Title", "Awarded on"],
                *[
                    [
                        str(item.employee_id),
                        item.recognition_type.replace("_", " "),
                        item.title,
                        item.awarded_on.isoformat(),
                    ]
                    for item in rows
                ],
            ]

        # performance-summary
        overview = await self.dashboard(cycle_id)
        return [
            ["Measure", "Value"],
            ["Active cycles", overview["active_cycles"]],
            ["Goals assigned", overview["goals_assigned"]],
            ["Goals completed", overview["goals_completed"]],
            ["Goal completion %", overview["goal_completion_percentage"]],
            ["Self reviews pending", overview["self_reviews_pending"]],
            ["Manager reviews pending", overview["manager_reviews_pending"]],
            ["Final ratings recorded", overview["final_ratings"]],
        ]

    @staticmethod
    def _pdf(report: str, rows: list[list[Any]]) -> bytes:
        """A plain tabular PDF. Landscape, because these tables are wide."""
        buffer = _io.BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=landscape(A4), title=report)
        table = Table([[str(cell) if cell is not None else "" for cell in row] for row in rows])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f5d5a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c3c3b8")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        document.build([Paragraph(report.replace("-", " ").title()), Spacer(1, 12), table])
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _assert_employee_exists(self, employee_id: uuid.UUID) -> None:
        if await self.employees.get(employee_id) is None:
            raise ConflictError("No such employee.", error_code="invalid_employee")

    async def _employee_for_user(self, user_id: uuid.UUID | None) -> Employee | None:
        """The employee record behind the signed-in account, if there is one.

        An administrator with no employment record can still act; the resulting
        rows simply record no author rather than refusing the write.
        """
        if user_id is None:
            return None
        from app.models.employee import Employee

        return await self.employees.find(Employee.user_id == user_id)

    async def _reporting_manager_id(self, employee_id: uuid.UUID) -> uuid.UUID | None:
        employee = await self.employees.get(employee_id)
        return employee.reporting_manager_id if employee else None

    async def _record_history(
        self,
        employee_id: uuid.UUID,
        cycle_id: uuid.UUID | None,
        event_type: str,
        summary: str,
        *,
        detail: str | None = None,
        rating: int | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        await self.history.add(
            PerformanceHistory(
                employee_id=employee_id,
                cycle_id=cycle_id,
                event_type=event_type,
                summary=summary,
                detail=detail,
                rating=rating,
            ),
            actor_id=actor_id,
        )

    async def _notify(self, employee_id: uuid.UUID, title: str, message: str, link: str, kind: str) -> None:
        """Best-effort in-app notification.

        Notifications address a *user*, so an employee with no linked account
        simply gets none -- there is nowhere to deliver it. Nothing here is
        allowed to fail the surrounding write: a notice is a courtesy, and
        losing a submitted review because one could not be written would be far
        worse than a missed bell icon.
        """
        if self.notifications is None:
            return

        employee = await self.employees.get(employee_id)
        if employee is None or employee.user_id is None:
            return

        await self.notifications.add(
            Notification(
                user_id=employee.user_id,
                title=title,
                message=message,
                link=link,
                notification_type=kind,
            )
        )


class _AllRecognitions:
    """Params for an unfiltered recognition export.

    The repository takes one params shape; a report wanting everything says so
    with this rather than the repository growing a second query.
    """

    employee_id = None
    recognition_type = None
    offset = 0
    page_size = 10_000


#: The cycle date fields validated together on update.
_CYCLE_DATE_FIELDS = (
    "start_date",
    "end_date",
    "self_review_deadline",
    "manager_review_deadline",
    "hr_review_deadline",
)
