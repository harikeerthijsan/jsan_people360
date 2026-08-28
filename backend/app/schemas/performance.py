"""Performance management request and response schemas.

Validation that belongs to the *shape* of a request lives here; validation that
needs the database -- does this employee already have 100% of their weightage
committed, is this cycle still open -- belongs in the service, because a schema
cannot see other rows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    MAX_RATING,
    MIN_RATING,
    FeedbackCategory,
    FeedbackVisibility,
    GoalPriority,
    GoalStatus,
    PerformanceCycleStatus,
    PerformanceRecommendation,
    RecognitionType,
)
from app.schemas.common import PaginationParams

READ_CONFIG = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# Performance cycles
# ----------------------------------------------------------------------
class CycleDates(BaseModel):
    """The date rules shared by create and update.

    The three deadlines must fall in review order. A manager cannot sensibly
    review before the self-assessment is due, and HR cannot finalise before the
    manager has had their window.
    """

    @model_validator(mode="after")
    def _ordered(self) -> CycleDates:
        start, end = getattr(self, "start_date", None), getattr(self, "end_date", None)
        if start and end and end <= start:
            raise ValueError("The cycle must end after it starts")

        deadlines = [
            ("self_review_deadline", getattr(self, "self_review_deadline", None)),
            ("manager_review_deadline", getattr(self, "manager_review_deadline", None)),
            ("hr_review_deadline", getattr(self, "hr_review_deadline", None)),
        ]
        supplied = [(name, value) for name, value in deadlines if value is not None]
        for (_, earlier), (later_name, later) in pairwise(supplied):
            if later < earlier:
                raise ValueError(f"{later_name.replace('_', ' ')} cannot fall before the previous deadline")

        if start and supplied and supplied[0][1] < start:
            raise ValueError("Review deadlines cannot fall before the cycle starts")
        return self


class PerformanceCycleCreate(CycleDates):
    name: str = Field(min_length=2, max_length=150)
    financial_year: str = Field(min_length=4, max_length=20, examples=["2026-27"])
    start_date: date
    end_date: date
    self_review_deadline: date
    manager_review_deadline: date
    hr_review_deadline: date
    description: str | None = Field(None, max_length=2000)


class PerformanceCycleUpdate(CycleDates):
    name: str | None = Field(None, min_length=2, max_length=150)
    financial_year: str | None = Field(None, min_length=4, max_length=20)
    start_date: date | None = None
    end_date: date | None = None
    self_review_deadline: date | None = None
    manager_review_deadline: date | None = None
    hr_review_deadline: date | None = None
    description: str | None = Field(None, max_length=2000)


class PerformanceCycleRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    cycle_code: str
    name: str
    financial_year: str
    start_date: date
    end_date: date
    self_review_deadline: date
    manager_review_deadline: date
    hr_review_deadline: date
    description: str | None
    status: str
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


# ----------------------------------------------------------------------
# Goals
# ----------------------------------------------------------------------
class GoalCreate(BaseModel):
    cycle_id: uuid.UUID
    employee_id: uuid.UUID
    project_id: uuid.UUID | None = None
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=5000)
    category: str = Field(min_length=2, max_length=100)
    success_criteria: str = Field(min_length=3, max_length=5000)
    weightage: Decimal = Field(gt=0, le=100, decimal_places=2)
    start_date: date
    due_date: date
    priority: GoalPriority = GoalPriority.MEDIUM

    @model_validator(mode="after")
    def _dates(self) -> GoalCreate:
        if self.due_date < self.start_date:
            raise ValueError("A goal cannot be due before it starts")
        return self


class GoalUpdate(BaseModel):
    """Edits a manager may make before the review stages begin."""

    title: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = Field(None, min_length=3, max_length=5000)
    category: str | None = Field(None, min_length=2, max_length=100)
    success_criteria: str | None = Field(None, min_length=3, max_length=5000)
    project_id: uuid.UUID | None = None
    weightage: Decimal | None = Field(None, gt=0, le=100, decimal_places=2)
    start_date: date | None = None
    due_date: date | None = None
    priority: GoalPriority | None = None
    status: GoalStatus | None = None


class GoalProgressCreate(BaseModel):
    """One progress report. Append-only: there is no update or delete."""

    completion_percentage: int = Field(ge=0, le=100)
    status: GoalStatus
    comments: str | None = Field(None, max_length=2000)
    evidence_document_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _completion_matches_status(self) -> GoalProgressCreate:
        # A goal reported complete at 40% is a contradiction the reviewer would
        # have to unpick later, so it is refused at the point of entry.
        if self.status is GoalStatus.COMPLETED and self.completion_percentage != 100:
            raise ValueError("A completed goal must be at 100%")
        if self.status is GoalStatus.NOT_STARTED and self.completion_percentage != 0:
            raise ValueError("A goal that has not started must be at 0%")
        return self


class GoalProgressRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    goal_id: uuid.UUID
    completion_percentage: int
    status: str
    comments: str | None
    evidence_document_id: uuid.UUID | None
    created_at: datetime
    created_by: uuid.UUID | None


class GoalRatingRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    goal_id: uuid.UUID
    stage: str
    rating: int
    comments: str | None


class EmployeeRef(BaseModel):
    """Just enough of an employee to render a row without another request."""

    model_config = READ_CONFIG
    id: uuid.UUID
    employee_code: str
    full_name: str


class GoalRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    goal_code: str
    cycle_id: uuid.UUID
    employee_id: uuid.UUID
    project_id: uuid.UUID | None
    assigned_by_id: uuid.UUID | None
    title: str
    description: str
    category: str
    success_criteria: str
    weightage: Decimal
    start_date: date
    due_date: date
    priority: str
    status: str
    completion_percentage: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    progress_updates: list[GoalProgressRead] = []
    ratings: list[GoalRatingRead] = []


# ----------------------------------------------------------------------
# Reviews
# ----------------------------------------------------------------------
class GoalRatingInput(BaseModel):
    goal_id: uuid.UUID
    rating: int = Field(ge=MIN_RATING, le=MAX_RATING)
    comments: str | None = Field(None, max_length=2000)


class SelfReviewSubmit(BaseModel):
    """An employee's assessment. Submitting is final."""

    overall_rating: int = Field(ge=MIN_RATING, le=MAX_RATING)
    overall_comments: str = Field(min_length=3, max_length=5000)
    achievements: str | None = Field(None, max_length=5000)
    challenges: str | None = Field(None, max_length=5000)
    goal_ratings: list[GoalRatingInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_duplicate_goals(self) -> SelfReviewSubmit:
        seen = [entry.goal_id for entry in self.goal_ratings]
        if len(set(seen)) != len(seen):
            raise ValueError("Each goal may be rated only once")
        return self


class ManagerReviewSubmit(BaseModel):
    overall_rating: int = Field(ge=MIN_RATING, le=MAX_RATING)
    overall_feedback: str = Field(min_length=3, max_length=5000)
    strengths: str | None = Field(None, max_length=5000)
    improvement_areas: str | None = Field(None, max_length=5000)
    recommendation: PerformanceRecommendation = PerformanceRecommendation.NONE
    goal_ratings: list[GoalRatingInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_duplicate_goals(self) -> ManagerReviewSubmit:
        seen = [entry.goal_id for entry in self.goal_ratings]
        if len(set(seen)) != len(seen):
            raise ValueError("Each goal may be rated only once")
        return self


class FinalReviewSubmit(BaseModel):
    final_rating: int = Field(ge=MIN_RATING, le=MAX_RATING)
    comments: str | None = Field(None, max_length=5000)


class SelfReviewRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    cycle_id: uuid.UUID
    employee_id: uuid.UUID
    overall_rating: int | None
    overall_comments: str | None
    achievements: str | None
    challenges: str | None
    status: str
    submitted_at: datetime | None


class ManagerReviewRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    cycle_id: uuid.UUID
    employee_id: uuid.UUID
    reviewer_id: uuid.UUID
    overall_rating: int | None
    overall_feedback: str | None
    strengths: str | None
    improvement_areas: str | None
    recommendation: str
    status: str
    submitted_at: datetime | None


class FinalReviewRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    cycle_id: uuid.UUID
    employee_id: uuid.UUID
    finalised_by_id: uuid.UUID | None
    final_rating: int
    comments: str | None
    self_rating: int | None
    manager_rating: int | None
    goal_completion_percentage: int | None
    finalised_at: datetime | None


class EmployeePerformanceRead(BaseModel):
    """Everything about one employee in one cycle, for the review screens."""

    employee: EmployeeRef
    cycle: PerformanceCycleRead
    goals: list[GoalRead]
    total_weightage: Decimal
    goal_completion_percentage: int
    self_review: SelfReviewRead | None
    manager_review: ManagerReviewRead | None
    final_review: FinalReviewRead | None


# ----------------------------------------------------------------------
# Recognition and feedback
# ----------------------------------------------------------------------
class RecognitionCreate(BaseModel):
    employee_id: uuid.UUID
    recognition_type: RecognitionType
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=2000)
    awarded_on: date


class RecognitionRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    employee_id: uuid.UUID
    awarded_by_id: uuid.UUID | None
    recognition_type: str
    title: str
    description: str
    awarded_on: date
    created_at: datetime


class FeedbackCreate(BaseModel):
    to_employee_id: uuid.UUID
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=2000)
    category: FeedbackCategory
    visibility: FeedbackVisibility = FeedbackVisibility.PRIVATE
    feedback_date: date


class FeedbackRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    from_employee_id: uuid.UUID
    to_employee_id: uuid.UUID
    title: str
    description: str
    category: str
    visibility: str
    feedback_date: date
    created_at: datetime


class PerformanceHistoryRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    employee_id: uuid.UUID
    cycle_id: uuid.UUID | None
    event_type: str
    summary: str
    detail: str | None
    rating: int | None
    created_at: datetime


# ----------------------------------------------------------------------
# Listing and analytics
# ----------------------------------------------------------------------
class CycleListParams(PaginationParams):
    search: str | None = None
    status: PerformanceCycleStatus | None = None
    financial_year: str | None = None


class GoalListParams(PaginationParams):
    search: str | None = None
    cycle_id: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    status: GoalStatus | None = None
    priority: GoalPriority | None = None


class FeedbackListParams(PaginationParams):
    employee_id: uuid.UUID | None = None
    category: FeedbackCategory | None = None


class RecognitionListParams(PaginationParams):
    employee_id: uuid.UUID | None = None
    recognition_type: RecognitionType | None = None


class CountByLabel(BaseModel):
    label: str
    count: int


class RatedEmployee(BaseModel):
    employee: EmployeeRef
    rating: int
    cycle_name: str


class DashboardRead(BaseModel):
    """The figures the performance dashboard opens with."""

    active_cycles: int
    goals_assigned: int
    goals_completed: int
    goal_completion_percentage: int
    self_reviews_pending: int
    manager_reviews_pending: int
    reviews_pending: int
    final_ratings: int
    top_performers: list[RatedEmployee]
    low_performance_alerts: list[RatedEmployee]
    by_goal_status: list[CountByLabel]
    by_priority: list[CountByLabel]


class AnalyticsRead(BaseModel):
    """Aggregates for the analytics screen, all scoped to one cycle when given."""

    goal_completion: list[CountByLabel]
    business_unit_performance: list[CountByLabel]
    manager_performance: list[CountByLabel]
    rating_distribution: list[CountByLabel]
    goal_distribution: list[CountByLabel]
    performance_trend: list[CountByLabel]


ReportName = Literal["goal-completion", "performance-summary", "employee-ratings", "recognitions"]
ExportFormat = Literal["csv", "xlsx", "pdf"]
