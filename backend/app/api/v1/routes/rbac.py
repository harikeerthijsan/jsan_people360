"""Role and permission administration.

NOTE: no ``from __future__ import annotations`` -- FastAPI reads parameter types
from evaluated annotations.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, RoleSvc, require
from app.schemas.common import APIErrorResponse, APIResponse, MessageData, Page
from app.schemas.rbac import (
    PermissionGroupRead,
    RoleCreate,
    RoleListParams,
    RoleRead,
    RoleUpdate,
    UserRoleAssign,
    UserRoleRead,
)

router = APIRouter(prefix="/roles", tags=["Roles & Permissions"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_403_FORBIDDEN: {"model": APIErrorResponse, "description": "Not permitted."},
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such record."},
    status.HTTP_409_CONFLICT: {"model": APIErrorResponse, "description": "A rule was violated."},
}


@router.get(
    "/permissions",
    dependencies=[require("roles:view")],
    response_model=APIResponse[list[PermissionGroupRead]],
    summary="The permission catalogue",
    description="Grouped as the role editor renders it: group, then module, then action.",
    responses=_ERRORS,
)
async def permission_catalogue(
    service: RoleSvc, current_user: CurrentUser
) -> APIResponse[list[PermissionGroupRead]]:
    del current_user
    groups = await service.catalogue()
    return APIResponse.ok([PermissionGroupRead.model_validate(group) for group in groups])


@router.post(
    "/permissions/reconcile",
    dependencies=[require("roles:update")],
    response_model=APIResponse[MessageData],
    summary="Reconcile the catalogue with the code registry",
    description=(
        "Adds any permission the application defines but the database lacks. Additive only: "
        "a permission no longer in the registry is reported, never deleted, because deleting "
        "it would silently strip it from every role that grants it."
    ),
    responses=_ERRORS,
)
async def reconcile(service: RoleSvc, current_user: CurrentUser) -> APIResponse[MessageData]:
    result = await service.reconcile_catalogue(actor_id=current_user.id)
    detail = f"Added {result['added']} permission(s); {result['stale']} stale row(s) left in place."
    return APIResponse.ok(MessageData(detail=detail), message=detail)


@router.get(
    "",
    dependencies=[require("roles:view")],
    response_model=APIResponse[Page[RoleRead]],
    summary="List roles",
    responses=_ERRORS,
)
async def list_roles(
    service: RoleSvc, current_user: CurrentUser, params: Annotated[RoleListParams, Query()]
) -> APIResponse[Page[RoleRead]]:
    del current_user
    rows, total = await service.list_roles(params)
    return APIResponse.ok(
        Page.create(
            [RoleRead.model_validate(row) for row in rows],
            page=params.page,
            page_size=params.page_size,
            total_items=total,
        )
    )


@router.post(
    "",
    dependencies=[require("roles:create")],
    response_model=APIResponse[RoleRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom role",
    responses=_ERRORS,
)
async def create_role(
    payload: RoleCreate, service: RoleSvc, current_user: CurrentUser
) -> APIResponse[RoleRead]:
    role = await service.create_role(payload, actor_id=current_user.id)
    return APIResponse.ok(RoleRead.model_validate(role), message="Role created successfully")


@router.get(
    "/{role_id}",
    dependencies=[require("roles:view")],
    response_model=APIResponse[RoleRead],
    summary="Get a role",
    responses=_ERRORS,
)
async def get_role(role_id: uuid.UUID, service: RoleSvc, current_user: CurrentUser) -> APIResponse[RoleRead]:
    del current_user
    return APIResponse.ok(RoleRead.model_validate(await service.get_role(role_id)))


@router.patch(
    "/{role_id}",
    dependencies=[require("roles:update")],
    response_model=APIResponse[RoleRead],
    summary="Update a role",
    description=(
        "A system role's permissions can be changed but its name cannot: the seeder "
        "reconciles system roles on every deployment, and a renamed one would reappear "
        "alongside its replacement. Sending `permissions` replaces the whole set."
    ),
    responses=_ERRORS,
)
async def update_role(
    role_id: uuid.UUID, payload: RoleUpdate, service: RoleSvc, current_user: CurrentUser
) -> APIResponse[RoleRead]:
    role = await service.update_role(role_id, payload, actor_id=current_user.id)
    return APIResponse.ok(RoleRead.model_validate(role), message="Role updated successfully")


@router.delete(
    "/{role_id}",
    dependencies=[require("roles:delete")],
    response_model=APIResponse[MessageData],
    summary="Delete a custom role",
    description="Refused while anybody still holds it, and refused outright for system roles.",
    responses=_ERRORS,
)
async def delete_role(
    role_id: uuid.UUID, service: RoleSvc, current_user: CurrentUser
) -> APIResponse[MessageData]:
    await service.delete_role(role_id, actor_id=current_user.id)
    return APIResponse.ok(MessageData(detail="Role deleted."), message="Role deleted successfully")


# ----------------------------------------------------------------------
# Assignment
# ----------------------------------------------------------------------
assignment_router = APIRouter(prefix="/users", tags=["Roles & Permissions"])


@assignment_router.get(
    "/{user_id}/roles",
    dependencies=[require("roles:view")],
    response_model=APIResponse[UserRoleRead],
    summary="Roles held by a user",
    responses=_ERRORS,
)
async def user_roles(
    user_id: uuid.UUID, service: RoleSvc, current_user: CurrentUser
) -> APIResponse[UserRoleRead]:
    del current_user
    return APIResponse.ok(UserRoleRead.model_validate(await service.roles_for_user(user_id)))


@assignment_router.put(
    "/{user_id}/roles",
    dependencies=[require("roles:update")],
    response_model=APIResponse[UserRoleRead],
    summary="Set the roles a user holds",
    description=(
        "Replaces the whole set. Refused when it would remove the last Super Admin, "
        "which would leave nobody able to undo it."
    ),
    responses=_ERRORS,
)
async def set_user_roles(
    user_id: uuid.UUID, payload: UserRoleAssign, service: RoleSvc, current_user: CurrentUser
) -> APIResponse[UserRoleRead]:
    result = await service.assign_roles(user_id, payload, actor_id=current_user.id)
    return APIResponse.ok(UserRoleRead.model_validate(result), message="Roles updated successfully")
