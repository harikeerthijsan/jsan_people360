"""Document category and type masters.

Both compose the same mixins as the nine organization masters, which is what
lets them reuse the shared master repository, service and router factory rather
than reimplementing paging, uniqueness and archive/restore. A document type
belongs to a category exactly as a practice belongs to a business unit.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.mixins import CodedMasterMixin, status_check, unique_ci, unique_ci_scoped

if TYPE_CHECKING:
    from app.models.document import Document


class DocumentCategory(Base, AuditableBase, CodedMasterMixin):
    """A grouping of document types -- Identity, Educational, Contracts."""

    __tablename__ = "document_categories"
    __table_args__ = (
        unique_ci("uq_document_categories_code_lower", "code"),
        unique_ci("uq_document_categories_name_lower", "name"),
        status_check(),
        {"comment": "Configurable groupings of document types."},
    )

    #: Controls the order categories are offered in, so the list a user meets
    #: reflects how often each is used rather than the alphabet.
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100", index=True
    )

    document_types: Mapped[list[DocumentType]] = relationship(
        back_populates="category",
        cascade="save-update, merge",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<DocumentCategory id={self.id} code={self.code!r}>"


class DocumentType(Base, AuditableBase, CodedMasterMixin):
    """A kind of document -- Aadhaar, Offer Letter, NDA."""

    __tablename__ = "document_types"
    __table_args__ = (
        unique_ci("uq_document_types_code_lower", "code"),
        unique_ci_scoped("uq_document_types_category_id_name_lower", "category_id", "name"),
        status_check(),
        {"comment": "Configurable document types, each belonging to a category."},
    )

    category_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    requires_expiry: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        doc=(
            "Whether an expiry date must be supplied. True for a passport or a "
            "visa; false for a résumé, which does not expire."
        ),
    )
    is_sensitive: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        doc="Marks types whose contents warrant extra care, such as identity documents.",
    )
    allowed_extensions: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        doc=(
            "Comma-separated narrowing of the platform allowlist, e.g. '.pdf' for "
            "a signed contract. Never widens it -- the platform list in "
            "app.utils.files is always applied first."
        ),
    )

    category: Mapped[DocumentCategory] = relationship(
        back_populates="document_types",
        foreign_keys=[category_id],
        lazy="joined",
    )
    documents: Mapped[list[Document]] = relationship(back_populates="document_type", lazy="noload")

    @property
    def extension_allowlist(self) -> frozenset[str] | None:
        """The type's own narrowing, or ``None`` when it does not narrow."""
        if not self.allowed_extensions:
            return None
        parsed = {part.strip().lower() for part in self.allowed_extensions.split(",") if part.strip()}
        return frozenset(parsed) or None

    def __repr__(self) -> str:
        return f"<DocumentType id={self.id} code={self.code!r}>"
