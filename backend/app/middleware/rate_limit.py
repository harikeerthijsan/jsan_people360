"""Per-client throttling for the credential endpoints.

Account lockout already exists and is the right control for *one* account under
attack: five failures and it is locked. It is the wrong control for the attack
that matters more here -- credential stuffing, where a list of a thousand
addresses is tried once each. Every account stays under its lockout threshold
and nothing anywhere trips.

**Failures are counted, not requests.** This is the design decision the whole
middleware turns on. An office shares one public address, so a limiter that
counted every login would throttle a hundred people arriving at nine o'clock and
call it an attack. A limiter that counts only *rejected* attempts is invisible to
them and trips immediately on somebody guessing, because guessing is nothing but
rejected attempts.

Applied only where a request is a guess: login, forgot-password, reset-password,
refresh. Everything else is unthrottled -- rate-limiting an authenticated user
reading their own dashboard buys nothing and breaks a legitimate workload the
first time somebody exports a report.

Deliberately in-process, and that is a real limitation rather than an oversight:
with N workers the effective limit is N times the configured one, and a restart
forgets. It is a speed bump sized for a single-node deployment. A cluster wants
this in Redis or, better, at the edge -- and the honest place to say so is here,
in the code, rather than in a document nobody reads at three in the morning.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("middleware.rate_limit")

#: Path suffixes where a request is a credential guess. Matched against the end
#: of the path so the API version prefix does not have to be repeated.
THROTTLED_SUFFIXES: tuple[str, ...] = (
    "/auth/login",
    "/auth/forgot-password",
    "/auth/reset-password",
    "/auth/refresh",
)

#: Below this, the attempt was accepted and costs the caller nothing.
_FAILURE_THRESHOLD = 400


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window limiter over *failed* attempts at the credential endpoints."""

    def __init__(self, app: object, *, limit: int, window_seconds: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._limit = limit
        self._window = window_seconds
        self._failures: defaultdict[str, deque[float]] = defaultdict(deque)

    def _client_key(self, request: Request) -> str:
        """Identify the caller.

        ``X-Forwarded-For`` is honoured because the application is expected to
        sit behind a reverse proxy, and without it every request would share the
        proxy's address and one user would throttle everybody. It is a
        client-supplied header and therefore forgeable -- acceptable for a speed
        bump, and not acceptable for an access control, which is why this is
        only ever used for throttling. The proxy should overwrite it.
        """
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _recent_failures(self, key: str, now: float) -> deque[float]:
        window = self._failures[key]
        while window and now - window[0] > self._window:
            window.popleft()
        return window

    def _evict_idle(self, now: float) -> None:
        """Bound the bookkeeping.

        Without this, an attacker rotating source addresses turns the limiter
        itself into the memory leak.
        """
        if len(self._failures) <= settings.RATE_LIMIT_MAX_TRACKED_CLIENTS:
            return
        stale = [key for key, hits in self._failures.items() if not hits or now - hits[-1] > self._window]
        for key in stale:
            del self._failures[key]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method != "POST" or not request.url.path.endswith(THROTTLED_SUFFIXES):
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        failures = self._recent_failures(key, now)

        if len(failures) >= self._limit:
            retry_after = max(1, int(self._window - (now - failures[0])))
            # Logged as a security event, and without the body: the interesting
            # fact is that one address is guessing, not what it guessed.
            logger.warning(
                "Rate limit exceeded",
                extra={"path": request.url.path, "client": key, "limit": self._limit},
            )
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "message": "Too many failed attempts. Please wait a moment and try again.",
                    "data": None,
                    "errors": [{"code": "rate_limited", "message": "Too many attempts.", "field": None}],
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)

        if response.status_code >= _FAILURE_THRESHOLD:
            failures.append(time.monotonic())
            self._evict_idle(now)
        elif failures:
            # A success clears the slate for that client. Somebody who mistyped
            # their password four times and then got it right is not an attacker,
            # and should not spend the rest of the window one slip from a refusal.
            failures.clear()

        return response
