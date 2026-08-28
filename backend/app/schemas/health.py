"""Health check schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ComponentStatus = Literal["up", "down"]


class HealthStatus(BaseModel):
    """Liveness payload -- answers "is the process running?"."""

    status: Literal["healthy"] = "healthy"
    service: str
    version: str
    environment: str
    timestamp: datetime


class DependencyCheck(BaseModel):
    """Result of probing a single downstream dependency."""

    name: str
    status: ComponentStatus
    latency_ms: float | None = Field(default=None, ge=0)
    detail: str | None = None


class ReadinessStatus(BaseModel):
    """Readiness payload -- answers "can this process serve traffic?"."""

    status: Literal["ready", "degraded"]
    service: str
    version: str
    environment: str
    timestamp: datetime
    checks: list[DependencyCheck]
