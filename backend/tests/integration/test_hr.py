"""Integration tests for the HR dashboard and HR administration.

These test one proposition: **HR is not an administrator.**

The access hierarchy the application claims is Employee -> Manager -> HR ->
Admin -> Super Admin, and each step widens *specific* permissions rather than
handing over the next tier wholesale. A test suite that only proved HR could
reach the HR screens would be satisfied by an implementation that gave HR
everything, so most of what follows is refusals: the things an HR Admin is
turned away from, with an Administrator making the identical request and being
let through.

Nothing here checks a role name, because nothing in the application does. Every
assertion below is about a permission, and the roles are only the shipped
bundles of them -- which is why the "HR cannot" tests are paired with a grant
that makes the same call succeed.

Two areas are asserted on the permission catalogue rather than over HTTP:
settings and audit administration have permissions but no endpoints yet. The one
place audit access *is* exercised -- the activity tab of the HR employee profile
-- is tested end to end.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.permissions import ALL_PERMISSIONS, SYSTEM_ROLES_BY_KEY
from app.core.security import hash_password
from app.models.employee import Employee
from app.models.enums import ApprovalStatus, EmploymentStatus, RecordStatus
from app.models.rbac import Permission, Role, UserRole
from app.models.user import User
from app.models.workforce import AttendanceRecord, LeaveRequest, LeaveType, Timesheet
from app.services.hr_service import DASHBOARD_SECTIONS, REPORTS

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
HR = f"{API}/hr"
EMPLOYEES = f"{API}/employees"
USERS = f"{API}/users"
ROLES = f"{API}/roles"

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
        assert role is not None, f"migration 0015/0017 should have seeded the {role_key} role"
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
        joining_date=date(2026, 1, 5),
        employment_status=EmploymentStatus.ACTIVE,
        user_id=user.id if user else None,
        reporting_manager_id=manager.id if manager else None,
    )
    session.add(record)
    await session.flush()
    return record


async def _grant(session: AsyncSession, user: User, permission: str) -> None:
    """Give one account one extra permission, through a role of its own.

    The point of several tests below: an HR user is refused an administrative
    action *until somebody grants it*, and the grant is a row in the permission
    system rather than a change of job title.
    """
    role = Role(
        key=f"custom_{uuid.uuid4().hex[:8]}",
        name=f"Custom {uuid.uuid4().hex[:4]}",
        is_system=False,
        status=RecordStatus.ACTIVE,
    )
    session.add(role)
    await session.flush()

    permission_id = (
        await session.execute(select(Permission.id).where(Permission.code == permission))
    ).scalar_one()
    from app.models.rbac import RolePermission

    session.add(RolePermission(role_id=role.id, permission_id=permission_id))
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.flush()


async def _sign_in(client: AsyncClient, user: User) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['tokens']['access_token']}"}


class People:
    """One of each seat, with the reporting lines that make scoping real."""

    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)

    employee_user: User
    employee: Employee
    manager_user: User
    manager: Employee
    report: Employee
    stranger: Employee
    hr_user: User
    hr: Employee
    hr_exec_user: User
    admin_user: User
    admin: Employee


@pytest.fixture
async def people(db_session: AsyncSession) -> People:
    manager_user = await _account(db_session, "manager", "mgr")
    manager = await _employee(db_session, "manager", user=manager_user)

    employee_user = await _account(db_session, "employee", "emp")
    employee = await _employee(db_session, "employee", user=employee_user, manager=manager)

    other_manager = await _employee(db_session, "other_manager")

    hr_user = await _account(db_session, "hr_admin", "hr")
    admin_user = await _account(db_session, "admin", "adm")

    return People(
        employee_user=employee_user,
        employee=employee,
        manager_user=manager_user,
        manager=manager,
        report=employee,
        stranger=await _employee(db_session, "stranger", manager=other_manager),
        hr_user=hr_user,
        hr=await _employee(db_session, "hr_person", user=hr_user),
        hr_exec_user=await _account(db_session, "hr_executive", "hrx"),
        admin_user=admin_user,
        admin=await _employee(db_session, "admin_person", user=admin_user),
    )


@pytest.fixture
async def hr_headers(client: AsyncClient, people: People) -> dict[str, str]:
    return await _sign_in(client, people.hr_user)


@pytest.fixture
async def admin_headers(client: AsyncClient, people: People) -> dict[str, str]:
    return await _sign_in(client, people.admin_user)


@pytest.fixture
async def leave_type(db_session: AsyncSession) -> LeaveType:
    record = LeaveType(
        name="Casual Leave",
        code=f"CL{uuid.uuid4().hex[:4].upper()}",
        annual_allocation=Decimal("12.0"),
        credit_frequency="monthly",
        credit_amount=Decimal("1.0"),
        status=RecordStatus.ACTIVE,
    )
    db_session.add(record)
    await db_session.flush()
    return record


async def _leave(session: AsyncSession, employee: Employee, leave_type: LeaveType) -> LeaveRequest:
    request = LeaveRequest(
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        from_date=date(2026, 3, 2),
        to_date=date(2026, 3, 3),
        days=Decimal("2.0"),
        reason="Personal",
        status=ApprovalStatus.PENDING.value,
    )
    session.add(request)
    await session.flush()
    return request


# ======================================================================
# EMPLOYEE
# ======================================================================
class TestEmployeeAccess:
    async def test_1_an_employee_reaches_their_own_data(self, client: AsyncClient, people: People) -> None:
        headers = await _sign_in(client, people.employee_user)

        me = await client.get(f"{API}/me", headers=headers)
        assert me.status_code == 200, me.text
        assert me.json()["data"]["id"] == str(people.employee.id)

        assert (await client.get(f"{API}/me/dashboard", headers=headers)).status_code == 200

    async def test_2_an_employee_cannot_reach_anybody_elses_data(
        self, client: AsyncClient, people: People
    ) -> None:
        headers = await _sign_in(client, people.employee_user)

        for path in (
            f"{EMPLOYEES}/{people.stranger.id}",
            f"{API}/workforce/leave/balances/{people.stranger.id}",
            f"{HR}/employees",
            f"{HR}/dashboard",
            f"{HR}/employees/{people.stranger.id}",
        ):
            response = await client.get(path, headers=headers)
            assert response.status_code == 403, f"{path}: {response.text}"


# ======================================================================
# MANAGER
# ======================================================================
class TestManagerAccess:
    async def test_3_a_manager_reaches_their_direct_reports(
        self, client: AsyncClient, people: People
    ) -> None:
        headers = await _sign_in(client, people.manager_user)

        response = await client.get(f"{API}/manager/team", headers=headers, params={"page_size": 100})
        assert response.status_code == 200, response.text
        assert {item["id"] for item in response.json()["data"]["items"]} == {str(people.report.id)}

    async def test_4_a_manager_cannot_reach_another_managers_employees(
        self, client: AsyncClient, people: People
    ) -> None:
        headers = await _sign_in(client, people.manager_user)

        assert (
            await client.get(f"{API}/manager/team/{people.stranger.id}", headers=headers)
        ).status_code == 403
        assert (await client.get(f"{EMPLOYEES}/{people.stranger.id}", headers=headers)).status_code == 403

    async def test_a_manager_cannot_reach_the_hr_screens(self, client: AsyncClient, people: People) -> None:
        """A manager holds ``attendance:approve`` but not ``employees:view_all``."""
        headers = await _sign_in(client, people.manager_user)

        for path in ("/dashboard", "/employees", "/attendance", "/leave", "/timesheets"):
            response = await client.get(f"{HR}{path}", headers=headers)
            assert response.status_code == 403, f"{path}: {response.text}"


# ======================================================================
# HR -- what it CAN do
# ======================================================================
class TestHrPermittedAccess:
    async def test_5_hr_opens_the_hr_dashboard(self, client: AsyncClient, hr_headers: dict[str, str]) -> None:
        response = await client.get(f"{HR}/dashboard", headers=hr_headers)
        assert response.status_code == 200, response.text

        data = response.json()["data"]
        # HR Admin holds every module view, so every section comes back.
        assert set(data["sections"]) == {name for name, _ in DASHBOARD_SECTIONS}
        assert data["employees"]["total_active"] >= 1
        assert data["requests"] is not None

    async def test_the_dashboard_reports_only_the_sections_the_caller_may_see(
        self, client: AsyncClient, db_session: AsyncSession, people: People
    ) -> None:
        """The contract the frontend renders from.

        An HR Executive holds no ``recruitment:view``... but does hold the rest.
        Whatever the seeded grant is, the response has to agree with it, which
        is what this asserts rather than hard-coding a list.
        """
        from app.services.authorization_service import AuthorizationService

        headers = await _sign_in(client, people.hr_exec_user)
        held = await AuthorizationService(db_session).permissions_for(people.hr_exec_user)
        expected = {name for name, needed in DASHBOARD_SECTIONS if set(needed) <= held}

        response = await client.get(f"{HR}/dashboard", headers=headers)
        assert response.status_code == 200, response.text
        assert set(response.json()["data"]["sections"]) == expected

        # And a section that is absent is absent, not zeroed.
        for name, _needed in DASHBOARD_SECTIONS:
            if name not in expected:
                assert response.json()["data"][name] is None, name

    async def test_6_hr_reads_the_employee_directory_without_the_sensitive_fields(
        self, client: AsyncClient, hr_headers: dict[str, str], people: People
    ) -> None:
        response = await client.get(f"{HR}/employees", headers=hr_headers, params={"page_size": 100})
        assert response.status_code == 200, response.text

        rows = response.json()["data"]["items"]
        assert {str(people.stranger.id), str(people.employee.id)} <= {row["id"] for row in rows}

        for forbidden in ("ctc", "bank_detail", "identification", "addresses", "notes", "salary_grade"):
            assert forbidden not in rows[0], f"{forbidden} has no business on the HR directory"

    async def test_6b_the_hr_profile_carries_the_nine_tabs_and_no_salary(
        self, client: AsyncClient, hr_headers: dict[str, str], people: People
    ) -> None:
        response = await client.get(f"{HR}/employees/{people.employee.id}", headers=hr_headers)
        assert response.status_code == 200, response.text

        data = response.json()["data"]
        for tab in ("employee", "attendance", "leave", "timesheets", "projects", "documents", "activity"):
            assert tab in data, tab
        for forbidden in ("ctc", "bank_detail", "identification"):
            assert forbidden not in data["employee"]

    async def test_7_hr_reads_organization_wide_workforce_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        people: People,
        leave_type: LeaveType,
        hr_headers: dict[str, str],
    ) -> None:
        db_session.add(AttendanceRecord(employee_id=people.stranger.id, attendance_date=date(2026, 3, 4)))
        db_session.add(Timesheet(employee_id=people.stranger.id, week_start_date=date(2026, 3, 2)))
        await _leave(db_session, people.stranger, leave_type)
        await db_session.flush()

        for path, key in (("/attendance", "record"), ("/leave", "request"), ("/timesheets", "timesheet")):
            response = await client.get(f"{HR}{path}", headers=hr_headers, params={"page_size": 100})
            assert response.status_code == 200, f"{path}: {response.text}"

            owners = {item["employee"]["id"] for item in response.json()["data"]["items"]}
            assert str(people.stranger.id) in owners, f"{path} should reach outside any reporting line"
            assert key in response.json()["data"]["items"][0]

    async def test_hr_sees_who_a_leave_request_is_actually_addressed_to(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        people: People,
        leave_type: LeaveType,
        hr_headers: dict[str, str],
    ) -> None:
        await _leave(db_session, people.report, leave_type)

        response = await client.get(f"{HR}/leave", headers=hr_headers, params={"page_size": 100})
        row = next(
            item
            for item in response.json()["data"]["items"]
            if item["employee"]["id"] == str(people.report.id)
        )
        assert row["reporting_manager"]["id"] == str(people.manager.id)

    async def test_hr_reviews_a_document_and_manages_leave_policy(
        self, client: AsyncClient, hr_headers: dict[str, str]
    ) -> None:
        """The two administrative powers HR *is* given by default."""
        created = await client.post(
            f"{HR}/leave/policies",
            headers=hr_headers,
            json={
                "name": f"Sick Leave {uuid.uuid4().hex[:4]}",
                "code": f"SL{uuid.uuid4().hex[:4].upper()}",
                "annual_allocation": 5,
                "credit_frequency": "annually",
                "credit_amount": 5,
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["data"]["credit_frequency"] == "annually"

        updated = await client.patch(
            f"{HR}/leave/policies/{created.json()['data']['id']}",
            headers=hr_headers,
            json={"prorate_on_joining": True},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["data"]["prorate_on_joining"] is True

    async def test_a_policy_that_credits_more_than_its_maximum_is_refused(
        self, client: AsyncClient, hr_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            f"{HR}/leave/policies",
            headers=hr_headers,
            json={
                "name": "Impossible Leave",
                "code": f"IL{uuid.uuid4().hex[:4].upper()}",
                "annual_allocation": 6,
                "credit_frequency": "monthly",
                "credit_amount": 1,
            },
        )
        assert response.status_code == 422, response.text

    async def test_a_partial_policy_update_is_checked_against_the_stored_values(
        self, client: AsyncClient, hr_headers: dict[str, str]
    ) -> None:
        """Halving the maximum without touching the monthly credit must fail."""
        created = await client.post(
            f"{HR}/leave/policies",
            headers=hr_headers,
            json={
                "name": f"Casual Leave {uuid.uuid4().hex[:4]}",
                "code": f"CL{uuid.uuid4().hex[:4].upper()}",
                "annual_allocation": 12,
                "credit_frequency": "monthly",
                "credit_amount": 1,
            },
        )
        assert created.status_code == 201, created.text

        response = await client.patch(
            f"{HR}/leave/policies/{created.json()['data']['id']}",
            headers=hr_headers,
            json={"annual_allocation": 6},
        )
        assert response.status_code == 422, response.text
        assert response.json()["errors"][0]["code"] == "invalid_policy"

    async def test_hr_reads_the_analytics_and_the_report_catalogue(
        self, client: AsyncClient, hr_headers: dict[str, str]
    ) -> None:
        analytics = await client.get(f"{HR}/analytics", headers=hr_headers, params={"months": 3})
        assert analytics.status_code == 200, analytics.text
        assert len(analytics.json()["data"]["headcount_trend"]) == 3

        catalogue = await client.get(f"{HR}/reports", headers=hr_headers)
        assert catalogue.status_code == 200, catalogue.text
        assert {item["key"] for item in catalogue.json()["data"]} == {key for key, _, _, _ in REPORTS}

    async def test_the_activity_tab_needs_audit_view(
        self, client: AsyncClient, people: People, hr_headers: dict[str, str]
    ) -> None:
        """HR Admin holds ``audit:view``; HR Executive does not."""
        as_hr_admin = await client.get(f"{HR}/employees/{people.employee.id}", headers=hr_headers)
        assert as_hr_admin.json()["data"]["can_read_activity"] is True

        headers = await _sign_in(client, people.hr_exec_user)
        as_hr_exec = await client.get(f"{HR}/employees/{people.employee.id}", headers=headers)
        assert as_hr_exec.status_code == 200, as_hr_exec.text
        assert as_hr_exec.json()["data"]["can_read_activity"] is False
        assert as_hr_exec.json()["data"]["activity"] == []


# ======================================================================
# HR -- what it CANNOT do
# ======================================================================
class TestHrIsNotAnAdministrator:
    async def test_8_hr_cannot_manage_users(self, client: AsyncClient, hr_headers: dict[str, str]) -> None:
        """HR Admin holds ``users:view`` and nothing else on the user directory."""
        assert (await client.get(USERS, headers=hr_headers)).status_code == 200

        created = await client.post(
            USERS,
            headers=hr_headers,
            json={
                "email": f"nope.{uuid.uuid4().hex[:8]}@jsan.example",
                "username": f"nope{uuid.uuid4().hex[:6]}",
                "first_name": "Should",
                "last_name": "Fail",
                "password": PASSWORD,
            },
        )
        assert created.status_code == 403, created.text
        assert created.json()["errors"][0]["message"] == "users:create"

    async def test_9_hr_cannot_manage_roles_or_permissions(
        self, client: AsyncClient, hr_headers: dict[str, str]
    ) -> None:
        assert (await client.get(ROLES, headers=hr_headers)).status_code == 403
        assert (await client.get(f"{ROLES}/permissions", headers=hr_headers)).status_code == 403

        created = await client.post(
            ROLES, headers=hr_headers, json={"name": "Nope", "permissions": ["employees:view"]}
        )
        assert created.status_code == 403, created.text

    def test_10_11_12_hr_holds_no_settings_security_or_audit_administration(self) -> None:
        """Asserted on the catalogue: these modules have no endpoints yet.

        Stated here rather than left untested, because the grant is the thing
        that decides it. The day a settings endpoint appears it will be guarded
        by ``settings:view`` / ``settings:update``, and this test already says
        HR does not hold either.
        """
        hr_admin = set(SYSTEM_ROLES_BY_KEY["hr_admin"].permissions)
        hr_executive = set(SYSTEM_ROLES_BY_KEY["hr_executive"].permissions)

        for held in (hr_admin, hr_executive):
            assert not {code for code in held if code.startswith("settings:")}
            assert not {code for code in held if code.startswith("roles:")}
            # Reading the trail is not administering it.
            assert "audit:export" not in held

        assert "audit:view" in hr_admin, "HR Admin reads the trail on an employee profile"
        assert "audit:view" not in hr_executive

    def test_13_hr_does_not_hold_the_administrative_workforce_actions(self) -> None:
        administrative = {
            "attendance:manage_all",
            "timesheets:manage_all",
            "leave:override_approval",
            "leave:balance_adjust",
        }
        for key in ("hr_admin", "hr_executive"):
            held = set(SYSTEM_ROLES_BY_KEY[key].permissions)
            assert not (administrative & held), f"{key} should hold none of {administrative}"

        # The one administrative power HR *is* given, and the reason it differs:
        # deciding how much leave the company grants is HR's job.
        assert "leave:policy_manage" in set(SYSTEM_ROLES_BY_KEY["hr_admin"].permissions)
        assert "leave:policy_manage" not in set(SYSTEM_ROLES_BY_KEY["hr_executive"].permissions)

    async def test_13b_hr_is_refused_the_administrative_endpoints(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        people: People,
        leave_type: LeaveType,
        hr_headers: dict[str, str],
    ) -> None:
        """The permission catalogue and the wire have to agree."""
        request = await _leave(db_session, people.stranger, leave_type)
        sheet = Timesheet(
            employee_id=people.stranger.id, week_start_date=date(2026, 3, 2), status="submitted"
        )
        db_session.add(sheet)
        await db_session.flush()

        refusals = (
            (
                "post",
                f"{HR}/attendance/{people.stranger.id}/correct",
                {"attendance_date": "2026-03-04", "status": "absent", "reason": "Marking absent"},
                "attendance:manage_all",
            ),
            (
                "post",
                f"{HR}/leave/{request.id}/override",
                {"approved": True},
                "leave:override_approval",
            ),
            (
                "post",
                f"{HR}/leave/balances/{people.stranger.id}/adjust",
                {"leave_type_id": str(leave_type.id), "days": 2, "reason": "Goodwill"},
                "leave:balance_adjust",
            ),
            (
                "post",
                f"{HR}/timesheets/{sheet.id}/decide",
                {"approved": True},
                "timesheets:manage_all",
            ),
        )

        for method, path, payload, permission in refusals:
            response = await getattr(client, method)(path, headers=hr_headers, json=payload)
            assert response.status_code == 403, f"{path}: {response.text}"
            assert response.json()["errors"][0]["message"] == permission

        await db_session.refresh(request)
        assert request.status == ApprovalStatus.PENDING.value, "a refusal must not have decided it"

    async def test_14_an_hr_executive_cannot_manage_leave_policy(
        self, client: AsyncClient, people: People
    ) -> None:
        headers = await _sign_in(client, people.hr_exec_user)

        response = await client.post(
            f"{HR}/leave/policies",
            headers=headers,
            json={"name": "Nope", "code": f"NP{uuid.uuid4().hex[:4].upper()}", "annual_allocation": 5},
        )
        assert response.status_code == 403, response.text
        assert response.json()["errors"][0]["message"] == "leave:policy_manage"

    async def test_14b_an_export_is_refused_without_the_module_permission(
        self, client: AsyncClient, db_session: AsyncSession, people: People
    ) -> None:
        """The catalogue and the download agree, and neither is a UI decision.

        An HR Executive holds ``reports:view`` -- so the catalogue answers -- and
        ``leave:export``, but not ``timesheets:export``. The report they cannot
        run is marked unavailable *and* refused when asked for anyway.
        """
        headers = await _sign_in(client, people.hr_exec_user)

        catalogue = await client.get(f"{HR}/reports", headers=headers)
        assert catalogue.status_code == 200, catalogue.text
        available = {item["key"]: item["available"] for item in catalogue.json()["data"]}
        assert available["timesheet"] is False
        assert available["leave-register"] is True

        refused = await client.get(f"{HR}/reports/timesheet/export", headers=headers, params={"fmt": "csv"})
        assert refused.status_code == 403, refused.text
        assert refused.json()["errors"][0]["message"] == "timesheets:export"

        allowed = await client.get(
            f"{HR}/reports/leave-register/export", headers=headers, params={"fmt": "csv"}
        )
        assert allowed.status_code == 200, allowed.text

    async def test_an_unknown_report_is_a_404_not_a_download(
        self, client: AsyncClient, hr_headers: dict[str, str]
    ) -> None:
        response = await client.get(
            f"{HR}/reports/security-audit/export", headers=hr_headers, params={"fmt": "csv"}
        )
        assert response.status_code == 404, response.text

    async def test_a_grant_is_what_changes_the_answer(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        people: People,
        leave_type: LeaveType,
    ) -> None:
        """The proof that none of this is a role-name check.

        The same HR account, the same request, refused and then allowed -- with
        nothing changed but one row in ``role_permissions``.
        """
        refused = await client.post(
            f"{HR}/leave/balances/{people.stranger.id}/adjust",
            headers=await _sign_in(client, people.hr_user),
            json={"leave_type_id": str(leave_type.id), "days": 2, "reason": "Goodwill gesture"},
        )
        assert refused.status_code == 403, refused.text

        await _grant(db_session, people.hr_user, "leave:balance_adjust")

        allowed = await client.post(
            f"{HR}/leave/balances/{people.stranger.id}/adjust",
            headers=await _sign_in(client, people.hr_user),
            json={"leave_type_id": str(leave_type.id), "days": 2, "reason": "Goodwill gesture"},
        )
        assert allowed.status_code == 200, allowed.text
        assert Decimal(allowed.json()["data"]["allocated"]) == Decimal("14.0")


# ======================================================================
# ADMIN
# ======================================================================
class TestAdminAccess:
    async def test_15_an_administrator_reaches_every_hr_module(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        for path in (
            "/dashboard",
            "/analytics",
            "/employees",
            "/attendance",
            "/leave",
            "/leave/policies",
            "/timesheets",
            "/documents",
            "/projects",
            "/performance",
            "/requests",
            "/reports",
        ):
            response = await client.get(f"{HR}{path}", headers=admin_headers)
            assert response.status_code == 200, f"{path}: {response.text}"

    async def test_16_an_administrator_manages_users(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            USERS,
            headers=admin_headers,
            json={
                "email": f"new.{uuid.uuid4().hex[:8]}@jsan.example",
                "username": f"new{uuid.uuid4().hex[:6]}",
                "first_name": "New",
                "last_name": "Starter",
                "password": PASSWORD,
            },
        )
        assert response.status_code == 201, response.text

    async def test_17_an_administrator_manages_roles_and_permissions(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        assert (await client.get(ROLES, headers=admin_headers)).status_code == 200
        assert (await client.get(f"{ROLES}/permissions", headers=admin_headers)).status_code == 200

        created = await client.post(
            ROLES,
            headers=admin_headers,
            json={
                "name": f"Payroll Clerk {uuid.uuid4().hex[:6]}",
                "permissions": ["attendance:view", "leave:view"],
            },
        )
        assert created.status_code == 201, created.text

    def test_18_19_20_an_administrator_holds_the_whole_catalogue(self) -> None:
        """Settings, reports and audit administration included.

        Asserted here for the same reason the HR version is: settings and audit
        have no endpoints yet, and the grant is what will decide the answer when
        they do.
        """
        held = set(SYSTEM_ROLES_BY_KEY["admin"].permissions)
        assert held == ALL_PERMISSIONS
        for permission in ("settings:view", "settings:update", "audit:view", "audit:export"):
            assert permission in held

    async def test_19b_every_report_is_available_to_an_administrator(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        response = await client.get(f"{HR}/reports", headers=admin_headers)
        assert all(item["available"] for item in response.json()["data"]), response.text

        for key in ("employees", "attendance", "leave-register", "document-compliance"):
            export = await client.get(
                f"{HR}/reports/{key}/export", headers=admin_headers, params={"fmt": "csv"}
            )
            assert export.status_code == 200, f"{key}: {export.text}"
            assert export.headers["content-type"].startswith("text/csv")

    async def test_21_an_administrator_performs_the_authorized_overrides(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        people: People,
        leave_type: LeaveType,
        admin_headers: dict[str, str],
    ) -> None:
        request = await _leave(db_session, people.stranger, leave_type)

        corrected = await client.post(
            f"{HR}/attendance/{people.stranger.id}/correct",
            headers=admin_headers,
            json={"attendance_date": "2026-03-04", "status": "absent", "reason": "Confirmed by payroll"},
        )
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["data"]["status"] == "absent"

        adjusted = await client.post(
            f"{HR}/leave/balances/{people.stranger.id}/adjust",
            headers=admin_headers,
            json={"leave_type_id": str(leave_type.id), "days": -2, "reason": "Correcting a duplicate credit"},
        )
        assert adjusted.status_code == 200, adjusted.text
        assert Decimal(adjusted.json()["data"]["allocated"]) == Decimal("10.0")

        overridden = await client.post(
            f"{HR}/leave/{request.id}/override",
            headers=admin_headers,
            json={"approved": True, "notes": "Manager is away"},
        )
        assert overridden.status_code == 200, overridden.text
        assert overridden.json()["data"]["status"] == ApprovalStatus.APPROVED.value

    async def test_21b_every_override_is_audited_as_one(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        people: People,
        leave_type: LeaveType,
        admin_headers: dict[str, str],
    ) -> None:
        """§19: an administrative act has to be distinguishable in the trail."""
        from app.models.audit_log import AuditAction, AuditLog

        request = await _leave(db_session, people.stranger, leave_type)
        await client.post(f"{HR}/leave/{request.id}/override", headers=admin_headers, json={"approved": True})
        await client.post(
            f"{HR}/attendance/{people.stranger.id}/correct",
            headers=admin_headers,
            json={"attendance_date": "2026-03-05", "status": "absent", "reason": "Payroll correction"},
        )
        await client.post(
            f"{HR}/leave/balances/{people.stranger.id}/adjust",
            headers=admin_headers,
            json={"leave_type_id": str(leave_type.id), "days": 1, "reason": "Carry forward correction"},
        )

        actions = set((await db_session.execute(select(AuditLog.action))).scalars().all())
        for expected in (
            AuditAction.LEAVE_DECISION_OVERRIDDEN,
            AuditAction.ATTENDANCE_CORRECTED,
            AuditAction.LEAVE_BALANCE_ADJUSTED,
        ):
            assert expected.value in actions, expected

    async def test_an_export_is_audited(
        self, client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
    ) -> None:
        from app.models.audit_log import AuditAction, AuditLog

        response = await client.get(
            f"{HR}/reports/employees/export", headers=admin_headers, params={"fmt": "csv"}
        )
        assert response.status_code == 200, response.text

        actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
        assert AuditAction.HR_REPORT_EXPORTED.value in set(actions)

    async def test_a_balance_adjustment_cannot_drop_below_what_is_taken(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        people: People,
        leave_type: LeaveType,
        admin_headers: dict[str, str],
    ) -> None:
        """The rule that keeps a balance reconciling with the requests behind it."""
        seed = await client.post(
            f"{HR}/leave/balances/{people.stranger.id}/adjust",
            headers=admin_headers,
            json={"leave_type_id": str(leave_type.id), "days": 1, "reason": "Opening the balance row"},
        )
        assert seed.status_code == 200, seed.text

        from app.models.workforce import LeaveBalance

        balance = (
            await db_session.execute(
                select(LeaveBalance).where(
                    LeaveBalance.employee_id == people.stranger.id,
                    LeaveBalance.leave_type_id == leave_type.id,
                )
            )
        ).scalar_one()
        balance.used = Decimal("10.0")
        await db_session.flush()

        response = await client.post(
            f"{HR}/leave/balances/{people.stranger.id}/adjust",
            headers=admin_headers,
            json={"leave_type_id": str(leave_type.id), "days": -8, "reason": "Trying to go below usage"},
        )
        assert response.status_code == 409, response.text
        assert response.json()["errors"][0]["code"] == "allocation_below_usage"


# ======================================================================
# SUPER ADMIN
# ======================================================================
class TestSuperAdminAccess:
    async def test_22_a_superuser_is_unaffected(
        self, client: AsyncClient, people: People, auth_headers: dict[str, str]
    ) -> None:
        for path in ("/dashboard", "/employees", "/attendance", "/leave", "/reports", "/requests"):
            response = await client.get(f"{HR}{path}", headers=auth_headers)
            assert response.status_code == 200, f"{path}: {response.text}"

        assert (await client.get(ROLES, headers=auth_headers)).status_code == 200
        assert (
            await client.get(f"{HR}/employees/{people.stranger.id}", headers=auth_headers)
        ).status_code == 200

    async def test_a_superuser_may_export_any_report(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """``is_superuser`` bypasses the permission check, including the export gate."""
        response = await client.get(
            f"{HR}/reports/timesheet/export", headers=auth_headers, params={"fmt": "csv"}
        )
        assert response.status_code == 200, response.text


# ======================================================================
# Leave policy meets the leave engine
# ======================================================================
class TestPolicyAffectsTheEngine:
    """Configuration with an effect, not configuration with a screen."""

    async def test_a_retired_policy_is_no_longer_offered(
        self, client: AsyncClient, db_session: AsyncSession, people: People, leave_type: LeaveType
    ) -> None:
        headers = await _sign_in(client, people.employee_user)

        before = await client.get(f"{API}/me/leave/types", headers=headers)
        assert str(leave_type.id) in {item["id"] for item in before.json()["data"]}

        leave_type.effective_to = date.today() - timedelta(days=1)
        await db_session.flush()

        after = await client.get(f"{API}/me/leave/types", headers=headers)
        assert str(leave_type.id) not in {item["id"] for item in after.json()["data"]}

    async def test_a_policy_that_has_not_started_is_not_offered_either(
        self, client: AsyncClient, db_session: AsyncSession, people: People, leave_type: LeaveType
    ) -> None:
        leave_type.effective_from = date.today() + timedelta(days=30)
        await db_session.flush()

        headers = await _sign_in(client, people.employee_user)
        response = await client.get(f"{API}/me/leave/types", headers=headers)
        assert str(leave_type.id) not in {item["id"] for item in response.json()["data"]}

    async def test_the_policy_screen_still_shows_a_retired_policy(
        self, client: AsyncClient, db_session: AsyncSession, leave_type: LeaveType, hr_headers: dict[str, str]
    ) -> None:
        """Otherwise nobody could extend the policy that expired last month."""
        leave_type.effective_to = date.today() - timedelta(days=1)
        await db_session.flush()

        response = await client.get(f"{HR}/leave/policies", headers=hr_headers)
        assert response.status_code == 200, response.text
        assert str(leave_type.id) in {item["id"] for item in response.json()["data"]}


# ======================================================================
# Structural guarantees
# ======================================================================
class TestNoRoleNameIsEverChecked:
    def test_the_codebase_contains_no_role_name_authorization(self) -> None:
        """§17 and §23: authorization is by permission, never by role name.

        A grep rather than a behavioural test, because the failure it guards
        against is a *new* line of code somewhere, not a wrong answer from an
        existing one -- and by the time it gives a wrong answer it has already
        shipped.
        """
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[2] / "app"
        # Comparisons against a role key: `role == "hr_admin"`, `key in {"admin"}`.
        pattern = re.compile(
            r"""(role|role_key|key)\s*(==|!=|\s+in\s+)\s*[\[({]?["'](hr_admin|hr_executive|admin|super_admin|manager|employee)["']"""
        )
        offenders = [
            f"{path.relative_to(root)}:{number}"
            for path in root.rglob("*.py")
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
            if pattern.search(line)
        ]
        assert not offenders, f"authorize on a permission, never on a role name: {offenders}"
