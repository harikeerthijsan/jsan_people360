"""Document category and type endpoints.

Both are built by :func:`app.api.master_router.build_master_router`, the same
factory that produces the nine organization masters. They therefore have an
identical HTTP contract -- list, get, create, update, archive, restore -- which
is the point: an administrator who has managed departments already knows how to
manage document types.
"""

from fastapi import APIRouter

from app.api.deps import get_document_category_service, get_document_type_service
from app.api.master_router import build_master_router
from app.schemas.document import (
    DocumentCategoryCreate,
    DocumentCategoryListParams,
    DocumentCategoryRead,
    DocumentCategoryUpdate,
    DocumentTypeCreate,
    DocumentTypeListParams,
    DocumentTypeRead,
    DocumentTypeUpdate,
)

router = APIRouter()

router.include_router(
    build_master_router(
        permission_module="documents",
        prefix="/document-categories",
        tag="Document categories",
        entity_label="Document category",
        entity_label_plural="document categories",
        read_schema=DocumentCategoryRead,
        create_schema=DocumentCategoryCreate,
        update_schema=DocumentCategoryUpdate,
        service_dependency=get_document_category_service,
        params_schema=DocumentCategoryListParams,
    )
)

router.include_router(
    build_master_router(
        permission_module="documents",
        prefix="/document-types",
        tag="Document types",
        entity_label="Document type",
        entity_label_plural="document types",
        read_schema=DocumentTypeRead,
        create_schema=DocumentTypeCreate,
        update_schema=DocumentTypeUpdate,
        service_dependency=get_document_type_service,
        params_schema=DocumentTypeListParams,
    )
)

__all__ = ["router"]
