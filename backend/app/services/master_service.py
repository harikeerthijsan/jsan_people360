"""Shared business logic for the organization master-data entities.

Every master behaves the same way: paged search, uniqueness on name and code,
archive instead of delete, restore, and an audit entry for each write. That
behaviour is implemented once here; the nine concrete services declare only what
is genuinely different about them -- their parent references and their archive
guards.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.db.base_class import Base
from app.models.enums import RecordStatus
from app.repositories.master_repository import MasterRepository
from app.schemas.masters import MasterListParams
from app.services.audit_service import AuditService

logger = get_logger("services.master")

ModelT = TypeVar("ModelT", bound=Base)
CreateT = TypeVar("CreateT", bound=BaseModel)
UpdateT = TypeVar("UpdateT", bound=BaseModel)
# Entities with a parent extend MasterListParams with a filter for it, so the
# list signature stays typed instead of reaching for getattr.
ParamsT = TypeVar("ParamsT", bound=MasterListParams)

# Audit verbs. Combined with each service's ``audit_entity`` to produce dotted
# actions such as ``organization.business_unit.created``.
ACTION_CREATED = "created"
ACTION_UPDATED = "updated"
ACTION_ARCHIVED = "archived"
ACTION_RESTORED = "restored"


class MasterService(Generic[ModelT, CreateT, UpdateT, ParamsT]):
    """Create, read, update, archive and restore a master-data entity."""

    #: Singular, human-readable label used in messages shown to users.
    entity_label: str = "Record"
    #: Plural label, used in referential-integrity messages.
    entity_label_plural: str = "records"
    #: Value stored in ``audit_logs.entity_type``.
    entity_type: str = "record"
    #: Dotted prefix for audit actions.
    audit_entity: str = "organization.record"

    def __init__(self, repository: MasterRepository[ModelT], audit_service: AuditService) -> None:
        self.repository = repository
        self._audit = audit_service

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def list(self, params: ParamsT) -> tuple[Sequence[ModelT], int]:
        """Return one page of records plus the total number of matches."""
        if params.sort_by not in self.repository.sortable_fields:
            allowed = ", ".join(sorted(self.repository.sortable_fields))
            raise BadRequestError(
                f"Cannot sort by {params.sort_by!r}. Sortable columns are: {allowed}.",
                error_code="invalid_sort_field",
            )
        return await self.repository.list_page(params, *self._list_criteria(params))

    async def get(self, entity_id: uuid.UUID, *, include_archived: bool = True) -> ModelT:
        """Fetch one record, or raise :class:`NotFoundError`.

        Archived records are readable by default so that a detail page reached
        from the archive list, or a stale bookmark, shows the record rather than
        a confusing 404.
        """
        entity = await self.repository.get(entity_id, include_deleted=include_archived)
        if entity is None:
            raise NotFoundError(self.entity_label)
        return entity

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    async def create(self, payload: CreateT, *, actor_id: uuid.UUID | None = None) -> ModelT:
        data = payload.model_dump()

        await self._validate_references(data)
        await self._assert_unique(data, entity=None)

        entity = self.repository.model(**data)
        await self.repository.add(entity, actor_id=actor_id)
        entity = await self._reload(entity)

        await self._audit.record_success(
            f"{self.audit_entity}.{ACTION_CREATED}",
            actor_id=actor_id,
            entity_type=self.entity_type,
            entity_id=entity.id,  # type: ignore[attr-defined]
            description=f"Created {self.entity_label.lower()} {self._describe(entity)}",
            context={"fields": sorted(data)},
        )
        logger.info(
            "Master record created",
            extra={"entity_type": self.entity_type, "record_id": str(entity.id)},  # type: ignore[attr-defined]
        )
        return entity

    async def update(
        self,
        entity_id: uuid.UUID,
        payload: UpdateT,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> ModelT:
        entity = await self.get(entity_id)

        if entity.deleted_at is not None:  # type: ignore[attr-defined]
            raise ConflictError(
                f"This {self.entity_label.lower()} is archived. Restore it before editing.",
                error_code="record_archived",
            )

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return entity

        # Uniqueness and reference checks run against the *resulting* record,
        # not the submitted fragment, so a partial update cannot sidestep them.
        effective = {**self._current_values(entity, changes.keys()), **changes}
        await self._validate_references(effective, entity=entity)
        await self._assert_unique(effective, entity=entity)

        await self.repository.update(entity, changes, actor_id=actor_id)
        entity = await self._reload(entity)

        await self._audit.record_success(
            f"{self.audit_entity}.{ACTION_UPDATED}",
            actor_id=actor_id,
            entity_type=self.entity_type,
            entity_id=entity.id,  # type: ignore[attr-defined]
            description=f"Updated {self.entity_label.lower()} {self._describe(entity)}",
            context={"fields": sorted(changes)},
        )
        return entity

    async def archive(self, entity_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> ModelT:
        """Soft delete a record after checking nothing live still depends on it."""
        entity = await self.get(entity_id)

        if entity.deleted_at is not None:  # type: ignore[attr-defined]
            raise ConflictError(
                f"This {self.entity_label.lower()} is already archived.",
                error_code="already_archived",
            )

        await self._assert_can_archive(entity)
        await self.repository.soft_delete(entity, actor_id=actor_id)

        await self._audit.record_success(
            f"{self.audit_entity}.{ACTION_ARCHIVED}",
            actor_id=actor_id,
            entity_type=self.entity_type,
            entity_id=entity.id,  # type: ignore[attr-defined]
            description=f"Archived {self.entity_label.lower()} {self._describe(entity)}",
        )
        logger.info(
            "Master record archived",
            extra={"entity_type": self.entity_type, "record_id": str(entity.id)},  # type: ignore[attr-defined]
        )
        return entity

    async def restore(self, entity_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> ModelT:
        """Bring an archived record back into use."""
        entity = await self.get(entity_id)

        if entity.deleted_at is None:  # type: ignore[attr-defined]
            raise ConflictError(
                f"This {self.entity_label.lower()} is not archived.",
                error_code="not_archived",
            )

        await self._assert_can_restore(entity)
        await self.repository.restore(entity, actor_id=actor_id)

        await self._audit.record_success(
            f"{self.audit_entity}.{ACTION_RESTORED}",
            actor_id=actor_id,
            entity_type=self.entity_type,
            entity_id=entity.id,  # type: ignore[attr-defined]
            description=f"Restored {self.entity_label.lower()} {self._describe(entity)}",
        )
        return entity

    # ------------------------------------------------------------------
    # Uniqueness
    # ------------------------------------------------------------------
    async def _assert_unique(self, data: dict[str, Any], *, entity: ModelT | None) -> None:
        """Reject duplicate names and codes before the database has to.

        The database enforces this too, via unique indexes on ``lower(column)``.
        Checking here first is what turns an opaque integrity error into a
        message naming the field and, when relevant, telling the user that the
        conflicting record is archived rather than missing.
        """
        exclude_id: uuid.UUID | None = entity.id if entity is not None else None  # type: ignore[attr-defined]

        name = data.get("name")
        if name is not None:
            scope = self._name_scope(data)
            clash = await self.repository.find_by_name_ci(name, *scope, exclude_id=exclude_id)
            if clash is not None:
                raise ConflictError(self._duplicate_message("name", name, clash), error_code="duplicate_name")

        code = data.get("code")
        if code is not None and self.repository.has_code:
            clash = await self.repository.find_by_code_ci(code, exclude_id=exclude_id)
            if clash is not None:
                raise ConflictError(self._duplicate_message("code", code, clash), error_code="duplicate_code")

    def _duplicate_message(self, field: str, value: str, clash: ModelT) -> str:
        subject = f'{self.entity_label} {field} "{value}" is already in use'
        if clash.deleted_at is not None:  # type: ignore[attr-defined]
            return (
                f"{subject} by an archived record. Restore that record instead of "
                "creating a duplicate, or choose a different value."
            )
        return f"{subject}."

    def _name_scope(self, data: dict[str, Any]) -> Sequence[ColumnElement[bool]]:
        """Criteria that scope name uniqueness.

        Empty by default, meaning names are globally unique. Entities whose
        names need only be unique within a parent override this.
        """
        del data
        return ()

    # ------------------------------------------------------------------
    # Hooks for concrete services
    # ------------------------------------------------------------------
    async def _validate_references(self, data: dict[str, Any], *, entity: ModelT | None = None) -> None:
        """Verify foreign keys point at usable records. No-op by default."""

    async def _assert_can_archive(self, entity: ModelT) -> None:
        """Refuse the archive if live records still depend on this one."""

    async def _assert_can_restore(self, entity: ModelT) -> None:
        """Refuse the restore if the record's parent is itself archived."""

    def _list_criteria(self, params: ParamsT) -> Sequence[ColumnElement[bool]]:
        """Extra filters applied to the list query. None by default."""
        del params
        return ()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _reload(self, entity: ModelT) -> ModelT:
        """Re-read a record after a write so its relationships are current."""
        refreshed = await self.repository.get_with_relationships(entity.id)  # type: ignore[attr-defined]
        if refreshed is None:  # pragma: no cover - the row was just flushed
            raise NotFoundError(self.entity_label)
        return refreshed

    @staticmethod
    def _current_values(entity: ModelT, fields: Any) -> dict[str, Any]:
        return {field: getattr(entity, field) for field in fields if hasattr(entity, field)}

    @staticmethod
    def _describe(entity: ModelT) -> str:
        code = getattr(entity, "code", None)
        name = getattr(entity, "name", "")
        return f"{name} ({code})" if code else str(name)

    def _blocked_by_children(self, count: int, child_label: str) -> ConflictError:
        """Uniform message for a refused archive."""
        noun = child_label if count == 1 else f"{child_label}s"
        return ConflictError(
            f"This {self.entity_label.lower()} still has {count} active {noun}. "
            f"Archive or reassign {'it' if count == 1 else 'them'} first.",
            error_code="has_active_children",
        )

    @staticmethod
    def _is_usable(entity: Any) -> bool:
        """A parent is selectable only when it is live and active."""
        return entity is not None and entity.deleted_at is None and entity.status == RecordStatus.ACTIVE
