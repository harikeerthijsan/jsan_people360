"""Document vault endpoints.

The upload routes are the only ones in the platform that accept multipart form
data. Two consequences shape them:

* **Metadata arrives as form fields, not a JSON body.** They are collected into
  the Pydantic model by hand so the rules stay in the schema rather than being
  spread across the endpoint signature.
* **The file is read fully into memory before anything else happens.** These are
  documents with a low megabyte cap, not video, and having the bytes in hand is
  what lets the signature be checked before a single byte is written.

Route order matters as elsewhere: ``/dashboard`` is registered before
``/{document_id}``.

NOTE: no ``from __future__ import annotations`` -- FastAPI reads parameter types
from evaluated annotations, and postponed evaluation breaks ``Annotated[...,
Query()]`` and ``File()``.
"""

import uuid
from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import (
    AuditSvc,
    CurrentScope,
    CurrentUser,
    DocumentDashboardSvc,
    DocumentSvc,
    require,
)
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.models.enums import DocumentOwnerType
from app.schemas.common import APIErrorResponse, APIResponse, Page
from app.schemas.document import (
    DocumentAuditEntry,
    DocumentDashboardStats,
    DocumentListParams,
    DocumentRead,
    DocumentReviewRequest,
    DocumentUpdate,
    DocumentUploadMetadata,
    DocumentVersionRead,
    DocumentVersionUploadMetadata,
)
from app.services.document_service import UploadedFile

router = APIRouter(prefix="/documents", tags=["Documents"])

_COMMON_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": APIErrorResponse,
        "description": "Validation failed, including a rejected file.",
    },
}
_NOT_FOUND: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such document."},
}
_CONFLICT: dict[int | str, dict[str, object]] = {
    status.HTTP_409_CONFLICT: {
        "model": APIErrorResponse,
        "description": "A referential or lifecycle rule was violated.",
    },
}
_WRITE_ERRORS = {**_COMMON_ERRORS, **_NOT_FOUND, **_CONFLICT}


async def _read_upload(upload: UploadFile) -> UploadedFile:
    """Drain the uploaded part into memory.

    The size is checked *before* the read, not only inside the validator: the
    part has been spooled by then, but reading it pulls the whole thing into
    the process, so a limit enforced afterwards is a limit enforced too late.
    The validator still re-checks the real length, since the reported size is
    another client-supplied claim.

    The filename is whatever the client sent and is sanitised downstream; the
    declared content type is recorded but never trusted.
    """
    limit = settings.max_upload_size_bytes
    if upload.size is not None and upload.size > limit:
        raise ValidationError(
            f"The file is larger than the {limit / (1024 * 1024):.0f} MB limit.",
            error_code="invalid_file",
        )

    content = await upload.read()
    if not content:
        raise ValidationError("The uploaded file is empty.", error_code="invalid_file")

    return UploadedFile(
        content=content,
        filename=upload.filename or "upload",
        declared_content_type=upload.content_type,
    )


def _content_disposition(filename: str, *, inline: bool) -> str:
    """Build a Content-Disposition that survives non-ASCII filenames.

    Both forms are emitted: a plain ``filename`` that every client understands,
    and the RFC 5987 ``filename*`` that carries the real characters. Quoting
    also stops a crafted name from injecting a header.
    """
    disposition = "inline" if inline else "attachment"
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "document"
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


# ----------------------------------------------------------------------
# Static segments -- must precede /{document_id}
# ----------------------------------------------------------------------
@router.get(
    "/dashboard",
    dependencies=[require("documents:view")],
    response_model=APIResponse[DocumentDashboardStats],
    summary="Document dashboard figures",
    responses={**_COMMON_ERRORS},
)
async def document_dashboard(
    service: DocumentDashboardSvc,
    current_user: CurrentUser,
) -> APIResponse[DocumentDashboardStats]:
    del current_user
    return APIResponse.ok(await service.stats(), message="Dashboard statistics retrieved successfully")


# ----------------------------------------------------------------------
# Listing and upload
# ----------------------------------------------------------------------
@router.get(
    "",
    dependencies=[require("documents:view")],
    response_model=APIResponse[Page[DocumentRead]],
    summary="List documents",
    description=(
        "Returns a page of documents with search, review-status filtering, category "
        "and type filters, an owner filter, an expiry-state filter and an upload-date "
        "range. Live and archived documents are never mixed: pass `archived=true` to "
        "see the archive."
    ),
    responses={**_COMMON_ERRORS},
)
async def list_documents(
    service: DocumentSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
    params: Annotated[DocumentListParams, Query()],
) -> APIResponse[Page[DocumentRead]]:
    del current_user
    rows, total = await service.list(params, scope=scope)

    items = [DocumentRead.from_document(row, owner=await service.resolve_owner(row)) for row in rows]
    page = Page.create(items, page=params.page, page_size=params.page_size, total_items=total)
    return APIResponse.ok(page, message="Documents retrieved successfully")


@router.post(
    "",
    dependencies=[require("documents:create")],
    response_model=APIResponse[DocumentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
    description=(
        "Stores a new document and its first version. The file is validated against "
        "its own content signature, not the name or the declared type, so a renamed "
        "executable is refused. Accepts PDF, JPEG and PNG."
    ),
    responses={**_COMMON_ERRORS, **_CONFLICT},
)
async def upload_document(
    service: DocumentSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
    file: Annotated[UploadFile, File(description="The document. PDF, JPG, JPEG or PNG.")],
    name: Annotated[str, Form(description="What the document is called.")],
    category_id: Annotated[uuid.UUID, Form()],
    document_type_id: Annotated[uuid.UUID, Form()],
    owner_type: Annotated[DocumentOwnerType, Form()],
    owner_id: Annotated[uuid.UUID, Form()],
    description: Annotated[str | None, Form()] = None,
    expiry_date: Annotated[date | None, Form()] = None,
) -> APIResponse[DocumentRead]:
    # Collected into the schema so the validation rules live in one place
    # rather than being spread across this signature.
    metadata = DocumentUploadMetadata(
        name=name,
        category_id=category_id,
        document_type_id=document_type_id,
        owner_type=owner_type,
        owner_id=owner_id,
        description=description,
        expiry_date=expiry_date,
    )

    created = await service.create(metadata, await _read_upload(file), actor_id=current_user.id, scope=scope)
    return APIResponse.ok(
        DocumentRead.from_document(created, owner=await service.resolve_owner(created)),
        message="Document uploaded successfully",
    )


# ----------------------------------------------------------------------
# One document
# ----------------------------------------------------------------------
@router.get(
    "/{document_id}",
    dependencies=[require("documents:view")],
    response_model=APIResponse[DocumentRead],
    summary="Get a document",
    responses={**_COMMON_ERRORS, **_NOT_FOUND},
)
async def get_document(
    document_id: uuid.UUID,
    service: DocumentSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
) -> APIResponse[DocumentRead]:
    del current_user
    document = await service.get_by_id(document_id, scope=scope)
    return APIResponse.ok(
        DocumentRead.from_document(document, owner=await service.resolve_owner(document)),
        message="Document retrieved successfully",
    )


@router.get(
    "/{document_id}/audit",
    dependencies=[require("documents:view")],
    response_model=APIResponse[list[DocumentAuditEntry]],
    summary="Document audit history",
    description="Every audited action for this document, newest first.",
    responses={**_COMMON_ERRORS, **_NOT_FOUND},
)
async def document_audit_history(
    document_id: uuid.UUID,
    service: DocumentSvc,
    audit_service: AuditSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
) -> APIResponse[list[DocumentAuditEntry]]:
    del current_user
    await service.get_by_id(document_id, scope=scope)
    rows = await audit_service.for_entity("document", document_id)
    return APIResponse.ok(
        [DocumentAuditEntry.model_validate(row) for row in rows],
        message="Document audit history retrieved successfully",
    )


@router.patch(
    "/{document_id}",
    dependencies=[require("documents:update")],
    response_model=APIResponse[DocumentRead],
    summary="Update document metadata",
    description=(
        "Changes the name, description, classification or expiry. The file itself is "
        "changed by uploading a new version."
    ),
    responses=_WRITE_ERRORS,
)
async def update_document(
    document_id: uuid.UUID,
    payload: DocumentUpdate,
    service: DocumentSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
) -> APIResponse[DocumentRead]:
    updated = await service.update(document_id, payload, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(
        DocumentRead.from_document(updated, owner=await service.resolve_owner(updated)),
        message="Document updated successfully",
    )


# ----------------------------------------------------------------------
# Versions
# ----------------------------------------------------------------------
@router.get(
    "/{document_id}/versions",
    dependencies=[require("documents:view")],
    response_model=APIResponse[list[DocumentVersionRead]],
    summary="Version history",
    description=(
        "Every version of the document, newest first. Append-only: there is no "
        "endpoint that edits or removes a version, and uploading never overwrites."
    ),
    responses={**_COMMON_ERRORS, **_NOT_FOUND},
)
async def document_versions(
    document_id: uuid.UUID,
    service: DocumentSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
) -> APIResponse[list[DocumentVersionRead]]:
    del current_user
    rows = await service.versions(document_id, scope=scope)
    return APIResponse.ok(
        [DocumentVersionRead.model_validate(row) for row in rows],
        message="Version history retrieved successfully",
    )


@router.post(
    "/{document_id}/versions",
    dependencies=[require("documents:update")],
    response_model=APIResponse[DocumentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new version",
    description=(
        "Adds a version without touching the previous one, which stays stored and "
        "downloadable. Re-uploading a byte-identical file is refused."
    ),
    responses=_WRITE_ERRORS,
)
async def upload_version(
    document_id: uuid.UUID,
    service: DocumentSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
    file: Annotated[UploadFile, File(description="The new version of the document.")],
    notes: Annotated[str | None, Form(description="Why this version was uploaded.")] = None,
) -> APIResponse[DocumentRead]:
    updated = await service.add_version(
        document_id,
        DocumentVersionUploadMetadata(notes=notes),
        await _read_upload(file),
        actor_id=current_user.id,
        scope=scope,
    )
    return APIResponse.ok(
        DocumentRead.from_document(updated, owner=await service.resolve_owner(updated)),
        message="New version uploaded successfully",
    )


# ----------------------------------------------------------------------
# File content
# ----------------------------------------------------------------------
@router.get(
    "/{document_id}/download",
    dependencies=[require("documents:view")],
    summary="Download a document",
    description=(
        "Returns the file as an attachment. Defaults to the current version; pass "
        "`version_id` for an earlier one. **Every download is recorded** in the audit "
        "trail."
    ),
    responses={
        **_COMMON_ERRORS,
        **_NOT_FOUND,
        status.HTTP_200_OK: {"content": {"application/octet-stream": {}}, "description": "The file."},
    },
)
async def download_document(
    document_id: uuid.UUID,
    service: DocumentSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
    version_id: Annotated[uuid.UUID | None, Query(description="Omit for the current version.")] = None,
) -> Response:
    payload = await service.read_file(
        document_id, version_id=version_id, actor_id=current_user.id, for_preview=False, scope=scope
    )
    return Response(
        content=payload.content,
        media_type=payload.content_type,
        headers={
            "Content-Disposition": _content_disposition(payload.filename, inline=False),
            # The content type was derived from the file's own signature, so
            # there is nothing for a browser to usefully second-guess.
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/{document_id}/preview",
    dependencies=[require("documents:view")],
    summary="Preview a document",
    description=(
        "Returns the file for display in the browser rather than as a download. "
        "Recorded separately from a download: previewing is browsing, downloading "
        "takes a copy out of the vault."
    ),
    responses={
        **_COMMON_ERRORS,
        **_NOT_FOUND,
        status.HTTP_200_OK: {
            "content": {"application/pdf": {}, "image/jpeg": {}, "image/png": {}},
            "description": "The file, for inline display.",
        },
    },
)
async def preview_document(
    document_id: uuid.UUID,
    service: DocumentSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
    version_id: Annotated[uuid.UUID | None, Query(description="Omit for the current version.")] = None,
) -> Response:
    payload = await service.read_file(
        document_id, version_id=version_id, actor_id=current_user.id, for_preview=True, scope=scope
    )
    return Response(
        content=payload.content,
        media_type=payload.content_type,
        headers={
            "Content-Disposition": _content_disposition(payload.filename, inline=True),
            "X-Content-Type-Options": "nosniff",
            # Served inline, so the sandbox matters: this stops anything the
            # file might contain from reaching the application's own origin.
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; object-src 'self'",
        },
    )


# ----------------------------------------------------------------------
# Lifecycle
# ----------------------------------------------------------------------
@router.post(
    "/{document_id}/review",
    dependencies=[require("documents:update")],
    response_model=APIResponse[DocumentRead],
    summary="Record a review decision",
    description="Marks the document as under review, approved or rejected.",
    responses=_WRITE_ERRORS,
)
async def review_document(
    document_id: uuid.UUID,
    payload: DocumentReviewRequest,
    service: DocumentSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
) -> APIResponse[DocumentRead]:
    updated = await service.review(document_id, payload, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(
        DocumentRead.from_document(updated, owner=await service.resolve_owner(updated)),
        message="Review recorded successfully",
    )


@router.post(
    "/{document_id}/archive",
    dependencies=[require("documents:delete")],
    response_model=APIResponse[DocumentRead],
    summary="Archive a document",
    description="Hides the document. Every version is kept and nothing is deleted from storage.",
    responses=_WRITE_ERRORS,
)
async def archive_document(
    document_id: uuid.UUID,
    service: DocumentSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
) -> APIResponse[DocumentRead]:
    document = await service.archive(document_id, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(
        DocumentRead.from_document(document, owner=await service.resolve_owner(document)),
        message="Document archived successfully",
    )


@router.post(
    "/{document_id}/restore",
    dependencies=[require("documents:delete")],
    response_model=APIResponse[DocumentRead],
    summary="Restore an archived document",
    responses=_WRITE_ERRORS,
)
async def restore_document(
    document_id: uuid.UUID,
    service: DocumentSvc,
    current_user: CurrentUser,
    scope: CurrentScope,
) -> APIResponse[DocumentRead]:
    document = await service.restore(document_id, actor_id=current_user.id, scope=scope)
    return APIResponse.ok(
        DocumentRead.from_document(document, owner=await service.resolve_owner(document)),
        message="Document restored successfully",
    )
