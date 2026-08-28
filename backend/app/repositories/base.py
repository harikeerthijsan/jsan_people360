"""Generic repository.

The repository layer is the *only* place that talks to SQLAlchemy. Services
depend on repositories; routes depend on services. This keeps persistence
concerns swappable and makes the service layer trivially unit-testable.

Repositories never commit -- transaction boundaries belong to the unit of work
managed by the request-scoped session dependency.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.base_class import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """CRUD operations shared by every entity.

    Soft-deleted rows are excluded from every read unless ``include_deleted``
    is explicitly set.
    """

    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Query construction
    # ------------------------------------------------------------------
    def _base_select(self, *, include_deleted: bool = False) -> Select[tuple[ModelType]]:
        stmt = select(self.model)
        if not include_deleted and hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        return stmt

    def _apply_ordering(
        self,
        stmt: Select[tuple[ModelType]],
        order_by: str | None,
        descending: bool,
    ) -> Select[tuple[ModelType]]:
        column_name = order_by or ("created_at" if hasattr(self.model, "created_at") else "id")
        column = getattr(self.model, column_name, None)
        if column is None:
            raise ValueError(f"{self.model.__name__} has no sortable column named {column_name!r}")
        return stmt.order_by(column.desc() if descending else column.asc())

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def get(self, entity_id: uuid.UUID, *, include_deleted: bool = False) -> ModelType | None:
        stmt = self._base_select(include_deleted=include_deleted).where(self.model.id == entity_id)  # type: ignore[attr-defined]
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by(self, *, include_deleted: bool = False, **filters: Any) -> ModelType | None:
        stmt = self._base_select(include_deleted=include_deleted).filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def find(
        self,
        *criteria: ColumnElement[bool],
        include_deleted: bool = False,
    ) -> ModelType | None:
        stmt = self._base_select(include_deleted=include_deleted).where(*criteria)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list(
        self,
        *criteria: ColumnElement[bool],
        offset: int = 0,
        limit: int = 50,
        order_by: str | None = None,
        descending: bool = True,
        include_deleted: bool = False,
    ) -> Sequence[ModelType]:
        stmt = self._base_select(include_deleted=include_deleted)
        if criteria:
            stmt = stmt.where(*criteria)
        stmt = self._apply_ordering(stmt, order_by, descending).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().unique().all()

    async def count(self, *criteria: ColumnElement[bool], include_deleted: bool = False) -> int:
        stmt = select(func.count()).select_from(self.model)
        if not include_deleted and hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        if criteria:
            stmt = stmt.where(*criteria)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def exists(self, *criteria: ColumnElement[bool], include_deleted: bool = False) -> bool:
        return await self.count(*criteria, include_deleted=include_deleted) > 0

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    async def add(self, entity: ModelType, *, actor_id: uuid.UUID | None = None) -> ModelType:
        """Stage a new entity and flush so server defaults (id) are populated."""
        if actor_id is not None:
            self._set_if_present(entity, "created_by", actor_id)
            self._set_if_present(entity, "updated_by", actor_id)
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(
        self,
        entity: ModelType,
        values: dict[str, Any],
        *,
        actor_id: uuid.UUID | None = None,
    ) -> ModelType:
        """Apply a partial update to a managed entity."""
        for field, value in values.items():
            if not hasattr(entity, field):
                raise ValueError(f"{self.model.__name__} has no attribute {field!r}")
            setattr(entity, field, value)
        if actor_id is not None:
            self._set_if_present(entity, "updated_by", actor_id)
        await self.session.flush()
        return entity

    async def soft_delete(self, entity: ModelType, *, actor_id: uuid.UUID | None = None) -> ModelType:
        """Mark an entity deleted without removing the row."""
        if not hasattr(entity, "deleted_at"):
            raise TypeError(f"{self.model.__name__} does not support soft delete")
        entity.deleted_at = datetime.now(UTC)
        self._set_if_present(entity, "deleted_by", actor_id)
        self._set_if_present(entity, "updated_by", actor_id)
        await self.session.flush()
        return entity

    async def restore(self, entity: ModelType, *, actor_id: uuid.UUID | None = None) -> ModelType:
        entity.deleted_at = None  # type: ignore[attr-defined]
        self._set_if_present(entity, "deleted_by", None)
        self._set_if_present(entity, "updated_by", actor_id)
        await self.session.flush()
        return entity

    async def hard_delete(self, entity: ModelType) -> None:
        """Physically remove a row. Reserved for data-retention jobs."""
        await self.session.delete(entity)
        await self.session.flush()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _set_if_present(entity: Any, field: str, value: Any) -> None:
        if hasattr(entity, field):
            setattr(entity, field, value)
