"""Workforce operations request and response schemas.

Shape validation only. Anything needing to see other rows -- does this leave
overlap an existing request, is there enough balance, is the employee allocated
to this project -- belongs to the service.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    CREDIT_PERIODS_PER_YEAR,
    MAX_DAILY_HOURS,
    ApprovalStatus,
    AttendanceStatus,
    CreditFrequency,
    HolidayType,
    LeaveDayPart,
    RecordStatus,
    ShiftType,
    TimesheetStatus,
    WorkMode,
)
from app.schemas.common import PaginationParams

READ_CONFIG = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# Shifts
# ----------------------------------------------------------------------
class ShiftCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=2, max_length=30)
    shift_type: ShiftType = ShiftType.GENERAL
    start_time: time
    end_time: time
    grace_minutes: int = Field(default=0, ge=0, le=240)
    break_minutes: int = Field(default=0, ge=0, le=480)
    #: Monday = 0, matching ``date.weekday()``.
    weekly_off: list[int] = Field(default_factory=lambda: [5, 6])
    status: RecordStatus = RecordStatus.ACTIVE

    @model_validator(mode="after")
    def _weekly_off_is_valid(self) -> ShiftCreate:
        if any(day < 0 or day > 6 for day in self.weekly_off):
            raise ValueError("Weekly off days are 0 (Monday) to 6 (Sunday)")
        if len(set(self.weekly_off)) != len(self.weekly_off):
            raise ValueError("A day cannot be listed twice as a weekly off")
        if len(self.weekly_off) >= 7:
            raise ValueError("A shift must have at least one working day")
        return self


class ShiftUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    shift_type: ShiftType | None = None
    start_time: time | None = None
    end_time: time | None = None
    grace_minutes: int | None = Field(None, ge=0, le=240)
    break_minutes: int | None = Field(None, ge=0, le=480)
    weekly_off: list[int] | None = None
    status: RecordStatus | None = None


class ShiftRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    name: str
    code: str
    shift_type: str
    start_time: time
    end_time: time
    grace_minutes: int
    break_minutes: int
    weekly_off: list[int]
    status: str
    created_at: datetime
    deleted_at: datetime | None


class ShiftAssign(BaseModel):
    employee_id: uuid.UUID
    shift_id: uuid.UUID
    effective_from: date


class EmployeeShiftRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    employee_id: uuid.UUID
    shift_id: uuid.UUID
    effective_from: date
    effective_to: date | None
    shift: ShiftRead | None = None


# ----------------------------------------------------------------------
# Attendance
# ----------------------------------------------------------------------
class CheckInRequest(BaseModel):
    work_mode: WorkMode = WorkMode.OFFICE
    notes: str | None = Field(None, max_length=1000)
    #: Back-dating is allowed for a forgotten entry; the service refuses a
    #: future date, which would be a prediction rather than a record.
    attendance_date: date | None = None


class CheckOutRequest(BaseModel):
    notes: str | None = Field(None, max_length=1000)
    attendance_date: date | None = None


class AttendanceRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    employee_id: uuid.UUID
    attendance_date: date
    shift_id: uuid.UUID | None
    check_in_at: datetime | None
    check_out_at: datetime | None
    work_mode: str
    status: str
    worked_minutes: int
    late_minutes: int
    early_exit_minutes: int
    overtime_minutes: int
    notes: str | None


class RegularizationCreate(BaseModel):
    attendance_date: date
    requested_check_in_at: datetime | None = None
    requested_check_out_at: datetime | None = None
    reason: str = Field(min_length=5, max_length=2000)
    supporting_document_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _something_to_correct(self) -> RegularizationCreate:
        if self.requested_check_in_at is None and self.requested_check_out_at is None:
            raise ValueError("Give the check-in time, the check-out time, or both")
        if (
            self.requested_check_in_at
            and self.requested_check_out_at
            and self.requested_check_out_at <= self.requested_check_in_at
        ):
            raise ValueError("Check-out must be after check-in")
        return self


class ApprovalDecision(BaseModel):
    """Shared by every approve/reject action a manager takes."""

    approved: bool
    notes: str | None = Field(None, max_length=2000)


class RegularizationRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    employee_id: uuid.UUID
    attendance_date: date
    requested_check_in_at: datetime | None
    requested_check_out_at: datetime | None
    reason: str
    supporting_document_id: uuid.UUID | None
    status: str
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    decision_notes: str | None
    created_at: datetime


# ----------------------------------------------------------------------
# Leave
# ----------------------------------------------------------------------
class LeavePolicyFields(BaseModel):
    """The schedule an entitlement is credited by, shared by create and update.

    ``annual_allocation`` is the annual maximum and the only figure the engine
    actually credits; these say how it is meant to be reached. Keeping them
    together in one base is what lets the coherence check below run identically
    on a create and on a partial update.
    """

    @model_validator(mode="after")
    def _schedule_fits_the_year(self) -> LeavePolicyFields:
        frequency = getattr(self, "credit_frequency", None)
        amount = getattr(self, "credit_amount", None)
        annual = getattr(self, "annual_allocation", None)

        if frequency is CreditFrequency.NONE and amount:
            raise ValueError("A leave type that is not credited cannot have a credit amount")
        # Only checkable when both halves are present. On a partial update the
        # service re-runs it against the stored values, because a schema can
        # only see the fields it was sent.
        if frequency is not None and amount is not None and annual is not None:
            periods = CREDIT_PERIODS_PER_YEAR[frequency.value]
            if periods and amount * periods > annual:
                raise ValueError(
                    f"{amount} days {periods} times a year is more than the annual maximum of {annual}"
                )
        return self

    @model_validator(mode="after")
    def _window_is_ordered(self) -> LeavePolicyFields:
        start = getattr(self, "effective_from", None)
        end = getattr(self, "effective_to", None)
        if start and end and end < start:
            raise ValueError("A policy cannot stop applying before it starts")
        return self


class LeaveTypeCreate(LeavePolicyFields):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=2, max_length=30)
    description: str | None = Field(None, max_length=2000)
    annual_allocation: Decimal = Field(default=Decimal(0), ge=0, le=365, description="The annual maximum.")
    carry_forward: bool = False
    max_carry_forward: Decimal = Field(default=Decimal(0), ge=0, le=365)
    allows_negative: bool = False
    is_paid: bool = True
    requires_document: bool = False
    status: RecordStatus = RecordStatus.ACTIVE

    credit_frequency: CreditFrequency = CreditFrequency.ANNUALLY
    credit_amount: Decimal = Field(default=Decimal(0), ge=0, le=365)
    prorate_on_joining: bool = False
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def _carry_forward_is_coherent(self) -> LeaveTypeCreate:
        if not self.carry_forward and self.max_carry_forward:
            raise ValueError("Set carry forward on before giving it a maximum")
        if self.carry_forward and self.max_carry_forward <= 0:
            raise ValueError("Carry forward needs a maximum above zero")
        return self


class LeaveTypeUpdate(LeavePolicyFields):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=2000)
    annual_allocation: Decimal | None = Field(None, ge=0, le=365)
    carry_forward: bool | None = None
    max_carry_forward: Decimal | None = Field(None, ge=0, le=365)
    allows_negative: bool | None = None
    is_paid: bool | None = None
    requires_document: bool | None = None
    status: RecordStatus | None = None

    credit_frequency: CreditFrequency | None = None
    credit_amount: Decimal | None = Field(None, ge=0, le=365)
    prorate_on_joining: bool | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class LeaveTypeRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    name: str
    code: str
    description: str | None
    annual_allocation: Decimal
    carry_forward: bool
    max_carry_forward: Decimal
    allows_negative: bool
    is_paid: bool
    requires_document: bool
    status: str

    credit_frequency: str = CreditFrequency.ANNUALLY.value
    credit_amount: Decimal = Decimal(0)
    prorate_on_joining: bool = False
    effective_from: date | None = None
    effective_to: date | None = None


class LeaveBalanceAdjustment(BaseModel):
    """An administrative correction to one employee's entitlement.

    A signed delta rather than a new total: "give her two more days" is what
    somebody actually decides, and it is also what the audit trail has to be
    able to state. A replacement figure records the outcome and loses the act.

    The reason is required and has a floor, because an adjustment with no
    explanation is the one an auditor will ask about and nobody will remember.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    leave_type_id: uuid.UUID
    year: int | None = Field(default=None, ge=2000, le=2100, description="Defaults to the current year.")
    days: Decimal = Field(ge=-365, le=365, decimal_places=1, description="Signed. Negative takes days away.")
    reason: str = Field(min_length=5, max_length=1000)

    @model_validator(mode="after")
    def _adjustment_changes_something(self) -> LeaveBalanceAdjustment:
        if self.days == 0:
            raise ValueError("An adjustment of zero days changes nothing")
        return self


class AttendanceCorrection(BaseModel):
    """An administrative amendment to an attendance record.

    Distinct from :class:`RegularizationCreate`, which is an employee *asking*
    their manager for the same change. This is somebody with
    ``attendance:manage_all`` making it directly, so it carries a reason and is
    audited as an administrative act.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    attendance_date: date
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    status: AttendanceStatus | None = None
    reason: str = Field(min_length=5, max_length=1000)

    @model_validator(mode="after")
    def _something_to_change(self) -> AttendanceCorrection:
        if self.check_in_at is None and self.check_out_at is None and self.status is None:
            raise ValueError("Give a check-in time, a check-out time or a status")
        if self.check_in_at and self.check_out_at and self.check_out_at <= self.check_in_at:
            raise ValueError("Check-out must be after check-in")
        return self


class LeaveApply(BaseModel):
    leave_type_id: uuid.UUID
    from_date: date
    to_date: date
    day_part: LeaveDayPart = LeaveDayPart.FULL_DAY
    reason: str = Field(min_length=3, max_length=2000)
    supporting_document_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _dates_and_day_part_agree(self) -> LeaveApply:
        if self.to_date < self.from_date:
            raise ValueError("Leave cannot end before it starts")
        # Half days only make sense on a single day. Silently rounding a
        # multi-day half-day request would produce a balance nobody can explain.
        if self.day_part is not LeaveDayPart.FULL_DAY and self.from_date != self.to_date:
            raise ValueError("A half day applies to a single date")
        return self


class LeaveRequestRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    from_date: date
    to_date: date
    day_part: str
    days: Decimal
    reason: str
    supporting_document_id: uuid.UUID | None
    status: str
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    decision_notes: str | None
    created_at: datetime
    leave_type: LeaveTypeRead | None = None


class LeaveBalanceRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    year: int
    opening_balance: Decimal
    allocated: Decimal
    used: Decimal
    pending: Decimal
    remaining: Decimal
    leave_type: LeaveTypeRead | None = None


# ----------------------------------------------------------------------
# Holidays
# ----------------------------------------------------------------------
class HolidayInput(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    holiday_date: date
    holiday_type: HolidayType = HolidayType.PUBLIC


class HolidayCalendarCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    year: int = Field(ge=2000, le=2100)
    location_id: uuid.UUID | None = None
    description: str | None = Field(None, max_length=2000)
    holidays: list[HolidayInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _holidays_are_unique_and_in_year(self) -> HolidayCalendarCreate:
        seen = [holiday.holiday_date for holiday in self.holidays]
        if len(set(seen)) != len(seen):
            raise ValueError("The same date is listed twice")
        outside = [d for d in seen if d.year != self.year]
        if outside:
            raise ValueError(f"{outside[0]} does not fall in {self.year}")
        return self


class HolidayRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    calendar_id: uuid.UUID
    name: str
    holiday_date: date
    holiday_type: str


class HolidayCalendarRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    name: str
    year: int
    location_id: uuid.UUID | None
    description: str | None
    status: str
    holidays: list[HolidayRead] = []


# ----------------------------------------------------------------------
# Timesheets
# ----------------------------------------------------------------------
class TimesheetEntryInput(BaseModel):
    project_id: uuid.UUID
    work_date: date
    task: str = Field(min_length=2, max_length=200)
    hours: Decimal = Field(gt=0, le=MAX_DAILY_HOURS, decimal_places=2)
    billable: bool = True
    comments: str | None = Field(None, max_length=1000)


class TimesheetSave(BaseModel):
    """The whole week, saved as one unit.

    Entries are replaced wholesale rather than patched line by line: a
    timesheet is edited as a grid, and diffing rows client-side would be a
    second source of truth for what the week contains.
    """

    week_start_date: date
    entries: list[TimesheetEntryInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _week_is_coherent(self) -> TimesheetSave:
        if self.week_start_date.weekday() != 0:
            raise ValueError("A timesheet week starts on a Monday")

        for entry in self.entries:
            offset = (entry.work_date - self.week_start_date).days
            if offset < 0 or offset > 6:
                raise ValueError(f"{entry.work_date} falls outside the week beginning {self.week_start_date}")

        # Total per day, not per line: four three-hour entries on one day is
        # fine, but twenty-six hours in a day is a typo.
        per_day: dict[date, Decimal] = {}
        for entry in self.entries:
            per_day[entry.work_date] = per_day.get(entry.work_date, Decimal(0)) + entry.hours
        for day, total in per_day.items():
            if total > MAX_DAILY_HOURS:
                raise ValueError(f"{day} totals {total} hours, more than {MAX_DAILY_HOURS}")

        # The same project and task twice on one day is a double entry.
        keys = [(entry.work_date, entry.project_id, entry.task.strip().lower()) for entry in self.entries]
        if len(set(keys)) != len(keys):
            raise ValueError("The same project and task is entered twice on one day")
        return self


class TimesheetEntryRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    timesheet_id: uuid.UUID
    project_id: uuid.UUID
    work_date: date
    task: str
    hours: Decimal
    billable: bool
    comments: str | None


class TimesheetRead(BaseModel):
    model_config = READ_CONFIG
    id: uuid.UUID
    timesheet_code: str
    employee_id: uuid.UUID
    week_start_date: date
    status: str
    total_hours: Decimal
    billable_hours: Decimal
    submitted_at: datetime | None
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    decision_notes: str | None
    entries: list[TimesheetEntryRead] = []


# ----------------------------------------------------------------------
# Listing, calendar and dashboard
# ----------------------------------------------------------------------
class ShiftListParams(PaginationParams):
    search: str | None = Field(default=None, max_length=100, description="Matches shift name or code.")
    shift_type: ShiftType | None = None
    status: RecordStatus | None = None


class AttendanceListParams(PaginationParams):
    employee_id: uuid.UUID | None = None
    status: AttendanceStatus | None = None
    from_date: date | None = None
    to_date: date | None = None


class LeaveListParams(PaginationParams):
    employee_id: uuid.UUID | None = None
    leave_type_id: uuid.UUID | None = None
    status: ApprovalStatus | None = None
    from_date: date | None = None
    to_date: date | None = None


class TimesheetListParams(PaginationParams):
    employee_id: uuid.UUID | None = None
    status: TimesheetStatus | None = None
    from_date: date | None = None
    to_date: date | None = None


class RegularizationListParams(PaginationParams):
    employee_id: uuid.UUID | None = None
    status: ApprovalStatus | None = None


class CalendarDay(BaseModel):
    """One square in the monthly calendar."""

    day: date
    is_weekend: bool
    holiday_name: str | None = None
    attendance_status: str | None = None
    worked_minutes: int = 0
    leave_type: str | None = None
    timesheet_hours: Decimal = Decimal(0)


class CountByLabel(BaseModel):
    label: str
    count: int


class WorkforceDashboard(BaseModel):
    """The figures the workforce dashboard opens with, for one day."""

    on_date: date
    present: int
    absent: int
    on_leave: int
    remote: int
    late_arrivals: int
    missing_timesheets: int
    leave_requests_pending: int
    regularizations_pending: int
    monthly_attendance_percentage: int
    headcount: int
    by_work_mode: list[CountByLabel]
    by_attendance_status: list[CountByLabel]


class TimesheetDashboard(BaseModel):
    draft: int
    submitted: int
    approved: int
    rejected: int
    missing: int


ReportName = Literal["attendance", "leave-register", "leave-balance", "timesheet", "overtime", "shift"]
ExportFormat = Literal["csv", "xlsx", "pdf"]
