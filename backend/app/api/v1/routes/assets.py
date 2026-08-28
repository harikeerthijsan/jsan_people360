"""Asset management endpoints.

Four audiences, and the differences between them are the access model rather
than a naming convention.

``me_router`` (**employee**) carries no ``require(...)`` guard, like everything
else under ``/me``: the only records in reach are the caller's own, and a
permission there would let an administrator take away somebody's ability to see
what they are holding. **No route on it takes an employee id.**

``manager_router`` (**manager**) carries ``assets:view`` *and* runs in
``ManagerScope``. The permission says the caller may use the module; the scope
says whose assets. Managers hold ``assets:view`` and nothing else, so these
screens are read-only by construction rather than by hiding buttons.

``hr_router`` (**HR**) is the offboarding-facing view: what one employee is
holding, for a clearance. It is guarded by ``assets:view`` together with
``employees:view_all`` -- the org-wide pairing ``require_org_wide`` exists for --
and there is deliberately no HR route that creates, assigns, moves or retires
anything. That absence *is* §12 of the brief.

``router`` (**admin**) carries the custody permissions, one per operation:
``assets:assign``, ``assets:return``, ``assets:transfer``, ``assets:maintain``,
``assets:retire``, ``assets:dispose``. They are separate because they are
separate authorities, and an organization that wants to split them can.

Route order matters as elsewhere: static segments precede the ``/{id}`` forms.

NOTE: no ``from __future__ import annotations`` -- FastAPI reads parameter types
from evaluated annotations, and postponed evaluation breaks ``Annotated[...,
Query()]``.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    AssetSvc,
    CurrentEmployee,
    CurrentScope,
    CurrentUser,
    ManagerScope,
    require,
    require_org_wide,
    require_team_scope,
)
from app.models.enums import AssetStatus
from app.schemas.asset import (
    AssetAssign,
    AssetAssignmentRead,
    AssetCategoryCreate,
    AssetCategoryRead,
    AssetCategoryUpdate,
    AssetCreate,
    AssetDashboard,
    AssetDetail,
    AssetListParams,
    AssetRead,
    AssetReturnInput,
    AssetReturnRead,
    AssetStatusChange,
    AssetTransferInput,
    AssetTransferRead,
    AssetUpdate,
    EmployeeAssetClearanceRow,
    MaintenanceCreate,
    MaintenanceListParams,
    MaintenanceRead,
    MaintenanceUpdate,
    MyAsset,
    TeamAssetRow,
)
from app.schemas.common import APIErrorResponse, APIResponse, Page

router = APIRouter(prefix="/assets", tags=["Asset Management"])
me_router = APIRouter(prefix="/me", tags=["Employee Self-Service"])
manager_router = APIRouter(prefix="/manager", tags=["Manager"])
hr_router = APIRouter(prefix="/hr", tags=["HR"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_403_FORBIDDEN: {
        "model": APIErrorResponse,
        "description": "Missing the permission, or the asset is outside your reach.",
    },
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such record."},
    status.HTTP_409_CONFLICT: {
        "model": APIErrorResponse,
        "description": "A workflow rule was violated -- an invalid status transition, or an asset "
        "that is already assigned.",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": APIErrorResponse,
        "description": "Validation failed.",
    },
}

AssetParams = Annotated[AssetListParams, Query()]
MaintenanceParams = Annotated[MaintenanceListParams, Query()]


# ======================================================================
# Employee self-service
# ======================================================================
@me_router.get(
    "/assets",
    response_model=APIResponse[list[MyAsset]],
    summary="Assets assigned to me",
    description=(
        "Only what the caller currently holds. Carries no purchase cost, vendor or internal notes: "
        "the read model omits them rather than filtering them out."
    ),
    responses={**_ERRORS},
)
async def my_assets(employee: CurrentEmployee, service: AssetSvc) -> APIResponse[list[MyAsset]]:
    return APIResponse.ok(await service.my_assets(employee))


# ======================================================================
# Manager
# ======================================================================
@manager_router.get(
    "/assets",
    dependencies=[require("assets:view")],
    response_model=APIResponse[list[TeamAssetRow]],
    summary="Assets held by my direct reports",
    description="Direct reports only, resolved from the reporting line rather than from a supplied id.",
    responses={**_ERRORS},
)
async def team_assets(
    scope: ManagerScope, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[list[TeamAssetRow]]:
    del current_user
    return APIResponse.ok(await service.team_assets(scope))


# ======================================================================
# HR -- sight for a clearance, and nothing else
# ======================================================================
@hr_router.get(
    "/assets/{employee_id}",
    dependencies=[require_org_wide("assets:view"), require_team_scope()],
    response_model=APIResponse[list[EmployeeAssetClearanceRow]],
    summary="What one employee is holding",
    description=(
        "The offboarding-facing view: the assets a leaver still has, for a clearance. There is no "
        "HR endpoint that issues, recalls, moves or retires anything -- those are Admin's."
    ),
    responses={**_ERRORS},
)
async def employee_assets(
    employee_id: uuid.UUID, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[list[EmployeeAssetClearanceRow]]:
    del current_user
    return APIResponse.ok(await service.assets_for_employee(employee_id))


# ======================================================================
# Admin: categories
# ======================================================================
@router.get(
    "/categories",
    dependencies=[require("assets:view")],
    response_model=APIResponse[list[AssetCategoryRead]],
    summary="Asset categories",
    description="The configurable category master. Never hardcoded in the client.",
    responses={**_ERRORS},
)
async def list_categories(
    current_user: CurrentUser,
    service: AssetSvc,
    include_inactive: Annotated[bool, Query()] = False,
) -> APIResponse[list[AssetCategoryRead]]:
    del current_user
    rows = await service.list_categories(include_inactive=include_inactive)
    return APIResponse.ok([AssetCategoryRead.model_validate(row) for row in rows])


@router.post(
    "/categories",
    dependencies=[require("assets:manage")],
    response_model=APIResponse[AssetCategoryRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create an asset category",
    responses={**_ERRORS},
)
async def create_category(
    payload: AssetCategoryCreate, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[AssetCategoryRead]:
    category = await service.create_category(payload, actor_id=current_user.id)
    return APIResponse.ok(AssetCategoryRead.model_validate(category), message="Category created")


@router.patch(
    "/categories/{category_id}",
    dependencies=[require("assets:manage")],
    response_model=APIResponse[AssetCategoryRead],
    summary="Update or deactivate an asset category",
    responses={**_ERRORS},
)
async def update_category(
    category_id: uuid.UUID,
    payload: AssetCategoryUpdate,
    current_user: CurrentUser,
    service: AssetSvc,
) -> APIResponse[AssetCategoryRead]:
    category = await service.update_category(category_id, payload, actor_id=current_user.id)
    return APIResponse.ok(AssetCategoryRead.model_validate(category), message="Category updated")


# ======================================================================
# Admin: dashboard, maintenance and reports (before /{asset_id})
# ======================================================================
@router.get(
    "/dashboard",
    dependencies=[require("assets:view")],
    response_model=APIResponse[AssetDashboard],
    summary="Asset dashboard",
    description="Counts by status, category and location, warranty exposure and recent movement.",
    responses={**_ERRORS},
)
async def dashboard(current_user: CurrentUser, service: AssetSvc) -> APIResponse[AssetDashboard]:
    del current_user
    return APIResponse.ok(await service.dashboard())


@router.get(
    "/maintenance",
    dependencies=[require("assets:view")],
    response_model=APIResponse[Page[MaintenanceRead]],
    summary="Maintenance records",
    responses={**_ERRORS},
)
async def list_maintenance(
    params: MaintenanceParams, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[Page[MaintenanceRead]]:
    del current_user
    rows, total = await service.list_maintenance(params)
    return APIResponse.ok(
        Page.create(
            [MaintenanceRead.model_validate(row) for row in rows],
            page=params.page,
            page_size=params.page_size,
            total_items=total,
        )
    )


@router.post(
    "/maintenance",
    dependencies=[require("assets:maintain")],
    response_model=APIResponse[MaintenanceRead],
    status_code=status.HTTP_201_CREATED,
    summary="Schedule or start maintenance",
    description="Starting it takes the asset off the floor; scheduling it does not.",
    responses={**_ERRORS},
)
async def schedule_maintenance(
    payload: MaintenanceCreate, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[MaintenanceRead]:
    record = await service.schedule_maintenance(payload, actor_id=current_user.id)
    return APIResponse.ok(MaintenanceRead.model_validate(record), message="Maintenance recorded")


@router.patch(
    "/maintenance/{maintenance_id}",
    dependencies=[require("assets:maintain")],
    response_model=APIResponse[MaintenanceRead],
    summary="Progress or complete maintenance",
    description="Completing it releases the asset, by default back to available.",
    responses={**_ERRORS},
)
async def update_maintenance(
    maintenance_id: uuid.UUID,
    payload: MaintenanceUpdate,
    current_user: CurrentUser,
    service: AssetSvc,
) -> APIResponse[MaintenanceRead]:
    record = await service.update_maintenance(maintenance_id, payload, actor_id=current_user.id)
    return APIResponse.ok(MaintenanceRead.model_validate(record), message="Maintenance updated")


@router.get(
    "/reports/{report}/export",
    dependencies=[require("assets:export")],
    summary="Export an asset report",
    description="inventory, assigned, available, by_employee, maintenance, warranty, lost_damaged "
    "or movement, as CSV or XLSX.",
    responses={**_ERRORS},
)
async def export_report(
    report: str,
    fmt: Literal["csv", "xlsx"],
    current_user: CurrentUser,
    service: AssetSvc,
) -> Response:
    content, media_type = await service.export(report, fmt, actor_id=current_user.id)
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="assets-{report}.{fmt}"'},
    )


# ======================================================================
# Admin: the register
# ======================================================================
@router.get(
    "",
    dependencies=[require("assets:view")],
    response_model=APIResponse[Page[AssetRead]],
    summary="The asset register",
    description=(
        "Server-side search, filtering and pagination. Narrowed to the holders the caller may see "
        "unless they hold employees:view_all."
    ),
    responses={**_ERRORS},
)
async def list_assets(
    params: AssetParams, scope: CurrentScope, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[Page[AssetRead]]:
    del current_user
    if params.employee_id is not None:
        scope.assert_allows(params.employee_id)
    rows, total = await service.list_assets(params, scope=scope)
    # One query for every holder on the page, not two per row.
    items = await service.present_many(rows)
    return APIResponse.ok(Page.create(items, page=params.page, page_size=params.page_size, total_items=total))


@router.post(
    "",
    dependencies=[require("assets:create")],
    response_model=APIResponse[AssetRead],
    status_code=status.HTTP_201_CREATED,
    summary="Register an asset",
    description="The asset code is generated. An asset cannot be created already assigned.",
    responses={**_ERRORS},
)
async def create_asset(
    payload: AssetCreate, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[AssetRead]:
    asset = await service.create_asset(payload, actor_id=current_user.id)
    return APIResponse.ok(await service.present(asset), message="Asset registered")


@router.get(
    "/{asset_id}",
    dependencies=[require("assets:view")],
    response_model=APIResponse[AssetDetail],
    summary="One asset, with its full history",
    responses={**_ERRORS},
)
async def get_asset(
    asset_id: uuid.UUID, scope: CurrentScope, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[AssetDetail]:
    del current_user
    asset = await service.get_asset(asset_id, scope=scope)
    return APIResponse.ok(await service.present_detail(asset))


@router.patch(
    "/{asset_id}",
    dependencies=[require("assets:update")],
    response_model=APIResponse[AssetRead],
    summary="Edit asset details",
    description=(
        "Details only. Custody moves through assign, return and transfer; status moves through the "
        "status endpoint. Neither is reachable from here, so an edit cannot rewrite history."
    ),
    responses={**_ERRORS},
)
async def update_asset(
    asset_id: uuid.UUID, payload: AssetUpdate, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[AssetRead]:
    asset = await service.update_asset(asset_id, payload, actor_id=current_user.id)
    return APIResponse.ok(await service.present(asset), message="Asset updated")


@router.post(
    "/{asset_id}/assign",
    dependencies=[require("assets:assign")],
    response_model=APIResponse[AssetAssignmentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Assign an asset to an employee",
    description="Refused when the asset is already assigned, under maintenance, retired or disposed.",
    responses={**_ERRORS},
)
async def assign_asset(
    asset_id: uuid.UUID, payload: AssetAssign, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[AssetAssignmentRead]:
    assignment = await service.assign(asset_id, payload, actor_id=current_user.id)
    return APIResponse.ok(AssetAssignmentRead.model_validate(assignment), message="Asset assigned")


@router.post(
    "/{asset_id}/return",
    dependencies=[require("assets:return")],
    response_model=APIResponse[AssetReturnRead],
    status_code=status.HTTP_201_CREATED,
    summary="Process a return",
    description=(
        "Writes a return transaction and closes the assignment. An asset returned damaged goes to "
        "maintenance rather than straight back to the available pool."
    ),
    responses={**_ERRORS},
)
async def return_asset(
    asset_id: uuid.UUID, payload: AssetReturnInput, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[AssetReturnRead]:
    record = await service.process_return(asset_id, payload, actor_id=current_user.id)
    return APIResponse.ok(AssetReturnRead.model_validate(record), message="Return recorded")


@router.post(
    "/{asset_id}/transfer",
    dependencies=[require("assets:transfer")],
    response_model=APIResponse[AssetTransferRead],
    status_code=status.HTTP_201_CREATED,
    summary="Transfer an asset between employees",
    description="Closes one custody period and opens another. Both survive, so the history reads A -> B.",
    responses={**_ERRORS},
)
async def transfer_asset(
    asset_id: uuid.UUID, payload: AssetTransferInput, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[AssetTransferRead]:
    record = await service.transfer(asset_id, payload, actor_id=current_user.id)
    return APIResponse.ok(AssetTransferRead.model_validate(record), message="Asset transferred")


@router.post(
    "/{asset_id}/status",
    dependencies=[require("assets:retire", "assets:dispose", require_all=False)],
    response_model=APIResponse[AssetRead],
    summary="Change an asset's status",
    description=(
        "Validated against the transition table: a disposed asset cannot come back, and a damaged "
        "one cannot become available without passing through maintenance."
    ),
    responses={**_ERRORS},
)
async def change_status(
    asset_id: uuid.UUID, payload: AssetStatusChange, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[AssetRead]:
    asset = await service.change_status(asset_id, payload, actor_id=current_user.id)
    return APIResponse.ok(await service.present(asset), message="Status updated")


@router.get(
    "/{asset_id}/transitions",
    dependencies=[require("assets:view")],
    response_model=APIResponse[list[AssetStatus]],
    summary="Where this asset may move next",
    description="Computed from the transition table so the client never holds a copy of it.",
    responses={**_ERRORS},
)
async def allowed_transitions(
    asset_id: uuid.UUID, scope: CurrentScope, current_user: CurrentUser, service: AssetSvc
) -> APIResponse[list[AssetStatus]]:
    del current_user
    asset = await service.get_asset(asset_id, scope=scope)
    detail = await service.present_detail(asset)
    return APIResponse.ok(detail.allowed_transitions)
