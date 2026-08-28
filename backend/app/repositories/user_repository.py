"""Persistence operations for :class:`app.models.user.User`."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.db.base_class import Base
from app.models.business_unit import BusinessUnit
from app.models.designation import Designation
from app.models.employment_type import EmploymentType
from app.models.enums import RecordStatus
from app.models.grade import Grade
from app.models.location import Location
from app.models.team import Team
from app.models.user import User
from app.repositories.base import BaseRepository
from app.repositories.master_repository import LIKE_ESCAPE, escape_like
from app.schemas.user import UserListParams
from app.utils.strings import normalise_email

#: The organizational references a user carries, and the label used when one of
#: them is rejected. Declared once so the checks and the messages cannot drift.
ORG_REFERENCE_MODELS: dict[str, tuple[type[Base], str]] = {
    "business_unit_id": (BusinessUnit, "business unit"),
    "team_id": (Team, "team"),
    "designation_id": (Designation, "designation"),
    "grade_id": (Grade, "grade"),
    "location_id": (Location, "location"),
    "employment_type_id": (EmploymentType, "employment type"),
}


class UserRepository(BaseRepository[User]):
    """Queries scoped to user accounts."""

    model = User

    #: Columns a free-text search covers. Deliberately includes the identifiers
    #: an administrator is most likely to be handed by someone else -- a staff
    #: code from a ticket, a username from a support call.
    searchable_fields: tuple[str, ...] = (
        "user_code",
        "username",
        "first_name",
        "last_name",
        "email",
        "personal_email",
        "phone_number",
    )

    #: Columns a client may sort by. Anything else is rejected by the service
    #: rather than passed through to SQL.
    sortable_fields: frozenset[str] = frozenset(
        {
            "user_code",
            "username",
            "first_name",
            "last_name",
            "email",
            "created_at",
            "updated_at",
            "last_login_at",
            "joining_date",
        }
    )

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    async def get_by_email(self, email: str, *, include_deleted: bool = False) -> User | None:
        """Look up an account by its normalised official email address."""
        stmt = self._base_select(include_deleted=include_deleted).where(User.email == normalise_email(email))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_username(self, username: str, *, include_deleted: bool = False) -> User | None:
        """Look up an account by username, compared case-insensitively."""
        stmt = self._base_select(include_deleted=include_deleted).where(
            func.lower(User.username) == username.lower()
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_reset_token_hash(self, token_hash: str) -> User | None:
        """Resolve the account holding an outstanding password reset token."""
        stmt = self._base_select().where(User.password_reset_token_hash == token_hash)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_with_relationships(self, user_id: uuid.UUID) -> User | None:
        """Re-read a user with the organizational relationships populated.

        Needed after a write: a freshly constructed row has ``business_unit_id``
        set but no ``business_unit`` object, and serialising it would lazy-load under
        asyncio. ``populate_existing`` also refreshes a reference that the write
        just changed, which would otherwise still hold the previous record.
        """
        stmt = select(User).where(User.id == user_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalars().unique().first()

    # ------------------------------------------------------------------
    # Uniqueness
    # ------------------------------------------------------------------
    async def find_email_owner(self, email: str, *, exclude_id: uuid.UUID | None = None) -> User | None:
        """Find any account using this official email, archived rows included.

        Archived accounts still hold their address -- the unique index covers
        every row -- so the service can tell the user to restore rather than
        leaving the database to raise an opaque integrity error.
        """
        stmt = select(User).where(User.email == normalise_email(email))
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def find_username_owner(self, username: str, *, exclude_id: uuid.UUID | None = None) -> User | None:
        """Find any account using this username, archived rows included."""
        stmt = select(User).where(func.lower(User.username) == username.lower())
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        return (await self.session.execute(stmt)).scalars().first()

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------
    def _scoped_select(self, *, archived: bool) -> Select[tuple[User]]:
        """Select either the live accounts or the archived ones, never both."""
        stmt = select(User)
        return stmt.where(User.deleted_at.is_not(None) if archived else User.deleted_at.is_(None))

    def _search_criteria(self, term: str) -> ColumnElement[bool]:
        """Case-insensitive OR across the searchable columns.

        Also matches the full name, so searching "Jane Doe" finds a row whose
        parts are stored separately -- the single most obvious thing to type,
        and the one a naive per-column search misses.
        """
        pattern = f"%{escape_like(term)}%"
        clauses: list[ColumnElement[bool]] = [
            getattr(User, field).ilike(pattern, escape=LIKE_ESCAPE)
            for field in self.searchable_fields
            if hasattr(User, field)
        ]
        clauses.append((User.first_name + " " + User.last_name).ilike(pattern, escape=LIKE_ESCAPE))
        return or_(*clauses)

    def _filters(self, params: UserListParams) -> list[ColumnElement[bool]]:
        criteria: list[ColumnElement[bool]] = []

        if params.search:
            criteria.append(self._search_criteria(params.search))

        # `status` is presented to clients as active/inactive for consistency
        # with the master-data screens; the column behind it is a boolean.
        if params.status is not None:
            criteria.append(User.is_active.is_(params.status is RecordStatus.ACTIVE))

        for field in ("business_unit_id", "designation_id", "location_id"):
            value = getattr(params, field)
            if value is not None:
                criteria.append(getattr(User, field) == value)

        return criteria

    async def list_page(self, params: UserListParams) -> tuple[Sequence[User], int]:
        """Return one page of accounts and the total number of matches."""
        base = self._scoped_select(archived=params.archived).where(*self._filters(params))

        count_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        column = getattr(User, params.sort_by)
        ordered = base.order_by(column.desc() if params.descending else column.asc()).order_by(User.id)

        page_stmt = ordered.offset(params.offset).limit(params.page_size)
        rows = (await self.session.execute(page_stmt)).scalars().unique().all()
        return rows, total

    async def find_unusable_org_references(self, data: dict[str, uuid.UUID | None]) -> list[str]:
        """Names of organizational references that cannot be assigned.

        A reference is usable only when the master record exists, is live and is
        active -- the same rule the master module applies to its own parents.
        Checking here keeps the SQL in the repository while letting the service
        report every bad field at once rather than one per round trip.
        """
        invalid: list[str] = []

        for field, (model, label) in ORG_REFERENCE_MODELS.items():
            value = data.get(field)
            if value is None:
                continue

            related: Any = model
            stmt = (
                select(func.count())
                .select_from(related)
                .where(
                    related.id == value,
                    related.deleted_at.is_(None),
                    related.status == RecordStatus.ACTIVE.value,
                )
            )
            if int((await self.session.execute(stmt)).scalar_one()) == 0:
                invalid.append(label)

        return invalid

    async def count_active(self) -> int:
        """Live, active accounts. Used to protect the last one standing."""
        stmt = (
            select(func.count()).select_from(User).where(User.deleted_at.is_(None), User.is_active.is_(True))
        )
        return int((await self.session.execute(stmt)).scalar_one())
