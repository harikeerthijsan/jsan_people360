"""Workforce operations endpoints.

Static segments precede the ``/{id}`` forms throughout, or ``/dashboard`` would
be read as an identifier.

NOTE: no ``from __future__ import annotations`` -- FastAPI reads parameter types
from evaluated annotations.
"""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel

from app.api.deps import CurrentScope, CurrentUser, WorkforceSvc, require, require_self_or
from app.schemas.common import APIErrorResponse, APIResponse, Page, PaginationParams
from app.schemas.workforce import (
    ApprovalDecision,
    AttendanceListParams,
    AttendanceRead,
    CalendarDay,
    CheckInRequest,
    CheckOutRequest,
    EmployeeShiftRead,
    ExportFormat,
    HolidayCalendarCreate,
    HolidayCalendarRead,
    LeaveApply,
    LeaveBalanceRead,
    LeaveListParams,
    LeaveRequestRead,
    LeaveTypeCreate,
    LeaveTypeRead,
    LeaveTypeUpdate,
    RegularizationCreate,
    RegularizationListParams,
    RegularizationRead,
    ReportName,
    ShiftAssign,
    ShiftCreate,
    ShiftListParams,
    ShiftRead,
    ShiftUpdate,
    TimesheetDashboard,
    TimesheetListParams,
    TimesheetRead,
    TimesheetSave,
    WorkforceDashboard,
)

router = APIRouter(prefix="/workforce", tags=["Workforce Operations"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such record."},
    status.HTTP_409_CONFLICT: {"model": APIErrorResponse, "description": "A workflow rule was violated."},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": APIErrorResponse, "description": "Validation failed."},
}


def _page(rows: tuple[Sequence[Any], int], params: PaginationParams, schema: type[BaseModel]) -> Page[Any]:
    return Page.create(
        [schema.model_validate(row) for row in rows[0]],
        page=params.page,
        page_size=params.page_size,
        total_items=rows[1],
    )


# ----------------------------------------------------------------------
# Dashboards, calendar and reports
# ----------------------------------------------------------------------
@router.get(
    "/dashboard",
    dependencies=[require("attendance:view")],
    response_model=APIResponse[WorkforceDashboard],
    summary="Workforce dashboard",
)
async def dashboard(
    service: WorkforceSvc,
    current_user: CurrentUser,
    on: Annotated[date | None, Query(description="Defaults to today.")] = None,
) -> APIResponse[WorkforceDashboard]:
    del current_user
    data = await service.dashboard(on)
    for key in ("by_work_mode", "by_attendance_status"):
        data[key] = [{"label": label, "count": count} for label, count in data[key]]
    return APIResponse.ok(WorkforceDashboard.model_validate(data))


@router.get(
    "/timesheets/dashboard",
    dependencies=[require("timesheets:view")],
    response_model=APIResponse[TimesheetDashboard],
    summary="Timesheet dashboard",
)
async def timesheet_dashboard(
    service: WorkforceSvc,
    current_user: CurrentUser,
    week_start: Annotated[date | None, Query()] = None,
) -> APIResponse[TimesheetDashboard]:
    del current_user
    return APIResponse.ok(TimesheetDashboard(**await service.timesheet_dashboard(week_start)))


@router.get(
    "/calendar/{employee_id}",
    dependencies=[require("attendance:view"), require_self_or("attendance:approve", "attendance:export")],
    response_model=APIResponse[list[CalendarDay]],
    summary="Monthly calendar",
    description="Attendance, leave, holidays and timesheet hours for one month.",
    responses=_ERRORS,
)
async def calendar(
    employee_id: uuid.UUID,
    service: WorkforceSvc,
    current_user: CurrentUser,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> APIResponse[list[CalendarDay]]:
    del current_user
    days = await service.calendar(employee_id, year, month)
    return APIResponse.ok([CalendarDay.model_validate(day) for day in days])


@router.get(
    "/reports/export", dependencies=[require("attendance:export")], summary="Export a workforce report"
)
async def export_report(
    report: ReportName,
    fmt: ExportFormat,
    service: WorkforceSvc,
    current_user: CurrentUser,
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
) -> Response:
    del current_user
    content, media_type = await service.export(report, fmt, from_date, to_date)
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{report}.{fmt}"'},
    )


# ----------------------------------------------------------------------
# Shifts
# ----------------------------------------------------------------------
@router.get(
    "/shifts",
    dependencies=[require("shifts:view")],
    response_model=APIResponse[Page[ShiftRead]],
    summary="List shifts",
)
async def list_shifts(
    service: WorkforceSvc, current_user: CurrentUser, params: Annotated[ShiftListParams, Query()]
) -> APIResponse[Page[ShiftRead]]:
    del current_user
    return APIResponse.ok(_page(await service.list_shifts(params), params, ShiftRead))


@router.post(
    "/shifts",
    dependencies=[require("shifts:create")],
    response_model=APIResponse[ShiftRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a shift",
    responses=_ERRORS,
)
async def create_shift(
    payload: ShiftCreate, service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[ShiftRead]:
    shift = await service.create_shift(payload, actor_id=current_user.id)
    return APIResponse.ok(ShiftRead.model_validate(shift), message="Shift created successfully")


@router.patch(
    "/shifts/{shift_id}",
    dependencies=[require("shifts:update")],
    response_model=APIResponse[ShiftRead],
    summary="Update a shift",
    responses=_ERRORS,
)
async def update_shift(
    shift_id: uuid.UUID, payload: ShiftUpdate, service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[ShiftRead]:
    shift = await service.update_shift(shift_id, payload, actor_id=current_user.id)
    return APIResponse.ok(ShiftRead.model_validate(shift), message="Shift updated successfully")


@router.post(
    "/shifts/assign",
    dependencies=[require("shifts:update")],
    response_model=APIResponse[EmployeeShiftRead],
    status_code=status.HTTP_201_CREATED,
    summary="Assign a shift",
    description="Closes the current assignment and opens a new one; history is never overwritten.",
    responses=_ERRORS,
)
async def assign_shift(
    payload: ShiftAssign, service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[EmployeeShiftRead]:
    assignment = await service.assign_shift(payload, actor_id=current_user.id)
    return APIResponse.ok(EmployeeShiftRead.model_validate(assignment), message="Shift assigned successfully")


@router.get(
    "/shifts/history/{employee_id}",
    dependencies=[require("shifts:view"), require_self_or("shifts:update")],
    response_model=APIResponse[list[EmployeeShiftRead]],
    summary="Shift history",
    responses=_ERRORS,
)
async def shift_history(
    employee_id: uuid.UUID, service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[list[EmployeeShiftRead]]:
    del current_user
    rows = await service.shift_history(employee_id)
    return APIResponse.ok([EmployeeShiftRead.model_validate(row) for row in rows])


# ----------------------------------------------------------------------
# Attendance
# ----------------------------------------------------------------------
@router.get(
    "/attendance",
    dependencies=[require("attendance:view")],
    response_model=APIResponse[Page[AttendanceRead]],
    summary="List attendance",
)
async def list_attendance(
    service: WorkforceSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
    params: Annotated[AttendanceListParams, Query()],
) -> APIResponse[Page[AttendanceRead]]:
    del current_user
    rows = await service.list_attendance(params, scope=scope)
    return APIResponse.ok(_page(rows, params, AttendanceRead))


@router.post(
    "/attendance/{employee_id}/check-in",
    dependencies=[require("attendance:create"), require_self_or("attendance:approve")],
    response_model=APIResponse[AttendanceRead],
    status_code=status.HTTP_201_CREATED,
    summary="Check in",
    responses=_ERRORS,
)
async def check_in(
    employee_id: uuid.UUID, payload: CheckInRequest, service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[AttendanceRead]:
    record = await service.check_in(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(AttendanceRead.model_validate(record), message="Checked in successfully")


@router.post(
    "/attendance/{employee_id}/check-out",
    dependencies=[require("attendance:create"), require_self_or("attendance:approve")],
    response_model=APIResponse[AttendanceRead],
    summary="Check out",
    description="Calculates worked, early-exit and overtime minutes against the shift in force.",
    responses=_ERRORS,
)
async def check_out(
    employee_id: uuid.UUID, payload: CheckOutRequest, service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[AttendanceRead]:
    record = await service.check_out(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(AttendanceRead.model_validate(record), message="Checked out successfully")


@router.get(
    "/regularizations",
    dependencies=[require("attendance:view")],
    response_model=APIResponse[Page[RegularizationRead]],
    summary="List correction requests",
)
async def list_regularizations(
    service: WorkforceSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
    params: Annotated[RegularizationListParams, Query()],
) -> APIResponse[Page[RegularizationRead]]:
    del current_user
    rows = await service.list_regularizations(params, scope=scope)
    return APIResponse.ok(_page(rows, params, RegularizationRead))


@router.post(
    "/regularizations/{employee_id}",
    dependencies=[require("attendance:create"), require_self_or("attendance:approve")],
    response_model=APIResponse[RegularizationRead],
    status_code=status.HTTP_201_CREATED,
    summary="Request an attendance correction",
    responses=_ERRORS,
)
async def request_regularization(
    employee_id: uuid.UUID,
    payload: RegularizationCreate,
    service: WorkforceSvc,
    current_user: CurrentUser,
) -> APIResponse[RegularizationRead]:
    request = await service.request_regularization(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(
        RegularizationRead.model_validate(request), message="Correction requested successfully"
    )


@router.post(
    "/regularizations/{request_id}/decide",
    dependencies=[require("attendance:approve")],
    response_model=APIResponse[RegularizationRead],
    summary="Approve or reject a correction",
    description="Approving is what actually amends the attendance record.",
    responses=_ERRORS,
)
async def decide_regularization(
    request_id: uuid.UUID,
    payload: ApprovalDecision,
    service: WorkforceSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
) -> APIResponse[RegularizationRead]:
    request = await service.decide_regularization(
        request_id, payload.approved, payload.notes, actor_id=current_user.id, scope=scope
    )
    return APIResponse.ok(RegularizationRead.model_validate(request), message="Decision recorded")


# ----------------------------------------------------------------------
# Leave
# ----------------------------------------------------------------------
@router.get(
    "/leave/types",
    dependencies=[require("leave:view")],
    response_model=APIResponse[list[LeaveTypeRead]],
    summary="List leave types",
)
async def list_leave_types(
    service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[list[LeaveTypeRead]]:
    del current_user
    rows = await service.list_leave_types()
    return APIResponse.ok([LeaveTypeRead.model_validate(row) for row in rows])


@router.post(
    "/leave/types",
    dependencies=[require("shifts:create")],
    response_model=APIResponse[LeaveTypeRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a leave type",
    responses=_ERRORS,
)
async def create_leave_type(
    payload: LeaveTypeCreate, service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[LeaveTypeRead]:
    leave_type = await service.create_leave_type(payload, actor_id=current_user.id)
    return APIResponse.ok(LeaveTypeRead.model_validate(leave_type), message="Leave type created successfully")


@router.patch(
    "/leave/types/{leave_type_id}",
    dependencies=[require("shifts:update")],
    response_model=APIResponse[LeaveTypeRead],
    summary="Update a leave type",
    responses=_ERRORS,
)
async def update_leave_type(
    leave_type_id: uuid.UUID, payload: LeaveTypeUpdate, service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[LeaveTypeRead]:
    leave_type = await service.update_leave_type(leave_type_id, payload, actor_id=current_user.id)
    return APIResponse.ok(LeaveTypeRead.model_validate(leave_type), message="Leave type updated successfully")


@router.get(
    "/leave/balances/{employee_id}",
    dependencies=[require("leave:view"), require_self_or("leave:approve", "leave:export")],
    response_model=APIResponse[list[LeaveBalanceRead]],
    summary="Leave balances",
    description="Creates the year's balance rows on first read, so a mid-year joiner sees theirs at once.",
    responses=_ERRORS,
)
async def leave_balances(
    employee_id: uuid.UUID,
    service: WorkforceSvc,
    current_user: CurrentUser,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> APIResponse[list[LeaveBalanceRead]]:
    del current_user
    rows = await service.balances_for(employee_id, year)
    return APIResponse.ok([LeaveBalanceRead.model_validate(row) for row in rows])


@router.get(
    "/leave",
    dependencies=[require("leave:view")],
    response_model=APIResponse[Page[LeaveRequestRead]],
    summary="List leave requests",
)
async def list_leave(
    service: WorkforceSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
    params: Annotated[LeaveListParams, Query()],
) -> APIResponse[Page[LeaveRequestRead]]:
    del current_user
    rows = await service.list_leave(params, scope=scope)
    return APIResponse.ok(_page(rows, params, LeaveRequestRead))


@router.post(
    "/leave/{employee_id}",
    dependencies=[require("leave:apply"), require_self_or("leave:approve")],
    response_model=APIResponse[LeaveRequestRead],
    status_code=status.HTTP_201_CREATED,
    summary="Apply for leave",
    description=(
        "Counted in working days: weekends and holidays are excluded, so a Friday-to-Monday "
        "absence costs two days. Refused when it overlaps an existing request or exceeds the balance."
    ),
    responses=_ERRORS,
)
async def apply_for_leave(
    employee_id: uuid.UUID, payload: LeaveApply, service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[LeaveRequestRead]:
    request = await service.apply_for_leave(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(LeaveRequestRead.model_validate(request), message="Leave applied successfully")


@router.post(
    "/leave/{request_id}/decide",
    dependencies=[require("leave:approve")],
    response_model=APIResponse[LeaveRequestRead],
    summary="Approve or reject leave",
    responses=_ERRORS,
)
async def decide_leave(
    request_id: uuid.UUID,
    payload: ApprovalDecision,
    service: WorkforceSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
) -> APIResponse[LeaveRequestRead]:
    request = await service.decide_leave(
        request_id, payload.approved, payload.notes, actor_id=current_user.id, scope=scope
    )
    return APIResponse.ok(LeaveRequestRead.model_validate(request), message="Decision recorded")


@router.post(
    "/leave/{request_id}/cancel",
    dependencies=[require("leave:apply")],
    response_model=APIResponse[LeaveRequestRead],
    summary="Cancel leave",
    description="Releases the held balance. Leave already taken cannot be cancelled.",
    responses=_ERRORS,
)
async def cancel_leave(
    request_id: uuid.UUID, service: WorkforceSvc, current_user: CurrentUser, scope: CurrentScope
) -> APIResponse[LeaveRequestRead]:
    request = await service.cancel_leave(request_id, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(LeaveRequestRead.model_validate(request), message="Leave cancelled")


# ----------------------------------------------------------------------
# Holidays
# ----------------------------------------------------------------------
@router.get(
    "/holidays",
    dependencies=[require("shifts:view")],
    response_model=APIResponse[list[HolidayCalendarRead]],
    summary="List holiday calendars",
)
async def list_calendars(
    service: WorkforceSvc,
    current_user: CurrentUser,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    location_id: Annotated[uuid.UUID | None, Query()] = None,
) -> APIResponse[list[HolidayCalendarRead]]:
    del current_user
    rows = await service.list_calendars(year, location_id)
    return APIResponse.ok([HolidayCalendarRead.model_validate(row) for row in rows])


@router.post(
    "/holidays",
    dependencies=[require("shifts:create")],
    response_model=APIResponse[HolidayCalendarRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a holiday calendar",
    responses=_ERRORS,
)
async def create_calendar(
    payload: HolidayCalendarCreate, service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[HolidayCalendarRead]:
    calendar_record = await service.create_calendar(payload, actor_id=current_user.id)
    return APIResponse.ok(
        HolidayCalendarRead.model_validate(calendar_record), message="Holiday calendar created"
    )


# ----------------------------------------------------------------------
# Timesheets
# ----------------------------------------------------------------------
@router.get(
    "/timesheets",
    dependencies=[require("timesheets:view")],
    response_model=APIResponse[Page[TimesheetRead]],
    summary="List timesheets",
)
async def list_timesheets(
    service: WorkforceSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
    params: Annotated[TimesheetListParams, Query()],
) -> APIResponse[Page[TimesheetRead]]:
    del current_user
    rows = await service.list_timesheets(params, scope=scope)
    return APIResponse.ok(_page(rows, params, TimesheetRead))


@router.post(
    "/timesheets/{employee_id}",
    dependencies=[require("timesheets:create"), require_self_or("timesheets:approve")],
    response_model=APIResponse[TimesheetRead],
    status_code=status.HTTP_201_CREATED,
    summary="Save a timesheet week",
    description=(
        "Creates or replaces the whole week. Refused when a day totals more than 24 hours, "
        "when the same project and task appear twice on a day, or when the employee is not "
        "allocated to a project booked against."
    ),
    responses=_ERRORS,
)
async def save_timesheet(
    employee_id: uuid.UUID, payload: TimesheetSave, service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[TimesheetRead]:
    timesheet = await service.save_timesheet(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(TimesheetRead.model_validate(timesheet), message="Timesheet saved")


@router.get(
    "/timesheets/{timesheet_id}",
    dependencies=[require("timesheets:view")],
    response_model=APIResponse[TimesheetRead],
    summary="Get a timesheet",
    responses=_ERRORS,
)
async def get_timesheet(
    timesheet_id: uuid.UUID, service: WorkforceSvc, current_user: CurrentUser, scope: CurrentScope
) -> APIResponse[TimesheetRead]:
    del current_user
    timesheet = await service.get_timesheet(timesheet_id, scope=scope)
    return APIResponse.ok(TimesheetRead.model_validate(timesheet))


@router.post(
    "/timesheets/{timesheet_id}/submit",
    dependencies=[require("timesheets:create")],
    response_model=APIResponse[TimesheetRead],
    summary="Submit a timesheet",
    responses=_ERRORS,
)
async def submit_timesheet(
    timesheet_id: uuid.UUID, service: WorkforceSvc, current_user: CurrentUser, scope: CurrentScope
) -> APIResponse[TimesheetRead]:
    timesheet = await service.submit_timesheet(timesheet_id, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(TimesheetRead.model_validate(timesheet), message="Timesheet submitted")


@router.post(
    "/timesheets/{timesheet_id}/decide",
    dependencies=[require("timesheets:approve")],
    response_model=APIResponse[TimesheetRead],
    summary="Approve or reject a timesheet",
    description="A rejected timesheet can be saved again, which returns it to draft for resubmission.",
    responses=_ERRORS,
)
async def decide_timesheet(
    timesheet_id: uuid.UUID,
    payload: ApprovalDecision,
    service: WorkforceSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
) -> APIResponse[TimesheetRead]:
    timesheet = await service.decide_timesheet(
        timesheet_id, payload.approved, payload.notes, actor_id=current_user.id, scope=scope
    )
    return APIResponse.ok(TimesheetRead.model_validate(timesheet), message="Decision recorded")
