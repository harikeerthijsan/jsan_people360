"""Request correlation and access logging middleware."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import (
    reset_request_context,
    set_actor_id,
    set_client_ip,
    set_request_id,
    set_user_agent,
)
from app.core.logging import get_logger

logger = get_logger("http.access")

REQUEST_ID_HEADER = "X-Request-ID"
RESPONSE_TIME_HEADER = "X-Response-Time-Ms"

# Probes are polled constantly; logging them buries real traffic.
_QUIET_PATHS = frozenset({"/health", "/api/v1/health", "/api/v1/health/live", "/metrics", "/favicon.ico"})


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, expose it downstream, and log one line per request.

    The id is taken from an inbound ``X-Request-ID`` header when present, so a
    trace started at the gateway survives into the application logs.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        forwarded = request.headers.get("x-forwarded-for")
        client_ip = (
            forwarded.split(",")[0].strip()
            if forwarded
            else (request.client.host if request.client else None)
        )

        request_id_token = set_request_id(request_id)
        client_ip_token = set_client_ip(client_ip)
        user_agent_token = set_user_agent(request.headers.get("user-agent"))
        # The authentication dependency fills this in once the caller is known.
        set_actor_id(None)

        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            # The exception handlers build the response; we only record timing.
            duration_ms = (time.perf_counter() - started) * 1000
            logger.error(
                "Request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "client_ip": client_ip,
                },
            )
            raise
        finally:
            reset_request_context(request_id_token, client_ip_token, user_agent_token)

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[RESPONSE_TIME_HEADER] = f"{duration_ms:.2f}"

        if request.url.path not in _QUIET_PATHS:
            log = logger.warning if response.status_code >= 500 else logger.info
            log(
                "Request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "client_ip": client_ip,
                    "request_id": request_id,
                },
            )

        return response
