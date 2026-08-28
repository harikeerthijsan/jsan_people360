"""Employee Management endpoints.

Route ordering matters here for the same reason it does on ``/users``: Starlette
matches in registration order, so the static segments ``/dashboard``, ``/export``
and ``/statuses`` are declared before ``/{employee_id}``. Registered the other
way round, ``/{employee_id}`` would capture "dashboard" and fail to parse it as a
UUID.

Every route is a translation of HTTP to a service call. The rules -- what may
change, what must stay unique, what has to be recorded -- live in
:mod:`app.services.employee_service`.

NOTE: no ``from __future__ import annotations`` -- FastAPI reads parameter types
from evaluated annotations, and postponed evaluation breaks ``Annotated[...,
Query()]`` on the list endpoint.
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    CurrentScope,
    CurrentUser,
    EmployeeDashboardSvc,
    EmployeeSvc,
    require,
    require_team_scope,
)
from app.models.audit_log import AuditAction
from app.schemas.common import APIErrorResponse, APIResponse, Page
from app.schemas.employee import (
    ChangeDesignationRequest,
    ChangeLocationRequest,
    ChangeManagerRequest,
    ChangeStatusRequest,
    ConfirmEmployeeRequest,
    EmployeeAddressInput,
    EmployeeAuditEntry,
    EmployeeBankInput,
    EmployeeBankReveal,
    EmployeeCreate,
    EmployeeDashboardStats,
    EmployeeExportParams,
    EmployeeIdentificationInput,
    EmployeeIdentificationReveal,
    EmployeeListParams,
    EmployeeRead,
    EmployeeSensitiveReveal,
    EmployeeUpdate,
    EmploymentHistoryRead,
    PromoteEmployeeRequest,
    TransferTeamRequest,
)
from app.services.employee_export_service import EXPORT_MEDIA_TYPES, filename_for, render

router = APIRouter(prefix="/employees", tags=["Employees"])

_COMMON_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": APIErrorResponse, "description": "Validation failed."},
}
_NOT_FOUND: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such employee."},
}
_CONFLICT: dict[int | str, dict[str, object]] = {
    status.HTTP_409_CONFLICT: {
        "model": APIErrorResponse,
        "description": "Duplicate identifier, or a referential or lifecycle rule was violated.",
    },
}
_WRITE_ERRORS = {**_COMMON_ERRORS, **_NOT_FOUND, **_CONFLICT}


# ----------------------------------------------------------------------
# Static segments -- must precede /{employee_id}
# ----------------------------------------------------------------------
@router.get(
    "/dashboard",
    dependencies=[require("employees:view")],
    response_model=APIResponse[EmployeeDashboardStats],
    summary="Employee dashboard figures",
    responses={**_COMMON_ERRORS},
)
async def employee_dashboard(
    service: EmployeeDashboardSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeDashboardStats]:
    del current_user
    return APIResponse.ok(await service.stats(), message="Dashboard statistics retrieved successfully")


@router.get(
    "/export",
    dependencies=[require("employees:export")],
    summary="Export the directory",
    description=(
        "Returns the employees matching the current filters as a file. The page "
        "parameters are ignored -- exporting page 1 of 12 is never what was meant. "
        "Bank details and government identifiers are never included."
    ),
    responses={
        **_COMMON_ERRORS,
        status.HTTP_200_OK: {
            "content": {media_type: {} for media_type in EXPORT_MEDIA_TYPES.values()},
            "description": "A CSV or XLSX file.",
        },
    },
)
async def export_employees(
    service: EmployeeSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
    params: Annotated[EmployeeExportParams, Query()],
) -> Response:
    employees = await service.list_for_export(params, scope=scope)
    payload, media_type = render(employees, params.export_format)
    filename = filename_for(params.export_format, today=date.today())

    await service.record_export(
        AuditAction.EMPLOYEE_EXPORTED,
        actor_id=current_user.id,
        row_count=len(employees),
        export_format=params.export_format.value,
    )

    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ----------------------------------------------------------------------
# Directory
# ----------------------------------------------------------------------
@router.get(
    "",
    dependencies=[require("employees:view")],
    response_model=APIResponse[Page[EmployeeRead]],
    summary="List employees",
    description=(
        "Returns a page of employees with search, lifecycle-status filtering, the "
        "full set of organizational filters, a joining-date range and sorting. "
        "Search covers the employee ID, both name parts, the composed full name, "
        "the email fields and the mobile numbers. Live and archived records are "
        "never mixed: pass `archived=true` to see the archive."
    ),
    responses={**_COMMON_ERRORS},
)
async def list_employees(
    service: EmployeeSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
    params: Annotated[EmployeeListParams, Query()],
) -> APIResponse[Page[EmployeeRead]]:
    del current_user
    rows, total = await service.list(params, scope=scope)
    page = Page.create(
        [EmployeeRead.from_employee(row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total_items=total,
    )
    return APIResponse.ok(page, message="Employees retrieved successfully")


@router.post(
    "",
    dependencies=[require("employees:create")],
    response_model=APIResponse[EmployeeRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee",
    description=(
        "Records a new employee together with their addresses, bank details and "
        "government identifiers. The employee ID is generated by the database and "
        "cannot be supplied. Creating the record also writes the opening row of "
        "the employment history."
    ),
    responses={**_COMMON_ERRORS, **_CONFLICT},
)
async def create_employee(
    payload: EmployeeCreate,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    created = await service.create(payload, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(created), message="Employee created successfully")


@router.get(
    "/{employee_id}",
    dependencies=[require("employees:view"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Get an employee",
    description="Bank details and government identifiers come back masked.",
    responses={**_COMMON_ERRORS, **_NOT_FOUND},
)
async def get_employee(
    employee_id: uuid.UUID,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    del current_user
    employee = await service.get_by_id(employee_id)
    return APIResponse.ok(EmployeeRead.from_employee(employee), message="Employee retrieved successfully")


@router.patch(
    "/{employee_id}",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Update an employee",
    description=(
        "Partial update; omitted fields are left unchanged. A change to the "
        "team, designation, grade, reporting manager, work location or "
        "status writes an employment-history row, exactly as the dedicated "
        "lifecycle endpoints do."
    ),
    responses=_WRITE_ERRORS,
)
async def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    updated = await service.update(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(updated), message="Employee updated successfully")


# ----------------------------------------------------------------------
# Employment history
# ----------------------------------------------------------------------
@router.get(
    "/{employee_id}/history",
    dependencies=[require("employees:view"), require_team_scope()],
    response_model=APIResponse[list[EmploymentHistoryRead]],
    summary="Employment history",
    description=(
        "The employee's placement history, most recent change first. Append-only: "
        "there is no endpoint that edits or removes an entry."
    ),
    responses={**_COMMON_ERRORS, **_NOT_FOUND},
)
async def employment_history(
    employee_id: uuid.UUID,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[list[EmploymentHistoryRead]]:
    del current_user
    rows = await service.history(employee_id)
    return APIResponse.ok(
        [EmploymentHistoryRead.model_validate(row) for row in rows],
        message="Employment history retrieved successfully",
    )


@router.get(
    "/{employee_id}/audit",
    dependencies=[require("employees:view"), require_team_scope()],
    response_model=APIResponse[list[EmployeeAuditEntry]],
    summary="Audit trail",
    description=(
        "Every audited action taken on this employee, most recent first. Distinct "
        "from the employment history: that records what the employment is, this "
        "records what was done to the record and by whom -- including actions that "
        "leave no placement trace, such as revealing the bank details."
    ),
    responses={**_COMMON_ERRORS, **_NOT_FOUND},
)
async def employee_audit_trail(
    employee_id: uuid.UUID,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[list[EmployeeAuditEntry]]:
    del current_user
    rows = await service.audit_trail(employee_id)
    return APIResponse.ok(
        [EmployeeAuditEntry.model_validate(row) for row in rows],
        message="Audit trail retrieved successfully",
    )


# ----------------------------------------------------------------------
# Sensitive details
# ----------------------------------------------------------------------
@router.get(
    "/{employee_id}/sensitive",
    dependencies=[require("employees:view"), require_team_scope()],
    response_model=APIResponse[EmployeeSensitiveReveal],
    summary="Reveal bank and identity details",
    description=(
        "Returns the unmasked bank account and government identifiers, for an edit "
        "form. **Every call is written to the audit trail**, because the reveal is "
        "the moment the masking elsewhere stops protecting anything."
    ),
    responses={**_COMMON_ERRORS, **_NOT_FOUND},
)
async def reveal_sensitive(
    employee_id: uuid.UUID,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeSensitiveReveal]:
    employee = await service.reveal_sensitive(employee_id, actor_id=current_user.id)
    payload = EmployeeSensitiveReveal(
        employee_id=employee.id,
        bank_detail=(
            EmployeeBankReveal.model_validate(employee.bank_detail) if employee.bank_detail else None
        ),
        identification=(
            EmployeeIdentificationReveal.model_validate(employee.identification)
            if employee.identification
            else None
        ),
    )
    return APIResponse.ok(payload, message="Sensitive details retrieved successfully")


@router.put(
    "/{employee_id}/bank",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Set bank details",
    responses=_WRITE_ERRORS,
)
async def set_bank_detail(
    employee_id: uuid.UUID,
    payload: EmployeeBankInput,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.set_bank_detail(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(employee), message="Bank details updated successfully")


@router.put(
    "/{employee_id}/identification",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Set government identifiers",
    responses=_WRITE_ERRORS,
)
async def set_identification(
    employee_id: uuid.UUID,
    payload: EmployeeIdentificationInput,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.set_identification(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(
        EmployeeRead.from_employee(employee), message="Government identifiers updated successfully"
    )


@router.put(
    "/{employee_id}/address",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Set an address",
    description="Creates or replaces the employee's current or permanent address.",
    responses=_WRITE_ERRORS,
)
async def set_address(
    employee_id: uuid.UUID,
    payload: EmployeeAddressInput,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.set_address(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(employee), message="Address updated successfully")


# ----------------------------------------------------------------------
# Lifecycle actions
#
# One endpoint per action rather than a general "change" with a mode: each has
# its own payload, its own guards and its own audit action, and collapsing them
# would make every field optional and every rule conditional.
# ----------------------------------------------------------------------
@router.post(
    "/{employee_id}/confirm",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Confirm an employee",
    description="Ends probation. Refused unless the employee is currently on probation.",
    responses=_WRITE_ERRORS,
)
async def confirm_employee(
    employee_id: uuid.UUID,
    payload: ConfirmEmployeeRequest,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.confirm(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(employee), message="Employee confirmed successfully")


@router.post(
    "/{employee_id}/transfer",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Transfer to another team",
    description=(
        "Moves the employee to a new team. Supply a business unit as well when the "
        "move crosses units, since a team belongs to one."
    ),
    responses=_WRITE_ERRORS,
)
async def transfer_team(
    employee_id: uuid.UUID,
    payload: TransferTeamRequest,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.transfer_team(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(employee), message="Employee transferred successfully")


@router.post(
    "/{employee_id}/designation",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Change designation",
    responses=_WRITE_ERRORS,
)
async def change_designation(
    employee_id: uuid.UUID,
    payload: ChangeDesignationRequest,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.change_designation(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(employee), message="Designation changed successfully")


@router.post(
    "/{employee_id}/manager",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Change reporting manager",
    description=(
        "Refused when the proposed manager reports to this employee, directly or "
        "through a chain, which would close a reporting loop."
    ),
    responses=_WRITE_ERRORS,
)
async def change_manager(
    employee_id: uuid.UUID,
    payload: ChangeManagerRequest,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.change_manager(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(
        EmployeeRead.from_employee(employee), message="Reporting manager changed successfully"
    )


@router.post(
    "/{employee_id}/location",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Change work location",
    responses=_WRITE_ERRORS,
)
async def change_location(
    employee_id: uuid.UUID,
    payload: ChangeLocationRequest,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.change_location(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(employee), message="Work location changed successfully")


@router.post(
    "/{employee_id}/promote",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Promote an employee",
    description=(
        "Records a promotion: a new designation, grade, salary grade or CTC, or "
        "several at once. At least one must change."
    ),
    responses=_WRITE_ERRORS,
)
async def promote_employee(
    employee_id: uuid.UUID,
    payload: PromoteEmployeeRequest,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.promote(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(employee), message="Employee promoted successfully")


@router.post(
    "/{employee_id}/status",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Change employment status",
    responses=_WRITE_ERRORS,
)
async def change_status(
    employee_id: uuid.UUID,
    payload: ChangeStatusRequest,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.change_status(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(
        EmployeeRead.from_employee(employee), message="Employment status changed successfully"
    )


@router.post(
    "/{employee_id}/activate",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Activate an employee",
    responses=_WRITE_ERRORS,
)
async def activate_employee(
    employee_id: uuid.UUID,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.set_active(employee_id, active=True, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(employee), message="Employee activated successfully")


@router.post(
    "/{employee_id}/deactivate",
    dependencies=[require("employees:update"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Deactivate an employee",
    responses=_WRITE_ERRORS,
)
async def deactivate_employee(
    employee_id: uuid.UUID,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.set_active(employee_id, active=False, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(employee), message="Employee deactivated successfully")


@router.post(
    "/{employee_id}/archive",
    dependencies=[require("employees:delete"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Archive an employee",
    description=(
        "Soft deletes the record. Refused while other employees still report to "
        "this one -- archiving a manager would leave their reports pointing at a "
        "hidden record."
    ),
    responses=_WRITE_ERRORS,
)
async def archive_employee(
    employee_id: uuid.UUID,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.archive(employee_id, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(employee), message="Employee archived successfully")


@router.post(
    "/{employee_id}/restore",
    dependencies=[require("employees:delete"), require_team_scope()],
    response_model=APIResponse[EmployeeRead],
    summary="Restore an archived employee",
    responses=_WRITE_ERRORS,
)
async def restore_employee(
    employee_id: uuid.UUID,
    service: EmployeeSvc,
    current_user: CurrentUser,
) -> APIResponse[EmployeeRead]:
    employee = await service.restore(employee_id, actor_id=current_user.id)
    return APIResponse.ok(EmployeeRead.from_employee(employee), message="Employee restored successfully")
