"""HR administration.

Like the employee portal and the manager module, this contains **no business
rules**. A leave policy change is :meth:`WorkforceService.update_leave_type`. A
document review is :meth:`DocumentService.review`. A balance adjustment is
:meth:`WorkforceService.adjust_balance`, audited there because that is where
balances live. If a rule appears to be missing from an HR screen, it is missing
from the module that owns it.

What this module owns is two things a shared service cannot.

**Composition.** An HR dashboard is seven modules' figures on one screen, and an
HR employee profile is nine tabs about one person. Assembling either in the
browser would be sixteen requests to render two screens.

**Graduated disclosure.** Every section of the dashboard is behind the
permission for the module it summarises, and the service asks the existing
:class:`~app.services.authorization_service.AuthorizationService` which of them
the caller holds. That is the one piece of authorization logic here, and it is a
*read* of the permission set rather than a second copy of it -- there is no role
name anywhere in this file, and a section is present exactly when the endpoint
behind it would answer.

The distinction the whole module exists to hold: **HR is not an administrator.**
Every screen below is guarded by an HR permission; none of them touches roles,
settings, integrations or the user directory, and the three administrative
workforce actions (:meth:`correct_attendance`, :meth:`adjust_balance`,
:meth:`override_leave_decision`) sit behind permissions the seeded HR roles do
not hold.
"""

from __future__ import annotations

import calendar
import csv
import io
import uuid
from collections.abc import Awaitable, Callable, Collection, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from openpyxl import Workbook

from app.core.permissions import PermissionAction, code
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.enums import (
    ApprovalStatus,
    AttendanceStatus,
    DocumentOwnerType,
    DocumentStatus,
    EmploymentStatus,
    ExpiryState,
    TimesheetStatus,
)
from app.models.interview import Interview
from app.models.offer import Offer
from app.models.onboarding import OnboardingCase
from app.models.recruitment import Candidate
from app.models.requisition import JobRequisition
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.interview_repository import InterviewRepository
from app.repositories.offer_repository import OfferRepository
from app.repositories.onboarding_repository import CaseRepository as OnboardingCaseRepository
from app.repositories.project_repository import AllocationRepository
from app.repositories.recruitment_repository import CandidateRepository
from app.repositories.requisition_repository import RequisitionRepository
from app.repositories.workforce_repository import (
    LeaveRequestRepository,
    RegularizationRepository,
    WorkforceAnalyticsRepository,
)
from app.schemas.document import DocumentListParams
from app.schemas.employee import EmployeeListParams, EmployeeSummary, ExportFormat
from app.schemas.hr import (
    CountByLabel,
    HrActivityEntry,
    HrAnalytics,
    HrAttendanceParams,
    HrAttendanceRow,
    HrAttendanceSection,
    HrAttendanceSummary,
    HrDashboard,
    HrDocumentParams,
    HrDocumentRow,
    HrDocumentSection,
    HrEmployeeParams,
    HrEmployeeProfile,
    HrEmployeeRow,
    HrEmployeeSection,
    HrLeaveBalanceRow,
    HrLeaveParams,
    HrLeaveRow,
    HrLeaveSection,
    HrPerformanceSection,
    HrPerformanceSummary,
    HrProjectRow,
    HrRecruitmentSection,
    HrReport,
    HrRequestQueueSection,
    HrTimesheetParams,
    HrTimesheetRow,
    HrTimesheetSummary,
    TrendPoint,
)
from app.schemas.masters import MasterSummary
from app.schemas.workforce import (
    AttendanceListParams,
    AttendanceRead,
    LeaveListParams,
    LeaveRequestRead,
    TimesheetListParams,
    TimesheetRead,
)
from app.services import employee_export_service as employee_export
from app.services.authorization_service import AuthorizationService
from app.services.document_service import DocumentService
from app.services.employee_service import EmployeeService
from app.services.performance_service import PerformanceService
from app.services.project_service import ProjectService
from app.services.scope_service import EmployeeScope
from app.services.workforce_service import WorkforceService

#: The largest page the shared list params accept.
PAGE_LIMIT = 100

#: How far back the analytics screen looks by default.
DEFAULT_TREND_MONTHS = 12

#: How many audit lines the HR profile's activity tab carries.
ACTIVITY_LIMIT = 25

#: How many bars a breakdown shows before the tail is dropped.
BREAKDOWN_LIMIT = 8

#: Hard ceiling on an export assembled here. Large enough for any realistic
#: headcount, small enough that a mistaken unfiltered export cannot exhaust
#: memory -- the same reasoning as ``EXPORT_LIMIT`` on the employee repository.
EXPORT_ROW_LIMIT = 10_000

_A = PermissionAction

#: Which permission gates which section of the dashboard. Declared as data so
#: the response, the report catalogue and the tests all read the same table
#: rather than three hand-maintained copies of it.
DASHBOARD_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("employees", (code("employees", _A.VIEW),)),
    ("attendance", (code("attendance", _A.VIEW),)),
    ("leave", (code("leave", _A.VIEW),)),
    ("recruitment", (code("recruitment", _A.VIEW),)),
    ("documents", (code("documents", _A.VIEW),)),
    ("performance", (code("performance", _A.VIEW),)),
    ("requests", (code("documents", _A.VIEW), code("leave", _A.VIEW))),
)

#: The HR report catalogue. Each names the permissions an export needs, and the
#: export endpoint checks them again -- the catalogue is what the screen renders
#: from, not what authorizes the download.
REPORTS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "employees",
        "Employee report",
        "The directory with placement, status and joining dates.",
        (code("employees", _A.EXPORT),),
    ),
    (
        "attendance",
        "Attendance report",
        "The daily register for a date range, with hours and lateness.",
        (code("attendance", _A.EXPORT),),
    ),
    (
        "leave-register",
        "Leave report",
        "Every leave request in a window, with its decision.",
        (code("leave", _A.EXPORT),),
    ),
    (
        "leave-balance",
        "Leave balance report",
        "Entitlement, usage and remaining days per employee.",
        (code("leave", _A.EXPORT),),
    ),
    (
        "timesheet",
        "Timesheet report",
        "Weekly totals and billable hours.",
        (code("timesheets", _A.EXPORT),),
    ),
    # The recruitment export is deliberately absent. It exists already, on the
    # recruitment module, behind ``recruitment:export`` and with its own filter
    # screen -- offering a second entry point here would be a second answer to
    # "which candidates are in this file".
    (
        "performance-summary",
        "Performance report",
        "Cycle progress, review completion and ratings.",
        (code("performance", _A.EXPORT),),
    ),
    (
        "document-compliance",
        "Document compliance report",
        "What each employee has filed and what is still outstanding.",
        (code("documents", _A.EXPORT),),
    ),
)


class HrService:
    """The HR-facing view of modules that already exist."""

    def __init__(
        self,
        *,
        authorization: AuthorizationService,
        employees: EmployeeService,
        workforce: WorkforceService,
        documents: DocumentService,
        performance: PerformanceService,
        projects: ProjectService,
        employee_repository: EmployeeRepository,
        document_repository: DocumentRepository,
        leave_requests: LeaveRequestRepository,
        regularizations: RegularizationRepository,
        analytics: WorkforceAnalyticsRepository,
        allocations: AllocationRepository,
        audit_logs: AuditLogRepository,
        requisitions: RequisitionRepository,
        candidates: CandidateRepository,
        interviews: InterviewRepository,
        offers: OfferRepository,
        onboarding_cases: OnboardingCaseRepository,
    ) -> None:
        self.authorization = authorization
        self.employees = employees
        self.workforce = workforce
        # ``vault`` rather than ``documents``: this class has a ``documents()``
        # method, and an attribute of the same name would shadow it.
        self.vault = documents
        self.performance = performance
        # ``projects_service`` rather than ``projects``: this class has a
        # ``projects()`` method, and an attribute of the same name would shadow
        # it -- the same collision the portal and the manager module both hit.
        self.projects_service = projects
        self.employee_repository = employee_repository
        self.document_repository = document_repository
        self.leave_requests = leave_requests
        self.regularizations = regularizations
        self.analytics = analytics
        self.allocations = allocations
        self.audit_logs = audit_logs
        # Counted rather than composed: five COUNTs answer the recruitment tile,
        # where five module dashboards would compute forty figures to show five.
        self.requisitions = requisitions
        self.candidates = candidates
        self.interviews = interviews
        self.offers = offers
        self.onboarding_cases = onboarding_cases

    # ==================================================================
    # Dashboard
    # ==================================================================
    async def dashboard(self, user: Any) -> HrDashboard:
        """One screen, assembled from seven modules and narrowed to one caller.

        Each section is built only when its permission is held. A caller who
        cannot see recruitment gets a response with no recruitment block rather
        than a block of zeroes -- zero open requisitions and "you may not ask"
        are different answers, and a dashboard that renders the first for the
        second is lying quietly.
        """
        held = await self.authorization.permissions_for(user)
        today = self._today()
        sections = [name for name, needed in DASHBOARD_SECTIONS if set(needed) <= held]

        return HrDashboard(
            on_date=today,
            sections=sections,
            employees=await self._employee_section(today) if "employees" in sections else None,
            attendance=await self._attendance_section(today) if "attendance" in sections else None,
            leave=await self._leave_section(today) if "leave" in sections else None,
            recruitment=await self._recruitment_section() if "recruitment" in sections else None,
            documents=await self._document_section(today) if "documents" in sections else None,
            performance=await self._performance_section() if "performance" in sections else None,
            requests=await self._request_queue_section(today) if "requests" in sections else None,
        )

    async def _employee_section(self, today: date) -> HrEmployeeSection:
        month_start = today.replace(day=1)
        month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])

        return HrEmployeeSection(
            total_active=await self.employee_repository.count_employed(),
            total_records=await self.employee_repository.count_live(),
            new_joiners_this_month=await self.employee_repository.count_joining_between(
                month_start, month_end
            ),
            on_probation=await self.employee_repository.count_with_status(EmploymentStatus.PROBATION),
            exiting=(
                await self.employee_repository.count_with_status(EmploymentStatus.NOTICE_PERIOD)
                + await self.employee_repository.count_with_status(EmploymentStatus.RESIGNED)
            ),
            by_status=self._labelled(await self.employee_repository.count_by_status()),
            by_business_unit=self._labelled(
                await self.employee_repository.count_by_business_unit(limit=BREAKDOWN_LIMIT),
                humanise=False,
            ),
            by_work_mode=self._labelled(await self.employee_repository.count_by_work_mode()),
        )

    async def _attendance_section(self, today: date) -> HrAttendanceSection:
        figures = await self.workforce.dashboard(today)
        return HrAttendanceSection(
            on_date=today,
            present=figures["present"],
            absent=figures["absent"],
            late_arrivals=figures["late_arrivals"],
            on_leave=figures["on_leave"],
            monthly_attendance_percentage=figures["monthly_attendance_percentage"],
        )

    async def _leave_section(self, today: date) -> HrLeaveSection:
        month_start = today.replace(day=1)
        return HrLeaveSection(
            pending_requests=await self.leave_requests.count_pending(),
            pending_without_a_manager=await self.leave_requests.count_pending_without_manager(),
            approved_this_month=await self.leave_requests.count_decided_between(
                ApprovalStatus.APPROVED, month_start, today
            ),
            rejected_this_month=await self.leave_requests.count_decided_between(
                ApprovalStatus.REJECTED, month_start, today
            ),
            days_taken_this_month=await self.leave_requests.days_between(month_start, today),
            by_leave_type=self._labelled(
                await self.leave_requests.count_by_type(month_start, today), humanise=False
            ),
            trend=await self._leave_trend(today, months=6),
        )

    async def _recruitment_section(self) -> HrRecruitmentSection:
        return HrRecruitmentSection(
            open_requisitions=await self.requisitions.count(JobRequisition.status == "open"),
            # No status column on a candidate: somebody is active until they are
            # hired, which ``hired_at`` is the record of.
            active_candidates=await self.candidates.count(Candidate.hired_at.is_(None)),
            interviews_scheduled=await self.interviews.count(Interview.status == "scheduled"),
            offers_pending=await self.offers.count(Offer.status.in_(["pending_approval", "released"])),
            onboarding_in_progress=await self.onboarding_cases.count(
                OnboardingCase.status.in_(["not_started", "in_progress"])
            ),
        )

    async def _document_section(self, today: date) -> HrDocumentSection:
        by_status = await self.document_repository.count_by_status()
        return HrDocumentSection(
            pending_review=await self.document_repository.count_pending_review(),
            rejected=next((count for name, count in by_status if name == DocumentStatus.REJECTED.value), 0),
            expiring_soon=await self.document_repository.count_by_expiry(
                ExpiryState.EXPIRING_SOON, today=today
            ),
            expired=await self.document_repository.count_by_expiry(ExpiryState.EXPIRED, today=today),
            by_status=self._labelled(by_status),
        )

    async def _performance_section(self) -> HrPerformanceSection:
        figures = await self.performance.dashboard()
        pending = figures["self_reviews_pending"] + figures["manager_reviews_pending"]
        finalised = figures["final_ratings"]
        return HrPerformanceSection(
            active_cycles=figures["active_cycles"],
            goals_assigned=figures["goals_assigned"],
            self_reviews_pending=figures["self_reviews_pending"],
            manager_reviews_pending=figures["manager_reviews_pending"],
            final_ratings=finalised,
            completion_percentage=int(finalised * 100 / (finalised + pending)) if finalised + pending else 0,
        )

    async def _request_queue_section(self, today: date) -> HrRequestQueueSection:
        """What employees are waiting on HR for.

        Not the helpdesk: the platform has one now (Phase 20), but tickets
        already have their own dashboard at ``/helpdesk/dashboard``. This
        section counts the request rows that *bypass* the ticket queue --
        documents awaiting review, and the leave and corrections nobody can
        decide because the employee has no manager. Counting them twice on two
        dashboards would be worse than counting them once each.
        """
        by_status = await self.document_repository.count_by_status()
        waiting_since = [
            stamp
            for stamp in (
                await self.document_repository.oldest_pending_at(),
                await self.leave_requests.oldest_pending_at(),
            )
            if stamp is not None
        ]
        oldest = min(waiting_since) if waiting_since else None

        return HrRequestQueueSection(
            documents_awaiting_review=await self.document_repository.count_pending_review(),
            documents_rejected=next(
                (count for name, count in by_status if name == DocumentStatus.REJECTED.value), 0
            ),
            leave_without_a_manager=await self.leave_requests.count_pending_without_manager(),
            regularizations_without_a_manager=(await self.regularizations.count_pending_without_manager()),
            oldest_waiting_days=(today - oldest.date()).days if oldest else 0,
        )

    # ==================================================================
    # Analytics
    # ==================================================================
    async def analytics_overview(self, *, months: int = DEFAULT_TREND_MONTHS) -> HrAnalytics:
        """Trends, every point counted from rows.

        One query per month per series rather than one grouped query per series:
        the windows differ per series -- a headcount is a position at a moment,
        a hiring figure is a count within a month -- and expressing all of them
        as one aggregate would need a calendar table this schema does not have.
        Twelve points is twelve cheap COUNTs on an indexed column.
        """
        today = self._today()
        windows = self._months_back(today, months)

        headcount = [
            TrendPoint(
                period=self._period(end),
                label=self._month_label(end),
                count=await self.employee_repository.count_joined_by(end),
            )
            for _start, end in windows
        ]
        hiring = [
            TrendPoint(
                period=self._period(end),
                label=self._month_label(end),
                count=await self.employee_repository.count_joining_between(start, end),
            )
            for start, end in windows
        ]
        attendance = [
            TrendPoint(
                period=self._period(end),
                label=self._month_label(end),
                count=await self.analytics.attendance_percentage(start, end),
            )
            for start, end in windows
        ]

        performance = await self._performance_section()
        by_status = await self.document_repository.count_by_status()
        decided = sum(
            count
            for name, count in by_status
            if name in {DocumentStatus.APPROVED.value, DocumentStatus.REJECTED.value}
        )
        approved = next((count for name, count in by_status if name == DocumentStatus.APPROVED.value), 0)

        return HrAnalytics(
            months=months,
            headcount_trend=headcount,
            hiring_trend=hiring,
            leave_trend=await self._leave_trend(today, months=months),
            attendance_trend=attendance,
            performance_completion=performance.completion_percentage,
            document_compliance=int(approved * 100 / decided) if decided else 0,
        )

    async def _leave_trend(self, today: date, *, months: int) -> list[TrendPoint]:
        return [
            TrendPoint(
                period=self._period(end),
                label=self._month_label(end),
                count=int(await self.leave_requests.days_between(start, end)),
            )
            for start, end in self._months_back(today, months)
        ]

    # ==================================================================
    # The HR employee view
    # ==================================================================
    async def employees_page(
        self, params: HrEmployeeParams, *, scope: EmployeeScope
    ) -> tuple[list[HrEmployeeRow], int]:
        """The directory, paged and filtered by the database.

        The scope goes down into the query rather than being applied to the
        result: an HR user who does not hold ``employees:view_all`` sees their
        own reporting line here, which is the same narrowing every other screen
        applies, and the page count stays correct because the filter ran in SQL.
        """
        rows, total = await self.employees.list(
            EmployeeListParams(
                page=params.page,
                page_size=params.page_size,
                search=params.search,
                sort_by=params.sort_by,
                sort_order=params.sort_order,
                employment_status=params.employment_status,
                business_unit_id=params.business_unit_id,
                team_id=params.team_id,
                designation_id=params.designation_id,
                work_location_id=params.work_location_id,
                employment_type_id=params.employment_type_id,
                reporting_manager_id=params.reporting_manager_id,
                joined_from=params.joined_from,
                joined_to=params.joined_to,
            ),
            scope=scope,
        )
        return [self._as_row(row) for row in rows], total

    async def employee_profile(
        self, employee_id: uuid.UUID, *, scope: EmployeeScope, user: Any
    ) -> HrEmployeeProfile:
        """The nine tabs, in one response.

        The scope check comes first and nothing is read before it, so an
        employee outside the caller's reach is refused rather than answered.
        The activity tab is the one part gated separately: reading the audit
        trail is ``audit:view``, which HR holds and an HR Executive may not, and
        the tab comes back empty rather than the whole profile failing.
        """
        scope.assert_allows(employee_id, field="employee_id")
        employee = await self.employees.get_by_id(employee_id)

        today = self._today()
        one_person = EmployeeScope.just_self(employee_id, employee.user_id)
        held = await self.authorization.permissions_for(user)
        may_read_activity = code("audit", _A.VIEW) in held

        performance = await self.performance.for_employees([employee_id])
        return HrEmployeeProfile(
            employee=self._as_row(employee),
            attendance=await self._attendance_summary(
                employee_id, today.replace(day=1), today, scope=one_person
            ),
            leave=await self._leave_balances(employee_id),
            timesheets=await self._timesheet_summary(employee_id, scope=one_person),
            projects=await self._projects(employee_id, on=today),
            performance=self._as_performance(performance[0]) if performance else None,
            documents=await self._employee_documents(employee, scope=one_person),
            activity=await self._activity(employee_id) if may_read_activity else [],
            can_read_activity=may_read_activity,
        )

    # ==================================================================
    # Organization-wide reads
    # ==================================================================
    async def attendance(
        self, params: HrAttendanceParams, *, scope: EmployeeScope
    ) -> tuple[list[HrAttendanceRow], int]:
        """The register, narrowed by the placement filters before it is paged.

        The four placement filters have no equivalent on ``AttendanceListParams``
        -- a business unit is a fact about the employee, not about the day -- so
        they are resolved to a set of employee ids and intersected with the
        caller's scope. The intersection is what stops a filter widening reach:
        it can only ever remove ids the scope already allowed.
        """
        narrowed = await self._narrow(scope, params)
        rows, total = await self.workforce.list_attendance(
            AttendanceListParams(
                page=params.page,
                page_size=params.page_size,
                employee_id=params.employee_id,
                status=params.status,
                from_date=params.from_date,
                to_date=params.to_date,
            ),
            scope=narrowed,
        )
        directory = await self._directory({row.employee_id for row in rows})
        return [
            HrAttendanceRow(employee=directory[row.employee_id], record=AttendanceRead.model_validate(row))
            for row in rows
            if row.employee_id in directory
        ], total

    async def leave(self, params: HrLeaveParams, *, scope: EmployeeScope) -> tuple[list[HrLeaveRow], int]:
        if params.employee_id is not None:
            scope.assert_allows(params.employee_id, field="employee_id")

        rows, total = await self.workforce.list_leave(
            LeaveListParams(
                page=params.page,
                page_size=params.page_size,
                employee_id=params.employee_id,
                leave_type_id=params.leave_type_id,
                status=params.status,
                from_date=params.from_date,
                to_date=params.to_date,
            ),
            scope=scope,
        )
        employees = await self._employees_by_id({row.employee_id for row in rows})
        managers = await self._employees_by_id(
            {row.reporting_manager_id for row in employees.values() if row.reporting_manager_id}
        )

        return [
            HrLeaveRow(
                employee=EmployeeSummary.model_validate(employees[row.employee_id]),
                request=LeaveRequestRead.model_validate(row),
                # Named on the row because the first question about a request HR
                # is looking at is "whose decision is this actually?" -- and the
                # answer decides whether an override is the right move.
                reporting_manager=self._summary_of(
                    managers.get(manager_id)
                    if (manager_id := employees[row.employee_id].reporting_manager_id)
                    else None
                ),
            )
            for row in rows
            if row.employee_id in employees
        ], total

    async def timesheets(
        self, params: HrTimesheetParams, *, scope: EmployeeScope
    ) -> tuple[list[HrTimesheetRow], int]:
        if params.employee_id is not None:
            scope.assert_allows(params.employee_id, field="employee_id")

        rows, total = await self.workforce.list_timesheets(
            TimesheetListParams(
                page=params.page,
                page_size=params.page_size,
                employee_id=params.employee_id,
                status=params.status,
                from_date=params.from_date,
                to_date=params.to_date,
            ),
            scope=scope,
        )
        directory = await self._directory({row.employee_id for row in rows})
        return [
            HrTimesheetRow(employee=directory[row.employee_id], timesheet=TimesheetRead.model_validate(row))
            for row in rows
            if row.employee_id in directory
        ], total

    async def documents(
        self, params: HrDocumentParams, *, scope: EmployeeScope
    ) -> tuple[list[HrDocumentRow], int]:
        """The review queue.

        Filtered to employee-owned documents when an employee is named, and
        otherwise left as the vault's own scoped list -- which already keeps
        organization policies readable and candidate paperwork behind
        recruitment's own permission.
        """
        if params.employee_id is not None:
            scope.assert_allows(params.employee_id, field="employee_id")

        rows, total = await self.vault.list(
            DocumentListParams(
                page=params.page,
                page_size=params.page_size,
                search=params.search,
                status=params.status,
                category_id=params.category_id,
                owner_type=DocumentOwnerType.EMPLOYEE if params.employee_id else None,
                owner_id=params.employee_id,
            ),
            scope=scope,
        )
        return [await self.as_document_row(row) for row in rows], total

    async def projects(self) -> dict[str, Any]:
        """Workforce allocation, read-only, from the Project Allocation module.

        The module's own dashboard and bench, returned as they are. HR reads
        this screen to answer "who is unallocated" and "how billable are we";
        changing an allocation is ``projects:update`` on the project screens,
        and there is no endpoint here that writes one.
        """
        return {
            "allocation": await self.projects_service.dashboard(),
            "bench": await self.projects_service.bench(),
        }

    async def performance_overview(self) -> HrPerformanceSection:
        """Cycle progress and review completion, organization-wide."""
        return await self._performance_section()

    async def request_queue(self) -> HrRequestQueueSection:
        """What employees are waiting on HR for. See :meth:`_request_queue_section`."""
        return await self._request_queue_section(self._today())

    async def reports(self, user: Any) -> list[HrReport]:
        """The report catalogue, with each entry marked available or not.

        Rendered from the same table the export endpoint checks against, so the
        screen cannot offer a download the API will refuse -- and an
        administrator can see *which* permission is missing rather than
        wondering why a button is greyed out.
        """
        held = await self.authorization.permissions_for(user)
        return [
            HrReport(
                key=key,
                name=name,
                description=description,
                required_permissions=list(required),
                available=set(required) <= held,
            )
            for key, name, description, required in REPORTS
        ]

    @staticmethod
    def report_permissions(key: str) -> tuple[str, ...]:
        """What an export of this report needs. Raises for an unknown key."""
        for candidate, _name, _description, required in REPORTS:
            if candidate == key:
                return required
        raise KeyError(key)

    async def export_report(
        self,
        key: str,
        fmt: str,
        *,
        from_date: date,
        to_date: date,
        scope: EmployeeScope,
    ) -> tuple[bytes, str]:
        """Render one report, through the module that owns the data.

        No report is built here except document compliance, which has no owner:
        an attendance export is ``WorkforceService.export``, so the file a
        manager downloads from the workforce screen and the file HR downloads
        from this one contain the same rows in the same order. Two renderers
        would be two definitions of what "the attendance report" means.

        The permission was already checked at the route; this re-derives nothing
        and trusts nothing about the caller.
        """
        if key == "employees":
            rows = await self.employees.list_for_export(
                EmployeeListParams(page=1, page_size=PAGE_LIMIT), scope=scope
            )
            return employee_export.render(rows, ExportFormat(fmt))

        if key in {"attendance", "leave-register", "leave-balance", "timesheet"}:
            return await self.workforce.export(key, fmt, from_date, to_date)

        if key == "performance-summary":
            return await self.performance.export("performance-summary", fmt)

        if key == "document-compliance":
            return await self._document_compliance(fmt, scope=scope)

        raise KeyError(key)

    async def _document_compliance(self, fmt: str, *, scope: EmployeeScope) -> tuple[bytes, str]:
        """What each employee has filed, and what is still outstanding.

        The one report assembled here, because no module owns it: it crosses the
        directory and the vault, and neither of them should grow a method whose
        only caller is an HR screen. It carries counts and nothing else -- no
        document name and no classification -- so the file is safe to send to
        somebody chasing paperwork.
        """
        employees = await self._drain(
            lambda page: self.employees.list(
                EmployeeListParams(page=page, page_size=PAGE_LIMIT), scope=scope
            ),
            limit=EXPORT_ROW_LIMIT,
        )
        counts = await self.document_repository.status_counts_for_owners(
            DocumentOwnerType.EMPLOYEE, [row.id for row in employees]
        )
        by_employee: dict[uuid.UUID, dict[str, int]] = {}
        for owner_id, status, count in counts:
            by_employee.setdefault(owner_id, {})[status] = count

        rows: list[list[Any]] = [
            ["Employee", "Employee ID", "Filed", "Approved", "Awaiting review", "Rejected"]
        ]
        for employee in employees:
            tally = by_employee.get(employee.id, {})
            rows.append(
                [
                    employee.full_name,
                    employee.employee_code,
                    sum(tally.values()),
                    tally.get(DocumentStatus.APPROVED.value, 0),
                    tally.get(DocumentStatus.UPLOADED.value, 0)
                    + tally.get(DocumentStatus.UNDER_REVIEW.value, 0),
                    tally.get(DocumentStatus.REJECTED.value, 0),
                ]
            )

        if fmt == "csv":
            out = io.StringIO()
            csv.writer(out).writerows(rows)
            # utf-8-sig so Excel opens accented names correctly, as every other
            # export in the platform does.
            return out.getvalue().encode("utf-8-sig"), "text/csv"

        book = Workbook()
        sheet = book.active
        sheet.title = "Document compliance"
        for row in rows:
            sheet.append(row)
        buffer = io.BytesIO()
        book.save(buffer)
        return (
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # ==================================================================
    # Profile helpers
    # ==================================================================
    async def _attendance_summary(
        self, employee_id: uuid.UUID, start: date, end: date, *, scope: EmployeeScope
    ) -> HrAttendanceSummary:
        rows, _ = await self.workforce.list_attendance(
            AttendanceListParams(
                page=1, page_size=PAGE_LIMIT, employee_id=employee_id, from_date=start, to_date=end
            ),
            scope=scope,
        )
        return HrAttendanceSummary(
            from_date=start,
            to_date=end,
            present_days=sum(1 for row in rows if row.status == AttendanceStatus.PRESENT.value),
            absent_days=sum(1 for row in rows if row.status == AttendanceStatus.ABSENT.value),
            leave_days=sum(1 for row in rows if row.status == AttendanceStatus.LEAVE.value),
            half_days=sum(1 for row in rows if row.status == AttendanceStatus.HALF_DAY.value),
            late_arrivals=sum(1 for row in rows if row.late_minutes > 0),
            worked_minutes=sum(row.worked_minutes for row in rows),
            overtime_minutes=sum(row.overtime_minutes for row in rows),
        )

    async def _leave_balances(self, employee_id: uuid.UUID) -> list[HrLeaveBalanceRow]:
        return [
            HrLeaveBalanceRow(
                leave_type_id=balance.leave_type_id,
                leave_type_name=balance.leave_type.name if balance.leave_type else "Leave",
                year=balance.year,
                allocated=balance.allocated,
                used=balance.used,
                pending=balance.pending,
                available=balance.remaining,
            )
            for balance in await self.workforce.balances_for(employee_id)
        ]

    async def _timesheet_summary(self, employee_id: uuid.UUID, *, scope: EmployeeScope) -> HrTimesheetSummary:
        rows = await self._drain(
            lambda page: self.workforce.list_timesheets(
                TimesheetListParams(page=page, page_size=PAGE_LIMIT, employee_id=employee_id),
                scope=scope,
            ),
            limit=500,
        )
        return HrTimesheetSummary(
            draft=sum(1 for row in rows if row.status == TimesheetStatus.DRAFT.value),
            submitted=sum(1 for row in rows if row.status == TimesheetStatus.SUBMITTED.value),
            approved=sum(1 for row in rows if row.status == TimesheetStatus.APPROVED.value),
            rejected=sum(1 for row in rows if row.status == TimesheetStatus.REJECTED.value),
            total_hours=sum((row.total_hours for row in rows), start=Decimal(0)),
            billable_hours=sum((row.billable_hours for row in rows), start=Decimal(0)),
        )

    async def _projects(self, employee_id: uuid.UUID, *, on: date) -> list[HrProjectRow]:
        del on
        return [
            HrProjectRow(
                project_id=allocation.project_id,
                project_code=allocation.project.project_code,
                project_name=allocation.project.project_name,
                client_name=allocation.project.client.client_name if allocation.project.client else None,
                allocation_percentage=allocation.allocation_percentage,
                billable=allocation.billable,
                start_date=allocation.start_date,
                end_date=allocation.end_date,
            )
            for allocation, _member in await self.allocations.for_employee(employee_id)
        ]

    async def _employee_documents(self, employee: Employee, *, scope: EmployeeScope) -> list[HrDocumentRow]:
        rows, _ = await self.vault.list(
            DocumentListParams(
                page=1,
                page_size=PAGE_LIMIT,
                owner_type=DocumentOwnerType.EMPLOYEE,
                owner_id=employee.id,
            ),
            scope=scope,
        )
        return [await self.as_document_row(row) for row in rows]

    async def _activity(self, employee_id: uuid.UUID) -> list[HrActivityEntry]:
        rows: Sequence[AuditLog] = await self.audit_logs.search(
            entity_type="employee", entity_id=str(employee_id), limit=ACTIVITY_LIMIT
        )
        return [
            HrActivityEntry(
                id=row.id,
                action=row.action,
                outcome=row.outcome,
                description=row.description,
                actor_email=row.actor_email,
                created_at=row.created_at,
            )
            for row in rows
        ]

    # ==================================================================
    # Helpers
    # ==================================================================
    async def _narrow(self, scope: EmployeeScope, params: HrAttendanceParams) -> EmployeeScope:
        """Intersect the placement filters with the caller's scope.

        Returns the scope unchanged when no placement filter is set, so the
        common case costs nothing. When one *is* set, the result is always a
        subset of what the caller could already reach -- an id resolved from a
        filter that was not in the scope does not survive the intersection.
        """
        if params.employee_id is not None:
            scope.assert_allows(params.employee_id, field="employee_id")

        placement = {
            "business_unit_id": params.business_unit_id,
            "team_id": params.team_id,
            "work_location_id": params.work_location_id,
            "reporting_manager_id": params.reporting_manager_id,
        }
        if not any(placement.values()):
            return scope

        matched = await self._drain(
            lambda page: self.employees.list(
                EmployeeListParams(page=page, page_size=PAGE_LIMIT, **placement),
                scope=scope,
            ),
            limit=2000,
        )
        return EmployeeScope.of_direct_reports({row.id for row in matched})

    async def _directory(self, employee_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, EmployeeSummary]:
        rows = await self._employees_by_id(employee_ids)
        return {key: EmployeeSummary.model_validate(row) for key, row in rows.items()}

    async def _employees_by_id(self, employee_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, Employee]:
        """Resolve a set of ids to employees, in one query.

        Read straight from the repository rather than through the scoped list:
        the ids arrived from rows the scope has *already* admitted, and
        re-filtering them would drop the manager of a visible employee -- whose
        name the leave screen has to show, and who is not themselves in scope.
        """
        ids = [employee_id for employee_id in employee_ids if employee_id is not None]
        if not ids:
            return {}
        rows = await self.employee_repository.list(
            Employee.id.in_(ids), limit=PAGE_LIMIT * 2, include_deleted=True
        )
        return {row.id: row for row in rows}

    @staticmethod
    def _summary_of(employee: Employee | None) -> EmployeeSummary | None:
        return EmployeeSummary.model_validate(employee) if employee is not None else None

    def _as_row(self, employee: Employee) -> HrEmployeeRow:
        return HrEmployeeRow(
            id=employee.id,
            employee_code=employee.employee_code,
            full_name=employee.full_name,
            photo_url=employee.photo_url,
            official_email=employee.official_email,
            official_mobile=employee.official_mobile,
            mobile_number=employee.mobile_number,
            designation=self._master(employee.designation),
            business_unit=self._master(employee.business_unit),
            team=self._master(employee.team),
            work_location=self._master(employee.work_location),
            employment_type=self._master(employee.employment_type),
            reporting_manager=self._summary_of(employee.reporting_manager),
            joining_date=employee.joining_date,
            confirmation_date=employee.confirmation_date,
            employment_status=EmploymentStatus(employee.employment_status),
            work_mode=employee.work_mode,
        )

    async def as_document_row(self, document: Any) -> HrDocumentRow:
        owner = await self.vault.resolve_owner(document)
        return HrDocumentRow(
            id=document.id,
            document_code=document.document_code,
            name=document.name,
            category=self._master(document.category),
            document_type=self._master(document.document_type),
            status=DocumentStatus(document.status),
            expiry_date=document.expiry_date,
            review_notes=document.review_notes,
            reviewed_at=document.reviewed_at,
            owner_id=document.owner_id,
            owner_name=owner.display_name if owner else None,
            version_count=document.version_count,
            created_at=document.created_at,
        )

    @staticmethod
    def _as_performance(row: dict[str, Any]) -> HrPerformanceSummary:
        return HrPerformanceSummary(
            cycle_id=row["cycle_id"],
            cycle_name=row["cycle_name"],
            goals=row["goals"],
            goals_completed=row["goals_completed"],
            goal_progress=row["goal_progress"],
            self_review_status=row["self_review_status"],
            manager_review_status=row["manager_review_status"],
            current_rating=row["current_rating"],
        )

    @staticmethod
    def _labelled(rows: Sequence[tuple[str, int]], *, humanise: bool = True) -> list[CountByLabel]:
        return [
            CountByLabel(label=name.replace("_", " ").capitalize() if humanise else name, count=count)
            for name, count in rows
        ]

    @staticmethod
    def _master(record: Any) -> MasterSummary | None:
        return MasterSummary.model_validate(record) if record is not None else None

    @staticmethod
    async def _drain(
        fetch: Callable[[int], Awaitable[tuple[Sequence[Any], int]]], *, limit: int
    ) -> list[Any]:
        """Read every page of a paged query, up to a hard ceiling."""
        rows: list[Any] = []
        page = 1
        while len(rows) < limit:
            batch, total = await fetch(page)
            rows.extend(batch)
            if not batch or len(rows) >= total:
                break
            page += 1
        return rows[:limit]

    @staticmethod
    def _months_back(today: date, months: int) -> list[tuple[date, date]]:
        """``(first, last)`` of each of the last ``months`` months, oldest first."""
        windows: list[tuple[date, date]] = []
        cursor = today.replace(day=1)
        for _ in range(months):
            last = cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1])
            windows.append((cursor, min(last, today)))
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        return list(reversed(windows))

    @staticmethod
    def _period(on: date) -> str:
        return f"{on.year:04d}-{on.month:02d}"

    @staticmethod
    def _month_label(on: date) -> str:
        return f"{calendar.month_abbr[on.month]} {on.year}"

    @staticmethod
    def _today() -> date:
        return datetime.now(UTC).date()
