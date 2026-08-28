"""Document category and type services.

Both extend :class:`~app.services.master_service.MasterService`, so paged
search, duplicate detection, archive and restore all come from the shared
implementation. Only what is genuinely different is declared here: the parent
check on a type, and the guards that stop either being archived while documents
still refer to it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import ConflictError
from app.models.document_category import DocumentCategory, DocumentType
from app.repositories.document_repository import (
    DocumentCategoryRepository,
    DocumentRepository,
    DocumentTypeRepository,
)
from app.schemas.document import (
    DocumentCategoryCreate,
    DocumentCategoryListParams,
    DocumentCategoryUpdate,
    DocumentTypeCreate,
    DocumentTypeListParams,
    DocumentTypeUpdate,
)
from app.services.audit_service import AuditService
from app.services.master_service import MasterService


class DocumentCategoryService(
    MasterService[
        DocumentCategory, DocumentCategoryCreate, DocumentCategoryUpdate, DocumentCategoryListParams
    ]
):
    entity_label = "Document category"
    entity_label_plural = "document categories"
    entity_type = "document_category"
    audit_entity = "document.category"

    def __init__(
        self,
        repository: DocumentCategoryRepository,
        audit_service: AuditService,
        document_repository: DocumentRepository | None = None,
        type_repository: DocumentTypeRepository | None = None,
    ) -> None:
        super().__init__(repository, audit_service)
        self._documents = document_repository
        self._types = type_repository

    async def _assert_can_archive(self, entity: DocumentCategory) -> None:
        """Refuse while types or documents still point at the category.

        Archiving it out from under them would leave documents classified under
        something a user can no longer see.
        """
        if self._types is not None:
            types = await self._types.count_children(DocumentType.category_id == entity.id, DocumentType)
            if types:
                raise self._blocked_by_children(types, "document type")

        if self._documents is not None:
            documents = await self._documents.count_for_category(entity.id)
            if documents:
                raise self._blocked_by_children(documents, "document")


class DocumentTypeService(
    MasterService[DocumentType, DocumentTypeCreate, DocumentTypeUpdate, DocumentTypeListParams]
):
    entity_label = "Document type"
    entity_label_plural = "document types"
    entity_type = "document_type"
    audit_entity = "document.type"

    def __init__(
        self,
        repository: DocumentTypeRepository,
        category_repository: DocumentCategoryRepository,
        audit_service: AuditService,
        document_repository: DocumentRepository | None = None,
    ) -> None:
        super().__init__(repository, audit_service)
        self._categories = category_repository
        self._documents = document_repository

    def _name_scope(self, data: dict[str, Any]) -> Sequence[ColumnElement[bool]]:
        """Type names are unique within their category, not globally.

        Two categories may each hold a "Certificate"; one category may not hold
        two.
        """
        category_id = data.get("category_id")
        return (DocumentType.category_id == category_id,) if category_id else ()

    async def _validate_references(self, data: dict[str, Any], *, entity: DocumentType | None = None) -> None:
        """The category must exist, be live and be active."""
        category_id = data.get("category_id")
        if category_id is None:
            return

        # An existing type whose category was later deactivated stays editable;
        # only a *change* of category is checked. Otherwise deactivating a
        # category would freeze every type inside it.
        if entity is not None and entity.category_id == category_id:
            return

        category = await self._categories.get(category_id, include_deleted=True)
        if not self._is_usable(category):
            raise ConflictError(
                "The selected document category does not exist, is archived, or is inactive.",
                error_code="invalid_category",
            )

    async def _assert_can_restore(self, entity: DocumentType) -> None:
        """A type cannot come back under an archived category -- it would be an orphan."""
        category = await self._categories.get(entity.category_id, include_deleted=True)
        if category is not None and category.deleted_at is not None:
            raise ConflictError(
                "The category this type belongs to is archived. Restore the category first.",
                error_code="parent_archived",
            )

    async def _assert_can_archive(self, entity: DocumentType) -> None:
        if self._documents is None:
            return
        documents = await self._documents.count_for_type(entity.id)
        if documents:
            raise self._blocked_by_children(documents, "document")

    def _list_criteria(self, params: DocumentTypeListParams) -> Sequence[ColumnElement[bool]]:
        if params.category_id is not None:
            return (DocumentType.category_id == params.category_id,)
        return ()
