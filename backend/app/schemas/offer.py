from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import PaginationParams


class SalaryComponentInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    component_type: str = Field(min_length=1, max_length=30)
    annual_amount: Decimal = Field(ge=0)
    is_employer_contribution: bool = False


class OfferCreate(BaseModel):
    candidate_id: uuid.UUID
    template_id: uuid.UUID | None = None
    ctc: Decimal = Field(gt=0)
    joining_date: date
    probation_months: int = Field(ge=0, le=36)
    notice_period_days: int = Field(ge=0, le=365)
    reporting_manager_id: uuid.UUID | None = None
    work_mode: Literal["office", "hybrid", "remote"]
    shift: str | None = None
    benefits: str = Field(min_length=1)
    leave_policy_summary: str = Field(min_length=1)
    working_hours: str = Field(min_length=1)
    confidentiality: str = Field(min_length=1)
    nda_required: bool = False
    additional_conditions: str | None = None
    expiry_date: date
    salary_components: list[SalaryComponentInput] = Field(min_length=3)
    hr_executive_id: uuid.UUID
    hr_manager_id: uuid.UUID
    business_unit_head_id: uuid.UUID

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.joining_date <= date.today():
            raise ValueError("Joining date must be in the future")
        if self.expiry_date <= date.today() or self.expiry_date >= self.joining_date:
            raise ValueError("Expiry date must be before joining date and in the future")
        names = {x.name.lower().replace(" ", "_") for x in self.salary_components}
        if not {"basic_salary", "hra", "special_allowance"}.issubset(names):
            raise ValueError("Basic Salary, HRA, and Special Allowance are mandatory")
        if sum(x.annual_amount for x in self.salary_components) != self.ctc:
            raise ValueError("Salary components must equal CTC")
        return self


class OfferUpdate(BaseModel):
    joining_date: date | None = None
    probation_months: int | None = Field(None, ge=0, le=36)
    notice_period_days: int | None = Field(None, ge=0, le=365)
    reporting_manager_id: uuid.UUID | None = None
    work_mode: Literal["office", "hybrid", "remote"] | None = None
    shift: str | None = None
    benefits: str | None = None
    leave_policy_summary: str | None = None
    working_hours: str | None = None
    confidentiality: str | None = None
    nda_required: bool | None = None
    additional_conditions: str | None = None
    expiry_date: date | None = None


class ApprovalAction(BaseModel):
    comments: str | None = Field(None, max_length=2000)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ClarificationRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class TemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    body: str = Field(min_length=20)


class TemplateRead(TemplateCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    is_active: bool
    created_at: datetime


class ComponentRead(SalaryComponentInput):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    version_number: int
    snapshot: dict[str, Any]
    pdf_document_id: uuid.UUID | None
    created_at: datetime


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sequence: int
    role_name: str
    approver_id: uuid.UUID
    status: str
    comments: str | None
    acted_at: datetime | None


class HistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    action: str
    from_status: str | None
    to_status: str
    comments: str | None
    created_at: datetime


class OfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    offer_code: str
    candidate_id: uuid.UUID
    job_opening_id: uuid.UUID
    template_id: uuid.UUID | None
    status: str
    ctc: Decimal
    joining_date: date
    probation_months: int
    notice_period_days: int
    reporting_manager_id: uuid.UUID | None
    work_mode: str
    shift: str | None
    benefits: str
    leave_policy_summary: str
    working_hours: str
    confidentiality: str
    nda_required: bool
    additional_conditions: str | None
    release_date: date | None
    expiry_date: date
    accepted_at: datetime | None
    declined_at: datetime | None
    decline_reason: str | None
    clarification_request: str | None
    withdrawn_at: datetime | None
    withdrawal_reason: str | None
    current_version: int
    salary_components: list[ComponentRead]
    versions: list[VersionRead]
    approvals: list[ApprovalRead]
    history: list[HistoryRead]
    created_at: datetime


class OfferListParams(PaginationParams):
    status: str | None = None
    candidate_id: uuid.UUID | None = None
    search: str | None = None


class OfferDashboard(BaseModel):
    total: int
    draft: int
    pending_approval: int
    approved: int
    released: int
    accepted: int
    declined: int
    expired: int
    joining_pending: int
    acceptance_rate: float
    offer_to_join_ratio: float
