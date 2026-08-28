"""Cryptographic primitives: password hashing, JWT access tokens, opaque tokens.

Design notes
------------
* Passwords use bcrypt. bcrypt silently truncates input beyond 72 bytes, so the
  maximum password length is enforced here *and* in the Pydantic schemas.
* Access tokens are short-lived signed JWTs carried in the ``Authorization``
  header.
* Refresh and password-reset tokens are opaque, high-entropy random strings.
  Only their SHA-256 digest is persisted, so a database leak cannot be replayed.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, Final, Literal

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError as PyJWTInvalidTokenError

from app.core.config import settings
from app.core.exceptions import InvalidTokenError

TokenType = Literal["access"]

MAX_PASSWORD_BYTES: Final[int] = 72
_OPAQUE_TOKEN_BYTES: Final[int] = 48


# ----------------------------------------------------------------------
# Passwords
# ----------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must not exceed {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Constant-time verification of a plaintext password against its hash."""
    try:
        encoded = password.encode("utf-8")
        if len(encoded) > MAX_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(encoded, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed stored hash -- treat as a failed login, never a crash.
        return False


@lru_cache(maxsize=1)
def _timing_equalizer_hash() -> bytes:
    """A real bcrypt hash, computed once, used only to normalise login timing."""
    return bcrypt.hashpw(
        b"jsan-people360-timing-equalizer",
        bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS),
    )


def dummy_password_verify() -> None:
    """Burn a bcrypt cycle so unknown emails cost the same as known ones.

    Without this, the response time of a login attempt leaks whether an account
    exists (user enumeration).
    """
    bcrypt.checkpw(b"jsan-people360-timing-equalizer", _timing_equalizer_hash())


# ----------------------------------------------------------------------
# Opaque tokens (refresh tokens, password reset tokens)
# ----------------------------------------------------------------------
def generate_opaque_token() -> str:
    """Return a URL-safe, cryptographically random token."""
    return secrets.token_urlsafe(_OPAQUE_TOKEN_BYTES)


def hash_opaque_token(token: str) -> str:
    """Return the SHA-256 hex digest stored in place of the raw token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(token: str, token_hash: str) -> bool:
    """Constant-time comparison of an opaque token against its stored digest."""
    return hmac.compare_digest(hash_opaque_token(token), token_hash)


# ----------------------------------------------------------------------
# JWT access tokens
# ----------------------------------------------------------------------
def create_access_token(
    subject: uuid.UUID | str,
    *,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, datetime]:
    """Create a signed access token.

    Returns the encoded token and its absolute expiry so callers can report
    ``expires_in`` without decoding the token again.
    """
    now = datetime.now(UTC)
    expires_at = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token, raising :class:`InvalidTokenError`."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except PyJWTInvalidTokenError as exc:
        raise InvalidTokenError("Your session is invalid or has expired. Please sign in again.") from exc

    if payload.get("type") != "access":
        raise InvalidTokenError("An access token is required for this operation.")

    return payload


def get_subject_id(payload: dict[str, Any]) -> uuid.UUID:
    """Extract and validate the user id from a decoded token payload."""
    try:
        return uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("The token subject is malformed.") from exc
