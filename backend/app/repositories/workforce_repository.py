"""Persistence for Workforce Operations.

Query shapes only. Whether a leave request may be approved, or what a day's
attendance amounts to, belongs to the service.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.employee import Employee
from app.models.enums import (
    ApprovalStatus,
    RecordStatus,
    TimesheetStatus,
)
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
)
from app.repositories.base import BaseRepository
from app.schemas.common import PaginationParams
from app.schemas.workforce import (
    AttendanceListParams,
    LeaveListParams,
    RegularizationListParams,
    ShiftListParams,
    TimesheetListParams,
)


def _page(rows_stmt: Select[Any], params: PaginationParams) -> Select[Any]:
    """Shared paging tail, so every list endpoint counts the same way."""
    return rows_stmt.offset(params.offset).limit(params.page_size)


def _visible(stmt: Select[Any], column: Any, visible_ids: Collection[uuid.UUID] | None) -> Select[Any]:
    """Narrow a list query to the employees the caller may see.

    ``None`` means unrestricted -- HR, Super Admin, or an internal caller with no
    reporting line. An empty collection is the opposite and must not collapse
    into the same branch: it means the caller is entitled to nobody, and the
    honest answer is an empty page rather than the whole company.
    """
    if visible_ids is None:
        return stmt
    return stmt.where(column.in_(visible_ids)) if visible_ids else stmt.where(false())


class ShiftRepository(BaseRepository[Shift]):
    model = Shift

    async def search(self, params: ShiftListParams) -> tuple[Sequence[Shift], int]:
        stmt = self._base_select()
        if params.search:
            term = f"%{params.search}%"
            stmt = stmt.where(or_(Shift.name.ilike(term), Shift.code.ilike(term)))
        if params.shift_type is not None:
            stmt = stmt.where(Shift.shift_type == params.shift_type.value)
        if params.status is not None:
            stmt = stmt.where(Shift.status == params.status.value)
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (await self.session.execute(_page(stmt.order_by(Shift.start_time), params)))
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def active(self) -> Sequence[Shift]:
        stmt = self._base_select().where(Shift.status == RecordStatus.ACTIVE.value)
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def find_by_code(self, code: str) -> Shift | None:
        return (
            (await self.session.execute(select(Shift).where(func.lower(Shift.code) == code.strip().lower())))
            .scalars()
            .first()
        )


class EmployeeShiftRepository(BaseRepository[EmployeeShift]):
    """Append-and-close, never overwrite -- see the model."""

    model = EmployeeShift

    async def current(self, employee_id: uuid.UUID, on: date) -> EmployeeShift | None:
        """The assignment in force on a given day."""
        stmt = (
            self._base_select()
            .where(
                EmployeeShift.employee_id == employee_id,
                EmployeeShift.effective_from <= on,
                or_(EmployeeShift.effective_to.is_(None), EmployeeShift.effective_to >= on),
            )
            .order_by(EmployeeShift.effective_from.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def open_assignment(self, employee_id: uuid.UUID) -> EmployeeShift | None:
        stmt = self._base_select().where(
            EmployeeShift.employee_id == employee_id, EmployeeShift.effective_to.is_(None)
        )
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def history(self, employee_id: uuid.UUID) -> Sequence[EmployeeShift]:
        stmt = (
            self._base_select()
            .where(EmployeeShift.employee_id == employee_id)
            .order_by(EmployeeShift.effective_from.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()


class AttendanceRepository(BaseRepository[AttendanceRecord]):
    model = AttendanceRecord

    async def for_day(self, employee_id: uuid.UUID, on: date) -> AttendanceRecord | None:
        return await self.get_by(employee_id=employee_id, attendance_date=on)

    async def search(
        self, params: AttendanceListParams, *, visible_ids: Collection[uuid.UUID] | None = None
    ) -> tuple[Sequence[AttendanceRecord], int]:
        stmt = self._base_select()
        stmt = self._apply_window(stmt, params, AttendanceRecord.attendance_date)
        stmt = _visible(stmt, AttendanceRecord.employee_id, visible_ids)
        if params.employee_id is not None:
            stmt = stmt.where(AttendanceRecord.employee_id == params.employee_id)
        if params.status is not None:
            stmt = stmt.where(AttendanceRecord.status == params.status.value)

        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    _page(stmt.order_by(AttendanceRecord.attendance_date.desc()), params)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def between(self, employee_id: uuid.UUID, start: date, end: date) -> Sequence[AttendanceRecord]:
        stmt = (
            self._base_select()
            .where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.attendance_date.between(start, end),
            )
            .order_by(AttendanceRecord.attendance_date)
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def count_on(self, on: date, *criteria: ColumnElement[bool]) -> int:
        return await self.count(AttendanceRecord.attendance_date == on, *criteria)

    async def count_by(self, column: Any, on: date) -> list[tuple[str, int]]:
        stmt = (
            select(column, func.count(AttendanceRecord.id))
            .where(AttendanceRecord.deleted_at.is_(None), AttendanceRecord.attendance_date == on)
            .group_by(column)
        )
        return [(row[0], int(row[1])) for row in (await self.session.execute(stmt)).all()]

    async def status_totals(self, start: date, end: date) -> dict[str, int]:
        """Counts per status across a window, for the monthly percentage."""
        stmt = (
            select(AttendanceRecord.status, func.count(AttendanceRecord.id))
            .where(
                AttendanceRecord.deleted_at.is_(None),
                AttendanceRecord.attendance_date.between(start, end),
            )
            .group_by(AttendanceRecord.status)
        )
        return {row[0]: int(row[1]) for row in (await self.session.execute(stmt)).all()}

    @staticmethod
    def _apply_window(stmt: Select[Any], params: Any, column: Any) -> Select[Any]:
        if getattr(params, "from_date", None) is not None:
            stmt = stmt.where(column >= params.from_date)
        if getattr(params, "to_date", None) is not None:
            stmt = stmt.where(column <= params.to_date)
        return stmt


class RegularizationRepository(BaseRepository[AttendanceRegularization]):
    model = AttendanceRegularization

    async def search(
        self, params: RegularizationListParams, *, visible_ids: Collection[uuid.UUID] | None = None
    ) -> tuple[Sequence[AttendanceRegularization], int]:
        stmt = _visible(self._base_select(), AttendanceRegularization.employee_id, visible_ids)
        if params.employee_id is not None:
            stmt = stmt.where(AttendanceRegularization.employee_id == params.employee_id)
        if params.status is not None:
            stmt = stmt.where(AttendanceRegularization.status == params.status.value)

        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    _page(stmt.order_by(AttendanceRegularization.attendance_date.desc()), params)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def pending_for_day(self, employee_id: uuid.UUID, on: date) -> AttendanceRegularization | None:
        stmt = self._base_select().where(
            AttendanceRegularization.employee_id == employee_id,
            AttendanceRegularization.attendance_date == on,
            AttendanceRegularization.status == ApprovalStatus.PENDING.value,
        )
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def count_pending(self) -> int:
        return await self.count(AttendanceRegularization.status == ApprovalStatus.PENDING.value)

    async def count_pending_without_manager(self) -> int:
        """Corrections nobody is going to decide -- same reasoning as leave."""
        stmt = (
            select(func.count(AttendanceRegularization.id))
            .join(Employee, Employee.id == AttendanceRegularization.employee_id)
            .where(
                AttendanceRegularization.deleted_at.is_(None),
                AttendanceRegularization.status == ApprovalStatus.PENDING.value,
                Employee.deleted_at.is_(None),
                Employee.reporting_manager_id.is_(None),
            )
        )
        return int(await self.session.scalar(stmt) or 0)


class LeaveTypeRepository(BaseRepository[LeaveType]):
    model = LeaveType

    async def active(self) -> Sequence[LeaveType]:
        stmt = self._base_select().where(LeaveType.status == RecordStatus.ACTIVE.value)
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def find_by_code(self, code: str) -> LeaveType | None:
        return (
            (
                await self.session.execute(
                    select(LeaveType).where(func.lower(LeaveType.code) == code.strip().lower())
                )
            )
            .scalars()
            .first()
        )


class LeaveBalanceRepository(BaseRepository[LeaveBalance]):
    model = LeaveBalance

    async def for_employee(
        self, employee_id: uuid.UUID, leave_type_id: uuid.UUID, year: int
    ) -> LeaveBalance | None:
        return await self.get_by(employee_id=employee_id, leave_type_id=leave_type_id, year=year)

    async def all_for_employee(self, employee_id: uuid.UUID, year: int) -> Sequence[LeaveBalance]:
        stmt = (
            self._base_select()
            .where(LeaveBalance.employee_id == employee_id, LeaveBalance.year == year)
            .order_by(LeaveBalance.year.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()


class LeaveRequestRepository(BaseRepository[LeaveRequest]):
    model = LeaveRequest

    async def search(
        self, params: LeaveListParams, *, visible_ids: Collection[uuid.UUID] | None = None
    ) -> tuple[Sequence[LeaveRequest], int]:
        stmt = _visible(self._base_select(), LeaveRequest.employee_id, visible_ids)
        if params.employee_id is not None:
            stmt = stmt.where(LeaveRequest.employee_id == params.employee_id)
        if params.leave_type_id is not None:
            stmt = stmt.where(LeaveRequest.leave_type_id == params.leave_type_id)
        if params.status is not None:
            stmt = stmt.where(LeaveRequest.status == params.status.value)
        if params.from_date is not None:
            stmt = stmt.where(LeaveRequest.to_date >= params.from_date)
        if params.to_date is not None:
            stmt = stmt.where(LeaveRequest.from_date <= params.to_date)

        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (await self.session.execute(_page(stmt.order_by(LeaveRequest.from_date.desc()), params)))
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def overlapping(
        self, employee_id: uuid.UUID, start: date, end: date, *, exclude_id: uuid.UUID | None = None
    ) -> LeaveRequest | None:
        """Any live request touching the window.

        Two requests covering the same day would each consume balance for it,
        so the overlap is refused rather than netted off afterwards.
        """
        criteria: list[ColumnElement[bool]] = [
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.deleted_at.is_(None),
            LeaveRequest.status.in_([ApprovalStatus.PENDING.value, ApprovalStatus.APPROVED.value]),
            LeaveRequest.from_date <= end,
            LeaveRequest.to_date >= start,
        ]
        if exclude_id is not None:
            criteria.append(LeaveRequest.id != exclude_id)
        return (await self.session.execute(select(LeaveRequest).where(*criteria))).scalars().first()

    async def approved_between(
        self, employee_id: uuid.UUID, start: date, end: date
    ) -> Sequence[LeaveRequest]:
        stmt = self._base_select().where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == ApprovalStatus.APPROVED.value,
            LeaveRequest.from_date <= end,
            LeaveRequest.to_date >= start,
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def count_pending(self) -> int:
        return await self.count(LeaveRequest.status == ApprovalStatus.PENDING.value)

    async def count_pending_without_manager(self) -> int:
        """Pending requests nobody is going to decide.

        A leave request is addressed to ``reporting_manager_id``. When the
        employee has none recorded, the request sits in a queue with no owner
        and will stay there until somebody notices -- which is precisely the
        subset HR is meant to act on, and the reason the HR dashboard reports it
        separately from the organization-wide pending count.
        """
        stmt = (
            select(func.count(LeaveRequest.id))
            .join(Employee, Employee.id == LeaveRequest.employee_id)
            .where(
                LeaveRequest.deleted_at.is_(None),
                LeaveRequest.status == ApprovalStatus.PENDING.value,
                Employee.deleted_at.is_(None),
                Employee.reporting_manager_id.is_(None),
            )
        )
        return int(await self.session.scalar(stmt) or 0)

    async def days_between(self, start: date, end: date) -> Decimal:
        """Approved leave days whose request *starts* in the window.

        Attributed to the start date rather than spread across the days it
        covers, so a trend line's periods add up to the total and a request
        straddling a month boundary is not counted twice.
        """
        stmt = select(func.coalesce(func.sum(LeaveRequest.days), 0)).where(
            LeaveRequest.deleted_at.is_(None),
            LeaveRequest.status == ApprovalStatus.APPROVED.value,
            LeaveRequest.from_date.between(start, end),
        )
        return Decimal(await self.session.scalar(stmt) or 0)

    async def count_by_type(self, start: date, end: date) -> list[tuple[str, int]]:
        """Approved requests per leave type in a window, largest first."""
        stmt = (
            select(LeaveType.name, func.count(LeaveRequest.id))
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
            .where(
                LeaveRequest.deleted_at.is_(None),
                LeaveRequest.status == ApprovalStatus.APPROVED.value,
                LeaveRequest.from_date.between(start, end),
            )
            .group_by(LeaveType.name)
            .order_by(func.count(LeaveRequest.id).desc(), LeaveType.name)
        )
        return [(row[0], int(row[1])) for row in (await self.session.execute(stmt)).all()]

    async def count_decided_between(self, status: ApprovalStatus, start: date, end: date) -> int:
        stmt = select(func.count(LeaveRequest.id)).where(
            LeaveRequest.deleted_at.is_(None),
            LeaveRequest.status == status.value,
            func.date(LeaveRequest.decided_at).between(start, end),
        )
        return int(await self.session.scalar(stmt) or 0)

    async def oldest_pending_at(self) -> datetime | None:
        """When the longest-waiting pending request arrived."""
        stmt = select(func.min(LeaveRequest.created_at)).where(
            LeaveRequest.deleted_at.is_(None),
            LeaveRequest.status == ApprovalStatus.PENDING.value,
        )
        oldest: datetime | None = await self.session.scalar(stmt)
        return oldest

    async def on_leave_on(self, on: date) -> int:
        return await self.count(
            LeaveRequest.status == ApprovalStatus.APPROVED.value,
            LeaveRequest.from_date <= on,
            LeaveRequest.to_date >= on,
        )


class HolidayRepository(BaseRepository[HolidayCalendar]):
    model = HolidayCalendar

    def _detailed(self) -> Select[tuple[HolidayCalendar]]:
        return self._base_select().options(selectinload(HolidayCalendar.holidays))

    async def detailed(self, calendar_id: uuid.UUID) -> HolidayCalendar | None:
        stmt = (
            self._detailed()
            .where(HolidayCalendar.id == calendar_id)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def calendars(self, year: int | None, location_id: uuid.UUID | None) -> Sequence[HolidayCalendar]:
        stmt = self._detailed()
        if year is not None:
            stmt = stmt.where(HolidayCalendar.year == year)
        if location_id is not None:
            # A calendar with no location applies everywhere, so it is always
            # in scope alongside the location-specific one.
            stmt = stmt.where(
                or_(HolidayCalendar.location_id == location_id, HolidayCalendar.location_id.is_(None))
            )
        return (
            (await self.session.execute(stmt.order_by(HolidayCalendar.year.desc()))).scalars().unique().all()
        )

    async def dates_between(self, start: date, end: date, location_id: uuid.UUID | None = None) -> set[date]:
        """Every holiday date in the window, for leave-day arithmetic."""
        stmt = (
            select(Holiday.holiday_date)
            .join(HolidayCalendar, HolidayCalendar.id == Holiday.calendar_id)
            .where(
                Holiday.deleted_at.is_(None),
                HolidayCalendar.deleted_at.is_(None),
                HolidayCalendar.status == RecordStatus.ACTIVE.value,
                Holiday.holiday_date.between(start, end),
            )
        )
        if location_id is not None:
            stmt = stmt.where(
                or_(HolidayCalendar.location_id == location_id, HolidayCalendar.location_id.is_(None))
            )
        return {row[0] for row in (await self.session.execute(stmt)).all()}

    async def upcoming(self, on: date, limit: int = 5) -> Sequence[Holiday]:
        stmt = (
            select(Holiday)
            .join(HolidayCalendar, HolidayCalendar.id == Holiday.calendar_id)
            .where(
                Holiday.deleted_at.is_(None),
                HolidayCalendar.status == RecordStatus.ACTIVE.value,
                Holiday.holiday_date >= on,
            )
            .order_by(Holiday.holiday_date)
            .limit(limit)
        )
        return (await self.session.execute(stmt)).scalars().unique().all()


class TimesheetRepository(BaseRepository[Timesheet]):
    model = Timesheet

    def _detailed(self) -> Select[tuple[Timesheet]]:
        return self._base_select().options(selectinload(Timesheet.entries))

    async def detailed(self, timesheet_id: uuid.UUID) -> Timesheet | None:
        stmt = self._detailed().where(Timesheet.id == timesheet_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def for_week(self, employee_id: uuid.UUID, week_start: date) -> Timesheet | None:
        stmt = (
            self._detailed()
            .where(Timesheet.employee_id == employee_id, Timesheet.week_start_date == week_start)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def search(
        self, params: TimesheetListParams, *, visible_ids: Collection[uuid.UUID] | None = None
    ) -> tuple[Sequence[Timesheet], int]:
        stmt = _visible(self._detailed(), Timesheet.employee_id, visible_ids)
        if params.employee_id is not None:
            stmt = stmt.where(Timesheet.employee_id == params.employee_id)
        if params.status is not None:
            stmt = stmt.where(Timesheet.status == params.status.value)
        if params.from_date is not None:
            stmt = stmt.where(Timesheet.week_start_date >= params.from_date)
        if params.to_date is not None:
            stmt = stmt.where(Timesheet.week_start_date <= params.to_date)

        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (await self.session.execute(_page(stmt.order_by(Timesheet.week_start_date.desc()), params)))
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def count_by_status(self, status: TimesheetStatus, week_start: date | None = None) -> int:
        criteria: list[ColumnElement[bool]] = [Timesheet.status == status.value]
        if week_start is not None:
            criteria.append(Timesheet.week_start_date == week_start)
        return await self.count(*criteria)

    async def employees_without(self, week_start: date) -> int:
        """Live employees with no timesheet for the week.

        Counted from employees rather than timesheets, because a week nobody
        filed produces no rows at all -- the very case this is meant to surface.
        """
        filed = (
            select(Timesheet.employee_id)
            .where(Timesheet.week_start_date == week_start, Timesheet.deleted_at.is_(None))
            .subquery()
        )
        stmt = (
            select(func.count(Employee.id))
            .outerjoin(filed, filed.c.employee_id == Employee.id)
            .where(Employee.deleted_at.is_(None), filed.c.employee_id.is_(None))
        )
        return int(await self.session.scalar(stmt) or 0)

    async def hours_between(self, employee_id: uuid.UUID, start: date, end: date) -> dict[date, Decimal]:
        """Hours per day, for the calendar view."""
        from app.models.workforce import TimesheetEntry

        stmt = (
            select(TimesheetEntry.work_date, func.sum(TimesheetEntry.hours))
            .join(Timesheet, Timesheet.id == TimesheetEntry.timesheet_id)
            .where(
                Timesheet.employee_id == employee_id,
                Timesheet.deleted_at.is_(None),
                TimesheetEntry.work_date.between(start, end),
            )
            .group_by(TimesheetEntry.work_date)
        )
        return {row[0]: Decimal(row[1] or 0) for row in (await self.session.execute(stmt)).all()}


class WorkforceAnalyticsRepository(BaseRepository[AttendanceRecord]):
    """Cross-entity counts that belong to no single repository."""

    model = AttendanceRecord

    async def headcount(self) -> int:
        return int(
            await self.session.scalar(select(func.count(Employee.id)).where(Employee.deleted_at.is_(None)))
            or 0
        )

    async def attendance_percentage(self, start: date, end: date) -> int:
        """Days credited over days counted, across everyone.

        Holidays and weekends are excluded entirely: counting them as present
        flatters the figure, counting them as absent destroys it.
        """
        from app.models.enums import ATTENDANCE_CREDIT, COUNTED_ATTENDANCE_STATUSES

        stmt = (
            select(AttendanceRecord.status, func.count(AttendanceRecord.id))
            .where(
                AttendanceRecord.deleted_at.is_(None),
                AttendanceRecord.attendance_date.between(start, end),
                AttendanceRecord.status.in_([s.value for s in COUNTED_ATTENDANCE_STATUSES]),
            )
            .group_by(AttendanceRecord.status)
        )
        rows = (await self.session.execute(stmt)).all()
        counted = sum(int(row[1]) for row in rows)
        if not counted:
            return 0
        credited = sum(ATTENDANCE_CREDIT.get(row[0], 0.0) * int(row[1]) for row in rows)
        return round(credited * 100 / counted)

    async def team_summary(self, manager_id: uuid.UUID, on: date) -> list[tuple[str, int]]:
        """A manager's direct reports, grouped by today's attendance status."""
        stmt = (
            select(AttendanceRecord.status, func.count(AttendanceRecord.id))
            .join(Employee, Employee.id == AttendanceRecord.employee_id)
            .where(
                Employee.reporting_manager_id == manager_id,
                Employee.deleted_at.is_(None),
                AttendanceRecord.attendance_date == on,
                AttendanceRecord.deleted_at.is_(None),
            )
            .group_by(AttendanceRecord.status)
        )
        return [(row[0], int(row[1])) for row in (await self.session.execute(stmt)).all()]

    async def overtime_between(self, start: date, end: date) -> list[tuple[Employee, int]]:
        stmt = (
            select(Employee, func.sum(AttendanceRecord.overtime_minutes))
            .join(AttendanceRecord, AttendanceRecord.employee_id == Employee.id)
            .where(
                AttendanceRecord.deleted_at.is_(None),
                AttendanceRecord.attendance_date.between(start, end),
                AttendanceRecord.overtime_minutes > 0,
            )
            .group_by(Employee.id)
            .order_by(func.sum(AttendanceRecord.overtime_minutes).desc())
        )
        return [(row[0], int(row[1] or 0)) for row in (await self.session.execute(stmt)).all()]

    async def records_with_employees(self, start: date, end: date) -> list[tuple[AttendanceRecord, Employee]]:
        stmt = (
            select(AttendanceRecord, Employee)
            .join(Employee, Employee.id == AttendanceRecord.employee_id)
            .where(
                AttendanceRecord.deleted_at.is_(None),
                AttendanceRecord.attendance_date.between(start, end),
            )
            .order_by(Employee.first_name, Employee.last_name, AttendanceRecord.attendance_date)
        )
        return [tuple(row) for row in (await self.session.execute(stmt)).all()]

    async def leave_register(self, start: date, end: date) -> list[tuple[LeaveRequest, Employee, LeaveType]]:
        stmt = (
            select(LeaveRequest, Employee, LeaveType)
            .join(Employee, Employee.id == LeaveRequest.employee_id)
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
            .where(
                LeaveRequest.deleted_at.is_(None),
                LeaveRequest.from_date <= end,
                LeaveRequest.to_date >= start,
            )
            .order_by(LeaveRequest.from_date)
        )
        return [tuple(row) for row in (await self.session.execute(stmt)).all()]

    async def balances_with_employees(self, year: int) -> list[tuple[LeaveBalance, Employee, LeaveType]]:
        stmt = (
            select(LeaveBalance, Employee, LeaveType)
            .join(Employee, Employee.id == LeaveBalance.employee_id)
            .join(LeaveType, LeaveType.id == LeaveBalance.leave_type_id)
            .where(LeaveBalance.deleted_at.is_(None), LeaveBalance.year == year)
            .order_by(Employee.first_name, Employee.last_name)
        )
        return [tuple(row) for row in (await self.session.execute(stmt)).all()]
