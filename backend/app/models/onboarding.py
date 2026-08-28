"""Preboarding and onboarding persistence models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase


class PreboardingProfile(Base, AuditableBase):
    __tablename__ = "preboarding_profiles"
    __table_args__ = (UniqueConstraint("candidate_id"), UniqueConstraint("offer_id"))
    candidate_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("candidates.id"))
    offer_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("offers.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    joining_date: Mapped[date] = mapped_column(Date)
    joining_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(20))
    blood_group: Mapped[str | None] = mapped_column(String(3))
    marital_status: Mapped[str | None] = mapped_column(String(20))
    nationality: Mapped[str | None] = mapped_column(String(100))
    personal_email: Mapped[str] = mapped_column(String(320))
    mobile_number: Mapped[str] = mapped_column(String(32))
    emergency_contact: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    addresses: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    bank_details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    aadhaar_number: Mapped[str | None] = mapped_column(String(12))
    pan_number: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(30), default="information_pending", index=True)
    information_approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    employee_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("employees.id"))


class OnboardingCase(Base, AuditableBase):
    __tablename__ = "onboarding_cases"
    __table_args__ = (UniqueConstraint("profile_id"), UniqueConstraint("employee_id"))
    profile_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("preboarding_profiles.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("employees.id"))
    status: Mapped[str] = mapped_column(String(30), default="not_started", index=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tasks: Mapped[list[OnboardingTask]] = relationship(lazy="selectin", order_by="OnboardingTask.due_date")


class OnboardingTask(Base, AuditableBase):
    __tablename__ = "onboarding_tasks"
    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("onboarding_cases.id"), index=True
    )
    category: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), index=True)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="not_started", index=True)
    comments: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    case: Mapped[OnboardingCase] = relationship(back_populates="tasks")


class PolicyAcknowledgement(Base, AuditableBase):
    __tablename__ = "policy_acknowledgements"
    __table_args__ = (UniqueConstraint("profile_id", "policy_code"),)
    profile_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("preboarding_profiles.id"))
    policy_code: Mapped[str] = mapped_column(String(50))
    policy_name: Mapped[str] = mapped_column(String(150))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))


class OnboardingHistory(Base, AuditableBase):
    __tablename__ = "onboarding_history"
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("preboarding_profiles.id"), index=True
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("onboarding_cases.id"))
    action: Mapped[str] = mapped_column(String(80))
    details: Mapped[str | None] = mapped_column(Text)
