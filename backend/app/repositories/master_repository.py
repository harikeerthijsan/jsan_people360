"""Shared repository for the organization master-data entities.

Adds the query patterns every master list screen needs -- paged search, status
filtering, live/archived scoping and case-insensitive uniqueness lookups -- on
top of :class:`app.repositories.base.BaseRepository`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import TypeVar

from sqlalchemy import Select, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.db.base_class import Base
from app.repositories.base import BaseRepository
from app.schemas.masters import MasterListParams

ModelType = TypeVar("ModelType", bound=Base)

#: Characters that would otherwise be treated as wildcards inside a LIKE
#: pattern. A user searching for "50%" must not match every row.
LIKE_ESCAPE = "\\"

#: Retained for readability inside this module.
_LIKE_ESCAPE = LIKE_ESCAPE


def escape_like(term: str) -> str:
    """Escape LIKE wildcards so a search term is matched literally."""
    return (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


class MasterRepository(BaseRepository[ModelType]):
    """Queries shared by every master-data entity."""

    #: Columns a free-text search looks at.
    searchable_fields: tuple[str, ...] = ("name", "description")

    #: Columns a client may sort by. Anything else is rejected by the service
    #: rather than passed through to SQL.
    sortable_fields: frozenset[str] = frozenset({"name", "status", "created_at", "updated_at"})

    #: Whether the entity has a ``code`` column subject to uniqueness.
    has_code: bool = False

    # ------------------------------------------------------------------
    # Scoping
    # ------------------------------------------------------------------
    def _scoped_select(self, *, archived: bool) -> Select[tuple[ModelType]]:
        """Select either the live records or the archived ones, never both."""
        stmt = select(self.model)
        deleted_at = self.model.deleted_at  # type: ignore[attr-defined]
        return stmt.where(deleted_at.is_not(None) if archived else deleted_at.is_(None))

    def _search_criteria(self, term: str) -> ColumnElement[bool]:
        """Case-insensitive OR across the searchable columns."""
        pattern = f"%{escape_like(term)}%"
        clauses = [
            getattr(self.model, field).ilike(pattern, escape=_LIKE_ESCAPE)
            for field in self.searchable_fields
            if hasattr(self.model, field)
        ]
        return or_(*clauses)

    def _apply_filters(
        self,
        stmt: Select[tuple[ModelType]],
        params: MasterListParams,
        extra: Sequence[ColumnElement[bool]],
    ) -> Select[tuple[ModelType]]:
        if params.search:
            stmt = stmt.where(self._search_criteria(params.search))
        if params.status is not None:
            stmt = stmt.where(self.model.status == params.status.value)  # type: ignore[attr-defined]
        if extra:
            stmt = stmt.where(*extra)
        return stmt

    # ------------------------------------------------------------------
    # Paged listing
    # ------------------------------------------------------------------
    async def list_page(
        self,
        params: MasterListParams,
        *extra_criteria: ColumnElement[bool],
    ) -> tuple[Sequence[ModelType], int]:
        """Return one page of results and the total number of matches.

        The count is issued against the same filters as the page so that
        pagination controls never disagree with the rows on screen.
        """
        base = self._scoped_select(archived=params.archived)
        filtered = self._apply_filters(base, params, extra_criteria)

        count_stmt = select(func.count()).select_from(filtered.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        ordered = self._apply_ordering(filtered, params.sort_by, params.descending)
        # A second, stable sort key keeps paging deterministic when the primary
        # key has duplicates (many records share a status, for example).
        ordered = ordered.order_by(self.model.id)  # type: ignore[attr-defined]

        page_stmt = ordered.offset(params.offset).limit(params.page_size)
        rows = (await self.session.execute(page_stmt)).scalars().unique().all()
        return rows, total

    # ------------------------------------------------------------------
    # Reloading
    # ------------------------------------------------------------------
    async def get_with_relationships(self, entity_id: uuid.UUID) -> ModelType | None:
        """Re-read a record with its eager relationships populated.

        Needed after a write for two reasons:

        * A freshly constructed entity has ``parent_id`` set but no ``parent``
          object. Serialising it would lazy-load under asyncio and raise
          ``MissingGreenlet``.
        * After a parent reference is *changed*, the previously loaded parent is
          stale. ``populate_existing`` forces the identity-mapped instance to be
          refreshed rather than reused as-is.

        Archived rows are included, so this also serves the archive/restore path.
        """
        stmt = (
            select(self.model)
            .where(self.model.id == entity_id)  # type: ignore[attr-defined]
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalars().unique().first()

    # ------------------------------------------------------------------
    # Uniqueness lookups
    # ------------------------------------------------------------------
    async def find_by_name_ci(
        self,
        name: str,
        *scope: ColumnElement[bool],
        exclude_id: uuid.UUID | None = None,
    ) -> ModelType | None:
        """Case-insensitively find a record by name.

        Archived records are deliberately included: the database's unique index
        covers every row, so an archived record still occupies its name. Finding
        it here lets the service say "restore it" instead of letting the insert
        fail with a raw integrity error.
        """
        stmt = select(self.model).where(func.lower(self.model.name) == name.lower())  # type: ignore[attr-defined]
        if scope:
            stmt = stmt.where(*scope)
        if exclude_id is not None:
            stmt = stmt.where(self.model.id != exclude_id)  # type: ignore[attr-defined]
        return (await self.session.execute(stmt)).scalars().first()

    async def find_by_code_ci(
        self,
        code: str,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> ModelType | None:
        """Case-insensitively find a record by code, archived rows included."""
        if not self.has_code:
            raise TypeError(f"{self.model.__name__} has no code column")

        stmt = select(self.model).where(func.lower(self.model.code) == code.lower())  # type: ignore[attr-defined]
        if exclude_id is not None:
            stmt = stmt.where(self.model.id != exclude_id)  # type: ignore[attr-defined]
        return (await self.session.execute(stmt)).scalars().first()

    # ------------------------------------------------------------------
    # Referential checks
    # ------------------------------------------------------------------
    async def count_children(self, child_criteria: ColumnElement[bool], child_model: type[Base]) -> int:
        """Count live child rows pointing at a record.

        Used before archiving so a parent cannot be retired out from under its
        children without the caller being told.
        """
        stmt = (
            select(func.count())
            .select_from(child_model)
            .where(child_criteria, child_model.deleted_at.is_(None))  # type: ignore[attr-defined]
        )
        return int((await self.session.execute(stmt)).scalar_one())
