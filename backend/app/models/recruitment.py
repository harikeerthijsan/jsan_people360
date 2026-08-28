"""Recruitment and applicant-tracking domain models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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
from app.models.requisition import JobRequisition


class JobOpening(Base, AuditableBase):
    __tablename__ = "job_openings"
    __table_args__ = (Index("ix_job_openings_status_recruiter", "status", "recruiter_id"),)
    job_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text("'JOB-' || lpad(nextval('job_openings_code_seq')::text, 6, '0')"),
    )
    requisition_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_requisitions.id", ondelete="RESTRICT"), unique=True
    )
    recruiter_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft", index=True)
    closing_date: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidates: Mapped[list[Candidate]] = relationship(back_populates="job_opening", lazy="selectin")
    requisition: Mapped[JobRequisition] = relationship(lazy="joined")

    @property
    def job_title(self) -> str:
        return self.requisition.job_title

    @property
    def location_id(self) -> uuid.UUID:
        return self.requisition.location_id

    @property
    def employment_type_id(self) -> uuid.UUID:
        return self.requisition.employment_type_id

    @property
    def open_positions(self) -> int:
        return self.requisition.openings


class CandidateSource(Base, AuditableBase):
    __tablename__ = "candidate_sources"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")


class RecruitmentStage(Base, AuditableBase):
    __tablename__ = "recruitment_stages"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    sequence: Mapped[int] = mapped_column(Integer, unique=True)
    category: Mapped[str] = mapped_column(String(30), default="active", server_default="active")
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")


class Candidate(Base, AuditableBase):
    __tablename__ = "candidates"
    __table_args__ = (
        Index("ix_candidates_name", "first_name", "last_name"),
        Index("ix_candidates_stage_recruiter", "stage_id", "recruiter_id"),
    )
    candidate_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text("'CAN-' || lpad(nextval('candidates_code_seq')::text, 6, '0')"),
    )
    job_opening_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_openings.id", ondelete="RESTRICT"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidate_sources.id", ondelete="RESTRICT"), index=True
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recruitment_stages.id", ondelete="RESTRICT"), index=True
    )
    recruiter_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320), index=True)
    mobile_number: Mapped[str] = mapped_column(String(30), index=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    current_company: Mapped[str | None] = mapped_column(String(200))
    current_designation: Mapped[str | None] = mapped_column(String(200))
    experience_years: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=0, server_default="0")
    current_ctc: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    expected_ctc: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    notice_period_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    current_location: Mapped[str | None] = mapped_column(String(200), index=True)
    preferred_location: Mapped[str | None] = mapped_column(String(200))
    certifications: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    hired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job_opening: Mapped[JobOpening] = relationship(back_populates="candidates")
    stage: Mapped[RecruitmentStage] = relationship(lazy="joined")
    source: Mapped[CandidateSource] = relationship(lazy="joined")
    documents: Mapped[list[CandidateDocument]] = relationship(back_populates="candidate", lazy="selectin")
    skills: Mapped[list[CandidateSkill]] = relationship(
        back_populates="candidate", lazy="selectin", cascade="all, delete-orphan"
    )
    stage_history: Mapped[list[CandidateStageHistory]] = relationship(
        back_populates="candidate", lazy="selectin", order_by="CandidateStageHistory.created_at.desc()"
    )
    notes: Mapped[list[RecruiterNote]] = relationship(
        back_populates="candidate", lazy="selectin", order_by="RecruiterNote.created_at.desc()"
    )


class CandidateDocument(Base, AuditableBase):
    __tablename__ = "candidate_documents"
    __table_args__ = (UniqueConstraint("candidate_id", "document_id"),)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT")
    )
    document_kind: Mapped[str] = mapped_column(String(30))
    candidate: Mapped[Candidate] = relationship(back_populates="documents")


class CandidateSkill(Base, AuditableBase):
    __tablename__ = "candidate_skills"
    __table_args__ = (UniqueConstraint("candidate_id", "name"),)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100), index=True)
    proficiency: Mapped[str | None] = mapped_column(String(30))
    candidate: Mapped[Candidate] = relationship(back_populates="skills")


class CandidateStageHistory(Base, AuditableBase):
    __tablename__ = "candidate_stage_history"
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recruitment_stages.id", ondelete="RESTRICT")
    )
    to_stage_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recruitment_stages.id", ondelete="RESTRICT")
    )
    comments: Mapped[str | None] = mapped_column(Text)
    candidate: Mapped[Candidate] = relationship(back_populates="stage_history")


class RecruiterNote(Base, AuditableBase):
    __tablename__ = "recruiter_notes"
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    mentions: Mapped[str | None] = mapped_column(Text)
    is_internal: Mapped[bool] = mapped_column(default=True, server_default="true")
    candidate: Mapped[Candidate] = relationship(back_populates="notes")


class TalentPool(Base, AuditableBase):
    __tablename__ = "talent_pools"
    name: Mapped[str] = mapped_column(String(150), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    candidates: Mapped[list[CandidateTalentPool]] = relationship(
        back_populates="talent_pool", lazy="selectin"
    )


class CandidateTalentPool(Base, AuditableBase):
    __tablename__ = "candidate_talent_pools"
    __table_args__ = (UniqueConstraint("candidate_id", "talent_pool_id"),)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    talent_pool_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("talent_pools.id", ondelete="CASCADE"), index=True
    )
    talent_pool: Mapped[TalentPool] = relationship(back_populates="candidates")
