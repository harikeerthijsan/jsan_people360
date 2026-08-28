"""Document vault request/response schemas.

Two things are worth knowing before reading the rest.

**The file itself never appears in a schema.** An upload arrives as multipart
form data -- a file part plus metadata parts -- so the metadata is modelled here
and the bytes are validated in :mod:`app.utils.files` against their own content.
Pydantic cannot check that a file claiming to be a PDF actually is one.

**No storage key is ever returned.** ``DocumentVersionRead`` deliberately omits
it. Downloads go through the document and version ids, so the API never reveals
where anything physically lives.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.models.enums import DocumentOwnerType, DocumentStatus, ExpiryState
from app.schemas.masters import (
    CodedMasterCreateBase,
    CodedMasterReadBase,
    CodedMasterUpdateBase,
    MasterListParams,
    MasterSummary,
    SortOrder,
    normalise_optional_text,
)
from app.utils.files import ALLOWED_EXTENSIONS

DOCUMENT_MODEL_CONFIG = ConfigDict(str_strip_whitespace=True, extra="forbid")


def validate_extension_list(value: str | None) -> str | None:
    """Normalise a document type's extension narrowing.

    Only ever *narrows* the platform allowlist. An entry outside it is rejected
    rather than silently ignored, so nobody can believe they have enabled ``.docx``
    by typing it here.
    """
    if value is None:
        return None

    cleaned = value.strip().lower()
    if not cleaned:
        return None

    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    normalised = [part if part.startswith(".") else f".{part}" for part in parts]

    unknown = sorted(set(normalised) - ALLOWED_EXTENSIONS)
    if unknown:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(
            f"{', '.join(unknown)} cannot be allowed here. This setting only narrows the "
            f"platform list, which is: {allowed}."
        )

    return ",".join(sorted(set(normalised)))


def validate_expiry_date(value: date | None) -> date | None:
    """Reject an expiry so far out it is certainly a mistyped year."""
    if value is None:
        return None
    if value.year > date.today().year + 100:
        raise ValueError("Expiry date is implausibly far in the future; check the year.")
    return value


DocumentName = Annotated[str, Field(min_length=2, max_length=200)]
DocumentDescription = Annotated[
    str | None, Field(default=None, max_length=2000), AfterValidator(normalise_optional_text)
]
ExpiryDate = Annotated[date | None, Field(default=None), AfterValidator(validate_expiry_date)]
ExtensionList = Annotated[
    str | None, Field(default=None, max_length=120), AfterValidator(validate_extension_list)
]


# ----------------------------------------------------------------------
# Category and type masters
#
# Built on the shared master bases, so they behave exactly like the nine
# organization masters -- same paging, same uniqueness messages, same
# archive/restore semantics -- without reimplementing any of it.
# ----------------------------------------------------------------------
class DocumentCategoryCreate(CodedMasterCreateBase):
    display_order: int = Field(
        default=100,
        ge=1,
        le=999,
        description="Controls the order categories are offered in. Lower comes first.",
    )


class DocumentCategoryUpdate(CodedMasterUpdateBase):
    display_order: int | None = Field(default=None, ge=1, le=999)


class DocumentCategoryRead(CodedMasterReadBase):
    display_order: int


class DocumentTypeCreate(CodedMasterCreateBase):
    category_id: uuid.UUID
    requires_expiry: bool = Field(
        default=False,
        description="Whether an expiry date must be supplied. True for a passport, false for a résumé.",
    )
    is_sensitive: bool = Field(default=False)
    allowed_extensions: ExtensionList = None


class DocumentTypeUpdate(CodedMasterUpdateBase):
    category_id: uuid.UUID | None = None
    requires_expiry: bool | None = None
    is_sensitive: bool | None = None
    allowed_extensions: ExtensionList = None


class DocumentTypeRead(CodedMasterReadBase):
    category_id: uuid.UUID
    category: MasterSummary | None = None
    requires_expiry: bool
    is_sensitive: bool
    allowed_extensions: str | None = None


class DocumentTypeListParams(MasterListParams):
    category_id: uuid.UUID | None = Field(default=None, description="Return only types in this category.")


# ----------------------------------------------------------------------
# Upload and metadata
# ----------------------------------------------------------------------
class DocumentUploadMetadata(BaseModel):
    """The metadata parts of a multipart upload.

    Assembled from form fields by the route rather than parsed from a JSON body,
    because the file travels alongside them. Validating it as a model keeps the
    rules in one place instead of scattered through the endpoint.
    """

    model_config = DOCUMENT_MODEL_CONFIG

    name: DocumentName
    category_id: uuid.UUID
    document_type_id: uuid.UUID
    owner_type: DocumentOwnerType
    owner_id: uuid.UUID
    description: DocumentDescription = None
    expiry_date: ExpiryDate = None


class DocumentVersionUploadMetadata(BaseModel):
    """What accompanies a new version of an existing document."""

    model_config = DOCUMENT_MODEL_CONFIG

    notes: Annotated[
        str | None, Field(default=None, max_length=1000), AfterValidator(normalise_optional_text)
    ] = None


class DocumentUpdate(BaseModel):
    """Metadata-only edit. The file is changed by uploading a new version."""

    model_config = DOCUMENT_MODEL_CONFIG

    name: DocumentName | None = None
    description: DocumentDescription = None
    category_id: uuid.UUID | None = None
    document_type_id: uuid.UUID | None = None
    expiry_date: ExpiryDate = None


class DocumentReviewRequest(BaseModel):
    """Approve or reject a document."""

    model_config = DOCUMENT_MODEL_CONFIG

    status: DocumentStatus
    review_notes: Annotated[
        str | None, Field(default=None, max_length=2000), AfterValidator(normalise_optional_text)
    ] = None

    @field_validator("status")
    @classmethod
    def _reviewable(cls, value: DocumentStatus) -> DocumentStatus:
        """Only the outcomes of a review may be set here.

        ``expired`` is derived from a date and ``archived`` has its own endpoint,
        so allowing either would let a reviewer set a state the rest of the
        system computes for itself.
        """
        allowed = {DocumentStatus.UNDER_REVIEW, DocumentStatus.APPROVED, DocumentStatus.REJECTED}
        if value not in allowed:
            names = ", ".join(sorted(status.value for status in allowed))
            raise ValueError(f"A review can only set one of: {names}.")
        return value


# ----------------------------------------------------------------------
# Read schemas
# ----------------------------------------------------------------------
class DocumentVersionRead(BaseModel):
    """One uploaded file.

    ``storage_key`` is deliberately absent: it is where the file physically
    lives, and no client has a legitimate use for it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    original_filename: str
    content_type: str
    size_bytes: int
    size_display: str = Field(description="Human-readable size, so the client need not do arithmetic.")
    checksum: str
    notes: str | None = None

    created_at: datetime
    created_by: uuid.UUID | None = None


class DocumentAuditEntry(BaseModel):
    """A safe, document-scoped projection of an append-only audit entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    outcome: str
    description: str | None = None
    actor_id: uuid.UUID | None = None
    actor_email: str | None = None
    context: dict[str, Any] | None = None
    created_at: datetime


class DocumentOwnerRef(BaseModel):
    """The owner, resolved to something a person recognises.

    A bare type and UUID is not usable in a list; this carries the name the
    owner is known by, looked up per owner type.
    """

    owner_type: DocumentOwnerType
    owner_id: uuid.UUID
    display_name: str | None = Field(
        default=None, description="Null when the owner no longer exists or cannot be resolved."
    )
    reference_code: str | None = Field(default=None, description="The owner's own identifier, e.g. JSAN336.")


class DocumentRead(BaseModel):
    """Full representation of a document."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_code: str
    name: str
    description: str | None = None

    category_id: uuid.UUID
    document_type_id: uuid.UUID
    category: MasterSummary | None = None
    document_type: MasterSummary | None = None

    owner_type: DocumentOwnerType
    owner_id: uuid.UUID
    owner: DocumentOwnerRef | None = None

    status: DocumentStatus
    expiry_date: date | None = None
    expiry_state: ExpiryState = Field(
        description="Derived from the expiry date on every read, so it can never be stale."
    )
    review_notes: str | None = None
    reviewed_at: datetime | None = None
    reviewed_by: uuid.UUID | None = None

    current_version: DocumentVersionRead | None = None
    version_count: int

    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
    deleted_at: datetime | None = Field(
        default=None, description="Set when the document is archived; null when live."
    )

    @classmethod
    def from_document(cls, document: Any, *, owner: DocumentOwnerRef | None = None) -> DocumentRead:
        """Build the response, assembling the projected fields.

        ``expiry_state`` is computed by the model and ``owner`` is resolved by
        the service, so both are supplied here rather than read off a column
        that could drift.
        """
        data: dict[str, Any] = {
            name: getattr(document, name) for name in cls.model_fields if hasattr(document, name)
        }
        data["expiry_state"] = document.expiry_state
        data["owner"] = owner
        return cls.model_validate(data)


class DocumentSummary(BaseModel):
    """Compact document reference, for embedding in other modules' payloads."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_code: str
    name: str
    status: DocumentStatus
    expiry_date: date | None = None


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------
class CountByLabel(BaseModel):
    label: str
    count: int


class DocumentDashboardStats(BaseModel):
    """Headline figures for the document dashboard."""

    total_documents: int = Field(description="Live documents, whatever their status.")
    pending_review: int = Field(description="Uploaded or under review, awaiting a decision.")
    expiring_soon: int = Field(description="Valid, but expiring within 30 days.")
    expired: int
    approved: int
    rejected: int
    archived: int
    total_storage_bytes: int = Field(description="Across every version, including superseded ones.")
    by_category: list[CountByLabel]
    by_status: list[CountByLabel]


# ----------------------------------------------------------------------
# Query parameters
# ----------------------------------------------------------------------
class DocumentListParams(MasterListParams):
    """The shared list parameters plus the document filters.

    ``status`` is overridden: the inherited one is the master-data
    active/inactive pair, and a document has a six-state review lifecycle of its
    own.
    """

    status: DocumentStatus | None = Field(  # type: ignore[assignment]
        default=None, description="Filter by review status."
    )
    # Newest first by default: a document list is a record of what arrived, and
    # what arrived most recently is what a person is usually looking for.
    sort_by: str = Field(default="created_at", max_length=50, description="Column to sort by.")
    sort_order: SortOrder = SortOrder.DESC

    category_id: uuid.UUID | None = None
    document_type_id: uuid.UUID | None = None
    owner_type: DocumentOwnerType | None = None
    owner_id: uuid.UUID | None = None
    expiry_state: ExpiryState | None = Field(
        default=None, description="valid, expiring_soon, expired, or none for documents without an expiry."
    )
    uploaded_from: date | None = Field(default=None, description="Uploaded on or after this date.")
    uploaded_to: date | None = Field(default=None, description="Uploaded on or before this date.")


class DocumentCategoryListParams(MasterListParams):
    sort_by: str = Field(default="display_order", max_length=50, description="Column to sort by.")


__all__ = [
    "CountByLabel",
    "DocumentCategoryCreate",
    "DocumentCategoryListParams",
    "DocumentCategoryRead",
    "DocumentCategoryUpdate",
    "DocumentDashboardStats",
    "DocumentListParams",
    "DocumentOwnerRef",
    "DocumentRead",
    "DocumentReviewRequest",
    "DocumentSummary",
    "DocumentTypeCreate",
    "DocumentTypeListParams",
    "DocumentTypeRead",
    "DocumentTypeUpdate",
    "DocumentUpdate",
    "DocumentUploadMetadata",
    "DocumentVersionRead",
    "DocumentVersionUploadMetadata",
]
