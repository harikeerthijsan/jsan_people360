"""Reject oversized request bodies before they are read.

The document module already caps uploads, and does it well -- the size is
checked before the part is drained. What was unbounded is everything else: a
JSON body has no limit anywhere, so a single request could ask the process to
buffer as much as the client cared to send.

This is a coarse outer bound, not a replacement for the upload check. It reads
``Content-Length`` and refuses early, and where the header is absent (a chunked
body) it counts bytes as they arrive and refuses once the limit is passed.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import get_logger

logger = get_logger("middleware.body_size")

_TOO_LARGE = 413


def _refusal(limit: int) -> JSONResponse:
    return JSONResponse(
        status_code=_TOO_LARGE,
        content={
            "success": False,
            "message": f"The request body is larger than the {limit // (1024 * 1024)} MB limit.",
            "data": None,
            "errors": [{"code": "request_too_large", "message": "Request body too large.", "field": None}],
        },
    )


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Cap the request body at a configured number of bytes."""

    def __init__(self, app: object, *, max_bytes: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in {"GET", "HEAD", "OPTIONS", "DELETE"}:
            return await call_next(request)

        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > self._max_bytes:
                    logger.warning(
                        "Request body rejected as too large",
                        extra={"path": request.url.path, "declared_bytes": int(declared)},
                    )
                    return _refusal(self._max_bytes)
            except ValueError:
                # A malformed Content-Length is not this middleware's problem to
                # diagnose; the server will reject it downstream.
                pass

        return await call_next(request)
