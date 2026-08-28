"""Employee self-service request and response schemas.

Two things separate this module from the ones it presents.

**No payload here carries an employee id.** Not "it is ignored" or "it is
overwritten" -- the field does not exist on the models, so a client cannot send
one and no future edit to a route can accidentally start honouring it. The
subject of every ``/me`` request is resolved from the access token.

**The write model is the smallest thing that works.** :class:`MyProfileUpdate`
lists exactly the fields an employee owns. Everything else about their
employment -- team, designation, grade, manager, joining date, status -- is
absent from the schema rather than rejected by a check, which is the same
reason ``ProfileUpdate`` exists alongside ``UserUpdate`` on ``users``.

The read models are projections assembled by the service. They are deliberately
*not* the HR read models: an employee looking at their own record has no use for
`ctc`, `notes` or the audit columns, and a schema that omits a field cannot leak
it by forgetting to.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import (
    ApprovalStatus,
    AttendanceStatus,
    DocumentStatus,
    TimesheetStatus,
)
from app.schemas.announcement import MyAnnouncement
from app.schemas.document import DocumentOwnerRef, DocumentRead
from app.schemas.employee import (
    EmployeeAddressRead,
    EmployeeOrganization,
    EmployeeSummary,
    Relationship,
    ShortText,
)
from app.schemas.masters import normalise_optional_text
from app.schemas.user import MobileNumber, PhotoUrl
from app.schemas.workforce import (
    AttendanceRead,
    LeaveRequestRead,
    LeaveTypeRead,
    TimesheetRead,
)
from app.utils.strings import normalise_email

SELF_SERVICE_MODEL_CONFIG = ConfigDict(str_strip_whitespace=True, extra="forbid")
READ_CONFIG = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# Profile
# ----------------------------------------------------------------------
class MyProfileUpdate(BaseModel):
    """What an employee may change about themselves.

    Six fields. Everything an employer decides -- where you sit, what you are
    called, what you are paid, who you report to -- is not on this model, so a
    request cannot carry it whatever the caller puts in the body: ``extra`` is
    forbidden, so an attempt is a 422 rather than a silently dropped field.
    """

    model_config = SELF_SERVICE_MODEL_CONFIG

    photo_url: PhotoUrl = None
    personal_email: EmailStr | None = None
    mobile_number: MobileNumber = None
    alternate_number: MobileNumber = None
    emergency_contact_name: ShortText = None
    emergency_contact_number: MobileNumber = None
    emergency_contact_relationship: Relationship = None

    @field_validator("personal_email")
    @classmethod
    def _normalise_personal_email(cls, value: str | None) -> str | None:
        return normalise_email(value) if value else None


class MyProfileRead(BaseModel):
    """An employee's own record, as the portal shows it.

    The system-controlled block is present and read-only rather than hidden:
    people need to see which team they are recorded against in order to notice
    that it is wrong, and hiding it would only move that discovery to payroll.
    """

    model_config = READ_CONFIG

    id: uuid.UUID
    employee_code: str

    first_name: str
    last_name: str
    full_name: str

    # -- Editable ------------------------------------------------------
    photo_url: str | None = None
    personal_email: EmailStr | None = None
    mobile_number: str | None = None
    alternate_number: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_number: str | None = None
    emergency_contact_relationship: str | None = None
    addresses: list[EmployeeAddressRead] = Field(default_factory=list)

    # -- System controlled ---------------------------------------------
    official_email: EmailStr
    official_mobile: str | None = None
    extension_number: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    blood_group: str | None = None
    marital_status: str | None = None
    nationality: str | None = None
    joining_date: date
    confirmation_date: date | None = None
    employment_status: str
    work_mode: str | None = None
    organization: EmployeeOrganization
    reporting_manager: EmployeeSummary | None = None

    #: Named on the response rather than assumed by the client, so the form can
    #: disable exactly what the server will refuse and the two cannot drift.
    editable_fields: list[str] = Field(
        description="The fields PATCH /me/profile accepts. Everything else is read-only."
    )

    @classmethod
    def from_employee(cls, employee: Any) -> MyProfileRead:
        data: dict[str, Any] = {
            name: getattr(employee, name) for name in cls.model_fields if hasattr(employee, name)
        }
        data["organization"] = EmployeeOrganization.model_validate(employee)
        data["editable_fields"] = sorted(MyProfileUpdate.model_fields)
        return cls.model_validate(data)


# The address an employee edits is the same address HR edits, so it reuses
# ``EmployeeAddressInput`` rather than declaring a parallel model whose
# validation could drift from it. There is no self-service-only address rule.


# ----------------------------------------------------------------------
# Attendance
# ----------------------------------------------------------------------
class MyCheckIn(BaseModel):
    """Checking in. No date: you check in now, on the day it is now."""

    model_config = SELF_SERVICE_MODEL_CONFIG

    work_mode: str = Field(default="office", pattern="^(office|remote|hybrid|client_site)$")
    notes: str | None = Field(default=None, max_length=1000)


class MyCheckOut(BaseModel):
    model_config = SELF_SERVICE_MODEL_CONFIG

    notes: str | None = Field(default=None, max_length=1000)


class MyAttendanceToday(BaseModel):
    """The state the check-in / check-out control renders from.

    ``elapsed_minutes`` is sent alongside the raw timestamps rather than instead
    of them: the client runs the ticking timer, and it needs a server-anchored
    starting point or every browser with a skewed clock shows a different
    number.
    """

    on_date: date
    record: AttendanceRead | None = None
    checked_in: bool
    checked_out: bool
    can_check_in: bool
    can_check_out: bool
    status: AttendanceStatus | None = None
    worked_minutes: int = 0
    elapsed_minutes: int = Field(
        default=0, description="Minutes since check-in for a day still open; 0 once checked out."
    )
    server_time: datetime


class MyAttendanceSummary(BaseModel):
    """Totals for a window, counted from the same rows the register shows."""

    from_date: date
    to_date: date
    present_days: int
    absent_days: int
    leave_days: int
    half_days: int
    late_arrivals: int
    early_exits: int
    worked_minutes: int
    overtime_minutes: int


# A correction request, a leave application and a saved week are the workforce
# module's own payloads -- ``RegularizationCreate``, ``LeaveApply`` and
# ``TimesheetSave`` -- and the portal posts them unchanged. None of the three
# carries an employee id, so there is nothing to strip and nothing to redeclare;
# a parallel model here would be a second copy of rules like "a half day applies
# to a single date" waiting to disagree with the first.


# ----------------------------------------------------------------------
# Leave
# ----------------------------------------------------------------------
class MyLeaveBalance(BaseModel):
    """One leave type's entitlement, in the five figures an employee asks about.

    ``accrued`` is opening balance plus this year's allocation -- everything
    credited to the employee so far. The platform credits the full annual
    entitlement when the balance row is first read rather than accruing it
    month by month, so on today's data ``accrued`` and ``allocated`` differ only
    by days carried forward. It is surfaced as its own figure because that is
    the number people are shown elsewhere, and because a proportional accrual
    engine changes what fills it without changing this contract.
    """

    leave_type_id: uuid.UUID
    leave_type: LeaveTypeRead | None = None
    year: int
    allocated: Decimal
    accrued: Decimal
    used: Decimal
    pending: Decimal
    available: Decimal
    is_paid: bool
    requires_document: bool


# ----------------------------------------------------------------------
# Projects
# ----------------------------------------------------------------------
class MyProject(BaseModel):
    """An allocation as the person allocated sees it. Read-only by construction.

    Defined before the timesheet models because the week carries the list: a
    picker that offers a project the save endpoint will refuse is worse than no
    picker at all.
    """

    allocation_id: uuid.UUID
    project_id: uuid.UUID
    project_code: str
    project_name: str
    client_name: str | None = None
    role: str | None = None
    allocation_percentage: Decimal
    start_date: date
    end_date: date | None = None
    billable: bool
    status: str
    is_current: bool = Field(description="True when today falls inside the allocation window.")


# ----------------------------------------------------------------------
# Timesheets
# ----------------------------------------------------------------------
class MyTimesheetWeek(BaseModel):
    """The current week's grid, with the projects that may appear in it.

    The allocations travel with the timesheet because the picker cannot be built
    without them, and because sending the whole project list would offer
    projects the save endpoint will refuse.
    """

    week_start_date: date
    timesheet: TimesheetRead | None = None
    editable: bool = Field(description="False once submitted or approved.")
    projects: list[MyProject]


# ----------------------------------------------------------------------
# Holidays and documents
# ----------------------------------------------------------------------
class MyHoliday(BaseModel):
    """A holiday that applies where this employee works."""

    id: uuid.UUID
    name: str
    holiday_date: date
    holiday_type: str
    calendar_name: str
    is_past: bool


class MyDocument(DocumentRead):
    """A vault document plus the one thing the portal has to decide.

    ``can_replace`` is the answer to "may I upload a new version of this?", and
    it is false for anything HR issued. An offer letter is the employee's to
    read and to keep, and not theirs to reissue.
    """

    can_replace: bool = Field(description="True only for documents this employee uploaded themselves.")

    @classmethod
    def build(cls, document: Any, *, owner: DocumentOwnerRef | None, can_replace: bool) -> MyDocument:
        base = DocumentRead.from_document(document, owner=owner)
        return cls(**base.model_dump(), can_replace=can_replace)


class MyDocumentUpload(BaseModel):
    """The metadata parts of a personal upload.

    No ``owner_type`` and no ``owner_id``: the vault files it against the person
    who sent it, which is the whole point of the endpoint.
    """

    model_config = SELF_SERVICE_MODEL_CONFIG

    name: Annotated[str, Field(min_length=2, max_length=200)]
    category_id: uuid.UUID
    document_type_id: uuid.UUID
    description: Annotated[
        str | None, Field(default=None, max_length=2000), AfterValidator(normalise_optional_text)
    ] = None
    expiry_date: date | None = None


class MyDocumentType(BaseModel):
    """A type an employee may file something under, with its category."""

    model_config = READ_CONFIG

    id: uuid.UUID
    name: str
    code: str | None = None
    category_id: uuid.UUID
    category_name: str
    requires_expiry: bool
    allowed_extensions: str | None = None


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------
class PendingAction(BaseModel):
    """Something waiting on the employee, not on somebody else.

    Deliberately not "notifications": a notification says what happened, this
    says what is still theirs to do, and mixing the two produces a list nobody
    can finish.
    """

    code: str
    label: str
    detail: str | None = None
    link: str


class MyNotification(BaseModel):
    """An entry from the existing in-app inbox, unchanged."""

    model_config = READ_CONFIG

    id: uuid.UUID
    title: str
    message: str
    link: str | None = None
    notification_type: str
    is_read: bool
    created_at: datetime


class MyDocumentSummary(BaseModel):
    total: int
    pending_review: int
    approved: int
    rejected: int
    expiring_soon: int


class MyDashboard(BaseModel):
    """Everything the employee's home screen shows -- and nothing about anybody else.

    Assembled server-side rather than by eight client requests: the screen is
    the first thing a person sees after signing in, and eight round trips is
    eight chances for one of them to be the slow one.
    """

    employee: EmployeeSummary
    on_date: date
    attendance: MyAttendanceToday
    month_summary: MyAttendanceSummary
    leave_balances: list[MyLeaveBalance]
    pending_leave: list[LeaveRequestRead]
    upcoming_holidays: list[MyHoliday]
    current_timesheet: TimesheetRead | None = None
    current_week_start: date
    projects: list[MyProject]
    documents: MyDocumentSummary
    recent_documents: list[MyDocument]
    pending_actions: list[PendingAction]
    #: Real announcements, addressed to this employee's business unit, team,
    #: location or to everybody. Published only, and in their window.
    #:
    #: This used to be the notification inbox, with a comment saying the
    #: platform had no announcements table and that inventing one would be a
    #: second message system. There is one now, and it is not a second message
    #: system: publishing an announcement still delivers through the inbox --
    #: the announcement is the durable thing the notification points at.
    recent_announcements: list[MyAnnouncement]
    #: The inbox itself, under its own name. A notification is personal and
    #: disposable; an announcement is the same text for everybody it reaches.
    recent_notifications: list[MyNotification]


# ----------------------------------------------------------------------
# Query parameters
#
# None of these carry an employee id. The service supplies it from the session,
# which is what stops "filter by employee" from becoming "read any employee".
# ----------------------------------------------------------------------
class MyPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class MyAttendanceParams(MyPageParams):
    status: AttendanceStatus | None = None
    from_date: date | None = None
    to_date: date | None = None


class MyLeaveParams(MyPageParams):
    leave_type_id: uuid.UUID | None = None
    status: ApprovalStatus | None = None
    from_date: date | None = None
    to_date: date | None = None


class MyTimesheetParams(MyPageParams):
    status: TimesheetStatus | None = None
    from_date: date | None = None
    to_date: date | None = None


class MyRegularizationParams(MyPageParams):
    status: ApprovalStatus | None = None


class MyDocumentParams(MyPageParams):
    status: DocumentStatus | None = None
    category_id: uuid.UUID | None = None
    search: str | None = Field(default=None, max_length=150)


__all__ = [
    "MyAttendanceParams",
    "MyAttendanceSummary",
    "MyAttendanceToday",
    "MyCheckIn",
    "MyCheckOut",
    "MyDashboard",
    "MyDocument",
    "MyDocumentParams",
    "MyDocumentSummary",
    "MyDocumentType",
    "MyDocumentUpload",
    "MyHoliday",
    "MyLeaveBalance",
    "MyLeaveParams",
    "MyNotification",
    "MyPageParams",
    "MyProfileRead",
    "MyProfileUpdate",
    "MyProject",
    "MyRegularizationParams",
    "MyTimesheetParams",
    "MyTimesheetWeek",
]
