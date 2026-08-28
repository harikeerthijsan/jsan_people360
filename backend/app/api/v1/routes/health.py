"""Health check endpoints.

Deliberately unauthenticated so that orchestrators can probe them, and
deliberately free of business logic — everything lives in ``HealthService``.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import HealthSvc
from app.schemas.common import APIResponse
from app.schemas.health import HealthStatus, ReadinessStatus

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "",
    response_model=APIResponse[HealthStatus],
    summary="Liveness probe",
    description="Confirms the API process is running. Performs no dependency checks.",
)
async def health_check(service: HealthSvc) -> APIResponse[HealthStatus]:
    return APIResponse.ok(service.liveness(), message="Service is healthy")


@router.get(
    "/ready",
    response_model=APIResponse[ReadinessStatus],
    summary="Readiness probe",
    description="Verifies every downstream dependency. Returns 503 when the API cannot serve traffic.",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "One or more dependencies are unavailable."}
    },
)
async def readiness_check(service: HealthSvc, response: Response) -> APIResponse[ReadinessStatus]:
    result = await service.readiness()
    if result.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return APIResponse(
            success=False,
            message="One or more dependencies are unavailable",
            data=result,
            errors=None,
        )
    return APIResponse.ok(result, message="Service is ready")
