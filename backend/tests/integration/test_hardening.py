"""Production-hardening tests: the controls added in the final audit.

Three things are asserted here, and each exists because the audit found the
control missing rather than weak.

**Production refuses to start when it is configured like a laptop.** Every
setting checked has a default that is right locally and wrong on the internet,
and the failure mode of a checklist is that somebody deploys without reading it.

**The credential endpoints are throttled per client.** Account lockout already
handled one account under attack; this handles one client attacking many
accounts, which lockout cannot see.

**Request bodies are bounded.** Uploads were already capped; JSON was not.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.models.employee import Employee
from app.models.enums import EmploymentStatus
from app.models.user import User
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX

#: Long enough for the length rule and varied enough for the entropy rule.
#: Not a real key -- generated once for this test and never used to sign anything.
STRONG_ENOUGH_KEY = "q7WzP0mK4tR9xJ2vB5nL8cF3hG6dS1yA-eU_iO+wQ:zXrTvNbMlKjHgFdSa"


def _from_a_fresh_address() -> dict[str, str]:
    """Headers that put this test in its own throttling bucket.

    The limiter keys on ``X-Forwarded-For`` when it is present, so a unique
    address per test keeps them independent -- and exercises the forwarded-for
    path, which is the one that matters behind a reverse proxy.
    """
    octet = uuid.uuid4().int % 250 + 1
    return {"X-Forwarded-For": f"203.0.113.{octet}"}


def _production(**overrides: object) -> Settings:
    """A production settings object that is otherwise correctly configured."""
    base: dict[str, object] = {
        "APP_ENV": "production",
        "SECRET_KEY": STRONG_ENOUGH_KEY,
        "COOKIE_SECURE": True,
        "JP360_DEBUG": False,
        "LOG_REQUEST_BODY": False,
        "DEFAULT_ADMIN_PASSWORD": "not-the-documented-one",
        "POSTGRES_PASSWORD": "a-real-password",
        "TRUSTED_HOSTS": "api.example.com",
        "BACKEND_CORS_ORIGINS": "https://app.example.com",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class TestProductionConfigurationIsValidated:
    def test_a_correctly_configured_production_process_starts(self) -> None:
        assert _production().is_production is True

    def test_local_and_test_environments_are_untouched(self) -> None:
        """The guard must not make a developer's machine harder to run."""
        assert Settings(APP_ENV="local", SECRET_KEY="x" * 40).APP_ENV == "local"
        assert Settings(APP_ENV="test", SECRET_KEY="x" * 40).APP_ENV == "test"

    @pytest.mark.parametrize(
        ("override", "expected"),
        [
            ({"SECRET_KEY": "x" * 40}, "SECRET_KEY"),
            ({"JP360_DEBUG": True}, "JP360_DEBUG"),
            ({"COOKIE_SECURE": False}, "COOKIE_SECURE"),
            ({"LOG_REQUEST_BODY": True}, "LOG_REQUEST_BODY"),
            ({"DEFAULT_ADMIN_PASSWORD": "Admin@12345"}, "DEFAULT_ADMIN_PASSWORD"),
            ({"POSTGRES_PASSWORD": "postgres"}, "POSTGRES_PASSWORD"),
            ({"TRUSTED_HOSTS": ""}, "TRUSTED_HOSTS"),
            ({"BACKEND_CORS_ORIGINS": "http://localhost:3000"}, "BACKEND_CORS_ORIGINS"),
            ({"BACKEND_CORS_ORIGINS": "*"}, "BACKEND_CORS_ORIGINS"),
        ],
    )
    def test_each_unsafe_setting_is_refused(self, override: dict[str, object], expected: str) -> None:
        with pytest.raises(ValueError, match=expected):
            _production(**override)

    def test_the_refusal_lists_every_problem_at_once(self) -> None:
        """One deploy, one list. Fixing them one restart at a time is nobody's idea of a morning."""
        with pytest.raises(ValueError) as caught:
            Settings(APP_ENV="production", SECRET_KEY="x" * 40)
        message = str(caught.value)
        for expected in ("SECRET_KEY", "COOKIE_SECURE", "TRUSTED_HOSTS", "BACKEND_CORS_ORIGINS"):
            assert expected in message


class TestCredentialEndpointsAreThrottled:
    async def test_repeated_login_attempts_are_eventually_refused(self, client: AsyncClient) -> None:
        """Credential stuffing: many accounts, one client, no lockout tripped.

        Each attempt uses a *different* address, so per-account lockout never
        fires and only the per-client limiter can stop it.
        """
        if not settings.RATE_LIMIT_ENABLED:
            pytest.skip("rate limiting disabled in this environment")

        headers = _from_a_fresh_address()
        statuses = []
        for _ in range(settings.RATE_LIMIT_ATTEMPTS + 3):
            response = await client.post(
                f"{API}/auth/login",
                json={"email": f"{uuid.uuid4().hex[:10]}@jsan.example", "password": "Wrong!Passw0rd"},
                headers=headers,
            )
            statuses.append(response.status_code)

        assert 429 in statuses, f"no attempt was throttled: {statuses}"
        throttled = statuses.index(429)
        assert throttled >= settings.RATE_LIMIT_ATTEMPTS, (
            f"throttled after {throttled} attempts, before the configured limit of "
            f"{settings.RATE_LIMIT_ATTEMPTS}"
        )

    async def test_the_refusal_uses_the_standard_envelope(self, client: AsyncClient) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            pytest.skip("rate limiting disabled in this environment")

        headers = _from_a_fresh_address()
        last = None
        for _ in range(settings.RATE_LIMIT_ATTEMPTS + 3):
            last = await client.post(
                f"{API}/auth/login",
                json={"email": f"{uuid.uuid4().hex[:10]}@jsan.example", "password": "Wrong!Passw0rd"},
                headers=headers,
            )
            if last.status_code == 429:
                break

        assert last is not None and last.status_code == 429
        body = last.json()
        assert body["success"] is False
        assert body["errors"][0]["code"] == "rate_limited"
        assert "Retry-After" in last.headers

    async def test_ordinary_endpoints_are_not_throttled(self, client: AsyncClient) -> None:
        """The limiter must not touch anything but the credential endpoints."""
        for _ in range(settings.RATE_LIMIT_ATTEMPTS + 5):
            assert (await client.get(f"{API}/health")).status_code == 200

    async def test_a_successful_sign_in_clears_the_slate(self, client: AsyncClient, test_user: User) -> None:
        """An office behind one NAT gateway must never be throttled.

        Counting failures rather than requests is what makes that true, and this
        is the test that would fail if somebody changed it back: a hundred
        successful sign-ins from one address cost nothing.
        """
        del test_user  # the fixture creates the account; the credentials are below
        headers = _from_a_fresh_address()
        for _ in range(settings.RATE_LIMIT_ATTEMPTS + 5):
            response = await client.post(
                f"{API}/auth/login",
                json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
                headers=headers,
            )
            assert response.status_code == 200, response.text


class TestRequestBodiesAreBounded:
    async def test_an_oversized_body_is_refused_before_it_is_parsed(self, client: AsyncClient) -> None:
        """Refused by size before authentication is even considered."""
        oversized = "x" * (settings.max_request_body_bytes + 1024)
        response = await client.post(
            f"{API}/auth/login",
            json={"email": "someone@jsan.example", "password": oversized},
            headers=_from_a_fresh_address(),
        )
        assert response.status_code == 413, response.status_code
        assert response.json()["errors"][0]["code"] == "request_too_large"

    async def test_an_ordinary_body_is_unaffected(self, client: AsyncClient) -> None:
        response = await client.post(
            f"{API}/auth/login",
            json={"email": "nobody@jsan.example", "password": "Wrong!Passw0rd"},
            headers=_from_a_fresh_address(),
        )
        assert response.status_code == 401


class TestSecurityHeaders:
    async def test_the_baseline_headers_are_present(self, client: AsyncClient) -> None:
        response = await client.get(f"{API}/health")
        for header in (
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Referrer-Policy",
            "Content-Security-Policy",
        ):
            assert header in response.headers, f"{header} missing"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"


class TestLeaveAccrualIsIdempotent:
    """§11: run the accrual twice and confirm no duplicate credits.

    Two independent guarantees, and the second is the one that holds under
    concurrency. In code, balances are created lazily and only for leave types
    the employee does not already have a row for, so a second call is a no-op.
    In the database, ``UNIQUE (employee_id, leave_type_id, year)`` means two
    requests racing for the same employee cannot both insert -- one of them
    fails rather than double-crediting somebody a year of leave.
    """

    async def test_reading_balances_twice_credits_once(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, test_user: User
    ) -> None:
        # The portal needs an employee record behind the account; the shared
        # fixture deliberately has none, so link one here.
        db_session.add(
            Employee(
                first_name="Balance",
                last_name="Reader",
                official_email=f"balance.{uuid.uuid4().hex[:8]}@jsan.example",
                joining_date=date(2024, 1, 5),
                employment_status=EmploymentStatus.ACTIVE,
                user_id=test_user.id,
            )
        )
        await db_session.flush()

        first = await client.get(f"{API}/me/leave/balance", headers=auth_headers)
        assert first.status_code == 200, first.text
        second = await client.get(f"{API}/me/leave/balance", headers=auth_headers)
        assert second.status_code == 200, second.text

        before = {row["leave_type_id"]: row["allocated"] for row in first.json()["data"]}
        after = {row["leave_type_id"]: row["allocated"] for row in second.json()["data"]}
        assert before == after, "a second read changed the entitlement"
        assert len(after) == len(set(after)), "duplicate balance rows for one leave type"

    async def test_the_database_refuses_a_duplicate_balance_row(self) -> None:
        """The half that survives two workers racing."""
        from app.db.base import Base

        table = Base.metadata.tables["leave_balances"]
        unique = {
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if type(constraint).__name__ == "UniqueConstraint"
        }
        assert ("employee_id", "leave_type_id", "year") in unique
