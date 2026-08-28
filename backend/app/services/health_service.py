"""Health and readiness probes."""

from __future__ import annotations

import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.health import DependencyCheck, HealthStatus, ReadinessStatus
from app.utils.datetime import utc_now

logger = get_logger("services.health")


class HealthService:
    """Answers "is the process alive?" and "can it serve traffic?"."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def liveness(self) -> HealthStatus:
        """Cheap check with no dependencies — safe for a container liveness probe."""
        return HealthStatus(
            service=settings.APP_NAME,
            version=settings.APP_VERSION,
            environment=settings.APP_ENV,
            timestamp=utc_now(),
        )

    async def readiness(self) -> ReadinessStatus:
        """Probes every downstream dependency the API needs to serve requests."""
        checks = [await self._check_database()]
        overall = "ready" if all(check.status == "up" for check in checks) else "degraded"

        return ReadinessStatus(
            status=overall,
            service=settings.APP_NAME,
            version=settings.APP_VERSION,
            environment=settings.APP_ENV,
            timestamp=utc_now(),
            checks=checks,
        )

    async def _check_database(self) -> DependencyCheck:
        started = time.perf_counter()
        try:
            await self._session.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            logger.error("Database readiness check failed", exc_info=exc)
            return DependencyCheck(
                name="postgresql",
                status="down",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                detail="The database is unreachable.",
            )

        return DependencyCheck(
            name="postgresql",
            status="up",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
