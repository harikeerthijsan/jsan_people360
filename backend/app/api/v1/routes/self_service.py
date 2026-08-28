"""Employee self-service endpoints.

Every route in this module is about the caller and cannot be about anybody else.

**No route takes an employee id.** Not "validates one", not "ignores one" --
there is no such path parameter and no such body field anywhere below. The
employee is resolved from the access token by ``CurrentEmployee``, which is
what makes an IDOR here a thing that cannot be written rather than a thing that
must be remembered. The three routes that do take an id -- a leave request, a
timesheet, a document -- take the id *of that record*, and each is checked
against the caller's scope before it is read.

**Authorization is by identity, not by permission.** These endpoints carry no
``require(...)`` guard, for the same reason ``GET /users/me`` carries none:
a permission answers "may you act on this module", and the only record in reach
here is your own. Guarding them would let an administrator take away an
employee's ability to see their own attendance, which is not a thing anybody
wants to be able to do. ``get_current_employee`` is tagged so the RBAC coverage
test recognises this as a deliberate category rather than an omission.

Route order matters as elsewhere: static segments precede the ``/{id}`` forms.

NOTE: no ``from __future__ import annotations`` -- FastAPI reads parameter types
from evaluated annotations, and postponed evaluation breaks ``Annotated[...,
Query()]`` and ``File()``.
"""

import uuid
from datetime import date
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import CurrentEmployee, CurrentUser, SelfScope, SelfServiceSvc
from app.api.v1.routes.documents import _read_upload
from app.schemas.common import APIErrorResponse, APIResponse, Page
from app.schemas.employee import EmployeeAddressInput
from app.schemas.self_service import (
    MyAttendanceParams,
    MyAttendanceSummary,
    MyAttendanceToday,
    MyCheckIn,
    MyCheckOut,
    MyDashboard,
    MyDocument,
    MyDocumentParams,
    MyDocumentType,
    MyDocumentUpload,
    MyHoliday,
    MyLeaveBalance,
    MyLeaveParams,
    MyPageParams,
    MyProfileRead,
    MyProfileUpdate,
    MyProject,
    MyRegularizationParams,
    MyTimesheetParams,
    MyTimesheetWeek,
)
from app.schemas.workforce import (
    AttendanceRead,
    CalendarDay,
    LeaveApply,
    LeaveRequestRead,
    LeaveTypeRead,
    RegularizationCreate,
    RegularizationRead,
    TimesheetRead,
    TimesheetSave,
)

router = APIRouter(prefix="/me", tags=["Employee Self Service"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_403_FORBIDDEN: {
        "model": APIErrorResponse,
        "description": "This account has no employee record, or the record is not yours.",
    },
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such record."},
    status.HTTP_409_CONFLICT: {"model": APIErrorResponse, "description": "A workflow rule was violated."},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": APIErrorResponse, "description": "Validation failed."},
}


def _page(rows: list[Any], total: int, params: MyPageParams) -> Page[Any]:
    """Wrap a page of already-serialised rows in the shared envelope."""
    return Page.create(rows, page=params.page, page_size=params.page_size, total_items=total)


def _content_disposition(filename: str, *, inline: bool) -> str:
    """Same two-form header the vault's own download uses."""
    disposition = "inline" if inline else "attachment"
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "document"
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


# ----------------------------------------------------------------------
# Identity and profile
# ----------------------------------------------------------------------
@router.get(
    "",
    response_model=APIResponse[MyProfileRead],
    summary="My employee record",
    description="The signed-in employee, with the editable and read-only halves marked.",
    responses=_ERRORS,
)
async def me(employee: CurrentEmployee, service: SelfServiceSvc) -> APIResponse[MyProfileRead]:
    return APIResponse.ok(MyProfileRead.from_employee(await service.profile(employee)))


@router.get(
    "/dashboard",
    response_model=APIResponse[MyDashboard],
    summary="My dashboard",
    description=(
        "Today's attendance, this month's summary, leave balances, the current timesheet, "
        "current allocations, recent documents and what is still outstanding -- for the "
        "signed-in employee only."
    ),
    responses=_ERRORS,
)
async def dashboard(
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
    scope: SelfScope,
) -> APIResponse[MyDashboard]:
    return APIResponse.ok(await service.dashboard(employee, user_id=current_user.id, scope=scope))


@router.patch(
    "/profile",
    response_model=APIResponse[MyProfileRead],
    summary="Update my profile",
    description=(
        "Photo, personal email, mobile numbers and emergency contact. Team, designation, "
        "grade, manager, joining date, employment type, location and official email are "
        "not fields on this payload and cannot be sent."
    ),
    responses=_ERRORS,
)
async def update_profile(
    payload: MyProfileUpdate,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
) -> APIResponse[MyProfileRead]:
    updated = await service.update_profile(employee, payload, actor_id=current_user.id)
    return APIResponse.ok(MyProfileRead.from_employee(updated), message="Profile updated successfully")


@router.put(
    "/profile/address",
    response_model=APIResponse[MyProfileRead],
    summary="Set my current or permanent address",
    responses=_ERRORS,
)
async def set_address(
    payload: EmployeeAddressInput,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
) -> APIResponse[MyProfileRead]:
    updated = await service.set_address(employee, payload, actor_id=current_user.id)
    return APIResponse.ok(MyProfileRead.from_employee(updated), message="Address updated successfully")


# ----------------------------------------------------------------------
# Attendance
# ----------------------------------------------------------------------
@router.get(
    "/attendance/today",
    response_model=APIResponse[MyAttendanceToday],
    summary="My attendance today",
    description="What the check-in control renders from, including whether each action is available.",
    responses=_ERRORS,
)
async def attendance_today(
    employee: CurrentEmployee, service: SelfServiceSvc, scope: SelfScope
) -> APIResponse[MyAttendanceToday]:
    return APIResponse.ok(await service.today(employee, scope=scope))


@router.post(
    "/attendance/check-in",
    response_model=APIResponse[AttendanceRead],
    status_code=status.HTTP_201_CREATED,
    summary="Check in",
    description=(
        "Records today's arrival against the shift in force. Refused when the day already "
        "has a check-in, which is also what stops a second check-in after checking out."
    ),
    responses=_ERRORS,
)
async def check_in(
    payload: MyCheckIn,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
) -> APIResponse[AttendanceRead]:
    record = await service.check_in(employee, payload, actor_id=current_user.id)
    return APIResponse.ok(AttendanceRead.model_validate(record), message="Checked in successfully")


@router.post(
    "/attendance/check-out",
    response_model=APIResponse[AttendanceRead],
    summary="Check out",
    description="Closes today's record and calculates worked, early-exit and overtime minutes.",
    responses=_ERRORS,
)
async def check_out(
    payload: MyCheckOut,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
) -> APIResponse[AttendanceRead]:
    record = await service.check_out(employee, payload, actor_id=current_user.id)
    return APIResponse.ok(AttendanceRead.model_validate(record), message="Checked out successfully")


@router.get(
    "/attendance/calendar",
    response_model=APIResponse[list[CalendarDay]],
    summary="My attendance calendar",
    description="One month of my own days: attendance, leave, holidays, weekends and booked hours.",
    responses=_ERRORS,
)
async def attendance_calendar(
    employee: CurrentEmployee,
    service: SelfServiceSvc,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> APIResponse[list[CalendarDay]]:
    days = await service.calendar(employee, year, month)
    return APIResponse.ok([CalendarDay.model_validate(day) for day in days])


@router.get(
    "/attendance/summary",
    response_model=APIResponse[MyAttendanceSummary],
    summary="My attendance totals",
    description="Present, absent, leave and half days, late arrivals, early exits and overtime.",
    responses=_ERRORS,
)
async def attendance_summary(
    employee: CurrentEmployee,
    service: SelfServiceSvc,
    scope: SelfScope,
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
) -> APIResponse[MyAttendanceSummary]:
    return APIResponse.ok(await service.attendance_summary(employee, from_date, to_date, scope=scope))


@router.get(
    "/attendance/regularizations",
    response_model=APIResponse[Page[RegularizationRead]],
    summary="My correction requests",
    description="Pending, approved and rejected corrections, newest first.",
    responses=_ERRORS,
)
async def my_regularizations(
    employee: CurrentEmployee,
    service: SelfServiceSvc,
    scope: SelfScope,
    params: Annotated[MyRegularizationParams, Query()],
) -> APIResponse[Page[RegularizationRead]]:
    rows, total = await service.regularizations(employee, params, scope=scope)
    return APIResponse.ok(_page([RegularizationRead.model_validate(row) for row in rows], total, params))


@router.post(
    "/attendance/regularization",
    response_model=APIResponse[RegularizationRead],
    status_code=status.HTTP_201_CREATED,
    summary="Request an attendance correction",
    description=(
        "The only way an employee changes an attendance record: the request goes to their "
        "manager, and approving it is what amends the day."
    ),
    responses=_ERRORS,
)
async def request_regularization(
    payload: RegularizationCreate,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
    scope: SelfScope,
) -> APIResponse[RegularizationRead]:
    request = await service.request_regularization(employee, payload, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(
        RegularizationRead.model_validate(request), message="Correction requested successfully"
    )


@router.get(
    "/attendance",
    response_model=APIResponse[Page[AttendanceRead]],
    summary="My attendance history",
    responses=_ERRORS,
)
async def my_attendance(
    employee: CurrentEmployee,
    service: SelfServiceSvc,
    scope: SelfScope,
    params: Annotated[MyAttendanceParams, Query()],
) -> APIResponse[Page[AttendanceRead]]:
    rows, total = await service.attendance(employee, params, scope=scope)
    return APIResponse.ok(_page([AttendanceRead.model_validate(row) for row in rows], total, params))


# ----------------------------------------------------------------------
# Leave
# ----------------------------------------------------------------------
@router.get(
    "/leave/balance",
    response_model=APIResponse[list[MyLeaveBalance]],
    summary="My leave balance",
    description=(
        "Allocated, accrued, used, pending and available per leave type. Computed by the "
        "leave engine; the portal only projects it."
    ),
    responses=_ERRORS,
)
async def my_leave_balance(
    employee: CurrentEmployee,
    service: SelfServiceSvc,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> APIResponse[list[MyLeaveBalance]]:
    return APIResponse.ok(await service.leave_balances(employee, year))


@router.get(
    "/leave/types",
    response_model=APIResponse[list[LeaveTypeRead]],
    summary="Leave types I can apply for",
    responses=_ERRORS,
)
async def my_leave_types(
    employee: CurrentEmployee, service: SelfServiceSvc
) -> APIResponse[list[LeaveTypeRead]]:
    del employee
    return APIResponse.ok([LeaveTypeRead.model_validate(row) for row in await service.leave_types()])


@router.post(
    "/leave/{request_id}/cancel",
    response_model=APIResponse[LeaveRequestRead],
    summary="Cancel my leave request",
    description=(
        "Releases the held balance. Refused for leave already taken, and for a request "
        "belonging to anybody else."
    ),
    responses=_ERRORS,
)
async def cancel_my_leave(
    request_id: uuid.UUID,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
    scope: SelfScope,
) -> APIResponse[LeaveRequestRead]:
    request = await service.cancel_leave(employee, request_id, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(LeaveRequestRead.model_validate(request), message="Leave cancelled")


@router.get(
    "/leave",
    response_model=APIResponse[Page[LeaveRequestRead]],
    summary="My leave requests",
    description="Pending, approved, rejected and cancelled requests.",
    responses=_ERRORS,
)
async def my_leave(
    employee: CurrentEmployee,
    service: SelfServiceSvc,
    scope: SelfScope,
    params: Annotated[MyLeaveParams, Query()],
) -> APIResponse[Page[LeaveRequestRead]]:
    rows, total = await service.leave(employee, params, scope=scope)
    return APIResponse.ok(_page([LeaveRequestRead.model_validate(row) for row in rows], total, params))


@router.post(
    "/leave",
    response_model=APIResponse[LeaveRequestRead],
    status_code=status.HTTP_201_CREATED,
    summary="Apply for leave",
    description=(
        "Counted in working days: weekends and holidays inside the range are not charged. "
        "Refused when it overlaps an existing request or exceeds the available balance, and "
        "the balance is held as soon as it is sent."
    ),
    responses=_ERRORS,
)
async def apply_for_leave(
    payload: LeaveApply,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
    scope: SelfScope,
) -> APIResponse[LeaveRequestRead]:
    request = await service.apply_for_leave(employee, payload, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(LeaveRequestRead.model_validate(request), message="Leave applied successfully")


# ----------------------------------------------------------------------
# Timesheets
# ----------------------------------------------------------------------
@router.get(
    "/timesheets/current",
    response_model=APIResponse[MyTimesheetWeek],
    summary="My current timesheet week",
    description=(
        "The week's grid together with the projects I am allocated to. The picker is built "
        "from the allocations rather than the project list, so it cannot offer a project the "
        "save would refuse."
    ),
    responses=_ERRORS,
)
async def my_current_timesheet(
    employee: CurrentEmployee,
    service: SelfServiceSvc,
    scope: SelfScope,
    week_start: Annotated[date | None, Query(description="Any date in the week. Defaults to today.")] = None,
) -> APIResponse[MyTimesheetWeek]:
    return APIResponse.ok(await service.timesheet_week(employee, week_start, scope=scope))


@router.post(
    "/timesheets",
    response_model=APIResponse[TimesheetRead],
    status_code=status.HTTP_201_CREATED,
    summary="Save my timesheet week",
    description=(
        "Creates or replaces the whole week as a draft. Refused when a day totals more than "
        "24 hours, when the same project and task appear twice on a day, when the week is "
        "already submitted or approved, or when a project is one I am not allocated to."
    ),
    responses=_ERRORS,
)
async def save_my_timesheet(
    payload: TimesheetSave,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
    scope: SelfScope,
) -> APIResponse[TimesheetRead]:
    timesheet = await service.save_timesheet(employee, payload, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(TimesheetRead.model_validate(timesheet), message="Timesheet saved")


@router.post(
    "/timesheets/{timesheet_id}/submit",
    response_model=APIResponse[TimesheetRead],
    summary="Submit my timesheet",
    responses=_ERRORS,
)
async def submit_my_timesheet(
    timesheet_id: uuid.UUID,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
    scope: SelfScope,
) -> APIResponse[TimesheetRead]:
    del employee
    timesheet = await service.submit_timesheet(timesheet_id, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(TimesheetRead.model_validate(timesheet), message="Timesheet submitted")


@router.get(
    "/timesheets/{timesheet_id}",
    response_model=APIResponse[TimesheetRead],
    summary="One of my timesheets",
    responses=_ERRORS,
)
async def my_timesheet(
    timesheet_id: uuid.UUID,
    employee: CurrentEmployee,
    service: SelfServiceSvc,
    scope: SelfScope,
) -> APIResponse[TimesheetRead]:
    del employee
    return APIResponse.ok(TimesheetRead.model_validate(await service.timesheet(timesheet_id, scope=scope)))


@router.get(
    "/timesheets",
    response_model=APIResponse[Page[TimesheetRead]],
    summary="My timesheets",
    responses=_ERRORS,
)
async def my_timesheets(
    employee: CurrentEmployee,
    service: SelfServiceSvc,
    scope: SelfScope,
    params: Annotated[MyTimesheetParams, Query()],
) -> APIResponse[Page[TimesheetRead]]:
    rows, total = await service.timesheets(employee, params, scope=scope)
    return APIResponse.ok(_page([TimesheetRead.model_validate(row) for row in rows], total, params))


# ----------------------------------------------------------------------
# Documents
# ----------------------------------------------------------------------
@router.get(
    "/documents/types",
    response_model=APIResponse[list[MyDocumentType]],
    summary="Document types I can file under",
    responses=_ERRORS,
)
async def my_document_types(
    employee: CurrentEmployee, service: SelfServiceSvc
) -> APIResponse[list[MyDocumentType]]:
    del employee
    return APIResponse.ok(await service.selectable_document_types())


@router.post(
    "/documents",
    response_model=APIResponse[MyDocument],
    status_code=status.HTTP_201_CREATED,
    summary="Upload one of my documents",
    description=(
        "Files the document against me. There is no owner field on this request: the vault "
        "records the uploader as the owner. Validated against the file's own signature, so a "
        "renamed executable is refused."
    ),
    responses=_ERRORS,
)
async def upload_my_document(
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
    scope: SelfScope,
    file: Annotated[UploadFile, File(description="The document. PDF, JPG, JPEG or PNG.")],
    name: Annotated[str, Form()],
    category_id: Annotated[uuid.UUID, Form()],
    document_type_id: Annotated[uuid.UUID, Form()],
    description: Annotated[str | None, Form()] = None,
    expiry_date: Annotated[date | None, Form()] = None,
) -> APIResponse[MyDocument]:
    metadata = MyDocumentUpload(
        name=name,
        category_id=category_id,
        document_type_id=document_type_id,
        description=description,
        expiry_date=expiry_date,
    )
    created = await service.upload_document(
        employee, metadata, await _read_upload(file), actor_id=current_user.id, scope=scope
    )
    return APIResponse.ok(created, message="Document uploaded successfully")


@router.post(
    "/documents/{document_id}/replace",
    response_model=APIResponse[MyDocument],
    status_code=status.HTTP_201_CREATED,
    summary="Replace one of my documents",
    description=(
        "Adds a version without removing the previous one -- the normal answer to a "
        "rejection. Refused for documents HR issued to me, such as an offer or relieving "
        "letter."
    ),
    responses=_ERRORS,
)
async def replace_my_document(
    document_id: uuid.UUID,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
    scope: SelfScope,
    file: Annotated[UploadFile, File(description="The replacement file.")],
    notes: Annotated[str | None, Form(description="Why this version was uploaded.")] = None,
) -> APIResponse[MyDocument]:
    updated = await service.replace_document(
        employee,
        document_id,
        await _read_upload(file),
        notes=notes,
        actor_id=current_user.id,
        scope=scope,
    )
    return APIResponse.ok(updated, message="Replacement uploaded successfully")


@router.get(
    "/documents/{document_id}/download",
    summary="Download one of my documents",
    description="Recorded in the document's audit trail, exactly as a download from the vault is.",
    responses=_ERRORS,
)
async def download_my_document(
    document_id: uuid.UUID,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
    scope: SelfScope,
    version_id: Annotated[uuid.UUID | None, Query(description="Omit for the current version.")] = None,
) -> Response:
    payload = await service.read_document_file(
        employee,
        document_id,
        version_id=version_id,
        for_preview=False,
        actor_id=current_user.id,
        scope=scope,
    )
    return Response(
        content=payload.content,
        media_type=payload.content_type,
        headers={
            "Content-Disposition": _content_disposition(payload.filename, inline=False),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/documents/{document_id}/preview",
    summary="Preview one of my documents",
    responses=_ERRORS,
)
async def preview_my_document(
    document_id: uuid.UUID,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: SelfServiceSvc,
    scope: SelfScope,
    version_id: Annotated[uuid.UUID | None, Query(description="Omit for the current version.")] = None,
) -> Response:
    payload = await service.read_document_file(
        employee,
        document_id,
        version_id=version_id,
        for_preview=True,
        actor_id=current_user.id,
        scope=scope,
    )
    return Response(
        content=payload.content,
        media_type=payload.content_type,
        headers={
            "Content-Disposition": _content_disposition(payload.filename, inline=True),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; object-src 'self'",
        },
    )


@router.get(
    "/documents/{document_id}",
    response_model=APIResponse[MyDocument],
    summary="One of my documents",
    description="Includes the rejection reason when there is one, and whether I may replace it.",
    responses=_ERRORS,
)
async def my_document(
    document_id: uuid.UUID,
    employee: CurrentEmployee,
    service: SelfServiceSvc,
    scope: SelfScope,
) -> APIResponse[MyDocument]:
    return APIResponse.ok(await service.document(employee, document_id, scope=scope))


@router.get(
    "/documents",
    response_model=APIResponse[Page[MyDocument]],
    summary="My documents",
    description="Everything filed against me -- what I uploaded and what HR issued to me.",
    responses=_ERRORS,
)
async def my_documents(
    employee: CurrentEmployee,
    service: SelfServiceSvc,
    scope: SelfScope,
    params: Annotated[MyDocumentParams, Query()],
) -> APIResponse[Page[MyDocument]]:
    rows, total = await service.documents(employee, params, scope=scope)
    return APIResponse.ok(_page(rows, total, params))


# ----------------------------------------------------------------------
# Projects and holidays
# ----------------------------------------------------------------------
@router.get(
    "/projects",
    response_model=APIResponse[list[MyProject]],
    summary="My projects",
    description="Read-only, from the Project Allocation module: role, allocation, dates and billing.",
    responses=_ERRORS,
)
async def my_projects(employee: CurrentEmployee, service: SelfServiceSvc) -> APIResponse[list[MyProject]]:
    return APIResponse.ok(await service.projects(employee))


@router.get(
    "/holidays",
    response_model=APIResponse[list[MyHoliday]],
    summary="My holidays",
    description=(
        "The calendar for my work location, plus any calendar that applies everywhere. "
        "Other locations' calendars are not included."
    ),
    responses=_ERRORS,
)
async def my_holidays(
    employee: CurrentEmployee,
    service: SelfServiceSvc,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> APIResponse[list[MyHoliday]]:
    return APIResponse.ok(await service.holidays(employee, year))


__all__ = ["router"]
