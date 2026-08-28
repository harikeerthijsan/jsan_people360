"""Persistence for roles, permissions and assignments."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.repositories.base import BaseRepository
from app.schemas.rbac import RoleListParams
from app.utils.datetime import utc_now


class PermissionRepository(BaseRepository[Permission]):
    model = Permission

    async def all_ordered(self) -> Sequence[Permission]:
        stmt = self._base_select().order_by(Permission.permission_group, Permission.module, Permission.action)
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def by_codes(self, codes: Sequence[str]) -> Sequence[Permission]:
        if not codes:
            return []
        stmt = self._base_select().where(Permission.code.in_(list(codes)))
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def existing_codes(self) -> set[str]:
        return set((await self.session.execute(select(Permission.code))).scalars().all())


class RoleRepository(BaseRepository[Role]):
    model = Role

    def _with_permissions(self) -> Select[tuple[Role]]:
        return self._base_select().options(
            selectinload(Role.permissions).selectinload(RolePermission.permission)
        )

    async def detailed(self, role_id: uuid.UUID) -> Role | None:
        # ``populate_existing`` because the role is usually already in the
        # identity map with its grants loaded -- from the read that preceded the
        # edit. Without it SQLAlchemy hands back that stale collection and the
        # response shows the permissions the role had before it was saved.
        stmt = self._with_permissions().where(Role.id == role_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def find_by_key(self, key: str) -> Role | None:
        stmt = self._base_select().where(func.lower(Role.key) == key.strip().lower())
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def find_by_name(self, name: str) -> Role | None:
        stmt = self._base_select().where(func.lower(Role.name) == name.strip().lower())
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def search(self, params: RoleListParams) -> tuple[Sequence[Role], int]:
        stmt = self._with_permissions()
        if getattr(params, "search", None):
            term = f"%{params.search}%"
            stmt = stmt.where(or_(Role.name.ilike(term), Role.key.ilike(term)))
        if getattr(params, "status", None):
            stmt = stmt.where(Role.status == params.status)
        if getattr(params, "is_system", None) is not None:
            stmt = stmt.where(Role.is_system.is_(params.is_system))

        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(Role.is_system.desc(), Role.name)
                    .offset(params.offset)
                    .limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def holder_counts(self, role_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        """How many accounts hold each role, in one query rather than N."""
        if not role_ids:
            return {}
        stmt = (
            select(UserRole.role_id, func.count(func.distinct(UserRole.user_id)))
            .where(UserRole.role_id.in_(list(role_ids)), UserRole.deleted_at.is_(None))
            .group_by(UserRole.role_id)
        )
        return {row[0]: int(row[1]) for row in (await self.session.execute(stmt)).all()}


class RolePermissionRepository(BaseRepository[RolePermission]):
    model = RolePermission

    async def replace(
        self, role_id: uuid.UUID, permission_ids: Sequence[uuid.UUID], *, actor_id: uuid.UUID | None
    ) -> None:
        """Set the role's grants to exactly this list.

        Deleted and recreated rather than diffed: the set is small, and a diff
        that goes wrong leaves a role granting something nobody chose.
        """
        existing = (
            (await self.session.execute(select(RolePermission).where(RolePermission.role_id == role_id)))
            .scalars()
            .all()
        )
        for row in existing:
            await self.session.delete(row)
        await self.session.flush()

        for permission_id in permission_ids:
            self.session.add(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        await self.session.flush()


class UserRoleRepository(BaseRepository[UserRole]):
    model = UserRole

    async def for_user(self, user_id: uuid.UUID) -> Sequence[UserRole]:
        stmt = self._base_select().where(UserRole.user_id == user_id)
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def replace(
        self, user_id: uuid.UUID, role_ids: Sequence[uuid.UUID], *, actor_id: uuid.UUID | None
    ) -> None:
        existing = (
            (await self.session.execute(select(UserRole).where(UserRole.user_id == user_id))).scalars().all()
        )
        for row in existing:
            await self.session.delete(row)
        await self.session.flush()

        for role_id in dict.fromkeys(role_ids):
            self.session.add(
                UserRole(
                    user_id=user_id,
                    role_id=role_id,
                    granted_at=utc_now(),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        await self.session.flush()

    async def count_for_role(self, role_id: uuid.UUID) -> int:
        return await self.count(UserRole.role_id == role_id)
