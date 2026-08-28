"""Manager and team management.

Like :mod:`app.services.self_service_service`, this module contains **no
business rules**, and for the same reason. Approving leave is
:meth:`WorkforceService.decide_leave`, with the same balance arithmetic and the
same notification. A team roster is :meth:`EmployeeService.list`, with the same
search and the same filters. A performance row is
:meth:`PerformanceService.for_employees`. If a rule appears to be missing from a
manager screen, it is missing from the module that owns it, which is where it
should be fixed.

What this module owns is two things a shared service cannot:

**Whose team.** Every method takes an :class:`EmployeeScope` built by
:meth:`EmployeeScope.of_direct_reports` from the signed-in user's reporting
line. No method takes a manager id, so "show me a team" cannot be turned into
"show me *that* team" by editing a request. The scope is passed down into the
shared services, so their existing checks do the enforcing -- the manager module
does not carry a second copy of "may I see this row".

**Composition.** A team screen is a roster crossed with today's attendance,
today's approved leave and today's allocations; a dashboard is that plus four
approval queues and a holiday list. Those live in four modules, and asking the
browser to assemble them would make the first screen a manager opens the slowest
one they have.

One rule *is* stated here, because no other module could state it: **a manager
does not decide their own request.** The scope already refuses it -- the caller
is deliberately not a member of their own team scope -- but the refusal deserves
to say why, so the three decision methods check it explicitly first and answer
``own_request`` rather than ``outside_your_team``.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.core.exceptions import PermissionDeniedError
from app.models.employee import Employee
from app.models.enums import (
    ApprovalStatus,
    AttendanceStatus,
    DocumentStatus,
    TimesheetStatus,
)
from app.models.project import EmployeeAllocation
from app.models.workforce import AttendanceRecord, LeaveRequest, Timesheet
from app.repositories.project_repository import AllocationRepository
from app.schemas.employee import EmployeeListParams, EmployeeSummary
from app.schemas.manager import (
    ManagerDashboard,
    TeamAllocation,
    TeamAllocationSummary,
    TeamAttendanceParams,
    TeamAttendanceRow,
    TeamAttendanceSummary,
    TeamCalendar,
    TeamCalendarEntry,
    TeamDocumentStatus,
    TeamHoliday,
    TeamLeaveBalance,
    TeamLeaveParams,
    TeamLeaveRow,
    TeamListParams,
    TeamMember,
    TeamMemberProfile,
    TeamPerformance,
    TeamProject,
    TeamProjectMember,
    TeamRegularizationParams,
    TeamRegularizationRow,
    TeamTimesheetParams,
    TeamTimesheetRow,
    TeamTimesheetSummary,
)
from app.schemas.masters import MasterSummary
from app.schemas.workforce import (
    ApprovalDecision,
    AttendanceListParams,
    AttendanceRead,
    LeaveListParams,
    LeaveRequestRead,
    RegularizationListParams,
    RegularizationRead,
    TimesheetListParams,
    TimesheetRead,
)
from app.services.document_service import DocumentService
from app.services.employee_service import EmployeeService
from app.services.performance_service import PerformanceService
from app.services.scope_service import EmployeeScope
from app.services.workforce_service import WorkforceService

#: The largest page the shared list params accept. Every composition below reads
#: a whole team in one request rather than paging, and this is the ceiling that
#: makes that safe to assume.
PAGE_LIMIT = 100

#: How many rows the calendar will assemble before it stops. A month of one
#: team's exceptions is far below this; the cap exists so a pathological team
#: cannot turn one screen into an unbounded read.
CALENDAR_ROW_LIMIT = 500

#: How far ahead the dashboard looks for holidays, and how many it shows.
DASHBOARD_HOLIDAY_COUNT = 5

#: How many rows sit behind each of the dashboard's approval counts.
DASHBOARD_QUEUE_COUNT = 5

#: Documents nobody has decided about yet.
UNDECIDED_DOCUMENT_STATUSES = frozenset({DocumentStatus.UPLOADED.value, DocumentStatus.UNDER_REVIEW.value})


@dataclass(frozen=True)
class TeamDirectory:
    """The team, resolved once per request and passed around as a value.

    Three facts about the same people, read together because they come from the
    same rows: who they are, when they joined, and where they work. Carrying
    them on one object rather than as service attributes keeps the methods below
    functions of their arguments -- the alternative was state left over from a
    previous call, which is the kind of thing that works until two screens share
    a service instance.
    """

    summaries: dict[uuid.UUID, EmployeeSummary]
    joining_dates: dict[uuid.UUID, date]
    locations: frozenset[uuid.UUID]

    @property
    def ids(self) -> list[uuid.UUID]:
        return list(self.summaries)

    def __len__(self) -> int:
        return len(self.summaries)

    def name(self, employee_id: uuid.UUID) -> str:
        summary = self.summaries.get(employee_id)
        return summary.full_name if summary else "A team member"


class ManagerService:
    """The reporting line's view of modules that already exist."""

    def __init__(
        self,
        *,
        workforce: WorkforceService,
        employees: EmployeeService,
        performance: PerformanceService,
        documents: DocumentService,
        allocations: AllocationRepository,
    ) -> None:
        self.workforce = workforce
        self.employees = employees
        self.performance = performance
        # ``vault`` rather than ``documents``: this class has a
        # ``document_status`` method and the naming stays parallel with the
        # self-service module, which had the same collision.
        self.vault = documents
        self.allocations = allocations

    # ==================================================================
    # The team
    # ==================================================================
    async def team(self, params: TeamListParams, *, scope: EmployeeScope) -> tuple[list[TeamMember], int]:
        """The roster, filtered inside the reporting line.

        The project filter is resolved to a set of employee ids and
        *intersected* with the team before the directory query runs. Order
        matters: a filter applied after the fact could only ever remove rows the
        scope had already allowed, but one that could reach outside the team
        would be a filter that widened access, which is the failure this module
        exists to prevent.
        """
        today = self._today()
        visible = set(scope.employee_ids)
        if params.project_id is not None:
            visible &= await self.allocations.employee_ids_on_project(params.project_id, today)

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
            ),
            scope=EmployeeScope.of_direct_reports(visible),
        )
        return await self._as_members(rows, on=today), total

    async def member(self, employee_id: uuid.UUID, *, scope: EmployeeScope) -> TeamMemberProfile:
        """One team member's profile.

        The only place in this module where an employee id arrives from the
        client, and the first thing done with it is to check it against the
        reporting line. Nothing is read before that check, so an id belonging to
        another manager's report is refused rather than answered.
        """
        scope.assert_allows(employee_id, field="employee_id")
        employee = await self.employees.get_by_id(employee_id)

        today = self._today()
        member = (await self._as_members([employee], on=today))[0]
        one_person = EmployeeScope.of_direct_reports({employee_id})

        performance = await self.performance.for_employees([employee_id])
        return TeamMemberProfile(
            member=member,
            joining_date=employee.joining_date,
            confirmation_date=employee.confirmation_date,
            reporting_manager=(
                EmployeeSummary.model_validate(employee.reporting_manager)
                if employee.reporting_manager
                else None
            ),
            work_mode=employee.work_mode,
            attendance=await self._attendance_summary(
                employee_id, today.replace(day=1), today, scope=one_person
            ),
            leave=await self._leave_balances(employee_id),
            timesheets=await self._timesheet_summary(scope=one_person),
            performance=(
                self._as_performance(performance[0], EmployeeSummary.model_validate(employee))
                if performance
                else None
            ),
        )

    # ==================================================================
    # Attendance
    # ==================================================================
    async def attendance(
        self, params: TeamAttendanceParams, *, scope: EmployeeScope
    ) -> tuple[list[TeamAttendanceRow], int]:
        self._assert_filter_in_scope(params.employee_id, scope)
        rows, total = await self.workforce.list_attendance(
            AttendanceListParams(
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
            TeamAttendanceRow(
                employee=directory.summaries[row.employee_id], record=AttendanceRead.model_validate(row)
            )
            for row in rows
            if row.employee_id in directory.summaries
        ], total

    async def regularizations(
        self, params: TeamRegularizationParams, *, scope: EmployeeScope
    ) -> tuple[list[TeamRegularizationRow], int]:
        self._assert_filter_in_scope(params.employee_id, scope)
        rows, total = await self.workforce.list_regularizations(
            RegularizationListParams(
                page=params.page,
                page_size=params.page_size,
                employee_id=params.employee_id,
                status=params.status,
            ),
            scope=scope,
        )
        return await self._as_regularization_rows(rows), total

    async def decide_regularization(
        self,
        manager: Employee,
        request_id: uuid.UUID,
        decision: ApprovalDecision,
        *,
        actor_id: uuid.UUID,
        scope: EmployeeScope,
    ) -> RegularizationRead:
        request = await self.workforce.get_regularization(request_id)
        self._assert_decidable(manager, request.employee_id, scope)
        decided = await self.workforce.decide_regularization(
            request_id, decision.approved, decision.notes, actor_id=actor_id, scope=scope
        )
        return RegularizationRead.model_validate(decided)

    # ==================================================================
    # Leave
    # ==================================================================
    async def leave(self, params: TeamLeaveParams, *, scope: EmployeeScope) -> tuple[list[TeamLeaveRow], int]:
        self._assert_filter_in_scope(params.employee_id, scope)
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
        return await self._as_leave_rows(rows), total

    async def decide_leave(
        self,
        manager: Employee,
        request_id: uuid.UUID,
        decision: ApprovalDecision,
        *,
        actor_id: uuid.UUID,
        scope: EmployeeScope,
    ) -> LeaveRequestRead:
        request = await self.workforce.get_leave_request(request_id)
        self._assert_decidable(manager, request.employee_id, scope)
        decided = await self.workforce.decide_leave(
            request_id, decision.approved, decision.notes, actor_id=actor_id, scope=scope
        )
        return LeaveRequestRead.model_validate(decided)

    # ==================================================================
    # Timesheets
    # ==================================================================
    async def timesheets(
        self, params: TeamTimesheetParams, *, scope: EmployeeScope
    ) -> tuple[list[TeamTimesheetRow], int]:
        self._assert_filter_in_scope(params.employee_id, scope)
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
        return await self._as_timesheet_rows(rows), total

    async def timesheet(self, timesheet_id: uuid.UUID, *, scope: EmployeeScope) -> TimesheetRead:
        return TimesheetRead.model_validate(await self.workforce.get_timesheet(timesheet_id, scope=scope))

    async def decide_timesheet(
        self,
        manager: Employee,
        timesheet_id: uuid.UUID,
        decision: ApprovalDecision,
        *,
        actor_id: uuid.UUID,
        scope: EmployeeScope,
    ) -> TimesheetRead:
        """Approve a week, or return it for correction.

        "Request correction" is a rejection carrying notes: the workforce module
        already models that state, and a rejected week is the one state an
        employee may save over. Adding a fourth outcome here would be a second
        way to say the same thing, and the two would drift.
        """
        sheet = await self.workforce.get_timesheet(timesheet_id)
        self._assert_decidable(manager, sheet.employee_id, scope)
        decided = await self.workforce.decide_timesheet(
            timesheet_id, decision.approved, decision.notes, actor_id=actor_id, scope=scope
        )
        return TimesheetRead.model_validate(decided)

    # ==================================================================
    # Projects
    # ==================================================================
    async def projects(self, *, scope: EmployeeScope) -> list[TeamProject]:
        """Projects the team is on today, read-only.

        Read-only by construction rather than by a flag: this module has no
        method that writes an allocation. A manager who is also entitled to move
        people between projects does that on the Project Allocation screens,
        which are guarded by ``projects:update``.
        """
        today = self._today()
        directory = await self._directory(scope.employee_ids)
        allocations = await self.allocations.current_for_employees(directory.ids, today)

        grouped: dict[uuid.UUID, list[EmployeeAllocation]] = {}
        for allocation in allocations:
            grouped.setdefault(allocation.project_id, []).append(allocation)

        projects: list[TeamProject] = []
        for rows in grouped.values():
            project = rows[0].project
            total = sum(row.allocation_percentage for row in rows)
            billable = sum(row.allocation_percentage for row in rows if row.billable)
            projects.append(
                TeamProject(
                    project_id=project.id,
                    project_code=project.project_code,
                    project_name=project.project_name,
                    client_name=project.client.client_name if project.client else None,
                    status=project.status,
                    start_date=project.start_date,
                    end_date=project.end_date,
                    team_size=len({row.employee_id for row in rows}),
                    total_allocation=total,
                    billable_percentage=int(billable * 100 / total) if total else 0,
                    members=[
                        TeamProjectMember(
                            employee=directory.summaries[row.employee_id],
                            allocation_percentage=row.allocation_percentage,
                            billable=row.billable,
                            start_date=row.start_date,
                            end_date=row.end_date,
                        )
                        for row in rows
                        if row.employee_id in directory.summaries
                    ],
                )
            )
        projects.sort(key=lambda item: (-item.team_size, item.project_name))
        return projects

    # ==================================================================
    # Performance
    # ==================================================================
    async def team_performance(
        self, *, scope: EmployeeScope, cycle_id: uuid.UUID | None = None
    ) -> list[TeamPerformance]:
        directory = await self._directory(scope.employee_ids)
        rows = await self.performance.for_employees(directory.ids, cycle_id=cycle_id)
        return [
            self._as_performance(row, directory.summaries[row["employee_id"]])
            for row in rows
            if row["employee_id"] in directory.summaries
        ]

    # ==================================================================
    # Calendar
    # ==================================================================
    async def calendar(self, year: int, month: int, *, scope: EmployeeScope) -> TeamCalendar:
        """One month of everything dated that concerns the team.

        Four kinds of entry in one stream -- approved leave, the holidays that
        apply where the team works, attendance exceptions and joining dates --
        because that is how a month is read. Four parallel lists would have to be
        merged and sorted by whoever rendered them.
        """
        start = date(year, month, 1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        directory = await self._directory(scope.employee_ids)

        entries: list[TeamCalendarEntry] = []

        leave = await self._drain(
            lambda page: self.workforce.list_leave(
                LeaveListParams(
                    page=page,
                    page_size=PAGE_LIMIT,
                    status=ApprovalStatus.APPROVED,
                    from_date=start,
                    to_date=end,
                ),
                scope=scope,
            ),
            limit=CALENDAR_ROW_LIMIT,
        )
        for request in leave:
            name = directory.name(request.employee_id)
            for day in self._days_between(max(request.from_date, start), min(request.to_date, end)):
                entries.append(
                    TeamCalendarEntry(
                        day=day,
                        kind="leave",
                        label=f"{name} on leave",
                        employee_id=request.employee_id,
                        employee_name=name,
                        detail=request.leave_type.name if request.leave_type else None,
                    )
                )

        for holiday in await self._holidays(directory.locations, year):
            if start <= holiday.holiday_date <= end:
                entries.append(
                    TeamCalendarEntry(
                        day=holiday.holiday_date,
                        kind="holiday",
                        label=holiday.name,
                        detail=holiday.calendar_name,
                    )
                )

        attendance = await self._drain(
            lambda page: self.workforce.list_attendance(
                AttendanceListParams(page=page, page_size=PAGE_LIMIT, from_date=start, to_date=end),
                scope=scope,
            ),
            limit=CALENDAR_ROW_LIMIT,
        )
        for record in attendance:
            exception = self._attendance_exception(record)
            if exception is None:
                continue
            name = directory.name(record.employee_id)
            entries.append(
                TeamCalendarEntry(
                    day=record.attendance_date,
                    kind="exception",
                    label=f"{name}: {exception}",
                    employee_id=record.employee_id,
                    employee_name=name,
                    detail=exception,
                )
            )

        for employee_id, summary in directory.summaries.items():
            joining = directory.joining_dates.get(employee_id)
            if joining is not None and start <= joining <= end:
                entries.append(
                    TeamCalendarEntry(
                        day=joining,
                        kind="joining",
                        label=f"{summary.full_name} joins",
                        employee_id=employee_id,
                        employee_name=summary.full_name,
                    )
                )

        entries.sort(key=lambda item: (item.day, item.kind, item.label))
        return TeamCalendar(year=year, month=month, entries=entries)

    # ==================================================================
    # Document completion
    # ==================================================================
    async def document_status(self, *, scope: EmployeeScope) -> list[TeamDocumentStatus]:
        """Counts per team member. Never a document, never a file.

        Reachable only with ``documents:view``, which the Manager role holds and
        the Team Lead role does not -- so the seat that is not entitled to the
        vault does not get a summary of it either.
        """
        directory = await self._directory(scope.employee_ids)
        counts = await self.vault.status_counts_for_employees(directory.ids, scope=scope)

        rows = [
            TeamDocumentStatus(
                employee=summary,
                total=sum(counts.get(employee_id, {}).values()),
                approved=counts.get(employee_id, {}).get(DocumentStatus.APPROVED.value, 0),
                pending=sum(
                    count
                    for status, count in counts.get(employee_id, {}).items()
                    if status in UNDECIDED_DOCUMENT_STATUSES
                ),
                rejected=counts.get(employee_id, {}).get(DocumentStatus.REJECTED.value, 0),
            )
            for employee_id, summary in directory.summaries.items()
        ]
        rows.sort(key=lambda item: item.employee.full_name)
        return rows

    # ==================================================================
    # Dashboard
    # ==================================================================
    async def dashboard(self, manager: Employee, *, scope: EmployeeScope) -> ManagerDashboard:
        """One screen, assembled from five modules, about one reporting line."""
        today = self._today()
        directory = await self._directory(scope.employee_ids)

        attendance_today, _ = await self.workforce.list_attendance(
            AttendanceListParams(page=1, page_size=PAGE_LIMIT, from_date=today, to_date=today),
            scope=scope,
        )
        leave_today, _ = await self.workforce.list_leave(
            LeaveListParams(
                page=1,
                page_size=PAGE_LIMIT,
                status=ApprovalStatus.APPROVED,
                from_date=today,
                to_date=today,
            ),
            scope=scope,
        )
        on_leave = {request.employee_id for request in leave_today}

        pending_leave, leave_total = await self.workforce.list_leave(
            LeaveListParams(page=1, page_size=DASHBOARD_QUEUE_COUNT, status=ApprovalStatus.PENDING),
            scope=scope,
        )
        pending_timesheets, timesheet_total = await self.workforce.list_timesheets(
            TimesheetListParams(page=1, page_size=DASHBOARD_QUEUE_COUNT, status=TimesheetStatus.SUBMITTED),
            scope=scope,
        )
        pending_corrections, correction_total = await self.workforce.list_regularizations(
            RegularizationListParams(page=1, page_size=DASHBOARD_QUEUE_COUNT, status=ApprovalStatus.PENDING),
            scope=scope,
        )

        allocations = await self.allocations.current_for_employees(directory.ids, today)
        performance = await self.performance.for_employees(directory.ids)
        holidays = [
            holiday
            for holiday in await self._holidays(directory.locations, today.year)
            if holiday.holiday_date >= today
        ]

        recorded = {record.employee_id for record in attendance_today}
        present = sum(
            1
            for record in attendance_today
            if record.status in {AttendanceStatus.PRESENT.value, AttendanceStatus.HALF_DAY.value}
        )
        absent = sum(1 for record in attendance_today if record.status == AttendanceStatus.ABSENT.value)

        return ManagerDashboard(
            manager=EmployeeSummary.model_validate(manager),
            on_date=today,
            team_size=len(directory),
            present_today=present,
            absent_today=absent,
            # Counted from approved leave rather than from the attendance status,
            # because a day marked as leave is written when the request is
            # approved and a request approved this morning has not touched
            # today's row yet.
            on_leave_today=len(on_leave),
            not_recorded_today=len(set(directory.ids) - recorded - on_leave),
            pending_leave_approvals=leave_total,
            pending_timesheet_approvals=timesheet_total,
            pending_regularizations=correction_total,
            pending_performance_reviews=sum(1 for row in performance if row["review_due"]),
            upcoming_holidays=holidays[:DASHBOARD_HOLIDAY_COUNT],
            active_projects=len({allocation.project_id for allocation in allocations}),
            allocation=self._allocation_summary(directory, allocations),
            leave_awaiting_decision=await self._as_leave_rows(pending_leave),
            timesheets_awaiting_decision=await self._as_timesheet_rows(pending_timesheets),
            regularizations_awaiting_decision=await self._as_regularization_rows(pending_corrections),
        )

    # ==================================================================
    # Row assembly
    # ==================================================================
    async def _as_members(self, employees: Sequence[Employee], *, on: date) -> list[TeamMember]:
        """Decorate a page of employees with today's attendance, leave and allocation.

        Three queries for the whole page rather than three per row. The page is
        capped at :data:`PAGE_LIMIT`, and each of the three returns at most one
        row per employee per day, so a single unpaged read covers it.
        """
        ids = [employee.id for employee in employees]
        if not ids:
            return []

        page_scope = EmployeeScope.of_direct_reports(ids)
        attendance, _ = await self.workforce.list_attendance(
            AttendanceListParams(page=1, page_size=PAGE_LIMIT, from_date=on, to_date=on),
            scope=page_scope,
        )
        leave, _ = await self.workforce.list_leave(
            LeaveListParams(
                page=1,
                page_size=PAGE_LIMIT,
                status=ApprovalStatus.APPROVED,
                from_date=on,
                to_date=on,
            ),
            scope=page_scope,
        )
        allocations = await self.allocations.current_for_employees(ids, on)

        by_day = {record.employee_id: record for record in attendance}
        on_leave = {request.employee_id: request for request in leave}
        allocated: dict[uuid.UUID, list[EmployeeAllocation]] = {}
        for allocation in allocations:
            allocated.setdefault(allocation.employee_id, []).append(allocation)

        return [
            self._as_member(employee, by_day.get(employee.id), on_leave.get(employee.id), allocated)
            for employee in employees
        ]

    def _as_member(
        self,
        employee: Employee,
        record: AttendanceRecord | None,
        leave: LeaveRequest | None,
        allocated: dict[uuid.UUID, list[EmployeeAllocation]],
    ) -> TeamMember:
        rows = allocated.get(employee.id, [])
        return TeamMember(
            id=employee.id,
            employee_code=employee.employee_code,
            full_name=employee.full_name,
            photo_url=employee.photo_url,
            official_email=employee.official_email,
            employment_status=employee.employment_status,
            designation=self._master(employee.designation),
            business_unit=self._master(employee.business_unit),
            team=self._master(employee.team),
            work_location=self._master(employee.work_location),
            employment_type=self._master(employee.employment_type),
            allocations=[
                TeamAllocation(
                    project_id=row.project_id,
                    project_code=row.project.project_code,
                    project_name=row.project.project_name,
                    client_name=row.project.client.client_name if row.project.client else None,
                    allocation_percentage=row.allocation_percentage,
                    billable=row.billable,
                )
                for row in rows
            ],
            allocated_percentage=sum((row.allocation_percentage for row in rows), start=Decimal(0)),
            attendance_status=AttendanceStatus(record.status) if record else None,
            checked_in_at=record.check_in_at if record else None,
            checked_out_at=record.check_out_at if record else None,
            on_leave_type=(leave.leave_type.name if leave and leave.leave_type else None),
        )

    async def _as_leave_rows(self, rows: Sequence[LeaveRequest]) -> list[TeamLeaveRow]:
        directory = await self._directory({row.employee_id for row in rows})
        return [
            TeamLeaveRow(
                employee=directory.summaries[row.employee_id],
                request=LeaveRequestRead.model_validate(row),
            )
            for row in rows
            if row.employee_id in directory.summaries
        ]

    async def _as_timesheet_rows(self, rows: Sequence[Timesheet]) -> list[TeamTimesheetRow]:
        directory = await self._directory({row.employee_id for row in rows})
        return [
            TeamTimesheetRow(
                employee=directory.summaries[row.employee_id],
                timesheet=TimesheetRead.model_validate(row),
            )
            for row in rows
            if row.employee_id in directory.summaries
        ]

    async def _as_regularization_rows(self, rows: Sequence[Any]) -> list[TeamRegularizationRow]:
        directory = await self._directory({row.employee_id for row in rows})
        return [
            TeamRegularizationRow(
                employee=directory.summaries[row.employee_id],
                request=RegularizationRead.model_validate(row),
            )
            for row in rows
            if row.employee_id in directory.summaries
        ]

    @staticmethod
    def _as_performance(row: dict[str, Any], employee: EmployeeSummary) -> TeamPerformance:
        return TeamPerformance(
            employee=employee,
            cycle_id=row["cycle_id"],
            cycle_name=row["cycle_name"],
            goals=row["goals"],
            goals_completed=row["goals_completed"],
            goal_progress=row["goal_progress"],
            self_review_status=row["self_review_status"],
            manager_review_status=row["manager_review_status"],
            current_rating=row["current_rating"],
            review_due=row["review_due"],
        )

    # ==================================================================
    # Summaries
    # ==================================================================
    async def _attendance_summary(
        self, employee_id: uuid.UUID, start: date, end: date, *, scope: EmployeeScope
    ) -> TeamAttendanceSummary:
        rows, _ = await self.workforce.list_attendance(
            AttendanceListParams(
                page=1, page_size=PAGE_LIMIT, employee_id=employee_id, from_date=start, to_date=end
            ),
            scope=scope,
        )
        return TeamAttendanceSummary(
            from_date=start,
            to_date=end,
            present_days=sum(1 for row in rows if row.status == AttendanceStatus.PRESENT.value),
            absent_days=sum(1 for row in rows if row.status == AttendanceStatus.ABSENT.value),
            leave_days=sum(1 for row in rows if row.status == AttendanceStatus.LEAVE.value),
            half_days=sum(1 for row in rows if row.status == AttendanceStatus.HALF_DAY.value),
            late_arrivals=sum(1 for row in rows if row.late_minutes > 0),
            early_exits=sum(1 for row in rows if row.early_exit_minutes > 0),
            worked_minutes=sum(row.worked_minutes for row in rows),
            overtime_minutes=sum(row.overtime_minutes for row in rows),
        )

    async def _leave_balances(self, employee_id: uuid.UUID) -> list[TeamLeaveBalance]:
        return [
            TeamLeaveBalance(
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

    async def _timesheet_summary(self, *, scope: EmployeeScope) -> TeamTimesheetSummary:
        rows = await self._drain(
            lambda page: self.workforce.list_timesheets(
                TimesheetListParams(page=page, page_size=PAGE_LIMIT), scope=scope
            ),
            limit=CALENDAR_ROW_LIMIT,
        )
        return TeamTimesheetSummary(
            draft=sum(1 for row in rows if row.status == TimesheetStatus.DRAFT.value),
            submitted=sum(1 for row in rows if row.status == TimesheetStatus.SUBMITTED.value),
            approved=sum(1 for row in rows if row.status == TimesheetStatus.APPROVED.value),
            rejected=sum(1 for row in rows if row.status == TimesheetStatus.REJECTED.value),
            total_hours=sum((row.total_hours for row in rows), start=Decimal(0)),
            billable_hours=sum((row.billable_hours for row in rows), start=Decimal(0)),
        )

    @staticmethod
    def _allocation_summary(
        directory: TeamDirectory, allocations: Sequence[EmployeeAllocation]
    ) -> TeamAllocationSummary:
        per_employee: dict[uuid.UUID, Decimal] = {}
        billable: set[uuid.UUID] = set()
        for allocation in allocations:
            per_employee[allocation.employee_id] = (
                per_employee.get(allocation.employee_id, Decimal(0)) + allocation.allocation_percentage
            )
            if allocation.billable:
                billable.add(allocation.employee_id)

        allocated = len(per_employee)
        return TeamAllocationSummary(
            allocated_members=allocated,
            unallocated_members=max(0, len(directory) - allocated),
            average_allocation=int(sum(per_employee.values()) / allocated) if allocated else 0,
            billable_members=len(billable),
            active_projects=len({allocation.project_id for allocation in allocations}),
        )

    async def _holidays(self, locations: Collection[uuid.UUID], year: int) -> list[TeamHoliday]:
        """The holidays that apply where this team works.

        A calendar with no location applies everywhere; a located one applies
        only to the people placed there. Returning every location's calendar
        would tell a manager in Hyderabad about a holiday nobody on their team
        is taking.

        Read once and filtered here rather than asked for per location:
        ``list_calendars`` given a location returns that one *plus* every
        location-less calendar, so calling it per location would return the
        national calendar as many times as the team has offices.
        """
        calendars = await self.workforce.list_calendars(year, None)
        rows = [
            TeamHoliday(
                id=holiday.id,
                name=holiday.name,
                holiday_date=holiday.holiday_date,
                holiday_type=holiday.holiday_type,
                calendar_name=calendar.name,
            )
            for calendar in calendars
            if calendar.location_id is None or calendar.location_id in locations
            for holiday in calendar.holidays
        ]
        rows.sort(key=lambda item: item.holiday_date)
        return rows

    # ==================================================================
    # Helpers
    # ==================================================================
    async def _directory(self, employee_ids: Collection[uuid.UUID]) -> TeamDirectory:
        """Resolve a set of team ids to the people behind them.

        Read through :meth:`EmployeeService.list` with a scope built from the
        very ids being asked for, so this cannot become a way to look up an
        employee the caller was not already entitled to: an id that was not in
        the scope its caller passed in is not in the scope this builds either.
        """
        ids = list(employee_ids)
        if not ids:
            return TeamDirectory(summaries={}, joining_dates={}, locations=frozenset())

        rows = await self._drain(
            lambda page: self.employees.list(
                EmployeeListParams(page=page, page_size=PAGE_LIMIT),
                scope=EmployeeScope.of_direct_reports(ids),
            ),
            limit=CALENDAR_ROW_LIMIT,
        )
        return TeamDirectory(
            summaries={row.id: EmployeeSummary.model_validate(row) for row in rows},
            joining_dates={row.id: row.joining_date for row in rows},
            locations=frozenset(row.work_location_id for row in rows if row.work_location_id),
        )

    @staticmethod
    async def _drain(
        fetch: Callable[[int], Awaitable[tuple[Sequence[Any], int]]], *, limit: int
    ) -> list[Any]:
        """Read every page of a paged query, up to a hard ceiling.

        The shared list params cap a page at 100, and several of the
        compositions above genuinely need the whole set -- a month of a team's
        attendance does not fit in one page. The ceiling is what stops that
        turning into an unbounded read on a pathological team.
        """
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
    def _assert_filter_in_scope(employee_id: uuid.UUID | None, scope: EmployeeScope) -> None:
        """An "employee" filter narrows the team; it never reaches outside it.

        Refused rather than silently emptied. The repository would already
        return nothing -- the scope and the filter are both applied -- but an
        empty page and a refusal say different things, and a manager who has
        typed the wrong id deserves the second.
        """
        if employee_id is not None:
            scope.assert_allows(employee_id, field="employee_id")

    @staticmethod
    def _assert_decidable(manager: Employee, employee_id: uuid.UUID, scope: EmployeeScope) -> None:
        """Whose request a manager may decide: their team's, and not their own.

        The scope refuses both cases on its own -- the manager is deliberately
        not in their own team scope -- so this exists for the message. "You can
        only see records for the people who report to you" is a puzzling answer
        to somebody looking at their own leave request.
        """
        if employee_id == manager.id:
            raise PermissionDeniedError(
                "You cannot decide your own request. It goes to your own manager.",
                details=[{"code": "own_request", "message": "employee_id"}],
            )
        scope.assert_allows(employee_id, field="employee_id")

    @staticmethod
    def _attendance_exception(record: AttendanceRecord) -> str | None:
        """What is notable about a day, or ``None`` when nothing is."""
        if record.status == AttendanceStatus.ABSENT.value:
            return "absent"
        if record.status == AttendanceStatus.HALF_DAY.value:
            return "half day"
        if record.late_minutes > 0:
            return f"late by {record.late_minutes} min"
        if record.early_exit_minutes > 0:
            return f"left {record.early_exit_minutes} min early"
        return None

    @staticmethod
    def _master(record: Any) -> MasterSummary | None:
        return MasterSummary.model_validate(record) if record is not None else None

    @staticmethod
    def _days_between(start: date, end: date) -> list[date]:
        if end < start:
            return []
        return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]

    @staticmethod
    def _today() -> date:
        return datetime.now(UTC).date()
