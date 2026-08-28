"""Global exception handlers.

These handlers guarantee that *every* failure -- domain error, validation
error, database error, unhandled crash, 404 or 500 -- leaves the application
in the standard API envelope with a user-friendly message. Internal details
are logged, never returned to the client.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.context import get_request_id
from app.core.exceptions import AppException
from app.core.logging import get_logger
from app.schemas.common import APIErrorResponse, ErrorDetail

logger = get_logger("core.errors")

# Friendly copy for the status codes clients see most often.
_STATUS_MESSAGES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "The request could not be processed.",
    status.HTTP_401_UNAUTHORIZED: "You need to sign in to continue.",
    status.HTTP_403_FORBIDDEN: "You do not have permission to perform this action.",
    status.HTTP_404_NOT_FOUND: "The requested resource was not found.",
    status.HTTP_405_METHOD_NOT_ALLOWED: "This action is not supported for the requested resource.",
    status.HTTP_409_CONFLICT: "The resource conflicts with the current state.",
    status.HTTP_413_CONTENT_TOO_LARGE: "The uploaded content is too large.",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "One or more fields failed validation.",
    status.HTTP_429_TOO_MANY_REQUESTS: "Too many requests. Please try again later.",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "Something went wrong on our side. Please try again.",
    status.HTTP_503_SERVICE_UNAVAILABLE: "The service is temporarily unavailable.",
}

_STATUS_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "permission_denied",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_413_CONTENT_TOO_LARGE: "payload_too_large",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
    status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
}


def _envelope(
    *,
    status_code: int,
    message: str,
    errors: list[ErrorDetail] | None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = APIErrorResponse(success=False, message=message, data=None, errors=errors)
    response_headers = dict(headers or {})
    request_id = get_request_id()
    if request_id:
        response_headers.setdefault("X-Request-ID", request_id)
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers=response_headers,
    )


def _location_to_field(location: tuple[Any, ...]) -> str | None:
    """Convert a Pydantic error location into a dotted client-facing field path."""
    parts = [str(part) for part in location if part not in ("body", "query", "path", "header", "cookie")]
    return ".".join(parts) if parts else None


def _validation_details(errors: Sequence[Mapping[str, Any]]) -> list[ErrorDetail]:
    return [
        ErrorDetail(
            code=str(error.get("type", "validation_error")),
            message=str(error.get("msg", "Invalid value.")),
            field=_location_to_field(tuple(error.get("loc", ()))),
        )
        for error in errors
    ]


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle every expected domain failure."""
    log = logger.warning if exc.status_code < 500 else logger.error
    log(
        "Handled application exception",
        extra={
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method,
        },
        exc_info=exc.status_code >= 500,
    )

    errors = [ErrorDetail(**detail) for detail in exc.details] or [
        ErrorDetail(code=exc.error_code, message=exc.message)
    ]
    return _envelope(status_code=exc.status_code, message=exc.message, errors=errors, headers=exc.headers)


async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle inbound payload / query / path validation failures."""
    details = _validation_details(exc.errors())
    logger.info(
        "Request validation failed",
        extra={"path": request.url.path, "method": request.method, "error_count": len(details)},
    )
    return _envelope(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        message=_STATUS_MESSAGES[status.HTTP_422_UNPROCESSABLE_CONTENT],
        errors=details,
    )


async def pydantic_validation_handler(request: Request, exc: PydanticValidationError) -> JSONResponse:
    """Handle model validation raised inside the service layer."""
    details = _validation_details(exc.errors())
    logger.warning(
        "Domain model validation failed",
        extra={"path": request.url.path, "method": request.method, "error_count": len(details)},
    )
    return _envelope(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        message=_STATUS_MESSAGES[status.HTTP_422_UNPROCESSABLE_CONTENT],
        errors=details,
    )


async def response_validation_handler(request: Request, exc: ResponseValidationError) -> JSONResponse:
    """A response that does not match its declared schema is always our bug."""
    logger.error(
        "Response validation failed",
        extra={"path": request.url.path, "method": request.method},
        exc_info=exc,
    )
    return _envelope(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=_STATUS_MESSAGES[status.HTTP_500_INTERNAL_SERVER_ERROR],
        errors=[
            ErrorDetail(code="response_validation_error", message="The server produced an invalid response.")
        ],
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle framework-raised HTTP errors, including 404 and 405."""
    code = _STATUS_CODES.get(exc.status_code, "http_error")
    default_message = _STATUS_MESSAGES.get(exc.status_code, "The request could not be completed.")

    # Starlette puts a terse default in ``detail``; prefer our friendlier copy
    # unless the raiser supplied a custom string.
    detail = exc.detail if isinstance(exc.detail, str) else None
    message = (
        detail if detail and detail.lower() not in {"not found", "method not allowed"} else default_message
    )

    if exc.status_code >= 500:
        logger.error(
            "HTTP error", extra={"path": request.url.path, "status_code": exc.status_code}, exc_info=exc
        )
    else:
        logger.info("HTTP error", extra={"path": request.url.path, "status_code": exc.status_code})

    headers = dict(getattr(exc, "headers", None) or {})
    return _envelope(
        status_code=exc.status_code,
        message=message,
        errors=[ErrorDetail(code=code, message=message)],
        headers=headers,
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Unique / foreign key / check constraint violations become 409s."""
    logger.warning(
        "Database integrity error",
        extra={"path": request.url.path, "method": request.method, "orig": str(getattr(exc, "orig", exc))},
    )
    message = "The operation conflicts with existing data."
    return _envelope(
        status_code=status.HTTP_409_CONFLICT,
        message=message,
        errors=[ErrorDetail(code="integrity_error", message=message)],
    )


async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Any other database failure is a 500 with the detail kept server-side."""
    logger.error(
        "Database error",
        extra={"path": request.url.path, "method": request.method},
        exc_info=exc,
    )
    message = "A database error occurred while processing the request."
    return _envelope(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=message,
        errors=[ErrorDetail(code="database_error", message=message)],
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last line of defence: never leak a stack trace to the client."""
    logger.critical(
        "Unhandled exception",
        extra={"path": request.url.path, "method": request.method},
        exc_info=exc,
    )
    message = _STATUS_MESSAGES[status.HTTP_500_INTERNAL_SERVER_ERROR]
    detail = repr(exc) if settings.debug else message
    return _envelope(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=message,
        errors=[ErrorDetail(code="internal_error", message=detail)],
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire every handler onto the application instance."""
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, request_validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ResponseValidationError, response_validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(PydanticValidationError, pydantic_validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, integrity_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
