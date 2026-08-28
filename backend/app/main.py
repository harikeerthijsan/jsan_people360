"""Application factory and ASGI entry point.

Run with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.gzip import GZipMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine
from app.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)

logger = get_logger("main")

DESCRIPTION = """
The platform API for **JSAN People360**, an enterprise HR management system.

### Response format

Every endpoint — success or failure — returns the same envelope:

```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": {},
  "errors": null
}
```

### Authentication

Sign in at `POST /api/v1/auth/login`. The response carries a short-lived JWT
access token; the refresh token is set as an HttpOnly cookie and rotated on
every use. Send the access token as `Authorization: Bearer <token>`.
"""

TAGS_METADATA = [
    {"name": "Health", "description": "Liveness and readiness probes for orchestrators."},
    {"name": "Authentication", "description": "Sign in, session rotation, sign out and password recovery."},
    {"name": "Users", "description": "Self-service profile operations for the authenticated caller."},
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start-up and shut-down hooks.

    Note what is *absent*: no ``Base.metadata.create_all``. The schema is owned
    exclusively by Alembic — run ``alembic upgrade head`` before starting.
    """
    configure_logging()

    logger.info(
        "Application starting",
        extra={
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
            "docs_enabled": settings.docs_enabled,
        },
    )

    yield

    await dispose_engine()
    logger.info("Application stopped")


def create_application() -> FastAPI:
    """Build and configure the FastAPI application."""
    configure_logging()

    # Synchronous filesystem work belongs here rather than in the async
    # lifespan, where a blocking call would stall the event loop.
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        swagger_ui_parameters={"persistAuthorization": True},
        contact={"name": "JSAN People360 Platform Team"},
        license_info={"name": "Proprietary"},
    )

    # Middleware executes in reverse registration order, so the request-context
    # middleware is added last to make it the outermost layer: every log line
    # and every error response then carries a request id.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(SecurityHeadersMiddleware)

    # Outermost of the request-shaping layers, so an oversized body is refused
    # before anything downstream buffers it, and a guessing client is refused
    # before the password hasher is asked to burn a bcrypt round on them.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    if settings.RATE_LIMIT_ENABLED:
        app.add_middleware(
            RateLimitMiddleware,
            limit=settings.RATE_LIMIT_ATTEMPTS,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        )

    # Host validation. Empty means "any", which is the local default; production
    # refuses to start without it -- see Settings._reject_unsafe_production_configuration.
    if settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,  # required for the refresh-token cookie
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        """Send humans to the docs, or to the health probe when docs are off."""
        target = "/docs" if settings.docs_enabled else f"{settings.API_V1_PREFIX}/health"
        return RedirectResponse(url=target)

    return app


app = create_application()
