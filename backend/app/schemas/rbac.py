"""Schemas for roles, permissions and the session payload."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.permissions import ALL_PERMISSIONS
from app.schemas.common import PaginationParams
from app.schemas.user import UserRead

READ_CONFIG = ConfigDict(from_attributes=True)


class PermissionRead(BaseModel):
    model_config = READ_CONFIG

    id: uuid.UUID
    code: str
    module: str
    action: str
    permission_group: str
    label: str
    description: str | None


class PermissionGroupRead(BaseModel):
    """The catalogue as the role screen renders it: grouped, then by module."""

    group: str
    label: str
    modules: list[ModulePermissions]


class ModulePermissions(BaseModel):
    module: str
    label: str
    description: str
    permissions: list[PermissionRead]


class RoleSummary(BaseModel):
    model_config = READ_CONFIG

    id: uuid.UUID
    key: str
    name: str
    is_system: bool
    status: str


class RoleRead(RoleSummary):
    description: str | None
    created_at: datetime
    #: Flattened to codes rather than nested join rows: every consumer -- the
    #: edit form, the diff on save, the React guard -- wants the set, not the
    #: association objects.
    permissions: list[str] = []
    #: How many accounts hold this role, so deleting one is an informed choice.
    user_count: int = 0


def _known_permissions(codes: list[str]) -> list[str]:
    unknown = sorted(set(codes) - ALL_PERMISSIONS)
    if unknown:
        raise ValueError(f"Unknown permission(s): {', '.join(unknown)}")
    # Deduplicated and ordered so two identical grants cannot produce two
    # different-looking roles.
    return sorted(set(codes))


class RoleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    permissions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _permissions_exist(self) -> RoleCreate:
        self.permissions = _known_permissions(self.permissions)
        return self


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")
    #: ``None`` leaves the grants alone; a list replaces them wholesale. A role
    #: is edited as a set of checkboxes, and diffing them client-side would be a
    #: second source of truth for what the role grants.
    permissions: list[str] | None = None

    @model_validator(mode="after")
    def _permissions_exist(self) -> RoleUpdate:
        if self.permissions is not None:
            self.permissions = _known_permissions(self.permissions)
        return self


class RoleListParams(PaginationParams):
    search: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")
    is_system: bool | None = None


class UserRoleAssign(BaseModel):
    """Replaces the whole set of roles a user holds.

    Wholesale rather than add/remove, for the same reason a role's permissions
    are: the screen is a list of checkboxes, and two endpoints that each move one
    row make "what does this person hold?" a question with two answers.
    """

    model_config = ConfigDict(extra="forbid")

    role_ids: list[uuid.UUID] = Field(default_factory=list)


class UserRoleRead(BaseModel):
    model_config = READ_CONFIG

    user_id: uuid.UUID
    roles: list[RoleSummary]
    permissions: list[str]


class SessionRead(BaseModel):
    """What ``/auth/me`` answers.

    The permission list is sent with the profile rather than fetched separately,
    because the very first render already needs it -- the shell decides which
    navigation items exist -- and a second round trip would mean a visible flash
    of menu items the user cannot use.
    """

    user: UserRead
    roles: list[RoleSummary]
    permissions: list[str]
    is_superuser: bool


PermissionGroupRead.model_rebuild()
