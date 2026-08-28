"""Workforce operations business logic.

Four rules shape this module.

**A day belongs to one attendance record.** Checking in twice does not create a
second row; it is refused. Every monthly figure depends on that being true.

**Leave is counted in working days.** Weekends and holidays are excluded when a
request is measured, so a Friday-to-Monday absence costs two days, not four.
Getting this wrong quietly overcharges people for their own weekends.

**Balance is held, then spent.** Applying moves days into ``pending``; approving
moves them from ``pending`` into ``used``; rejecting or cancelling releases them.
The held amount is what stops two overlapping requests both being approved
against the same entitlement.

**A submitted timesheet is not edited.** It is approved or rejected; only a
rejected week can be saved again, and saving is what returns it to draft. An
approval therefore always refers to a state someone actually saw.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import or_

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.audit_log import AuditAction
from app.models.employee import Employee
from app.models.enums import (
    CREDIT_PERIODS_PER_YEAR,
    ApprovalStatus,
    AttendanceStatus,
    CreditFrequency,
    LeaveDayPart,
    RecordStatus,
    TimesheetStatus,
    WorkMode,
)
from app.models.project import EmployeeAllocation
from app.models.requisition import Notification
from app.models.workforce import (
    AttendanceRecord,
    AttendanceRegularization,
    EmployeeShift,
    Holiday,
    HolidayCalendar,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    Shift,
    Timesheet,
    TimesheetEntry,
)
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.offboarding_repository import OffboardingCaseRepository
from app.repositories.project_repository import AllocationRepository
from app.repositories.requisition_repository import NotificationRepository
from app.repositories.workforce_repository import (
    AttendanceRepository,
    EmployeeShiftRepository,
    HolidayRepository,
    LeaveBalanceRepository,
    LeaveRequestRepository,
    LeaveTypeRepository,
    RegularizationRepository,
    ShiftRepository,
    TimesheetRepository,
    WorkforceAnalyticsRepository,
)
from app.schemas.workforce import (
    AttendanceCorrection,
    AttendanceListParams,
    CheckInRequest,
    CheckOutRequest,
    HolidayCalendarCreate,
    LeaveApply,
    LeaveBalanceAdjustment,
    LeaveListParams,
    LeaveTypeCreate,
    LeaveTypeUpdate,
    RegularizationCreate,
    RegularizationListParams,
    ShiftAssign,
    ShiftCreate,
    ShiftListParams,
    ShiftUpdate,
    TimesheetListParams,
    TimesheetSave,
)
from app.services.audit_service import AuditService
from app.services.scope_service import EmployeeScope, visible_employee_ids
from app.utils.datetime import utc_now

logger = get_logger("services.workforce")

MINUTES_PER_HOUR = 60
UPCOMING_HOLIDAY_COUNT = 5


class WorkforceService:
    """Shifts, attendance, leave and timesheets."""

    def __init__(
        self,
        shifts: ShiftRepository,
        assignments: EmployeeShiftRepository,
        attendance: AttendanceRepository,
        regularizations: RegularizationRepository,
        leave_types: LeaveTypeRepository,
        balances: LeaveBalanceRepository,
        leave_requests: LeaveRequestRepository,
        holidays: HolidayRepository,
        timesheets: TimesheetRepository,
        analytics: WorkforceAnalyticsRepository,
        employees: EmployeeRepository,
        audit: AuditService,
        allocations: AllocationRepository | None = None,
        notifications: NotificationRepository | None = None,
        separations: OffboardingCaseRepository | None = None,
    ) -> None:
        self.shifts = shifts
        self.assignments = assignments
        self.attendance = attendance
        self.regularizations = regularizations
        self.leave_types = leave_types
        self.balances = balances
        self.leave_requests = leave_requests
        self.holidays = holidays
        self.timesheets = timesheets
        self.analytics = analytics
        self.employees = employees
        self.audit = audit
        # Used only to confirm a timesheet line has an allocation behind it.
        self.allocations = allocations
        # Read-only, and only to find a last working day. Optional so that the
        # unit tests and the seeder can build this service without the
        # offboarding module; the guard degrades to the employment-status check.
        self.separations = separations
        self.notifications = notifications

    # ==================================================================
    # Shifts
    # ==================================================================
    async def list_shifts(self, params: ShiftListParams) -> tuple[Sequence[Shift], int]:
        return await self.shifts.search(params)

    async def get_shift(self, shift_id: uuid.UUID) -> Shift:
        shift = await self.shifts.get(shift_id, include_deleted=True)
        if shift is None:
            raise NotFoundError("Shift")
        return shift

    async def create_shift(self, payload: ShiftCreate, *, actor_id: uuid.UUID | None = None) -> Shift:
        if await self.shifts.find_by_code(payload.code) is not None:
            raise ConflictError(
                f'A shift with the code "{payload.code}" already exists.', error_code="duplicate_code"
            )

        values = payload.model_dump()
        values["shift_type"] = payload.shift_type.value
        values["status"] = payload.status.value
        shift = await self.shifts.add(Shift(**values), actor_id=actor_id)

        await self.audit.record_success(
            AuditAction.SHIFT_CREATED,
            actor_id=actor_id,
            entity_type="shift",
            entity_id=shift.id,
            description=f"Created shift {shift.name} ({shift.code})",
        )
        return shift

    async def update_shift(
        self, shift_id: uuid.UUID, payload: ShiftUpdate, *, actor_id: uuid.UUID | None = None
    ) -> Shift:
        shift = await self.get_shift(shift_id)
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return shift

        for field in ("shift_type", "status"):
            if changes.get(field) is not None:
                changes[field] = changes[field].value

        await self.shifts.update(shift, changes, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.SHIFT_UPDATED,
            actor_id=actor_id,
            entity_type="shift",
            entity_id=shift.id,
            description=f"Updated shift {shift.name}",
            context={"fields": sorted(changes)},
        )
        return shift

    async def assign_shift(self, payload: ShiftAssign, *, actor_id: uuid.UUID | None = None) -> EmployeeShift:
        """Close the current assignment and open a new one.

        Never an update: an attendance record from last month has to be read
        against the shift that was in force then.
        """
        await self._assert_employee_exists(payload.employee_id)
        shift = await self.get_shift(payload.shift_id)
        if shift.status != RecordStatus.ACTIVE.value or shift.deleted_at is not None:
            raise ConflictError(
                "That shift is not active and cannot be assigned.", error_code="invalid_shift"
            )

        open_assignment = await self.assignments.open_assignment(payload.employee_id)
        if open_assignment is not None:
            if open_assignment.shift_id == payload.shift_id:
                raise ConflictError("This employee is already on that shift.", error_code="already_on_shift")
            if payload.effective_from <= open_assignment.effective_from:
                raise ValidationError(
                    "The new shift must start after the current assignment began.",
                    error_code="invalid_effective_date",
                )
            await self.assignments.update(
                open_assignment,
                {"effective_to": payload.effective_from - timedelta(days=1)},
                actor_id=actor_id,
            )

        assignment = await self.assignments.add(EmployeeShift(**payload.model_dump()), actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.SHIFT_ASSIGNED,
            actor_id=actor_id,
            entity_type="employee_shift",
            entity_id=assignment.id,
            description=f"Assigned shift {shift.code} from {payload.effective_from}",
        )
        await self._notify(
            payload.employee_id,
            "Shift assigned",
            f"You are on the {shift.name} shift from {payload.effective_from}.",
            "/workforce/attendance",
            "shift_assigned",
        )
        # Reloaded because ``EmployeeShift.shift`` is a joined relationship: on
        # a row that was added rather than queried it is still unloaded, and
        # serialising it would attempt lazy IO outside the greenlet.
        reloaded = await self.assignments.get(assignment.id)
        if reloaded is None:  # pragma: no cover - just written
            raise NotFoundError("Shift assignment")
        return reloaded

    async def shift_history(self, employee_id: uuid.UUID) -> Sequence[EmployeeShift]:
        await self._assert_employee_exists(employee_id)
        return await self.assignments.history(employee_id)

    # ==================================================================
    # Attendance
    # ==================================================================
    async def check_in(
        self, employee_id: uuid.UUID, payload: CheckInRequest, *, actor_id: uuid.UUID | None = None
    ) -> AttendanceRecord:
        on = payload.attendance_date or self._today()
        self._assert_not_future(on)
        await self._assert_can_record(employee_id, on)

        existing = await self.attendance.for_day(employee_id, on)
        if existing is not None and existing.check_in_at is not None:
            raise ConflictError(f"Already checked in on {on}.", error_code="already_checked_in")

        assignment = await self.assignments.current(employee_id, on)
        shift = assignment.shift if assignment else None
        now = utc_now()

        record = existing or AttendanceRecord(employee_id=employee_id, attendance_date=on)
        values: dict[str, Any] = {
            "check_in_at": now,
            "work_mode": payload.work_mode.value,
            "shift_id": shift.id if shift else None,
            "status": AttendanceStatus.PRESENT.value,
            "late_minutes": self._late_minutes(now, shift, on),
            "notes": payload.notes,
        }

        if existing is None:
            for field, value in values.items():
                setattr(record, field, value)
            await self.attendance.add(record, actor_id=actor_id)
        else:
            await self.attendance.update(record, values, actor_id=actor_id)

        await self.audit.record_success(
            AuditAction.ATTENDANCE_CHECKED_IN,
            actor_id=actor_id,
            entity_type="attendance",
            entity_id=record.id,
            description=f"Checked in on {on}",
            context={"work_mode": payload.work_mode.value, "late_minutes": values["late_minutes"]},
        )
        return record

    async def check_out(
        self, employee_id: uuid.UUID, payload: CheckOutRequest, *, actor_id: uuid.UUID | None = None
    ) -> AttendanceRecord:
        on = payload.attendance_date or self._today()
        record = await self.attendance.for_day(employee_id, on)
        if record is None or record.check_in_at is None:
            raise ConflictError(f"There is no check-in on {on} to close.", error_code="not_checked_in")
        if record.check_out_at is not None:
            raise ConflictError(f"Already checked out on {on}.", error_code="already_checked_out")

        now = utc_now()
        if now <= record.check_in_at:
            raise ValidationError("Check-out cannot be before check-in.", error_code="invalid_checkout")

        shift = await self.shifts.get(record.shift_id) if record.shift_id else None
        figures = self._day_figures(record.check_in_at, now, shift)

        await self.attendance.update(
            record,
            {"check_out_at": now, "notes": payload.notes or record.notes, **figures},
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.ATTENDANCE_CHECKED_OUT,
            actor_id=actor_id,
            entity_type="attendance",
            entity_id=record.id,
            description=f"Checked out on {on}",
            context={"worked_minutes": figures["worked_minutes"]},
        )
        return record

    def _day_figures(self, check_in: datetime, check_out: datetime, shift: Shift | None) -> dict[str, Any]:
        """Worked, early-exit and overtime minutes for a completed day.

        With no shift assigned there is nothing to measure against, so the
        derived figures stay at zero rather than being invented from a default
        that would be wrong for anyone on nights.
        """
        worked = int((check_out - check_in).total_seconds() // 60)
        if shift is None:
            return {
                "worked_minutes": max(0, worked),
                "early_exit_minutes": 0,
                "overtime_minutes": 0,
                "status": AttendanceStatus.PRESENT.value,
            }

        worked = max(0, worked - shift.break_minutes)
        expected = self._shift_minutes(shift)

        scheduled_end = datetime.combine(
            check_in.date() + (timedelta(days=1) if shift.crosses_midnight else timedelta()),
            shift.end_time,
            tzinfo=UTC,
        )
        early_exit = max(0, int((scheduled_end - check_out).total_seconds() // 60))
        overtime = max(0, worked - expected)

        # Less than half a shift is a half day, not a full one -- otherwise a
        # ten-minute appearance counts the same as a full day worked.
        status = (
            AttendanceStatus.HALF_DAY.value
            if expected and worked < expected / 2
            else AttendanceStatus.PRESENT.value
        )
        return {
            "worked_minutes": worked,
            "early_exit_minutes": early_exit,
            "overtime_minutes": overtime,
            "status": status,
        }

    @staticmethod
    def _shift_minutes(shift: Shift) -> int:
        start = shift.start_time.hour * 60 + shift.start_time.minute
        end = shift.end_time.hour * 60 + shift.end_time.minute
        span = end - start if end > start else (24 * 60 - start) + end
        return max(0, span - shift.break_minutes)

    @staticmethod
    def _late_minutes(arrival: datetime, shift: Shift | None, on: date) -> int:
        """How late an arrival was, after the shift's grace period."""
        if shift is None:
            return 0
        expected = datetime.combine(on, shift.start_time, tzinfo=UTC) + timedelta(minutes=shift.grace_minutes)
        return max(0, int((arrival - expected).total_seconds() // 60))

    async def list_attendance(
        self, params: AttendanceListParams, *, scope: EmployeeScope | None = None
    ) -> tuple[Sequence[AttendanceRecord], int]:
        return await self.attendance.search(params, visible_ids=visible_employee_ids(scope))

    async def request_regularization(
        self, employee_id: uuid.UUID, payload: RegularizationCreate, *, actor_id: uuid.UUID | None = None
    ) -> AttendanceRegularization:
        await self._assert_employee_exists(employee_id)
        self._assert_not_future(payload.attendance_date)

        if await self.regularizations.pending_for_day(employee_id, payload.attendance_date):
            raise ConflictError(
                f"A correction for {payload.attendance_date} is already awaiting a decision.",
                error_code="already_requested",
            )

        request = await self.regularizations.add(
            AttendanceRegularization(
                employee_id=employee_id,
                **payload.model_dump(),
                status=ApprovalStatus.PENDING.value,
            ),
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.REGULARIZATION_REQUESTED,
            actor_id=actor_id,
            entity_type="attendance_regularization",
            entity_id=request.id,
            description=f"Requested a correction for {payload.attendance_date}",
        )
        manager_id = await self._manager_of(employee_id)
        if manager_id:
            await self._notify(
                manager_id,
                "Attendance correction pending",
                f"A correction for {payload.attendance_date} needs your decision.",
                "/workforce/regularizations",
                "regularization_pending",
            )
        return request

    async def get_regularization(
        self, request_id: uuid.UUID, *, scope: EmployeeScope | None = None
    ) -> AttendanceRegularization:
        """One correction request, by its own id rather than the employee's.

        Same reasoning as :meth:`get_timesheet`: the caller is handed a request
        id, and whose day it concerns is only knowable once the row has been
        read -- so the scope check belongs here rather than at the route.
        """
        request = await self.regularizations.get(request_id)
        if request is None:
            raise NotFoundError("Regularization request")
        self._assert_in_scope(scope, request.employee_id)
        return request

    async def decide_regularization(
        self,
        request_id: uuid.UUID,
        approved: bool,
        notes: str | None,
        *,
        actor_id: uuid.UUID | None = None,
        scope: EmployeeScope | None = None,
    ) -> AttendanceRegularization:
        request = await self.get_regularization(request_id, scope=scope)
        self._assert_undecided(request.status, "correction")

        decider = await self._employee_for_user(actor_id)
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        await self.regularizations.update(
            request,
            {
                "status": status.value,
                "decided_by_id": decider.id if decider else None,
                "decided_at": utc_now(),
                "decision_notes": notes,
            },
            actor_id=actor_id,
        )

        # Approval is what actually corrects the record; the request on its own
        # changes nothing, which is why the two are separate steps.
        if approved:
            await self._apply_regularization(request, actor_id=actor_id)

        await self.audit.record_success(
            AuditAction.REGULARIZATION_DECIDED,
            actor_id=actor_id,
            entity_type="attendance_regularization",
            entity_id=request.id,
            description=f"{status.value.title()} the correction for {request.attendance_date}",
        )
        await self._notify(
            request.employee_id,
            f"Attendance correction {status.value}",
            f"Your correction for {request.attendance_date} was {status.value}.",
            "/workforce/attendance",
            "regularization_decided",
        )
        return request

    async def _apply_regularization(
        self, request: AttendanceRegularization, *, actor_id: uuid.UUID | None
    ) -> None:
        record = await self.attendance.for_day(request.employee_id, request.attendance_date)
        assignment = await self.assignments.current(request.employee_id, request.attendance_date)
        shift = assignment.shift if assignment else None

        check_in = request.requested_check_in_at or (record.check_in_at if record else None)
        check_out = request.requested_check_out_at or (record.check_out_at if record else None)

        values: dict[str, Any] = {"check_in_at": check_in, "check_out_at": check_out}
        if check_in is not None:
            values["late_minutes"] = self._late_minutes(check_in, shift, request.attendance_date)
        if check_in is not None and check_out is not None:
            values |= self._day_figures(check_in, check_out, shift)

        if record is None:
            await self.attendance.add(
                AttendanceRecord(
                    employee_id=request.employee_id,
                    attendance_date=request.attendance_date,
                    shift_id=shift.id if shift else None,
                    work_mode=WorkMode.OFFICE.value,
                    **values,
                ),
                actor_id=actor_id,
            )
            return
        await self.attendance.update(record, values, actor_id=actor_id)

    async def list_regularizations(
        self, params: RegularizationListParams, *, scope: EmployeeScope | None = None
    ) -> tuple[Sequence[AttendanceRegularization], int]:
        return await self.regularizations.search(params, visible_ids=visible_employee_ids(scope))

    # ==================================================================
    # Leave
    # ==================================================================
    async def list_leave_types(self) -> Sequence[LeaveType]:
        """What may be applied for today.

        Narrowed by the policy's effective window as well as its status. A type
        retired on 31 December is still ``active`` on the row -- its status says
        whether anyone deactivated it, not whether it still applies -- and
        offering it in January would produce a request against a policy that no
        longer exists. A type with no window set has always applied, which is
        every type created before policy administration existed.
        """
        today = self._today()
        return [row for row in await self.leave_types.active() if row.in_force_on(today)]

    async def create_leave_type(
        self, payload: LeaveTypeCreate, *, actor_id: uuid.UUID | None = None
    ) -> LeaveType:
        if await self.leave_types.find_by_code(payload.code) is not None:
            raise ConflictError(
                f'A leave type with the code "{payload.code}" already exists.',
                error_code="duplicate_code",
            )
        values = payload.model_dump()
        values["status"] = payload.status.value
        values["credit_frequency"] = payload.credit_frequency.value
        leave_type = await self.leave_types.add(LeaveType(**values), actor_id=actor_id)

        await self.audit.record_success(
            AuditAction.LEAVE_TYPE_CREATED,
            actor_id=actor_id,
            entity_type="leave_type",
            entity_id=leave_type.id,
            description=f"Created leave type {leave_type.name}",
        )
        return leave_type

    async def update_leave_type(
        self, leave_type_id: uuid.UUID, payload: LeaveTypeUpdate, *, actor_id: uuid.UUID | None = None
    ) -> LeaveType:
        """Amend a leave type, including the policy behind it.

        The coherence check runs against the *merged* values rather than the
        submitted ones. A schema can only see the fields it was sent, so
        halving the annual maximum without touching the monthly credit would
        pass validation and leave a policy that credits more than it allows.

        Audited: §6 requires policy changes to be, and until now this was the
        one write in the module that recorded nothing.
        """
        leave_type = await self.leave_types.get(leave_type_id, include_deleted=True)
        if leave_type is None:
            raise NotFoundError("Leave type")

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return leave_type

        for field in ("status", "credit_frequency"):
            if changes.get(field) is not None:
                changes[field] = changes[field].value

        self._assert_schedule_fits(
            frequency=changes.get("credit_frequency", leave_type.credit_frequency),
            amount=changes.get("credit_amount", leave_type.credit_amount),
            annual=changes.get("annual_allocation", leave_type.annual_allocation),
        )
        self._assert_window_ordered(
            changes.get("effective_from", leave_type.effective_from),
            changes.get("effective_to", leave_type.effective_to),
        )

        await self.leave_types.update(leave_type, changes, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.LEAVE_TYPE_UPDATED,
            actor_id=actor_id,
            entity_type="leave_type",
            entity_id=leave_type.id,
            description=f"Updated leave policy {leave_type.name} ({leave_type.code})",
            context={"fields": sorted(changes)},
        )
        return leave_type

    @staticmethod
    def _assert_schedule_fits(*, frequency: str, amount: Decimal, annual: Decimal) -> None:
        periods = CREDIT_PERIODS_PER_YEAR.get(frequency, 0)
        if frequency == CreditFrequency.NONE.value and amount:
            raise ValidationError(
                "A leave type that is not credited cannot have a credit amount.",
                error_code="invalid_policy",
            )
        if periods and amount * periods > annual:
            raise ValidationError(
                f"{amount} days {periods} times a year exceeds the annual maximum of {annual}.",
                error_code="invalid_policy",
            )

    @staticmethod
    def _assert_window_ordered(start: date | None, end: date | None) -> None:
        if start and end and end < start:
            raise ValidationError(
                "A policy cannot stop applying before it starts.", error_code="invalid_policy"
            )

    async def list_leave_policies(self, *, include_retired: bool = True) -> Sequence[LeaveType]:
        """Every leave type, for the policy administration screen.

        Distinct from :meth:`list_leave_types`, which answers "what may I apply
        for today" and therefore hides anything out of its effective window.
        An administrator has to be able to see the policy that expired last
        month in order to extend it.
        """
        rows = await self.leave_types.list(order_by="name", descending=False, limit=200)
        return rows if include_retired else [row for row in rows if row.in_force_on(self._today())]

    async def adjust_balance(
        self,
        employee_id: uuid.UUID,
        payload: LeaveBalanceAdjustment,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> LeaveBalance:
        """Correct an entitlement by hand, and say why.

        Applied to ``allocated`` rather than to ``used`` or ``pending``: those
        two are the running total of what the workflow has done, and rewriting
        them would make the balance stop reconciling with the requests behind
        it. Allocation is the figure somebody is entitled to, which is exactly
        what an administrative correction is about.

        Refused when it would take the allocation below what has already been
        taken -- the resulting balance would be negative for a reason no report
        could explain, and the honest fix is to cancel the leave instead.
        """
        await self._assert_employee_exists(employee_id)
        leave_type = await self.leave_types.get(payload.leave_type_id)
        if leave_type is None:
            raise NotFoundError("Leave type")

        year = payload.year or self._today().year
        balance = await self._balance_for(employee_id, leave_type, year)
        updated = balance.allocated + payload.days

        if updated < 0:
            raise ConflictError(
                f"That would take the allocation to {updated} days.", error_code="negative_allocation"
            )
        if not leave_type.allows_negative and updated < balance.used + balance.pending:
            raise ConflictError(
                f"{balance.used + balance.pending} day(s) are already taken or held; "
                f"the allocation cannot drop to {updated}.",
                error_code="allocation_below_usage",
            )

        await self.balances.update(balance, {"allocated": updated}, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.LEAVE_BALANCE_ADJUSTED,
            actor_id=actor_id,
            entity_type="leave_balance",
            entity_id=balance.id,
            description=(
                f"Adjusted {leave_type.name} for {year} by {payload.days:+} day(s): {payload.reason}"
            ),
            context={
                "employee_id": str(employee_id),
                "leave_type": leave_type.code,
                "year": year,
                "days": str(payload.days),
                "from": str(balance.allocated - payload.days),
                "to": str(updated),
                "reason": payload.reason,
            },
        )
        await self._notify(
            employee_id,
            "Leave balance adjusted",
            f"Your {leave_type.name} balance for {year} changed by {payload.days:+} day(s).",
            "/employee/leave",
            "leave_balance_adjusted",
        )
        return balance

    async def override_leave_decision(
        self,
        request_id: uuid.UUID,
        approved: bool,
        notes: str | None,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> LeaveRequest:
        """Decide a request that was addressed to somebody else's manager.

        Deliberately calls :meth:`decide_leave` with no scope: the point of an
        override is that the reporting line does not apply. The permission is
        what makes that safe, and it is checked at the route -- this method is
        unreachable without ``leave:override_approval``.

        The second audit entry is not redundant. ``decide_leave`` records that
        the request was decided; this records that it was decided by somebody
        it was not addressed to, which is the fact an auditor is looking for and
        the one that would otherwise be invisible.
        """
        request = await self.get_leave_request(request_id)
        manager_id = await self._manager_of(request.employee_id)
        decided = await self.decide_leave(request_id, approved, notes, actor_id=actor_id, scope=None)

        await self.audit.record_success(
            AuditAction.LEAVE_DECISION_OVERRIDDEN,
            actor_id=actor_id,
            entity_type="leave_request",
            entity_id=request_id,
            description=(
                f"Administrative override: {'approved' if approved else 'rejected'} leave for "
                f"{request.from_date} to {request.to_date}"
            ),
            context={
                "employee_id": str(request.employee_id),
                "reporting_manager_id": str(manager_id) if manager_id else None,
                "notes": notes,
            },
        )
        return decided

    async def correct_attendance(
        self,
        employee_id: uuid.UUID,
        payload: AttendanceCorrection,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> AttendanceRecord:
        """Amend an attendance record directly, with a reason.

        The administrative counterpart of the regularization flow, and the only
        write in this module that changes somebody's day without them having
        asked. It reuses ``_day_figures`` so a corrected day is measured against
        the same shift, by the same arithmetic, as one that was worked -- a
        correction that produced different overtime from an identical real day
        would be a second definition of a working day.
        """
        await self._assert_employee_exists(employee_id)
        self._assert_not_future(payload.attendance_date)

        record = await self.attendance.for_day(employee_id, payload.attendance_date)
        assignment = await self.assignments.current(employee_id, payload.attendance_date)
        shift = assignment.shift if assignment else None

        check_in = payload.check_in_at or (record.check_in_at if record else None)
        check_out = payload.check_out_at or (record.check_out_at if record else None)

        values: dict[str, Any] = {"check_in_at": check_in, "check_out_at": check_out}
        if check_in is not None:
            values["late_minutes"] = self._late_minutes(check_in, shift, payload.attendance_date)
        if check_in is not None and check_out is not None:
            values |= self._day_figures(check_in, check_out, shift)
        # An explicit status wins over the derived one: marking a day as absent
        # or on leave is precisely the correction that cannot be expressed as a
        # pair of timestamps.
        if payload.status is not None:
            values["status"] = payload.status.value

        if record is None:
            record = await self.attendance.add(
                AttendanceRecord(
                    employee_id=employee_id,
                    attendance_date=payload.attendance_date,
                    shift_id=shift.id if shift else None,
                    work_mode=WorkMode.OFFICE.value,
                    **values,
                ),
                actor_id=actor_id,
            )
        else:
            await self.attendance.update(record, values, actor_id=actor_id)

        await self.audit.record_success(
            AuditAction.ATTENDANCE_CORRECTED,
            actor_id=actor_id,
            entity_type="attendance",
            entity_id=record.id,
            description=f"Administrative correction to {payload.attendance_date}: {payload.reason}",
            context={
                "employee_id": str(employee_id),
                "attendance_date": str(payload.attendance_date),
                "reason": payload.reason,
                "fields": sorted(values),
            },
        )
        await self._notify(
            employee_id,
            "Attendance corrected",
            f"Your attendance for {payload.attendance_date} was amended by HR.",
            "/employee/attendance",
            "attendance_corrected",
        )
        return record

    async def override_timesheet_decision(
        self,
        timesheet_id: uuid.UUID,
        approved: bool,
        notes: str | None,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Timesheet:
        """Decide a timesheet addressed to somebody else's manager. Audited as one."""
        timesheet = await self.get_timesheet(timesheet_id)
        decided = await self.decide_timesheet(timesheet_id, approved, notes, actor_id=actor_id, scope=None)
        await self.audit.record_success(
            AuditAction.TIMESHEET_DECISION_OVERRIDDEN,
            actor_id=actor_id,
            entity_type="timesheet",
            entity_id=timesheet_id,
            description=(
                f"Administrative override: {'approved' if approved else 'rejected'} "
                f"{timesheet.timesheet_code}"
            ),
            context={"employee_id": str(timesheet.employee_id), "notes": notes},
        )
        return decided

    async def balances_for(self, employee_id: uuid.UUID, year: int | None = None) -> Sequence[LeaveBalance]:
        await self._assert_employee_exists(employee_id)
        target = year or self._today().year
        existing = await self.balances.all_for_employee(employee_id, target)
        known = {balance.leave_type_id for balance in existing}

        # A balance row is created the first time it is looked at rather than by
        # a nightly job: an employee who joins mid-year still sees their
        # entitlement immediately.
        #
        # Only for policies in force. A row created against a retired policy
        # would be an entitlement nobody can apply against -- the type is no
        # longer offered -- and it would appear on every balance screen as days
        # the employee has and cannot use. Rows created while a policy *was* in
        # force are left exactly where they are; retiring a policy does not
        # take back what it already granted.
        created = False
        employee = await self.employees.get(employee_id)
        prior = {
            balance.leave_type_id: balance
            for balance in await self.balances.all_for_employee(employee_id, target - 1)
        }
        for leave_type in await self.leave_types.active():
            if leave_type.id in known or not leave_type.in_force_on(date(target, 12, 31)):
                continue
            await self.balances.add(
                LeaveBalance(
                    employee_id=employee_id,
                    leave_type_id=leave_type.id,
                    year=target,
                    allocated=self._allocation_for(leave_type, employee, target),
                    opening_balance=self._carry_forward(leave_type, prior.get(leave_type.id)),
                )
            )
            created = True

        return await self.balances.all_for_employee(employee_id, target) if created else existing

    @staticmethod
    def _carry_forward(leave_type: LeaveType, prior: LeaveBalance | None) -> Decimal:
        """What last year's unused days are worth this year.

        The policy's two fields finally do what the policy screen has always
        said they do: nothing carries unless ``carry_forward`` is set, and what
        carries is capped at ``max_carry_forward``. Computed when the new
        year's row is first created -- the same lazy moment the row itself
        exists from -- so there is no year-end job to forget to run.

        Floor at zero: an overdrawn year is a matter for the payroll module,
        not a debt the next year's holiday starts in.
        """
        if prior is None or not leave_type.carry_forward:
            return Decimal(0)
        unused = prior.opening_balance + prior.allocated - prior.used
        if unused <= 0:
            return Decimal(0)
        return min(unused, leave_type.max_carry_forward)

    def _allocation_for(self, leave_type: LeaveType, employee: Employee | None, year: int) -> Decimal:
        """The year's credit, prorated for a mid-year joiner when the policy asks.

        Whole months remaining including the joining month, over twelve --
        the convention HR actually uses -- rounded to the half day the balance
        columns can carry. Only the joining year is prorated: from the next
        January the person is simply an employee.
        """
        allocation = leave_type.annual_allocation
        if (
            not leave_type.prorate_on_joining
            or employee is None
            or employee.joining_date is None
            or employee.joining_date.year != year
        ):
            return allocation
        months_remaining = 12 - employee.joining_date.month + 1
        prorated = allocation * months_remaining / 12
        return (prorated * 2).quantize(Decimal("1")) / 2

    async def apply_for_leave(
        self, employee_id: uuid.UUID, payload: LeaveApply, *, actor_id: uuid.UUID | None = None
    ) -> LeaveRequest:
        # Guarded on the *end* of the requested period: leave that runs past
        # somebody's last working day is leave from a job they no longer hold.
        await self._assert_can_record(employee_id, payload.to_date)
        leave_type = await self.leave_types.get(payload.leave_type_id)
        if leave_type is None or leave_type.status != RecordStatus.ACTIVE.value:
            raise ConflictError("That leave type is not available.", error_code="invalid_leave_type")

        if leave_type.requires_document and payload.supporting_document_id is None:
            raise ValidationError(
                f"{leave_type.name} needs a supporting document.", error_code="document_required"
            )

        clash = await self.leave_requests.overlapping(employee_id, payload.from_date, payload.to_date)
        if clash is not None:
            raise ConflictError(
                f"This overlaps leave already requested for {clash.from_date} to {clash.to_date}.",
                error_code="overlapping_leave",
            )

        days = await self._working_days(employee_id, payload)
        if days <= 0:
            raise ValidationError(
                "That range is entirely weekends and holidays, so no leave is needed.",
                error_code="no_working_days",
            )

        balance = await self._balance_for(employee_id, leave_type, payload.from_date.year)
        if not leave_type.allows_negative and balance.remaining < days:
            raise ConflictError(
                f"Only {balance.remaining} day(s) of {leave_type.name} remain; {days} requested.",
                error_code="insufficient_balance",
            )

        request = await self.leave_requests.add(
            LeaveRequest(
                employee_id=employee_id,
                leave_type_id=payload.leave_type_id,
                from_date=payload.from_date,
                to_date=payload.to_date,
                day_part=payload.day_part.value,
                days=days,
                reason=payload.reason,
                supporting_document_id=payload.supporting_document_id,
                status=ApprovalStatus.PENDING.value,
            ),
            actor_id=actor_id,
        )

        # Held now, not on approval: two overlapping requests must not both be
        # approvable against the same entitlement.
        await self.balances.update(balance, {"pending": balance.pending + days}, actor_id=actor_id)

        await self.audit.record_success(
            AuditAction.LEAVE_APPLIED,
            actor_id=actor_id,
            entity_type="leave_request",
            entity_id=request.id,
            description=f"Applied for {days} day(s) of {leave_type.name}",
            context={"from": str(payload.from_date), "to": str(payload.to_date)},
        )
        manager_id = await self._manager_of(employee_id)
        if manager_id:
            await self._notify(
                manager_id,
                "Leave request pending",
                f"A {days}-day {leave_type.name} request needs your decision.",
                "/workforce/leave",
                "leave_applied",
            )
        # Same reason as an assignment: ``LeaveRequest.leave_type`` is joined,
        # and a freshly added row has not loaded it.
        reloaded = await self.leave_requests.get(request.id)
        if reloaded is None:  # pragma: no cover - just written
            raise NotFoundError("Leave request")
        return reloaded

    async def get_leave_request(
        self, request_id: uuid.UUID, *, scope: EmployeeScope | None = None
    ) -> LeaveRequest:
        """One leave request, by its own id. The choke point for scoping it."""
        request = await self.leave_requests.get(request_id)
        if request is None:
            raise NotFoundError("Leave request")
        self._assert_in_scope(scope, request.employee_id)
        return request

    async def decide_leave(
        self,
        request_id: uuid.UUID,
        approved: bool,
        notes: str | None,
        *,
        actor_id: uuid.UUID | None = None,
        scope: EmployeeScope | None = None,
    ) -> LeaveRequest:
        request = await self.get_leave_request(request_id, scope=scope)
        self._assert_undecided(request.status, "leave request")

        decider = await self._employee_for_user(actor_id)
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        await self.leave_requests.update(
            request,
            {
                "status": status.value,
                "decided_by_id": decider.id if decider else None,
                "decided_at": utc_now(),
                "decision_notes": notes,
            },
            actor_id=actor_id,
        )

        balance = await self._balance_for(request.employee_id, request.leave_type, request.from_date.year)
        if approved:
            # Held days become spent days.
            await self.balances.update(
                balance,
                {"pending": balance.pending - request.days, "used": balance.used + request.days},
                actor_id=actor_id,
            )
            await self._mark_leave_days(request, actor_id=actor_id)
        else:
            await self.balances.update(
                balance, {"pending": balance.pending - request.days}, actor_id=actor_id
            )

        await self.audit.record_success(
            AuditAction.LEAVE_DECIDED,
            actor_id=actor_id,
            entity_type="leave_request",
            entity_id=request.id,
            description=f"{status.value.title()} leave for {request.from_date} to {request.to_date}",
        )
        await self._notify(
            request.employee_id,
            f"Leave {status.value}",
            f"Your leave for {request.from_date} to {request.to_date} was {status.value}.",
            "/workforce/leave",
            f"leave_{status.value}",
        )
        return request

    async def cancel_leave(
        self,
        request_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        scope: EmployeeScope | None = None,
    ) -> LeaveRequest:
        request = await self.get_leave_request(request_id, scope=scope)
        if request.status == ApprovalStatus.CANCELLED.value:
            raise ConflictError("This request is already cancelled.", error_code="already_cancelled")
        if request.status == ApprovalStatus.REJECTED.value:
            raise ConflictError("A rejected request cannot be cancelled.", error_code="already_decided")
        if request.to_date < self._today():
            raise ConflictError(
                "Leave that has already been taken cannot be cancelled.", error_code="leave_taken"
            )

        was_approved = request.status == ApprovalStatus.APPROVED.value
        await self.leave_requests.update(
            request, {"status": ApprovalStatus.CANCELLED.value}, actor_id=actor_id
        )

        balance = await self._balance_for(request.employee_id, request.leave_type, request.from_date.year)
        field = "used" if was_approved else "pending"
        await self.balances.update(
            balance, {field: getattr(balance, field) - request.days}, actor_id=actor_id
        )

        await self.audit.record_success(
            AuditAction.LEAVE_CANCELLED,
            actor_id=actor_id,
            entity_type="leave_request",
            entity_id=request.id,
            description=f"Cancelled leave for {request.from_date} to {request.to_date}",
        )
        return request

    async def list_leave(
        self, params: LeaveListParams, *, scope: EmployeeScope | None = None
    ) -> tuple[Sequence[LeaveRequest], int]:
        return await self.leave_requests.search(params, visible_ids=visible_employee_ids(scope))

    async def _mark_leave_days(self, request: LeaveRequest, *, actor_id: uuid.UUID | None) -> None:
        """Write the approved days onto the attendance record.

        Without this an approved absence would read as ``absent`` on every
        report, which is exactly the thing the employee asked permission to
        avoid.
        """
        employee = await self.employees.get(request.employee_id)
        location_id = employee.work_location_id if employee else None
        holidays = await self.holidays.dates_between(request.from_date, request.to_date, location_id)
        weekend = await self._weekly_off(request.employee_id, request.from_date)

        for offset in range((request.to_date - request.from_date).days + 1):
            day = request.from_date + timedelta(days=offset)
            if day.weekday() in weekend or day in holidays:
                continue

            existing = await self.attendance.for_day(request.employee_id, day)
            status = (
                AttendanceStatus.HALF_DAY.value
                if request.day_part != LeaveDayPart.FULL_DAY.value
                else AttendanceStatus.LEAVE.value
            )
            if existing is None:
                await self.attendance.add(
                    AttendanceRecord(employee_id=request.employee_id, attendance_date=day, status=status),
                    actor_id=actor_id,
                )
                continue
            await self.attendance.update(existing, {"status": status}, actor_id=actor_id)

    async def _working_days(self, employee_id: uuid.UUID, payload: LeaveApply) -> Decimal:
        """Days a request actually costs, weekends and holidays removed."""
        if payload.day_part is not LeaveDayPart.FULL_DAY:
            return Decimal("0.5")

        employee = await self.employees.get(employee_id)
        location_id = employee.work_location_id if employee else None
        holidays = await self.holidays.dates_between(payload.from_date, payload.to_date, location_id)
        weekend = await self._weekly_off(employee_id, payload.from_date)

        total = 0
        for offset in range((payload.to_date - payload.from_date).days + 1):
            day = payload.from_date + timedelta(days=offset)
            if day.weekday() in weekend or day in holidays:
                continue
            total += 1
        return Decimal(total)

    async def _weekly_off(self, employee_id: uuid.UUID, on: date) -> set[int]:
        """The employee's non-working weekdays, from their shift.

        Falls back to Saturday and Sunday when no shift is assigned -- the
        alternative is treating every day as working, which would overcharge
        anyone without an assignment.
        """
        assignment = await self.assignments.current(employee_id, on)
        if assignment is None or assignment.shift is None:
            return {5, 6}
        return set(assignment.shift.weekly_off or [5, 6])

    async def _balance_for(self, employee_id: uuid.UUID, leave_type: LeaveType, year: int) -> LeaveBalance:
        balance = await self.balances.for_employee(employee_id, leave_type.id, year)
        if balance is not None:
            return balance
        return await self.balances.add(
            LeaveBalance(
                employee_id=employee_id,
                leave_type_id=leave_type.id,
                year=year,
                allocated=leave_type.annual_allocation,
            )
        )

    # ==================================================================
    # Holidays
    # ==================================================================
    async def list_calendars(
        self, year: int | None = None, location_id: uuid.UUID | None = None
    ) -> Sequence[HolidayCalendar]:
        return await self.holidays.calendars(year, location_id)

    async def create_calendar(
        self, payload: HolidayCalendarCreate, *, actor_id: uuid.UUID | None = None
    ) -> HolidayCalendar:
        clash = await self.holidays.find(
            HolidayCalendar.name == payload.name, HolidayCalendar.year == payload.year
        )
        if clash is not None:
            raise ConflictError(
                f'A calendar called "{payload.name}" already exists for {payload.year}.',
                error_code="duplicate_calendar",
            )

        calendar = await self.holidays.add(
            HolidayCalendar(
                name=payload.name,
                year=payload.year,
                location_id=payload.location_id,
                description=payload.description,
                status=RecordStatus.ACTIVE.value,
            ),
            actor_id=actor_id,
        )
        for holiday in payload.holidays:
            self.holidays.session.add(
                Holiday(
                    calendar_id=calendar.id,
                    name=holiday.name,
                    holiday_date=holiday.holiday_date,
                    holiday_type=holiday.holiday_type.value,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        await self.holidays.session.flush()

        await self.audit.record_success(
            AuditAction.HOLIDAY_CALENDAR_CREATED,
            actor_id=actor_id,
            entity_type="holiday_calendar",
            entity_id=calendar.id,
            description=f"Created {calendar.name} with {len(payload.holidays)} holiday(s)",
        )
        reloaded = await self.holidays.detailed(calendar.id)
        if reloaded is None:  # pragma: no cover - just written
            raise NotFoundError("Holiday calendar")
        return reloaded

    async def upcoming_holidays(self) -> Sequence[Holiday]:
        return await self.holidays.upcoming(self._today(), UPCOMING_HOLIDAY_COUNT)

    # ==================================================================
    # Timesheets
    # ==================================================================
    async def get_timesheet(
        self, timesheet_id: uuid.UUID, *, scope: EmployeeScope | None = None
    ) -> Timesheet:
        """One timesheet, by its own id rather than the employee's.

        The scope check has to happen here rather than at the route: the route
        is handed a timesheet id, and whose week it is only becomes knowable
        once the row has been read.
        """
        timesheet = await self.timesheets.detailed(timesheet_id)
        if timesheet is None:
            raise NotFoundError("Timesheet")
        self._assert_in_scope(scope, timesheet.employee_id)
        return timesheet

    async def save_timesheet(
        self, employee_id: uuid.UUID, payload: TimesheetSave, *, actor_id: uuid.UUID | None = None
    ) -> Timesheet:
        """Create or replace a draft week."""
        await self._assert_can_record(employee_id, payload.week_start_date)
        await self._assert_allocations_exist(employee_id, payload)

        timesheet = await self.timesheets.for_week(employee_id, payload.week_start_date)
        if timesheet is not None and timesheet.status not in {
            TimesheetStatus.DRAFT.value,
            TimesheetStatus.REJECTED.value,
        }:
            raise ConflictError(
                f"This week is {timesheet.status} and can no longer be edited.",
                error_code="timesheet_locked",
            )

        if timesheet is None:
            timesheet = await self.timesheets.add(
                Timesheet(employee_id=employee_id, week_start_date=payload.week_start_date),
                actor_id=actor_id,
            )
        else:
            # Replaced wholesale: the grid is the unit of editing, and diffing
            # rows would be a second source of truth for what the week holds.
            timesheet.entries.clear()
            await self.timesheets.session.flush()

        total = Decimal(0)
        billable = Decimal(0)
        for entry in payload.entries:
            self.timesheets.session.add(
                TimesheetEntry(
                    timesheet_id=timesheet.id,
                    **entry.model_dump(),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
            total += entry.hours
            if entry.billable:
                billable += entry.hours

        await self.timesheets.update(
            timesheet,
            {
                "total_hours": total,
                "billable_hours": billable,
                "status": TimesheetStatus.DRAFT.value,
            },
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.TIMESHEET_SAVED,
            actor_id=actor_id,
            entity_type="timesheet",
            entity_id=timesheet.id,
            description=f"Saved timesheet for week beginning {payload.week_start_date}",
            context={"total_hours": str(total)},
        )
        return await self.get_timesheet(timesheet.id)

    async def submit_timesheet(
        self,
        timesheet_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        scope: EmployeeScope | None = None,
    ) -> Timesheet:
        timesheet = await self.get_timesheet(timesheet_id, scope=scope)
        if timesheet.status == TimesheetStatus.SUBMITTED.value:
            raise ConflictError("This timesheet is already submitted.", error_code="already_submitted")
        if timesheet.status == TimesheetStatus.APPROVED.value:
            raise ConflictError("This timesheet is already approved.", error_code="already_approved")
        if not timesheet.entries:
            raise ConflictError("An empty timesheet cannot be submitted.", error_code="empty_timesheet")

        await self.timesheets.update(
            timesheet,
            {"status": TimesheetStatus.SUBMITTED.value, "submitted_at": utc_now()},
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.TIMESHEET_SUBMITTED,
            actor_id=actor_id,
            entity_type="timesheet",
            entity_id=timesheet.id,
            description=f"Submitted timesheet {timesheet.timesheet_code}",
        )
        manager_id = await self._manager_of(timesheet.employee_id)
        if manager_id:
            await self._notify(
                manager_id,
                "Timesheet submitted",
                f"{timesheet.timesheet_code} is waiting for your approval.",
                "/workforce/timesheets",
                "timesheet_submitted",
            )
        return await self.get_timesheet(timesheet.id)

    async def decide_timesheet(
        self,
        timesheet_id: uuid.UUID,
        approved: bool,
        notes: str | None,
        *,
        actor_id: uuid.UUID | None = None,
        scope: EmployeeScope | None = None,
    ) -> Timesheet:
        timesheet = await self.get_timesheet(timesheet_id, scope=scope)
        if timesheet.status != TimesheetStatus.SUBMITTED.value:
            raise ConflictError(
                "Only a submitted timesheet can be approved or rejected.",
                error_code="not_submitted",
            )

        decider = await self._employee_for_user(actor_id)
        # Rejection is a state the employee can see, not a silent reset: the
        # week stays ``rejected`` until it is saved again, and saving is what
        # returns it to draft. An approval therefore always refers to a state
        # somebody actually looked at.
        status = TimesheetStatus.APPROVED if approved else TimesheetStatus.REJECTED
        await self.timesheets.update(
            timesheet,
            {
                "status": status.value,
                "decided_by_id": decider.id if decider else None,
                "decided_at": utc_now(),
                "decision_notes": notes,
            },
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.TIMESHEET_DECIDED,
            actor_id=actor_id,
            entity_type="timesheet",
            entity_id=timesheet.id,
            description=f"{status.value.title()} {timesheet.timesheet_code}",
        )
        await self._notify(
            timesheet.employee_id,
            f"Timesheet {status.value}",
            f"{timesheet.timesheet_code} was {status.value}.",
            "/workforce/timesheets",
            f"timesheet_{status.value}",
        )
        return await self.get_timesheet(timesheet.id)

    async def list_timesheets(
        self, params: TimesheetListParams, *, scope: EmployeeScope | None = None
    ) -> tuple[Sequence[Timesheet], int]:
        return await self.timesheets.search(params, visible_ids=visible_employee_ids(scope))

    async def _assert_allocations_exist(self, employee_id: uuid.UUID, payload: TimesheetSave) -> None:
        """Every entry must fall inside an allocation to the project it books against.

        Two failures, not one. Booking hours to a project nobody assigned you to
        is the obvious one, and it makes the utilisation figures in Project
        Allocation stop reconciling. The quieter one is booking to a project you
        *were* on: an allocation that ended in March does not make April's hours
        billable to it, and an allocation still weeks away does not make this
        week's.

        Checked per date rather than per project, because a week can straddle
        the day an allocation starts or ends.
        """
        if self.allocations is None or not payload.entries:
            return

        for entry in payload.entries:
            allocation = await self.allocations.find(
                EmployeeAllocation.employee_id == employee_id,
                EmployeeAllocation.project_id == entry.project_id,
                EmployeeAllocation.start_date <= entry.work_date,
                or_(
                    EmployeeAllocation.end_date.is_(None),
                    EmployeeAllocation.end_date >= entry.work_date,
                ),
            )
            if allocation is None:
                raise ConflictError(
                    "Hours can only be booked against a project you were allocated to on that date.",
                    error_code="not_allocated",
                )

    # ==================================================================
    # Dashboards, calendar and reports
    # ==================================================================
    async def dashboard(self, on: date | None = None) -> dict[str, Any]:
        day = on or self._today()
        month_start = day.replace(day=1)

        return {
            "on_date": day,
            "present": await self.attendance.count_on(
                day, AttendanceRecord.status == AttendanceStatus.PRESENT.value
            ),
            "absent": await self.attendance.count_on(
                day, AttendanceRecord.status == AttendanceStatus.ABSENT.value
            ),
            "on_leave": await self.leave_requests.on_leave_on(day),
            "remote": await self.attendance.count_on(
                day, AttendanceRecord.work_mode == WorkMode.REMOTE.value
            ),
            "late_arrivals": await self.attendance.count_on(day, AttendanceRecord.late_minutes > 0),
            "missing_timesheets": await self.timesheets.employees_without(self._week_start(day)),
            "leave_requests_pending": await self.leave_requests.count_pending(),
            "regularizations_pending": await self.regularizations.count_pending(),
            "monthly_attendance_percentage": await self.analytics.attendance_percentage(month_start, day),
            "headcount": await self.analytics.headcount(),
            "by_work_mode": await self.attendance.count_by(AttendanceRecord.work_mode, day),
            "by_attendance_status": await self.attendance.count_by(AttendanceRecord.status, day),
        }

    async def timesheet_dashboard(self, week_start: date | None = None) -> dict[str, int]:
        week = week_start or self._week_start(self._today())
        return {
            "draft": await self.timesheets.count_by_status(TimesheetStatus.DRAFT, week),
            "submitted": await self.timesheets.count_by_status(TimesheetStatus.SUBMITTED, week),
            "approved": await self.timesheets.count_by_status(TimesheetStatus.APPROVED, week),
            "rejected": await self.timesheets.count_by_status(TimesheetStatus.REJECTED, week),
            "missing": await self.timesheets.employees_without(week),
        }

    async def calendar(self, employee_id: uuid.UUID, year: int, month: int) -> list[dict[str, Any]]:
        """One month, with attendance, leave, holidays and hours per square."""
        await self._assert_employee_exists(employee_id)
        start = date(year, month, 1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        employee = await self.employees.get(employee_id)
        location_id = employee.work_location_id if employee else None

        records = {r.attendance_date: r for r in await self.attendance.between(employee_id, start, end)}
        holiday_names = {
            holiday.holiday_date: holiday.name
            for holiday in await self.holidays.upcoming(start, 400)
            if start <= holiday.holiday_date <= end
        }
        holiday_dates = await self.holidays.dates_between(start, end, location_id)
        leaves = await self.leave_requests.approved_between(employee_id, start, end)
        hours = await self.timesheets.hours_between(employee_id, start, end)
        weekend = await self._weekly_off(employee_id, start)

        days: list[dict[str, Any]] = []
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            record = records.get(day)
            on_leave = next((leave for leave in leaves if leave.from_date <= day <= leave.to_date), None)
            days.append(
                {
                    "day": day,
                    "is_weekend": day.weekday() in weekend,
                    "holiday_name": holiday_names.get(day) or ("Holiday" if day in holiday_dates else None),
                    "attendance_status": record.status if record else None,
                    "worked_minutes": record.worked_minutes if record else 0,
                    "leave_type": on_leave.leave_type.name if on_leave else None,
                    "timesheet_hours": hours.get(day, Decimal(0)),
                }
            )
        return days

    async def export(self, report: str, fmt: str, start: date, end: date) -> tuple[bytes, str]:
        rows = await self._report_rows(report, start, end)

        if fmt == "csv":
            out = io.StringIO()
            csv.writer(out).writerows(rows)
            return out.getvalue().encode("utf-8-sig"), "text/csv"
        if fmt == "pdf":
            return self._pdf(report, rows), "application/pdf"

        book = Workbook()
        sheet = book.active
        sheet.title = report[:31]
        for row in rows:
            sheet.append(list(row))
        out_bytes = io.BytesIO()
        book.save(out_bytes)
        return (
            out_bytes.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    async def _report_rows(self, report: str, start: date, end: date) -> list[list[Any]]:
        if report == "attendance":
            pairs = await self.analytics.records_with_employees(start, end)
            return [
                ["Employee", "Employee ID", "Date", "Status", "Work mode", "Hours", "Late (min)"],
                *[
                    [
                        employee.full_name,
                        employee.employee_code,
                        record.attendance_date.isoformat(),
                        record.status.replace("_", " "),
                        record.work_mode,
                        round(record.worked_minutes / MINUTES_PER_HOUR, 2),
                        record.late_minutes,
                    ]
                    for record, employee in pairs
                ],
            ]

        if report == "leave-register":
            entries = await self.analytics.leave_register(start, end)
            return [
                ["Employee", "Employee ID", "Leave type", "From", "To", "Days", "Status"],
                *[
                    [
                        employee.full_name,
                        employee.employee_code,
                        leave_type.name,
                        request.from_date.isoformat(),
                        request.to_date.isoformat(),
                        str(request.days),
                        request.status,
                    ]
                    for request, employee, leave_type in entries
                ],
            ]

        if report == "leave-balance":
            balances = await self.analytics.balances_with_employees(start.year)
            return [
                [
                    "Employee",
                    "Employee ID",
                    "Leave type",
                    "Opening",
                    "Allocated",
                    "Used",
                    "Pending",
                    "Remaining",
                ],
                *[
                    [
                        employee.full_name,
                        employee.employee_code,
                        leave_type.name,
                        str(balance.opening_balance),
                        str(balance.allocated),
                        str(balance.used),
                        str(balance.pending),
                        str(balance.remaining),
                    ]
                    for balance, employee, leave_type in balances
                ],
            ]

        if report == "overtime":
            overtime = await self.analytics.overtime_between(start, end)
            return [
                ["Employee", "Employee ID", "Overtime hours"],
                *[
                    [employee.full_name, employee.employee_code, round(minutes / MINUTES_PER_HOUR, 2)]
                    for employee, minutes in overtime
                ],
            ]

        if report == "shift":
            shifts = await self.shifts.active()
            return [
                ["Shift", "Code", "Type", "Start", "End", "Grace (min)", "Break (min)"],
                *[
                    [
                        shift.name,
                        shift.code,
                        shift.shift_type,
                        shift.start_time.isoformat(),
                        shift.end_time.isoformat(),
                        shift.grace_minutes,
                        shift.break_minutes,
                    ]
                    for shift in shifts
                ],
            ]

        # timesheet
        rows, _ = await self.timesheets.search(
            cast(TimesheetListParams, _AllTimesheets(from_date=start, to_date=end))
        )
        return [
            ["Timesheet", "Week beginning", "Status", "Total hours", "Billable hours"],
            *[
                [
                    sheet.timesheet_code,
                    sheet.week_start_date.isoformat(),
                    sheet.status,
                    str(sheet.total_hours),
                    str(sheet.billable_hours),
                ]
                for sheet in rows
            ],
        ]

    @staticmethod
    def _pdf(report: str, rows: list[list[Any]]) -> bytes:
        buffer = io.BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=landscape(A4), title=report)
        table = Table([[str(cell) if cell is not None else "" for cell in row] for row in rows])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f5d5a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c3c3b8")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        document.build([Paragraph(report.replace("-", " ").title()), Spacer(1, 12), table])
        return buffer.getvalue()

    # ==================================================================
    # Helpers
    # ==================================================================
    @staticmethod
    def _today() -> date:
        return datetime.now(UTC).date()

    @staticmethod
    def _week_start(on: date) -> date:
        """The Monday of the week containing ``on``."""
        return on - timedelta(days=on.weekday())

    def _assert_not_future(self, on: date) -> None:
        if on > self._today():
            raise ValidationError(
                "Attendance cannot be recorded for a future date.", error_code="future_date"
            )

    @staticmethod
    def _assert_undecided(status: str, label: str) -> None:
        if status != ApprovalStatus.PENDING.value:
            raise ConflictError(f"This {label} has already been {status}.", error_code="already_decided")

    @staticmethod
    def _assert_in_scope(scope: EmployeeScope | None, employee_id: uuid.UUID) -> None:
        """Refuse a record belonging to somebody outside the caller's team.

        Applied *before* the workflow guards, not after: telling a manager that
        a stranger's leave request "has already been approved" answers a
        question they were not entitled to ask.

        ``None`` means no scope was supplied and the caller is trusted -- the
        seeder, a report, a notification fan-out. Routes always supply one.
        """
        if scope is not None:
            scope.assert_allows(employee_id)

    async def _assert_can_record(self, employee_id: uuid.UUID, on: date) -> None:
        """Refuse new activity from somebody who has left. §21 of the brief.

        Two separate reasons, because they become true at different moments. An
        employee whose offboarding is complete is ``inactive`` and may record
        nothing at all. An employee still on the books but past their last
        working day may record nothing *dated after it* -- they are serving out
        an exit that has not been closed yet, and the fortnight between the two
        is exactly when this would otherwise be missed.

        Historical rows are untouched either way. This guards creation, not
        reading: their attendance, leave and timesheets stay visible to everyone
        who could see them before, which is what §21 requires.
        """
        employee = await self.employees.get(employee_id)
        if employee is None:
            raise ConflictError("No such employee.", error_code="invalid_employee")
        if not employee.is_employed:
            raise ConflictError(
                "This employee has exited and cannot record new activity. "
                "Their existing records remain available.",
                error_code="employee_exited",
            )
        if self.separations is None:
            return
        last_working_day = await self.separations.effective_last_working_day(employee_id)
        if last_working_day is not None and on > last_working_day:
            raise ConflictError(
                f"This date falls after the last working day ({last_working_day.isoformat()}). "
                "No new record can be created for it.",
                error_code="after_last_working_day",
            )

    async def _assert_employee_exists(self, employee_id: uuid.UUID) -> None:
        if await self.employees.get(employee_id) is None:
            raise ConflictError("No such employee.", error_code="invalid_employee")

    async def _employee_for_user(self, user_id: uuid.UUID | None) -> Employee | None:
        if user_id is None:
            return None
        from app.models.employee import Employee

        return await self.employees.find(Employee.user_id == user_id)

    async def _manager_of(self, employee_id: uuid.UUID) -> uuid.UUID | None:
        employee = await self.employees.get(employee_id)
        return employee.reporting_manager_id if employee else None

    async def _notify(self, employee_id: uuid.UUID, title: str, message: str, link: str, kind: str) -> None:
        """Best-effort in-app notification -- never allowed to fail a write."""
        if self.notifications is None:
            return
        employee = await self.employees.get(employee_id)
        if employee is None or employee.user_id is None:
            return
        await self.notifications.add(
            Notification(
                user_id=employee.user_id,
                title=title,
                message=message,
                link=link,
                notification_type=kind,
            )
        )


class _AllTimesheets:
    """Params for an unfiltered timesheet export."""

    employee_id = None
    status = None
    offset = 0
    page_size = 10_000

    def __init__(self, from_date: date, to_date: date) -> None:
        self.from_date = from_date
        self.to_date = to_date
