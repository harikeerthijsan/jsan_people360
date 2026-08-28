"""Integration tests for password recovery."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import verify_password
from app.models.refresh_token import RefreshToken
from app.models.user import User
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

pytestmark = pytest.mark.integration

AUTH = f"{settings.API_V1_PREFIX}/auth"
NEW_PASSWORD = "Rotated@Password9"


async def _request_reset_token(client: AsyncClient, email: str = TEST_USER_EMAIL) -> str | None:
    response = await client.post(AUTH + "/forgot-password", json={"email": email})
    assert response.status_code == 200
    return response.json()["data"]["reset_token"]


class TestForgotPassword:
    async def test_issues_a_token_for_a_known_account(self, client: AsyncClient, test_user: User) -> None:
        assert await _request_reset_token(client)

    async def test_unknown_address_gets_the_same_response(self, client: AsyncClient, test_user: User) -> None:
        """Identical responses are what stop this endpoint enumerating accounts."""
        known = await client.post(AUTH + "/forgot-password", json={"email": TEST_USER_EMAIL})
        unknown = await client.post(AUTH + "/forgot-password", json={"email": "nobody@example.com"})

        assert known.status_code == unknown.status_code == 200
        assert known.json()["message"] == unknown.json()["message"]
        assert unknown.json()["data"]["reset_token"] is None

    async def test_the_raw_token_is_never_persisted(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ) -> None:
        raw_token = await _request_reset_token(client)

        await db_session.refresh(test_user)
        assert test_user.password_reset_token_hash != raw_token
        assert len(test_user.password_reset_token_hash or "") == 64
        assert test_user.password_reset_expires_at is not None

    async def test_invalid_email_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post(AUTH + "/forgot-password", json={"email": "not-an-email"})
        assert response.status_code == 422


class TestResetPassword:
    async def test_a_valid_token_changes_the_password(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ) -> None:
        raw_token = await _request_reset_token(client)

        response = await client.post(
            AUTH + "/reset-password",
            json={"token": raw_token, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        )

        assert response.status_code == 200
        await db_session.refresh(test_user)
        assert verify_password(NEW_PASSWORD, test_user.hashed_password)
        assert not verify_password(TEST_USER_PASSWORD, test_user.hashed_password)

    async def test_the_new_password_works_for_sign_in(self, client: AsyncClient, test_user: User) -> None:
        raw_token = await _request_reset_token(client)
        await client.post(
            AUTH + "/reset-password",
            json={"token": raw_token, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        )

        response = await client.post(
            AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": NEW_PASSWORD}
        )
        assert response.status_code == 200

    async def test_the_token_is_single_use(self, client: AsyncClient, test_user: User) -> None:
        raw_token = await _request_reset_token(client)
        first = await client.post(
            AUTH + "/reset-password",
            json={"token": raw_token, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        )
        assert first.status_code == 200

        second = await client.post(
            AUTH + "/reset-password",
            json={
                "token": raw_token,
                "new_password": "Another@Password7",
                "confirm_password": "Another@Password7",
            },
        )
        assert second.status_code == 401

    async def test_every_session_is_revoked(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ) -> None:
        await client.post(AUTH + "/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD})
        raw_token = await _request_reset_token(client)

        await client.post(
            AUTH + "/reset-password",
            json={"token": raw_token, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        )

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

    async def test_an_unknown_token_is_rejected(self, client: AsyncClient, test_user: User) -> None:
        response = await client.post(
            AUTH + "/reset-password",
            json={"token": "n" * 48, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        )
        assert response.status_code == 401

    async def test_mismatched_confirmation_is_rejected(self, client: AsyncClient, test_user: User) -> None:
        raw_token = await _request_reset_token(client)

        response = await client.post(
            AUTH + "/reset-password",
            json={
                "token": raw_token,
                "new_password": NEW_PASSWORD,
                "confirm_password": "Different@Password2",
            },
        )
        assert response.status_code == 422

    async def test_a_weak_password_is_rejected(self, client: AsyncClient, test_user: User) -> None:
        raw_token = await _request_reset_token(client)

        response = await client.post(
            AUTH + "/reset-password",
            json={"token": raw_token, "new_password": "weak", "confirm_password": "weak"},
        )
        assert response.status_code == 422


class TestChangePassword:
    async def test_changes_the_password(
        self, client: AsyncClient, test_user: User, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        response = await client.post(
            AUTH + "/change-password",
            headers=auth_headers,
            json={
                "current_password": TEST_USER_PASSWORD,
                "new_password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
            },
        )

        assert response.status_code == 200
        await db_session.refresh(test_user)
        assert verify_password(NEW_PASSWORD, test_user.hashed_password)

    async def test_the_wrong_current_password_is_rejected(
        self, client: AsyncClient, test_user: User, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            AUTH + "/change-password",
            headers=auth_headers,
            json={
                "current_password": "Wrong@Password1",
                "new_password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
            },
        )
        assert response.status_code == 401

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            AUTH + "/change-password",
            json={
                "current_password": TEST_USER_PASSWORD,
                "new_password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
            },
        )
        assert response.status_code == 401
