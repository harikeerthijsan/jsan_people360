"""Client, project and employee allocation domain models."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
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


class Client(Base, AuditableBase):
    __tablename__ = "clients"
    client_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text("'CLT-' || lpad(nextval('clients_code_seq')::text,6,'0')"),
    )
    client_name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(100))
    contact_person: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str] = mapped_column(String(32))
    country: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", index=True)
    projects: Mapped[list[Project]] = relationship(back_populates="client", lazy="selectin")


class Project(Base, AuditableBase):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_status_end_date", "status", "end_date"),)
    project_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text("'PRJ-' || lpad(nextval('projects_code_seq')::text,6,'0')"),
    )
    project_name: Mapped[str] = mapped_column(String(200), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="planned", server_default="planned", index=True)
    project_manager_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("employees.id"))
    delivery_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id")
    )
    work_location_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("locations.id")
    )
    is_billable: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    technology_stack: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    priority: Mapped[str] = mapped_column(String(20), default="medium", server_default="medium")
    client: Mapped[Client] = relationship(back_populates="projects", lazy="joined")
    members: Mapped[list[ProjectMember]] = relationship(back_populates="project", lazy="selectin")
    allocations: Mapped[list[EmployeeAllocation]] = relationship(back_populates="project", lazy="selectin")


class ProjectMember(Base, AuditableBase):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "employee_id"),)
    project_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(150))
    reporting_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id")
    )
    joined_at: Mapped[date] = mapped_column(Date)
    left_at: Mapped[date | None] = mapped_column(Date)
    project: Mapped[Project] = relationship(back_populates="members")


class EmployeeAllocation(Base, AuditableBase):
    __tablename__ = "employee_allocations"
    __table_args__ = (Index("ix_allocations_employee_dates", "employee_id", "start_date", "end_date"),)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id"), index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("project_members.id"))
    allocation_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    billable: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    project: Mapped[Project] = relationship(back_populates="allocations", lazy="joined")


class AllocationHistory(Base, AuditableBase):
    __tablename__ = "allocation_history"
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), index=True
    )
    previous_project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id")
    )
    new_project_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id"))
    previous_allocation_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    new_allocation_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    effective_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(30))
