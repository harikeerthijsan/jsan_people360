"""Integration tests for the health endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings

pytestmark = pytest.mark.integration


class TestLiveness:
    async def test_returns_the_standard_envelope(self, client: AsyncClient) -> None:
        response = await client.get(f"{settings.API_V1_PREFIX}/health")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"success", "message", "data", "errors"}
        assert body["success"] is True
        assert body["errors"] is None

    async def test_reports_service_identity(self, client: AsyncClient) -> None:
        body = (await client.get(f"{settings.API_V1_PREFIX}/health")).json()

        assert body["data"]["status"] == "healthy"
        assert body["data"]["service"] == settings.APP_NAME
        assert body["data"]["version"] == settings.APP_VERSION

    async def test_needs_no_authentication(self, client: AsyncClient) -> None:
        assert (await client.get(f"{settings.API_V1_PREFIX}/health")).status_code == 200

    async def test_carries_a_request_id(self, client: AsyncClient) -> None:
        response = await client.get(f"{settings.API_V1_PREFIX}/health")
        assert response.headers.get("X-Request-ID")

    async def test_echoes_an_inbound_request_id(self, client: AsyncClient) -> None:
        response = await client.get(
            f"{settings.API_V1_PREFIX}/health",
            headers={"X-Request-ID": "trace-from-the-gateway"},
        )
        assert response.headers["X-Request-ID"] == "trace-from-the-gateway"


class TestReadiness:
    async def test_reports_the_database_as_up(self, client: AsyncClient) -> None:
        response = await client.get(f"{settings.API_V1_PREFIX}/health/ready")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "ready"

        database = next(check for check in data["checks"] if check["name"] == "postgresql")
        assert database["status"] == "up"
        assert database["latency_ms"] >= 0


class TestSecurityHeaders:
    async def test_hardening_headers_are_present(self, client: AsyncClient) -> None:
        headers = (await client.get(f"{settings.API_V1_PREFIX}/health")).headers

        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert "Content-Security-Policy" in headers


class TestNotFound:
    async def test_unknown_route_returns_the_error_envelope(self, client: AsyncClient) -> None:
        response = await client.get(f"{settings.API_V1_PREFIX}/does-not-exist")

        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False
        assert body["data"] is None
        assert body["errors"][0]["code"] == "not_found"
        # The message must be presentable to an end user, not a stack trace.
        assert body["message"] == "The requested resource was not found."
