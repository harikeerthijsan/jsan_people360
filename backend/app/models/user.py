"""User account model.

This one table serves two purposes and will serve a third:

* the **authentication principal** (credentials, lockout, sessions), which is
  what Phase 1 established;
* the **user directory record** (identity, contact details, organizational
  placement), added by the User Management module;
* later, the anchor an ``employees`` row will hang off.

Keeping them in one table -- rather than adding a parallel "profile" table --
means there is exactly one row per person, one id for other modules to
reference, and no chance of the two drifting apart.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.enums import GENDER_SQL_VALUES
from app.models.mixins import unique_ci

if TYPE_CHECKING:
    from app.models.business_unit import BusinessUnit
    from app.models.designation import Designation
    from app.models.employment_type import EmploymentType
    from app.models.grade import Grade
    from app.models.location import Location
    from app.models.refresh_token import RefreshToken
    from app.models.team import Team

#: Generates USR-000001, USR-000002, ... in the database itself.
#:
#: A sequence rather than ``SELECT max(...) + 1``: two concurrent creates would
#: read the same maximum and produce the same code, and the unique index would
#: then reject one of them for a reason the user cannot act on.
USER_CODE_SEQUENCE = "users_user_code_seq"
USER_CODE_DEFAULT = f"'USR-' || lpad(nextval('{USER_CODE_SEQUENCE}')::text, 6, '0')"


class User(Base, AuditableBase):
    """An authenticated principal and directory record of the platform.

    Written in Phase 1 before the role model existed; RBAC arrived in Phase 15
    and every administrative route now carries a permission guard. What this
    class deliberately still does not carry is the permissions themselves --
    roles are data, resolved per request by the authorization service.
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_is_active_deleted_at", "is_active", "deleted_at"),
        Index("ix_users_name", "first_name", "last_name"),
        # Usernames are compared case-insensitively, so "J.Doe" and "j.doe" are
        # the same handle rather than two accounts a phisher could exploit.
        # Email needs no equivalent: it is lower-cased before it is stored.
        unique_ci("uq_users_username_lower", "username"),
        CheckConstraint(f"gender IS NULL OR gender IN ({GENDER_SQL_VALUES})", name="gender"),
        {"comment": "Authenticated principals and directory records of the platform."},
    )

    # -- Identity -----------------------------------------------------
    user_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        index=True,
        server_default=text(USER_CODE_DEFAULT),
        doc="System-generated staff identifier (USR-000001). Never editable.",
    )
    username: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Unique sign-in handle. Compared case-insensitively.",
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        unique=True,
        index=True,
        doc="Official email address. Normalised to lower case; also a sign-in identifier.",
    )
    personal_email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
        doc="Optional personal address, used for offboarding correspondence.",
    )
    phone_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True, doc="Mobile number, stored in E.164-ish form."
    )
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True, doc="Profile photo URL.")

    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)

    # -- Organizational placement --------------------------------------
    #
    # All nullable, and all ON DELETE RESTRICT.
    #
    # Nullable because a user can legitimately exist before the org tree does --
    # the bootstrap administrator is created against an empty database, and
    # requiring a business unit would make the first sign-in impossible.
    #
    # RESTRICT because master records are archived, never deleted; a hard delete
    # that silently unassigned every user is not a recovery path.
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_units.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    designation_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("designations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    grade_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("grades.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    employment_type_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employment_types.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    joining_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # -- Credentials --------------------------------------------------
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    force_password_change: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        doc="Set after an administrator reset; the client must collect a new password.",
    )

    password_reset_token_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        doc="SHA-256 digest of the outstanding password reset token, if any.",
    )
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # -- Status -------------------------------------------------------
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        doc=(
            "The permission-check bypass: a superuser passes every require() and "
            "every scope. Enforced in the authorization service; grant it to almost nobody."
        ),
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # -- Sign-in telemetry / lockout ----------------------------------
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # -- Relationships -------------------------------------------------
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="RefreshToken.user_id",
        lazy="selectin",
    )

    # Eager-loaded because the user list and profile always display the names,
    # not the ids. Lazy loading them would be an N+1 per row.
    business_unit: Mapped[BusinessUnit | None] = relationship(foreign_keys=[business_unit_id], lazy="joined")
    team: Mapped[Team | None] = relationship(foreign_keys=[team_id], lazy="joined")
    designation: Mapped[Designation | None] = relationship(foreign_keys=[designation_id], lazy="joined")
    grade: Mapped[Grade | None] = relationship(foreign_keys=[grade_id], lazy="joined")
    location: Mapped[Location | None] = relationship(foreign_keys=[location_id], lazy="joined")
    employment_type: Mapped[EmploymentType | None] = relationship(
        foreign_keys=[employment_type_id], lazy="joined"
    )

    # -- Behaviour ----------------------------------------------------
    @property
    def full_name(self) -> str:
        """Display name, derived rather than stored.

        Storing it alongside the parts would let the two disagree the first time
        someone edits only their surname.
        """
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def initials(self) -> str:
        return f"{self.first_name[:1]}{self.last_name[:1]}".upper()

    @property
    def is_locked(self) -> bool:
        """``True`` while the account is inside a failed-login lockout window."""
        if self.locked_until is None:
            return False
        return self.locked_until > datetime.now(UTC)

    @property
    def can_authenticate(self) -> bool:
        return self.is_active and not self.is_deleted and not self.is_locked

    def has_valid_reset_token(self, at: datetime | None = None) -> bool:
        if not self.password_reset_token_hash or not self.password_reset_expires_at:
            return False
        return self.password_reset_expires_at > (at or datetime.now(UTC))

    def clear_password_reset(self) -> None:
        self.password_reset_token_hash = None
        self.password_reset_expires_at = None

    def __repr__(self) -> str:
        return f"<User id={self.id} code={self.user_code!r} email={self.email!r}>"
