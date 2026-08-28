"""Resolving what a signed-in user may do.

The rule is simple and worth keeping simple: **effective permissions are the
union of every active role the user holds.** There is no deny list and no
precedence order. Denies that override grants read well in a design document and
are impossible to reason about at three in the morning when somebody cannot
approve leave and nobody can say why.

``is_superuser`` short-circuits the whole thing. It predates RBAC, it is how the
first account bootstraps, and removing it would mean a bad grant could lock every
administrator out of the screen that fixes grants.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDeniedError
from app.core.logging import get_logger
from app.core.permissions import ALL_PERMISSIONS, PermissionAction, code
from app.db.session import detached_session_scope
from app.models.audit_log import AuditAction
from app.models.enums import RecordStatus
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.services.audit_service import AuditService

logger = get_logger("services.authorization")


class AuthorizationService:
    """Answers "may this user do that?" and nothing else."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def permissions_for(self, user: User) -> frozenset[str]:
        """Every permission code the user effectively holds.

        A superuser gets the whole catalogue rather than a wildcard token, so
        that everything downstream -- the API response, the React guard, the
        role screen -- reasons about one shape of data instead of two.
        """
        if user.is_superuser:
            return ALL_PERMISSIONS

        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user.id,
                UserRole.deleted_at.is_(None),
                Role.deleted_at.is_(None),
                # An inactive role stops granting immediately. Revoking access
                # by deactivating the role is the fastest lever an administrator
                # has, and it would be worthless if it only applied to new grants.
                Role.status == RecordStatus.ACTIVE.value,
                RolePermission.deleted_at.is_(None),
                Permission.deleted_at.is_(None),
            )
            .distinct()
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return frozenset(rows)

    async def roles_for(self, user: User) -> list[Role]:
        """The roles themselves, for display rather than for checking."""
        stmt = (
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user.id,
                UserRole.deleted_at.is_(None),
                Role.deleted_at.is_(None),
            )
            .order_by(Role.name)
            .distinct()
        )
        return list((await self._session.execute(stmt)).scalars().unique().all())

    async def has_permission(self, user: User, permission: str) -> bool:
        return permission in await self.permissions_for(user)

    async def assert_can(self, user: User, *permissions: str, require_all: bool = True) -> None:
        """Raise unless the user may proceed.

        ``require_all`` defaults to true because that is the safer reading of a
        list: an endpoint naming two permissions almost always needs both, and a
        guard that quietly settles for one of them is a hole nobody notices.
        """
        held = await self.permissions_for(user)
        satisfied = held.issuperset(permissions) if require_all else bool(held.intersection(permissions))
        if not satisfied:
            missing = sorted(set(permissions) - held)
            await self._record_denial(user, missing)
            # The missing codes are named. This is an internal HR system, and a
            # 403 that says only "denied" turns every access question into a
            # support ticket somebody has to reproduce.
            raise PermissionDeniedError(
                "You do not have permission to perform this action.",
                details=[{"code": "missing_permission", "message": item} for item in missing],
            )

    async def _record_denial(self, user: User, missing: list[str]) -> None:
        """Write the denial to the audit trail, in its own transaction.

        The refusal raised next rolls the request session back, so an entry
        written there would vanish with the request it describes. Recording
        never raises: a failure to write the trail must not turn a 403 into
        a 500.
        """
        try:
            async with detached_session_scope() as session:
                await AuditService(AuditLogRepository(session)).record_failure(
                    AuditAction.PERMISSION_DENIED,
                    actor_id=user.id,
                    actor_email=user.email,
                    context={"missing_permissions": missing},
                )
        except Exception:  # the trail must never break the refusal itself
            logger.error("Failed to record permission denial", exc_info=True)

    async def can_export(self, user: User, module: str) -> bool:
        return await self.has_permission(user, code(module, PermissionAction.EXPORT))

    async def user_ids_with_permission(self, permission: str) -> list[uuid.UUID]:
        """Who could act on this -- used to address a notification at the right people.

        Superusers are included: they hold everything, and a request that only
        they can approve is still their queue.
        """
        stmt = (
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                Permission.code == permission,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                UserRole.deleted_at.is_(None),
                Role.deleted_at.is_(None),
                Role.status == RecordStatus.ACTIVE.value,
            )
            .distinct()
        )
        holders = set((await self._session.execute(stmt)).scalars().all())

        supers = (
            (
                await self._session.execute(
                    select(User.id).where(
                        User.is_superuser.is_(True), User.is_active.is_(True), User.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        return sorted(holders.union(supers))
