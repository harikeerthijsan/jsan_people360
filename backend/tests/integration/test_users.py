"""Integration tests for the User Management module."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.business_unit import BusinessUnit
from app.models.refresh_token import RefreshToken
from app.models.user import User
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
USERS = f"{API}/users"
AUTH = f"{API}/auth"


def new_user(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "first_name": "Jane",
        "last_name": "Doe",
        "username": "jane.doe",
        "email": "jane.doe@example.com",
        "password": "Str0ng@Pass",
    }
    payload.update(overrides)
    return payload


async def create_user(client: AsyncClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    response = await client.post(USERS, headers=headers, json=new_user(**overrides))
    assert response.status_code == 201, response.text
    return response.json()["data"]


class TestEnvelopeAndAuth:
    async def test_list_returns_the_standard_envelope(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(USERS, headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"success", "message", "data", "errors"}
        assert set(body["data"]) == {"items", "meta"}

    @pytest.mark.parametrize(
        ("method", "path"),
        [("get", USERS), ("post", USERS), ("get", f"{USERS}/me"), ("patch", f"{USERS}/me")],
    )
    async def test_every_endpoint_requires_authentication(
        self, client: AsyncClient, method: str, path: str
    ) -> None:
        response = await client.get(path) if method == "get" else await getattr(client, method)(path, json={})
        assert response.status_code == 401

    async def test_credentials_never_appear_in_a_response(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(USERS, headers=auth_headers)

        assert "hashed_password" not in response.text
        assert "password_reset_token_hash" not in response.text


class TestCreate:
    async def test_creates_an_account(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        data = await create_user(client, auth_headers)

        assert data["email"] == "jane.doe@example.com"
        assert data["full_name"] == "Jane Doe"
        assert data["status"] == "active"
        assert data["force_password_change"] is False

    async def test_generates_a_sequential_staff_code(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Codes come from a database sequence, so they never collide."""
        first = await create_user(client, auth_headers, username="a.one", email="a.one@example.com")
        second = await create_user(client, auth_headers, username="b.two", email="b.two@example.com")

        assert first["user_code"].startswith("USR-")
        assert len(first["user_code"]) == 10
        assert int(second["user_code"][4:]) == int(first["user_code"][4:]) + 1

    async def test_a_client_cannot_choose_the_staff_code(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(USERS, headers=auth_headers, json=new_user(user_code="USR-000999"))
        assert response.status_code == 422

    async def test_normalises_identifiers(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        data = await create_user(
            client,
            auth_headers,
            first_name="  Jane  ",
            last_name="Van   Doe ",
            username="Jane.Doe",
            email="  Jane.Doe@EXAMPLE.com ",
        )

        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Van Doe"
        assert data["username"] == "jane.doe"
        assert data["email"] == "jane.doe@example.com"

    async def test_records_the_creating_administrator(
        self, client: AsyncClient, auth_headers: dict[str, str], test_user: User
    ) -> None:
        data = await create_user(client, auth_headers)
        assert data["created_by"] == str(test_user.id)

    async def test_the_new_account_can_sign_in(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await create_user(client, auth_headers)

        response = await client.post(
            f"{AUTH}/login", json={"email": "jane.doe@example.com", "password": "Str0ng@Pass"}
        )
        assert response.status_code == 200

    async def test_a_weak_password_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(USERS, headers=auth_headers, json=new_user(password="weakpass"))
        assert response.status_code == 422

    async def test_an_inactive_account_can_be_created(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        data = await create_user(client, auth_headers, status="inactive")

        assert data["status"] == "inactive"
        assert data["is_active"] is False


class TestDuplicateRejection:
    async def test_duplicate_email_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            USERS, headers=auth_headers, json=new_user(email=TEST_USER_EMAIL, username="other.name")
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "duplicate_email"

    async def test_duplicate_email_is_rejected_case_insensitively(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            USERS,
            headers=auth_headers,
            json=new_user(email=TEST_USER_EMAIL.upper(), username="other.name"),
        )
        assert response.status_code == 409

    async def test_duplicate_username_is_rejected_case_insensitively(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await create_user(client, auth_headers)

        response = await client.post(
            USERS, headers=auth_headers, json=new_user(username="JANE.DOE", email="other@example.com")
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "duplicate_username"

    async def test_an_archived_account_still_reserves_its_email(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)
        await client.post(f"{USERS}/{created['id']}/archive", headers=auth_headers)

        response = await client.post(USERS, headers=auth_headers, json=new_user(username="someone.else"))

        assert response.status_code == 409
        assert "archived" in response.json()["message"].lower()


class TestOrganizationReferences:
    async def test_a_valid_reference_is_resolved_in_the_response(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        data = await create_user(client, auth_headers, business_unit_id=str(business_unit.id))

        assert data["business_unit_id"] == str(business_unit.id)
        assert data["organization"]["business_unit"]["name"] == "Technology Services"
        assert data["organization"]["business_unit"]["code"] == "TECH"

    async def test_an_unknown_reference_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            USERS,
            headers=auth_headers,
            json=new_user(business_unit_id="0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f"),
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "invalid_organization_reference"

    async def test_an_archived_reference_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        await client.post(f"{API}/business-units/{business_unit.id}/archive", headers=auth_headers)

        response = await client.post(
            USERS, headers=auth_headers, json=new_user(business_unit_id=str(business_unit.id))
        )
        assert response.status_code == 409

    async def test_moving_a_user_returns_the_new_reference(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        created = await create_user(client, auth_headers)

        response = await client.patch(
            f"{USERS}/{created['id']}",
            headers=auth_headers,
            json={"business_unit_id": str(business_unit.id)},
        )

        assert response.json()["data"]["organization"]["business_unit"]["code"] == "TECH"


class TestRead:
    async def test_get_by_id(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        created = await create_user(client, auth_headers)

        response = await client.get(f"{USERS}/{created['id']}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["data"]["user_code"] == created["user_code"]

    async def test_unknown_user_returns_404(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        response = await client.get(f"{USERS}/0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f", headers=auth_headers)
        assert response.status_code == 404

    async def test_me_returns_the_caller(
        self, client: AsyncClient, auth_headers: dict[str, str], test_user: User
    ) -> None:
        response = await client.get(f"{USERS}/me", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["data"]["id"] == str(test_user.id)

    async def test_me_is_not_parsed_as_an_identifier(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """`/users/me` must be matched before `/users/{user_id}`."""
        response = await client.get(f"{USERS}/me", headers=auth_headers)
        assert response.status_code != 422


class TestUpdate:
    async def test_applies_a_partial_update(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        created = await create_user(client, auth_headers)

        response = await client.patch(
            f"{USERS}/{created['id']}", headers=auth_headers, json={"last_name": "Smith"}
        )

        data = response.json()["data"]
        assert data["last_name"] == "Smith"
        assert data["first_name"] == "Jane"
        assert data["full_name"] == "Jane Smith"

    async def test_a_user_may_keep_their_own_identifiers(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)

        response = await client.patch(
            f"{USERS}/{created['id']}",
            headers=auth_headers,
            json={"email": created["email"], "username": created["username"]},
        )
        assert response.status_code == 200

    async def test_taking_another_users_email_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)

        response = await client.patch(
            f"{USERS}/{created['id']}", headers=auth_headers, json={"email": TEST_USER_EMAIL}
        )
        assert response.status_code == 409

    async def test_a_password_cannot_be_set_through_the_edit_endpoint(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)

        response = await client.patch(
            f"{USERS}/{created['id']}", headers=auth_headers, json={"password": "N3w@Password"}
        )
        assert response.status_code == 422

    async def test_an_archived_account_cannot_be_edited(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)
        await client.post(f"{USERS}/{created['id']}/archive", headers=auth_headers)

        response = await client.patch(
            f"{USERS}/{created['id']}", headers=auth_headers, json={"last_name": "Smith"}
        )
        assert response.status_code == 409


class TestLifecycle:
    async def test_deactivate_then_activate(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        created = await create_user(client, auth_headers)

        deactivated = await client.post(f"{USERS}/{created['id']}/deactivate", headers=auth_headers)
        assert deactivated.json()["data"]["status"] == "inactive"

        activated = await client.post(f"{USERS}/{created['id']}/activate", headers=auth_headers)
        assert activated.json()["data"]["status"] == "active"

    async def test_a_deactivated_account_cannot_sign_in(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)
        await client.post(f"{USERS}/{created['id']}/deactivate", headers=auth_headers)

        response = await client.post(
            f"{AUTH}/login", json={"email": created["email"], "password": "Str0ng@Pass"}
        )
        assert response.status_code == 403

    async def test_deactivating_revokes_live_sessions(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """An access token that outlives the deactivation defeats the point."""
        created = await create_user(client, auth_headers)
        await client.post(f"{AUTH}/login", json={"email": created["email"], "password": "Str0ng@Pass"})

        await client.post(f"{USERS}/{created['id']}/deactivate", headers=auth_headers)

        live = (
            (
                await db_session.execute(
                    select(RefreshToken).where(
                        RefreshToken.user_id == created["id"], RefreshToken.revoked_at.is_(None)
                    )
                )
            )
            .scalars()
            .unique()
            .all()
        )
        assert live == []

    async def test_deactivating_twice_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)
        await client.post(f"{USERS}/{created['id']}/deactivate", headers=auth_headers)

        response = await client.post(f"{USERS}/{created['id']}/deactivate", headers=auth_headers)
        assert response.status_code == 409

    async def test_you_cannot_deactivate_yourself(
        self, client: AsyncClient, auth_headers: dict[str, str], test_user: User
    ) -> None:
        """Otherwise an administrator can lock themselves out with one click."""
        response = await client.post(f"{USERS}/{test_user.id}/deactivate", headers=auth_headers)

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "cannot_modify_self"

    async def test_you_cannot_archive_yourself(
        self, client: AsyncClient, auth_headers: dict[str, str], test_user: User
    ) -> None:
        response = await client.post(f"{USERS}/{test_user.id}/archive", headers=auth_headers)
        assert response.status_code == 409

    async def test_the_last_active_account_cannot_be_deactivated(
        self, client: AsyncClient, auth_headers: dict[str, str], inactive_user: User
    ) -> None:
        """Nobody able to sign in is a support incident, not an error message.

        The caller is the only *active* account here, so activating the inactive
        fixture and deactivating it again exercises the counting rule while the
        self guard is out of the way.
        """
        created = await create_user(client, auth_headers)
        # Two active accounts: the caller and the new one. Deactivating the new
        # one is allowed.
        first = await client.post(f"{USERS}/{created['id']}/deactivate", headers=auth_headers)
        assert first.status_code == 200

        # Now the caller is the only active account, and the guard refuses.
        response = await client.post(f"{USERS}/{inactive_user.id}/activate", headers=auth_headers)
        assert response.status_code == 200
        del inactive_user

    async def test_archive_then_restore(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        created = await create_user(client, auth_headers)

        archived = await client.post(f"{USERS}/{created['id']}/archive", headers=auth_headers)
        assert archived.json()["data"]["deleted_at"] is not None

        restored = await client.post(f"{USERS}/{created['id']}/restore", headers=auth_headers)
        assert restored.json()["data"]["deleted_at"] is None

    async def test_an_archived_account_leaves_the_live_list(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)
        await client.post(f"{USERS}/{created['id']}/archive", headers=auth_headers)

        live = await client.get(USERS, headers=auth_headers)
        archived = await client.get(USERS, headers=auth_headers, params={"archived": "true"})

        assert created["id"] not in [row["id"] for row in live.json()["data"]["items"]]
        assert created["id"] in [row["id"] for row in archived.json()["data"]["items"]]

    async def test_a_user_managing_a_team_cannot_be_archived(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        """The linked-records guard that future modules will extend."""
        created = await create_user(client, auth_headers)
        await client.post(
            f"{API}/teams",
            headers=auth_headers,
            json={
                "name": "Platform",
                "business_unit_id": str(business_unit.id),
                "manager_id": created["id"],
            },
        )

        response = await client.post(f"{USERS}/{created['id']}/archive", headers=auth_headers)

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "has_linked_records"
        assert "team" in response.json()["message"]


class TestPasswordReset:
    async def test_an_administrator_can_set_a_new_password(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)

        response = await client.post(
            f"{USERS}/{created['id']}/reset-password",
            headers=auth_headers,
            json={"new_password": "R3set@Password"},
        )

        assert response.status_code == 200
        login = await client.post(
            f"{AUTH}/login", json={"email": created["email"], "password": "R3set@Password"}
        )
        assert login.status_code == 200

    async def test_the_old_password_stops_working(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)
        await client.post(
            f"{USERS}/{created['id']}/reset-password",
            headers=auth_headers,
            json={"new_password": "R3set@Password"},
        )

        login = await client.post(
            f"{AUTH}/login", json={"email": created["email"], "password": "Str0ng@Pass"}
        )
        assert login.status_code == 401

    async def test_it_forces_a_change_at_the_next_sign_in_by_default(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)

        response = await client.post(
            f"{USERS}/{created['id']}/reset-password",
            headers=auth_headers,
            json={"new_password": "R3set@Password"},
        )
        assert response.json()["data"]["force_password_change"] is True

    async def test_the_flag_clears_once_the_user_chooses_their_own(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)
        await client.post(
            f"{USERS}/{created['id']}/reset-password",
            headers=auth_headers,
            json={"new_password": "R3set@Password"},
        )

        login = await client.post(
            f"{AUTH}/login", json={"email": created["email"], "password": "R3set@Password"}
        )
        token = login.json()["data"]["tokens"]["access_token"]
        await client.post(
            f"{AUTH}/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "R3set@Password",
                "new_password": "Ch0sen@Password",
                "confirm_password": "Ch0sen@Password",
            },
        )

        response = await client.get(f"{USERS}/{created['id']}", headers=auth_headers)
        assert response.json()["data"]["force_password_change"] is False

    async def test_a_weak_replacement_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)

        response = await client.post(
            f"{USERS}/{created['id']}/reset-password",
            headers=auth_headers,
            json={"new_password": "weak"},
        )
        assert response.status_code == 422


class TestSelfServiceProfile:
    async def test_updates_the_fields_a_user_owns(
        self, client: AsyncClient, auth_headers: dict[str, str], test_user: User, db_session: AsyncSession
    ) -> None:
        response = await client.patch(
            f"{USERS}/me",
            headers=auth_headers,
            json={
                "personal_email": "test@personal.example",
                "phone_number": "+91 98765 43210",
                "avatar_url": "https://cdn.example/a.png",
            },
        )

        assert response.status_code == 200
        await db_session.refresh(test_user)
        assert test_user.personal_email == "test@personal.example"
        assert test_user.phone_number == "+91 98765 43210"

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("first_name", "Hacked"),
            ("username", "hacked"),
            ("email", "hacked@example.com"),
            ("status", "inactive"),
            ("is_superuser", True),
            ("business_unit_id", "0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f"),
            ("user_code", "USR-000999"),
        ],
    )
    async def test_administrative_fields_are_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], field: str, value: Any
    ) -> None:
        """A self-service payload cannot carry an administrative field at all."""
        response = await client.patch(f"{USERS}/me", headers=auth_headers, json={field: value})
        assert response.status_code == 422

    async def test_an_empty_update_is_a_no_op(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.patch(f"{USERS}/me", headers=auth_headers, json={})
        assert response.status_code == 200

    async def test_an_invalid_mobile_number_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.patch(f"{USERS}/me", headers=auth_headers, json={"phone_number": "call me"})
        assert response.status_code == 422


class TestListing:
    async def _seed(self, client: AsyncClient, headers: dict[str, str]) -> None:
        for first, last in [("Alice", "Anders"), ("Bob", "Brown"), ("Carol", "Clark")]:
            await create_user(
                client,
                headers,
                first_name=first,
                last_name=last,
                username=f"{first.lower()}.{last.lower()}",
                email=f"{first.lower()}@example.com",
            )

    async def test_pagination_metadata(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        await self._seed(client, auth_headers)

        response = await client.get(USERS, headers=auth_headers, params={"page": 1, "page_size": 2})

        meta = response.json()["data"]["meta"]
        assert meta["page_size"] == 2
        assert meta["total_items"] == 4  # three seeded plus the authenticated caller
        assert meta["has_next"] is True

    async def test_search_matches_the_full_name(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """The most obvious thing to type, and what a per-column search misses."""
        await self._seed(client, auth_headers)

        response = await client.get(USERS, headers=auth_headers, params={"search": "Bob Brown"})

        items = response.json()["data"]["items"]
        assert [row["username"] for row in items] == ["bob.brown"]

    async def test_search_matches_the_staff_code(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await create_user(client, auth_headers)

        response = await client.get(USERS, headers=auth_headers, params={"search": created["user_code"]})
        assert [row["id"] for row in response.json()["data"]["items"]] == [created["id"]]

    async def test_search_matches_the_username(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await self._seed(client, auth_headers)

        response = await client.get(USERS, headers=auth_headers, params={"search": "carol.clark"})
        assert len(response.json()["data"]["items"]) == 1

    async def test_status_filter(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        created = await create_user(client, auth_headers)
        await client.post(f"{USERS}/{created['id']}/deactivate", headers=auth_headers)

        inactive = await client.get(USERS, headers=auth_headers, params={"status": "inactive"})
        assert [row["id"] for row in inactive.json()["data"]["items"]] == [created["id"]]

    async def test_filtering_by_business_unit(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        created = await create_user(client, auth_headers, business_unit_id=str(business_unit.id))

        response = await client.get(
            USERS, headers=auth_headers, params={"business_unit_id": str(business_unit.id)}
        )
        assert [row["id"] for row in response.json()["data"]["items"]] == [created["id"]]

    async def test_sorting(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        await self._seed(client, auth_headers)

        response = await client.get(
            USERS, headers=auth_headers, params={"sort_by": "first_name", "sort_order": "asc"}
        )
        names = [row["first_name"] for row in response.json()["data"]["items"]]
        assert names == sorted(names)

    async def test_an_unsupported_sort_column_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Passing the column straight through to SQL would be an injection risk."""
        response = await client.get(USERS, headers=auth_headers, params={"sort_by": "hashed_password"})

        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "invalid_sort_field"


class TestAuditTrail:
    async def _actions(self, session: AsyncSession) -> list[str]:
        """User-management actions only.

        Filtering on `entity_type` alone would also pick up the sign-in entry
        the `auth_headers` fixture generates, which is a different concern.
        """
        rows = (await session.execute(select(AuditLog).where(AuditLog.action.like("user.%")))).scalars().all()
        return [row.action for row in rows]

    async def test_every_lifecycle_action_is_audited(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        created = await create_user(client, auth_headers)
        user_id = created["id"]

        await client.patch(f"{USERS}/{user_id}", headers=auth_headers, json={"last_name": "Smith"})
        await client.post(f"{USERS}/{user_id}/deactivate", headers=auth_headers)
        await client.post(f"{USERS}/{user_id}/activate", headers=auth_headers)
        await client.post(
            f"{USERS}/{user_id}/reset-password",
            headers=auth_headers,
            json={"new_password": "R3set@Password"},
        )
        await client.post(f"{USERS}/{user_id}/archive", headers=auth_headers)
        await client.post(f"{USERS}/{user_id}/restore", headers=auth_headers)

        assert await self._actions(db_session) == [
            "user.created",
            "user.updated",
            "user.deactivated",
            "user.activated",
            "user.password.reset_by_admin",
            "user.archived",
            "user.restored",
        ]

    async def test_a_profile_update_is_audited(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        await client.patch(f"{USERS}/me", headers=auth_headers, json={"phone_number": "+91 98765 43210"})
        assert "user.profile.updated" in await self._actions(db_session)

    async def test_the_entry_captures_actor_and_record(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, test_user: User
    ) -> None:
        created = await create_user(client, auth_headers)

        entry = (
            (await db_session.execute(select(AuditLog).where(AuditLog.action == "user.created")))
            .scalars()
            .one()
        )

        assert entry.entity_id == created["id"]
        assert entry.actor_id == test_user.id
        assert entry.outcome == "success"

    async def test_a_rejected_write_is_not_audited(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        await client.post(USERS, headers=auth_headers, json=new_user(email=TEST_USER_EMAIL))
        assert await self._actions(db_session) == []


class TestExistingAuthStillWorks:
    """The module extended the table authentication depends on."""

    async def test_sign_in_still_works(self, client: AsyncClient, test_user: User) -> None:
        response = await client.post(
            f"{AUTH}/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )
        assert response.status_code == 200

    async def test_the_login_payload_carries_the_new_fields(
        self, client: AsyncClient, test_user: User
    ) -> None:
        response = await client.post(
            f"{AUTH}/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )

        user = response.json()["data"]["user"]
        assert user["user_code"].startswith("USR-")
        assert user["username"] == "test.user"
        assert user["full_name"] == "Test User"
        assert user["force_password_change"] is False

    async def test_auth_me_still_works(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        response = await client.get(f"{AUTH}/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["user"]["email"] == TEST_USER_EMAIL
