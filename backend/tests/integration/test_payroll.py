"""Integration tests for the payroll foundation.

Two propositions carry the module, and most of what follows is refusals.

**Salary history is append-only.** A revision ends the current record and
opens a new one; both survive, and the history records previous CTC, new CTC,
reason and author. The test that matters is the one that reads the *old*
record back after a revision.

**Nobody sees a salary they were not explicitly granted.** No seeded role
below Administrator holds any payroll permission: the seeded manager is
refused their own report's compensation, and seeded HR Admin is refused the
register. Access appears only when a custom role grants it — and a manager's
``payroll:team_view`` reaches their direct reports and stops there.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.employee import Employee
from app.models.enums import EmploymentStatus
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.user import User

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
PAYROLL = f"{API}/payroll"
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


async def _grant(session: AsyncSession, user: User, *codes: str) -> None:
    """A custom role holding exactly ``codes``, assigned to ``user``.

    The payroll access model is that no seeded role below Administrator holds
    anything, so every positive case in this file goes through a grant made on
    purpose — exactly as an administrator would on the roles screen.
    """
    suffix = uuid.uuid4().hex[:8]
    role = Role(
        key=f"t_payroll_{suffix}",
        name=f"Payroll Test {suffix}",
        description="Granted by the payroll test suite.",
        is_system=False,
        status="active",
    )
    session.add(role)
    await session.flush()

    rows = (await session.execute(select(Permission).where(Permission.code.in_(list(codes))))).scalars().all()
    assert {row.code for row in rows} == set(codes), "every granted permission must be seeded"
    for row in rows:
        session.add(RolePermission(role_id=role.id, permission_id=row.id))
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.flush()


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
    stranger_user: User
    stranger: Employee


@pytest.fixture
async def people(db_session: AsyncSession) -> People:
    manager_user = await _account(db_session, "manager", "pay_mgr")
    manager = await _employee(db_session, "pay_manager", user=manager_user)

    employee_user = await _account(db_session, "employee", "pay_emp")
    employee = await _employee(db_session, "pay_employee", user=employee_user, manager=manager)

    stranger_user = await _account(db_session, "employee", "pay_stranger")
    stranger = await _employee(db_session, "pay_stranger", user=stranger_user)

    return People(
        admin_user=await _account(db_session, "admin", "pay_adm"),
        hr_user=await _account(db_session, "hr_admin", "pay_hr"),
        manager_user=manager_user,
        manager=manager,
        employee_user=employee_user,
        employee=employee,
        stranger_user=stranger_user,
        stranger=stranger,
    )


async def _component_ids(client: AsyncClient, headers: dict[str, str]) -> dict[str, str]:
    response = await client.get(f"{PAYROLL}/components", headers=headers)
    assert response.status_code == 200, response.text
    return {row["code"]: row["id"] for row in response.json()["data"]}


async def _active_structure(client: AsyncClient, headers: dict[str, str], component_ids: list[str]) -> dict:
    created = await client.post(
        f"{PAYROLL}/structures",
        json={
            "name": f"Standard {uuid.uuid4().hex[:8]}",
            "description": "Monthly staff structure",
            "pay_frequency": "monthly",
            "currency": "INR",
            "components": [{"component_id": cid} for cid in component_ids],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    structure = created.json()["data"]
    assert structure["status"] == "draft"

    activated = await client.post(f"{PAYROLL}/structures/{structure['id']}/status/active", headers=headers)
    assert activated.status_code == 200, activated.text
    return activated.json()["data"]


def _compensation_body(structure: dict, components: dict[str, str], **overrides: object) -> dict:
    body = {
        "salary_structure_id": structure["id"],
        "currency": "INR",
        "annual_ctc": "500000.00",
        "annual_gross": "460000.00",
        "monthly_gross": "38333.33",
        "basic_salary": "20000.00",
        "effective_from": "2026-01-01",
        "components": [
            {"component_id": components["BASIC"], "value": "240000.00"},
            {"component_id": components["HRA"], "value": "40.00"},
        ],
    }
    body.update(overrides)
    return body


# ----------------------------------------------------------------------
class TestConfiguration:
    async def test_seeded_components_exist(self, client: AsyncClient, people: People) -> None:
        headers = await _sign_in(client, people.admin_user)
        codes = await _component_ids(client, headers)
        assert {"BASIC", "HRA", "PF", "TAX"} <= set(codes)

    async def test_duplicate_component_code_is_refused(self, client: AsyncClient, people: People) -> None:
        headers = await _sign_in(client, people.admin_user)
        body = {
            "name": "Basic Again",
            "code": "basic",  # normalised to BASIC, which the migration seeded
            "component_type": "earning",
            "calculation_type": "fixed",
            "value": "0",
        }
        assert (await client.post(f"{PAYROLL}/components", json=body, headers=headers)).status_code == 409

    async def test_percentage_component_requires_a_basis(self, client: AsyncClient, people: People) -> None:
        headers = await _sign_in(client, people.admin_user)
        body = {
            "name": "Broken Percentage",
            "code": f"PCT{uuid.uuid4().hex[:6].upper()}",
            "component_type": "earning",
            "calculation_type": "percentage",
            "value": "10",
        }
        assert (await client.post(f"{PAYROLL}/components", json=body, headers=headers)).status_code == 422

    async def test_a_draft_structure_cannot_be_assigned(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        components = await _component_ids(client, headers)
        created = await client.post(
            f"{PAYROLL}/structures",
            json={
                "name": f"Draft {uuid.uuid4().hex[:8]}",
                "components": [{"component_id": components["BASIC"]}],
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        draft = created.json()["data"]

        target = await _employee(db_session, "draft_target")
        body = _compensation_body(draft, components)
        body["components"] = [{"component_id": components["BASIC"], "value": "240000.00"}]
        refused = await client.post(
            f"{PAYROLL}/employees/{target.id}/compensation", json=body, headers=headers
        )
        assert refused.status_code == 409
        assert refused.json()["errors"][0]["code"] == "structure_not_active"

    async def test_structure_status_moves_only_along_the_map(
        self, client: AsyncClient, people: People
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        components = await _component_ids(client, headers)
        created = await client.post(
            f"{PAYROLL}/structures",
            json={
                "name": f"Transitions {uuid.uuid4().hex[:8]}",
                "components": [{"component_id": components["BASIC"]}],
            },
            headers=headers,
        )
        structure_id = created.json()["data"]["id"]

        # draft -> inactive is not a thing; draft -> active -> inactive is.
        assert (
            await client.post(f"{PAYROLL}/structures/{structure_id}/status/inactive", headers=headers)
        ).status_code == 409
        assert (
            await client.post(f"{PAYROLL}/structures/{structure_id}/status/active", headers=headers)
        ).status_code == 200
        assert (
            await client.post(f"{PAYROLL}/structures/{structure_id}/status/inactive", headers=headers)
        ).status_code == 200


# ----------------------------------------------------------------------
class TestAssignmentAndRevision:
    async def test_the_full_lifecycle_preserves_history(self, client: AsyncClient, people: People) -> None:
        """Assign, revise, and read everything back: the old record survives,
        the history names both amounts, and /me sees it all."""
        headers = await _sign_in(client, people.admin_user)
        components = await _component_ids(client, headers)
        structure = await _active_structure(client, headers, [components["BASIC"], components["HRA"]])

        assigned = await client.post(
            f"{PAYROLL}/employees/{people.employee.id}/compensation",
            json=_compensation_body(structure, components),
            headers=headers,
        )
        assert assigned.status_code == 201, assigned.text
        first = assigned.json()["data"]
        assert first["status"] == "active"
        assert first["effective_to"] is None
        assert {row["code"] for row in first["components"]} == {"BASIC", "HRA"}
        # The percentage snapshot came from the master, not from the client.
        hra = next(row for row in first["components"] if row["code"] == "HRA")
        assert hra["calculation_type"] == "percentage"
        assert hra["percentage_basis"] == "basic"

        revised = await client.post(
            f"{PAYROLL}/employees/{people.employee.id}/revisions",
            json={
                **_compensation_body(structure, components),
                "annual_ctc": "600000.00",
                "effective_from": "2026-07-01",
                "reason": "Annual increment",
            },
            headers=headers,
        )
        assert revised.status_code == 201, revised.text
        second = revised.json()["data"]
        assert second["annual_ctc"] == "600000.00"

        detail = await client.get(f"{PAYROLL}/employees/{people.employee.id}/compensation", headers=headers)
        assert detail.status_code == 200
        data = detail.json()["data"]
        assert data["current"]["id"] == second["id"]
        assert len(data["records"]) == 2
        old = next(row for row in data["records"] if row["id"] == first["id"])
        # The previous record was ended, not rewritten: its amounts survive.
        assert old["status"] == "ended"
        assert old["effective_to"] == "2026-06-30"
        assert old["annual_ctc"] == "500000.00"

        history = await client.get(f"{PAYROLL}/employees/{people.employee.id}/history", headers=headers)
        assert history.status_code == 200
        entries = history.json()["data"]
        assert len(entries) == 2
        newest = entries[0]
        assert newest["previous_annual_ctc"] == "500000.00"
        assert newest["new_annual_ctc"] == "600000.00"
        assert newest["reason"] == "Annual increment"
        assert newest["changed_by_name"]

        # The employee reads the same facts through /me, with no id anywhere.
        own = await _sign_in(client, people.employee_user)
        mine = await client.get(f"{API}/me/payroll", headers=own)
        assert mine.status_code == 200
        assert mine.json()["data"]["current"]["annual_ctc"] == "600000.00"
        my_history = await client.get(f"{API}/me/payroll/history", headers=own)
        assert my_history.status_code == 200
        assert len(my_history.json()["data"]) == 2

    async def test_overlapping_compensation_is_refused(self, client: AsyncClient, people: People) -> None:
        headers = await _sign_in(client, people.admin_user)
        components = await _component_ids(client, headers)
        structure = await _active_structure(client, headers, [components["BASIC"]])
        body = _compensation_body(structure, components)
        body["components"] = [{"component_id": components["BASIC"], "value": "240000.00"}]

        target = people.stranger
        assert (
            await client.post(f"{PAYROLL}/employees/{target.id}/compensation", json=body, headers=headers)
        ).status_code == 201
        second = await client.post(
            f"{PAYROLL}/employees/{target.id}/compensation", json=body, headers=headers
        )
        assert second.status_code == 409
        assert second.json()["errors"][0]["code"] == "overlapping_compensation"

    async def test_a_missing_required_component_is_refused(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        components = await _component_ids(client, headers)
        structure = await _active_structure(client, headers, [components["BASIC"], components["HRA"]])
        body = _compensation_body(structure, components)
        body["components"] = [{"component_id": components["BASIC"], "value": "240000.00"}]

        target = await _employee(db_session, "missing_component")
        refused = await client.post(
            f"{PAYROLL}/employees/{target.id}/compensation", json=body, headers=headers
        )
        assert refused.status_code == 422
        assert "HRA" in refused.text

    async def test_a_percentage_over_100_is_refused(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        components = await _component_ids(client, headers)
        structure = await _active_structure(client, headers, [components["BASIC"], components["HRA"]])
        body = _compensation_body(structure, components)
        body["components"] = [
            {"component_id": components["BASIC"], "value": "240000.00"},
            {"component_id": components["HRA"], "value": "140.00"},
        ]
        target = await _employee(db_session, "over_percentage")
        assert (
            await client.post(f"{PAYROLL}/employees/{target.id}/compensation", json=body, headers=headers)
        ).status_code == 422

    async def test_negative_money_is_refused_at_the_edge(self, client: AsyncClient, people: People) -> None:
        headers = await _sign_in(client, people.admin_user)
        components = await _component_ids(client, headers)
        structure = await _active_structure(client, headers, [components["BASIC"]])
        body = _compensation_body(structure, components, annual_ctc="-1")
        assert (
            await client.post(
                f"{PAYROLL}/employees/{people.stranger.id}/compensation", json=body, headers=headers
            )
        ).status_code == 422

    async def test_a_revision_needs_something_to_revise(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        components = await _component_ids(client, headers)
        structure = await _active_structure(client, headers, [components["BASIC"]])
        body = _compensation_body(structure, components)
        body["components"] = [{"component_id": components["BASIC"], "value": "240000.00"}]
        body["reason"] = "Nothing to revise"

        target = await _employee(db_session, "no_current")
        refused = await client.post(f"{PAYROLL}/employees/{target.id}/revisions", json=body, headers=headers)
        assert refused.status_code == 409
        assert refused.json()["errors"][0]["code"] == "nothing_to_revise"

    async def test_a_revision_cannot_predate_the_current_record(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, people.admin_user)
        components = await _component_ids(client, headers)
        structure = await _active_structure(client, headers, [components["BASIC"]])
        body = _compensation_body(structure, components)
        body["components"] = [{"component_id": components["BASIC"], "value": "240000.00"}]

        target = await _employee(db_session, "backdated")
        assert (
            await client.post(f"{PAYROLL}/employees/{target.id}/compensation", json=body, headers=headers)
        ).status_code == 201
        refused = await client.post(
            f"{PAYROLL}/employees/{target.id}/revisions",
            json={**body, "effective_from": "2026-01-01", "reason": "Backdated"},
            headers=headers,
        )
        assert refused.status_code == 422


# ----------------------------------------------------------------------
class TestAccessModel:
    """The twelve refusals of §19, or as many as have a server to refuse them."""

    async def test_an_employee_cannot_read_another_employees_salary(
        self, client: AsyncClient, people: People
    ) -> None:
        headers = await _sign_in(client, people.employee_user)
        response = await client.get(f"{PAYROLL}/employees/{people.stranger.id}/compensation", headers=headers)
        assert response.status_code == 403
        assert (
            await client.get(f"{PAYROLL}/employees/{people.stranger.id}/history", headers=headers)
        ).status_code == 403

    async def test_an_employee_cannot_write_salary_anywhere(
        self, client: AsyncClient, people: People
    ) -> None:
        headers = await _sign_in(client, people.employee_user)
        own = people.employee.id
        assert (
            await client.post(f"{PAYROLL}/employees/{own}/compensation", json={}, headers=headers)
        ).status_code == 403
        assert (
            await client.post(f"{PAYROLL}/employees/{own}/revisions", json={}, headers=headers)
        ).status_code == 403
        assert (await client.post(f"{PAYROLL}/structures", json={}, headers=headers)).status_code == 403
        assert (await client.post(f"{PAYROLL}/components", json={}, headers=headers)).status_code == 403

    async def test_a_seeded_manager_cannot_see_their_reports_salary(
        self, client: AsyncClient, people: People
    ) -> None:
        """The inversion under test: everywhere else the reporting line narrows
        access; in payroll it grants none."""
        headers = await _sign_in(client, people.manager_user)
        response = await client.get(f"{PAYROLL}/employees/{people.employee.id}/compensation", headers=headers)
        assert response.status_code == 403

    async def test_team_view_reaches_direct_reports_and_stops_there(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        await _grant(db_session, people.manager_user, "payroll:team_view")
        headers = await _sign_in(client, people.manager_user)

        assert (
            await client.get(f"{PAYROLL}/employees/{people.employee.id}/compensation", headers=headers)
        ).status_code == 200
        assert (
            await client.get(f"{PAYROLL}/employees/{people.employee.id}/history", headers=headers)
        ).status_code == 200
        # A stranger does not report to them; team_view must not reach them.
        assert (
            await client.get(f"{PAYROLL}/employees/{people.stranger.id}/compensation", headers=headers)
        ).status_code == 403

    async def test_seeded_hr_admin_holds_no_payroll_access(self, client: AsyncClient, people: People) -> None:
        """HR manages compensation only through payroll permissions ticked on
        purpose; the seeded HR Admin has none of them."""
        headers = await _sign_in(client, people.hr_user)
        assert (await client.get(f"{PAYROLL}/compensation", headers=headers)).status_code == 403
        assert (await client.get(f"{PAYROLL}/structures", headers=headers)).status_code == 403
        assert (
            await client.get(f"{PAYROLL}/employees/{people.employee.id}/compensation", headers=headers)
        ).status_code == 403
        assert (
            await client.post(
                f"{PAYROLL}/employees/{people.employee.id}/compensation", json={}, headers=headers
            )
        ).status_code == 403

    async def test_granted_hr_can_do_exactly_what_was_granted(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        """payroll:view + create (and view_all for org-wide reach) opens the
        register and assignment — and still refuses structure administration."""
        await _grant(
            db_session,
            people.hr_user,
            "payroll:view",
            "payroll:create",
            "payroll:update",
            "employees:view_all",
        )
        admin_headers = await _sign_in(client, people.admin_user)
        components = await _component_ids(client, admin_headers)
        structure = await _active_structure(client, admin_headers, [components["BASIC"]])

        headers = await _sign_in(client, people.hr_user)
        assert (await client.get(f"{PAYROLL}/compensation", headers=headers)).status_code == 200

        body = _compensation_body(structure, components)
        body["components"] = [{"component_id": components["BASIC"], "value": "240000.00"}]
        assigned = await client.post(
            f"{PAYROLL}/employees/{people.employee.id}/compensation", json=body, headers=headers
        )
        assert assigned.status_code == 201, assigned.text

        # What was not granted stays shut: configuration and history.
        assert (await client.post(f"{PAYROLL}/structures", json={}, headers=headers)).status_code == 403
        assert (await client.post(f"{PAYROLL}/components", json={}, headers=headers)).status_code == 403
        history = await client.get(f"{PAYROLL}/employees/{people.employee.id}/history", headers=headers)
        assert history.status_code == 403, "history needs payroll:history_view, which was not granted"

    async def test_salary_history_cannot_be_deleted_or_edited(
        self, client: AsyncClient, people: People
    ) -> None:
        """No DELETE or PUT route exists anywhere under history — 405, not 403."""
        headers = await _sign_in(client, people.admin_user)
        path = f"{PAYROLL}/employees/{people.employee.id}/history"
        assert (await client.delete(path, headers=headers)).status_code == 405
        assert (await client.put(path, json={}, headers=headers)).status_code == 405

    async def test_salary_does_not_leak_through_the_employee_api(
        self, client: AsyncClient, people: People
    ) -> None:
        """The generic employee read model carries no compensation fields."""
        admin_headers = await _sign_in(client, people.admin_user)
        components = await _component_ids(client, admin_headers)
        structure = await _active_structure(client, admin_headers, [components["BASIC"]])
        body = _compensation_body(structure, components)
        body["components"] = [{"component_id": components["BASIC"], "value": "240000.00"}]
        await client.post(
            f"{PAYROLL}/employees/{people.employee.id}/compensation", json=body, headers=admin_headers
        )

        profile = await client.get(f"{API}/employees/{people.employee.id}", headers=admin_headers)
        assert profile.status_code == 200
        text = profile.text
        for field in ("annual_ctc", "monthly_gross", "salary_structure", "basic_salary"):
            assert field not in text, f"the employee API must not carry {field}"

    async def test_unauthenticated_requests_get_401(self, client: AsyncClient, people: People) -> None:
        assert (await client.get(f"{PAYROLL}/compensation")).status_code == 401
        assert (await client.get(f"{PAYROLL}/employees/{people.employee.id}/compensation")).status_code == 401
        assert (await client.get(f"{API}/me/payroll")).status_code == 401
