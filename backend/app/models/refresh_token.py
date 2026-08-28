"""Refresh token model.

Refresh tokens are opaque random strings; only their SHA-256 digest is stored.
Tokens rotate on every use: the consumed row is revoked and linked to its
replacement, which gives us reuse detection (a replayed token whose row is
already revoked invalidates the whole chain).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base, AuditableBase):
    """A single issued refresh token belonging to one user session."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_id_expires_at", "user_id", "expires_at"),
        {"comment": "Rotating refresh tokens backing authenticated sessions."},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        doc="SHA-256 hex digest of the issued token. The raw token is never stored.",
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
        doc="The token issued when this one was rotated.",
    )

    # -- Session provenance -------------------------------------------
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    user: Mapped[User] = relationship(
        back_populates="refresh_tokens",
        foreign_keys=[user_id],
        lazy="joined",
    )

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= datetime.now(UTC)

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_usable(self) -> bool:
        return not self.is_revoked and not self.is_expired and not self.is_deleted

    def revoke(self, reason: str, *, at: datetime | None = None) -> None:
        if self.revoked_at is None:
            self.revoked_at = at or datetime.now(UTC)
            self.revoked_reason = reason

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id} revoked={self.is_revoked}>"
