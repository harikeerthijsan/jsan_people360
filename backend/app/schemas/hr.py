"""HR dashboard and administration schemas.

Three properties shape this module.

**Every section is optional, and absence means "not permitted".** The HR
dashboard is not one screen with one audience: an HR Executive holds a different
set of permissions from an HR Admin, and both differ from an Administrator. So
:class:`HrDashboard` carries each section as a nullable block, the service fills
in only the ones the caller may see, and ``sections`` names what came back. A
client renders what it was given rather than deciding for itself what to ask
for, and the two can never disagree about who may see the recruitment figures.

**No payload here confers access.** There is no "as this employee" field and no
role name anywhere. Which records an HR screen returns is decided by the
caller's :class:`~app.services.scope_service.EmployeeScope`, and what they may
do is decided by the permission guards on the route.

**The HR employee view is a projection, not the employee record.**
:class:`HrEmployeeRow` and :class:`HrEmployeeProfile` carry what HR operations
need -- placement, contact, status, summaries. CTC, bank details and statutory
identifiers are absent by construction, not masked: they live on
``EmployeeRead`` behind ``employees:view`` and the audited reveal endpoint, and
a schema that never declares a field cannot leak it by forgetting to.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ApprovalStatus,
    AttendanceStatus,
    DocumentStatus,
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

HR_MODEL_CONFIG = ConfigDict(extra="forbid")


class CountByLabel(BaseModel):
    label: str
    count: int


class TrendPoint(BaseModel):
    """One period on a trend line, keyed by an ISO month so it sorts as text."""

    period: str = Field(description="ISO month, e.g. 2026-08.")
    label: str
    count: int


# ----------------------------------------------------------------------
# Query parameters
# ----------------------------------------------------------------------
class HrPageParams(BaseModel):
    model_config = HR_MODEL_CONFIG

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class HrEmployeeParams(HrPageParams):
    """Filters for the HR directory.

    "Department" and "Practice" are not fields on this platform: migration 0012
    removed both levels, leaving Business Unit -> Team. Those are the two
    offered, and the HR screen labels them accordingly.
    """

    search: str | None = Field(default=None, max_length=150)
    business_unit_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    work_location_id: uuid.UUID | None = None
    employment_type_id: uuid.UUID | None = None
    reporting_manager_id: uuid.UUID | None = None
    employment_status: EmploymentStatus | None = None
    joined_from: date | None = None
    joined_to: date | None = None
    sort_by: str = Field(default="employee_code", max_length=50)
    sort_order: SortOrder = SortOrder.ASC


class HrAttendanceParams(HrPageParams):
    employee_id: uuid.UUID | None = None
    business_unit_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    work_location_id: uuid.UUID | None = None
    reporting_manager_id: uuid.UUID | None = None
    status: AttendanceStatus | None = None
    from_date: date | None = None
    to_date: date | None = None


class HrLeaveParams(HrPageParams):
    employee_id: uuid.UUID | None = None
    leave_type_id: uuid.UUID | None = None
    status: ApprovalStatus | None = None
    from_date: date | None = None
    to_date: date | None = None


class HrTimesheetParams(HrPageParams):
    employee_id: uuid.UUID | None = None
    status: TimesheetStatus | None = None
    from_date: date | None = None
    to_date: date | None = None


class HrDocumentParams(HrPageParams):
    search: str | None = Field(default=None, max_length=150)
    status: DocumentStatus | None = None
    category_id: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None


# ----------------------------------------------------------------------
# The HR employee view
# ----------------------------------------------------------------------
class HrEmployeeRow(BaseModel):
    """One employee as the HR directory lists them.

    Contact details are here because HR operations genuinely need them --
    chasing a document, confirming a start date. Everything an HR screen does
    not need to do its job is absent: there is no ``ctc``, no ``bank_detail``,
    no ``identification`` and no address on this model.
    """

    id: uuid.UUID
    employee_code: str
    full_name: str
    photo_url: str | None = None
    official_email: str
    official_mobile: str | None = None
    mobile_number: str | None = None

    designation: MasterSummary | None = None
    business_unit: MasterSummary | None = None
    team: MasterSummary | None = None
    work_location: MasterSummary | None = None
    employment_type: MasterSummary | None = None
    reporting_manager: EmployeeSummary | None = None

    joining_date: date
    confirmation_date: date | None = None
    employment_status: EmploymentStatus
    work_mode: str | None = None


class HrAttendanceSummary(BaseModel):
    from_date: date
    to_date: date
    present_days: int
    absent_days: int
    leave_days: int
    half_days: int
    late_arrivals: int
    worked_minutes: int
    overtime_minutes: int


class HrLeaveBalanceRow(BaseModel):
    leave_type_id: uuid.UUID
    leave_type_name: str
    year: int
    allocated: Decimal
    used: Decimal
    pending: Decimal
    available: Decimal


class HrTimesheetSummary(BaseModel):
    draft: int
    submitted: int
    approved: int
    rejected: int
    total_hours: Decimal
    billable_hours: Decimal


class HrProjectRow(BaseModel):
    project_id: uuid.UUID
    project_code: str
    project_name: str
    client_name: str | None = None
    allocation_percentage: Decimal
    billable: bool
    start_date: date
    end_date: date | None = None


class HrPerformanceSummary(BaseModel):
    cycle_id: uuid.UUID | None = None
    cycle_name: str | None = None
    goals: int
    goals_completed: int
    goal_progress: int
    self_review_status: str | None = None
    manager_review_status: str | None = None
    current_rating: int | None = None


class HrDocumentRow(BaseModel):
    id: uuid.UUID
    document_code: str
    name: str
    category: MasterSummary | None = None
    document_type: MasterSummary | None = None
    status: DocumentStatus
    expiry_date: date | None = None
    review_notes: str | None = None
    reviewed_at: datetime | None = None
    owner_id: uuid.UUID
    owner_name: str | None = None
    version_count: int
    created_at: datetime


class HrActivityEntry(BaseModel):
    """One line of the employee's audit trail, as HR may read it.

    A projection of :class:`~app.models.audit_log.AuditLog` rather than the row:
    the trail carries request ids, IP addresses and user agents that belong in
    an operator's investigation, not on an HR profile page. HR seeing *that*
    something happened is a different grant from HR administering the trail,
    which is the Administrator's.
    """

    id: uuid.UUID
    action: str
    outcome: str
    description: str | None = None
    actor_email: str | None = None
    created_at: datetime


class HrEmployeeProfile(BaseModel):
    """The nine tabs of the HR employee profile, in one response.

    Assembled server-side because the tabs interlock -- the attendance summary
    and the leave balances are read for the same window -- and because nine
    requests to render one screen is eight chances for one of them to be the
    slow one.
    """

    employee: HrEmployeeRow
    attendance: HrAttendanceSummary
    leave: list[HrLeaveBalanceRow]
    timesheets: HrTimesheetSummary
    projects: list[HrProjectRow]
    performance: HrPerformanceSummary | None = None
    documents: list[HrDocumentRow]
    #: Empty rather than absent when the caller lacks ``audit:view``: the tab
    #: still renders, and says it has nothing to show.
    activity: list[HrActivityEntry] = Field(default_factory=list)
    can_read_activity: bool = Field(
        description="False when the caller does not hold audit:view; the tab is empty by design."
    )


# ----------------------------------------------------------------------
# Rows: a module's own record, paired with whose it is
# ----------------------------------------------------------------------
class HrAttendanceRow(BaseModel):
    employee: EmployeeSummary
    record: AttendanceRead


class HrLeaveRow(BaseModel):
    employee: EmployeeSummary
    request: LeaveRequestRead
    reporting_manager: EmployeeSummary | None = Field(
        default=None, description="Who the request is actually addressed to."
    )


class HrTimesheetRow(BaseModel):
    employee: EmployeeSummary
    timesheet: TimesheetRead


class HrRegularizationRow(BaseModel):
    employee: EmployeeSummary
    request: RegularizationRead


# ----------------------------------------------------------------------
# Dashboard sections
#
# One class per area of HR responsibility, each nullable on the dashboard. A
# section is present when the caller holds the permission behind it and absent
# when they do not -- so the response is the authorization decision rather than
# a description of it.
# ----------------------------------------------------------------------
class HrEmployeeSection(BaseModel):
    total_active: int = Field(description="Employed: probation, confirmed, active or on notice.")
    total_records: int = Field(description="Live records, whatever their status.")
    new_joiners_this_month: int
    on_probation: int
    exiting: int = Field(description="On notice or resigned.")
    by_status: list[CountByLabel]
    by_business_unit: list[CountByLabel]
    by_work_mode: list[CountByLabel]


class HrAttendanceSection(BaseModel):
    on_date: date
    present: int
    absent: int
    late_arrivals: int
    on_leave: int
    monthly_attendance_percentage: int


class HrLeaveSection(BaseModel):
    pending_requests: int = Field(description="Awaiting a decision anywhere in the organization.")
    #: The subset HR should actually act on: nobody is going to decide them,
    #: because the employee has no reporting manager recorded.
    pending_without_a_manager: int
    approved_this_month: int
    rejected_this_month: int
    days_taken_this_month: Decimal
    by_leave_type: list[CountByLabel]
    trend: list[TrendPoint]


class HrRecruitmentSection(BaseModel):
    open_requisitions: int
    active_candidates: int
    interviews_scheduled: int
    offers_pending: int
    onboarding_in_progress: int


class HrDocumentSection(BaseModel):
    pending_review: int
    rejected: int
    expiring_soon: int
    expired: int
    by_status: list[CountByLabel]


class HrProjectHeadcountRow(BaseModel):
    project_id: str
    project: str
    headcount: int


class HrAllocationSection(BaseModel):
    total_clients: int
    active_projects: int
    completed_projects: int
    employees_allocated: int
    bench_employees: int
    allocation_utilization_percent: float
    projects_ending_soon: int
    allocation_conflicts: int
    project_headcount: list[HrProjectHeadcountRow]


class HrBenchRow(BaseModel):
    employee_id: uuid.UUID
    employee_code: str
    name: str
    bench_since: date | None
    bench_duration_days: int
    skills: list[str]
    team: str | None
    manager: str | None


class HrProjectsSection(BaseModel):
    """Workforce allocation as HR reads it: the module's own dashboard and
    bench, typed instead of the ``Any`` the audit found -- an untyped envelope
    was why the frontend could only ``JSON.stringify`` this screen."""

    allocation: HrAllocationSection
    bench: list[HrBenchRow]


class HrPerformanceSection(BaseModel):
    active_cycles: int
    goals_assigned: int
    self_reviews_pending: int
    manager_reviews_pending: int
    final_ratings: int
    completion_percentage: int


class HrRequestQueueSection(BaseModel):
    """What employees are waiting on HR for.

    Not the helpdesk -- tickets have their own dashboard. This is the queue of
    employee-raised requests that bypass the ticket system: documents awaiting
    review, attendance corrections nobody can decide because the employee has
    no manager, and leave in the same position. Every figure is a count of rows
    that exist.
    """

    documents_awaiting_review: int
    documents_rejected: int
    leave_without_a_manager: int
    regularizations_without_a_manager: int
    oldest_waiting_days: int = Field(description="Age of the oldest item in the queue, in days.")


class HrDashboard(BaseModel):
    on_date: date
    #: The sections that came back, so a client renders from the response rather
    #: than from its own idea of who may see what.
    sections: list[str]

    employees: HrEmployeeSection | None = None
    attendance: HrAttendanceSection | None = None
    leave: HrLeaveSection | None = None
    recruitment: HrRecruitmentSection | None = None
    documents: HrDocumentSection | None = None
    performance: HrPerformanceSection | None = None
    requests: HrRequestQueueSection | None = None


class HrAnalytics(BaseModel):
    """Trends, every one of them counted from rows rather than configured.

    Attrition is deliberately absent: the platform records an employment status
    but not a leaving date, so a leaver cannot be attributed to the month they
    left. A trend line that silently attributed everyone to the month the report
    ran would be worse than no line at all.
    """

    months: int
    headcount_trend: list[TrendPoint]
    hiring_trend: list[TrendPoint] = Field(description="Employees whose joining date fell in the month.")
    leave_trend: list[TrendPoint]
    attendance_trend: list[TrendPoint] = Field(description="Attendance percentage per month.")
    performance_completion: int
    document_compliance: int = Field(description="Approved documents as a percentage of those decided.")


# ----------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------
class HrReport(BaseModel):
    """One report in the catalogue, and whether this caller may run it."""

    key: str
    name: str
    description: str
    #: Every permission needed to export it. Shown so an administrator can see
    #: why a report is unavailable rather than guessing.
    required_permissions: list[str]
    available: bool


__all__ = [
    "CountByLabel",
    "HrActivityEntry",
    "HrAnalytics",
    "HrAttendanceParams",
    "HrAttendanceRow",
    "HrAttendanceSection",
    "HrAttendanceSummary",
    "HrDashboard",
    "HrDocumentParams",
    "HrDocumentRow",
    "HrDocumentSection",
    "HrEmployeeParams",
    "HrEmployeeProfile",
    "HrEmployeeRow",
    "HrEmployeeSection",
    "HrLeaveBalanceRow",
    "HrLeaveParams",
    "HrLeaveRow",
    "HrLeaveSection",
    "HrPageParams",
    "HrPerformanceSection",
    "HrPerformanceSummary",
    "HrProjectRow",
    "HrRecruitmentSection",
    "HrRegularizationRow",
    "HrReport",
    "HrRequestQueueSection",
    "HrTimesheetParams",
    "HrTimesheetRow",
    "HrTimesheetSummary",
    "TrendPoint",
]
