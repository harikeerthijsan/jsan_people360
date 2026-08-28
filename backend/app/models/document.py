"""Documents and their versions.

The split matters. A **document** is the thing a person means when they say
"her passport": one item, with a name, a type, an owner and a status. A
**version** is one uploaded file. Re-uploading adds a version and never
replaces one, so the history is complete by construction rather than by
remembering to keep it.

The current version is the one with the highest number. It is denormalised onto
the document as ``current_version_id`` so that listing a thousand documents does
not need a correlated subquery per row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.enums import (
    DOCUMENT_OWNER_TYPE_SQL_VALUES,
    DOCUMENT_STATUS_SQL_VALUES,
    EXPIRY_WARNING_DAYS,
    DocumentStatus,
    ExpiryState,
)

if TYPE_CHECKING:
    from app.models.document_category import DocumentCategory, DocumentType

#: Generates DOC-000001, DOC-000002, ... in the database itself, for the same
#: reason as the employee and user codes: two concurrent uploads reading
#: ``max(...) + 1`` would produce the same number.
DOCUMENT_CODE_SEQUENCE = "documents_document_code_seq"
DOCUMENT_CODE_DEFAULT = f"'DOC-' || lpad(nextval('{DOCUMENT_CODE_SEQUENCE}')::text, 6, '0')"


class Document(Base, AuditableBase):
    """One logical document belonging to one owner."""

    __tablename__ = "documents"
    __table_args__ = (
        # The list screen's primary access path: everything filed against one
        # owner, newest first.
        Index("ix_documents_owner", "owner_type", "owner_id"),
        Index("ix_documents_status_deleted_at", "status", "deleted_at"),
        # Serves both the expiry dashboard and the "expiring soon" filter.
        Index("ix_documents_expiry_date", "expiry_date"),
        CheckConstraint(f"owner_type IN ({DOCUMENT_OWNER_TYPE_SQL_VALUES})", name="owner_type"),
        CheckConstraint(f"status IN ({DOCUMENT_STATUS_SQL_VALUES})", name="status"),
        {"comment": "A document belonging to an employee, candidate, organization or user."},
    )

    document_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        index=True,
        server_default=text(DOCUMENT_CODE_DEFAULT),
        doc="System-generated document identifier (DOC-000001). Never editable.",
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        doc="What a person calls it -- 'Passport', not the uploaded filename.",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # -- Classification --------------------------------------------------
    category_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    document_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # -- Ownership -------------------------------------------------------
    #
    # Polymorphic, so no foreign key: the target table differs by owner type,
    # and candidates do not have a table yet. The service verifies the target
    # exists for the types it can; the CHECK constrains the discriminator.
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    # -- Lifecycle -------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DocumentStatus.UPLOADED,
        server_default=DocumentStatus.UPLOADED.value,
        index=True,
    )
    expiry_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, doc="When the document stops being valid. Null when it does not expire."
    )
    review_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Why it was approved or rejected."
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    # -- Current version --------------------------------------------------
    #
    # Denormalised. Without it, every row of a list page needs a correlated
    # subquery to find its newest version, which is the query that stops a
    # document list scaling.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    version_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # -- Relationships -----------------------------------------------------
    category: Mapped[DocumentCategory] = relationship(foreign_keys=[category_id], lazy="joined")
    document_type: Mapped[DocumentType] = relationship(
        back_populates="documents", foreign_keys=[document_type_id], lazy="joined"
    )
    current_version: Mapped[DocumentVersion | None] = relationship(
        foreign_keys=[current_version_id], lazy="joined", post_update=True
    )
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        foreign_keys="DocumentVersion.document_id",
        cascade="all, delete-orphan",
        # Only the detail page reads the whole history, and it grows without
        # bound. Loading it per row of a list would be wasteful.
        lazy="noload",
        order_by="DocumentVersion.version_number.desc()",
    )

    # -- Behaviour ---------------------------------------------------------
    @property
    def expiry_state(self) -> ExpiryState:
        """Derived on read so it can never be stale.

        A stored "expiring soon" would be wrong the morning after it was
        written, and keeping it right would need a scheduled job that has to be
        running for the data to be trustworthy.
        """
        if self.expiry_date is None:
            return ExpiryState.NONE

        remaining = (self.expiry_date - datetime.now(UTC).date()).days
        if remaining < 0:
            return ExpiryState.EXPIRED
        if remaining <= EXPIRY_WARNING_DAYS:
            return ExpiryState.EXPIRING_SOON
        return ExpiryState.VALID

    @property
    def is_expired(self) -> bool:
        return self.expiry_state is ExpiryState.EXPIRED

    def __repr__(self) -> str:
        return f"<Document id={self.id} code={self.document_code!r} name={self.name!r}>"


class DocumentVersion(Base, AuditableBase):
    """One uploaded file belonging to a document.

    Append-only: nothing updates or deletes a version. Re-uploading creates the
    next one, so the vault can always answer "what did we hold in March?".
    """

    __tablename__ = "document_versions"
    __table_args__ = (
        # One row per version number per document -- the database's half of the
        # duplicate-version guard.
        Index(
            "uq_document_versions_document_id_version",
            "document_id",
            "version_number",
            unique=True,
        ),
        Index("ix_document_versions_checksum", "checksum"),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        {"comment": "Append-only versions of a document. One row per uploaded file."},
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="1 for the first upload, then 2, 3, … Assigned by the service."
    )

    # -- File metadata -----------------------------------------------------
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="The sanitised name the uploader used. For display and download only.",
    )
    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Derived from the file's own signature, never from what the client declared.",
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="SHA-256 of the content. Recognises a re-upload of an identical file.",
    )

    storage_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        doc=(
            "Opaque handle into the storage backend. On local disk it happens to "
            "be a relative path; on object storage it is an object key. **Never "
            "returned by the API** -- downloads go through the document id."
        ),
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True, doc="Why this version was uploaded.")

    document: Mapped[Document] = relationship(
        back_populates="versions",
        foreign_keys=[document_id],
    )

    @property
    def size_display(self) -> str:
        """Human-readable size, for a UI that should not do arithmetic."""
        size = float(self.size_bytes)
        for unit in ("B", "KB", "MB"):
            if size < 1024 or unit == "MB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} MB"

    def __repr__(self) -> str:
        return f"<DocumentVersion id={self.id} document_id={self.document_id} v{self.version_number}>"
