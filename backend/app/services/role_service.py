"""Managing roles and who holds them.

Three rules protect the system from itself.

**A system role cannot be renamed or deleted.** The seeder reconciles the eight
shipped roles on every deployment, so a renamed one would silently reappear
alongside its replacement. Their *permissions* can be edited freely -- what "HR
Executive" means is a policy decision, and it is a company's to make.

**A role in use cannot be deleted.** Deleting one would strip access from
everybody holding it, and the person doing the deleting cannot see who that is
from the confirmation dialog. Revoke it or deactivate it instead.

**The last Super Admin cannot be demoted.** Not paranoia: role editing is itself
behind ``roles:update``, so an administrator who removes their own last
administrative role locks the door from the inside with the key still in it.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.permissions import (
    ALL_PERMISSIONS,
    GROUP_LABELS,
    MODULES,
    PermissionGroup,
    action_label,
)
from app.models.audit_log import AuditAction
from app.models.enums import RecordStatus
from app.models.rbac import Role
from app.repositories.rbac_repository import (
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
    UserRoleRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas.rbac import RoleCreate, RoleListParams, RoleUpdate, UserRoleAssign
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthorizationService

logger = get_logger("services.roles")

SUPER_ADMIN_KEY = "super_admin"


def _slug(name: str) -> str:
    """A stable key derived from the name, since custom roles are named, not keyed."""
    key = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return key[:50] or "role"


class RoleService:
    def __init__(
        self,
        roles: RoleRepository,
        permissions: PermissionRepository,
        grants: RolePermissionRepository,
        assignments: UserRoleRepository,
        users: UserRepository,
        authorization: AuthorizationService,
        audit: AuditService,
    ) -> None:
        self.roles = roles
        self.permissions = permissions
        self.grants = grants
        self.assignments = assignments
        self.users = users
        self.authorization = authorization
        self.audit = audit

    # ==================================================================
    # Catalogue
    # ==================================================================
    async def catalogue(self) -> list[dict[str, Any]]:
        """The permission list, grouped the way the role screen renders it."""
        stored = {row.code: row for row in await self.permissions.all_ordered()}
        groups: list[dict[str, Any]] = []

        for group in PermissionGroup:
            modules = []
            for module in MODULES:
                if module.group is not group:
                    continue
                codes = [f"{module.key}:{action.value}" for action in module.actions]
                rows = [stored[permission_code] for permission_code in codes if permission_code in stored]
                if rows:
                    modules.append(
                        {
                            "module": module.key,
                            "label": module.label,
                            "description": module.description,
                            "permissions": rows,
                        }
                    )
            if modules:
                groups.append({"group": group.value, "label": GROUP_LABELS[group], "modules": modules})
        return groups

    # ==================================================================
    # Roles
    # ==================================================================
    async def list_roles(self, params: RoleListParams) -> tuple[list[dict[str, Any]], int]:
        rows, total = await self.roles.search(params)
        counts = await self.roles.holder_counts([role.id for role in rows])
        return [self._present(role, counts.get(role.id, 0)) for role in rows], total

    async def get_role(self, role_id: uuid.UUID) -> dict[str, Any]:
        role = await self.roles.detailed(role_id)
        if role is None:
            raise NotFoundError("Role")
        return self._present(role, await self.assignments.count_for_role(role.id))

    async def create_role(self, payload: RoleCreate, *, actor_id: uuid.UUID | None = None) -> dict[str, Any]:
        if await self.roles.find_by_name(payload.name) is not None:
            raise ConflictError(
                f'A role called "{payload.name}" already exists.', error_code="duplicate_role"
            )

        key = _slug(payload.name)
        if await self.roles.find_by_key(key) is not None:
            key = f"{key}_{uuid.uuid4().hex[:6]}"

        role = await self.roles.add(
            Role(
                key=key,
                name=payload.name.strip(),
                description=payload.description,
                is_system=False,
                status=RecordStatus.ACTIVE.value,
            ),
            actor_id=actor_id,
        )
        await self._set_permissions(role.id, payload.permissions, actor_id=actor_id)

        await self.audit.record_success(
            AuditAction.ROLE_CREATED,
            actor_id=actor_id,
            entity_type="role",
            entity_id=role.id,
            description=f"Created role {role.name}",
            context={"permissions": len(payload.permissions)},
        )
        return await self.get_role(role.id)

    async def update_role(
        self, role_id: uuid.UUID, payload: RoleUpdate, *, actor_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        role = await self.roles.detailed(role_id)
        if role is None:
            raise NotFoundError("Role")

        changes = payload.model_dump(exclude_unset=True, exclude={"permissions"})

        if role.is_system and "name" in changes and changes["name"] != role.name:
            raise ConflictError(
                "A system role cannot be renamed. Its permissions can still be changed.",
                error_code="system_role_immutable",
            )
        if role.is_system and changes.get("status") == RecordStatus.INACTIVE.value:
            raise ConflictError(
                "A system role cannot be deactivated. Revoke it from the people who hold it instead.",
                error_code="system_role_immutable",
            )
        if "name" in changes:
            clash = await self.roles.find_by_name(changes["name"])
            if clash is not None and clash.id != role.id:
                raise ConflictError(
                    f'A role called "{changes["name"]}" already exists.', error_code="duplicate_role"
                )

        if payload.permissions is not None:
            await self._assert_super_admin_survives(role, payload.permissions)
            await self._set_permissions(role.id, payload.permissions, actor_id=actor_id)

        if changes:
            await self.roles.update(role, changes, actor_id=actor_id)

        await self.audit.record_success(
            AuditAction.ROLE_UPDATED,
            actor_id=actor_id,
            entity_type="role",
            entity_id=role.id,
            description=f"Updated role {role.name}",
            context={"fields": sorted(changes), "permissions_replaced": payload.permissions is not None},
        )
        return await self.get_role(role.id)

    async def delete_role(self, role_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> None:
        role = await self.roles.get(role_id)
        if role is None:
            raise NotFoundError("Role")
        if role.is_system:
            raise ConflictError(
                "A system role cannot be deleted. Deactivate it or revoke it instead.",
                error_code="system_role_immutable",
            )

        holders = await self.assignments.count_for_role(role.id)
        if holders:
            raise ConflictError(
                f"{holders} account(s) still hold this role. Revoke it from them first.",
                error_code="role_in_use",
            )

        await self.roles.soft_delete(role, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.ROLE_DELETED,
            actor_id=actor_id,
            entity_type="role",
            entity_id=role.id,
            description=f"Deleted role {role.name}",
        )

    # ==================================================================
    # Assignment
    # ==================================================================
    async def roles_for_user(self, user_id: uuid.UUID) -> dict[str, Any]:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User")
        roles = await self.authorization.roles_for(user)
        return {
            "user_id": user.id,
            "roles": roles,
            "permissions": sorted(await self.authorization.permissions_for(user)),
        }

    async def assign_roles(
        self, user_id: uuid.UUID, payload: UserRoleAssign, *, actor_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User")

        wanted: list[uuid.UUID] = []
        for role_id in payload.role_ids:
            role = await self.roles.get(role_id)
            if role is None:
                raise ValidationError("One of the selected roles does not exist.", error_code="invalid_role")
            if role.status != RecordStatus.ACTIVE.value:
                raise ConflictError(
                    f'"{role.name}" is inactive and cannot be granted.', error_code="inactive_role"
                )
            wanted.append(role.id)

        await self._assert_not_last_super_admin(user_id, wanted)
        await self.assignments.replace(user_id, wanted, actor_id=actor_id)

        await self.audit.record_success(
            AuditAction.USER_ROLES_ASSIGNED,
            actor_id=actor_id,
            entity_type="user",
            entity_id=user.id,
            description=f"Set roles for {user.email}",
            context={"role_count": len(wanted)},
        )
        return await self.roles_for_user(user_id)

    # ==================================================================
    # Internals
    # ==================================================================
    async def _set_permissions(
        self, role_id: uuid.UUID, codes: Sequence[str], *, actor_id: uuid.UUID | None
    ) -> None:
        rows = await self.permissions.by_codes(list(codes))
        found = {row.code for row in rows}
        missing = sorted(set(codes) - found)
        if missing:
            # The schema already checked these against the registry, so reaching
            # here means the catalogue table has drifted from the code.
            raise ConflictError(
                "The permission catalogue is out of date; run the migrations.",
                error_code="permission_catalogue_stale",
                details=[{"code": "missing_permission", "message": item} for item in missing],
            )
        await self.grants.replace(role_id, [row.id for row in rows], actor_id=actor_id)

    async def _assert_super_admin_survives(self, role: Role, codes: Sequence[str]) -> None:
        """Super Admin must keep the permissions that let it fix a mistake."""
        if role.key != SUPER_ADMIN_KEY:
            return
        required = {"roles:view", "roles:update"}
        if not required.issubset(set(codes)):
            raise ConflictError(
                "Super Admin must keep the ability to view and edit roles, or nobody "
                "could undo this change.",
                error_code="would_lock_out",
            )

    async def _assert_not_last_super_admin(self, user_id: uuid.UUID, wanted: Sequence[uuid.UUID]) -> None:
        super_admin = await self.roles.find_by_key(SUPER_ADMIN_KEY)
        if super_admin is None or super_admin.id in wanted:
            return

        held = {row.role_id for row in await self.assignments.for_user(user_id)}
        if super_admin.id not in held:
            return

        # They are losing it. Somebody else must still have it.
        remaining = await self.assignments.count_for_role(super_admin.id)
        if remaining <= 1:
            raise ConflictError(
                "This is the last account with Super Admin. Grant it to somebody else first.",
                error_code="last_super_admin",
            )

    @staticmethod
    def _present(role: Role, user_count: int) -> dict[str, Any]:
        return {
            "id": role.id,
            "key": role.key,
            "name": role.name,
            "description": role.description,
            "is_system": role.is_system,
            "status": role.status,
            "created_at": role.created_at,
            "permissions": sorted(
                grant.permission.code for grant in role.permissions if grant.permission is not None
            ),
            "user_count": user_count,
        }

    async def reconcile_catalogue(self, *, actor_id: uuid.UUID | None = None) -> dict[str, int]:
        """Bring the permissions table back in line with the code registry.

        Exposed so a deployment that adds a module does not need a migration to
        make its permissions grantable. Additive only: a permission that has
        disappeared from the registry is left alone rather than deleted, because
        deleting it would silently strip it from every role that grants it.
        """
        existing = await self.permissions.existing_codes()
        missing = sorted(ALL_PERMISSIONS - existing)
        stale = sorted(existing - ALL_PERMISSIONS)

        from app.models.rbac import Permission

        for module in MODULES:
            for action in module.actions:
                permission_code = f"{module.key}:{action.value}"
                if permission_code not in missing:
                    continue
                await self.permissions.add(
                    Permission(
                        code=permission_code,
                        module=module.key,
                        action=action.value,
                        permission_group=module.group.value,
                        label=action_label(action, module.label),
                        description=module.description,
                    ),
                    actor_id=actor_id,
                )

        if stale:
            logger.warning(
                "permission_catalogue_has_stale_rows",
                extra={"count": len(stale), "codes": stale},
            )
        return {"added": len(missing), "stale": len(stale)}
