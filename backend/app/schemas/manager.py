"""Manager and team-management request and response schemas.

Two properties shape this module, and both are about *whose* records a manager
screen is allowed to be about.

**No payload names a manager.** There is no ``manager_id`` field anywhere below.
The manager is the signed-in user, resolved from the access token, and their
team is derived from the reporting line -- so a caller cannot ask for somebody
else's team by supplying an id, in the same way a ``/me`` payload cannot ask for
somebody else's attendance.

**Employee ids appear only as filters, never as subjects.** ``employee_id`` on a
list params model narrows a query that is *already* narrowed to the caller's
direct reports; it can shrink the result set and never widen it. The one place
an employee id is the subject rather than a filter -- the team member profile --
takes it in the path and the service checks it against the reporting line before
reading anything.

The read models are projections. They deliberately reuse the owning modules'
read schemas (``AttendanceRead``, ``LeaveRequestRead``, ``TimesheetRead``) rather
than restating their fields, and pair each with the employee it belongs to,
because the one thing a team screen adds to a personal screen is "whose row is
this".

Sensitive personal data is absent by construction. :class:`TeamMember` and
:class:`TeamMemberProfile` carry no CTC, no bank detail, no statutory identifier
and no home address -- not masked, not filtered, simply not fields. Those live
on the HR employee record behind ``employees:view`` and its reveal endpoint,
which audits every access.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ApprovalStatus,
    AttendanceStatus,
    EmploymentStatus,
    TimesheetStatus,
)
from app.schemas.employee import EmployeeSummary
from app.schemas.masters import MasterSummary, SortOrder
from app.schemas.workforce import (
    AttendanceRead,
    LeaveRequestRead,
    RegularizationRead,
    TimesheetRead,
)

#: Every params model forbids unknown fields, so a filter this module does not
#: support is a 422 rather than a silently ignored narrowing -- which on a
#: security-scoped screen would read as "the filter worked".
MANAGER_MODEL_CONFIG = ConfigDict(extra="forbid")


# ----------------------------------------------------------------------
# Query parameters
#
# None of these carries a manager id. The team is resolved from the session's
# reporting line, which is what stops "show me a team" from becoming "show me
# any team".
# ----------------------------------------------------------------------
class ManagerPageParams(BaseModel):
    model_config = MANAGER_MODEL_CONFIG

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class TeamListParams(ManagerPageParams):
    """Filters for the team roster.

    ``project_id`` has no equivalent on ``EmployeeListParams`` -- an allocation
    is not a column on the employee -- so the service resolves it to a set of
    employee ids and intersects it with the team before the directory query
    runs. That ordering matters: the filter narrows an already-scoped set and
    can never reach outside it.
    """

    search: str | None = Field(
        default=None, max_length=150, description="Matches name, staff code or work email."
    )
    business_unit_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    work_location_id: uuid.UUID | None = None
    employment_type_id: uuid.UUID | None = None
    employment_status: EmploymentStatus | None = None
    project_id: uuid.UUID | None = Field(
        default=None, description="Only team members allocated to this project today."
    )
    sort_by: str = Field(default="employee_code", max_length=50)
    sort_order: SortOrder = SortOrder.ASC


class TeamAttendanceParams(ManagerPageParams):
    employee_id: uuid.UUID | None = Field(
        default=None,
        description="Narrow to one team member. Refused for anybody outside the team.",
    )
    status: AttendanceStatus | None = None
    from_date: date | None = None
    to_date: date | None = None


class TeamLeaveParams(ManagerPageParams):
    employee_id: uuid.UUID | None = None
    leave_type_id: uuid.UUID | None = None
    status: ApprovalStatus | None = None
    from_date: date | None = None
    to_date: date | None = None


class TeamTimesheetParams(ManagerPageParams):
    employee_id: uuid.UUID | None = None
    status: TimesheetStatus | None = None
    from_date: date | None = None
    to_date: date | None = None


class TeamRegularizationParams(ManagerPageParams):
    employee_id: uuid.UUID | None = None
    #: Defaults to the requests that need a decision, because that is what the
    #: screen exists for. The other states are still reachable by asking.
    status: ApprovalStatus | None = ApprovalStatus.PENDING


# ----------------------------------------------------------------------
# The team roster
# ----------------------------------------------------------------------
class TeamAllocation(BaseModel):
    """Where one team member's time is committed today."""

    project_id: uuid.UUID
    project_code: str
    project_name: str
    client_name: str | None = None
    allocation_percentage: Decimal
    billable: bool


class TeamMember(BaseModel):
    """One direct report, as the team list shows them.

    The placement fields are the *resolved* masters rather than bare ids, so a
    row renders without a lookup per cell. ``business_unit`` and ``team`` are
    what this platform calls the two levels of the organizational hierarchy;
    practices and departments were removed in migration 0012 and are not
    reintroduced here.
    """

    id: uuid.UUID
    employee_code: str
    full_name: str
    photo_url: str | None = None
    official_email: str
    employment_status: EmploymentStatus

    designation: MasterSummary | None = None
    business_unit: MasterSummary | None = None
    team: MasterSummary | None = None
    work_location: MasterSummary | None = None
    employment_type: MasterSummary | None = None

    allocations: list[TeamAllocation] = Field(default_factory=list)
    allocated_percentage: Decimal = Field(
        default=Decimal(0), description="Total of today's live allocations. Above 100 is over-committed."
    )

    attendance_status: AttendanceStatus | None = Field(
        default=None, description="Today's recorded status. Null when nothing has been recorded."
    )
    checked_in_at: datetime | None = None
    checked_out_at: datetime | None = None
    #: Non-null when an approved leave request covers today.
    on_leave_type: str | None = None


# ----------------------------------------------------------------------
# Summaries used on the profile and the dashboard
# ----------------------------------------------------------------------
class TeamAttendanceSummary(BaseModel):
    """Attendance totals for one person over a window."""

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


class TeamLeaveBalance(BaseModel):
    """One leave type's position for one team member."""

    leave_type_id: uuid.UUID
    leave_type_name: str
    year: int
    allocated: Decimal
    used: Decimal
    pending: Decimal
    available: Decimal


class TeamTimesheetSummary(BaseModel):
    draft: int
    submitted: int
    approved: int
    rejected: int
    total_hours: Decimal
    billable_hours: Decimal


# ----------------------------------------------------------------------
# Rows: a module's own record, paired with whose it is
# ----------------------------------------------------------------------
class TeamAttendanceRow(BaseModel):
    employee: EmployeeSummary
    record: AttendanceRead


class TeamLeaveRow(BaseModel):
    employee: EmployeeSummary
    request: LeaveRequestRead


class TeamTimesheetRow(BaseModel):
    employee: EmployeeSummary
    timesheet: TimesheetRead


class TeamRegularizationRow(BaseModel):
    employee: EmployeeSummary
    request: RegularizationRead


# ----------------------------------------------------------------------
# Projects
# ----------------------------------------------------------------------
class TeamProjectMember(BaseModel):
    employee: EmployeeSummary
    allocation_percentage: Decimal
    billable: bool
    start_date: date
    end_date: date | None = None


class TeamProject(BaseModel):
    """A project seen through the manager's team.

    ``team_size`` counts the manager's own people on it, not everybody on the
    project: this screen answers "where is my team working", and a headline
    figure that included other teams' people would be read as though it did not.
    """

    project_id: uuid.UUID
    project_code: str
    project_name: str
    client_name: str | None = None
    status: str
    start_date: date
    end_date: date | None = None
    team_size: int
    total_allocation: Decimal
    billable_percentage: int
    members: list[TeamProjectMember]


class TeamAllocationSummary(BaseModel):
    """How committed the team is, in one line."""

    allocated_members: int
    unallocated_members: int
    average_allocation: int = Field(description="Mean allocation across allocated members, as a percentage.")
    billable_members: int
    active_projects: int


# ----------------------------------------------------------------------
# Performance
# ----------------------------------------------------------------------
class TeamPerformance(BaseModel):
    """One team member's standing in the current cycle.

    Every figure is read from the Performance Management module. Nothing here
    is computed a second way: ``goal_progress`` is the weighted completion that
    module already reports, and the review statuses are its own.
    """

    employee: EmployeeSummary
    cycle_id: uuid.UUID | None = None
    cycle_name: str | None = None
    goals: int
    goals_completed: int
    goal_progress: int = Field(description="Weighted completion across live goals, as a percentage.")
    self_review_status: str | None = None
    manager_review_status: str | None = None
    current_rating: int | None = Field(
        default=None, description="The final rating when one exists, otherwise the manager's."
    )
    review_due: bool = Field(
        description="True when the self review is in and the manager review is not -- the manager's move."
    )


class TeamMemberProfile(BaseModel):
    """One team member's record, as their manager may see it.

    Deliberately not :class:`~app.schemas.employee.EmployeeRead`. That model
    carries CTC, bank details, statutory identifiers and home addresses, and a
    manager's need to see who is on their team is not a reason to hand them
    those. Anyone who does need them reaches the employee module, which is
    guarded separately and audits the reveal.

    Declared here rather than beside :class:`TeamMember` because it composes
    four models defined above it, and a forward reference that Pydantic has to
    rebuild is a cost paid on every schema generation for no reading benefit.
    """

    member: TeamMember
    joining_date: date
    confirmation_date: date | None = None
    reporting_manager: EmployeeSummary | None = None
    work_mode: str | None = None

    attendance: TeamAttendanceSummary
    leave: list[TeamLeaveBalance]
    timesheets: TeamTimesheetSummary
    performance: TeamPerformance | None = None


# ----------------------------------------------------------------------
# Calendar
# ----------------------------------------------------------------------
class TeamCalendarEntry(BaseModel):
    """One dated thing on the team calendar.

    A single shape for four kinds of entry -- leave, holiday, attendance
    exception, joining date -- because the calendar renders them as one stream
    and four parallel lists would have to be merged and sorted by the client
    anyway.
    """

    day: date
    kind: str = Field(description="leave, holiday, exception or joining.")
    label: str
    employee_id: uuid.UUID | None = None
    employee_name: str | None = None
    detail: str | None = None


class TeamCalendar(BaseModel):
    year: int
    month: int
    entries: list[TeamCalendarEntry]


# ----------------------------------------------------------------------
# Document completion
# ----------------------------------------------------------------------
class TeamDocumentStatus(BaseModel):
    """Counts only. No name, no classification, no file.

    §12 of the brief asks for completion status without exposing the documents
    themselves, and counts are the whole of what this returns -- an Aadhaar
    scan and a signed policy are indistinguishable in it.
    """

    employee: EmployeeSummary
    total: int
    approved: int
    pending: int
    rejected: int


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------
class TeamHoliday(BaseModel):
    id: uuid.UUID
    name: str
    holiday_date: date
    holiday_type: str
    calendar_name: str


class ManagerDashboard(BaseModel):
    """The manager's home screen. Every figure is about their direct reports.

    There is deliberately no headcount, no company attendance percentage and no
    organization-wide pending count. Those exist on the workforce dashboard,
    which is guarded and scoped for the people entitled to them; repeating them
    here would make it impossible to tell at a glance whether a number on this
    screen is about the team.
    """

    manager: EmployeeSummary
    on_date: date

    team_size: int
    present_today: int
    absent_today: int
    on_leave_today: int
    not_recorded_today: int = Field(description="Team members with no attendance row for today at all.")

    pending_leave_approvals: int
    pending_timesheet_approvals: int
    pending_regularizations: int
    pending_performance_reviews: int

    upcoming_holidays: list[TeamHoliday]
    active_projects: int
    allocation: TeamAllocationSummary

    #: The few rows behind the counts, so the dashboard can show what is waiting
    #: rather than only how much of it there is.
    leave_awaiting_decision: list[TeamLeaveRow]
    timesheets_awaiting_decision: list[TeamTimesheetRow]
    regularizations_awaiting_decision: list[TeamRegularizationRow]


__all__ = [
    "ManagerDashboard",
    "ManagerPageParams",
    "TeamAllocation",
    "TeamAllocationSummary",
    "TeamAttendanceParams",
    "TeamAttendanceRow",
    "TeamAttendanceSummary",
    "TeamCalendar",
    "TeamCalendarEntry",
    "TeamDocumentStatus",
    "TeamHoliday",
    "TeamLeaveBalance",
    "TeamLeaveParams",
    "TeamLeaveRow",
    "TeamListParams",
    "TeamMember",
    "TeamMemberProfile",
    "TeamPerformance",
    "TeamProject",
    "TeamProjectMember",
    "TeamRegularizationParams",
    "TeamRegularizationRow",
    "TeamTimesheetParams",
    "TeamTimesheetRow",
    "TeamTimesheetSummary",
]
