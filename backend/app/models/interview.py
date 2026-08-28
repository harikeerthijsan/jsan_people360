"""Interview scheduling, panels, scorecards, history, and attachments."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase


class Interview(Base, AuditableBase):
    __tablename__ = "interviews"
    __table_args__ = (
        Index("ix_interviews_schedule_status", "starts_at", "status"),
        Index("ix_interviews_candidate_schedule", "candidate_id", "starts_at"),
    )
    interview_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text("'INT-' || lpad(nextval('interviews_code_seq')::text,6,'0')"),
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"), index=True
    )
    job_opening_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_openings.id", ondelete="RESTRICT"), index=True
    )
    interview_type: Mapped[str] = mapped_column(String(30))
    interview_round: Mapped[str] = mapped_column(String(100))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    time_zone: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20))
    meeting_link: Mapped[str | None] = mapped_column(String(1000))
    location: Mapped[str | None] = mapped_column(String(500))
    recruiter_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(30), default="scheduled", server_default="scheduled", index=True
    )
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    overall_recommendation: Mapped[str | None] = mapped_column(String(30))
    decision: Mapped[str | None] = mapped_column(String(30))
    panels: Mapped[list[InterviewPanel]] = relationship(
        back_populates="interview", lazy="selectin", cascade="all, delete-orphan"
    )
    feedback: Mapped[list[InterviewFeedback]] = relationship(back_populates="interview", lazy="selectin")
    history: Mapped[list[InterviewScheduleHistory]] = relationship(
        back_populates="interview", lazy="selectin", order_by="InterviewScheduleHistory.created_at.desc()"
    )
    attachments: Mapped[list[InterviewAttachment]] = relationship(back_populates="interview", lazy="selectin")


class InterviewPanel(Base, AuditableBase):
    __tablename__ = "interview_panels"
    __table_args__ = (UniqueConstraint("interview_id", "employee_id"),)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    designation_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("designations.id", ondelete="SET NULL")
    )
    panel_role: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="assigned", server_default="assigned")
    interview: Mapped[Interview] = relationship(back_populates="panels")


class InterviewFeedback(Base, AuditableBase):
    __tablename__ = "interview_feedback"
    __table_args__ = (UniqueConstraint("interview_id", "interviewer_id"),)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    interviewer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    overall_comments: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(String(30))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    interview: Mapped[Interview] = relationship(back_populates="feedback")
    scores: Mapped[list[InterviewScore]] = relationship(
        back_populates="feedback", lazy="selectin", cascade="all, delete-orphan"
    )


class InterviewScore(Base, AuditableBase):
    __tablename__ = "interview_scores"
    __table_args__ = (UniqueConstraint("feedback_id", "category"),)
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interview_feedback.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(50))
    score: Mapped[int] = mapped_column(Integer)
    comments: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[InterviewFeedback] = relationship(back_populates="scores")


class InterviewScheduleHistory(Base, AuditableBase):
    __tablename__ = "interview_schedule_history"
    interview_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(50))
    previous_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comments: Mapped[str | None] = mapped_column(Text)
    interview: Mapped[Interview] = relationship(back_populates="history")


class InterviewAttachment(Base, AuditableBase):
    __tablename__ = "interview_attachments"
    __table_args__ = (UniqueConstraint("interview_id", "document_id"),)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT")
    )
    attachment_kind: Mapped[str] = mapped_column(String(40))
    interview: Mapped[Interview] = relationship(back_populates="attachments")
