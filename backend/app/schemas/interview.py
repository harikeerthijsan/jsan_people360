from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.schemas.common import PaginationParams

InterviewType = Literal["hr", "technical", "managerial", "client", "final_hr"]
Mode = Literal["online", "offline", "hybrid"]
PanelRole = Literal["lead_interviewer", "panel_member", "observer"]
Recommendation = Literal["strong_hire", "hire", "hold", "reject"]


class PanelAssign(BaseModel):
    employee_id: uuid.UUID
    designation_id: uuid.UUID | None = None
    panel_role: PanelRole


class InterviewCreate(BaseModel):
    candidate_id: uuid.UUID
    interview_type: InterviewType
    interview_round: str = Field(min_length=1, max_length=100)
    starts_at: datetime
    ends_at: datetime
    time_zone: str = Field(min_length=1, max_length=100)
    mode: Mode
    meeting_link: HttpUrl | None = None
    location: str | None = Field(None, max_length=500)
    recruiter_notes: str | None = Field(None, max_length=5000)
    panels: list[PanelAssign] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Interview date and time must include a time zone")
        minutes = (self.ends_at - self.starts_at).total_seconds() / 60
        if minutes < 15 or minutes > 480:
            raise ValueError("Interview duration must be between 15 minutes and 8 hours")
        employee_ids = [x.employee_id for x in self.panels]
        if len(employee_ids) != len(set(employee_ids)):
            raise ValueError("An interviewer cannot appear twice on the panel")
        if sum(x.panel_role == "lead_interviewer" for x in self.panels) != 1:
            raise ValueError("Exactly one lead interviewer is required")
        if self.mode == "offline" and not self.location:
            raise ValueError("Offline interviews require a location")
        return self


class InterviewUpdate(BaseModel):
    interview_type: InterviewType | None = None
    interview_round: str | None = Field(None, min_length=1, max_length=100)
    mode: Mode | None = None
    meeting_link: HttpUrl | None = None
    location: str | None = None
    recruiter_notes: str | None = None


class RescheduleRequest(BaseModel):
    starts_at: datetime
    ends_at: datetime
    time_zone: str = Field(min_length=1, max_length=100)
    comments: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def valid_duration(self) -> Self:
        minutes = (self.ends_at - self.starts_at).total_seconds() / 60
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None or not 15 <= minutes <= 480:
            raise ValueError("Provide a timezone-aware slot between 15 minutes and 8 hours")
        return self


class CancelRequest(BaseModel):
    comments: str = Field(min_length=1, max_length=2000)


class ScoreInput(BaseModel):
    category: Literal[
        "technical_skills", "communication", "problem_solving", "domain_knowledge", "attitude", "culture_fit"
    ]
    score: int = Field(ge=1, le=10)
    comments: str | None = Field(None, max_length=2000)


class FeedbackCreate(BaseModel):
    interviewer_id: uuid.UUID
    scores: list[ScoreInput] = Field(min_length=6, max_length=6)
    overall_comments: str = Field(min_length=1, max_length=5000)
    recommendation: Recommendation

    @model_validator(mode="after")
    def all_categories_once(self) -> Self:
        categories = [x.category for x in self.scores]
        if len(set(categories)) != 6:
            raise ValueError("Every scorecard category must be submitted exactly once")
        return self


class DecisionRequest(BaseModel):
    decision: Literal["next_round", "reject", "hold", "shortlist", "final_selection"]
    target_stage_id: uuid.UUID | None = None
    comments: str = Field(min_length=1, max_length=2000)


class AttachmentLink(BaseModel):
    document_id: uuid.UUID
    attachment_kind: Literal["coding_test", "assignment", "notes", "evaluation_sheet"]


class PanelRead(PanelAssign):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str


class ScoreRead(ScoreInput):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    interviewer_id: uuid.UUID
    scores: list[ScoreRead]
    overall_comments: str
    recommendation: str
    submitted_at: datetime


class HistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    action: str
    previous_starts_at: datetime | None
    previous_ends_at: datetime | None
    new_starts_at: datetime | None
    new_ends_at: datetime | None
    comments: str | None
    created_at: datetime


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    document_id: uuid.UUID
    attachment_kind: str
    created_at: datetime


class InterviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    interview_code: str
    candidate_id: uuid.UUID
    job_opening_id: uuid.UUID
    interview_type: str
    interview_round: str
    starts_at: datetime
    ends_at: datetime
    time_zone: str
    mode: str
    meeting_link: str | None
    location: str | None
    recruiter_notes: str | None
    status: str
    overall_score: float | None
    overall_recommendation: str | None
    decision: str | None
    panels: list[PanelRead]
    feedback: list[FeedbackRead]
    history: list[HistoryRead]
    attachments: list[AttachmentRead]
    created_at: datetime


class InterviewListParams(PaginationParams):
    search: str | None = None
    candidate_id: uuid.UUID | None = None
    interviewer_id: uuid.UUID | None = None
    status: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class InterviewDashboard(BaseModel):
    todays_interviews: int
    upcoming_interviews: int
    completed_interviews: int
    cancelled_interviews: int
    pending_feedback: int
    average_score: float
    selection_ratio: float
    completion_rate: float
    candidate_status: list[dict[str, Any]]
    interviewer_workload: list[dict[str, Any]]
