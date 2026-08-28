"""Performance management domain models.

The rule this module exists to enforce is that **a submitted review is never
rewritten**. Ratings, feedback and recognitions are written once and then only
read; a correction is a new cycle, not an edit to a closed one. That is what
makes a year-on-year performance record defensible when someone disputes it.

Two shapes are worth knowing before reading further:

* **Ratings live in one table, not two.** A self rating and a manager rating of
  the same goal are the same thing -- a score out of five with comments -- so
  they share :class:`GoalRating` and are told apart by ``stage``. Two
  near-identical tables would have meant two of every query and two chances for
  the scales to drift apart.
* **Progress is append-only.** :class:`GoalProgress` records what was reported
  and when; the goal's current percentage is the latest row, not a column that
  someone overwrote.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.enums import (
    FEEDBACK_CATEGORY_SQL_VALUES,
    FEEDBACK_VISIBILITY_SQL_VALUES,
    GOAL_PRIORITY_SQL_VALUES,
    GOAL_STATUS_SQL_VALUES,
    MAX_RATING,
    MIN_RATING,
    PERFORMANCE_CYCLE_STATUS_SQL_VALUES,
    PERFORMANCE_RECOMMENDATION_SQL_VALUES,
    RECOGNITION_TYPE_SQL_VALUES,
    REVIEW_STAGE_SQL_VALUES,
    REVIEW_STATUS_SQL_VALUES,
)

#: Generated identifiers, issued by PostgreSQL so two concurrent writers can
#: never be handed the same number.
CYCLE_CODE_SEQUENCE = "performance_cycles_code_seq"
GOAL_CODE_SEQUENCE = "goals_code_seq"


def _rating_check(table: str, column: str) -> CheckConstraint:
    """The 1-5 scale, enforced by the database rather than only by Pydantic.

    Named explicitly because the metadata naming convention cannot derive a name
    for a bare check -- an unnamed one would fail at import.
    """
    return CheckConstraint(
        f"{column} IS NULL OR ({column} >= {MIN_RATING} AND {column} <= {MAX_RATING})",
        name=f"ck_{table}_{column}",
    )


class PerformanceCycle(Base, AuditableBase):
    """One appraisal period, e.g. "FY 2026-27 Annual"."""

    __tablename__ = "performance_cycles"
    __table_args__ = (
        UniqueConstraint("name", "financial_year", name="uq_performance_cycles_name_year"),
        CheckConstraint("end_date > start_date", name="ck_performance_cycles_dates"),
        CheckConstraint(
            f"status IN ({PERFORMANCE_CYCLE_STATUS_SQL_VALUES})", name="ck_performance_cycles_status"
        ),
        Index("ix_performance_cycles_status_start", "status", "start_date"),
        {"comment": "Appraisal periods. Multiple cycles may exist across years."},
    )

    cycle_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text(f"'PC-' || lpad(nextval('{CYCLE_CODE_SEQUENCE}')::text, 6, '0')"),
    )
    name: Mapped[str] = mapped_column(String(150), index=True)
    financial_year: Mapped[str] = mapped_column(String(20), index=True, doc="e.g. 2026-27")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)

    # Deadlines are advisory rather than enforced: a review submitted late is
    # still a review, and refusing it would lose the content entirely.
    self_review_deadline: Mapped[date] = mapped_column(Date)
    manager_review_deadline: Mapped[date] = mapped_column(Date)
    hr_review_deadline: Mapped[date] = mapped_column(Date)

    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft", index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    goals: Mapped[list[Goal]] = relationship(back_populates="cycle", lazy="selectin")

    def __repr__(self) -> str:
        return f"<PerformanceCycle {self.cycle_code} {self.name!r}>"


class Goal(Base, AuditableBase):
    """One objective assigned to an employee within a cycle."""

    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint("due_date >= start_date", name="ck_goals_dates"),
        CheckConstraint("weightage > 0 AND weightage <= 100", name="ck_goals_weightage"),
        CheckConstraint(f"status IN ({GOAL_STATUS_SQL_VALUES})", name="ck_goals_status"),
        CheckConstraint(f"priority IN ({GOAL_PRIORITY_SQL_VALUES})", name="ck_goals_priority"),
        CheckConstraint(
            "completion_percentage >= 0 AND completion_percentage <= 100", name="ck_goals_completion"
        ),
        Index("ix_goals_cycle_employee", "cycle_id", "employee_id"),
        {"comment": "Objectives assigned to an employee for one performance cycle."},
    )

    goal_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text(f"'GOAL-' || lpad(nextval('{GOAL_CODE_SEQUENCE}')::text, 6, '0')"),
    )
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("performance_cycles.id", ondelete="RESTRICT"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    # Optional: a goal may be tied to delivery work, or be a personal
    # development objective with no project behind it.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )

    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100), index=True)
    success_criteria: Mapped[str] = mapped_column(Text, doc="How the goal will be judged met.")

    weightage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), doc="Share of the employee's cycle, as a percentage."
    )
    start_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date, index=True)

    priority: Mapped[str] = mapped_column(String(20), default="medium", server_default="medium", index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="not_started", server_default="not_started", index=True
    )
    #: Denormalised from the newest progress row so a list page does not need a
    #: correlated subquery per goal. The progress trail remains the source of truth.
    completion_percentage: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    cycle: Mapped[PerformanceCycle] = relationship(back_populates="goals", lazy="joined")
    progress_updates: Mapped[list[GoalProgress]] = relationship(
        back_populates="goal",
        lazy="selectin",
        order_by="GoalProgress.created_at.desc()",
    )
    ratings: Mapped[list[GoalRating]] = relationship(back_populates="goal", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Goal {self.goal_code} {self.title!r} {self.completion_percentage}%>"


class GoalProgress(Base, AuditableBase):
    """One progress report against a goal. Append-only.

    There is deliberately no update or delete: an employee's account of where a
    goal stood in March is a fact about March, and editing it later would make
    the trail useless as evidence in a review.
    """

    __tablename__ = "goal_progress"
    __table_args__ = (
        CheckConstraint(
            "completion_percentage >= 0 AND completion_percentage <= 100",
            name="ck_goal_progress_completion",
        ),
        Index("ix_goal_progress_goal_created", "goal_id", "created_at"),
        {"comment": "Append-only progress reports against a goal."},
    )

    goal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), index=True
    )
    completion_percentage: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), doc="The goal's status as at this update.")
    comments: Mapped[str | None] = mapped_column(Text)
    #: Evidence lives in the Document Vault rather than being re-uploaded here,
    #: so it inherits versioning, validation and the audit trail for free.
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )

    goal: Mapped[Goal] = relationship(back_populates="progress_updates")

    def __repr__(self) -> str:
        return f"<GoalProgress goal={self.goal_id} {self.completion_percentage}%>"


class GoalRating(Base, AuditableBase):
    """One reviewer's score for one goal.

    Shared by the self and manager stages -- see the module docstring. The
    unique constraint is what stops a second submission silently creating a
    duplicate score for the same goal.
    """

    __tablename__ = "goal_ratings"
    __table_args__ = (
        UniqueConstraint("goal_id", "stage", name="uq_goal_ratings_goal_stage"),
        CheckConstraint(f"stage IN ({REVIEW_STAGE_SQL_VALUES})", name="ck_goal_ratings_stage"),
        _rating_check("goal_ratings", "rating"),
        {"comment": "Per-goal scores from the self and manager review stages."},
    )

    goal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(20), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    comments: Mapped[str | None] = mapped_column(Text)
    rated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )

    goal: Mapped[Goal] = relationship(back_populates="ratings")

    def __repr__(self) -> str:
        return f"<GoalRating goal={self.goal_id} {self.stage}={self.rating}>"


class SelfReview(Base, AuditableBase):
    """An employee's own assessment for one cycle."""

    __tablename__ = "self_reviews"
    __table_args__ = (
        UniqueConstraint("cycle_id", "employee_id", name="uq_self_reviews_cycle_employee"),
        CheckConstraint(f"status IN ({REVIEW_STATUS_SQL_VALUES})", name="ck_self_reviews_status"),
        _rating_check("self_reviews", "overall_rating"),
        {"comment": "One self-assessment per employee per cycle."},
    )

    cycle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("performance_cycles.id", ondelete="RESTRICT"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    overall_rating: Mapped[int | None] = mapped_column(Integer)
    overall_comments: Mapped[str | None] = mapped_column(Text)
    achievements: Mapped[str | None] = mapped_column(Text)
    challenges: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<SelfReview cycle={self.cycle_id} employee={self.employee_id} {self.status}>"


class ManagerReview(Base, AuditableBase):
    """A manager's assessment of one employee for one cycle."""

    __tablename__ = "manager_reviews"
    __table_args__ = (
        UniqueConstraint("cycle_id", "employee_id", name="uq_manager_reviews_cycle_employee"),
        CheckConstraint(f"status IN ({REVIEW_STATUS_SQL_VALUES})", name="ck_manager_reviews_status"),
        CheckConstraint(
            f"recommendation IN ({PERFORMANCE_RECOMMENDATION_SQL_VALUES})",
            name="ck_manager_reviews_recommendation",
        ),
        _rating_check("manager_reviews", "overall_rating"),
        {"comment": "One manager assessment per employee per cycle."},
    )

    cycle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("performance_cycles.id", ondelete="RESTRICT"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    overall_rating: Mapped[int | None] = mapped_column(Integer)
    overall_feedback: Mapped[str | None] = mapped_column(Text)
    strengths: Mapped[str | None] = mapped_column(Text)
    improvement_areas: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(String(30), default="none", server_default="none")
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<ManagerReview cycle={self.cycle_id} employee={self.employee_id} {self.status}>"


class FinalReview(Base, AuditableBase):
    """HR's finalisation. Written once, then read forever."""

    __tablename__ = "final_reviews"
    __table_args__ = (
        UniqueConstraint("cycle_id", "employee_id", name="uq_final_reviews_cycle_employee"),
        _rating_check("final_reviews", "final_rating"),
        {"comment": "The rating of record for an employee in a cycle."},
    )

    cycle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("performance_cycles.id", ondelete="RESTRICT"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    finalised_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    final_rating: Mapped[int] = mapped_column(Integer, index=True)
    comments: Mapped[str | None] = mapped_column(Text)
    #: Copied from the two earlier stages at the moment of finalisation, so the
    #: record still reads correctly if a goal is later cancelled or re-weighted.
    self_rating: Mapped[int | None] = mapped_column(Integer)
    manager_rating: Mapped[int | None] = mapped_column(Integer)
    goal_completion_percentage: Mapped[int | None] = mapped_column(Integer)
    finalised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<FinalReview cycle={self.cycle_id} employee={self.employee_id} rating={self.final_rating}>"


class Recognition(Base, AuditableBase):
    """A public thank-you, independent of any cycle.

    Not tied to a performance cycle on purpose: recognition works when it is
    immediate, and waiting for an appraisal window would defeat it.
    """

    __tablename__ = "recognitions"
    __table_args__ = (
        CheckConstraint(f"recognition_type IN ({RECOGNITION_TYPE_SQL_VALUES})", name="ck_recognitions_type"),
        Index("ix_recognitions_employee_awarded", "employee_id", "awarded_on"),
        {"comment": "Recognitions awarded to employees."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    awarded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    recognition_type: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    awarded_on: Mapped[date] = mapped_column(Date, index=True)

    def __repr__(self) -> str:
        return f"<Recognition {self.recognition_type} employee={self.employee_id}>"


class ContinuousFeedback(Base, AuditableBase):
    """Feedback exchanged at any time, not only at review time."""

    __tablename__ = "continuous_feedback"
    __table_args__ = (
        CheckConstraint(f"category IN ({FEEDBACK_CATEGORY_SQL_VALUES})", name="ck_feedback_category"),
        CheckConstraint(f"visibility IN ({FEEDBACK_VISIBILITY_SQL_VALUES})", name="ck_feedback_visibility"),
        Index("ix_feedback_recipient_date", "to_employee_id", "feedback_date"),
        {"comment": "Continuous feedback between employees."},
    )

    from_employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    to_employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private", server_default="private")
    feedback_date: Mapped[date] = mapped_column(Date, index=True)

    def __repr__(self) -> str:
        return f"<ContinuousFeedback {self.category} to={self.to_employee_id}>"


class PerformanceHistory(Base, AuditableBase):
    """An immutable record of what happened, and when.

    Distinct from the audit log: that records who touched what, this records the
    performance narrative an employee and their manager can read back years
    later. Append-only, like the employment history it sits alongside.
    """

    __tablename__ = "performance_history"
    __table_args__ = (
        Index("ix_performance_history_employee_created", "employee_id", "created_at"),
        {"comment": "Append-only narrative of performance events."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("performance_cycles.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    summary: Mapped[str] = mapped_column(
        Text, doc="Frozen at write time; a later rename cannot rewrite history."
    )
    detail: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(Integer)

    def __repr__(self) -> str:
        return f"<PerformanceHistory {self.event_type} employee={self.employee_id}>"
