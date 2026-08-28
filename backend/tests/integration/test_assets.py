"""Integration tests for asset management.

Three propositions are under test, and most of what follows is refusals.

**Custody is a transaction, not a column.** Every assignment, return and
transfer leaves a record, and the history survives all of them. The test that
matters here is the transfer one: after A hands a laptop to B, the history has
to still say A had it.

**Status moves only along the transition table.** A disposed asset cannot come
back. A damaged one cannot become available without passing through
maintenance. Both are asserted as refusals, because a transition table nothing
enforces is documentation.

**Assets belong to Admin, and HR only gets to look.** HR Admin holds
``assets:view`` and none of the eight custody actions, so each of those is
paired here with an Administrator making the identical call and being let
through -- the difference is a permission, never a role name.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.permissions import SYSTEM_ROLES_BY_KEY
from app.core.security import hash_password
from app.models.asset import AssetCategory, AssetHistory
from app.models.audit_log import AuditAction, AuditLog
from app.models.employee import Employee
from app.models.enums import AssetEvent, EmploymentStatus, RecordStatus
from app.models.rbac import Role, UserRole
from app.models.user import User

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
ASSETS = f"{API}/assets"
PASSWORD = "Str0ng!Passw0rd"


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
async def _account(session: AsyncSession, role_key: str | None, label: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"{label}_{suffix}",
        first_name=label.replace("_", " ").title(),
        last_name="Tester",
        email=f"{label}.{suffix}@jsan.example",
        hashed_password=hash_password(PASSWORD),
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()
    if role_key is not None:
        role = (await session.execute(select(Role).where(Role.key == role_key))).scalars().first()
        assert role is not None, f"the {role_key} role should be seeded"
        session.add(UserRole(user_id=user.id, role_id=role.id))
        await session.flush()
    return user


async def _employee(
    session: AsyncSession,
    label: str,
    *,
    user: User | None = None,
    manager: Employee | None = None,
) -> Employee:
    suffix = uuid.uuid4().hex[:8]
    record = Employee(
        first_name=label.replace("_", " ").title(),
        last_name="Person",
        official_email=f"{label}.{suffix}@jsan.example",
        joining_date=date(2024, 1, 5),
        employment_status=EmploymentStatus.ACTIVE,
        user_id=user.id if user else None,
        reporting_manager_id=manager.id if manager else None,
    )
    session.add(record)
    await session.flush()
    return record


async def _sign_in(client: AsyncClient, user: User) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['tokens']['access_token']}"}


class People:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)

    admin_user: User
    hr_user: User
    manager_user: User
    manager: Employee
    employee_user: User
    employee: Employee
    other_manager_user: User
    stranger_user: User
    stranger: Employee


@pytest.fixture
async def people(db_session: AsyncSession) -> People:
    manager_user = await _account(db_session, "manager", "mgr")
    manager = await _employee(db_session, "manager", user=manager_user)

    employee_user = await _account(db_session, "employee", "emp")
    employee = await _employee(db_session, "employee", user=employee_user, manager=manager)

    other_manager_user = await _account(db_session, "manager", "mgr2")
    other_manager = await _employee(db_session, "other_manager", user=other_manager_user)

    stranger_user = await _account(db_session, "employee", "stranger")

    return People(
        admin_user=await _account(db_session, "admin", "adm"),
        hr_user=await _account(db_session, "hr_admin", "hr"),
        manager_user=manager_user,
        manager=manager,
        employee_user=employee_user,
        employee=employee,
        other_manager_user=other_manager_user,
        stranger_user=stranger_user,
        stranger=await _employee(db_session, "stranger", user=stranger_user, manager=other_manager),
    )


@pytest.fixture
async def category(db_session: AsyncSession) -> AssetCategory:
    row = AssetCategory(
        name=f"Laptop {uuid.uuid4().hex[:4]}",
        code=f"LT{uuid.uuid4().hex[:6].upper()}",
        returnable=True,
        status=RecordStatus.ACTIVE,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _create_asset(
    client: AsyncClient, headers: dict[str, str], category: AssetCategory, **overrides: object
) -> dict:
    body = {
        "name": "ThinkPad X1",
        "category_id": str(category.id),
        "asset_tag": f"TAG-{uuid.uuid4().hex[:8].upper()}",
        "condition": "new",
        "status": "available",
    }
    body.update(overrides)  # type: ignore[arg-type]
    response = await client.post(ASSETS, json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


# ======================================================================
# 1-3. Creation and uniqueness
# ======================================================================
class TestRegistration:
    async def test_an_admin_registers_an_asset(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        data = await _create_asset(client, headers, category)

        assert data["asset_code"].startswith("AST-")
        assert data["status"] == "available"
        assert data["assigned_to"] is None

    async def test_the_asset_tag_is_unique(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        first = await _create_asset(client, headers, category)

        response = await client.post(
            ASSETS,
            json={
                "name": "Duplicate",
                "category_id": str(category.id),
                "asset_tag": first["asset_tag"],
                "condition": "new",
            },
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "duplicate_asset_tag"

    async def test_the_serial_number_is_unique_where_present(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        serial = f"SN{uuid.uuid4().hex[:10].upper()}"
        await _create_asset(client, headers, category, serial_number=serial)

        clash = await client.post(
            ASSETS,
            json={
                "name": "Same serial",
                "category_id": str(category.id),
                "asset_tag": f"TAG-{uuid.uuid4().hex[:8].upper()}",
                "condition": "new",
                "serial_number": serial,
            },
            headers=headers,
        )
        assert clash.status_code == 409
        assert clash.json()["errors"][0]["code"] == "duplicate_serial_number"

    async def test_several_assets_may_have_no_serial(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        """Two blanks are not a duplicate of each other -- the partial index."""
        headers = await _sign_in(client, people.admin_user)
        await _create_asset(client, headers, category)
        await _create_asset(client, headers, category)

    async def test_an_asset_cannot_be_created_already_assigned(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        """There would be no assignment record behind the custody."""
        headers = await _sign_in(client, people.admin_user)
        response = await client.post(
            ASSETS,
            json={
                "name": "Born assigned",
                "category_id": str(category.id),
                "asset_tag": f"TAG-{uuid.uuid4().hex[:8].upper()}",
                "condition": "new",
                "status": "assigned",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "invalid_initial_status"


# ======================================================================
# 4-5, 12-14. Custody
# ======================================================================
class TestCustody:
    async def test_an_available_asset_can_be_assigned(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)

        response = await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text

        detail = await client.get(f"{ASSETS}/{asset['id']}", headers=headers)
        body = detail.json()["data"]
        assert body["status"] == "assigned"
        assert body["assigned_to"]["id"] == str(people.employee.id)

    async def test_an_assigned_asset_cannot_be_assigned_again(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        payload = {
            "employee_id": str(people.employee.id),
            "assigned_date": date.today().isoformat(),
            "condition_at_assignment": "new",
        }
        assert (
            await client.post(f"{ASSETS}/{asset['id']}/assign", json=payload, headers=headers)
        ).status_code == 201

        payload["employee_id"] = str(people.stranger.id)
        again = await client.post(f"{ASSETS}/{asset['id']}/assign", json=payload, headers=headers)
        assert again.status_code == 409
        assert again.json()["errors"][0]["code"] == "asset_not_assignable"

    async def test_an_asset_cannot_be_issued_to_somebody_who_has_left(
        self, client: AsyncClient, people: People, category: AssetCategory, db_session: AsyncSession
    ) -> None:
        people.stranger.employment_status = EmploymentStatus.INACTIVE.value
        await db_session.flush()

        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        response = await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.stranger.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "employee_not_active"

    async def test_a_return_frees_the_asset_and_writes_a_record(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=headers,
        )

        response = await client.post(
            f"{ASSETS}/{asset['id']}/return",
            json={"return_date": date.today().isoformat(), "condition_at_return": "good"},
            headers=headers,
        )
        assert response.status_code == 201, response.text

        detail = (await client.get(f"{ASSETS}/{asset['id']}", headers=headers)).json()["data"]
        assert detail["status"] == "available"
        assert detail["assigned_to"] is None
        assert detail["condition"] == "good"
        assert {row["event"] for row in detail["history"]} >= {"created", "assigned", "returned"}

    async def test_a_damaged_return_goes_to_maintenance_not_the_shelf(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=headers,
        )
        await client.post(
            f"{ASSETS}/{asset['id']}/return",
            json={
                "return_date": date.today().isoformat(),
                "condition_at_return": "damaged",
                "damage_details": "Cracked screen",
            },
            headers=headers,
        )

        detail = (await client.get(f"{ASSETS}/{asset['id']}", headers=headers)).json()["data"]
        assert detail["status"] == "under_maintenance"

    async def test_a_transfer_preserves_both_sides_of_the_history(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        """The test this module exists for: A -> B, and A is still there."""
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=headers,
        )

        response = await client.post(
            f"{ASSETS}/{asset['id']}/transfer",
            json={
                "to_employee_id": str(people.stranger.id),
                "transfer_date": date.today().isoformat(),
                "condition_at_transfer": "good",
                "reason": "Team change",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text

        detail = (await client.get(f"{ASSETS}/{asset['id']}", headers=headers)).json()["data"]
        assert detail["assigned_to"]["id"] == str(people.stranger.id)

        transfers = [row for row in detail["history"] if row["event"] == "transferred"]
        assert transfers, "the transfer is not in the history"
        assert people.employee.full_name in (transfers[0]["previous_value"] or "")
        assert people.stranger.full_name in (transfers[0]["new_value"] or "")

    async def test_an_unassigned_asset_cannot_be_transferred(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        response = await client.post(
            f"{ASSETS}/{asset['id']}/transfer",
            json={
                "to_employee_id": str(people.stranger.id),
                "transfer_date": date.today().isoformat(),
                "condition_at_transfer": "good",
            },
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "not_assigned"

    async def test_editing_an_asset_cannot_move_custody(self) -> None:
        """Asserted on the schema: there is no field that could ask for it."""
        from app.schemas.asset import AssetUpdate

        fields = set(AssetUpdate.model_fields)
        assert "status" not in fields
        assert "condition" not in fields
        assert not any("employee" in field or "assign" in field for field in fields)


# ======================================================================
# Status transitions
# ======================================================================
class TestStatusTransitions:
    async def test_a_disposed_asset_cannot_come_back(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)

        for target in ("retired", "disposed"):
            response = await client.post(
                f"{ASSETS}/{asset['id']}/status",
                json={"status": target, "reason": "End of life"},
                headers=headers,
            )
            assert response.status_code == 200, response.text

        back = await client.post(
            f"{ASSETS}/{asset['id']}/status",
            json={"status": "available", "reason": "Changed my mind"},
            headers=headers,
        )
        assert back.status_code == 409
        assert back.json()["errors"][0]["code"] == "invalid_status_transition"

    async def test_damaged_cannot_jump_straight_to_available(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/status",
            json={"status": "damaged", "reason": "Dropped"},
            headers=headers,
        )

        response = await client.post(
            f"{ASSETS}/{asset['id']}/status",
            json={"status": "available", "reason": "Looks fine"},
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "invalid_status_transition"

    async def test_the_permitted_moves_are_published(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        """So the client never holds its own copy of the transition table."""
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        response = await client.get(f"{ASSETS}/{asset['id']}/transitions", headers=headers)
        assert response.status_code == 200
        assert "assigned" in response.json()["data"]
        assert "disposed" not in response.json()["data"]

    async def test_status_cannot_be_used_to_assign(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        response = await client.post(
            f"{ASSETS}/{asset['id']}/status",
            json={"status": "assigned", "reason": "Shortcut"},
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "use_assignment"


# ======================================================================
# 15. Maintenance
# ======================================================================
class TestMaintenance:
    async def test_starting_maintenance_takes_the_asset_off_the_floor(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)

        response = await client.post(
            f"{ASSETS}/maintenance",
            json={
                "asset_id": asset["id"],
                "maintenance_type": "repair",
                "start_date": date.today().isoformat(),
                "description": "Battery replacement",
                "start_now": True,
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text

        detail = (await client.get(f"{ASSETS}/{asset['id']}", headers=headers)).json()["data"]
        assert detail["status"] == "under_maintenance"

    async def test_completing_maintenance_releases_the_asset(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        record = (
            await client.post(
                f"{ASSETS}/maintenance",
                json={
                    "asset_id": asset["id"],
                    "maintenance_type": "repair",
                    "start_date": date.today().isoformat(),
                    "start_now": True,
                },
                headers=headers,
            )
        ).json()["data"]

        response = await client.patch(
            f"{ASSETS}/maintenance/{record['id']}",
            json={
                "status": "completed",
                "end_date": date.today().isoformat(),
                "cost": "120.00",
                "resulting_condition": "good",
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text

        detail = (await client.get(f"{ASSETS}/{asset['id']}", headers=headers)).json()["data"]
        assert detail["status"] == "available"
        assert detail["condition"] == "good"

    async def test_maintenance_on_an_assigned_asset_ends_the_custody(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        """The register must never claim somebody holds a laptop that is in a shop."""
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=headers,
        )
        await client.post(
            f"{ASSETS}/maintenance",
            json={
                "asset_id": asset["id"],
                "maintenance_type": "repair",
                "start_date": date.today().isoformat(),
                "start_now": True,
            },
            headers=headers,
        )

        detail = (await client.get(f"{ASSETS}/{asset['id']}", headers=headers)).json()["data"]
        assert detail["status"] == "under_maintenance"
        assert detail["assigned_to"] is None


# ======================================================================
# 6-11, 19. Access control
# ======================================================================
class TestAccessControl:
    async def test_an_employee_sees_their_own_assets(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        admin = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, admin, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=admin,
        )

        headers = await _sign_in(client, people.employee_user)
        response = await client.get(f"{API}/me/assets", headers=headers)
        assert response.status_code == 200
        rows = response.json()["data"]
        assert len(rows) == 1
        assert rows[0]["asset_tag"] == asset["asset_tag"]

    async def test_the_employee_view_carries_no_purchase_cost(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        admin = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, admin, category, purchase_cost="1499.00", vendor="Dell")
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=admin,
        )

        headers = await _sign_in(client, people.employee_user)
        body = (await client.get(f"{API}/me/assets", headers=headers)).text
        assert "1499" not in body
        assert "Dell" not in body

    async def test_an_employee_cannot_see_another_employees_assets(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        admin = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, admin, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=admin,
        )

        stranger = await _sign_in(client, people.stranger_user)
        # Their own list is empty ...
        assert (await client.get(f"{API}/me/assets", headers=stranger)).json()["data"] == []
        # ... and the register is closed to them entirely.
        assert (await client.get(ASSETS, headers=stranger)).status_code == 403
        assert (await client.get(f"{ASSETS}/{asset['id']}", headers=stranger)).status_code == 403

    async def test_a_manager_sees_their_teams_assets(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        admin = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, admin, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=admin,
        )

        headers = await _sign_in(client, people.manager_user)
        response = await client.get(f"{API}/manager/assets", headers=headers)
        assert response.status_code == 200
        rows = response.json()["data"]
        assert [row["employee"]["id"] for row in rows] == [str(people.employee.id)]

    async def test_a_manager_cannot_see_another_teams_assets(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        admin = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, admin, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.stranger.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=admin,
        )

        headers = await _sign_in(client, people.manager_user)
        assert (await client.get(f"{API}/manager/assets", headers=headers)).json()["data"] == []
        assert (await client.get(f"{ASSETS}/{asset['id']}", headers=headers)).status_code == 403

    async def test_a_manager_cannot_move_anything(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        """Managers hold assets:view and none of the custody actions."""
        admin = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, admin, category)

        headers = await _sign_in(client, people.manager_user)
        for path, body in (
            ("assign", {"employee_id": str(people.employee.id), "condition_at_assignment": "new"}),
            ("return", {"condition_at_return": "good"}),
            ("transfer", {"to_employee_id": str(people.employee.id), "condition_at_transfer": "good"}),
            ("status", {"status": "retired", "reason": "no"}),
        ):
            response = await client.post(f"{ASSETS}/{asset['id']}/{path}", json=body, headers=headers)
            assert response.status_code == 403, f"{path} -> {response.status_code}"


class TestHrIsNotAnAssetAdministrator:
    """§12 and §24: HR sees, and does not touch."""

    def test_hr_holds_only_the_view_permission(self) -> None:
        for role_key in ("hr_admin", "hr_executive"):
            held = {p for p in SYSTEM_ROLES_BY_KEY[role_key].permissions if p.startswith("assets:")}
            assert held == {"assets:view"}, f"{role_key} holds {held}"

    def test_the_administrator_holds_the_custody_actions(self) -> None:
        held = {p for p in SYSTEM_ROLES_BY_KEY["admin"].permissions if p.startswith("assets:")}
        for action in ("assign", "return", "transfer", "maintain", "retire", "dispose", "manage"):
            assert f"assets:{action}" in held

    async def test_hr_can_see_what_a_leaver_is_holding(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        admin = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, admin, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=admin,
        )

        headers = await _sign_in(client, people.hr_user)
        response = await client.get(f"{API}/hr/assets/{people.employee.id}", headers=headers)
        assert response.status_code == 200, response.text
        rows = response.json()["data"]
        assert len(rows) == 1
        assert rows[0]["asset_tag"] == asset["asset_tag"]
        assert rows[0]["returnable"] is True

    async def test_hr_cannot_create_assign_or_retire(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        admin = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, admin, category)

        headers = await _sign_in(client, people.hr_user)
        refused = [
            await client.post(
                ASSETS,
                json={
                    "name": "HR laptop",
                    "category_id": str(category.id),
                    "asset_tag": f"TAG-{uuid.uuid4().hex[:8].upper()}",
                    "condition": "new",
                },
                headers=headers,
            ),
            await client.post(
                f"{ASSETS}/{asset['id']}/assign",
                json={"employee_id": str(people.employee.id), "condition_at_assignment": "new"},
                headers=headers,
            ),
            await client.post(
                f"{ASSETS}/{asset['id']}/status",
                json={"status": "retired", "reason": "no"},
                headers=headers,
            ),
            await client.post(
                f"{ASSETS}/categories",
                json={"name": "New", "code": f"N{uuid.uuid4().hex[:5].upper()}"},
                headers=headers,
            ),
            await client.post(
                f"{ASSETS}/maintenance",
                json={
                    "asset_id": asset["id"],
                    "maintenance_type": "repair",
                    "start_date": date.today().isoformat(),
                },
                headers=headers,
            ),
        ]
        assert [r.status_code for r in refused] == [403] * 5

    async def test_hr_can_still_read_the_register(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        """The refusals above must not be a blanket denial."""
        admin = await _sign_in(client, people.admin_user)
        await _create_asset(client, admin, category)

        headers = await _sign_in(client, people.hr_user)
        assert (await client.get(ASSETS, headers=headers)).status_code == 200
        assert (await client.get(f"{ASSETS}/dashboard", headers=headers)).status_code == 200

    async def test_a_permission_grant_is_what_changes_the_answer(
        self, client: AsyncClient, people: People, category: AssetCategory, db_session: AsyncSession
    ) -> None:
        """Nothing checks a role name: granting the permission lets HR through."""
        from app.models.rbac import Permission, RolePermission

        role = Role(
            key=f"custom_{uuid.uuid4().hex[:8]}",
            name=f"Custom {uuid.uuid4().hex[:4]}",
            is_system=False,
            status=RecordStatus.ACTIVE,
        )
        db_session.add(role)
        await db_session.flush()
        permission_id = (
            await db_session.execute(select(Permission.id).where(Permission.code == "assets:create"))
        ).scalar_one()
        db_session.add(RolePermission(role_id=role.id, permission_id=permission_id))
        db_session.add(UserRole(user_id=people.hr_user.id, role_id=role.id))
        await db_session.flush()

        headers = await _sign_in(client, people.hr_user)
        response = await client.post(
            ASSETS,
            json={
                "name": "Now permitted",
                "category_id": str(category.id),
                "asset_tag": f"TAG-{uuid.uuid4().hex[:8].upper()}",
                "condition": "new",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text

    async def test_an_anonymous_caller_gets_401_not_403(self, client: AsyncClient) -> None:
        assert (await client.get(ASSETS)).status_code == 401


# ======================================================================
# 16-18, 20. Offboarding, history and audit
# ======================================================================
class TestOffboardingIntegration:
    @staticmethod
    async def _open_case(client: AsyncClient, people: People, admin: dict[str, str]) -> dict:
        employee_headers = await _sign_in(client, people.employee_user)
        resignation = (
            await client.post(
                f"{API}/me/resignation",
                json={
                    "resignation_date": date.today().isoformat(),
                    "proposed_last_working_day": (date.today() + timedelta(days=30)).isoformat(),
                    "reason": "Career change",
                },
                headers=employee_headers,
            )
        ).json()["data"]

        manager_headers = await _sign_in(client, people.manager_user)
        await client.post(
            f"{API}/manager/resignations/{resignation['id']}/decision",
            json={"decision": "approve"},
            headers=manager_headers,
        )
        processed = await client.post(
            f"{API}/offboarding/resignations/{resignation['id']}/process",
            json={"approved_last_working_day": (date.today() + timedelta(days=30)).isoformat()},
            headers=admin,
        )
        assert processed.status_code == 201, processed.text
        return processed.json()["data"]

    async def test_the_clearance_is_seeded_from_the_register(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        """§16: the offboarding screen shows what the employee actually holds."""
        admin = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, admin, category, name="Issued Laptop")
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=admin,
        )

        case = await self._open_case(client, people, admin)
        tags = {row["asset_tag"] for row in case["assets"]}
        assert asset["asset_tag"] in tags, "the real asset is not on the clearance list"

    async def test_resolving_the_clearance_updates_the_real_asset(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        """The integration in both directions: tick it there, it is free here."""
        admin = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, admin, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=admin,
        )
        case = await self._open_case(client, people, admin)

        row = next(r for r in case["assets"] if r["asset_tag"] == asset["asset_tag"])
        response = await client.patch(
            f"{API}/offboarding/assets/{row['id']}",
            json={"status": "returned"},
            headers=admin,
        )
        assert response.status_code == 200, response.text

        detail = (await client.get(f"{ASSETS}/{asset['id']}", headers=admin)).json()["data"]
        assert detail["status"] == "available", "the register still thinks the leaver has it"
        assert detail["assigned_to"] is None

    async def test_a_waiver_is_audited(
        self, client: AsyncClient, people: People, category: AssetCategory, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, admin, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=admin,
        )
        case = await self._open_case(client, people, admin)
        row = next(r for r in case["assets"] if r["asset_tag"] == asset["asset_tag"])

        await client.patch(
            f"{API}/offboarding/assets/{row['id']}",
            json={"status": "waived", "comments": "Written off"},
            headers=admin,
        )

        waivers = (
            await db_session.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.ASSET_CLEARANCE_WAIVED.value)
            )
        ).scalar_one()
        assert waivers >= 1, "a waiver must be auditable"

    async def test_offboarding_cannot_complete_with_an_outstanding_asset(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        admin = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, admin, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=admin,
        )
        case = await self._open_case(client, people, admin)

        response = await client.post(
            f"{API}/offboarding/cases/{case['id']}/complete",
            json={"force": False},
            headers=admin,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "clearance_outstanding"


class TestHistoryAndAudit:
    async def test_the_history_survives_every_custody_change(
        self, client: AsyncClient, people: People, category: AssetCategory, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        for body, path in (
            (
                {
                    "employee_id": str(people.employee.id),
                    "assigned_date": date.today().isoformat(),
                    "condition_at_assignment": "new",
                },
                "assign",
            ),
            (
                {
                    "to_employee_id": str(people.stranger.id),
                    "transfer_date": date.today().isoformat(),
                    "condition_at_transfer": "good",
                },
                "transfer",
            ),
            ({"return_date": date.today().isoformat(), "condition_at_return": "good"}, "return"),
        ):
            assert (
                await client.post(f"{ASSETS}/{asset['id']}/{path}", json=body, headers=headers)
            ).status_code == 201

        events = (
            (
                await db_session.execute(
                    select(AssetHistory.event).where(AssetHistory.asset_id == uuid.UUID(asset["id"]))
                )
            )
            .scalars()
            .all()
        )
        assert set(events) >= {
            AssetEvent.CREATED.value,
            AssetEvent.ASSIGNED.value,
            AssetEvent.TRANSFERRED.value,
            AssetEvent.RETURNED.value,
        }

    async def test_sensitive_actions_are_audited(
        self, client: AsyncClient, people: People, category: AssetCategory, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category)
        await client.post(
            f"{ASSETS}/{asset['id']}/assign",
            json={
                "employee_id": str(people.employee.id),
                "assigned_date": date.today().isoformat(),
                "condition_at_assignment": "new",
            },
            headers=headers,
        )
        await client.post(
            f"{ASSETS}/{asset['id']}/return",
            json={"return_date": date.today().isoformat(), "condition_at_return": "good"},
            headers=headers,
        )
        await client.post(
            f"{ASSETS}/{asset['id']}/status",
            json={"status": "retired", "reason": "Old"},
            headers=headers,
        )

        actions = (
            (await db_session.execute(select(AuditLog.action).where(AuditLog.action.like("asset.%"))))
            .scalars()
            .all()
        )
        for expected in (
            AuditAction.ASSET_CREATED,
            AuditAction.ASSET_ASSIGNED,
            AuditAction.ASSET_RETURNED,
            AuditAction.ASSET_RETIRED,
        ):
            assert expected.value in actions, f"{expected.value} was not audited"


# ======================================================================
# Dashboard, reports and filtering
# ======================================================================
class TestDashboardAndReports:
    async def test_the_dashboard_counts_real_rows(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        await _create_asset(client, headers, category)
        response = await client.get(f"{ASSETS}/dashboard", headers=headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] >= 1
        assert data["available"] >= 1
        assert any(row["count"] > 0 for row in data["by_category"])

    async def test_the_register_filters_server_side(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        asset = await _create_asset(client, headers, category, location="Chennai")

        hit = await client.get(ASSETS, params={"location": "Chennai"}, headers=headers)
        assert hit.status_code == 200
        assert asset["id"] in [row["id"] for row in hit.json()["data"]["items"]]

        miss = await client.get(ASSETS, params={"status": "disposed"}, headers=headers)
        assert asset["id"] not in [row["id"] for row in miss.json()["data"]["items"]]

    @pytest.mark.parametrize("report", ["inventory", "assigned", "available", "maintenance", "warranty"])
    async def test_each_report_exports(
        self, client: AsyncClient, people: People, category: AssetCategory, report: str
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        await _create_asset(client, headers, category)
        response = await client.get(
            f"{ASSETS}/reports/{report}/export", params={"fmt": "csv"}, headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/csv")

    async def test_the_warranty_state_is_derived(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        soon = await _create_asset(
            client,
            headers,
            category,
            warranty_start=date.today().isoformat(),
            warranty_end=(date.today() + timedelta(days=10)).isoformat(),
        )
        assert soon["warranty_state"] == "expiring_soon"

        none_set = await _create_asset(client, headers, category)
        assert none_set["warranty_state"] == "none"


class TestCategories:
    async def test_categories_are_configurable_not_hardcoded(
        self, client: AsyncClient, people: People
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        listed = await client.get(f"{ASSETS}/categories", headers=headers)
        assert listed.status_code == 200
        assert len(listed.json()["data"]) >= 14, "the seeded categories are missing"

        created = await client.post(
            f"{ASSETS}/categories",
            json={"name": "Docking Station", "code": f"DOCK{uuid.uuid4().hex[:4].upper()}"},
            headers=headers,
        )
        assert created.status_code == 201, created.text

    async def test_an_inactive_category_cannot_be_used(
        self, client: AsyncClient, people: People, category: AssetCategory
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        await client.patch(f"{ASSETS}/categories/{category.id}", json={"status": "inactive"}, headers=headers)

        response = await client.post(
            ASSETS,
            json={
                "name": "Retired category",
                "category_id": str(category.id),
                "asset_tag": f"TAG-{uuid.uuid4().hex[:8].upper()}",
                "condition": "new",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "inactive_category"
