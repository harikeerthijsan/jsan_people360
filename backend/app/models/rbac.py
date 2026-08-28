"""Roles, permissions and who holds what.

Two shape decisions are worth stating.

**Permissions are a mirror, not a source.** The rows in ``permissions`` are
reconciled from ``app.core.permissions`` by the seeder. They exist as a table so
that ``role_permissions`` can carry a foreign key and the database can refuse a
grant to something that does not exist -- not so that anybody can add one.

**A user holds roles, not permissions.** There is no user-permission table. A
one-off grant is invisible on the roles screen, survives every audit unnoticed,
and is exactly how an access model rots. If somebody needs a different set, that
set is a role.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase


class Permission(Base, AuditableBase):
    """One thing that may be done to one module.

    ``code`` is the wire format (``employees:view``) and is what a guard, a
    token claim and a React prop all carry.
    """

    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("code", name="uq_permissions_code"),
        Index("ix_permissions_group_module", "permission_group", "module"),
        {"comment": "The permission catalogue, reconciled from app.core.permissions."},
    )

    code: Mapped[str] = mapped_column(String(80), index=True, doc="e.g. employees:view")
    module: Mapped[str] = mapped_column(String(40), index=True)
    action: Mapped[str] = mapped_column(String(40))
    permission_group: Mapped[str] = mapped_column(String(30), index=True)
    label: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"


class Role(Base, AuditableBase):
    """A named set of permissions.

    ``is_system`` marks the nine roles that ship with the product. They may be
    granted and revoked freely but not renamed or deleted: the seeder reconciles
    them on every deployment, and a renamed system role would silently reappear
    alongside its replacement.
    """

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("key", name="uq_roles_key"),
        CheckConstraint("char_length(trim(name)) > 0", name="name_not_blank"),
        {"comment": "System and custom roles."},
    )

    key: Mapped[str] = mapped_column(String(50), index=True, doc="Stable identifier, e.g. hr_admin.")
    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        index=True,
        doc="Shipped with the product; reconciled by the seeder and not deletable.",
    )
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", index=True)

    permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Role {self.key}>"


class RolePermission(Base, AuditableBase):
    """A grant. Deleted and recreated wholesale when a role is edited."""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_pair"),
        {"comment": "Which permissions a role grants."},
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), index=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), index=True
    )

    role: Mapped[Role] = relationship(back_populates="permissions")
    permission: Mapped[Permission] = relationship(lazy="joined")


class UserRole(Base, AuditableBase):
    """Who holds a role.

    Multiple roles per user are supported and their permissions union: somebody
    can be both a Manager and a Recruiter without inventing a ninth role for the
    combination.

    ``scope_business_unit_id`` is carried but not yet enforced. It is the seam
    for department-scoped access -- "approve leave, but only for this business
    unit" -- and storing it now means turning that on later is a change to the
    resolver rather than a migration against live grants.
    """

    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "scope_business_unit_id", name="uq_user_roles_grant"),
        # PostgreSQL treats NULLs as distinct in a unique constraint, so the
        # constraint above does *not* stop the same unscoped role being granted
        # to the same user twice. A partial index covers the NULL case, which is
        # the common one.
        Index(
            "uq_user_roles_unscoped",
            "user_id",
            "role_id",
            unique=True,
            postgresql_where=text("scope_business_unit_id IS NULL"),
        ),
        Index("ix_user_roles_user_role", "user_id", "role_id"),
        {"comment": "Role assignments, optionally scoped to a business unit."},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), index=True
    )
    scope_business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_units.id", ondelete="CASCADE"),
        index=True,
        doc="Reserved for department-scoped access; not yet enforced.",
    )
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    role: Mapped[Role] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return f"<UserRole user={self.user_id} role={self.role_id}>"
