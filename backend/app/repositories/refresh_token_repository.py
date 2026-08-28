"""Persistence operations for :class:`app.models.refresh_token.RefreshToken`."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update

from app.models.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Queries scoped to issued refresh tokens."""

    model = RefreshToken

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        """Fetch a token row regardless of revocation state.

        Revoked rows must remain visible so that replay of a rotated token can
        be detected rather than silently treated as "unknown token".
        """
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def list_active_for_user(self, user_id: uuid.UUID) -> Sequence[RefreshToken]:
        stmt = (
            self._base_select()
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(UTC),
            )
            .order_by(RefreshToken.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().all()

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, reason: str) -> int:
        """Revoke every live token for a user. Returns the number affected.

        Used on logout-everywhere, password reset and refresh-token reuse.
        """
        now = datetime.now(UTC)
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.deleted_at.is_(None),
            )
            .values(revoked_at=now, revoked_reason=reason, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        result = cast(CursorResult[Any], await self.session.execute(stmt))
        return int(result.rowcount or 0)

    async def purge_expired(self, *, older_than: datetime | None = None) -> int:
        """Soft delete tokens that expired before the cut-off (retention job)."""
        cutoff = older_than or datetime.now(UTC)
        now = datetime.now(UTC)
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.expires_at < cutoff, RefreshToken.deleted_at.is_(None))
            .values(deleted_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        result = cast(CursorResult[Any], await self.session.execute(stmt))
        return int(result.rowcount or 0)
