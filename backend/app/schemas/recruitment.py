from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.schemas.common import PaginationParams


class OpeningCreate(BaseModel):
    requisition_id: uuid.UUID
    recruiter_id: uuid.UUID | None = None
    closing_date: date | None = None


class OpeningRead(OpeningCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_code: str
    status: str
    published_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    job_title: str
    location_id: uuid.UUID
    employment_type_id: uuid.UUID
    open_positions: int


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str


class StageRead(SourceRead):
    sequence: int
    category: str


class StageCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    sequence: int = Field(ge=1)
    category: Literal["active", "hired", "terminal"] = "active"


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    proficiency: str | None


class CandidateDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    document_id: uuid.UUID
    document_kind: str
    created_at: datetime


class StageHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    from_stage_id: uuid.UUID | None
    to_stage_id: uuid.UUID
    comments: str | None
    created_at: datetime


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    body: str
    mentions: str | None
    is_internal: bool
    created_at: datetime
    created_by: uuid.UUID | None


class DocumentLink(BaseModel):
    document_id: uuid.UUID
    document_kind: Literal["resume", "cover_letter", "portfolio", "certificate"]


class CandidateCreate(BaseModel):
    job_opening_id: uuid.UUID
    source_id: uuid.UUID
    recruiter_id: uuid.UUID | None = None
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    mobile_number: str = Field(pattern=r"^\+?[0-9 ()-]{7,30}$")
    linkedin_url: HttpUrl | None = None
    current_company: str | None = Field(None, max_length=200)
    current_designation: str | None = Field(None, max_length=200)
    experience_years: Decimal = Field(ge=0, le=60)
    current_ctc: Decimal | None = Field(None, ge=0)
    expected_ctc: Decimal | None = Field(None, ge=0)
    notice_period_days: int = Field(ge=0, le=365)
    current_location: str | None = Field(None, max_length=200)
    preferred_location: str | None = Field(None, max_length=200)
    certifications: str | None = None
    tags: str | None = None
    skills: list[str] = Field(min_length=1)
    resume_document_id: uuid.UUID

    @model_validator(mode="after")
    def validate_ctc(self) -> Self:
        if (
            self.current_ctc is not None
            and self.expected_ctc is not None
            and self.expected_ctc < self.current_ctc
        ):
            raise ValueError("Expected CTC cannot be lower than current CTC")
        return self


class CandidateUpdate(BaseModel):
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    mobile_number: str | None = Field(None, pattern=r"^\+?[0-9 ()-]{7,30}$")
    linkedin_url: HttpUrl | None = None
    current_company: str | None = None
    current_designation: str | None = None
    experience_years: Decimal | None = Field(None, ge=0, le=60)
    current_ctc: Decimal | None = Field(None, ge=0)
    expected_ctc: Decimal | None = Field(None, ge=0)
    notice_period_days: int | None = Field(None, ge=0, le=365)
    current_location: str | None = None
    preferred_location: str | None = None
    certifications: str | None = None
    tags: str | None = None
    recruiter_id: uuid.UUID | None = None


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    candidate_code: str
    job_opening_id: uuid.UUID
    source_id: uuid.UUID
    stage_id: uuid.UUID
    recruiter_id: uuid.UUID | None
    first_name: str
    last_name: str
    email: str
    mobile_number: str
    linkedin_url: str | None
    current_company: str | None
    current_designation: str | None
    experience_years: Decimal
    current_ctc: Decimal | None
    expected_ctc: Decimal | None
    notice_period_days: int
    current_location: str | None
    preferred_location: str | None
    certifications: str | None
    tags: str | None
    applied_at: datetime
    stage: StageRead
    source: SourceRead
    skills: list[SkillRead]
    documents: list[CandidateDocumentRead]
    stage_history: list[StageHistoryRead]
    notes: list[NoteRead]


class CandidateListParams(PaginationParams):
    search: str | None = None
    skill: str | None = None
    experience_min: Decimal | None = None
    experience_max: Decimal | None = None
    notice_period_max: int | None = None
    source_id: uuid.UUID | None = None
    recruiter_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    location: str | None = None
    job_opening_id: uuid.UUID | None = None


class StageMove(BaseModel):
    stage_id: uuid.UUID
    comments: str | None = Field(None, max_length=2000)


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    mentions: str | None = None
    is_internal: bool = True


class TalentPoolCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(None, max_length=2000)


class TalentPoolRead(TalentPoolCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime


class PoolMember(BaseModel):
    candidate_id: uuid.UUID


class DuplicateResult(BaseModel):
    duplicates: list[CandidateRead]


class RecruitmentDashboard(BaseModel):
    open_jobs: int
    total_applicants: int
    offers_released: int
    offers_accepted: int
    offers_declined: int
    joining_pending: int
    by_stage: list[dict[str, Any]]
    recruiter_workload: list[dict[str, Any]]
    hiring_trend: list[dict[str, Any]]
    average_time_to_hire_days: float
    average_time_to_fill_days: float
