"""HR dashboard and administration endpoints.

**HR is not an administrator, and this module is where that is enforced.**

Three kinds of guard appear below, and the difference between them is the whole
access model:

* ``require_org_wide("attendance:view")`` -- an HR *read* across the
  organization. It is the conjunction of "may you use this module" and
  ``employees:view_all``, which is the platform's only scoping permission. An HR
  user without the second sees their own reporting line here and nothing else.
* ``require("leave:policy_manage")`` -- an HR *administrative* action. Seeded HR
  Admin holds this one, because deciding how much casual leave the company gives
  is HR's job by definition.
* ``require("attendance:manage_all")``, ``require("leave:balance_adjust")``,
  ``require("leave:override_approval")``, ``require("timesheets:manage_all")`` --
  administrative actions the seeded HR roles deliberately **do not** hold. They
  amend somebody's record with no request behind it, or decide a request
  addressed to their manager. An organization that wants HR to hold one ticks it
  on the roles screen; nothing here grants it.

Nothing in this module checks a role name. There is no ``if role == "HR"``
anywhere in the codebase, and the three groups above are the only thing
separating an HR Executive from an HR Admin from an Administrator.

What is deliberately absent is as important as what is here: no endpoint below
touches users, roles, permissions, settings or integrations, and none
administers the audit trail. Those are the Administrator's, on their own
modules, behind their own permissions.

Route order matters as elsewhere: static segments precede the ``/{id}`` forms.

NOTE: no ``from __future__ import annotations`` -- FastAPI reads parameter types
from evaluated annotations.
"""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    AuditSvc,
    AuthzSvc,
    CurrentScope,
    CurrentUser,
    DocumentSvc,
    HrSvc,
    WorkforceSvc,
    require,
    require_org_wide,
)
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.audit_log import AuditAction
from app.schemas.common import APIErrorResponse, APIResponse, Page
from app.schemas.document import DocumentReviewRequest
from app.schemas.hr import (
    HrAnalytics,
    HrAttendanceParams,
    HrAttendanceRow,
    HrDashboard,
    HrDocumentParams,
    HrDocumentRow,
    HrEmployeeParams,
    HrEmployeeProfile,
    HrEmployeeRow,
    HrLeaveParams,
    HrLeaveRow,
    HrPageParams,
    HrPerformanceSection,
    HrProjectsSection,
    HrReport,
    HrRequestQueueSection,
    HrTimesheetParams,
    HrTimesheetRow,
)
from app.schemas.workforce import (
    ApprovalDecision,
    AttendanceCorrection,
    AttendanceRead,
    ExportFormat,
    LeaveBalanceAdjustment,
    LeaveRequestRead,
    LeaveTypeCreate,
    LeaveTypeRead,
    LeaveTypeUpdate,
    TimesheetRead,
)
from app.services.hr_service import HrService

router = APIRouter(prefix="/hr", tags=["HR Administration"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_403_FORBIDDEN: {
        "model": APIErrorResponse,
        "description": "Missing the permission, or the record is outside your reach.",
    },
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such record."},
    status.HTTP_409_CONFLICT: {"model": APIErrorResponse, "description": "A workflow rule was violated."},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": APIErrorResponse, "description": "Validation failed."},
}


def _page(rows: list[Any], total: int, params: HrPageParams) -> Page[Any]:
    return Page.create(rows, page=params.page, page_size=params.page_size, total_items=total)


# ----------------------------------------------------------------------
# Dashboard and analytics
# ----------------------------------------------------------------------
@router.get(
    "/dashboard",
    dependencies=[require_org_wide("employees:view")],
    response_model=APIResponse[HrDashboard],
    summary="HR dashboard",
    description=(
        "Employee, attendance, leave, recruitment, document, performance and request "
        "figures. Each section is present only when the caller holds the permission for "
        "the module behind it, and `sections` names the ones that came back -- a block of "
        "zeroes and 'you may not ask' are different answers."
    ),
    responses=_ERRORS,
)
async def dashboard(user: CurrentUser, service: HrSvc) -> APIResponse[HrDashboard]:
    return APIResponse.ok(await service.dashboard(user))


@router.get(
    "/analytics",
    dependencies=[require_org_wide("reports:view")],
    response_model=APIResponse[HrAnalytics],
    summary="HR analytics",
    description=(
        "Headcount, hiring, leave and attendance trends, counted from rows rather than "
        "configured. Attrition is absent: the platform records no leaving date, and a "
        "trend built from one it does not have would be a number nobody could check."
    ),
    responses=_ERRORS,
)
async def analytics(
    user: CurrentUser,
    service: HrSvc,
    months: Annotated[int, Query(ge=1, le=36)] = 12,
) -> APIResponse[HrAnalytics]:
    del user
    return APIResponse.ok(await service.analytics_overview(months=months))


# ----------------------------------------------------------------------
# Employees
# ----------------------------------------------------------------------
@router.get(
    "/employees",
    dependencies=[require_org_wide("employees:view")],
    response_model=APIResponse[Page[HrEmployeeRow]],
    summary="HR employee directory",
    description=(
        "Placement, status and contact details -- what HR operations need. No CTC, no "
        "bank details and no statutory identifiers: those are not fields on this "
        "response, and reaching them needs the employee module's audited reveal endpoint."
    ),
    responses=_ERRORS,
)
async def employees(
    service: HrSvc,
    scope: CurrentScope,
    user: CurrentUser,
    params: Annotated[HrEmployeeParams, Query()],
) -> APIResponse[Page[HrEmployeeRow]]:
    del user
    rows, total = await service.employees_page(params, scope=scope)
    return APIResponse.ok(_page(rows, total, params))


@router.get(
    "/employees/{employee_id}",
    dependencies=[require_org_wide("employees:view")],
    response_model=APIResponse[HrEmployeeProfile],
    summary="HR employee profile",
    description=(
        "The nine tabs in one response. The activity tab needs `audit:view` and comes "
        "back empty without it, with `can_read_activity` saying so."
    ),
    responses=_ERRORS,
)
async def employee_profile(
    employee_id: uuid.UUID,
    service: HrSvc,
    scope: CurrentScope,
    user: CurrentUser,
) -> APIResponse[HrEmployeeProfile]:
    return APIResponse.ok(await service.employee_profile(employee_id, scope=scope, user=user))


# ----------------------------------------------------------------------
# Attendance
# ----------------------------------------------------------------------
@router.post(
    "/attendance/{employee_id}/correct",
    dependencies=[require("attendance:manage_all")],
    response_model=APIResponse[AttendanceRead],
    summary="Correct an attendance record",
    description=(
        "Administrative: amends the day directly, with no correction request behind it. "
        "Needs `attendance:manage_all`, which the seeded HR roles do not hold -- the "
        "ordinary route is the employee raising a correction their manager approves. "
        "Audited, and the employee is notified."
    ),
    responses=_ERRORS,
)
async def correct_attendance(
    employee_id: uuid.UUID,
    payload: AttendanceCorrection,
    service: WorkforceSvc,
    current_user: CurrentUser,
) -> APIResponse[AttendanceRead]:
    record = await service.correct_attendance(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(AttendanceRead.model_validate(record), message="Attendance corrected")


@router.get(
    "/attendance",
    dependencies=[require_org_wide("attendance:view")],
    response_model=APIResponse[Page[HrAttendanceRow]],
    summary="Organization attendance",
    description=(
        "Read-only. Filters by business unit, team, location, manager, employee and "
        "status are applied in the database and intersected with the caller's scope."
    ),
    responses=_ERRORS,
)
async def attendance(
    service: HrSvc,
    scope: CurrentScope,
    user: CurrentUser,
    params: Annotated[HrAttendanceParams, Query()],
) -> APIResponse[Page[HrAttendanceRow]]:
    del user
    rows, total = await service.attendance(params, scope=scope)
    return APIResponse.ok(_page(rows, total, params))


# ----------------------------------------------------------------------
# Leave
# ----------------------------------------------------------------------
@router.get(
    "/leave/policies",
    dependencies=[require_org_wide("leave:view")],
    response_model=APIResponse[list[LeaveTypeRead]],
    summary="Leave policies",
    description=(
        "Every policy, including ones outside their effective window -- an administrator "
        "has to see the policy that expired last month in order to extend it."
    ),
    responses=_ERRORS,
)
async def leave_policies(service: WorkforceSvc, user: CurrentUser) -> APIResponse[list[LeaveTypeRead]]:
    del user
    rows = await service.list_leave_policies()
    return APIResponse.ok([LeaveTypeRead.model_validate(row) for row in rows])


@router.post(
    "/leave/policies",
    dependencies=[require("leave:policy_manage")],
    response_model=APIResponse[LeaveTypeRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a leave policy",
    description=(
        "Credit frequency, credit amount, annual maximum, carry forward, proration and "
        "the effective window. Refused when the schedule credits more than the annual "
        "maximum allows. Audited."
    ),
    responses=_ERRORS,
)
async def create_leave_policy(
    payload: LeaveTypeCreate, service: WorkforceSvc, current_user: CurrentUser
) -> APIResponse[LeaveTypeRead]:
    policy = await service.create_leave_type(payload, actor_id=current_user.id)
    return APIResponse.ok(LeaveTypeRead.model_validate(policy), message="Leave policy created")


@router.patch(
    "/leave/policies/{leave_type_id}",
    dependencies=[require("leave:policy_manage")],
    response_model=APIResponse[LeaveTypeRead],
    summary="Update a leave policy",
    description=(
        "Coherence is checked against the merged values, not the submitted ones: halving "
        "the annual maximum without touching the monthly credit is refused. Audited."
    ),
    responses=_ERRORS,
)
async def update_leave_policy(
    leave_type_id: uuid.UUID,
    payload: LeaveTypeUpdate,
    service: WorkforceSvc,
    current_user: CurrentUser,
) -> APIResponse[LeaveTypeRead]:
    policy = await service.update_leave_type(leave_type_id, payload, actor_id=current_user.id)
    return APIResponse.ok(LeaveTypeRead.model_validate(policy), message="Leave policy updated")


@router.post(
    "/leave/balances/{employee_id}/adjust",
    dependencies=[require("leave:balance_adjust")],
    response_model=APIResponse[Any],
    summary="Adjust a leave balance",
    description=(
        "A signed number of days and a required reason. Applied to the allocation, never "
        "to what has been taken, and refused when it would drop the allocation below what "
        "is already used or held. Needs `leave:balance_adjust`, which the seeded HR roles "
        "do not hold. Audited with the reason."
    ),
    responses=_ERRORS,
)
async def adjust_leave_balance(
    employee_id: uuid.UUID,
    payload: LeaveBalanceAdjustment,
    service: WorkforceSvc,
    current_user: CurrentUser,
) -> APIResponse[Any]:
    balance = await service.adjust_balance(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(
        {
            "id": balance.id,
            "employee_id": balance.employee_id,
            "leave_type_id": balance.leave_type_id,
            "year": balance.year,
            "allocated": balance.allocated,
            "used": balance.used,
            "pending": balance.pending,
            "remaining": balance.remaining,
        },
        message="Leave balance adjusted",
    )


@router.post(
    "/leave/{request_id}/override",
    dependencies=[require("leave:override_approval")],
    response_model=APIResponse[LeaveRequestRead],
    summary="Override a leave decision",
    description=(
        "Decides a request addressed to somebody else's manager. The escape hatch for a "
        "manager who is away, not the normal path -- which is why it needs "
        "`leave:override_approval`, which the seeded HR roles do not hold. Recorded in "
        "the audit trail as an override, separately from the decision itself."
    ),
    responses=_ERRORS,
)
async def override_leave(
    request_id: uuid.UUID,
    payload: ApprovalDecision,
    service: WorkforceSvc,
    current_user: CurrentUser,
) -> APIResponse[LeaveRequestRead]:
    decided = await service.override_leave_decision(
        request_id, payload.approved, payload.notes, actor_id=current_user.id
    )
    return APIResponse.ok(LeaveRequestRead.model_validate(decided), message="Decision overridden")


@router.get(
    "/leave",
    dependencies=[require_org_wide("leave:view")],
    response_model=APIResponse[Page[HrLeaveRow]],
    summary="Organization leave",
    description=(
        "Every request, with the manager it is actually addressed to named on each row. "
        "Read-only: deciding one from here is an override and needs its own permission."
    ),
    responses=_ERRORS,
)
async def leave(
    service: HrSvc,
    scope: CurrentScope,
    user: CurrentUser,
    params: Annotated[HrLeaveParams, Query()],
) -> APIResponse[Page[HrLeaveRow]]:
    del user
    rows, total = await service.leave(params, scope=scope)
    return APIResponse.ok(_page(rows, total, params))


# ----------------------------------------------------------------------
# Timesheets
# ----------------------------------------------------------------------
@router.post(
    "/timesheets/{timesheet_id}/decide",
    dependencies=[require("timesheets:manage_all")],
    response_model=APIResponse[TimesheetRead],
    summary="Decide a timesheet administratively",
    description=(
        "Needs `timesheets:manage_all`. Normal approval stays with the reporting manager; "
        "this is the override, and it is audited as one."
    ),
    responses=_ERRORS,
)
async def decide_timesheet(
    timesheet_id: uuid.UUID,
    payload: ApprovalDecision,
    service: WorkforceSvc,
    current_user: CurrentUser,
) -> APIResponse[TimesheetRead]:
    decided = await service.override_timesheet_decision(
        timesheet_id, payload.approved, payload.notes, actor_id=current_user.id
    )
    return APIResponse.ok(TimesheetRead.model_validate(decided), message="Decision overridden")


@router.get(
    "/timesheets",
    dependencies=[require_org_wide("timesheets:view")],
    response_model=APIResponse[Page[HrTimesheetRow]],
    summary="Organization timesheets",
    description="Read-only. Approving remains the reporting manager's, on the manager screens.",
    responses=_ERRORS,
)
async def timesheets(
    service: HrSvc,
    scope: CurrentScope,
    user: CurrentUser,
    params: Annotated[HrTimesheetParams, Query()],
) -> APIResponse[Page[HrTimesheetRow]]:
    del user
    rows, total = await service.timesheets(params, scope=scope)
    return APIResponse.ok(_page(rows, total, params))


# ----------------------------------------------------------------------
# Documents
# ----------------------------------------------------------------------
@router.post(
    "/documents/{document_id}/review",
    dependencies=[require("documents:update")],
    response_model=APIResponse[HrDocumentRow],
    summary="Review a document",
    description=(
        "Approve, reject or mark under review. Rejecting with notes is what asks the "
        "employee for a re-upload -- the vault notifies them and a rejected document is "
        "the one state they may replace. The same service the document module uses."
    ),
    responses=_ERRORS,
)
async def review_document(
    document_id: uuid.UUID,
    payload: DocumentReviewRequest,
    documents: DocumentSvc,
    service: HrSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
) -> APIResponse[HrDocumentRow]:
    reviewed = await documents.review(document_id, payload, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(await service.as_document_row(reviewed), message="Document reviewed")


@router.get(
    "/documents",
    dependencies=[require_org_wide("documents:view")],
    response_model=APIResponse[Page[HrDocumentRow]],
    summary="Document review queue",
    responses=_ERRORS,
)
async def documents(
    service: HrSvc,
    scope: CurrentScope,
    user: CurrentUser,
    params: Annotated[HrDocumentParams, Query()],
) -> APIResponse[Page[HrDocumentRow]]:
    del user
    rows, total = await service.documents(params, scope=scope)
    return APIResponse.ok(_page(rows, total, params))


# ----------------------------------------------------------------------
# Projects, performance and reports
# ----------------------------------------------------------------------
@router.get(
    "/projects",
    dependencies=[require_org_wide("projects:view")],
    response_model=APIResponse[HrProjectsSection],
    summary="Workforce allocation",
    description=(
        "Allocation and bench, read-only. Creating or changing a project needs "
        "`projects:create` / `projects:update` on the project module; there is no "
        "endpoint here that writes one."
    ),
    responses=_ERRORS,
)
async def projects(service: HrSvc, user: CurrentUser) -> APIResponse[HrProjectsSection]:
    del user
    return APIResponse.ok(HrProjectsSection.model_validate(await service.projects()))


@router.get(
    "/performance",
    dependencies=[require_org_wide("performance:view")],
    response_model=APIResponse[HrPerformanceSection],
    summary="Organization performance",
    description=(
        "Cycle progress and review completion, from the Performance Management module. "
        "Managing a cycle needs that module's own `performance:create` / "
        "`performance:update`, and finalising a rating needs `performance:approve`."
    ),
    responses=_ERRORS,
)
async def performance(service: HrSvc, user: CurrentUser) -> APIResponse[HrPerformanceSection]:
    del user
    return APIResponse.ok(await service.performance_overview())


@router.get(
    "/reports/{report}/export",
    # `reports:export` rather than `view`: every seeded role that can see the
    # catalogue can also export it today, so nobody loses access -- but the two
    # are now separable, which is what the catalogue always promised.
    dependencies=[require("reports:export")],
    summary="Export an HR report",
    description=(
        "Every report names the permissions it needs, and they are checked here as well "
        "as on the catalogue -- a screen that offered a download it could not deliver "
        "would be a UI restriction standing in for an authorization one. Exports are "
        "audited."
    ),
    responses=_ERRORS,
)
async def export_report(
    report: str,
    fmt: ExportFormat,
    service: HrSvc,
    authorization: AuthzSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
    audit: AuditSvc,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
) -> Response:
    try:
        required = HrService.report_permissions(report)
    except KeyError as exc:
        raise NotFoundError("Report") from exc

    held = await authorization.permissions_for(current_user)
    missing = sorted(set(required) - held)
    if missing and not current_user.is_superuser:
        raise PermissionDeniedError(
            "You do not have permission to export this report.",
            details=[{"code": "permission_denied", "message": permission} for permission in missing],
        )

    today = date.today()
    window_start = from_date or today.replace(day=1)
    window_end = to_date or today

    content, media_type = await service.export_report(
        report, fmt, from_date=window_start, to_date=window_end, scope=scope
    )
    await audit.record_success(
        AuditAction.HR_REPORT_EXPORTED,
        actor_id=current_user.id,
        entity_type="hr_report",
        entity_id=None,
        description=f"Exported the {report} report as {fmt}",
        context={"report": report, "format": fmt, "from": str(window_start), "to": str(window_end)},
    )
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{report}.{fmt}"'},
    )


@router.get(
    "/requests",
    dependencies=[require_org_wide("documents:view", "leave:view")],
    response_model=APIResponse[HrRequestQueueSection],
    summary="Employee requests waiting on HR",
    description=(
        "Not the helpdesk -- tickets have their own dashboard at /helpdesk/dashboard. "
        "This counts the request rows that bypass the ticket queue: documents awaiting "
        "review, documents rejected, and the leave and corrections nobody can decide because the "
        "employee has no reporting manager recorded. The queues themselves are at "
        "`/hr/documents` and `/hr/leave`."
    ),
    responses=_ERRORS,
)
async def requests(service: HrSvc, user: CurrentUser) -> APIResponse[HrRequestQueueSection]:
    del user
    return APIResponse.ok(await service.request_queue())


@router.get(
    "/reports",
    dependencies=[require("reports:view")],
    response_model=APIResponse[list[HrReport]],
    summary="HR report catalogue",
    description=(
        "Each entry says which permissions it needs and whether the caller has them, so "
        "an unavailable report explains itself rather than simply being absent."
    ),
    responses=_ERRORS,
)
async def reports(user: CurrentUser, service: HrSvc) -> APIResponse[list[HrReport]]:
    return APIResponse.ok(await service.reports(user))


__all__ = ["router"]
