from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator

from app.schemas.common import PaginationParams


class ClientCreate(BaseModel):
    client_name: str = Field(min_length=2, max_length=200)
    company_name: str = Field(min_length=2, max_length=200)
    industry: str = Field(min_length=2, max_length=100)
    contact_person: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=32)
    country: str = Field(min_length=2, max_length=100)
    address: str = Field(min_length=5, max_length=2000)
    website: HttpUrl | None = None
    status: Literal["active", "inactive"] = "active"


class ClientUpdate(BaseModel):
    client_name: str | None = Field(None, min_length=2, max_length=200)
    company_name: str | None = Field(None, min_length=2, max_length=200)
    industry: str | None = Field(None, min_length=2, max_length=100)
    contact_person: str | None = Field(None, min_length=2, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(None, min_length=7, max_length=32)
    country: str | None = Field(None, min_length=2, max_length=100)
    address: str | None = Field(None, min_length=5, max_length=2000)
    website: HttpUrl | None = None
    status: Literal["active", "inactive"] | None = None


class ClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    client_code: str
    client_name: str
    company_name: str
    industry: str
    contact_person: str
    email: str
    phone: str
    country: str
    address: str
    website: str | None
    status: str
    created_at: datetime


class ProjectBase(BaseModel):
    project_name: str = Field(min_length=2, max_length=200)
    client_id: uuid.UUID
    description: str = Field(min_length=5, max_length=5000)
    start_date: date
    end_date: date | None = None
    status: Literal["planned", "active", "on_hold", "completed", "cancelled"] = "planned"
    project_manager_id: uuid.UUID
    delivery_manager_id: uuid.UUID | None = None
    work_location_id: uuid.UUID | None = None
    is_billable: bool = True
    technology_stack: list[str] = Field(default_factory=list, max_length=100)
    priority: Literal["low", "medium", "high", "critical"] = "medium"

    @model_validator(mode="after")
    def valid_dates(self) -> Self:
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("Project end date must be on or after start date")
        return self


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    project_name: str | None = Field(None, min_length=2, max_length=200)
    description: str | None = Field(None, min_length=5, max_length=5000)
    start_date: date | None = None
    end_date: date | None = None
    status: Literal["planned", "active", "on_hold", "completed", "cancelled"] | None = None
    project_manager_id: uuid.UUID | None = None
    delivery_manager_id: uuid.UUID | None = None
    work_location_id: uuid.UUID | None = None
    is_billable: bool | None = None
    technology_stack: list[str] | None = Field(None, max_length=100)
    priority: Literal["low", "medium", "high", "critical"] | None = None


class AllocationCreate(BaseModel):
    employee_id: uuid.UUID
    role: str = Field(min_length=2, max_length=150)
    allocation_percentage: Decimal = Field(gt=0, le=100, decimal_places=2)
    start_date: date
    end_date: date | None = None
    reporting_manager_id: uuid.UUID | None = None
    billable: bool = True
    reason: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def valid_dates(self) -> Self:
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("Allocation end date must be on or after start date")
        return self


class AllocationChange(BaseModel):
    allocation_percentage: Decimal = Field(gt=0, le=100, decimal_places=2)
    effective_date: date
    end_date: date | None = None
    role: str | None = Field(None, min_length=2, max_length=150)
    reporting_manager_id: uuid.UUID | None = None
    billable: bool | None = None
    reason: str = Field(min_length=3, max_length=2000)


class AllocationRemove(BaseModel):
    effective_date: date
    reason: str = Field(min_length=3, max_length=2000)


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    employee_id: uuid.UUID
    role: str
    reporting_manager_id: uuid.UUID | None
    joined_at: date
    left_at: date | None


class AllocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    project_id: uuid.UUID
    member_id: uuid.UUID
    allocation_percentage: Decimal
    start_date: date
    end_date: date | None
    billable: bool
    status: str
    reason: str | None
    created_at: datetime


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_code: str
    client: ClientRead
    members: list[MemberRead]
    allocations: list[AllocationRead]
    created_at: datetime


class HistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    previous_project_id: uuid.UUID | None
    new_project_id: uuid.UUID | None
    previous_allocation_percentage: Decimal | None
    new_allocation_percentage: Decimal | None
    effective_date: date
    reason: str
    action: str
    created_at: datetime


class ListParams(PaginationParams):
    status: str | None = None
    search: str | None = None


class DashboardRead(BaseModel):
    total_clients: int
    active_projects: int
    completed_projects: int
    employees_allocated: int
    bench_employees: int
    allocation_utilization_percent: float
    projects_ending_soon: int
    allocation_conflicts: int
    project_headcount: list[dict[str, Any]]
