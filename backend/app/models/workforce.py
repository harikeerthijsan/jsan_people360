"""Workforce operations: shifts, attendance, leave and timesheets.

Three sub-domains that share a spine -- an employee and a date -- and are
deliberately kept separate rather than merged into one "day" record:

* **Attendance** is what happened: when someone arrived and left.
* **Leave** is an agreement about a future absence, approved before the day
  arrives.
* **A timesheet** is what the time was spent *on*, which is a different question
  from whether the person was present and belongs to project reporting.

They meet at the edges -- an approved leave day shows as ``leave`` on the
attendance record -- but a single table would force one lifecycle on three
things that are approved by different people at different times.

Two rules the schema enforces rather than trusting callers to remember:

* **One attendance record per employee per day.** A duplicate would double-count
  in every monthly figure.
* **A shift assignment is closed, never overwritten.** The question "which shift
  was she on in March?" has to stay answerable.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.enums import (
    APPROVAL_STATUS_SQL_VALUES,
    ATTENDANCE_STATUS_SQL_VALUES,
    CREDIT_FREQUENCY_SQL_VALUES,
    HOLIDAY_TYPE_SQL_VALUES,
    LEAVE_DAY_PART_SQL_VALUES,
    MAX_DAILY_HOURS,
    RECORD_STATUS_SQL_VALUES,
    SHIFT_TYPE_SQL_VALUES,
    TIMESHEET_STATUS_SQL_VALUES,
    WORK_MODE_SQL_VALUES,
)

TIMESHEET_CODE_SEQUENCE = "timesheets_code_seq"


class Shift(Base, AuditableBase):
    """A working pattern employees are assigned to."""

    __tablename__ = "shifts"
    __table_args__ = (
        UniqueConstraint("code", name="uq_shifts_code"),
        CheckConstraint(f"shift_type IN ({SHIFT_TYPE_SQL_VALUES})", name="ck_shifts_type"),
        CheckConstraint(f"status IN ({RECORD_STATUS_SQL_VALUES})", name="ck_shifts_status"),
        CheckConstraint("grace_minutes >= 0", name="ck_shifts_grace"),
        CheckConstraint("break_minutes >= 0", name="ck_shifts_break"),
        {"comment": "Configurable working patterns."},
    )

    name: Mapped[str] = mapped_column(String(100), index=True)
    code: Mapped[str] = mapped_column(String(30), index=True)
    shift_type: Mapped[str] = mapped_column(
        String(20), default="general", server_default="general", index=True
    )
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    grace_minutes: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        doc="Minutes after the start time before an arrival counts as late.",
    )
    break_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: Weekday numbers that are non-working, Monday = 0 to match ``date.weekday()``.
    #: A list rather than seven booleans so a four-day week needs no migration.
    weekly_off: Mapped[list[int]] = mapped_column(JSONB, default=list, server_default="[]")
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", index=True)

    @property
    def crosses_midnight(self) -> bool:
        """Whether the shift ends on the following day, e.g. a night shift."""
        return self.end_time <= self.start_time

    def __repr__(self) -> str:
        return f"<Shift {self.code} {self.start_time}-{self.end_time}>"


class EmployeeShift(Base, AuditableBase):
    """Which shift an employee was on, and when.

    Closed and replaced rather than edited, exactly like a project allocation:
    an attendance record from March has to be read against the shift that was in
    force in March, not the one assigned since.
    """

    __tablename__ = "employee_shifts"
    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="ck_employee_shifts_dates"
        ),
        Index("ix_employee_shifts_employee_from", "employee_id", "effective_from"),
        {"comment": "Shift assignment history."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("shifts.id", ondelete="RESTRICT"), index=True
    )
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, doc="Null while this is the current assignment.")

    shift: Mapped[Shift] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return f"<EmployeeShift employee={self.employee_id} from={self.effective_from}>"


class AttendanceRecord(Base, AuditableBase):
    """One employee, one day."""

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("employee_id", "attendance_date", name="uq_attendance_employee_date"),
        CheckConstraint(f"status IN ({ATTENDANCE_STATUS_SQL_VALUES})", name="ck_attendance_status"),
        CheckConstraint(f"work_mode IN ({WORK_MODE_SQL_VALUES})", name="ck_attendance_work_mode"),
        CheckConstraint("worked_minutes >= 0", name="ck_attendance_worked"),
        Index("ix_attendance_date_status", "attendance_date", "status"),
        {"comment": "Daily attendance, one row per employee per day."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    attendance_date: Mapped[date] = mapped_column(Date, index=True)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("shifts.id", ondelete="SET NULL")
    )

    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    work_mode: Mapped[str] = mapped_column(String(20), default="office", server_default="office")
    status: Mapped[str] = mapped_column(String(20), default="present", server_default="present", index=True)

    #: Derived on check-out and stored, because these are read far more often
    #: than they are written and recomputing them per row on every report would
    #: mean re-deriving the shift that applied on the day.
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    late_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    early_exit_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<AttendanceRecord {self.employee_id} {self.attendance_date} {self.status}>"


class AttendanceRegularization(Base, AuditableBase):
    """A request to correct an attendance record."""

    __tablename__ = "attendance_regularizations"
    __table_args__ = (
        CheckConstraint(f"status IN ({APPROVAL_STATUS_SQL_VALUES})", name="ck_regularization_status"),
        Index("ix_regularizations_status_date", "status", "attendance_date"),
        {"comment": "Requests to correct an attendance record."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    attendance_date: Mapped[date] = mapped_column(Date, index=True)
    requested_check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text)
    #: Evidence lives in the Document Vault so it inherits versioning and audit.
    supporting_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<AttendanceRegularization {self.employee_id} {self.attendance_date} {self.status}>"


class LeaveType(Base, AuditableBase):
    """A configurable kind of leave."""

    __tablename__ = "leave_types"
    __table_args__ = (
        UniqueConstraint("code", name="uq_leave_types_code"),
        CheckConstraint(f"status IN ({RECORD_STATUS_SQL_VALUES})", name="ck_leave_types_status"),
        CheckConstraint("annual_allocation >= 0", name="ck_leave_types_allocation"),
        CheckConstraint("max_carry_forward >= 0", name="ck_leave_types_carry"),
        CheckConstraint(
            f"credit_frequency IN ({CREDIT_FREQUENCY_SQL_VALUES})", name="ck_leave_types_credit_frequency"
        ),
        CheckConstraint("credit_amount >= 0", name="ck_leave_types_credit_amount"),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_leave_types_effective_window",
        ),
        Index("ix_leave_types_effective", "effective_from", "effective_to"),
        {"comment": "Configurable leave categories."},
    )

    name: Mapped[str] = mapped_column(String(100), index=True)
    code: Mapped[str] = mapped_column(String(30), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    #: The annual maximum. What the engine actually credits, and what the HR
    #: policy screen labels "Annual maximum" -- the schedule below says how it is
    #: reached, not how much it is.
    annual_allocation: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=0, server_default="0")
    carry_forward: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    max_carry_forward: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=0, server_default="0")

    # -- Policy ---------------------------------------------------------
    #
    # How the annual figure above is arrived at. ``carry_forward`` and
    # ``prorate_on_joining`` are applied when a year's balance row is first
    # created (see ``WorkforceService.balances_for``); ``credit_frequency`` and
    # ``credit_amount`` remain descriptive -- the platform credits the year in
    # one go rather than dripping it, and these record the schedule a drip
    # engine would follow.
    credit_frequency: Mapped[str] = mapped_column(String(20), default="annually", server_default="'annually'")
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=0, server_default="0")
    prorate_on_joining: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    #: The window this policy applies in. Null at either end means open, which is
    #: what every leave type created before policy administration existed has --
    #: so an unset window has to mean "always", not "never".
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)

    def in_force_on(self, on: date) -> bool:
        """Whether this policy applies on a date.

        Asked before a balance row is created and before a type is offered to
        an applicant, so a retired policy stops being selectable without the
        rows it already produced disappearing.
        """
        if self.effective_from is not None and on < self.effective_from:
            return False
        return self.effective_to is None or on <= self.effective_to

    #: Loss of pay is the case this exists for: the balance goes negative by
    #: design rather than the request being refused.
    allows_negative: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    requires_document: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", index=True)

    def __repr__(self) -> str:
        return f"<LeaveType {self.code}>"


class LeaveBalance(Base, AuditableBase):
    """One employee's entitlement for one leave type in one year."""

    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint("employee_id", "leave_type_id", "year", name="uq_leave_balances_employee_type_year"),
        CheckConstraint("year >= 2000", name="ck_leave_balances_year"),
        {"comment": "Leave entitlement and consumption, per year."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("leave_types.id", ondelete="RESTRICT"), index=True
    )
    year: Mapped[int] = mapped_column(Integer, index=True)

    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(5, 1), default=0, server_default="0", doc="Carried forward from last year."
    )
    allocated: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=0, server_default="0")
    used: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=0, server_default="0")
    #: Held against approved-but-not-yet-taken and pending requests, so two
    #: overlapping requests cannot both be approved against the same day.
    pending: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=0, server_default="0")

    leave_type: Mapped[LeaveType] = relationship(lazy="joined")

    @property
    def remaining(self) -> Decimal:
        """Derived, never stored: a stored total is one write away from lying."""
        return self.opening_balance + self.allocated - self.used - self.pending

    def __repr__(self) -> str:
        return f"<LeaveBalance {self.employee_id} {self.year} remaining={self.remaining}>"


class LeaveRequest(Base, AuditableBase):
    """An application for leave."""

    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint("to_date >= from_date", name="ck_leave_requests_dates"),
        CheckConstraint("days > 0", name="ck_leave_requests_days"),
        CheckConstraint(f"status IN ({APPROVAL_STATUS_SQL_VALUES})", name="ck_leave_requests_status"),
        CheckConstraint(f"day_part IN ({LEAVE_DAY_PART_SQL_VALUES})", name="ck_leave_requests_day_part"),
        Index("ix_leave_requests_employee_dates", "employee_id", "from_date", "to_date"),
        {"comment": "Leave applications and their approval state."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("leave_types.id", ondelete="RESTRICT"), index=True
    )
    from_date: Mapped[date] = mapped_column(Date, index=True)
    to_date: Mapped[date] = mapped_column(Date, index=True)
    day_part: Mapped[str] = mapped_column(String(20), default="full_day", server_default="full_day")
    #: Working days only -- weekends and holidays are excluded when it is
    #: calculated, so a Friday-to-Monday request costs two days, not four.
    days: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    reason: Mapped[str] = mapped_column(Text)
    supporting_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(Text)

    leave_type: Mapped[LeaveType] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return f"<LeaveRequest {self.employee_id} {self.from_date}..{self.to_date} {self.status}>"


class HolidayCalendar(Base, AuditableBase):
    """A set of holidays for one location and year."""

    __tablename__ = "holiday_calendars"
    __table_args__ = (
        UniqueConstraint("name", "year", name="uq_holiday_calendars_name_year"),
        CheckConstraint(f"status IN ({RECORD_STATUS_SQL_VALUES})", name="ck_holiday_calendars_status"),
        {"comment": "Holiday calendars, scoped to a location."},
    )

    name: Mapped[str] = mapped_column(String(150), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    #: Null means the calendar applies everywhere -- the common case for a
    #: single-country company, and the sensible default.
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", index=True)

    holidays: Mapped[list[Holiday]] = relationship(
        back_populates="calendar", lazy="selectin", order_by="Holiday.holiday_date"
    )

    def __repr__(self) -> str:
        return f"<HolidayCalendar {self.name} {self.year}>"


class Holiday(Base, AuditableBase):
    """One non-working day."""

    __tablename__ = "holidays"
    __table_args__ = (
        UniqueConstraint("calendar_id", "holiday_date", name="uq_holidays_calendar_date"),
        CheckConstraint(f"holiday_type IN ({HOLIDAY_TYPE_SQL_VALUES})", name="ck_holidays_type"),
        Index("ix_holidays_date", "holiday_date"),
        {"comment": "Individual holidays within a calendar."},
    )

    calendar_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("holiday_calendars.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    holiday_date: Mapped[date] = mapped_column(Date)
    holiday_type: Mapped[str] = mapped_column(String(20), default="public", server_default="public")

    calendar: Mapped[HolidayCalendar] = relationship(back_populates="holidays")

    def __repr__(self) -> str:
        return f"<Holiday {self.name} {self.holiday_date}>"


class Timesheet(Base, AuditableBase):
    """A week of an employee's time, submitted and approved as one unit.

    Separate from attendance on purpose: attendance answers "were they here?",
    a timesheet answers "what did the time go on?". They are approved by
    different people, for different reasons, and one being wrong does not make
    the other wrong.
    """

    __tablename__ = "timesheets"
    __table_args__ = (
        UniqueConstraint("employee_id", "week_start_date", name="uq_timesheets_employee_week"),
        CheckConstraint(f"status IN ({TIMESHEET_STATUS_SQL_VALUES})", name="ck_timesheets_status"),
        Index("ix_timesheets_status_week", "status", "week_start_date"),
        {"comment": "Weekly timesheets."},
    )

    timesheet_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text(f"'TS-' || lpad(nextval('{TIMESHEET_CODE_SEQUENCE}')::text, 6, '0')"),
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    #: Always a Monday, so "the week of" is unambiguous and two people cannot
    #: file overlapping weeks that start on different days.
    week_start_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft", index=True)
    total_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, server_default="0")
    billable_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, server_default="0")

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(Text)

    entries: Mapped[list[TimesheetEntry]] = relationship(
        back_populates="timesheet",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="TimesheetEntry.work_date",
    )

    def __repr__(self) -> str:
        return f"<Timesheet {self.timesheet_code} week={self.week_start_date} {self.status}>"


class TimesheetEntry(Base, AuditableBase):
    """One line: a day, a project, and the hours spent."""

    __tablename__ = "timesheet_entries"
    __table_args__ = (
        CheckConstraint(f"hours > 0 AND hours <= {MAX_DAILY_HOURS}", name="ck_timesheet_entries_hours"),
        Index("ix_timesheet_entries_date", "work_date"),
        {"comment": "Individual timesheet lines."},
    )

    timesheet_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("timesheets.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    work_date: Mapped[date] = mapped_column(Date)
    task: Mapped[str] = mapped_column(String(200))
    hours: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    billable: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    comments: Mapped[str | None] = mapped_column(Text)

    timesheet: Mapped[Timesheet] = relationship(back_populates="entries")

    def __repr__(self) -> str:
        return f"<TimesheetEntry {self.work_date} {self.hours}h>"
