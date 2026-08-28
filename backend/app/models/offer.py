"""Offer management, compensation, approvals, templates, and immutable versions."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase


class Offer(Base, AuditableBase):
    __tablename__ = "offers"
    __table_args__ = (Index("ix_offers_status_expiry", "status", "expiry_date"),)
    offer_code: Mapped[str] = mapped_column(
        String(20), unique=True, server_default=text("'OFF-' || lpad(nextval('offers_code_seq')::text,6,'0')")
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"), index=True
    )
    job_opening_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_openings.id", ondelete="RESTRICT")
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offer_templates.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(30), default="draft", server_default="draft", index=True)
    ctc: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    joining_date: Mapped[date] = mapped_column(Date)
    probation_months: Mapped[int] = mapped_column(Integer)
    notice_period_days: Mapped[int] = mapped_column(Integer)
    reporting_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    work_mode: Mapped[str] = mapped_column(String(20))
    shift: Mapped[str | None] = mapped_column(String(100))
    benefits: Mapped[str] = mapped_column(Text)
    leave_policy_summary: Mapped[str] = mapped_column(Text)
    working_hours: Mapped[str] = mapped_column(Text)
    confidentiality: Mapped[str] = mapped_column(Text)
    nda_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    additional_conditions: Mapped[str | None] = mapped_column(Text)
    release_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decline_reason: Mapped[str | None] = mapped_column(Text)
    clarification_request: Mapped[str | None] = mapped_column(Text)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawal_reason: Mapped[str | None] = mapped_column(Text)
    current_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    salary_components: Mapped[list[OfferSalaryComponent]] = relationship(
        back_populates="offer", lazy="selectin", cascade="all, delete-orphan"
    )
    versions: Mapped[list[OfferVersion]] = relationship(
        back_populates="offer", lazy="selectin", order_by="OfferVersion.version_number.desc()"
    )
    approvals: Mapped[list[OfferApproval]] = relationship(
        back_populates="offer", lazy="selectin", order_by="OfferApproval.sequence"
    )
    history: Mapped[list[OfferStatusHistory]] = relationship(
        back_populates="offer", lazy="selectin", order_by="OfferStatusHistory.created_at.desc()"
    )


class OfferTemplate(Base, AuditableBase):
    __tablename__ = "offer_templates"
    name: Mapped[str] = mapped_column(String(150), unique=True)
    body: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class OfferVersion(Base, AuditableBase):
    __tablename__ = "offer_versions"
    __table_args__ = (UniqueConstraint("offer_id", "version_number"),)
    offer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offers.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    pdf_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    offer: Mapped[Offer] = relationship(back_populates="versions")


class OfferApproval(Base, AuditableBase):
    __tablename__ = "offer_approvals"
    __table_args__ = (UniqueConstraint("offer_id", "sequence"),)
    offer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offers.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    role_name: Mapped[str] = mapped_column(String(100))
    approver_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(30), default="waiting", server_default="waiting")
    comments: Mapped[str | None] = mapped_column(Text)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offer: Mapped[Offer] = relationship(back_populates="approvals")


class OfferStatusHistory(Base, AuditableBase):
    __tablename__ = "offer_status_history"
    offer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offers.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(50))
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    comments: Mapped[str | None] = mapped_column(Text)
    offer: Mapped[Offer] = relationship(back_populates="history")


class OfferSalaryComponent(Base, AuditableBase):
    __tablename__ = "offer_salary_components"
    __table_args__ = (UniqueConstraint("offer_id", "name"),)
    offer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    component_type: Mapped[str] = mapped_column(String(30))
    annual_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    is_employer_contribution: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    offer: Mapped[Offer] = relationship(back_populates="salary_components")
