from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import PaginationParams

Status = Literal[
    "draft", "pending_approval", "approved", "rejected", "open", "on_hold", "closed", "cancelled"
]
Priority = Literal["low", "medium", "high", "critical"]


class RequisitionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    job_title: str = Field(min_length=2, max_length=200)
    hiring_type: Literal["new_position", "replacement", "contract", "internship"]
    request_type: Literal["new_position", "replacement", "contract", "internship"]
    business_unit_id: uuid.UUID
    team_id: uuid.UUID | None = None
    location_id: uuid.UUID
    designation_id: uuid.UUID
    grade_id: uuid.UUID | None = None
    employment_type_id: uuid.UUID
    openings: int = Field(ge=1, le=1000)
    experience_min: int = Field(default=0, ge=0, le=60)
    experience_max: int | None = Field(default=None, ge=0, le=60)
    education: str | None = Field(default=None, max_length=500)
    skills: list[str] = Field(default_factory=list, max_length=100)
    certifications: list[str] = Field(default_factory=list, max_length=100)
    salary_from: Decimal | None = Field(default=None, ge=0)
    salary_to: Decimal | None = Field(default=None, ge=0)
    budget_approved: bool = False
    hiring_manager_id: uuid.UUID
    second_approver_id: uuid.UUID
    hr_approver_id: uuid.UUID
    recruiter_id: uuid.UUID | None = None
    target_joining_date: date
    priority: Priority = "medium"
    responsibilities: str = Field(min_length=10, max_length=20000)
    requirements: str = Field(min_length=10, max_length=20000)
    benefits: str | None = Field(default=None, max_length=20000)
    working_model: Literal["office", "remote", "hybrid"]
    business_justification: str = Field(min_length=10, max_length=10000)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if not hasattr(self, "status") and self.target_joining_date <= date.today():
            raise ValueError("Target joining date must be in the future")
        if self.salary_from is not None and self.salary_to is not None and self.salary_from > self.salary_to:
            raise ValueError("Salary range from cannot exceed salary range to")
        if self.experience_max is not None and self.experience_min > self.experience_max:
            raise ValueError("Minimum experience cannot exceed maximum")
        return self


class RequisitionUpdate(RequisitionCreate):
    pass


class WorkflowAction(BaseModel):
    comments: str | None = Field(default=None, max_length=3000)


class AttachmentLink(BaseModel):
    document_id: uuid.UUID
    attachment_type: Literal["job_description", "budget_approval", "supporting_document"]


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sequence: int
    role_name: str
    approver_id: uuid.UUID
    status: str
    comments: str | None
    acted_at: datetime | None


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    document_id: uuid.UUID
    attachment_type: str
    created_at: datetime


class HistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    action: str
    from_status: str | None
    to_status: str
    comments: str | None
    context: dict[str, Any] | None
    created_at: datetime
    created_by: uuid.UUID | None


class RequisitionRead(RequisitionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    requisition_code: str
    status: Status
    current_approval_sequence: int | None
    submitted_at: datetime | None
    approved_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    deleted_at: datetime | None
    approvals: list[ApprovalRead] = []
    attachments: list[AttachmentRead] = []
    history: list[HistoryRead] = []


class RequisitionListParams(PaginationParams):
    search: str | None = None
    hiring_manager_id: uuid.UUID | None = None
    status: Status | None = None
    priority: Priority | None = None
    date_from: date | None = None
    date_to: date | None = None
    sort_by: str = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"


class DashboardStats(BaseModel):
    total_open: int
    pending_approvals: int
    approved: int
    closed: int
    expired: int
    upcoming_targets: int
    by_business_unit: list[dict[str, Any]]
    hiring_trend: list[dict[str, Any]]


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    message: str
    link: str | None
    notification_type: str
    read_at: datetime | None
    created_at: datetime
