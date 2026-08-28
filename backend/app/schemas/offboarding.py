"""Resignation and offboarding schemas.

Two properties shape this module, and both are security properties rather than
conveniences.

**No write schema carries an employee id.** Not the resignation an employee
submits, not the exit interview they complete. The employee is resolved from the
access token, so an IDOR on the *submission* path is a thing that cannot be
written rather than a thing somebody must remember to check. The read schemas
name the employee because a manager and an HR user legitimately need to know
whose separation they are looking at.

**Employee-facing and administrative views are separate models.**
:class:`MyResignation` tells an employee where their own request has got to;
:class:`ResignationRead` tells HR who decided what and when. They are not the
same object with fields hidden, because a schema that never declares
``hr_comments`` cannot leak it by forgetting to -- the same rule the employee
portal and the HR module already follow.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    AccessClearanceStatus,
    AssetReturnStatus,
    ExitDocumentType,
    HandoverStatus,
    OffboardingCaseStatus,
    OffboardingDepartment,
    OffboardingTaskStatus,
    ResignationStatus,
    SettlementStatus,
)
from app.schemas.common import PaginationParams

_MAX_COMMENT = 4000


# ----------------------------------------------------------------------
# Employee: submitting and tracking a resignation
# ----------------------------------------------------------------------
class ResignationSubmit(BaseModel):
    """What an employee sends. Deliberately has no ``employee_id``."""

    resignation_date: date
    proposed_last_working_day: date
    reason: str = Field(min_length=3, max_length=100)
    comments: str | None = Field(default=None, max_length=_MAX_COMMENT)
    supporting_document_id: uuid.UUID | None = Field(
        default=None,
        description="An existing Document Vault document. The file is never uploaded here.",
    )

    @model_validator(mode="after")
    def dates_are_ordered(self) -> Self:
        if self.proposed_last_working_day < self.resignation_date:
            raise ValueError("The proposed last working day cannot be before the resignation date")
        return self


class ResignationWithdraw(BaseModel):
    comments: str | None = Field(default=None, max_length=_MAX_COMMENT)


class NoticePeriodView(BaseModel):
    """Everything §6 asks a screen to display, computed on the server."""

    resignation_date: date
    notice_period_days: int
    expected_last_working_day: date = Field(
        description="Resignation date plus the notice period. What the policy implies."
    )
    proposed_last_working_day: date
    approved_last_working_day: date | None
    remaining_days: int = Field(
        description="Calendar days from today to the effective last working day. Never negative."
    )
    notice_served_days: int
    notice_status: str = Field(description="not_started, serving, completed or waived.")
    notice_period_adjusted: bool


class ResignationHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    from_status: str | None
    to_status: str | None
    comments: str | None
    is_override: bool
    created_at: datetime


class MyResignation(BaseModel):
    """The employee's own view. Carries no HR commentary and no owner ids."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resignation_code: str
    status: ResignationStatus
    resignation_date: date
    proposed_last_working_day: date
    approved_last_working_day: date | None
    reason: str
    comments: str | None
    supporting_document_id: uuid.UUID | None
    submitted_at: datetime | None
    manager_comments: str | None = Field(
        default=None, description="Shown to the employee: a decision they are entitled to the reason for."
    )
    can_withdraw: bool
    notice: NoticePeriodView | None
    history: list[ResignationHistoryEntry] = []


class MyPendingAction(BaseModel):
    """One thing the employee still has to do, and where to do it."""

    key: str
    label: str
    link: str


# ----------------------------------------------------------------------
# Manager and HR: the administrative view
# ----------------------------------------------------------------------
class EmployeeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    full_name: str
    designation: str | None = None
    team: str | None = None


class ResignationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resignation_code: str
    employee: EmployeeSummary
    status: ResignationStatus
    resignation_date: date
    proposed_last_working_day: date
    recommended_last_working_day: date | None
    approved_last_working_day: date | None
    notice_period_days: int
    notice_period_adjusted: bool
    reason: str
    comments: str | None
    supporting_document_id: uuid.UUID | None
    submitted_at: datetime | None
    manager_id: uuid.UUID | None
    manager_decided_at: datetime | None
    manager_comments: str | None
    hr_owner_id: uuid.UUID | None
    hr_processed_at: datetime | None
    hr_comments: str | None
    case_id: uuid.UUID | None = None
    notice: NoticePeriodView | None = None
    history: list[ResignationHistoryEntry] = []


class ResignationListParams(PaginationParams):
    status: ResignationStatus | None = None
    employee_id: uuid.UUID | None = Field(
        default=None,
        description="Narrow to one employee. Still subject to the caller's scope -- "
        "supplying an id never widens what is returned.",
    )
    search: str | None = Field(default=None, max_length=100)
    from_date: date | None = None
    to_date: date | None = None


class ManagerDecision(BaseModel):
    """Approve or reject. The manager may recommend a different last working day."""

    decision: str = Field(pattern="^(approve|reject)$")
    comments: str | None = Field(default=None, max_length=_MAX_COMMENT)
    recommended_last_working_day: date | None = None


class HrProcess(BaseModel):
    """HR's step: settle the last working day and open the case."""

    approved_last_working_day: date | None = Field(
        default=None,
        description="Defaults to the manager's recommendation, then the employee's proposal.",
    )
    notice_period_days: int | None = Field(
        default=None,
        ge=0,
        le=365,
        description="An authorized adjustment. Recorded in history with the reason when it differs "
        "from the configured period.",
    )
    adjustment_reason: str | None = Field(default=None, max_length=_MAX_COMMENT)
    comments: str | None = Field(default=None, max_length=_MAX_COMMENT)


class LastWorkingDayChange(BaseModel):
    approved_last_working_day: date
    reason: str = Field(min_length=3, max_length=_MAX_COMMENT)


class ResignationCancel(BaseModel):
    reason: str = Field(min_length=3, max_length=_MAX_COMMENT)


# ----------------------------------------------------------------------
# Offboarding case
# ----------------------------------------------------------------------
class OffboardingTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    department: OffboardingDepartment
    owner_id: uuid.UUID | None
    due_date: date
    status: OffboardingTaskStatus
    comments: str | None
    completed_at: datetime | None
    sequence: int


class OffboardingTaskUpdate(BaseModel):
    status: OffboardingTaskStatus | None = None
    comments: str | None = Field(default=None, max_length=_MAX_COMMENT)
    due_date: date | None = None
    owner_id: uuid.UUID | None = Field(default=None, description="Reassignment. Requires offboarding:manage.")


class OffboardingTaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    department: OffboardingDepartment
    owner_id: uuid.UUID | None = None
    due_date: date


class AssetClearanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_name: str
    asset_tag: str | None
    assigned_date: date | None
    return_date: date | None
    condition: str | None
    status: AssetReturnStatus
    comments: str | None


class AssetClearanceInput(BaseModel):
    asset_name: str = Field(min_length=1, max_length=150)
    asset_tag: str | None = Field(default=None, max_length=100)
    assigned_date: date | None = None
    condition: str | None = Field(default=None, max_length=100)
    comments: str | None = Field(default=None, max_length=_MAX_COMMENT)


class AssetClearanceUpdate(BaseModel):
    status: AssetReturnStatus
    return_date: date | None = None
    condition: str | None = Field(default=None, max_length=100)
    comments: str | None = Field(default=None, max_length=_MAX_COMMENT)


class AccessClearanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    system_name: str
    category: str | None
    status: AccessClearanceStatus
    revoked_at: datetime | None
    comments: str | None


class AccessClearanceInput(BaseModel):
    system_name: str = Field(min_length=1, max_length=150)
    category: str | None = Field(default=None, max_length=50)
    comments: str | None = Field(default=None, max_length=_MAX_COMMENT)


class AccessClearanceUpdate(BaseModel):
    status: AccessClearanceStatus
    comments: str | None = Field(default=None, max_length=_MAX_COMMENT)


class HandoverRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: HandoverStatus
    projects: str | None
    responsibilities: str | None
    documentation: str | None
    replacement_employee_id: uuid.UUID | None
    notes: str | None
    attachment_ids: list[uuid.UUID] = []
    completed_at: datetime | None


class HandoverInput(BaseModel):
    status: HandoverStatus = HandoverStatus.IN_PROGRESS
    projects: str | None = Field(default=None, max_length=_MAX_COMMENT)
    responsibilities: str | None = Field(default=None, max_length=_MAX_COMMENT)
    documentation: str | None = Field(default=None, max_length=_MAX_COMMENT)
    replacement_employee_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=_MAX_COMMENT)
    attachment_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Existing Document Vault ids. Files are uploaded to the vault, not here.",
    )


class SettlementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: SettlementStatus
    settlement_reference: str | None
    settlement_date: date | None
    comments: str | None


class SettlementUpdate(BaseModel):
    """Status tracking only -- see :class:`app.models.enums.SettlementStatus`."""

    status: SettlementStatus
    settlement_reference: str | None = Field(default=None, max_length=100)
    settlement_date: date | None = None
    comments: str | None = Field(default=None, max_length=_MAX_COMMENT)


class ExitDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_type: ExitDocumentType
    document_id: uuid.UUID | None
    issued_at: datetime | None
    released: bool


class ExitDocumentGenerate(BaseModel):
    document_type: ExitDocumentType
    release: bool = Field(
        default=False, description="Release to the employee immediately rather than only generating."
    )


class ClearanceProgress(BaseModel):
    """One number per strand, so a screen can show where a case is stuck."""

    tasks_total: int
    tasks_settled: int
    assets_total: int
    assets_settled: int
    access_total: int
    access_settled: int
    percent: int
    outstanding_departments: list[OffboardingDepartment] = []


class OffboardingCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_code: str
    employee: EmployeeSummary
    resignation_id: uuid.UUID
    resignation_code: str | None = None
    resignation_status: ResignationStatus | None = None
    last_working_day: date
    notice_period_days: int
    hr_owner_id: uuid.UUID | None
    manager_id: uuid.UUID | None
    status: OffboardingCaseStatus
    progress_percent: int
    created_at: datetime
    completed_at: datetime | None

    tasks: list[OffboardingTaskRead] = []
    assets: list[AssetClearanceRead] = []
    access_items: list[AccessClearanceRead] = []
    handover: HandoverRead | None = None
    settlement: SettlementRead | None = None
    exit_documents: list[ExitDocumentRead] = []
    exit_interview_submitted: bool = False
    clearance: ClearanceProgress | None = None
    notice: NoticePeriodView | None = None


class OffboardingListParams(PaginationParams):
    status: OffboardingCaseStatus | None = None
    employee_id: uuid.UUID | None = None
    search: str | None = Field(default=None, max_length=100)
    exiting_before: date | None = None
    pending_clearance: bool | None = Field(
        default=None, description="Only cases with outstanding tasks, assets or access."
    )


class CaseCompletion(BaseModel):
    comments: str | None = Field(default=None, max_length=_MAX_COMMENT)
    force: bool = Field(
        default=False,
        description="Complete despite outstanding clearance. An authorized override; audited as one "
        "and refused without offboarding:manage.",
    )


# ----------------------------------------------------------------------
# Exit interview
# ----------------------------------------------------------------------
_RATING = Field(default=None, ge=1, le=5)


class ExitInterviewSubmit(BaseModel):
    """Completed by the employee. Carries no employee id, by construction."""

    reason_for_leaving: str = Field(min_length=3, max_length=100)
    overall_experience: int | None = _RATING
    management_rating: int | None = _RATING
    work_environment_rating: int | None = _RATING
    career_growth_rating: int | None = _RATING
    compensation_rating: int | None = _RATING
    management_feedback: str | None = Field(default=None, max_length=_MAX_COMMENT)
    work_environment_feedback: str | None = Field(default=None, max_length=_MAX_COMMENT)
    career_growth_feedback: str | None = Field(default=None, max_length=_MAX_COMMENT)
    compensation_feedback: str | None = Field(default=None, max_length=_MAX_COMMENT)
    suggestions: str | None = Field(default=None, max_length=_MAX_COMMENT)
    would_recommend: bool | None = None
    would_rejoin: bool | None = None


class ExitInterviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    employee_id: uuid.UUID
    reason_for_leaving: str
    overall_experience: int | None
    management_rating: int | None
    work_environment_rating: int | None
    career_growth_rating: int | None
    compensation_rating: int | None
    management_feedback: str | None
    work_environment_feedback: str | None
    career_growth_feedback: str | None
    compensation_feedback: str | None
    suggestions: str | None
    would_recommend: bool | None
    would_rejoin: bool | None
    submitted_at: datetime | None


class ExitInterviewListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    employee: EmployeeSummary
    reason_for_leaving: str
    overall_experience: int | None
    would_recommend: bool | None
    would_rejoin: bool | None
    submitted_at: datetime | None


# ----------------------------------------------------------------------
# Dashboards
# ----------------------------------------------------------------------
class MyOffboarding(BaseModel):
    """`/me/offboarding` -- one employee's own separation, and nothing else."""

    resignation: MyResignation | None
    case_code: str | None
    last_working_day: date | None
    case_status: OffboardingCaseStatus | None
    clearance: ClearanceProgress | None
    my_tasks: list[OffboardingTaskRead] = []
    pending_actions: list[MyPendingAction] = []
    exit_interview_submitted: bool = False
    exit_interview_available: bool = False
    exit_documents: list[ExitDocumentRead] = []
    settlement_status: SettlementStatus | None = None


class OffboardingSummary(BaseModel):
    """The counters a manager or HR dashboard opens with."""

    active_resignations: int
    pending_manager_review: int
    pending_hr_review: int
    serving_notice: int
    exiting_this_month: int
    pending_clearance: int
    exit_interviews_pending: int
    exit_documents_pending: int
    settlement_pending: int


class ManagerOffboardingRow(BaseModel):
    """One departing direct report, with what the manager still owes."""

    model_config = ConfigDict(from_attributes=True)

    resignation_id: uuid.UUID
    case_id: uuid.UUID | None
    employee: EmployeeSummary
    status: ResignationStatus
    last_working_day: date | None
    remaining_days: int | None
    handover_status: HandoverStatus | None
    pending_task_count: int
