"""The two administration modules the audit found half-built: settings and audit.

Both had storage, permissions and (for audit) a repository search -- and no
endpoint. These tests pin the endpoints that now exist, and the two properties
that make them safe: a locked setting refuses edits outright, and reading or
exporting the trail requires the audit permissions rather than riding on
something else.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.core.security import hash_password
from app.models.app_setting import AppSetting
from app.models.rbac import Role, UserRole
from app.models.user import User

API = app_settings.API_V1_PREFIX
pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def _admin_headers(client: AsyncClient, db_session: AsyncSession) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"admin.{suffix}@jsan.example",
        username=f"admin{suffix}",
        first_name="Ada",
        last_name="Admin",
        hashed_password=hash_password("Str0ng!Passw0rd"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    role = (await db_session.execute(Role.__table__.select().where(Role.__table__.c.key == "admin"))).first()
    assert role is not None, "system roles must be seeded"
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    await db_session.flush()

    response = await client.post(
        f"{API}/auth/login", json={"email": user.email, "password": "Str0ng!Passw0rd"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['tokens']['access_token']}"}


async def _employee_headers(client: AsyncClient, db_session: AsyncSession) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"emp.{suffix}@jsan.example",
        username=f"emp{suffix}",
        first_name="Eva",
        last_name="Employee",
        hashed_password=hash_password("Str0ng!Passw0rd"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    role = (
        await db_session.execute(Role.__table__.select().where(Role.__table__.c.key == "employee"))
    ).first()
    assert role is not None
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    await db_session.flush()

    response = await client.post(
        f"{API}/auth/login", json={"email": user.email, "password": "Str0ng!Passw0rd"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['tokens']['access_token']}"}


class TestSettings:
    async def test_settings_list_and_edit(self, client: AsyncClient, db_session: AsyncSession) -> None:
        # Rows come from the CLI seeder in a real deployment; the test database
        # only runs migrations, so the test plants its own.
        key = f"test.idle_minutes_{uuid.uuid4().hex[:6]}"
        db_session.add(AppSetting(key=key, value=30, category="security"))
        await db_session.flush()
        headers = await _admin_headers(client, db_session)

        listed = await client.get(f"{API}/settings", headers=headers)
        assert listed.status_code == 200, listed.text
        rows = {row["key"]: row for row in listed.json()["data"]}
        assert key in rows

        updated = await client.patch(f"{API}/settings/{key}", json={"value": 45}, headers=headers)
        assert updated.status_code == 200, updated.text
        assert updated.json()["data"]["value"] == 45

    async def test_a_locked_setting_refuses_edits(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """``is_editable=False`` rows show the value the platform enforces;
        letting an operator edit one would let the screen disagree with the
        code that actually applies the value."""
        key = f"test.locked_{uuid.uuid4().hex[:6]}"
        db_session.add(AppSetting(key=key, value=8, category="security", is_editable=False))
        await db_session.flush()
        headers = await _admin_headers(client, db_session)

        refused = await client.patch(f"{API}/settings/{key}", json={"value": 4}, headers=headers)
        assert refused.status_code == 409, refused.text
        assert refused.json()["errors"][0]["code"] == "setting_locked"

    async def test_an_employee_cannot_reach_settings(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _employee_headers(client, db_session)
        assert (await client.get(f"{API}/settings", headers=headers)).status_code == 403
        assert (
            await client.patch(f"{API}/settings/any.key", json={"value": 5}, headers=headers)
        ).status_code == 403


class TestAuditTrail:
    async def test_the_trail_is_searchable_and_records_its_own_export(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)

        # The sign-in above is itself an audited event, so the trail is
        # guaranteed non-empty -- no synthetic rows needed.
        searched = await client.get(f"{API}/audit", headers=headers, params={"page_size": 10})
        assert searched.status_code == 200, searched.text
        page = searched.json()["data"]
        assert page["meta"]["total_items"] >= 1
        assert all("action" in row and "created_at" in row for row in page["items"])

        actions = await client.get(f"{API}/audit/actions", headers=headers)
        assert actions.status_code == 200
        assert "auth.login.succeeded" in actions.json()["data"]

        exported = await client.get(f"{API}/audit/export", headers=headers)
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("text/csv")
        assert exported.text.splitlines()[0].startswith("created_at,action,outcome")

        # The export itself landed in the trail.
        recorded = await client.get(
            f"{API}/audit", headers=headers, params={"action": "audit.trail.exported"}
        )
        assert recorded.json()["data"]["meta"]["total_items"] >= 1

    async def test_an_employee_cannot_read_the_trail(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _employee_headers(client, db_session)
        assert (await client.get(f"{API}/audit", headers=headers)).status_code == 403
        assert (await client.get(f"{API}/audit/export", headers=headers)).status_code == 403
