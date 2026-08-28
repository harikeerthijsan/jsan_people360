"""Job requisitions, approvals, attachments, history and notifications."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase

REQUISITION_CODE_SEQUENCE = "job_requisitions_code_seq"
REQUISITION_CODE_DEFAULT = f"'REQ-' || lpad(nextval('{REQUISITION_CODE_SEQUENCE}')::text, 6, '0')"


class JobRequisition(Base, AuditableBase):
    __tablename__ = "job_requisitions"
    __table_args__ = (
        Index("ix_requisitions_status_priority", "status", "priority"),
        Index("ix_requisitions_business_unit_created", "business_unit_id", "created_at"),
    )

    requisition_code: Mapped[str] = mapped_column(
        String(20), unique=True, server_default=text(REQUISITION_CODE_DEFAULT)
    )
    job_title: Mapped[str] = mapped_column(String(200), index=True)
    hiring_type: Mapped[str] = mapped_column(String(30))
    request_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="draft", server_default="draft", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", server_default="medium", index=True)

    business_unit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_units.id", ondelete="RESTRICT")
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT")
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT")
    )
    designation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("designations.id", ondelete="RESTRICT")
    )
    grade_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("grades.id", ondelete="RESTRICT")
    )
    employment_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employment_types.id", ondelete="RESTRICT")
    )

    openings: Mapped[int] = mapped_column(Integer)
    experience_min: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    experience_max: Mapped[int | None] = mapped_column(Integer)
    education: Mapped[str | None] = mapped_column(String(500))
    skills: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    certifications: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    salary_from: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_to: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    hiring_manager_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    second_approver_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    hr_approver_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    recruiter_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    target_joining_date: Mapped[date] = mapped_column(Date)
    responsibilities: Mapped[str] = mapped_column(Text)
    requirements: Mapped[str] = mapped_column(Text)
    benefits: Mapped[str | None] = mapped_column(Text)
    working_model: Mapped[str] = mapped_column(String(20))
    business_justification: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_approval_sequence: Mapped[int | None] = mapped_column(Integer)

    approvals: Mapped[list[RequisitionApproval]] = relationship(
        back_populates="requisition",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="RequisitionApproval.sequence",
    )
    attachments: Mapped[list[RequisitionAttachment]] = relationship(
        back_populates="requisition", cascade="all, delete-orphan", lazy="selectin"
    )
    history: Mapped[list[RequisitionHistory]] = relationship(
        back_populates="requisition",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="RequisitionHistory.created_at.desc()",
    )


class RequisitionApproval(Base, AuditableBase):
    __tablename__ = "requisition_approvals"
    requisition_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_requisitions.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    role_name: Mapped[str] = mapped_column(String(80))
    approver_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(30), default="waiting", server_default="waiting")
    comments: Mapped[str | None] = mapped_column(Text)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requisition: Mapped[JobRequisition] = relationship(back_populates="approvals")


class RequisitionAttachment(Base, AuditableBase):
    __tablename__ = "requisition_attachments"
    requisition_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_requisitions.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT"), unique=True
    )
    attachment_type: Mapped[str] = mapped_column(String(40))
    requisition: Mapped[JobRequisition] = relationship(back_populates="attachments")


class RequisitionHistory(Base, AuditableBase):
    __tablename__ = "requisition_history"
    requisition_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_requisitions.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(80))
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    comments: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    requisition: Mapped[JobRequisition] = relationship(back_populates="history")


class Notification(Base, AuditableBase):
    __tablename__ = "notifications"
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    notification_type: Mapped[str] = mapped_column(String(50))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_read(self) -> bool:
        """``read_at`` is the record; this is the question screens ask of it.

        ``MyNotification`` validates from attributes and declares ``is_read``,
        so this property is load-bearing: without it, the first user to open
        their dashboard with anything in their inbox gets a 422.
        """
        return self.read_at is not None
