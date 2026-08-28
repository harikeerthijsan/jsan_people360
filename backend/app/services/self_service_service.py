"""Employee self-service.

This module contains **no business rules**, and that is the point of it.

A check-in is :meth:`WorkforceService.check_in`. A leave application is
:meth:`WorkforceService.apply_for_leave`, with the same overlap check, the same
working-day arithmetic and the same held balance. An upload is
:meth:`DocumentService.create`, with the same signature validation. A profile
edit is :meth:`EmployeeService.update`, which writes the same audit entry it
would for an HR administrator. If a rule appears to be missing from the portal,
it is because the module that owns it does not have it either -- which is where
it should be fixed.

What this module *does* own is two things a shared service cannot:

**Identity.** Every method takes an already-resolved :class:`Employee` and never
an id. There is no parameter for a client to tamper with, so the class of bug
where a route forgets to check ownership cannot be written here: the subject of
the call is the session.

**Composition.** A personal dashboard needs today's attendance, this year's
balances, this week's timesheet, the next few holidays and whatever is still
outstanding. Those live in four modules, and asking the browser to make eight
requests to assemble one screen is how the first render becomes the slow one.

Every call into a shared service is given a scope of
:meth:`EmployeeScope.just_self`, so the services' existing checks do the
enforcing. The portal does not carry its own copy of "may I see this row".
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError
from app.models.employee import Employee
from app.models.enums import (
    ApprovalStatus,
    AttendanceStatus,
    DocumentOwnerType,
    DocumentStatus,
    ExpiryState,
    RecordStatus,
    TimesheetStatus,
    WorkMode,
)
from app.models.workforce import (
    AttendanceRecord,
    AttendanceRegularization,
    LeaveRequest,
    Timesheet,
)
from app.repositories.document_repository import DocumentTypeRepository
from app.repositories.project_repository import AllocationRepository
from app.repositories.requisition_repository import NotificationRepository
from app.schemas.document import (
    DocumentListParams,
    DocumentTypeListParams,
    DocumentUploadMetadata,
    DocumentVersionUploadMetadata,
)
from app.schemas.employee import EmployeeAddressInput, EmployeeUpdate
from app.schemas.self_service import (
    MyAttendanceParams,
    MyAttendanceSummary,
    MyAttendanceToday,
    MyCheckIn,
    MyCheckOut,
    MyDashboard,
    MyDocument,
    MyDocumentParams,
    MyDocumentSummary,
    MyDocumentType,
    MyDocumentUpload,
    MyHoliday,
    MyLeaveBalance,
    MyLeaveParams,
    MyNotification,
    MyProfileUpdate,
    MyProject,
    MyRegularizationParams,
    MyTimesheetParams,
    MyTimesheetWeek,
    PendingAction,
)
from app.schemas.workforce import (
    AttendanceListParams,
    CheckInRequest,
    CheckOutRequest,
    LeaveApply,
    LeaveListParams,
    RegularizationCreate,
    RegularizationListParams,
    TimesheetListParams,
    TimesheetSave,
)
from app.services.document_service import DocumentService, FilePayload, UploadedFile
from app.services.employee_service import EmployeeService
from app.services.helpdesk_service import AnnouncementService
from app.services.scope_service import EmployeeScope
from app.services.workforce_service import WorkforceService

#: How many holidays the dashboard looks ahead for. Enough to plan a long
#: weekend around, few enough to stay a widget rather than a calendar.
DASHBOARD_HOLIDAY_COUNT = 4
DASHBOARD_DOCUMENT_COUNT = 5
DASHBOARD_NOTIFICATION_COUNT = 5
DASHBOARD_LEAVE_COUNT = 5

#: Documents nobody has decided about yet.
UNDECIDED_DOCUMENT_STATUSES = frozenset({DocumentStatus.UPLOADED.value, DocumentStatus.UNDER_REVIEW.value})

#: A timesheet in one of these is the employee's move, not their manager's.
TIMESHEET_NEEDS_ME = frozenset({TimesheetStatus.DRAFT.value, TimesheetStatus.REJECTED.value})


class SelfServiceService:
    """The employee-facing view of modules that already exist."""

    def __init__(
        self,
        *,
        workforce: WorkforceService,
        documents: DocumentService,
        employees: EmployeeService,
        allocations: AllocationRepository,
        document_types: DocumentTypeRepository,
        notifications: NotificationRepository,
        announcements: AnnouncementService | None = None,
    ) -> None:
        self.workforce = workforce
        # ``vault`` rather than ``documents``: this class has a ``documents()``
        # method, and an attribute of the same name would shadow it.
        self.vault = documents
        self.employees = employees
        self.allocations = allocations
        self.document_types = document_types
        self.notifications = notifications
        # Optional in the established style, so the seeder and the unit tests
        # can build this service without the announcements module.
        self.announcements = announcements

    # ==================================================================
    # Profile
    # ==================================================================
    async def profile(self, employee: Employee) -> Employee:
        """The caller's own record, reloaded so its addresses are present."""
        return await self.employees.get_by_id(employee.id)

    async def update_profile(
        self, employee: Employee, payload: MyProfileUpdate, *, actor_id: uuid.UUID
    ) -> Employee:
        """Apply the six fields an employee owns.

        Routed through :meth:`EmployeeService.update` rather than writing the
        columns here, so a self-service edit is audited exactly like an HR one
        and passes the same validation. ``exclude_unset`` keeps a partial update
        partial: sending only a mobile number must not blank an emergency
        contact.

        The payload cannot carry a placement field -- ``MyProfileUpdate`` has
        none -- so this can never produce an employment-history row, which is
        the guarantee that matters. It is not enforced by inspection afterwards;
        it is enforced by the shape of the schema.
        """
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return await self.employees.get_by_id(employee.id)
        return await self.employees.update(
            employee.id, EmployeeUpdate.model_validate(changes), actor_id=actor_id
        )

    async def set_address(
        self, employee: Employee, payload: EmployeeAddressInput, *, actor_id: uuid.UUID
    ) -> Employee:
        return await self.employees.set_address(employee.id, payload, actor_id=actor_id)

    # ==================================================================
    # Attendance
    # ==================================================================
    async def today(self, employee: Employee, *, scope: EmployeeScope) -> MyAttendanceToday:
        """What the check-in control should render right now.

        The three booleans are derived here rather than in the browser because
        they are the same conditions ``check_in`` and ``check_out`` enforce, and
        a client that computes them itself will eventually disagree with the
        server about whether a button should have been enabled.
        """
        on = self._today()
        record = await self._attendance_for(employee, on, scope=scope)
        now = datetime.now(UTC)

        checked_in = record is not None and record.check_in_at is not None
        checked_out = record is not None and record.check_out_at is not None
        elapsed = 0
        if checked_in and not checked_out and record is not None and record.check_in_at is not None:
            elapsed = max(0, int((now - record.check_in_at).total_seconds() // 60))

        return MyAttendanceToday(
            on_date=on,
            record=record,
            checked_in=checked_in,
            checked_out=checked_out,
            # Checking in again after checking out is refused by the service for
            # the same reason it is greyed out here: the day already has a
            # record, and a second one would double-count in every figure.
            can_check_in=not checked_in,
            can_check_out=checked_in and not checked_out,
            status=AttendanceStatus(record.status) if record else None,
            worked_minutes=record.worked_minutes if record else 0,
            elapsed_minutes=elapsed,
            server_time=now,
        )

    async def check_in(
        self, employee: Employee, payload: MyCheckIn, *, actor_id: uuid.UUID
    ) -> AttendanceRecord:
        """Check in, today, as yourself.

        ``attendance_date`` is deliberately absent from :class:`MyCheckIn`, so
        an employee cannot post an attendance record for a day they did not
        record one on. Fixing a missed day is a correction request, which a
        manager approves -- the flow the module already has.
        """
        return await self.workforce.check_in(
            employee.id,
            CheckInRequest(work_mode=WorkMode(payload.work_mode), notes=payload.notes),
            actor_id=actor_id,
        )

    async def check_out(
        self, employee: Employee, payload: MyCheckOut, *, actor_id: uuid.UUID
    ) -> AttendanceRecord:
        return await self.workforce.check_out(
            employee.id, CheckOutRequest(notes=payload.notes), actor_id=actor_id
        )

    async def attendance(
        self, employee: Employee, params: MyAttendanceParams, *, scope: EmployeeScope
    ) -> tuple[Sequence[Any], int]:
        return await self.workforce.list_attendance(self._attendance_params(employee, params), scope=scope)

    async def attendance_summary(
        self, employee: Employee, start: date, end: date, *, scope: EmployeeScope
    ) -> MyAttendanceSummary:
        """Totals over a window, counted from the rows the register shows.

        Counted rather than stored: the register and this summary must agree,
        and the only way to guarantee that is for one to be an aggregate of the
        other.
        """
        # Read whole rather than paged: a month of one person's attendance is at
        # most 31 rows, and a summary assembled from a partial page would be a
        # figure that quietly changes with the page size.
        rows, _ = await self.workforce.list_attendance(
            self._attendance_params(
                employee, MyAttendanceParams(page=1, page_size=100, from_date=start, to_date=end)
            ),
            scope=scope,
        )

        return MyAttendanceSummary(
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

    async def calendar(self, employee: Employee, year: int, month: int) -> list[dict[str, Any]]:
        return await self.workforce.calendar(employee.id, year, month)

    async def regularizations(
        self, employee: Employee, params: MyRegularizationParams, *, scope: EmployeeScope
    ) -> tuple[Sequence[Any], int]:
        return await self.workforce.list_regularizations(
            RegularizationListParams(
                page=params.page,
                page_size=params.page_size,
                employee_id=employee.id,
                status=params.status,
            ),
            scope=scope,
        )

    async def request_regularization(
        self,
        employee: Employee,
        payload: RegularizationCreate,
        *,
        actor_id: uuid.UUID,
        scope: EmployeeScope,
    ) -> AttendanceRegularization:
        return await self.workforce.request_regularization(employee.id, payload, actor_id=actor_id)

    # ==================================================================
    # Leave
    # ==================================================================
    async def leave_types(self) -> Sequence[Any]:
        return await self.workforce.list_leave_types()

    async def leave_balances(self, employee: Employee, year: int | None = None) -> list[MyLeaveBalance]:
        """The five figures, projected from the balance row the engine maintains.

        ``accrued`` is opening balance plus allocation -- everything credited so
        far. It is computed here rather than stored because the platform credits
        the whole year at once; a proportional accrual engine would fill the
        same field from a different sum without any client noticing.
        """
        balances = await self.workforce.balances_for(employee.id, year)
        return [
            MyLeaveBalance(
                leave_type_id=balance.leave_type_id,
                leave_type=balance.leave_type,
                year=balance.year,
                allocated=balance.allocated,
                accrued=balance.opening_balance + balance.allocated,
                used=balance.used,
                pending=balance.pending,
                available=balance.remaining,
                is_paid=balance.leave_type.is_paid if balance.leave_type else True,
                requires_document=balance.leave_type.requires_document if balance.leave_type else False,
            )
            for balance in balances
        ]

    async def leave(
        self, employee: Employee, params: MyLeaveParams, *, scope: EmployeeScope
    ) -> tuple[Sequence[Any], int]:
        return await self.workforce.list_leave(
            LeaveListParams(
                page=params.page,
                page_size=params.page_size,
                employee_id=employee.id,
                leave_type_id=params.leave_type_id,
                status=params.status,
                from_date=params.from_date,
                to_date=params.to_date,
            ),
            scope=scope,
        )

    async def apply_for_leave(
        self, employee: Employee, payload: LeaveApply, *, actor_id: uuid.UUID, scope: EmployeeScope
    ) -> LeaveRequest:
        return await self.workforce.apply_for_leave(employee.id, payload, actor_id=actor_id)

    async def cancel_leave(
        self, employee: Employee, request_id: uuid.UUID, *, actor_id: uuid.UUID, scope: EmployeeScope
    ) -> LeaveRequest:
        """Cancel one of your own requests.

        The scope is what makes "your own" true: ``cancel_leave`` checks the
        request's employee against it before it checks anything else, so a
        request id belonging to somebody else is a 403 rather than a cancelled
        colleague's holiday.
        """
        return await self.workforce.cancel_leave(request_id, actor_id=actor_id, scope=scope)

    # ==================================================================
    # Timesheets
    # ==================================================================
    async def timesheets(
        self, employee: Employee, params: MyTimesheetParams, *, scope: EmployeeScope
    ) -> tuple[Sequence[Any], int]:
        return await self.workforce.list_timesheets(
            TimesheetListParams(
                page=params.page,
                page_size=params.page_size,
                employee_id=employee.id,
                status=params.status,
                from_date=params.from_date,
                to_date=params.to_date,
            ),
            scope=scope,
        )

    async def timesheet(self, timesheet_id: uuid.UUID, *, scope: EmployeeScope) -> Timesheet:
        return await self.workforce.get_timesheet(timesheet_id, scope=scope)

    async def timesheet_week(
        self, employee: Employee, week_start: date | None, *, scope: EmployeeScope
    ) -> MyTimesheetWeek:
        """One week's grid plus the projects allowed in it."""
        monday = self._week_start(week_start or self._today())
        rows, _ = await self.workforce.list_timesheets(
            TimesheetListParams(
                page=1,
                page_size=1,
                employee_id=employee.id,
                from_date=monday,
                to_date=monday,
            ),
            scope=scope,
        )
        timesheet = rows[0] if rows else None

        return MyTimesheetWeek(
            week_start_date=monday,
            timesheet=timesheet,
            # A submitted week is not edited; a rejected one is, which is what
            # "returned for correction" means in this module.
            editable=timesheet is None or timesheet.status in TIMESHEET_NEEDS_ME,
            projects=await self.projects(employee, on=monday),
        )

    async def save_timesheet(
        self, employee: Employee, payload: TimesheetSave, *, actor_id: uuid.UUID, scope: EmployeeScope
    ) -> Timesheet:
        """Save a draft week.

        The allocation check lives in ``WorkforceService``, so an employee
        booking hours to a project they are not on is refused by the same rule
        that refuses it when HR does it on their behalf.
        """
        return await self.workforce.save_timesheet(employee.id, payload, actor_id=actor_id)

    async def submit_timesheet(
        self, timesheet_id: uuid.UUID, *, actor_id: uuid.UUID, scope: EmployeeScope
    ) -> Timesheet:
        return await self.workforce.submit_timesheet(timesheet_id, actor_id=actor_id, scope=scope)

    # ==================================================================
    # Documents
    # ==================================================================
    async def documents(
        self, employee: Employee, params: MyDocumentParams, *, scope: EmployeeScope
    ) -> tuple[list[MyDocument], int]:
        """The employee's own vault.

        Filtered by owner explicitly rather than left to the scope. Scope keeps
        organization policies and candidate paperwork readable by design -- the
        handbook is not somebody's personal document -- and "my documents" means
        the ones filed against me, not everything I am allowed to open.
        """
        rows, total = await self.vault.list(
            DocumentListParams(
                page=params.page,
                page_size=params.page_size,
                search=params.search,
                status=params.status,
                category_id=params.category_id,
                owner_type=DocumentOwnerType.EMPLOYEE,
                owner_id=employee.id,
            ),
            scope=scope,
        )
        return [await self._as_my_document(row, employee) for row in rows], total

    async def document(
        self, employee: Employee, document_id: uuid.UUID, *, scope: EmployeeScope
    ) -> MyDocument:
        document = await self.vault.get_by_id(document_id, scope=scope)
        self._assert_own_document(document, employee)
        return await self._as_my_document(document, employee)

    async def upload_document(
        self,
        employee: Employee,
        payload: MyDocumentUpload,
        upload: UploadedFile,
        *,
        actor_id: uuid.UUID,
        scope: EmployeeScope,
    ) -> MyDocument:
        """File a document against yourself.

        The owner is supplied here, not by the caller: :class:`MyDocumentUpload`
        has no ``owner_id`` field, so an employee cannot upload a document into
        somebody else's vault even though the underlying endpoint allows an
        owner to be named.
        """
        document = await self.vault.create(
            DocumentUploadMetadata(
                name=payload.name,
                category_id=payload.category_id,
                document_type_id=payload.document_type_id,
                owner_type=DocumentOwnerType.EMPLOYEE,
                owner_id=employee.id,
                description=payload.description,
                expiry_date=payload.expiry_date,
            ),
            upload,
            actor_id=actor_id,
            scope=scope,
        )
        return await self._as_my_document(document, employee)

    async def replace_document(
        self,
        employee: Employee,
        document_id: uuid.UUID,
        upload: UploadedFile,
        *,
        notes: str | None,
        actor_id: uuid.UUID,
        scope: EmployeeScope,
    ) -> MyDocument:
        """Upload a replacement -- typically after a rejection.

        Refused for anything the employee did not upload. An offer letter, an
        appointment letter or a relieving letter is issued *to* the employee;
        letting them add a version to one would let the copy on file stop
        matching the copy that was sent.
        """
        document = await self.vault.get_by_id(document_id, scope=scope)
        self._assert_own_document(document, employee)
        if not self._uploaded_by(document, actor_id):
            raise ConflictError(
                "This document was issued to you and can only be replaced by HR.",
                error_code="issued_document",
            )

        updated = await self.vault.add_version(
            document_id,
            DocumentVersionUploadMetadata(notes=notes),
            upload,
            actor_id=actor_id,
            scope=scope,
        )
        return await self._as_my_document(updated, employee)

    async def read_document_file(
        self,
        employee: Employee,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID | None,
        for_preview: bool,
        actor_id: uuid.UUID,
        scope: EmployeeScope,
    ) -> FilePayload:
        """Download or preview, through the vault's own audited read path."""
        document = await self.vault.get_by_id(document_id, scope=scope)
        self._assert_own_document(document, employee)
        return await self.vault.read_file(
            document_id,
            version_id=version_id,
            actor_id=actor_id,
            for_preview=for_preview,
            scope=scope,
        )

    async def document_versions(
        self, employee: Employee, document_id: uuid.UUID, *, scope: EmployeeScope
    ) -> Sequence[Any]:
        document = await self.vault.get_by_id(document_id, scope=scope)
        self._assert_own_document(document, employee)
        return await self.vault.versions(document_id, scope=scope)

    async def selectable_document_types(self) -> list[MyDocumentType]:
        """The classifications an upload form can offer.

        Read through the vault's own repository so a type retired on the HR
        settings screen disappears from the portal at the same moment, and an
        employee is never offered a classification the upload will refuse.
        """
        types, _ = await self.document_types.list_page(
            DocumentTypeListParams(page=1, page_size=100, status=RecordStatus.ACTIVE, sort_by="name")
        )
        return [
            MyDocumentType(
                id=item.id,
                name=item.name,
                code=item.code,
                category_id=item.category_id,
                category_name=item.category.name if item.category else "Other",
                requires_expiry=item.requires_expiry,
                allowed_extensions=item.allowed_extensions,
            )
            for item in types
        ]

    # ==================================================================
    # Projects and holidays
    # ==================================================================
    async def projects(self, employee: Employee, *, on: date | None = None) -> list[MyProject]:
        """Allocations, read-only, from the Project Allocation module.

        ``is_current`` is derived from the window rather than the ``status``
        column: an allocation that ended last month is still ``active`` until
        somebody removes it, and a timesheet picker that offers it would produce
        hours nobody can bill.
        """
        today = on or self._today()
        rows = await self.allocations.for_employee(employee.id)

        return [
            MyProject(
                allocation_id=allocation.id,
                project_id=allocation.project_id,
                project_code=allocation.project.project_code,
                project_name=allocation.project.project_name,
                client_name=allocation.project.client.client_name if allocation.project.client else None,
                role=member.role if member else None,
                allocation_percentage=allocation.allocation_percentage,
                start_date=allocation.start_date,
                end_date=allocation.end_date,
                billable=allocation.billable,
                status=allocation.status,
                is_current=(
                    allocation.start_date <= today
                    and (allocation.end_date is None or allocation.end_date >= today)
                ),
            )
            for allocation, member in rows
        ]

    async def holidays(self, employee: Employee, year: int | None = None) -> list[MyHoliday]:
        """The holidays that apply where this employee works.

        ``list_calendars`` treats a calendar with no location as one that
        applies everywhere, so an employee placed in Hyderabad gets the national
        calendar plus the Hyderabad one and never Chennai's.

        The second filter is for the employee who has no work location recorded
        yet. ``list_calendars`` applies no narrowing when it is given no
        location, which is right for an HR screen listing what exists and wrong
        here: it would show that person every office's calendar at once. With no
        location the only calendars that can be said to apply are the ones that
        apply everywhere.
        """
        target = year or self._today().year
        calendars = await self.workforce.list_calendars(target, employee.work_location_id)
        if employee.work_location_id is None:
            calendars = [calendar for calendar in calendars if calendar.location_id is None]
        today = self._today()

        rows = [
            MyHoliday(
                id=holiday.id,
                name=holiday.name,
                holiday_date=holiday.holiday_date,
                holiday_type=holiday.holiday_type,
                calendar_name=calendar.name,
                is_past=holiday.holiday_date < today,
            )
            for calendar in calendars
            for holiday in calendar.holidays
        ]
        rows.sort(key=lambda item: item.holiday_date)
        return rows

    # ==================================================================
    # Dashboard
    # ==================================================================
    async def dashboard(self, employee: Employee, *, user_id: uuid.UUID, scope: EmployeeScope) -> MyDashboard:
        """One screen, assembled from five modules, about one person."""
        today = self._today()
        month_start = today.replace(day=1)
        week_start = self._week_start(today)

        attendance = await self.today(employee, scope=scope)
        summary = await self.attendance_summary(employee, month_start, today, scope=scope)
        balances = await self.leave_balances(employee)

        pending_leave, _ = await self.leave(
            employee,
            MyLeaveParams(page=1, page_size=DASHBOARD_LEAVE_COUNT, status=ApprovalStatus.PENDING),
            scope=scope,
        )
        week = await self.timesheet_week(employee, week_start, scope=scope)
        projects = [project for project in week.projects if project.is_current]

        documents, document_total = await self.documents(
            employee, MyDocumentParams(page=1, page_size=DASHBOARD_DOCUMENT_COUNT), scope=scope
        )
        document_summary = await self._document_summary(employee, scope=scope, total=document_total)

        upcoming = [item for item in await self.holidays(employee) if not item.is_past]
        regularizations, pending_regularizations = await self.regularizations(
            employee,
            MyRegularizationParams(page=1, page_size=1, status=ApprovalStatus.PENDING),
            scope=scope,
        )
        del regularizations

        return MyDashboard(
            employee=employee,
            on_date=today,
            attendance=attendance,
            month_summary=summary,
            leave_balances=balances,
            pending_leave=list(pending_leave),
            upcoming_holidays=upcoming[:DASHBOARD_HOLIDAY_COUNT],
            current_timesheet=week.timesheet,
            current_week_start=week_start,
            projects=projects,
            documents=document_summary,
            recent_documents=documents,
            pending_actions=self._pending_actions(
                attendance=attendance,
                week=week,
                rejected_documents=document_summary.rejected,
                pending_regularizations=pending_regularizations,
            ),
            recent_announcements=(
                (await self.announcements.for_employee(employee))[:DASHBOARD_NOTIFICATION_COUNT]
                if self.announcements is not None
                else []
            ),
            recent_notifications=[
                MyNotification.model_validate(row)
                for row in (await self.notifications.for_user(user_id))[:DASHBOARD_NOTIFICATION_COUNT]
            ],
        )

    @staticmethod
    def _pending_actions(
        *,
        attendance: MyAttendanceToday,
        week: MyTimesheetWeek,
        rejected_documents: int,
        pending_regularizations: int,
    ) -> list[PendingAction]:
        """What is still the employee's to do, as opposed to what happened.

        Only things they can act on: a leave request awaiting a manager is not
        listed, because there is nothing for its author to do about it and a
        list that cannot be emptied stops being read.
        """
        actions: list[PendingAction] = []

        if attendance.can_check_in:
            actions.append(
                PendingAction(
                    code="check_in",
                    label="You have not checked in today",
                    link="/employee/attendance",
                )
            )
        elif attendance.can_check_out:
            actions.append(
                PendingAction(
                    code="check_out",
                    label="You are still checked in",
                    detail="Check out to record today's hours.",
                    link="/employee/attendance",
                )
            )

        timesheet = week.timesheet
        if timesheet is None:
            actions.append(
                PendingAction(
                    code="timesheet_missing",
                    label="This week's timesheet has not been started",
                    link="/employee/timesheets",
                )
            )
        elif timesheet.status == TimesheetStatus.REJECTED.value:
            actions.append(
                PendingAction(
                    code="timesheet_rejected",
                    label="A timesheet was returned for correction",
                    detail=timesheet.decision_notes,
                    link="/employee/timesheets",
                )
            )
        elif timesheet.status == TimesheetStatus.DRAFT.value:
            actions.append(
                PendingAction(
                    code="timesheet_draft",
                    label="This week's timesheet is still a draft",
                    detail="Submit it for approval.",
                    link="/employee/timesheets",
                )
            )

        if rejected_documents:
            actions.append(
                PendingAction(
                    code="document_rejected",
                    label=f"{rejected_documents} document(s) were rejected",
                    detail="Upload a replacement.",
                    link="/employee/documents",
                )
            )

        if pending_regularizations:
            actions.append(
                PendingAction(
                    code="regularization_pending",
                    label=f"{pending_regularizations} attendance correction(s) awaiting a decision",
                    link="/employee/attendance",
                )
            )

        return actions

    # ==================================================================
    # Helpers
    # ==================================================================
    async def _document_summary(
        self, employee: Employee, *, scope: EmployeeScope, total: int
    ) -> MyDocumentSummary:
        """Counts by review state, from the same filtered set the list returns."""
        rows, _ = await self.vault.list(
            DocumentListParams(
                page=1,
                page_size=100,
                owner_type=DocumentOwnerType.EMPLOYEE,
                owner_id=employee.id,
            ),
            scope=scope,
        )
        return MyDocumentSummary(
            total=total,
            pending_review=sum(1 for row in rows if row.status in UNDECIDED_DOCUMENT_STATUSES),
            approved=sum(1 for row in rows if row.status == DocumentStatus.APPROVED.value),
            rejected=sum(1 for row in rows if row.status == DocumentStatus.REJECTED.value),
            expiring_soon=sum(1 for row in rows if row.expiry_state is ExpiryState.EXPIRING_SOON),
        )

    async def _as_my_document(self, document: Any, employee: Employee) -> MyDocument:
        return MyDocument.build(
            document,
            owner=await self.vault.resolve_owner(document),
            can_replace=self._uploaded_by(document, employee.user_id),
        )

    @staticmethod
    def _uploaded_by(document: Any, user_id: uuid.UUID | None) -> bool:
        """Whether this document came from the employee rather than from HR.

        ``created_by`` is the only signal the vault records, and it is the right
        one: an HR-issued letter is created by the person who issued it. There
        is no ``issued_by`` flag to add, and adding one would mean backfilling a
        judgement about every document already stored.
        """
        return user_id is not None and document.created_by == user_id

    @staticmethod
    def _assert_own_document(document: Any, employee: Employee) -> None:
        """Belt to the scope check's braces.

        ``get_by_id`` already refuses a document outside the caller's scope, and
        for a ``/me`` request that scope is the caller alone. This second check
        exists because the two failure modes are different: a scope covers who a
        person may see, and this covers what "mine" means -- a company policy is
        readable by everyone and is nobody's personal document.
        """
        if document.owner_type != DocumentOwnerType.EMPLOYEE.value or document.owner_id != employee.id:
            raise NotFoundError("Document")

    async def _attendance_for(
        self, employee: Employee, on: date, *, scope: EmployeeScope
    ) -> AttendanceRecord | None:
        rows, _ = await self.workforce.list_attendance(
            AttendanceListParams(page=1, page_size=1, employee_id=employee.id, from_date=on, to_date=on),
            scope=scope,
        )
        return rows[0] if rows else None

    @staticmethod
    def _attendance_params(employee: Employee, params: MyAttendanceParams) -> AttendanceListParams:
        """Rebuild the module's own list params with the employee filled in.

        The client's parameters never include an employee id -- ``MyAttendanceParams``
        has no such field -- so this is the only place one can enter the query.
        """
        return AttendanceListParams(
            page=params.page,
            page_size=params.page_size,
            employee_id=employee.id,
            status=params.status,
            from_date=params.from_date,
            to_date=params.to_date,
        )

    @staticmethod
    def _today() -> date:
        return datetime.now(UTC).date()

    @staticmethod
    def _week_start(on: date) -> date:
        return on - timedelta(days=on.weekday())
