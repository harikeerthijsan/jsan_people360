"""Authentication business logic.

All sign-in, refresh, logout and password-recovery rules live here. Routes are
thin: they translate HTTP to service calls and back, and own nothing else.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from app.core.config import settings
from app.core.exceptions import (
    AccountInactiveError,
    AccountLockedError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.core.logging import get_logger
from app.core.security import (
    dummy_password_verify,
    generate_opaque_token,
    hash_opaque_token,
    verify_password,
)
from app.models.audit_log import AuditAction
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest
from app.services.audit_service import AuditService
from app.services.mail_service import MailService
from app.services.token_service import IssuedTokens, TokenService
from app.services.user_service import UserService
from app.utils.datetime import ensure_utc, utc_now
from app.utils.strings import mask_email

logger = get_logger("services.auth")


@dataclass(slots=True)
class RequestOrigin:
    """Where a request came from, used for session provenance and auditing."""

    ip_address: str | None = None
    user_agent: str | None = None


@dataclass(slots=True)
class AuthenticatedSession:
    """A signed-in user together with the tokens issued for them."""

    user: User
    tokens: IssuedTokens


class AuthService:
    """Owns the authentication lifecycle."""

    def __init__(
        self,
        *,
        user_repository: UserRepository,
        user_service: UserService,
        token_service: TokenService,
        audit_service: AuditService,
        mail_service: MailService,
    ) -> None:
        self._users = user_repository
        self._user_service = user_service
        self._tokens = token_service
        self._audit = audit_service
        self._mail = mail_service

    # ------------------------------------------------------------------
    # Sign in
    # ------------------------------------------------------------------
    async def login(self, payload: LoginRequest, origin: RequestOrigin) -> AuthenticatedSession:
        """Verify credentials and start a session.

        Failure modes are deliberately indistinguishable to the client: an
        unknown email and a wrong password both return the same message and
        cost the same amount of time.
        """
        user = await self._users.get_by_email(payload.email)

        if user is None:
            dummy_password_verify()
            await self._audit.record_failure(
                AuditAction.LOGIN_FAILED,
                actor_email=payload.email,
                description="No account matches the supplied email address",
            )
            logger.info("Login failed: unknown account", extra={"email": mask_email(payload.email)})
            raise InvalidCredentialsError()

        if user.is_locked:
            await self._audit.record_failure(
                AuditAction.LOGIN_BLOCKED,
                actor_id=user.id,
                actor_email=user.email,
                description="Account is locked after repeated failed attempts",
                context={
                    "locked_until": (
                        locked.isoformat() if (locked := ensure_utc(user.locked_until)) is not None else None
                    )
                },
            )
            raise AccountLockedError()

        if not verify_password(payload.password, user.hashed_password):
            await self._register_failed_attempt(user)
            raise InvalidCredentialsError()

        if not user.is_active:
            await self._audit.record_failure(
                AuditAction.LOGIN_BLOCKED,
                actor_id=user.id,
                actor_email=user.email,
                description="Account is deactivated",
            )
            raise AccountInactiveError()

        # Successful sign-in: clear the lockout counters and record telemetry.
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = utc_now()
        user.last_login_ip = origin.ip_address

        tokens = await self._tokens.issue_session(
            user,
            remember_me=payload.remember_me,
            user_agent=origin.user_agent,
            ip_address=origin.ip_address,
        )

        await self._audit.record_success(
            AuditAction.LOGIN_SUCCEEDED,
            actor_id=user.id,
            actor_email=user.email,
            entity_type="user",
            entity_id=user.id,
            context={"remember_me": payload.remember_me},
        )
        logger.info("Login succeeded", extra={"user_id": str(user.id)})
        return AuthenticatedSession(user=user, tokens=tokens)

    async def _register_failed_attempt(self, user: User) -> None:
        """Increment the failure counter and lock the account at the threshold."""
        user.failed_login_attempts += 1
        locked = user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS

        if locked:
            user.locked_until = utc_now() + timedelta(minutes=settings.ACCOUNT_LOCKOUT_MINUTES)
            user.failed_login_attempts = 0

        await self._audit.record_failure(
            AuditAction.LOGIN_FAILED,
            actor_id=user.id,
            actor_email=user.email,
            description="Incorrect password",
            context={"locked": locked},
        )
        logger.info(
            "Login failed: incorrect password",
            extra={"user_id": str(user.id), "account_locked": locked},
        )

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    async def refresh(self, raw_refresh_token: str, origin: RequestOrigin) -> AuthenticatedSession:
        """Exchange a valid refresh token for a new token pair."""
        stored = await self._tokens.resolve_refresh_token(raw_refresh_token)

        user = await self._users.get(stored.user_id)
        if user is None or not user.is_active:
            await self._tokens.revoke_all_for_user(stored.user_id, reason="account_unavailable")
            raise InvalidTokenError("Your session is no longer valid. Please sign in again.")

        tokens = await self._tokens.rotate(
            stored,
            user,
            user_agent=origin.user_agent,
            ip_address=origin.ip_address,
        )

        await self._audit.record_success(
            AuditAction.TOKEN_REFRESHED,
            actor_id=user.id,
            actor_email=user.email,
            entity_type="refresh_token",
            entity_id=stored.id,
        )
        return AuthenticatedSession(user=user, tokens=tokens)

    # ------------------------------------------------------------------
    # Sign out
    # ------------------------------------------------------------------
    async def logout(
        self,
        *,
        raw_refresh_token: str | None,
        user_id: uuid.UUID | None,
        all_sessions: bool = False,
    ) -> None:
        """End the current session, or every session for the user."""
        if all_sessions and user_id is not None:
            revoked = await self._tokens.revoke_all_for_user(user_id, reason="logout_all")
            await self._audit.record_success(
                AuditAction.LOGOUT,
                actor_id=user_id,
                description="Signed out of all sessions",
                context={"revoked_sessions": revoked},
            )
            return

        if raw_refresh_token:
            await self._tokens.revoke_by_raw_token(raw_refresh_token, reason="logout")

        await self._audit.record_success(
            AuditAction.LOGOUT,
            actor_id=user_id,
            description="Signed out of the current session",
        )

    # ------------------------------------------------------------------
    # Password recovery
    # ------------------------------------------------------------------
    async def request_password_reset(self, email: str) -> str | None:
        """Issue a single-use reset token.

        Always succeeds from the caller's perspective — revealing whether an
        address is registered would be a user-enumeration vector. The raw token
        is returned so that non-production environments can surface it.
        """
        user = await self._users.get_by_email(email)

        if user is None or not user.is_active:
            logger.info("Password reset requested for unusable account", extra={"email": mask_email(email)})
            await self._audit.record_failure(
                AuditAction.PASSWORD_RESET_REQUESTED,
                actor_email=email,
                description="No active account matches the supplied email address",
            )
            return None

        raw_token = generate_opaque_token()
        user.password_reset_token_hash = hash_opaque_token(raw_token)
        user.password_reset_expires_at = utc_now() + timedelta(
            minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        )
        await self._users.update(user, {}, actor_id=user.id)

        await self._mail.send_password_reset(
            to_email=user.email,
            full_name=user.full_name,
            reset_token=raw_token,
        )
        await self._audit.record_success(
            AuditAction.PASSWORD_RESET_REQUESTED,
            actor_id=user.id,
            actor_email=user.email,
            entity_type="user",
            entity_id=user.id,
        )
        logger.info("Password reset issued", extra={"user_id": str(user.id)})
        return raw_token

    async def reset_password(self, *, raw_token: str, new_password: str) -> User:
        """Consume a reset token and set a new password."""
        user = await self._users.get_by_reset_token_hash(hash_opaque_token(raw_token))

        if user is None or not user.has_valid_reset_token():
            await self._audit.record_failure(
                AuditAction.PASSWORD_RESET_COMPLETED,
                actor_id=user.id if user else None,
                description="Reset token was unknown or expired",
            )
            raise InvalidTokenError("This password reset link is invalid or has expired.")

        if not user.is_active:
            raise AccountInactiveError()

        await self._user_service.set_password(user, new_password, actor_id=user.id)

        # A password change invalidates every existing session.
        revoked = await self._tokens.revoke_all_for_user(user.id, reason="password_reset")

        await self._audit.record_success(
            AuditAction.PASSWORD_RESET_COMPLETED,
            actor_id=user.id,
            actor_email=user.email,
            entity_type="user",
            entity_id=user.id,
            context={"revoked_sessions": revoked},
        )
        await self._mail.send_password_changed_notice(to_email=user.email, full_name=user.full_name)
        logger.info("Password reset completed", extra={"user_id": str(user.id)})
        return user

    async def change_password(self, user: User, *, current_password: str, new_password: str) -> User:
        """Change the password of an already authenticated user."""
        if not verify_password(current_password, user.hashed_password):
            await self._audit.record_failure(
                AuditAction.PASSWORD_CHANGED,
                actor_id=user.id,
                actor_email=user.email,
                description="Current password did not match",
            )
            raise InvalidCredentialsError("Your current password is incorrect.")

        await self._user_service.set_password(user, new_password, actor_id=user.id)
        revoked = await self._tokens.revoke_all_for_user(user.id, reason="password_changed")

        await self._audit.record_success(
            AuditAction.PASSWORD_CHANGED,
            actor_id=user.id,
            actor_email=user.email,
            entity_type="user",
            entity_id=user.id,
            context={"revoked_sessions": revoked},
        )
        await self._mail.send_password_changed_notice(to_email=user.email, full_name=user.full_name)
        return user
