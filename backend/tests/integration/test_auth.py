"""Integration tests for the authentication flow."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.refresh_token import RefreshToken
from app.models.user import User
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

pytestmark = pytest.mark.integration

AUTH = f"{settings.API_V1_PREFIX}/auth"


class TestLogin:
    async def test_valid_credentials_return_a_token_pair(self, client: AsyncClient, test_user: User) -> None:
        response = await client.post(
            AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["tokens"]["token_type"] == "bearer"
        assert body["data"]["tokens"]["access_token"]
        assert body["data"]["tokens"]["expires_in"] > 0

    async def test_response_never_exposes_the_password_hash(
        self, client: AsyncClient, test_user: User
    ) -> None:
        response = await client.post(
            AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )

        assert "hashed_password" not in response.text
        assert "password_reset_token_hash" not in response.text

    async def test_refresh_token_is_an_httponly_cookie_not_a_body_field(
        self, client: AsyncClient, test_user: User
    ) -> None:
        response = await client.post(
            AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )

        assert "refresh_token" not in response.json()["data"]["tokens"]
        set_cookie = response.headers.get("set-cookie", "")
        assert settings.REFRESH_COOKIE_NAME in set_cookie
        assert "HttpOnly" in set_cookie

    async def test_email_is_matched_case_insensitively(self, client: AsyncClient, test_user: User) -> None:
        response = await client.post(
            AUTH + "/login", json={"email": TEST_USER_EMAIL.upper(), "password": TEST_USER_PASSWORD}
        )
        assert response.status_code == 200

    async def test_wrong_password_is_rejected(self, client: AsyncClient, test_user: User) -> None:
        response = await client.post(
            AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": "Wrong@Password1"}
        )

        assert response.status_code == 401
        assert response.json()["success"] is False

    async def test_unknown_and_wrong_password_are_indistinguishable(
        self, client: AsyncClient, test_user: User
    ) -> None:
        """Identical responses are what stop this endpoint enumerating accounts."""
        unknown = await client.post(
            AUTH + "/login", json={"email": "nobody@example.com", "password": "Any@Password1"}
        )
        wrong = await client.post(
            AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": "Wrong@Password1"}
        )

        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["message"] == wrong.json()["message"]

    async def test_inactive_account_is_refused(self, client: AsyncClient, inactive_user: User) -> None:
        response = await client.post(
            AUTH + "/login", json={"email": inactive_user.email, "password": TEST_USER_PASSWORD}
        )
        assert response.status_code == 403

    async def test_invalid_payload_returns_field_level_errors(self, client: AsyncClient) -> None:
        response = await client.post(AUTH + "/login", json={"email": "not-an-email", "password": ""})

        assert response.status_code == 422
        body = response.json()
        assert body["success"] is False
        assert {error["field"] for error in body["errors"]} == {"email", "password"}

    async def test_repeated_failures_lock_the_account(self, client: AsyncClient, test_user: User) -> None:
        for _ in range(settings.MAX_FAILED_LOGIN_ATTEMPTS):
            await client.post(AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": "Wrong@Password1"})

        # Even the *correct* password is now refused while the lockout holds.
        response = await client.post(
            AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )
        assert response.status_code == 423

    async def test_success_is_audited(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ) -> None:
        await client.post(AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD})

        entries = (
            (await db_session.execute(select(AuditLog).where(AuditLog.action == "auth.login.succeeded")))
            .scalars()
            .all()
        )
        assert len(entries) == 1
        assert entries[0].actor_id == test_user.id


class TestCurrentUser:
    async def test_returns_the_authenticated_profile(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(AUTH + "/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["data"]
        # Since RBAC, /me answers with the session -- profile, roles and the
        # permissions the shell needs on its first render -- not a bare profile.
        assert data["user"]["email"] == TEST_USER_EMAIL
        assert isinstance(data["permissions"], list)
        assert data["is_superuser"] is True

    async def test_missing_token_is_rejected(self, client: AsyncClient) -> None:
        response = await client.get(AUTH + "/me")

        assert response.status_code == 401
        assert response.json()["success"] is False

    async def test_garbage_token_is_rejected(self, client: AsyncClient) -> None:
        response = await client.get(AUTH + "/me", headers={"Authorization": "Bearer not-a-jwt"})
        assert response.status_code == 401


class TestRefresh:
    async def test_rotation_issues_a_new_token_pair(self, client: AsyncClient, test_user: User) -> None:
        await client.post(AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD})

        response = await client.post(AUTH + "/refresh")

        assert response.status_code == 200
        assert response.json()["data"]["tokens"]["access_token"]

    async def test_the_old_token_is_revoked_on_use(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ) -> None:
        await client.post(AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD})
        original = client.cookies.get(settings.REFRESH_COOKIE_NAME)

        await client.post(AUTH + "/refresh")

        tokens = (
            (await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == test_user.id)))
            .scalars()
            .unique()
            .all()
        )

        # Deliberately not ordered by `created_at`: PostgreSQL's `now()` is
        # transaction-scoped, and the test fixture runs the whole test inside one
        # transaction, so both rows carry the *same* timestamp and their relative
        # order is arbitrary. The rotation chain is what identifies them.
        assert len(tokens) == 2
        revoked = [token for token in tokens if token.revoked_at is not None]
        live = [token for token in tokens if token.revoked_at is None]

        assert len(revoked) == 1, "rotation must revoke exactly the token it replaced"
        assert len(live) == 1
        assert revoked[0].revoked_reason == "rotated"
        assert revoked[0].replaced_by_id == live[0].id
        assert client.cookies.get(settings.REFRESH_COOKIE_NAME) != original

    async def test_replaying_a_rotated_token_kills_every_session(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ) -> None:
        """Reuse is treated as theft: the whole token family is revoked."""
        await client.post(AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD})
        stolen = client.cookies.get(settings.REFRESH_COOKIE_NAME)

        await client.post(AUTH + "/refresh")  # rotates; `stolen` is now revoked

        replay = await client.post(AUTH + "/refresh", json={"refresh_token": stolen})
        assert replay.status_code == 401

        live = (
            (
                await db_session.execute(
                    select(RefreshToken).where(
                        RefreshToken.user_id == test_user.id, RefreshToken.revoked_at.is_(None)
                    )
                )
            )
            .scalars()
            .unique()
            .all()
        )
        assert live == []

    async def test_missing_token_is_rejected(self, client: AsyncClient) -> None:
        assert (await client.post(AUTH + "/refresh")).status_code == 401


class TestLogout:
    async def test_revokes_the_current_session(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ) -> None:
        login = await client.post(
            AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )
        token = login.json()["data"]["tokens"]["access_token"]

        response = await client.post(AUTH + "/logout", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        stored = (
            (await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == test_user.id)))
            .scalars()
            .unique()
            .all()
        )
        assert all(item.revoked_at is not None for item in stored)

    async def test_the_refresh_cookie_is_cleared(self, client: AsyncClient, test_user: User) -> None:
        login = await client.post(
            AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )
        token = login.json()["data"]["tokens"]["access_token"]

        await client.post(AUTH + "/logout", headers={"Authorization": f"Bearer {token}"})

        assert not client.cookies.get(settings.REFRESH_COOKIE_NAME)

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.post(AUTH + "/logout")).status_code == 401
