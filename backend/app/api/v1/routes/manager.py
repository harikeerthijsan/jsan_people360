"""Manager and team-management endpoints.

Every route here is about the caller's direct reports and cannot be about
anybody else's.

**No route takes a manager id.** The manager is resolved from the access token,
and their team from the reporting line, so "show me a team" cannot be turned
into "show me *that* team" by editing a request. The one route that names an
employee -- the team member profile -- checks the id against the reporting line
before it reads anything, and the ``employee_id`` filters on the list endpoints
are checked the same way.

**Two gates, both required.** Each route carries a ``require(...)`` permission
guard *and* runs in ``ManagerScope``. The permission answers "may you use this
kind of screen at all", which is why an Employee-role account with direct
reports gets nothing here; the scope answers "about whom", which is why a
Manager-role account with ``leave:approve`` reaches their own reports and stops.
Neither on its own is sufficient, and neither is implemented in React.

**The guards are the *manage-other-people* permissions, not the plain views.**
``attendance:approve`` rather than ``attendance:view``; ``leave:approve`` rather
than ``leave:view``; ``performance:create`` rather than ``performance:view``.
The base Employee role holds every one of the ``view`` permissions -- it has to,
or nobody could see their own attendance -- so guarding a team screen with one
would mean that an employee who happens to have somebody reporting to them
starts reading that person's records without anybody granting them anything.
That is a widening, and it is the same trap ``require_self_or`` documents in
:mod:`app.api.deps`. Document completion needs ``employees:view`` *and*
``documents:view`` together for the same reason: on its own, ``documents:view``
is a permission every employee has.

``ManagerScope`` is deliberately not ``CurrentScope``: it excludes the caller
and ignores ``employees:view_all``. See :func:`app.api.deps.get_manager_scope`.

Route order matters as elsewhere: static segments precede the ``/{id}`` forms.

NOTE: no ``from __future__ import annotations`` -- FastAPI reads parameter types
from evaluated annotations, and postponed evaluation breaks ``Annotated[...,
Query()]``.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import (
    CurrentEmployee,
    CurrentUser,
    ManagerScope,
    ManagerSvc,
    require,
)
from app.schemas.common import APIErrorResponse, APIResponse, Page
from app.schemas.manager import (
    ManagerDashboard,
    ManagerPageParams,
    TeamAttendanceParams,
    TeamAttendanceRow,
    TeamCalendar,
    TeamDocumentStatus,
    TeamLeaveParams,
    TeamLeaveRow,
    TeamListParams,
    TeamMember,
    TeamMemberProfile,
    TeamPerformance,
    TeamProject,
    TeamRegularizationParams,
    TeamRegularizationRow,
    TeamTimesheetParams,
    TeamTimesheetRow,
)
from app.schemas.workforce import (
    ApprovalDecision,
    LeaveRequestRead,
    RegularizationRead,
    TimesheetRead,
)

router = APIRouter(prefix="/manager", tags=["Manager & Team"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_403_FORBIDDEN: {
        "model": APIErrorResponse,
        "description": "Missing the permission, or the record is outside your team.",
    },
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such record."},
    status.HTTP_409_CONFLICT: {"model": APIErrorResponse, "description": "A workflow rule was violated."},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": APIErrorResponse, "description": "Validation failed."},
}


def _page(rows: list[Any], total: int, params: ManagerPageParams) -> Page[Any]:
    """Wrap a page of already-assembled rows in the shared envelope."""
    return Page.create(rows, page=params.page, page_size=params.page_size, total_items=total)


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------
@router.get(
    "/dashboard",
    dependencies=[require("employees:view")],
    response_model=APIResponse[ManagerDashboard],
    summary="Manager dashboard",
    description=(
        "Team size, today's attendance, the four approval queues, current allocation and "
        "upcoming holidays -- for the caller's direct reports only. No organization-wide "
        "figure appears on it."
    ),
    responses=_ERRORS,
)
async def dashboard(
    manager: CurrentEmployee, service: ManagerSvc, scope: ManagerScope
) -> APIResponse[ManagerDashboard]:
    return APIResponse.ok(await service.dashboard(manager, scope=scope))


# ----------------------------------------------------------------------
# The team
# ----------------------------------------------------------------------
@router.get(
    "/team",
    dependencies=[require("employees:view")],
    response_model=APIResponse[Page[TeamMember]],
    summary="My team",
    description=(
        "Direct reports, with today's attendance, today's approved leave and today's "
        "allocations. Search and every filter run against the team, so a search that "
        "matches somebody outside it returns nothing rather than revealing them."
    ),
    responses=_ERRORS,
)
async def team(
    service: ManagerSvc,
    scope: ManagerScope,
    current_user: CurrentUser,
    params: Annotated[TeamListParams, Query()],
) -> APIResponse[Page[TeamMember]]:
    del current_user
    rows, total = await service.team(params, scope=scope)
    return APIResponse.ok(_page(rows, total, params))


@router.get(
    "/team/{employee_id}",
    dependencies=[require("employees:view")],
    response_model=APIResponse[TeamMemberProfile],
    summary="A team member's profile",
    description=(
        "Refused with 403 for anybody who does not report to the caller. Carries no CTC, "
        "no bank detail, no statutory identifier and no home address -- those are on the "
        "employee record, behind their own permission and their own audit trail."
    ),
    responses=_ERRORS,
)
async def team_member(
    employee_id: uuid.UUID,
    service: ManagerSvc,
    scope: ManagerScope,
    current_user: CurrentUser,
) -> APIResponse[TeamMemberProfile]:
    del current_user
    return APIResponse.ok(await service.member(employee_id, scope=scope))


# ----------------------------------------------------------------------
# Attendance
# ----------------------------------------------------------------------
@router.get(
    "/attendance/regularizations",
    dependencies=[require("attendance:approve")],
    response_model=APIResponse[Page[TeamRegularizationRow]],
    summary="Team correction requests",
    description="Pending by default, because that is what the screen is for.",
    responses=_ERRORS,
)
async def regularizations(
    service: ManagerSvc,
    scope: ManagerScope,
    current_user: CurrentUser,
    params: Annotated[TeamRegularizationParams, Query()],
) -> APIResponse[Page[TeamRegularizationRow]]:
    del current_user
    rows, total = await service.regularizations(params, scope=scope)
    return APIResponse.ok(_page(rows, total, params))


@router.post(
    "/attendance/regularizations/{request_id}/decide",
    dependencies=[require("attendance:approve")],
    response_model=APIResponse[RegularizationRead],
    summary="Approve or reject a correction",
    description=(
        "Approving is what amends the attendance record -- the manager screens have no "
        "endpoint that edits attendance directly. Refused for another manager's report, "
        "and for the caller's own request."
    ),
    responses=_ERRORS,
)
async def decide_regularization(
    request_id: uuid.UUID,
    payload: ApprovalDecision,
    manager: CurrentEmployee,
    current_user: CurrentUser,
    service: ManagerSvc,
    scope: ManagerScope,
) -> APIResponse[RegularizationRead]:
    decided = await service.decide_regularization(
        manager, request_id, payload, actor_id=current_user.id, scope=scope
    )
    return APIResponse.ok(decided, message="Decision recorded")


@router.get(
    "/attendance",
    dependencies=[require("attendance:approve")],
    response_model=APIResponse[Page[TeamAttendanceRow]],
    summary="Team attendance",
    description=(
        "The register for the caller's direct reports. Read-only: there is no endpoint "
        "here that edits a day, because a correction is a request the employee raises and "
        "the manager approves."
    ),
    responses=_ERRORS,
)
async def attendance(
    service: ManagerSvc,
    scope: ManagerScope,
    current_user: CurrentUser,
    params: Annotated[TeamAttendanceParams, Query()],
) -> APIResponse[Page[TeamAttendanceRow]]:
    del current_user
    rows, total = await service.attendance(params, scope=scope)
    return APIResponse.ok(_page(rows, total, params))


# ----------------------------------------------------------------------
# Leave
# ----------------------------------------------------------------------
@router.post(
    "/leave/{request_id}/decide",
    dependencies=[require("leave:approve")],
    response_model=APIResponse[LeaveRequestRead],
    summary="Approve or reject team leave",
    description=(
        "Approving moves the held balance into used and marks the days on attendance; "
        "rejecting releases it. Refused for another manager's report, and for the "
        "caller's own request -- that one goes to their own manager."
    ),
    responses=_ERRORS,
)
async def decide_leave(
    request_id: uuid.UUID,
    payload: ApprovalDecision,
    manager: CurrentEmployee,
    current_user: CurrentUser,
    service: ManagerSvc,
    scope: ManagerScope,
) -> APIResponse[LeaveRequestRead]:
    decided = await service.decide_leave(manager, request_id, payload, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(decided, message="Decision recorded")


@router.get(
    "/leave",
    dependencies=[require("leave:approve")],
    response_model=APIResponse[Page[TeamLeaveRow]],
    summary="Team leave",
    description="Pending, approved, rejected and upcoming leave for the caller's direct reports.",
    responses=_ERRORS,
)
async def leave(
    service: ManagerSvc,
    scope: ManagerScope,
    current_user: CurrentUser,
    params: Annotated[TeamLeaveParams, Query()],
) -> APIResponse[Page[TeamLeaveRow]]:
    del current_user
    rows, total = await service.leave(params, scope=scope)
    return APIResponse.ok(_page(rows, total, params))


# ----------------------------------------------------------------------
# Timesheets
# ----------------------------------------------------------------------
@router.post(
    "/timesheets/{timesheet_id}/decide",
    dependencies=[require("timesheets:approve")],
    response_model=APIResponse[TimesheetRead],
    summary="Approve a timesheet, or return it for correction",
    description=(
        "Returning it for correction is a rejection carrying notes: a rejected week is the "
        "one state the employee may save over, which is what re-opens it for them."
    ),
    responses=_ERRORS,
)
async def decide_timesheet(
    timesheet_id: uuid.UUID,
    payload: ApprovalDecision,
    manager: CurrentEmployee,
    current_user: CurrentUser,
    service: ManagerSvc,
    scope: ManagerScope,
) -> APIResponse[TimesheetRead]:
    decided = await service.decide_timesheet(
        manager, timesheet_id, payload, actor_id=current_user.id, scope=scope
    )
    return APIResponse.ok(decided, message="Decision recorded")


@router.get(
    "/timesheets/{timesheet_id}",
    dependencies=[require("timesheets:approve")],
    response_model=APIResponse[TimesheetRead],
    summary="One team timesheet",
    responses=_ERRORS,
)
async def timesheet(
    timesheet_id: uuid.UUID,
    service: ManagerSvc,
    scope: ManagerScope,
    current_user: CurrentUser,
) -> APIResponse[TimesheetRead]:
    del current_user
    return APIResponse.ok(await service.timesheet(timesheet_id, scope=scope))


@router.get(
    "/timesheets",
    dependencies=[require("timesheets:approve")],
    response_model=APIResponse[Page[TeamTimesheetRow]],
    summary="Team timesheets",
    responses=_ERRORS,
)
async def timesheets(
    service: ManagerSvc,
    scope: ManagerScope,
    current_user: CurrentUser,
    params: Annotated[TeamTimesheetParams, Query()],
) -> APIResponse[Page[TeamTimesheetRow]]:
    del current_user
    rows, total = await service.timesheets(params, scope=scope)
    return APIResponse.ok(_page(rows, total, params))


# ----------------------------------------------------------------------
# Projects, performance, calendar and documents
# ----------------------------------------------------------------------
@router.get(
    "/projects",
    dependencies=[require("projects:view")],
    response_model=APIResponse[list[TeamProject]],
    summary="Team projects",
    description=(
        "Projects the caller's direct reports are allocated to today, with each person's "
        "share. Read-only: changing an allocation is a Project Allocation action and needs "
        "``projects:update`` on that module."
    ),
    responses=_ERRORS,
)
async def projects(
    service: ManagerSvc, scope: ManagerScope, current_user: CurrentUser
) -> APIResponse[list[TeamProject]]:
    del current_user
    return APIResponse.ok(await service.projects(scope=scope))


@router.get(
    "/performance",
    dependencies=[require("performance:create")],
    response_model=APIResponse[list[TeamPerformance]],
    summary="Team performance",
    description=(
        "Goals, weighted progress, review status and the rating of record for the current "
        "cycle. Read-only here; submitting a manager review is the Performance module's "
        "own endpoint, which this does not duplicate."
    ),
    responses=_ERRORS,
)
async def performance(
    service: ManagerSvc,
    scope: ManagerScope,
    current_user: CurrentUser,
    cycle_id: Annotated[uuid.UUID | None, Query(description="Defaults to the active cycle.")] = None,
) -> APIResponse[list[TeamPerformance]]:
    del current_user
    return APIResponse.ok(await service.team_performance(scope=scope, cycle_id=cycle_id))


@router.get(
    "/calendar",
    dependencies=[require("attendance:approve")],
    response_model=APIResponse[TeamCalendar],
    summary="Team calendar",
    description=(
        "One month of approved leave, the holidays that apply where the team works, "
        "attendance exceptions and joining dates -- as one dated stream."
    ),
    responses=_ERRORS,
)
async def calendar(
    service: ManagerSvc,
    scope: ManagerScope,
    current_user: CurrentUser,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> APIResponse[TeamCalendar]:
    del current_user
    return APIResponse.ok(await service.calendar(year, month, scope=scope))


@router.get(
    "/documents",
    dependencies=[require("employees:view", "documents:view")],
    response_model=APIResponse[list[TeamDocumentStatus]],
    summary="Team document completion",
    description=(
        "Counts per team member: filed, approved, awaiting review, rejected. No document "
        "name, no classification and no file -- an Aadhaar scan and a signed policy are "
        "indistinguishable here. Reaching a document itself needs the vault, which is "
        "scoped and audited separately."
    ),
    responses=_ERRORS,
)
async def document_status(
    service: ManagerSvc, scope: ManagerScope, current_user: CurrentUser
) -> APIResponse[list[TeamDocumentStatus]]:
    del current_user
    return APIResponse.ok(await service.document_status(scope=scope))


__all__ = ["router"]
