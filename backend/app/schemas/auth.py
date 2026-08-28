"""Authentication request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationInfo, field_validator

from app.schemas.user import PasswordStr, UserRead, validate_password_strength
from app.utils.strings import normalise_email


class LoginRequest(BaseModel):
    """Credentials submitted to ``POST /auth/login``."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "admin@example.com", "password": "Admin@12345"}}
    )

    email: EmailStr
    password: str = Field(min_length=1, max_length=128, description="Plaintext password.")
    remember_me: bool = Field(default=False, description="Extends the refresh token lifetime.")

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return normalise_email(value)


class TokenPair(BaseModel):
    """Access token payload returned to the client.

    The refresh token is *not* in the body -- it is set as an HttpOnly cookie so
    that JavaScript (and therefore XSS) cannot read it.
    """

    access_token: str
    # S105 suppressed: "bearer" is the RFC 6750 scheme name, not a secret.
    token_type: str = "bearer"  # noqa: S105
    expires_in: int = Field(description="Access token lifetime in seconds.")


class LoginResponse(BaseModel):
    """Successful sign-in payload: tokens plus the authenticated profile."""

    tokens: TokenPair
    user: UserRead


class RefreshRequest(BaseModel):
    """Optional body for ``POST /auth/refresh``.

    Non-browser clients that cannot hold cookies may send the refresh token
    explicitly; browsers should rely on the HttpOnly cookie.
    """

    refresh_token: str | None = Field(default=None, min_length=20, max_length=512)


class LogoutRequest(BaseModel):
    """Body for ``POST /auth/logout``."""

    all_sessions: bool = Field(default=False, description="Revoke every active session for the user.")


class ForgotPasswordRequest(BaseModel):
    """Body for ``POST /auth/forgot-password``."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return normalise_email(value)


class ResetPasswordRequest(BaseModel):
    """Body for ``POST /auth/reset-password``."""

    token: str = Field(min_length=20, max_length=512)
    new_password: PasswordStr
    confirm_password: PasswordStr

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return validate_password_strength(value)

    @field_validator("confirm_password")
    @classmethod
    def _check_match(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("new_password") and value != info.data["new_password"]:
            raise ValueError("Passwords do not match.")
        return value


class ChangePasswordRequest(BaseModel):
    """Body for ``POST /auth/change-password`` (authenticated)."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: PasswordStr
    confirm_password: PasswordStr

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return validate_password_strength(value)

    @field_validator("confirm_password")
    @classmethod
    def _check_match(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("new_password") and value != info.data["new_password"]:
            raise ValueError("Passwords do not match.")
        return value


class PasswordResetIssued(BaseModel):
    """Acknowledgement for a reset request.

    ``reset_token`` is populated only outside production, so that developers can
    complete the flow without a configured mail server.
    """

    detail: str
    reset_token: str | None = None
