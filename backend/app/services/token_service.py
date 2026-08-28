"""Issue, rotate and revoke authentication tokens.

Refresh token strategy
----------------------
1. Refresh tokens are opaque 64-byte random strings; only the SHA-256 digest is
   persisted, so a database dump cannot be replayed.
2. Every use rotates the token: the presented row is revoked and linked to its
   replacement.
3. Presenting an already-revoked token is treated as theft — the entire token
   family for that user is revoked and the event is audited.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.exceptions import InvalidTokenError
from app.core.logging import get_logger
from app.core.security import create_access_token, generate_opaque_token, hash_opaque_token
from app.models.audit_log import AuditAction
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.schemas.auth import TokenPair
from app.services.audit_service import AuditService
from app.utils.datetime import ensure_utc, utc_now
from app.utils.strings import truncate

logger = get_logger("services.token")

# Sessions started with "remember me" live longer before requiring a full sign-in.
REMEMBER_ME_MULTIPLIER = 4


@dataclass(slots=True)
class IssuedTokens:
    """Result of issuing a session: the API payload plus the raw refresh token.

    The raw refresh token exists only long enough for the route to set the
    HttpOnly cookie; it is never returned in a response body.
    """

    token_pair: TokenPair
    refresh_token: str
    refresh_expires_at: datetime
    refresh_token_record: RefreshToken


class TokenService:
    """Owns the lifecycle of access and refresh tokens."""

    def __init__(self, refresh_token_repository: RefreshTokenRepository, audit_service: AuditService) -> None:
        self._refresh_tokens = refresh_token_repository
        self._audit = audit_service

    # ------------------------------------------------------------------
    # Issuing
    # ------------------------------------------------------------------
    async def issue_session(
        self,
        user: User,
        *,
        remember_me: bool = False,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> IssuedTokens:
        """Mint a new access token and a fresh refresh token row."""
        access_token, access_expires_at = create_access_token(
            user.id,
            extra_claims={"email": user.email},
        )

        raw_refresh_token = generate_opaque_token()
        lifetime_days = settings.REFRESH_TOKEN_EXPIRE_DAYS * (REMEMBER_ME_MULTIPLIER if remember_me else 1)
        refresh_expires_at = utc_now() + timedelta(days=lifetime_days)

        record = await self._refresh_tokens.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_opaque_token(raw_refresh_token),
                expires_at=refresh_expires_at,
                user_agent=truncate(user_agent, 512),
                ip_address=ip_address,
            ),
            actor_id=user.id,
        )

        token_pair = TokenPair(
            access_token=access_token,
            token_type="bearer",  # noqa: S106 - the RFC 6750 scheme name, not a secret
            expires_in=int((access_expires_at - utc_now()).total_seconds()),
        )
        return IssuedTokens(
            token_pair=token_pair,
            refresh_token=raw_refresh_token,
            refresh_expires_at=refresh_expires_at,
            refresh_token_record=record,
        )

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------
    async def resolve_refresh_token(self, raw_token: str) -> RefreshToken:
        """Validate a presented refresh token, detecting replay.

        Raises :class:`InvalidTokenError` for unknown, expired or revoked
        tokens. A revoked-but-known token additionally revokes the whole family.
        """
        stored = await self._refresh_tokens.get_by_token_hash(hash_opaque_token(raw_token))

        if stored is None:
            raise InvalidTokenError("Your session has expired. Please sign in again.")

        if stored.is_revoked:
            # The token was already rotated or explicitly revoked. Someone is
            # replaying it — assume compromise and kill every live session.
            revoked_count = await self._refresh_tokens.revoke_all_for_user(
                stored.user_id, reason="refresh_token_reuse_detected"
            )
            await self._audit.record_failure(
                AuditAction.TOKEN_REUSE_DETECTED,
                actor_id=stored.user_id,
                entity_type="refresh_token",
                entity_id=stored.id,
                description="A revoked refresh token was presented; every live session was revoked.",
                context={"revoked_sessions": revoked_count},
            )
            logger.warning(
                "Refresh token reuse detected; revoked all sessions for user",
                extra={"user_id": str(stored.user_id), "revoked_sessions": revoked_count},
            )
            raise InvalidTokenError("Your session is no longer valid. Please sign in again.")

        expires_at = ensure_utc(stored.expires_at)
        if expires_at is None or expires_at <= utc_now():
            raise InvalidTokenError("Your session has expired. Please sign in again.")

        if stored.deleted_at is not None:
            raise InvalidTokenError("Your session is no longer valid. Please sign in again.")

        return stored

    async def rotate(
        self,
        stored: RefreshToken,
        user: User,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> IssuedTokens:
        """Consume a valid refresh token and issue its replacement."""
        remember_me = self._was_long_lived(stored)
        issued = await self.issue_session(
            user,
            remember_me=remember_me,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        stored.revoke("rotated")
        stored.replaced_by_id = issued.refresh_token_record.id
        await self._refresh_tokens.session.flush()

        return issued

    # ------------------------------------------------------------------
    # Revocation
    # ------------------------------------------------------------------
    async def revoke(self, stored: RefreshToken, *, reason: str = "logout") -> None:
        stored.revoke(reason)
        await self._refresh_tokens.session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, reason: str) -> int:
        return await self._refresh_tokens.revoke_all_for_user(user_id, reason=reason)

    async def revoke_by_raw_token(self, raw_token: str, *, reason: str = "logout") -> bool:
        """Best-effort revocation used by logout; unknown tokens are ignored."""
        stored = await self._refresh_tokens.get_by_token_hash(hash_opaque_token(raw_token))
        if stored is None or stored.is_revoked:
            return False
        await self.revoke(stored, reason=reason)
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _was_long_lived(stored: RefreshToken) -> bool:
        """Preserve the original "remember me" choice across rotations."""
        created_at = ensure_utc(stored.created_at)
        expires_at = ensure_utc(stored.expires_at)
        if created_at is None or expires_at is None:
            return False
        standard = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        # Allow an hour of slack for clock skew and request latency.
        return (expires_at - created_at) > standard + timedelta(hours=1)
