"""Application exception hierarchy.

Services and repositories raise these domain exceptions; the global handlers
registered in :mod:`app.core.error_handlers` translate them into the standard
API envelope. Routes never build error responses by hand.
"""

from __future__ import annotations

from typing import Any

from fastapi import status


class AppException(Exception):
    """Base class for every expected (handled) application failure."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"
    message: str = "An unexpected error occurred."

    #: The request session rolls back on failure, which is right for business
    #: writes and wrong for security bookkeeping: a refusal that also erases
    #: the failed-attempt counter it just incremented, or the token family it
    #: just revoked, refuses nothing. Exceptions that flag this commit what was
    #: already flushed before the refusal is returned.
    preserve_writes: bool = False

    def __init__(
        self,
        message: str | None = None,
        *,
        error_code: str | None = None,
        status_code: int | None = None,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.error_code = error_code or self.error_code
        self.status_code = status_code or self.status_code
        self.details = details or []
        self.headers = headers
        super().__init__(self.message)


class BadRequestError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "bad_request"
    message = "The request could not be processed."


class ValidationError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "validation_error"
    message = "One or more fields failed validation."


class AuthenticationError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "authentication_failed"
    message = "Authentication failed."

    # Every raise site in the auth stack writes its bookkeeping first — the
    # failed-attempt counter, the lockout, the revoked token family, the
    # failure audit row — and none of it may vanish with the rollback.
    preserve_writes = True

    def __init__(self, message: str | None = None, **kwargs: Any) -> None:
        headers = kwargs.pop("headers", None) or {"WWW-Authenticate": "Bearer"}
        super().__init__(message, headers=headers, **kwargs)


class InvalidCredentialsError(AuthenticationError):
    error_code = "invalid_credentials"
    message = "Incorrect email or password."


class InvalidTokenError(AuthenticationError):
    error_code = "invalid_token"
    message = "The supplied token is invalid or has expired."


class AccountLockedError(AuthenticationError):
    status_code = status.HTTP_423_LOCKED
    error_code = "account_locked"
    message = "This account is temporarily locked after too many failed sign-in attempts."


class AccountInactiveError(AuthenticationError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "account_inactive"
    message = "This account has been deactivated."


class PermissionDeniedError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "permission_denied"
    message = "You do not have permission to perform this action."


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"
    message = "The requested resource was not found."

    def __init__(self, resource: str | None = None, **kwargs: Any) -> None:
        message = kwargs.pop("message", None)
        if message is None and resource is not None:
            message = f"{resource} was not found."
        super().__init__(message, **kwargs)


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"
    message = "The resource conflicts with the current state."


class RateLimitedError(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "rate_limited"
    message = "Too many requests. Please try again later."


class DatabaseError(AppException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "database_error"
    message = "A database error occurred while processing the request."


class ServiceUnavailableError(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "service_unavailable"
    message = "The service is temporarily unavailable."
