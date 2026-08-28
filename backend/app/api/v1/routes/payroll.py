"""Payroll foundation endpoints.

Three audiences, and the differences between them are the access model.

``me_router`` (**employee**) carries no ``require(...)`` guard, like everything
else under ``/me``: the only compensation in reach is the caller's own,
resolved from the session. **No route on it takes an employee id.**

``router`` (**HR / Admin**) is where every permission is checked, and payroll
inverts the platform's usual scoping default on purpose. Everywhere else a
manager's reporting line narrows ``view``; here the reporting line grants
*nothing* — a manager sees a report's salary only if ``payroll:team_view`` was
ticked for them deliberately, and no seeded role below Administrator holds any
payroll permission at all. ``require_self_or`` supplies the mechanics: your own
record always answers (it is the same data ``/me/payroll`` serves), anybody
else's needs one of the escalating permissions *and* the record inside your
scope — which for a manager without ``employees:view_all`` is exactly their
direct reports.

Configuration reads (structures, components) are open to anybody who can
assign or revise, because a picker that 403s makes those grants unusable;
configuration *writes* need the dedicated manage permissions.

Route order matters as elsewhere: static segments precede the ``/{id}`` forms.

NOTE: no ``from __future__ import annotations`` — FastAPI reads parameter types
from evaluated annotations, and postponed evaluation breaks ``Annotated[...,
Query()]``.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    CurrentEmployee,
    CurrentUser,
    PayrollApprovalSvc,
    PayrollConfigSvc,
    PayrollInputSvc,
    PayrollReviewSvc,
    PayrollRunSvc,
    PayrollSvc,
    PayslipSvc,
    require,
    require_any,
    require_org_wide,
    require_self_or,
    require_team_scope,
)
from app.models.enums import (
    PayrollExceptionSeverity,
    PayrollExceptionStatus,
    PayrollPeriodStatus,
    RecordStatus,
    SalaryStructureStatus,
)
from app.schemas.common import APIErrorResponse, APIResponse, Page
from app.schemas.payroll import (
    ChecklistItemRead,
    ChecklistItemUpdate,
    CompensationAssign,
    CompensationListParams,
    CompensationListRow,
    CompensationRead,
    EmployeeCompensationData,
    EmployeeSettingsData,
    EmployeeSettingsListParams,
    EmployeeSettingsRead,
    EmployeeSettingsUpsert,
    LeaveRuleCreate,
    LeaveRuleRead,
    LeaveRuleUpdate,
    PayrollAdjustmentCancel,
    PayrollAdjustmentCreate,
    PayrollAdjustmentRead,
    PayrollApprovalDecision,
    PayrollApprovalSummary,
    PayrollCalculationResult,
    PayrollChangeDetectionResult,
    PayrollComparisonRow,
    PayrollConfigHistoryRead,
    PayrollConfigRead,
    PayrollConfigUpdate,
    PayrollExceptionResolve,
    PayrollFinalizeRequest,
    PayrollInputDetail,
    PayrollInputListParams,
    PayrollInputPrepareResult,
    PayrollInputRead,
    PayrollInputReview,
    PayrollPeriodCreate,
    PayrollPeriodRead,
    PayrollPeriodUpdate,
    PayrollReconciliation,
    PayrollRecordDetail,
    PayrollRecordListParams,
    PayrollRecordRead,
    PayrollRecordReviewMark,
    PayrollReturnRequest,
    PayrollRunCreate,
    PayrollRunExceptionRead,
    PayrollRunListParams,
    PayrollRunRead,
    PayrollSnapshotRead,
    PayslipDetail,
    PayslipGenerationResult,
    PayslipListParams,
    PayslipRead,
    PeriodExceptionRow,
    PeriodListParams,
    ReviewCommentCreate,
    ReviewCommentRead,
    ReviewReadiness,
    SalaryComponentCreate,
    SalaryComponentRead,
    SalaryComponentUpdate,
    SalaryHistoryRead,
    SalaryRevision,
    SalaryStructureCreate,
    SalaryStructureDetail,
    SalaryStructureUpdate,
    StructureListParams,
)

router = APIRouter(prefix="/payroll", tags=["Payroll"])
me_router = APIRouter(prefix="/me", tags=["Employee Self-Service"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_403_FORBIDDEN: {
        "model": APIErrorResponse,
        "description": "Missing the permission, or the employee is outside your reach.",
    },
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such record."},
    status.HTTP_409_CONFLICT: {
        "model": APIErrorResponse,
        "description": "A workflow rule was violated — an inactive structure, an overlapping "
        "compensation period, or an invalid status transition.",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": APIErrorResponse,
        "description": "Validation failed.",
    },
}

StructureParams = Annotated[StructureListParams, Query()]
CompensationParams = Annotated[CompensationListParams, Query()]
PeriodParams = Annotated[PeriodListParams, Query()]
SettingsParams = Annotated[EmployeeSettingsListParams, Query()]
InputParams = Annotated[PayrollInputListParams, Query()]
RunParams = Annotated[PayrollRunListParams, Query()]
RecordParams = Annotated[PayrollRecordListParams, Query()]
PayslipParams = Annotated[PayslipListParams, Query()]

#: Reading configuration rides on any grant that needs it; writing does not.
_CAN_READ_STRUCTURES = require_any("payroll:structure_manage", "payroll:create", "payroll:update")
_CAN_READ_COMPONENTS = require_any(
    "payroll:component_manage", "payroll:structure_manage", "payroll:create", "payroll:update"
)
_CAN_READ_CONFIG = require_any("payroll:config_view", "payroll:config_manage")
_CAN_READ_PERIODS = require_any("payroll:config_view", "payroll:period_manage")
_CAN_READ_RULES = require_any("payroll:config_view", "payroll:rule_manage")


# ======================================================================
# Employee self-service
# ======================================================================
@me_router.get(
    "/payroll",
    response_model=APIResponse[EmployeeCompensationData],
    summary="My compensation",
    description="The caller's own salary structure, components and every past period. "
    "Read-only: there is no self-service write anywhere in payroll.",
    responses={**_ERRORS},
)
async def my_compensation(
    employee: CurrentEmployee, service: PayrollSvc
) -> APIResponse[EmployeeCompensationData]:
    return APIResponse.ok(await service.my_compensation(employee))


@me_router.get(
    "/payroll/history",
    response_model=APIResponse[list[SalaryHistoryRead]],
    summary="My salary history",
    responses={**_ERRORS},
)
async def my_salary_history(
    employee: CurrentEmployee, service: PayrollSvc
) -> APIResponse[list[SalaryHistoryRead]]:
    return APIResponse.ok(await service.my_salary_history(employee))


# ======================================================================
# Components (before /structures/{id} but static anyway)
# ======================================================================
@router.get(
    "/components",
    dependencies=[_CAN_READ_COMPONENTS],
    response_model=APIResponse[list[SalaryComponentRead]],
    summary="Salary components",
    description="The configurable earning and deduction masters. Never hardcoded in the client.",
    responses={**_ERRORS},
)
async def list_components(
    current_user: CurrentUser,
    service: PayrollSvc,
    include_inactive: Annotated[bool, Query()] = False,
) -> APIResponse[list[SalaryComponentRead]]:
    del current_user
    rows = await service.list_components(include_inactive=include_inactive)
    return APIResponse.ok([SalaryComponentRead.model_validate(row) for row in rows])


@router.post(
    "/components",
    dependencies=[require("payroll:component_manage")],
    response_model=APIResponse[SalaryComponentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a salary component",
    responses={**_ERRORS},
)
async def create_component(
    payload: SalaryComponentCreate, current_user: CurrentUser, service: PayrollSvc
) -> APIResponse[SalaryComponentRead]:
    component = await service.create_component(payload, actor_id=current_user.id)
    return APIResponse.ok(SalaryComponentRead.model_validate(component), message="Component created")


@router.put(
    "/components/{component_id}",
    dependencies=[require("payroll:component_manage")],
    response_model=APIResponse[SalaryComponentRead],
    summary="Update a salary component",
    description="Changes the master only. Values already snapshotted onto employee "
    "compensation records are never touched.",
    responses={**_ERRORS},
)
async def update_component(
    component_id: uuid.UUID,
    payload: SalaryComponentUpdate,
    current_user: CurrentUser,
    service: PayrollSvc,
) -> APIResponse[SalaryComponentRead]:
    component = await service.update_component(component_id, payload, actor_id=current_user.id)
    return APIResponse.ok(SalaryComponentRead.model_validate(component), message="Component updated")


@router.post(
    "/components/{component_id}/status/{new_status}",
    dependencies=[require("payroll:component_manage")],
    response_model=APIResponse[SalaryComponentRead],
    summary="Activate or deactivate a component",
    responses={**_ERRORS},
)
async def set_component_status(
    component_id: uuid.UUID,
    new_status: Literal["active", "inactive"],
    current_user: CurrentUser,
    service: PayrollSvc,
) -> APIResponse[SalaryComponentRead]:
    component = await service.set_component_status(
        component_id, RecordStatus(new_status), actor_id=current_user.id
    )
    return APIResponse.ok(SalaryComponentRead.model_validate(component), message="Status updated")


# ======================================================================
# Structures
# ======================================================================
@router.get(
    "/structures",
    dependencies=[_CAN_READ_STRUCTURES],
    response_model=APIResponse[Page[SalaryStructureDetail]],
    summary="Salary structures",
    responses={**_ERRORS},
)
async def list_structures(
    params: StructureParams, current_user: CurrentUser, service: PayrollSvc
) -> APIResponse[Page[SalaryStructureDetail]]:
    del current_user
    rows, total = await service.list_structures(params)
    return APIResponse.ok(
        Page.create(
            [service.present_structure(row) for row in rows],
            page=params.page,
            page_size=params.page_size,
            total_items=total,
        )
    )


@router.post(
    "/structures",
    dependencies=[require("payroll:structure_manage")],
    response_model=APIResponse[SalaryStructureDetail],
    status_code=status.HTTP_201_CREATED,
    summary="Create a salary structure",
    description="Created as a draft. Activate it before assigning it to anybody.",
    responses={**_ERRORS},
)
async def create_structure(
    payload: SalaryStructureCreate, current_user: CurrentUser, service: PayrollSvc
) -> APIResponse[SalaryStructureDetail]:
    structure = await service.create_structure(payload, actor_id=current_user.id)
    return APIResponse.ok(service.present_structure(structure), message="Structure created")


@router.get(
    "/structures/{structure_id}",
    dependencies=[_CAN_READ_STRUCTURES],
    response_model=APIResponse[SalaryStructureDetail],
    summary="One salary structure, with its components",
    responses={**_ERRORS},
)
async def get_structure(
    structure_id: uuid.UUID, current_user: CurrentUser, service: PayrollSvc
) -> APIResponse[SalaryStructureDetail]:
    del current_user
    structure = await service.get_structure(structure_id)
    return APIResponse.ok(service.present_structure(structure))


@router.put(
    "/structures/{structure_id}",
    dependencies=[require("payroll:structure_manage")],
    response_model=APIResponse[SalaryStructureDetail],
    summary="Update a salary structure",
    description="Changes the template only. Compensation already assigned from it is a "
    "snapshot and is never touched.",
    responses={**_ERRORS},
)
async def update_structure(
    structure_id: uuid.UUID,
    payload: SalaryStructureUpdate,
    current_user: CurrentUser,
    service: PayrollSvc,
) -> APIResponse[SalaryStructureDetail]:
    structure = await service.update_structure(structure_id, payload, actor_id=current_user.id)
    return APIResponse.ok(service.present_structure(structure), message="Structure updated")


@router.post(
    "/structures/{structure_id}/status/{new_status}",
    dependencies=[require("payroll:structure_manage")],
    response_model=APIResponse[SalaryStructureDetail],
    summary="Activate or deactivate a structure",
    description="draft -> active, active -> inactive, inactive -> active. Nothing returns to draft.",
    responses={**_ERRORS},
)
async def set_structure_status(
    structure_id: uuid.UUID,
    new_status: Literal["active", "inactive"],
    current_user: CurrentUser,
    service: PayrollSvc,
) -> APIResponse[SalaryStructureDetail]:
    structure = await service.set_structure_status(
        structure_id, SalaryStructureStatus(new_status), actor_id=current_user.id
    )
    return APIResponse.ok(service.present_structure(structure), message="Status updated")


# ======================================================================
# Employee compensation
# ======================================================================
@router.get(
    "/compensation",
    dependencies=[require_org_wide("payroll:view")],
    response_model=APIResponse[Page[CompensationListRow]],
    summary="The payroll register",
    description="Every employee's current compensation. Organization-wide by definition, so it "
    "pairs payroll:view with employees:view_all.",
    responses={**_ERRORS},
)
async def list_compensation(
    params: CompensationParams, current_user: CurrentUser, service: PayrollSvc
) -> APIResponse[Page[CompensationListRow]]:
    del current_user
    rows, total = await service.list_current_compensation(params)
    return APIResponse.ok(Page.create(rows, page=params.page, page_size=params.page_size, total_items=total))


@router.get(
    "/employees/{employee_id}/compensation",
    dependencies=[require_self_or("payroll:view", "payroll:team_view")],
    response_model=APIResponse[EmployeeCompensationData],
    summary="One employee's compensation",
    description="Your own record always answers. Anybody else's needs payroll:view (scoped like "
    "every other read) or payroll:team_view (a manager's explicit grant, reaching their direct "
    "reports and stopping there).",
    responses={**_ERRORS},
)
async def employee_compensation(
    employee_id: uuid.UUID, current_user: CurrentUser, service: PayrollSvc
) -> APIResponse[EmployeeCompensationData]:
    del current_user
    return APIResponse.ok(await service.employee_compensation(employee_id))


@router.post(
    "/employees/{employee_id}/compensation",
    dependencies=[require("payroll:create"), require_team_scope()],
    response_model=APIResponse[CompensationRead],
    status_code=status.HTTP_201_CREATED,
    summary="Assign compensation",
    description="Refused when the structure is not active, a required component is missing, or "
    "an active compensation record already covers the period.",
    responses={**_ERRORS},
)
async def assign_compensation(
    employee_id: uuid.UUID,
    payload: CompensationAssign,
    current_user: CurrentUser,
    service: PayrollSvc,
) -> APIResponse[CompensationRead]:
    record = await service.assign_compensation(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(record, message="Compensation assigned")


@router.post(
    "/employees/{employee_id}/revisions",
    dependencies=[require("payroll:update"), require_team_scope()],
    response_model=APIResponse[CompensationRead],
    status_code=status.HTTP_201_CREATED,
    summary="Revise a salary",
    description="Ends the current record the day before the revision takes effect and opens a "
    "new one. Both survive; salary_history records the change, its reason and its author.",
    responses={**_ERRORS},
)
async def revise_salary(
    employee_id: uuid.UUID,
    payload: SalaryRevision,
    current_user: CurrentUser,
    service: PayrollSvc,
) -> APIResponse[CompensationRead]:
    record = await service.revise_salary(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(record, message="Salary revised")


@router.get(
    "/employees/{employee_id}/history",
    dependencies=[require_self_or("payroll:history_view", "payroll:team_view")],
    response_model=APIResponse[list[SalaryHistoryRead]],
    summary="One employee's salary history",
    description="Append-only. There is no endpoint anywhere that edits or deletes an entry.",
    responses={**_ERRORS},
)
async def employee_salary_history(
    employee_id: uuid.UUID, current_user: CurrentUser, service: PayrollSvc
) -> APIResponse[list[SalaryHistoryRead]]:
    del current_user
    return APIResponse.ok(await service.salary_history(employee_id))


# ======================================================================
# Phase 2 — payroll configuration
#
# All of it is Administration by default: no seeded role below Administrator
# holds any of the six configuration permissions, and there is deliberately
# no `/me` route in this section — an employee has no business in the
# rulebook, and the guard model makes that a property rather than a policy.
# ======================================================================
@router.get(
    "/config",
    dependencies=[_CAN_READ_CONFIG],
    response_model=APIResponse[PayrollConfigRead],
    summary="The payroll configuration",
    description="One configuration, always. Nothing here is read by a calculation yet; this is "
    "the rulebook a later phase will run against.",
    responses={**_ERRORS},
)
async def get_payroll_config(
    current_user: CurrentUser, service: PayrollConfigSvc
) -> APIResponse[PayrollConfigRead]:
    del current_user
    return APIResponse.ok(await service.get_config())


@router.put(
    "/config",
    dependencies=[require("payroll:config_manage")],
    response_model=APIResponse[PayrollConfigRead],
    summary="Update the payroll configuration",
    description="Requires a reason and an effective date. Every changed field writes a history "
    "row — previous value, new value, who, why — before the value moves.",
    responses={**_ERRORS},
)
async def update_payroll_config(
    payload: PayrollConfigUpdate, current_user: CurrentUser, service: PayrollConfigSvc
) -> APIResponse[PayrollConfigRead]:
    updated = await service.update_config(payload, actor_id=current_user.id)
    return APIResponse.ok(updated, message="Configuration updated")


@router.get(
    "/config/history",
    dependencies=[_CAN_READ_CONFIG],
    response_model=APIResponse[list[PayrollConfigHistoryRead]],
    summary="Configuration change history",
    description="Append-only. There is no endpoint anywhere that edits or deletes an entry.",
    responses={**_ERRORS},
)
async def payroll_config_history(
    current_user: CurrentUser, service: PayrollConfigSvc
) -> APIResponse[list[PayrollConfigHistoryRead]]:
    del current_user
    return APIResponse.ok(await service.config_history_entries())


# ======================================================================
# Phase 2 — payroll periods
# ======================================================================
@router.get(
    "/periods",
    dependencies=[_CAN_READ_PERIODS],
    response_model=APIResponse[Page[PayrollPeriodRead]],
    summary="Payroll periods",
    responses={**_ERRORS},
)
async def list_payroll_periods(
    params: PeriodParams, current_user: CurrentUser, service: PayrollConfigSvc
) -> APIResponse[Page[PayrollPeriodRead]]:
    del current_user
    rows, total = await service.list_periods(params)
    return APIResponse.ok(Page.create(rows, page=params.page, page_size=params.page_size, total_items=total))


@router.post(
    "/periods",
    dependencies=[require("payroll:period_manage")],
    response_model=APIResponse[PayrollPeriodRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a payroll period",
    description="Refused when the dates overlap any non-cancelled period.",
    responses={**_ERRORS},
)
async def create_payroll_period(
    payload: PayrollPeriodCreate, current_user: CurrentUser, service: PayrollConfigSvc
) -> APIResponse[PayrollPeriodRead]:
    period = await service.create_period(payload, actor_id=current_user.id)
    return APIResponse.ok(PayrollPeriodRead.model_validate(period), message="Period created")


@router.get(
    "/periods/{period_id}",
    dependencies=[_CAN_READ_PERIODS],
    response_model=APIResponse[PayrollPeriodRead],
    summary="One payroll period",
    responses={**_ERRORS},
)
async def get_payroll_period(
    period_id: uuid.UUID, current_user: CurrentUser, service: PayrollConfigSvc
) -> APIResponse[PayrollPeriodRead]:
    del current_user
    period = await service.get_period(period_id)
    return APIResponse.ok(PayrollPeriodRead.model_validate(period))


@router.put(
    "/periods/{period_id}",
    dependencies=[require("payroll:period_manage")],
    response_model=APIResponse[PayrollPeriodRead],
    summary="Edit a payroll period",
    description="Dates are editable only while the period is open.",
    responses={**_ERRORS},
)
async def update_payroll_period(
    period_id: uuid.UUID,
    payload: PayrollPeriodUpdate,
    current_user: CurrentUser,
    service: PayrollConfigSvc,
) -> APIResponse[PayrollPeriodRead]:
    period = await service.update_period(period_id, payload, actor_id=current_user.id)
    return APIResponse.ok(PayrollPeriodRead.model_validate(period), message="Period updated")


@router.post(
    "/periods/{period_id}/status/{new_status}",
    dependencies=[require("payroll:period_manage")],
    response_model=APIResponse[PayrollPeriodRead],
    summary="Move a period along its workflow",
    description="open -> processing -> under_review -> approved -> finalized, each step able to "
    "fall back one, and cancellation available until finalized. Finalized and cancelled are "
    "terminal. Nothing runs a payroll here — this phase only manages the period itself.",
    responses={**_ERRORS},
)
async def set_payroll_period_status(
    period_id: uuid.UUID,
    new_status: PayrollPeriodStatus,
    current_user: CurrentUser,
    service: PayrollConfigSvc,
) -> APIResponse[PayrollPeriodRead]:
    period = await service.set_period_status(period_id, new_status, actor_id=current_user.id)
    return APIResponse.ok(PayrollPeriodRead.model_validate(period), message="Status updated")


# ======================================================================
# Phase 2 — leave rules
# ======================================================================
@router.get(
    "/rules/leave",
    dependencies=[_CAN_READ_RULES],
    response_model=APIResponse[list[LeaveRuleRead]],
    summary="Payroll leave rules",
    description="How each existing leave type behaves in payroll. Leave types themselves belong "
    "to the workforce module; this is only their payroll treatment.",
    responses={**_ERRORS},
)
async def list_leave_rules(
    current_user: CurrentUser,
    service: PayrollConfigSvc,
    include_inactive: Annotated[bool, Query()] = False,
) -> APIResponse[list[LeaveRuleRead]]:
    del current_user
    return APIResponse.ok(await service.list_leave_rules(include_inactive=include_inactive))


@router.post(
    "/rules/leave",
    dependencies=[require("payroll:rule_manage")],
    response_model=APIResponse[LeaveRuleRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a leave rule",
    description="One rule per leave type. An unpaid rule must name its deduction basis.",
    responses={**_ERRORS},
)
async def create_leave_rule(
    payload: LeaveRuleCreate, current_user: CurrentUser, service: PayrollConfigSvc
) -> APIResponse[LeaveRuleRead]:
    rule = await service.create_leave_rule(payload, actor_id=current_user.id)
    return APIResponse.ok(rule, message="Rule created")


@router.put(
    "/rules/leave/{rule_id}",
    dependencies=[require("payroll:rule_manage")],
    response_model=APIResponse[LeaveRuleRead],
    summary="Update a leave rule",
    responses={**_ERRORS},
)
async def update_leave_rule(
    rule_id: uuid.UUID,
    payload: LeaveRuleUpdate,
    current_user: CurrentUser,
    service: PayrollConfigSvc,
) -> APIResponse[LeaveRuleRead]:
    rule = await service.update_leave_rule(rule_id, payload, actor_id=current_user.id)
    return APIResponse.ok(rule, message="Rule updated")


@router.post(
    "/rules/leave/{rule_id}/status/{new_status}",
    dependencies=[require("payroll:rule_manage")],
    response_model=APIResponse[LeaveRuleRead],
    summary="Activate or deactivate a leave rule",
    responses={**_ERRORS},
)
async def set_leave_rule_status(
    rule_id: uuid.UUID,
    new_status: Literal["active", "inactive"],
    current_user: CurrentUser,
    service: PayrollConfigSvc,
) -> APIResponse[LeaveRuleRead]:
    rule = await service.set_leave_rule_status(rule_id, RecordStatus(new_status), actor_id=current_user.id)
    return APIResponse.ok(rule, message="Status updated")


# ======================================================================
# Phase 2 — employee payroll settings
# ======================================================================
@router.get(
    "/employee-settings",
    dependencies=[require_org_wide("payroll:employee_settings_view")],
    response_model=APIResponse[Page[EmployeeSettingsRead]],
    summary="Employee payroll settings",
    description="Only employees somebody configured appear here: absence of a row means "
    "'not configured', never 'eligible by default'. Carries no salary figures.",
    responses={**_ERRORS},
)
async def list_employee_settings(
    params: SettingsParams, current_user: CurrentUser, service: PayrollConfigSvc
) -> APIResponse[Page[EmployeeSettingsRead]]:
    del current_user
    rows, total = await service.list_employee_settings(params)
    return APIResponse.ok(Page.create(rows, page=params.page, page_size=params.page_size, total_items=total))


@router.get(
    "/employees/{employee_id}/settings",
    dependencies=[require("payroll:employee_settings_view"), require_team_scope()],
    response_model=APIResponse[EmployeeSettingsData],
    summary="One employee's payroll settings",
    responses={**_ERRORS},
)
async def employee_payroll_settings(
    employee_id: uuid.UUID, current_user: CurrentUser, service: PayrollConfigSvc
) -> APIResponse[EmployeeSettingsData]:
    del current_user
    return APIResponse.ok(await service.employee_settings_data(employee_id))


@router.put(
    "/employees/{employee_id}/settings",
    dependencies=[require("payroll:employee_settings_update"), require_team_scope()],
    response_model=APIResponse[EmployeeSettingsData],
    summary="Set one employee's payroll settings",
    description="Creates the row when none exists, updates it otherwise. Every change is audited "
    "with the previous and new values.",
    responses={**_ERRORS},
)
async def upsert_employee_payroll_settings(
    employee_id: uuid.UUID,
    payload: EmployeeSettingsUpsert,
    current_user: CurrentUser,
    service: PayrollConfigSvc,
) -> APIResponse[EmployeeSettingsData]:
    data = await service.upsert_employee_settings(employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(data, message="Settings saved")


# ======================================================================
# Phase 3 — payroll inputs
#
# Static segments before ``/{employee_id}``, as everywhere. The detail route
# uses ``require_self_or``: your own input always answers (it is your own
# attendance and leave, restated), anybody else's needs ``inputs_view`` or a
# manager's explicit ``team_view`` — and the reporting line grants nothing
# by itself, exactly as with compensation.
# ======================================================================
@me_router.get(
    "/payroll/inputs",
    response_model=APIResponse[list[PayrollInputRead]],
    summary="My payroll inputs",
    description="The caller's own prepared inputs, every period. A restatement of their own "
    "attendance, leave and overtime — no salary figure appears anywhere in an input.",
    responses={**_ERRORS},
)
async def my_payroll_inputs(
    employee: CurrentEmployee, service: PayrollInputSvc
) -> APIResponse[list[PayrollInputRead]]:
    return APIResponse.ok(await service.my_inputs(employee))


@router.post(
    "/periods/{period_id}/inputs/generate",
    dependencies=[require("payroll:inputs_prepare")],
    response_model=APIResponse[PayrollInputPrepareResult],
    summary="Prepare payroll inputs for a period",
    description="Reads approved attendance, leave and overtime for every in-scope employee and "
    "snapshots the result. Re-running refreshes in place. Nothing in any source module is "
    "modified, and nothing is calculated as money.",
    responses={**_ERRORS},
)
async def generate_payroll_inputs(
    period_id: uuid.UUID, current_user: CurrentUser, service: PayrollInputSvc
) -> APIResponse[PayrollInputPrepareResult]:
    result = await service.prepare(period_id, actor_id=current_user.id)
    return APIResponse.ok(result, message="Payroll inputs prepared")


@router.post(
    "/periods/{period_id}/inputs/detect-changes",
    dependencies=[require("payroll:inputs_prepare")],
    response_model=APIResponse[PayrollChangeDetectionResult],
    summary="Detect source data changed after the snapshot",
    description="Recomputes each input's source fingerprint. Where attendance, leave or "
    "corrections moved since preparation, the input is flagged Requires Review rather than "
    "silently feeding stale numbers to a later phase.",
    responses={**_ERRORS},
)
async def detect_payroll_input_changes(
    period_id: uuid.UUID, current_user: CurrentUser, service: PayrollInputSvc
) -> APIResponse[PayrollChangeDetectionResult]:
    result = await service.detect_changes(period_id, actor_id=current_user.id)
    return APIResponse.ok(result)


@router.get(
    "/periods/{period_id}/inputs",
    dependencies=[require_org_wide("payroll:inputs_view")],
    response_model=APIResponse[Page[PayrollInputRead]],
    summary="Payroll inputs for a period",
    responses={**_ERRORS},
)
async def list_payroll_inputs(
    period_id: uuid.UUID,
    params: InputParams,
    current_user: CurrentUser,
    service: PayrollInputSvc,
) -> APIResponse[Page[PayrollInputRead]]:
    del current_user
    rows, total = await service.list_inputs(period_id, params)
    return APIResponse.ok(Page.create(rows, page=params.page, page_size=params.page_size, total_items=total))


@router.get(
    "/periods/{period_id}/exceptions",
    dependencies=[require_org_wide("payroll:inputs_view")],
    response_model=APIResponse[list[PeriodExceptionRow]],
    summary="Every payroll-impacting exception in a period",
    responses={**_ERRORS},
)
async def list_period_exceptions(
    period_id: uuid.UUID, current_user: CurrentUser, service: PayrollInputSvc
) -> APIResponse[list[PeriodExceptionRow]]:
    del current_user
    return APIResponse.ok(await service.period_exceptions(period_id))


@router.get(
    "/periods/{period_id}/inputs/{employee_id}",
    dependencies=[require_self_or("payroll:inputs_view", "payroll:team_view")],
    response_model=APIResponse[PayrollInputDetail],
    summary="One employee's payroll input, with exceptions and sources",
    description="Your own record always answers. Anybody else's needs payroll:inputs_view or a "
    "manager's explicit payroll:team_view, which reaches direct reports and stops there.",
    responses={**_ERRORS},
)
async def payroll_input_detail(
    period_id: uuid.UUID,
    employee_id: uuid.UUID,
    current_user: CurrentUser,
    service: PayrollInputSvc,
) -> APIResponse[PayrollInputDetail]:
    del current_user
    return APIResponse.ok(await service.input_detail(period_id, employee_id))


@router.post(
    "/inputs/{input_id}/review",
    dependencies=[require("payroll:inputs_review")],
    response_model=APIResponse[PayrollInputRead],
    summary="Mark a flagged input reviewed",
    description="Moves Requires Review back to Ready, recording who signed it off and why. The "
    "underlying attendance and leave records are never touched.",
    responses={**_ERRORS},
)
async def review_payroll_input(
    input_id: uuid.UUID,
    payload: PayrollInputReview,
    current_user: CurrentUser,
    service: PayrollInputSvc,
) -> APIResponse[PayrollInputRead]:
    result = await service.review(input_id, payload, actor_id=current_user.id)
    return APIResponse.ok(result, message="Input reviewed")


# ======================================================================
# Phase 4 — payroll runs and the calculation engine
#
# Run-wide reads pair runs_view with employees:view_all: a run's summary is
# every salary at once. The per-employee record uses require_self_or, with
# the same inversion as everywhere in payroll — your own record answers,
# anybody else's needs record_view or a manager's explicit team_view.
# ======================================================================
@me_router.get(
    "/payroll/records",
    response_model=APIResponse[list[PayrollRecordDetail]],
    summary="My calculated payroll",
    description="The caller's own calculated records, full line items included. Only records "
    "whose calculation completed appear; a flagged run's numbers are nobody's payslip yet.",
    responses={**_ERRORS},
)
async def my_payroll_records(
    employee: CurrentEmployee, service: PayrollRunSvc
) -> APIResponse[list[PayrollRecordDetail]]:
    return APIResponse.ok(await service.my_records(employee))


@router.get(
    "/runs",
    dependencies=[require_org_wide("payroll:runs_view")],
    response_model=APIResponse[Page[PayrollRunRead]],
    summary="Payroll runs",
    responses={**_ERRORS},
)
async def list_payroll_runs(
    params: RunParams, current_user: CurrentUser, service: PayrollRunSvc
) -> APIResponse[Page[PayrollRunRead]]:
    del current_user
    rows, total = await service.list_runs(params)
    return APIResponse.ok(Page.create(rows, page=params.page, page_size=params.page_size, total_items=total))


@router.post(
    "/runs",
    dependencies=[require("payroll:run_create")],
    response_model=APIResponse[PayrollRunRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a payroll run",
    description="One run per period. The run is born a draft with no numbers; calculation is a "
    "separate, separately-permissioned act.",
    responses={**_ERRORS},
)
async def create_payroll_run(
    payload: PayrollRunCreate, current_user: CurrentUser, service: PayrollRunSvc
) -> APIResponse[PayrollRunRead]:
    run = await service.create_run(payload, actor_id=current_user.id)
    return APIResponse.ok(run, message="Payroll run created")


@router.get(
    "/runs/{run_id}",
    dependencies=[require_org_wide("payroll:runs_view")],
    response_model=APIResponse[PayrollRunRead],
    summary="One payroll run's summary",
    responses={**_ERRORS},
)
async def get_payroll_run(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayrollRunSvc
) -> APIResponse[PayrollRunRead]:
    del current_user
    return APIResponse.ok(await service.get_run(run_id))


@router.post(
    "/runs/{run_id}/calculate",
    dependencies=[require("payroll:calculate")],
    response_model=APIResponse[PayrollCalculationResult],
    summary="Calculate a payroll run",
    description="Consumes the period's prepared inputs and produces one record per employee, "
    "each a full line-item breakdown. Refused when the run already has records — recalculating "
    "is a separate grant — and when the inputs are missing or flagged the affected employees "
    "become Requires Review rather than a guess.",
    responses={**_ERRORS},
)
async def calculate_payroll_run(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayrollRunSvc
) -> APIResponse[PayrollCalculationResult]:
    result = await service.calculate(run_id, actor_id=current_user.id, recalculation=False)
    return APIResponse.ok(result, message="Payroll calculated")


@router.post(
    "/runs/{run_id}/recalculate",
    dependencies=[require("payroll:recalculate")],
    response_model=APIResponse[PayrollCalculationResult],
    summary="Recalculate a payroll run",
    description="Replaces the run's records whole — never accumulates. Allowed while the run is "
    "draft, requires review or calculated; the approval phase will close that door.",
    responses={**_ERRORS},
)
async def recalculate_payroll_run(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayrollRunSvc
) -> APIResponse[PayrollCalculationResult]:
    result = await service.calculate(run_id, actor_id=current_user.id, recalculation=True)
    return APIResponse.ok(result, message="Payroll recalculated")


@router.get(
    "/runs/{run_id}/records",
    dependencies=[require_org_wide("payroll:runs_view")],
    response_model=APIResponse[Page[PayrollRecordRead]],
    summary="A run's per-employee records",
    responses={**_ERRORS},
)
async def list_payroll_records(
    run_id: uuid.UUID,
    params: RecordParams,
    current_user: CurrentUser,
    service: PayrollRunSvc,
) -> APIResponse[Page[PayrollRecordRead]]:
    del current_user
    rows, total = await service.list_records(run_id, params)
    return APIResponse.ok(Page.create(rows, page=params.page, page_size=params.page_size, total_items=total))


@router.get(
    "/runs/{run_id}/employees/{employee_id}",
    dependencies=[require_self_or("payroll:record_view", "payroll:team_view")],
    response_model=APIResponse[PayrollRecordDetail],
    summary="One employee's calculated payroll, with line items",
    description="Your own record always answers. Anybody else's needs payroll:record_view or a "
    "manager's explicit payroll:team_view, reaching direct reports and stopping there.",
    responses={**_ERRORS},
)
async def payroll_record_detail(
    run_id: uuid.UUID,
    employee_id: uuid.UUID,
    current_user: CurrentUser,
    service: PayrollRunSvc,
) -> APIResponse[PayrollRecordDetail]:
    del current_user
    return APIResponse.ok(await service.record_detail(run_id, employee_id))


# ======================================================================
# Phase 5 — payroll review and adjustments
#
# Reading the review surface shows every salary in the run at once, so all
# reads pair review_view with employees:view_all. The write grants are
# deliberately separate acts: resolving an exception, creating an adjustment,
# cancelling one, and signing off the review are each their own permission —
# and none of them arrives automatically with an HR or manager role.
# ======================================================================
@router.get(
    "/runs/{run_id}/exceptions",
    dependencies=[require_org_wide("payroll:review_view")],
    response_model=APIResponse[list[PayrollRunExceptionRead]],
    summary="A run's review exceptions, worst first",
    responses={**_ERRORS},
)
async def list_run_exceptions(
    run_id: uuid.UUID,
    current_user: CurrentUser,
    service: PayrollReviewSvc,
    status_filter: Annotated[PayrollExceptionStatus | None, Query(alias="status")] = None,
    severity: Annotated[PayrollExceptionSeverity | None, Query()] = None,
) -> APIResponse[list[PayrollRunExceptionRead]]:
    del current_user
    return APIResponse.ok(await service.list_exceptions(run_id, status=status_filter, severity=severity))


@router.post(
    "/runs/{run_id}/exceptions/{exception_id}/resolve",
    dependencies=[require("payroll:exception_resolve")],
    response_model=APIResponse[PayrollRunExceptionRead],
    summary="Resolve a review exception",
    description="Records who resolved it, when, and how — the exception is never deleted. "
    "Resolving explains the issue away; it does not touch attendance, leave or the numbers.",
    responses={**_ERRORS},
)
async def resolve_run_exception(
    run_id: uuid.UUID,
    exception_id: uuid.UUID,
    payload: PayrollExceptionResolve,
    current_user: CurrentUser,
    service: PayrollReviewSvc,
) -> APIResponse[PayrollRunExceptionRead]:
    row = await service.resolve_exception(run_id, exception_id, payload, actor_id=current_user.id)
    return APIResponse.ok(row, message="Exception resolved")


@router.get(
    "/runs/{run_id}/adjustments",
    dependencies=[require_org_wide("payroll:review_view")],
    response_model=APIResponse[list[PayrollAdjustmentRead]],
    summary="A run's adjustments, cancelled ones included",
    responses={**_ERRORS},
)
async def list_run_adjustments(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayrollReviewSvc
) -> APIResponse[list[PayrollAdjustmentRead]]:
    del current_user
    return APIResponse.ok(await service.list_adjustments(run_id))


@router.post(
    "/runs/{run_id}/employees/{employee_id}/adjustments",
    dependencies=[require("payroll:adjustment_create"), require_team_scope()],
    response_model=APIResponse[PayrollAdjustmentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add a manual adjustment",
    description="Additive only: a positive amount with a mandatory reason, layered on top of the "
    "calculation. The original calculated amounts are never edited — final pay is derived as "
    "original plus adjustments, and the record keeps both.",
    responses={**_ERRORS},
)
async def create_payroll_adjustment(
    run_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: PayrollAdjustmentCreate,
    current_user: CurrentUser,
    service: PayrollReviewSvc,
) -> APIResponse[PayrollAdjustmentRead]:
    row = await service.create_adjustment(run_id, employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(row, message="Adjustment added")


@router.post(
    "/runs/{run_id}/adjustments/{adjustment_id}/cancel",
    dependencies=[require("payroll:adjustment_update")],
    response_model=APIResponse[PayrollAdjustmentRead],
    summary="Cancel an adjustment",
    description="Marks the adjustment cancelled — with its reason — rather than deleting it, and "
    "backs its amount out of the employee's final pay.",
    responses={**_ERRORS},
)
async def cancel_payroll_adjustment(
    run_id: uuid.UUID,
    adjustment_id: uuid.UUID,
    payload: PayrollAdjustmentCancel,
    current_user: CurrentUser,
    service: PayrollReviewSvc,
) -> APIResponse[PayrollAdjustmentRead]:
    row = await service.cancel_adjustment(run_id, adjustment_id, payload, actor_id=current_user.id)
    return APIResponse.ok(row, message="Adjustment cancelled")


@router.post(
    "/runs/{run_id}/employees/{employee_id}/review-mark",
    dependencies=[require("payroll:review_complete"), require_team_scope()],
    response_model=APIResponse[None],
    summary="Mark a record reviewed or adjustment-required",
    description="A reviewer's judgement on one record. Only calculated records can be marked; a "
    "record the engine flagged stays Requires Review until its cause is fixed and recalculated.",
    responses={**_ERRORS},
)
async def mark_payroll_record(
    run_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: PayrollRecordReviewMark,
    current_user: CurrentUser,
    service: PayrollReviewSvc,
) -> APIResponse[None]:
    await service.mark_record(run_id, employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(None, message="Record marked")


@router.get(
    "/runs/{run_id}/checklist",
    dependencies=[require_org_wide("payroll:review_view")],
    response_model=APIResponse[list[ChecklistItemRead]],
    summary="The run's review checklist",
    responses={**_ERRORS},
)
async def get_review_checklist(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayrollReviewSvc
) -> APIResponse[list[ChecklistItemRead]]:
    del current_user
    return APIResponse.ok(await service.get_checklist(run_id))


@router.patch(
    "/runs/{run_id}/checklist/{item_key}",
    dependencies=[require("payroll:review_complete")],
    response_model=APIResponse[list[ChecklistItemRead]],
    summary="Tick or untick a checklist item",
    responses={**_ERRORS},
)
async def update_review_checklist(
    run_id: uuid.UUID,
    item_key: str,
    payload: ChecklistItemUpdate,
    current_user: CurrentUser,
    service: PayrollReviewSvc,
) -> APIResponse[list[ChecklistItemRead]]:
    rows = await service.update_checklist(run_id, item_key, payload, actor_id=current_user.id)
    return APIResponse.ok(rows, message="Checklist updated")


@router.get(
    "/runs/{run_id}/review-readiness",
    dependencies=[require_org_wide("payroll:review_view")],
    response_model=APIResponse[ReviewReadiness],
    summary="Whether the review can be completed, and why not",
    responses={**_ERRORS},
)
async def review_readiness(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayrollReviewSvc
) -> APIResponse[ReviewReadiness]:
    del current_user
    return APIResponse.ok(await service.readiness(run_id))


@router.post(
    "/runs/{run_id}/complete-review",
    dependencies=[require("payroll:review_complete")],
    response_model=APIResponse[ReviewReadiness],
    summary="Complete the run's review",
    description="Gated, not granted: every checklist item complete, zero open critical "
    "exceptions, and no record still requiring review or adjustment. Passing the gate promotes "
    "the run to Review Complete and its clean records to Ready for Approval.",
    responses={**_ERRORS},
)
async def complete_payroll_review(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayrollReviewSvc
) -> APIResponse[ReviewReadiness]:
    result = await service.complete_review(run_id, actor_id=current_user.id)
    return APIResponse.ok(result, message="Review completed")


@router.get(
    "/runs/{run_id}/comments",
    dependencies=[require_org_wide("payroll:review_view")],
    response_model=APIResponse[list[ReviewCommentRead]],
    summary="The run's review comments, oldest first",
    responses={**_ERRORS},
)
async def list_review_comments(
    run_id: uuid.UUID,
    current_user: CurrentUser,
    service: PayrollReviewSvc,
    employee_id: Annotated[uuid.UUID | None, Query()] = None,
) -> APIResponse[list[ReviewCommentRead]]:
    del current_user
    return APIResponse.ok(await service.list_comments(run_id, employee_id=employee_id))


@router.post(
    "/runs/{run_id}/comments",
    dependencies=[require_org_wide("payroll:review_view")],
    response_model=APIResponse[ReviewCommentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add a review comment",
    description="Append-only: there is no edit or delete, because a review conversation whose "
    "past can be rewritten is not a record of the review.",
    responses={**_ERRORS},
)
async def add_review_comment(
    run_id: uuid.UUID,
    payload: ReviewCommentCreate,
    current_user: CurrentUser,
    service: PayrollReviewSvc,
) -> APIResponse[ReviewCommentRead]:
    row = await service.add_comment(run_id, payload, actor_id=current_user.id)
    return APIResponse.ok(row, message="Comment added")


@router.get(
    "/runs/{run_id}/reconciliation",
    dependencies=[require_org_wide("payroll:review_view")],
    response_model=APIResponse[PayrollReconciliation],
    summary="Original vs adjusted vs final totals",
    responses={**_ERRORS},
)
async def payroll_reconciliation(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayrollReviewSvc
) -> APIResponse[PayrollReconciliation]:
    del current_user
    return APIResponse.ok(await service.reconciliation(run_id))


@router.get(
    "/runs/{run_id}/comparison",
    dependencies=[require_org_wide("payroll:review_view")],
    response_model=APIResponse[list[PayrollComparisonRow]],
    summary="This run against the previous period, notable moves first",
    description="Employees whose net moved beyond the review threshold — or who are new to "
    "payroll — are highlighted for a human to look at. Nothing is rejected automatically.",
    responses={**_ERRORS},
)
async def payroll_comparison(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayrollReviewSvc
) -> APIResponse[list[PayrollComparisonRow]]:
    del current_user
    return APIResponse.ok(await service.comparison(run_id))


# ======================================================================
# Phase 6 — approval and finalization
#
# There is no "set status" endpoint anywhere in payroll. Submit, approve,
# return and finalize are the only doors between states, each behind its
# own permission and each re-validating the run's state and the approval
# gates server-side. Reads pair their permission with employees:view_all,
# like every other run-wide surface.
# ======================================================================
@router.get(
    "/approval",
    dependencies=[require_org_wide("payroll:approval_view")],
    response_model=APIResponse[Page[PayrollRunRead]],
    summary="The approval queue",
    description="Runs submitted for approval, with their totals, exceptions and adjustments — "
    "everything an approver weighs before deciding.",
    responses={**_ERRORS},
)
async def payroll_approval_queue(
    params: RunParams, current_user: CurrentUser, service: PayrollApprovalSvc
) -> APIResponse[Page[PayrollRunRead]]:
    del current_user
    rows, total = await service.queue(params)
    return APIResponse.ok(Page.create(rows, page=params.page, page_size=params.page_size, total_items=total))


@router.get(
    "/history",
    dependencies=[require_org_wide("payroll:finalized_view")],
    response_model=APIResponse[Page[PayrollRunRead]],
    summary="Finalized payroll history",
    description="The read-only record of what was paid, run by run.",
    responses={**_ERRORS},
)
async def payroll_history(
    params: RunParams, current_user: CurrentUser, service: PayrollApprovalSvc
) -> APIResponse[Page[PayrollRunRead]]:
    del current_user
    rows, total = await service.history(params)
    return APIResponse.ok(Page.create(rows, page=params.page, page_size=params.page_size, total_items=total))


@router.get(
    "/runs/{run_id}/approval-summary",
    dependencies=[require_org_wide("payroll:approval_view")],
    response_model=APIResponse[PayrollApprovalSummary],
    summary="One run's approval summary",
    description="Totals, employee and review summaries, the full approval trail — and, verbatim, "
    "every reason the run cannot be approved yet.",
    responses={**_ERRORS},
)
async def payroll_approval_summary(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayrollApprovalSvc
) -> APIResponse[PayrollApprovalSummary]:
    del current_user
    return APIResponse.ok(await service.summary(run_id))


@router.post(
    "/runs/{run_id}/submit-approval",
    dependencies=[require("payroll:review_complete")],
    response_model=APIResponse[PayrollRunRead],
    summary="Submit a run for approval",
    description="Only a run whose review is complete can be submitted, and the approval gates are "
    "checked again at submission. From here the numbers are frozen until an approver decides.",
    responses={**_ERRORS},
)
async def submit_payroll_for_approval(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayrollApprovalSvc
) -> APIResponse[PayrollRunRead]:
    run = await service.submit(run_id, actor_id=current_user.id)
    return APIResponse.ok(run, message="Submitted for approval")


@router.post(
    "/runs/{run_id}/approve",
    dependencies=[require("payroll:approve")],
    response_model=APIResponse[PayrollRunRead],
    summary="Approve a submitted run",
    description="The comment is mandatory and the gates are re-validated at the moment of the "
    "decision — a screen that showed a clean run earlier is not an authority.",
    responses={**_ERRORS},
)
async def approve_payroll_run(
    run_id: uuid.UUID,
    payload: PayrollApprovalDecision,
    current_user: CurrentUser,
    service: PayrollApprovalSvc,
) -> APIResponse[PayrollRunRead]:
    run = await service.approve(run_id, payload, actor_id=current_user.id)
    return APIResponse.ok(run, message="Payroll approved")


@router.post(
    "/runs/{run_id}/return",
    dependencies=[require("payroll:return")],
    response_model=APIResponse[PayrollRunRead],
    summary="Return a submitted run for correction",
    description="Requires a reason, which goes on the run and into the approval trail. The run "
    "reopens for review and recalculation; nothing is altered silently.",
    responses={**_ERRORS},
)
async def return_payroll_run(
    run_id: uuid.UUID,
    payload: PayrollReturnRequest,
    current_user: CurrentUser,
    service: PayrollApprovalSvc,
) -> APIResponse[PayrollRunRead]:
    run = await service.send_back(run_id, payload, actor_id=current_user.id)
    return APIResponse.ok(run, message="Returned for correction")


@router.post(
    "/runs/{run_id}/finalize",
    dependencies=[require("payroll:finalize")],
    response_model=APIResponse[PayrollRunRead],
    summary="Finalize an approved run",
    description="Writes one immutable, fully denormalized snapshot per employee, locks the run "
    "against every mutation path, and closes its payroll period. After this, the payroll is "
    "read-only: later salary, attendance or leave changes cannot touch it.",
    responses={**_ERRORS},
)
async def finalize_payroll_run(
    run_id: uuid.UUID,
    payload: PayrollFinalizeRequest,
    current_user: CurrentUser,
    service: PayrollApprovalSvc,
) -> APIResponse[PayrollRunRead]:
    run = await service.finalize(run_id, payload, actor_id=current_user.id)
    return APIResponse.ok(run, message="Payroll finalized")


@router.get(
    "/runs/{run_id}/snapshots",
    dependencies=[require_org_wide("payroll:finalized_view")],
    response_model=APIResponse[list[PayrollSnapshotRead]],
    summary="A finalized run's immutable snapshots",
    description="The per-employee record of what was actually paid — names, dates, line items and "
    "adjustments copied in as plain values, unaffected by anything that changes later.",
    responses={**_ERRORS},
)
async def payroll_run_snapshots(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayrollApprovalSvc
) -> APIResponse[list[PayrollSnapshotRead]]:
    del current_user
    return APIResponse.ok(await service.run_snapshots(run_id))


# ======================================================================
# Phase 7 — payslips
#
# Official documents over finalized payroll. The employee's own payslips
# live under /me and take no employee id; the administrator paths carry the
# employee id so the scope guards apply, and the service refuses a payslip
# id that does not belong to that employee.
# ======================================================================
def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@me_router.get(
    "/payroll/payslips",
    response_model=APIResponse[Page[PayslipRead]],
    summary="My payslips",
    description="The caller's own official payslips, newest period first. Only finalized payroll "
    "produces a payslip; a run under review or approval shows nothing here.",
    responses={**_ERRORS},
)
async def my_payslips(
    params: PayslipParams, employee: CurrentEmployee, service: PayslipSvc
) -> APIResponse[Page[PayslipRead]]:
    rows, total = await service.list_mine(employee, params)
    return APIResponse.ok(Page.create(rows, page=params.page, page_size=params.page_size, total_items=total))


@me_router.get(
    "/payroll/payslips/{payslip_id}",
    response_model=APIResponse[PayslipDetail],
    summary="One of my payslips",
    responses={**_ERRORS},
)
async def my_payslip(
    payslip_id: uuid.UUID, employee: CurrentEmployee, current_user: CurrentUser, service: PayslipSvc
) -> APIResponse[PayslipDetail]:
    return APIResponse.ok(await service.get_mine(employee, payslip_id, actor_id=current_user.id))


@me_router.get(
    "/payroll/payslips/{payslip_id}/download",
    summary="Download one of my payslips",
    responses={**_ERRORS, 200: {"content": {"application/pdf": {}}, "description": "The PDF."}},
)
async def download_my_payslip(
    payslip_id: uuid.UUID, employee: CurrentEmployee, current_user: CurrentUser, service: PayslipSvc
) -> Response:
    content, filename = await service.download_mine(employee, payslip_id, actor_id=current_user.id)
    return _pdf_response(content, filename)


@router.get(
    "/payslips",
    dependencies=[require_org_wide("payroll:payslip_view")],
    response_model=APIResponse[Page[PayslipRead]],
    summary="Payslips across the organization",
    description="Filter by employee, payroll month (YYYY-MM), department (team) or payslip number.",
    responses={**_ERRORS},
)
async def list_payslips(
    params: PayslipParams, current_user: CurrentUser, service: PayslipSvc
) -> APIResponse[Page[PayslipRead]]:
    del current_user
    rows, total = await service.list_admin(params)
    return APIResponse.ok(Page.create(rows, page=params.page, page_size=params.page_size, total_items=total))


@router.post(
    "/runs/{run_id}/payslips/generate",
    dependencies=[require_org_wide("payroll:payslip_generate")],
    response_model=APIResponse[PayslipGenerationResult],
    summary="Generate payslips for a finalized run",
    description="One payslip per employee with a final snapshot; excluded employees are skipped and "
    "existing payslips are left alone. Refused for any run that is not finalized.",
    responses={**_ERRORS},
)
async def generate_payslips(
    run_id: uuid.UUID, current_user: CurrentUser, service: PayslipSvc
) -> APIResponse[PayslipGenerationResult]:
    result = await service.generate_for_run(run_id, actor_id=current_user.id)
    return APIResponse.ok(result, message=f"{result.generated} payslip(s) generated")


@router.post(
    "/payslips/{payslip_id}/regenerate",
    dependencies=[require_org_wide("payroll:payslip_generate")],
    response_model=APIResponse[PayslipRead],
    summary="Regenerate a payslip's PDF",
    description="Rebuilds the document from the same finalized snapshot. The payslip number and "
    "every figure stay exactly as they were.",
    responses={**_ERRORS},
)
async def regenerate_payslip(
    payslip_id: uuid.UUID, current_user: CurrentUser, service: PayslipSvc
) -> APIResponse[PayslipRead]:
    row = await service.regenerate(payslip_id, actor_id=current_user.id)
    return APIResponse.ok(row, message="Payslip PDF regenerated")


@router.get(
    "/employees/{employee_id}/payslips/{payslip_id}",
    dependencies=[require_self_or("payroll:payslip_view", "payroll:team_view")],
    response_model=APIResponse[PayslipDetail],
    summary="One employee's payslip",
    description="Your own payslip always answers. Anybody else's needs payroll:payslip_view or a "
    "manager's explicit payroll:team_view, and the payslip must belong to that employee.",
    responses={**_ERRORS},
)
async def employee_payslip(
    employee_id: uuid.UUID,
    payslip_id: uuid.UUID,
    current_user: CurrentUser,
    service: PayslipSvc,
) -> APIResponse[PayslipDetail]:
    return APIResponse.ok(await service.get_admin(employee_id, payslip_id, actor_id=current_user.id))


@router.get(
    "/employees/{employee_id}/payslips/{payslip_id}/download",
    dependencies=[require_self_or("payroll:payslip_download", "payroll:team_view")],
    summary="Download one employee's payslip",
    responses={**_ERRORS, 200: {"content": {"application/pdf": {}}, "description": "The PDF."}},
)
async def download_employee_payslip(
    employee_id: uuid.UUID,
    payslip_id: uuid.UUID,
    current_user: CurrentUser,
    service: PayslipSvc,
) -> Response:
    content, filename = await service.download_admin(employee_id, payslip_id, actor_id=current_user.id)
    return _pdf_response(content, filename)
