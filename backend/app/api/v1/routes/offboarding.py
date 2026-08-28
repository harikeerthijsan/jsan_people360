"""Resignation and offboarding endpoints.

Three audiences, three routers, three different ways of being guarded -- and the
differences are the access model rather than a style choice.

``me_router`` (**employee**) carries no ``require(...)`` guard, for the same
reason nothing under ``/me`` does: a permission answers "may you act on this
module", and the only record in reach here is your own. Guarding it would let an
administrator take away an employee's ability to resign or to read their own
relieving letter. **No route on it accepts an employee id** -- not as a path
parameter, not in a body -- so submitting somebody else's resignation is a thing
that cannot be expressed rather than a thing a check has to catch.

``manager_router`` (**manager**) carries a permission guard *and* runs in
``ManagerScope``. The permission is ``resignation:approve``, not
``resignation:view``: the base Employee role holds the views, so guarding a team
screen with one would silently widen access for any employee who happens to have
a direct report. ``ManagerScope`` excludes the caller, which is also what stops
a manager approving their own resignation through it.

``router`` (**HR and admin**) carries the module permissions, and the
administrative actions carry the *administrative* ones. ``resignation:process``
opens a case; ``offboarding:manage`` reassigns a task, forces a completion or
overrides a settled date. HR Admin holds the first and, deliberately, not
``resignation:approve`` -- deciding a team's resignation is the manager's.
Overrides are audited as overrides, per §18 of the brief.

Route order matters as elsewhere: static segments precede the ``/{id}`` forms.

NOTE: no ``from __future__ import annotations`` -- FastAPI reads parameter types
from evaluated annotations, and postponed evaluation breaks ``Annotated[...,
Query()]``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import (
    AuthzSvc,
    CurrentEmployee,
    CurrentScope,
    CurrentUser,
    ManagerScope,
    OffboardingSvc,
    require,
    require_any,
)
from app.core.permissions import PermissionAction, code
from app.schemas.common import APIErrorResponse, APIResponse, Page
from app.schemas.offboarding import (
    AccessClearanceInput,
    AccessClearanceRead,
    AccessClearanceUpdate,
    AssetClearanceInput,
    AssetClearanceRead,
    AssetClearanceUpdate,
    CaseCompletion,
    ExitDocumentGenerate,
    ExitDocumentRead,
    ExitInterviewListItem,
    ExitInterviewRead,
    ExitInterviewSubmit,
    HandoverInput,
    HandoverRead,
    HrProcess,
    LastWorkingDayChange,
    ManagerDecision,
    MyOffboarding,
    MyResignation,
    OffboardingCaseRead,
    OffboardingListParams,
    OffboardingSummary,
    OffboardingTaskCreate,
    OffboardingTaskRead,
    OffboardingTaskUpdate,
    ResignationCancel,
    ResignationListParams,
    ResignationRead,
    ResignationSubmit,
    ResignationWithdraw,
    SettlementRead,
    SettlementUpdate,
)

router = APIRouter(prefix="/offboarding", tags=["Resignation & Offboarding"])
me_router = APIRouter(prefix="/me", tags=["Employee Self-Service"])
manager_router = APIRouter(prefix="/manager", tags=["Manager"])

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

ResignationParams = Annotated[ResignationListParams, Query()]
CaseParams = Annotated[OffboardingListParams, Query()]


async def _may_manage(user: CurrentUser, authorization: AuthzSvc) -> bool:
    """Whether the caller holds ``offboarding:manage``.

    Passed into the service as a capability rather than checked there: the
    service answers "what this action does", and "who may do the administrative
    version of it" is the route's question. The alternative -- handing the
    service a user and letting it ask -- would put a second authorization path
    inside the service layer, which is the thing `AuthorizationService` exists
    to prevent.
    """
    if user.is_superuser:
        return True
    held = await authorization.permissions_for(user)
    return code("offboarding", PermissionAction.MANAGE) in held


# ======================================================================
# Employee self-service
# ======================================================================
@me_router.get(
    "/resignation",
    response_model=APIResponse[MyResignation | None],
    summary="My resignation",
    description="The caller's own resignation with its notice figures and history, or null.",
    responses={**_ERRORS},
)
async def my_resignation(
    employee: CurrentEmployee, service: OffboardingSvc
) -> APIResponse[MyResignation | None]:
    resignation = await service.my_resignation(employee)
    return APIResponse.ok(await service.present_my_resignation(resignation))


@me_router.post(
    "/resignation",
    response_model=APIResponse[MyResignation],
    status_code=status.HTTP_201_CREATED,
    summary="Submit my resignation",
    description=(
        "Submits the caller's own resignation. The employee is taken from the access token; "
        "there is no field here that names a person."
    ),
    responses={**_ERRORS},
)
async def submit_my_resignation(
    payload: ResignationSubmit,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[MyResignation]:
    resignation = await service.submit_resignation(employee, payload, actor_id=current_user.id)
    presented = await service.present_my_resignation(resignation)
    assert presented is not None
    return APIResponse.ok(presented, message="Resignation submitted successfully")


@me_router.post(
    "/resignation/withdraw",
    response_model=APIResponse[MyResignation],
    summary="Withdraw my resignation",
    description="Allowed while the resignation is still being reviewed. Afterwards HR cancels it.",
    responses={**_ERRORS},
)
async def withdraw_my_resignation(
    payload: ResignationWithdraw,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[MyResignation]:
    resignation = await service.withdraw_resignation(employee, payload, actor_id=current_user.id)
    presented = await service.present_my_resignation(resignation)
    assert presented is not None
    return APIResponse.ok(presented, message="Resignation withdrawn")


@me_router.get(
    "/offboarding",
    response_model=APIResponse[MyOffboarding],
    summary="My offboarding",
    description="Clearance progress, the caller's own tasks, exit interview and released documents.",
    responses={**_ERRORS},
)
async def my_offboarding(employee: CurrentEmployee, service: OffboardingSvc) -> APIResponse[MyOffboarding]:
    return APIResponse.ok(await service.present_my_offboarding(employee))


@me_router.get(
    "/exit-interview",
    response_model=APIResponse[ExitInterviewRead | None],
    summary="My exit interview",
    responses={**_ERRORS},
)
async def my_exit_interview(
    employee: CurrentEmployee, service: OffboardingSvc
) -> APIResponse[ExitInterviewRead | None]:
    interview = await service.my_exit_interview(employee)
    return APIResponse.ok(ExitInterviewRead.model_validate(interview) if interview else None)


@me_router.post(
    "/exit-interview",
    response_model=APIResponse[ExitInterviewRead],
    status_code=status.HTTP_201_CREATED,
    summary="Submit my exit interview",
    description="Available once the resignation has been approved. Submitted once.",
    responses={**_ERRORS},
)
async def submit_my_exit_interview(
    payload: ExitInterviewSubmit,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[ExitInterviewRead]:
    interview = await service.submit_exit_interview(employee, payload, actor_id=current_user.id)
    return APIResponse.ok(ExitInterviewRead.model_validate(interview), message="Exit interview submitted")


@me_router.get(
    "/exit-documents",
    response_model=APIResponse[list[ExitDocumentRead]],
    summary="My exit documents",
    description="Only documents HR has released. The file itself is downloaded from the Document Vault.",
    responses={**_ERRORS},
)
async def my_exit_documents(
    employee: CurrentEmployee, service: OffboardingSvc
) -> APIResponse[list[ExitDocumentRead]]:
    documents = await service.my_exit_documents(employee)
    return APIResponse.ok([ExitDocumentRead.model_validate(item) for item in documents])


# ======================================================================
# Manager
# ======================================================================
@manager_router.get(
    "/resignations",
    dependencies=[require("resignation:view", "resignation:approve")],
    response_model=APIResponse[Page[ResignationRead]],
    summary="My team's resignations",
    description="Direct reports only. An employee_id filter narrows this list; it never widens it.",
    responses={**_ERRORS},
)
async def team_resignations(
    params: ResignationParams,
    scope: ManagerScope,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[Page[ResignationRead]]:
    del current_user
    if params.employee_id is not None:
        scope.assert_allows(params.employee_id)
    rows, total = await service.list_resignations(params, scope=scope)
    items = [await service.present_resignation(row) for row in rows]
    return APIResponse.ok(Page.create(items, page=params.page, page_size=params.page_size, total_items=total))


@manager_router.post(
    "/resignations/{resignation_id}/decision",
    dependencies=[require("resignation:approve")],
    response_model=APIResponse[ResignationRead],
    summary="Approve or reject a direct report's resignation",
    description=(
        "The manager's decision. Refused for a resignation outside the caller's reporting line, "
        "and for their own -- the manager scope excludes the caller."
    ),
    responses={**_ERRORS},
)
async def decide_resignation(
    resignation_id: uuid.UUID,
    payload: ManagerDecision,
    scope: ManagerScope,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[ResignationRead]:
    resignation = await service.manager_decision(
        resignation_id, payload, actor_id=current_user.id, scope=scope
    )
    return APIResponse.ok(
        await service.present_resignation(resignation), message=f"Resignation {payload.decision}d"
    )


@manager_router.get(
    "/offboarding",
    dependencies=[require("offboarding:view", "resignation:view")],
    response_model=APIResponse[Page[OffboardingCaseRead]],
    summary="My team's offboarding cases",
    responses={**_ERRORS},
)
async def team_offboarding(
    params: CaseParams,
    scope: ManagerScope,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[Page[OffboardingCaseRead]]:
    del current_user
    if params.employee_id is not None:
        scope.assert_allows(params.employee_id)
    rows, total = await service.list_cases(params, scope=scope)
    items = [await service.present_case(row) for row in rows]
    return APIResponse.ok(Page.create(items, page=params.page, page_size=params.page_size, total_items=total))


@manager_router.get(
    "/offboarding/{case_id}",
    dependencies=[require("offboarding:view", "resignation:view")],
    response_model=APIResponse[OffboardingCaseRead],
    summary="One team member's offboarding case",
    responses={**_ERRORS},
)
async def team_offboarding_case(
    case_id: uuid.UUID,
    scope: ManagerScope,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[OffboardingCaseRead]:
    del current_user
    case = await service.get_case(case_id, scope=scope)
    return APIResponse.ok(await service.present_case(case))


@manager_router.put(
    "/offboarding/{case_id}/handover",
    dependencies=[require("offboarding:update")],
    response_model=APIResponse[HandoverRead],
    summary="Record the knowledge transfer",
    description="Projects, responsibilities, documentation, replacement and Document Vault attachments.",
    responses={**_ERRORS},
)
async def record_handover(
    case_id: uuid.UUID,
    payload: HandoverInput,
    scope: ManagerScope,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[HandoverRead]:
    record = await service.record_handover(case_id, payload, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(HandoverRead.model_validate(record), message="Handover recorded")


@manager_router.patch(
    "/offboarding/tasks/{task_id}",
    dependencies=[require("offboarding:update")],
    response_model=APIResponse[OffboardingTaskRead],
    summary="Complete one of my offboarding tasks",
    description="Scoped to the caller's direct reports. Reassignment needs offboarding:manage.",
    responses={**_ERRORS},
)
async def complete_manager_task(
    task_id: uuid.UUID,
    payload: OffboardingTaskUpdate,
    scope: ManagerScope,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[OffboardingTaskRead]:
    task = await service.update_task(
        task_id, payload, actor_id=current_user.id, scope=scope, may_reassign=False
    )
    return APIResponse.ok(OffboardingTaskRead.model_validate(task), message="Task updated")


# ======================================================================
# HR and admin
# ======================================================================
@router.get(
    "/summary",
    dependencies=[require_any("offboarding:view", "resignation:view")],
    response_model=APIResponse[OffboardingSummary],
    summary="Offboarding summary",
    description="Counters for the HR dashboard, narrowed to what the caller's scope reaches.",
    responses={**_ERRORS},
)
async def offboarding_summary(
    scope: CurrentScope, current_user: CurrentUser, service: OffboardingSvc
) -> APIResponse[OffboardingSummary]:
    del current_user
    return APIResponse.ok(await service.summary(scope=scope))


@router.get(
    "/resignations",
    dependencies=[require("resignation:view")],
    response_model=APIResponse[Page[ResignationRead]],
    summary="Resignations",
    responses={**_ERRORS},
)
async def list_resignations(
    params: ResignationParams,
    scope: CurrentScope,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[Page[ResignationRead]]:
    del current_user
    if params.employee_id is not None:
        scope.assert_allows(params.employee_id)
    rows, total = await service.list_resignations(params, scope=scope)
    items = [await service.present_resignation(row) for row in rows]
    return APIResponse.ok(Page.create(items, page=params.page, page_size=params.page_size, total_items=total))


@router.get(
    "/resignations/{resignation_id}",
    dependencies=[require("resignation:view")],
    response_model=APIResponse[ResignationRead],
    summary="One resignation",
    responses={**_ERRORS},
)
async def get_resignation(
    resignation_id: uuid.UUID,
    scope: CurrentScope,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[ResignationRead]:
    del current_user
    resignation = await service.get_resignation(resignation_id, scope=scope)
    return APIResponse.ok(await service.present_resignation(resignation))


@router.post(
    "/resignations/{resignation_id}/process",
    dependencies=[require("resignation:process")],
    response_model=APIResponse[OffboardingCaseRead],
    status_code=status.HTTP_201_CREATED,
    summary="Process a resignation and open the offboarding case",
    description=(
        "HR's step, distinct from the manager's approval: settles the last working day, "
        "applies any authorized notice adjustment and creates the case with its default checklist."
    ),
    responses={**_ERRORS},
)
async def process_resignation(
    resignation_id: uuid.UUID,
    payload: HrProcess,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[OffboardingCaseRead]:
    case = await service.process_resignation(resignation_id, payload, actor_id=current_user.id)
    return APIResponse.ok(await service.present_case(case), message="Offboarding started")


@router.post(
    "/resignations/{resignation_id}/last-working-day",
    dependencies=[require("resignation:process")],
    response_model=APIResponse[ResignationRead],
    summary="Change an approved last working day",
    description="Recorded in history with the reason. Audited as an override when the caller holds "
    "offboarding:manage, which is what an administrative change is.",
    responses={**_ERRORS},
)
async def change_last_working_day(
    resignation_id: uuid.UUID,
    payload: LastWorkingDayChange,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[ResignationRead]:
    resignation = await service.change_last_working_day(
        resignation_id, payload, actor_id=current_user.id, is_override=True
    )
    return APIResponse.ok(await service.present_resignation(resignation), message="Last working day updated")


@router.post(
    "/resignations/{resignation_id}/cancel",
    dependencies=[require("resignation:process", "offboarding:manage")],
    response_model=APIResponse[ResignationRead],
    summary="Cancel an approved separation",
    description="Reverses a decision already taken: cancels the case and returns the employee to active. "
    "Audited as an override.",
    responses={**_ERRORS},
)
async def cancel_resignation(
    resignation_id: uuid.UUID,
    payload: ResignationCancel,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[ResignationRead]:
    resignation = await service.cancel_resignation(
        resignation_id, payload, actor_id=current_user.id, is_override=True
    )
    return APIResponse.ok(await service.present_resignation(resignation), message="Separation cancelled")


@router.get(
    "/cases",
    dependencies=[require("offboarding:view")],
    response_model=APIResponse[Page[OffboardingCaseRead]],
    summary="Offboarding cases",
    responses={**_ERRORS},
)
async def list_cases(
    params: CaseParams,
    scope: CurrentScope,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[Page[OffboardingCaseRead]]:
    del current_user
    if params.employee_id is not None:
        scope.assert_allows(params.employee_id)
    rows, total = await service.list_cases(params, scope=scope)
    items = [await service.present_case(row) for row in rows]
    return APIResponse.ok(Page.create(items, page=params.page, page_size=params.page_size, total_items=total))


@router.get(
    "/cases/{case_id}",
    dependencies=[require("offboarding:view")],
    response_model=APIResponse[OffboardingCaseRead],
    summary="One offboarding case",
    responses={**_ERRORS},
)
async def get_case(
    case_id: uuid.UUID, scope: CurrentScope, current_user: CurrentUser, service: OffboardingSvc
) -> APIResponse[OffboardingCaseRead]:
    del current_user
    case = await service.get_case(case_id, scope=scope)
    return APIResponse.ok(await service.present_case(case))


@router.post(
    "/cases/{case_id}/tasks",
    dependencies=[require("offboarding:manage")],
    response_model=APIResponse[OffboardingTaskRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add a checklist task",
    responses={**_ERRORS},
)
async def add_task(
    case_id: uuid.UUID,
    payload: OffboardingTaskCreate,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[OffboardingTaskRead]:
    task = await service.add_task(case_id, payload, actor_id=current_user.id)
    return APIResponse.ok(OffboardingTaskRead.model_validate(task), message="Task added")


@router.patch(
    "/tasks/{task_id}",
    dependencies=[require("offboarding:update")],
    response_model=APIResponse[OffboardingTaskRead],
    summary="Update a checklist task",
    description="Reassignment (owner_id) additionally needs offboarding:manage.",
    responses={**_ERRORS},
)
async def update_task(
    task_id: uuid.UUID,
    payload: OffboardingTaskUpdate,
    current_user: CurrentUser,
    service: OffboardingSvc,
    scope: CurrentScope,
    authorization: AuthzSvc,
) -> APIResponse[OffboardingTaskRead]:
    task = await service.update_task(
        task_id,
        payload,
        actor_id=current_user.id,
        scope=scope,
        may_reassign=await _may_manage(current_user, authorization),
    )
    return APIResponse.ok(OffboardingTaskRead.model_validate(task), message="Task updated")


@router.post(
    "/cases/{case_id}/assets",
    dependencies=[require("offboarding:manage")],
    response_model=APIResponse[AssetClearanceRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add an asset to the clearance list",
    responses={**_ERRORS},
)
async def add_asset(
    case_id: uuid.UUID,
    payload: AssetClearanceInput,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[AssetClearanceRead]:
    asset = await service.add_asset(case_id, payload, actor_id=current_user.id)
    return APIResponse.ok(AssetClearanceRead.model_validate(asset), message="Asset added")


@router.patch(
    "/assets/{asset_id}",
    dependencies=[require("offboarding:manage")],
    response_model=APIResponse[AssetClearanceRead],
    summary="Record an asset return",
    responses={**_ERRORS},
)
async def update_asset(
    asset_id: uuid.UUID,
    payload: AssetClearanceUpdate,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[AssetClearanceRead]:
    asset = await service.update_asset(asset_id, payload, actor_id=current_user.id)
    return APIResponse.ok(AssetClearanceRead.model_validate(asset), message="Asset clearance updated")


@router.post(
    "/cases/{case_id}/access",
    dependencies=[require("offboarding:manage")],
    response_model=APIResponse[AccessClearanceRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add a system to the access-clearance list",
    responses={**_ERRORS},
)
async def add_access_item(
    case_id: uuid.UUID,
    payload: AccessClearanceInput,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[AccessClearanceRead]:
    item = await service.add_access_item(case_id, payload, actor_id=current_user.id)
    return APIResponse.ok(AccessClearanceRead.model_validate(item), message="Access item added")


@router.patch(
    "/access/{item_id}",
    dependencies=[require("offboarding:manage")],
    response_model=APIResponse[AccessClearanceRead],
    summary="Record an access revocation",
    description="Tracking only. Nothing here reaches out to a mail server or an identity provider.",
    responses={**_ERRORS},
)
async def update_access_item(
    item_id: uuid.UUID,
    payload: AccessClearanceUpdate,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[AccessClearanceRead]:
    item = await service.update_access_item(item_id, payload, actor_id=current_user.id)
    return APIResponse.ok(AccessClearanceRead.model_validate(item), message="Access clearance updated")


@router.put(
    "/cases/{case_id}/settlement",
    dependencies=[require("offboarding:manage")],
    response_model=APIResponse[SettlementRead],
    summary="Update full & final settlement status",
    description=(
        "Status, reference and date only. No salary, tax, PF, ESI or gratuity figure is "
        "calculated anywhere in this module."
    ),
    responses={**_ERRORS},
)
async def update_settlement(
    case_id: uuid.UUID,
    payload: SettlementUpdate,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[SettlementRead]:
    record = await service.update_settlement(case_id, payload, actor_id=current_user.id)
    return APIResponse.ok(SettlementRead.model_validate(record), message="Settlement status updated")


@router.post(
    "/cases/{case_id}/documents",
    dependencies=[require("exit_documents:manage")],
    response_model=APIResponse[ExitDocumentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Generate an exit document",
    description="Renders the letter, files it in the Document Vault and records that it was issued.",
    responses={**_ERRORS},
)
async def generate_exit_document(
    case_id: uuid.UUID,
    payload: ExitDocumentGenerate,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[ExitDocumentRead]:
    document = await service.generate_exit_document(case_id, payload, actor_id=current_user.id)
    return APIResponse.ok(ExitDocumentRead.model_validate(document), message="Exit document generated")


@router.post(
    "/cases/{case_id}/complete",
    dependencies=[require("offboarding:manage")],
    response_model=APIResponse[OffboardingCaseRead],
    summary="Complete the offboarding",
    description=(
        "Ends live project allocations, sets the employee inactive and closes the case. "
        "Nothing is deleted: attendance, leave, timesheets, projects, performance and documents "
        "all remain. Completing with outstanding clearance is an override and is audited as one."
    ),
    responses={**_ERRORS},
)
async def complete_case(
    case_id: uuid.UUID,
    payload: CaseCompletion,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[OffboardingCaseRead]:
    case = await service.complete_case(case_id, payload, actor_id=current_user.id, may_force=True)
    return APIResponse.ok(await service.present_case(case), message="Offboarding completed")


@router.get(
    "/exit-interviews",
    dependencies=[require("exit_interview:view")],
    response_model=APIResponse[Page[ExitInterviewListItem]],
    summary="Completed exit interviews",
    responses={**_ERRORS},
)
async def list_exit_interviews(
    scope: CurrentScope,
    current_user: CurrentUser,
    service: OffboardingSvc,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> APIResponse[Page[ExitInterviewListItem]]:
    del current_user
    items, total = await service.list_exit_interviews(page=page, page_size=page_size, scope=scope)
    return APIResponse.ok(Page.create(items, page=page, page_size=page_size, total_items=total))


@router.get(
    "/cases/{case_id}/exit-interview",
    dependencies=[require("exit_interview:view")],
    response_model=APIResponse[ExitInterviewRead | None],
    summary="One case's exit interview",
    responses={**_ERRORS},
)
async def get_exit_interview(
    case_id: uuid.UUID,
    scope: CurrentScope,
    current_user: CurrentUser,
    service: OffboardingSvc,
) -> APIResponse[ExitInterviewRead | None]:
    del current_user
    case = await service.get_case(case_id, scope=scope)
    interview = await service.interviews.for_case(case.id)
    return APIResponse.ok(ExitInterviewRead.model_validate(interview) if interview else None)
