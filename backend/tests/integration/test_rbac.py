"""Integration tests for role-based access control.

The tests that matter here are the *negative* ones. A permissions system that
grants correctly but never actually refuses is indistinguishable from no
permissions system at all, and it fails silently -- everything looks right until
somebody reads a salary they should not have seen.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import ClassVar

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.permissions import ALL_PERMISSIONS, SYSTEM_ROLES, all_permission_codes
from app.core.security import hash_password
from app.models.rbac import Role, UserRole
from app.models.user import User
from app.services.authorization_service import AuthorizationService

pytestmark = pytest.mark.integration

EMPLOYEES = f"{settings.API_V1_PREFIX}/employees"


async def _role(session: AsyncSession, key: str) -> Role:
    role = (await session.execute(select(Role).where(Role.key == key))).scalars().first()
    assert role is not None, f"migration 0015 should have seeded the {key} role"
    return role


async def _user_with_role(session: AsyncSession, key: str) -> tuple[User, str]:
    """An active, non-superuser account holding exactly one seeded role."""
    password = "Str0ng!Passw0rd"
    user = User(
        username=f"rbac_{key}_{uuid.uuid4().hex[:8]}",
        first_name=key.replace("_", " ").title(),
        last_name="Tester",
        email=f"rbac.{key}.{uuid.uuid4().hex[:8]}@jsan.example",
        hashed_password=hash_password(password),
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()

    role = await _role(session, key)
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.flush()
    return user, password


async def _sign_in(client: AsyncClient, user: User, password: str) -> dict[str, str]:
    response = await client.post(
        f"{settings.API_V1_PREFIX}/auth/login", json={"email": user.email, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['tokens']['access_token']}"}


# ----------------------------------------------------------------------
class TestSeededCatalogue:
    async def test_every_registry_permission_exists_in_the_database(self, db_session: AsyncSession) -> None:
        """The table is a mirror of the registry; drift makes guards unsatisfiable."""
        from app.models.rbac import Permission

        stored = set((await db_session.execute(select(Permission.code))).scalars().all())
        assert stored == set(all_permission_codes())

    async def test_the_eight_shipped_roles_are_marked_system(self, db_session: AsyncSession) -> None:
        rows = (await db_session.execute(select(Role).where(Role.is_system.is_(True)))).scalars().all()
        assert {role.key for role in rows} == {role.key for role in SYSTEM_ROLES}

    async def test_super_admin_holds_the_whole_catalogue(self, db_session: AsyncSession) -> None:
        user, _ = await _user_with_role(db_session, "super_admin")
        held = await AuthorizationService(db_session).permissions_for(user)
        assert held == ALL_PERMISSIONS


# ----------------------------------------------------------------------
class TestResolution:
    async def test_permissions_union_across_several_roles(self, db_session: AsyncSession) -> None:
        """Two roles means both sets, not the narrower one."""
        user, _ = await _user_with_role(db_session, "recruiter")
        session_service = AuthorizationService(db_session)
        recruiter_only = await session_service.permissions_for(user)

        db_session.add(UserRole(user_id=user.id, role_id=(await _role(db_session, "manager")).id))
        await db_session.flush()

        combined = await session_service.permissions_for(user)
        assert combined > recruiter_only
        assert "leave:approve" in combined, "the manager role should have added leave approval"
        assert "recruitment:create" in combined, "the recruiter role should still apply"

    async def test_deactivating_a_role_revokes_it_immediately(self, db_session: AsyncSession) -> None:
        """The fastest lever an administrator has must work on existing grants."""
        user, _ = await _user_with_role(db_session, "hr_admin")
        service = AuthorizationService(db_session)
        assert "employees:view" in await service.permissions_for(user)

        role = await _role(db_session, "hr_admin")
        role.status = "inactive"
        await db_session.flush()

        assert await service.permissions_for(user) == frozenset()

    async def test_a_user_with_no_roles_holds_nothing(self, db_session: AsyncSession) -> None:
        user = User(
            username=f"norole_{uuid.uuid4().hex[:8]}",
            first_name="No",
            last_name="Role",
            email=f"norole.{uuid.uuid4().hex[:8]}@jsan.example",
            hashed_password=hash_password("Str0ng!Passw0rd"),
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user)
        await db_session.flush()

        assert await AuthorizationService(db_session).permissions_for(user) == frozenset()


# ----------------------------------------------------------------------
class TestEnforcement:
    """The negative cases. These are the reason the module exists."""

    async def test_an_employee_cannot_browse_the_employee_master(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user, password = await _user_with_role(db_session, "employee")
        headers = await _sign_in(client, user, password)

        response = await client.get(EMPLOYEES, headers=headers)
        assert response.status_code == 403
        assert response.json()["errors"][0]["message"] == "employees:view"

    async def test_an_employee_cannot_read_sensitive_fields(
        self, client: AsyncClient, db_session: AsyncSession, employee
    ) -> None:
        """Salary, bank details and Aadhaar. The exposure RBAC was built to close."""
        user, password = await _user_with_role(db_session, "employee")
        headers = await _sign_in(client, user, password)

        response = await client.get(f"{EMPLOYEES}/{employee.id}/sensitive", headers=headers)
        assert response.status_code == 403

    async def test_an_employee_cannot_export_the_directory(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user, password = await _user_with_role(db_session, "employee")
        headers = await _sign_in(client, user, password)

        response = await client.get(f"{EMPLOYEES}/export", headers=headers)
        assert response.status_code == 403

    async def test_an_hr_executive_may_read_but_not_archive(
        self, client: AsyncClient, db_session: AsyncSession, employee
    ) -> None:
        """The gradient is the point: view and update without the destructive action."""
        user, password = await _user_with_role(db_session, "hr_executive")
        headers = await _sign_in(client, user, password)

        assert (await client.get(EMPLOYEES, headers=headers)).status_code == 200

        archived = await client.post(f"{EMPLOYEES}/{employee.id}/archive", headers=headers)
        assert archived.status_code == 403
        assert archived.json()["errors"][0]["message"] == "employees:delete"

    async def test_an_hr_admin_may_archive(
        self, client: AsyncClient, db_session: AsyncSession, employee
    ) -> None:
        user, password = await _user_with_role(db_session, "hr_admin")
        headers = await _sign_in(client, user, password)

        response = await client.post(f"{EMPLOYEES}/{employee.id}/archive", headers=headers)
        assert response.status_code == 200, response.text

    async def test_a_recruiter_cannot_create_employees(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A recruiter sees candidates. Turning one into an employee is HR's decision."""
        user, password = await _user_with_role(db_session, "recruiter")
        headers = await _sign_in(client, user, password)

        response = await client.post(
            EMPLOYEES,
            json={
                "first_name": "Should",
                "last_name": "Fail",
                "official_email": f"nope.{uuid.uuid4().hex[:8]}@jsan.example",
                "joining_date": date.today().isoformat(),
            },
            headers=headers,
        )
        assert response.status_code == 403

    async def test_a_superuser_bypasses_every_guard(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """The bootstrap account must never be locked out of the screen that fixes grants."""
        assert (await client.get(EMPLOYEES, headers=auth_headers)).status_code == 200
        assert (await client.get(f"{EMPLOYEES}/export", headers=auth_headers)).status_code == 200

    async def test_an_unauthenticated_caller_still_gets_401_not_403(self, client: AsyncClient) -> None:
        """Order matters: authentication is answered before authorization, or an
        anonymous caller learns which permission an endpoint wants."""
        assert (await client.get(EMPLOYEES)).status_code == 401


# ----------------------------------------------------------------------
class TestGuardCoverage:
    """Every endpoint is guarded, or is on this list for a stated reason.

    This is the test that matters most over time. The retrofit was a one-off;
    the risk that outlives it is a *new* endpoint merged without a guard, which
    looks exactly like a working endpoint until somebody reads something they
    should not have.
    """

    #: Deliberately reachable with nothing but a valid session -- or none at all.
    UNGUARDED: ClassVar[dict[str, str]] = {
        "GET /health": "Liveness probe; must answer before anything is configured.",
        "GET /health/ready": "Readiness probe, same reason.",
        "POST /auth/login": "Anonymous by definition.",
        "POST /auth/refresh": "Carries a refresh cookie, not a session.",
        "POST /auth/logout": "Ending a session needs no permission.",
        "GET /auth/me": "Your own identity and permissions.",
        "POST /auth/forgot-password": "Anonymous.",
        "POST /auth/reset-password": "Anonymous; the token is the credential.",
        "POST /auth/change-password": "Your own password.",
        "GET /users/me": "Your own account.",
        "PATCH /users/me": "Your own account.",
        "GET /organizations/primary": "Company name and logo; the shell renders it for everyone.",
        "GET /notifications": "Your own inbox.",
        "POST /notifications/{notification_id}/read": "Your own inbox.",
    }

    @staticmethod
    def _routes():
        from fastapi.routing import APIRoute

        from app.api.v1.router import api_router

        def walk(router):
            for route in getattr(router, "routes", []):
                inner = getattr(route, "original_router", None)
                if inner is not None:
                    yield from walk(inner)
                elif isinstance(route, APIRoute):
                    yield route

        return list(walk(api_router))

    @staticmethod
    def _permissions(route) -> list[str]:
        found: list[str] = []
        stack = list(route.dependant.dependencies)
        while stack:
            dependency = stack.pop()
            call = getattr(dependency, "call", None)
            if call is not None and hasattr(call, "__rbac_permissions__"):
                found.extend(call.__rbac_permissions__)
            stack.extend(dependency.dependencies)
        return found

    @staticmethod
    def _is_self_service(route) -> bool:
        """Whether the route is guarded by identity instead of by permission.

        A ``/me`` endpoint resolves its subject from the access token and takes
        no employee id, so there is no "whose record" question for a permission
        to answer. Recognising that as its own category keeps this test's signal
        intact: the alternative was thirty more lines of ``UNGUARDED``, at which
        point the list stops being read and a genuinely unguarded endpoint slips
        in among them.

        The tag is set on ``get_current_employee``, so a route earns it by
        actually depending on the self-service identity -- not by being named
        ``/me``.
        """
        stack = list(route.dependant.dependencies)
        while stack:
            dependency = stack.pop()
            call = getattr(dependency, "call", None)
            if call is not None and getattr(call, "__rbac_self_service__", False):
                return True
            stack.extend(dependency.dependencies)
        return False

    def test_every_endpoint_is_guarded_or_listed(self) -> None:
        unguarded = {
            f"{sorted(route.methods - {'HEAD'})[0]} {route.path}"
            for route in self._routes()
            if not self._permissions(route) and not self._is_self_service(route)
        }
        assert unguarded == set(self.UNGUARDED), (
            "An endpoint is unguarded and not listed. Either add a require(...) "
            "guard, take CurrentEmployee so it is self-service by construction, "
            "or add it to UNGUARDED with the reason it needs none."
        )

    def test_self_service_endpoints_never_accept_an_employee_id(self) -> None:
        """The structural half of the IDOR guarantee.

        ``test_self_service.py`` proves employee A cannot read employee B's
        records. This proves the stronger thing: there is no parameter through
        which they could try. A ``/me`` route that grew an ``employee_id`` would
        be back to relying on somebody remembering to check it.
        """
        offenders: dict[str, list[str]] = {}
        for route in self._routes():
            if not self._is_self_service(route):
                continue
            names = [
                field.name
                for field in (
                    route.dependant.path_params + route.dependant.query_params + route.dependant.body_params
                )
            ]
            named = [name for name in names if name in {"employee_id", "user_id", "owner_id"}]
            if named:
                offenders[f"{sorted(route.methods - {'HEAD'})[0]} {route.path}"] = named

        assert not offenders, f"self-service routes must not take an identity parameter: {offenders}"

    def test_every_guard_names_a_real_permission(self) -> None:
        """A guard on a permission nobody can hold is a locked door with no key."""
        for route in self._routes():
            for permission in self._permissions(route):
                assert permission in ALL_PERMISSIONS, f"{route.path} guards on unknown {permission}"

    def test_the_sensitive_employee_endpoints_are_guarded(self) -> None:
        """Named explicitly because this is the exposure RBAC was built to close."""
        wanted = {
            "GET /employees/{employee_id}/sensitive",
            "GET /employees/{employee_id}",
            "GET /employees",
            "GET /employees/export",
        }
        seen = {
            f"{sorted(route.methods - {'HEAD'})[0]} {route.path}": self._permissions(route)
            for route in self._routes()
        }
        for endpoint in wanted:
            assert seen.get(endpoint), f"{endpoint} must carry a permission guard"


# ----------------------------------------------------------------------
class TestRoleAdministration:
    ROLES = f"{settings.API_V1_PREFIX}/roles"

    async def test_the_catalogue_is_grouped(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        response = await client.get(f"{self.ROLES}/permissions", headers=auth_headers)
        assert response.status_code == 200, response.text

        groups = response.json()["data"]
        codes = {
            permission["code"]
            for group in groups
            for module in group["modules"]
            for permission in module["permissions"]
        }
        assert codes == set(ALL_PERMISSIONS), "the catalogue must expose every permission"

    async def test_creating_a_custom_role(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        response = await client.post(
            self.ROLES,
            json={
                "name": f"Payroll Clerk {uuid.uuid4().hex[:6]}",
                "description": "Reads attendance and leave for payroll runs.",
                "permissions": ["attendance:view", "leave:view", "reports:export"],
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["is_system"] is False
        assert data["permissions"] == ["attendance:view", "leave:view", "reports:export"]
        assert data["user_count"] == 0

    async def test_a_role_cannot_grant_an_invented_permission(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Rejected by the schema, so a typo never reaches the grant table."""
        response = await client.post(
            self.ROLES,
            json={"name": "Nonsense", "permissions": ["employees:teleport"]},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_a_system_role_cannot_be_renamed(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        role = await _role(db_session, "hr_admin")
        response = await client.patch(
            f"{self.ROLES}/{role.id}", json={"name": "Renamed"}, headers=auth_headers
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "system_role_immutable"

    async def test_a_system_role_permission_set_can_be_changed(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """What a role means is the company's decision, even for a shipped one."""
        role = await _role(db_session, "hr_executive")
        response = await client.patch(
            f"{self.ROLES}/{role.id}",
            json={"permissions": ["employees:view", "documents:view"]},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["permissions"] == ["documents:view", "employees:view"]

    async def test_a_system_role_cannot_be_deleted(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        role = await _role(db_session, "recruiter")
        response = await client.delete(f"{self.ROLES}/{role.id}", headers=auth_headers)
        assert response.status_code == 409

    async def test_a_role_in_use_cannot_be_deleted(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """Deleting it would strip access from people the dialog cannot show you."""
        created = await client.post(
            self.ROLES,
            json={"name": f"Temporary {uuid.uuid4().hex[:6]}", "permissions": ["leave:view"]},
            headers=auth_headers,
        )
        role_id = created.json()["data"]["id"]

        user, _ = await _user_with_role(db_session, "employee")
        db_session.add(UserRole(user_id=user.id, role_id=uuid.UUID(role_id)))
        await db_session.flush()

        response = await client.delete(f"{self.ROLES}/{role_id}", headers=auth_headers)
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "role_in_use"

    async def test_super_admin_cannot_lose_the_ability_to_fix_roles(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """Otherwise the administrator locks the door with the key still inside."""
        role = await _role(db_session, "super_admin")
        response = await client.patch(
            f"{self.ROLES}/{role.id}", json={"permissions": ["employees:view"]}, headers=auth_headers
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "would_lock_out"

    async def test_assigning_roles_replaces_the_whole_set(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        user, _ = await _user_with_role(db_session, "employee")
        manager = await _role(db_session, "manager")
        recruiter = await _role(db_session, "recruiter")

        response = await client.put(
            f"{settings.API_V1_PREFIX}/users/{user.id}/roles",
            json={"role_ids": [str(manager.id), str(recruiter.id)]},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text

        data = response.json()["data"]
        assert {role["key"] for role in data["roles"]} == {"manager", "recruiter"}
        assert "employee" not in {role["key"] for role in data["roles"]}, "the old role is replaced"
        assert "leave:approve" in data["permissions"]

    async def test_a_role_without_permission_cannot_reach_role_administration(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user, password = await _user_with_role(db_session, "hr_executive")
        headers = await _sign_in(client, user, password)

        assert (await client.get(self.ROLES, headers=headers)).status_code == 403
        assert (await client.get(f"{self.ROLES}/permissions", headers=headers)).status_code == 403


# ----------------------------------------------------------------------
class TestSessionPayload:
    async def test_me_carries_roles_and_permissions(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """The shell renders its menu from this, so it has to be right first time."""
        user, password = await _user_with_role(db_session, "recruiter")
        headers = await _sign_in(client, user, password)

        response = await client.get(f"{settings.API_V1_PREFIX}/auth/me", headers=headers)
        assert response.status_code == 200, response.text

        data = response.json()["data"]
        assert data["user"]["email"] == user.email
        assert [role["key"] for role in data["roles"]] == ["recruiter"]
        assert "recruitment:create" in data["permissions"]
        assert "employees:delete" not in data["permissions"]
        assert data["is_superuser"] is False


# ----------------------------------------------------------------------
class TestSelfScoping:
    """An employee acts on their own record and nobody else's.

    Permissions answer "may you call this endpoint". They say nothing about
    *whose* row is being asked for, which is how an Employee-role account could
    read a colleague's leave balances by changing the id in the URL. These are
    the tests that keep that shut.
    """

    WF = f"{settings.API_V1_PREFIX}/workforce"

    @staticmethod
    async def _linked(session: AsyncSession, role: str):
        """An account with a role *and* an employee record attached to it."""
        from app.models.employee import Employee
        from app.models.enums import EmploymentStatus

        user, password = await _user_with_role(session, role)
        employee = Employee(
            first_name="Self",
            last_name="Owner",
            official_email=f"self.{uuid.uuid4().hex[:8]}@jsan.example",
            joining_date=date(2025, 4, 1),
            employment_status=EmploymentStatus.ACTIVE,
            user_id=user.id,
        )
        session.add(employee)
        await session.flush()
        return user, password, employee

    async def test_an_employee_reads_their_own_leave_balances(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user, password, employee = await self._linked(db_session, "employee")
        headers = await _sign_in(client, user, password)

        response = await client.get(f"{self.WF}/leave/balances/{employee.id}", headers=headers)
        assert response.status_code == 200, response.text

    async def test_an_employee_cannot_read_somebody_elses_leave_balances(
        self, client: AsyncClient, db_session: AsyncSession, employee
    ) -> None:
        """The exact request that succeeded before the guard existed."""
        user, password, _own = await self._linked(db_session, "employee")
        headers = await _sign_in(client, user, password)

        response = await client.get(f"{self.WF}/leave/balances/{employee.id}", headers=headers)
        assert response.status_code == 403
        assert response.json()["errors"][0]["code"] == "not_your_record"

    async def test_an_employee_cannot_read_somebody_elses_attendance(
        self, client: AsyncClient, db_session: AsyncSession, employee
    ) -> None:
        user, password, _own = await self._linked(db_session, "employee")
        headers = await _sign_in(client, user, password)

        response = await client.get(
            f"{self.WF}/calendar/{employee.id}", params={"year": 2026, "month": 8}, headers=headers
        )
        assert response.status_code == 403

    async def test_an_employee_cannot_check_in_as_somebody_else(
        self, client: AsyncClient, db_session: AsyncSession, employee
    ) -> None:
        """Writes matter more than reads: this would forge another person's day."""
        user, password, _own = await self._linked(db_session, "employee")
        headers = await _sign_in(client, user, password)

        response = await client.post(
            f"{self.WF}/attendance/{employee.id}/check-in",
            json={"work_mode": "office"},
            headers=headers,
        )
        assert response.status_code == 403

    async def test_a_manager_may_read_their_reports(
        self, client: AsyncClient, db_session: AsyncSession, employee
    ) -> None:
        """Approving is what the escalation exists for, so it must still work."""
        user, password, own = await self._linked(db_session, "manager")

        # The reporting line has to be real. Holding ``leave:approve`` used to be
        # enough on its own; team scoping is precisely the change that made
        # "somebody's manager" a fact about the org chart rather than about the
        # permission, so a test that skipped this would now be asserting the
        # opposite of its own name.
        employee.reporting_manager_id = own.id
        await db_session.flush()

        headers = await _sign_in(client, user, password)
        response = await client.get(f"{self.WF}/leave/balances/{employee.id}", headers=headers)
        assert response.status_code == 200, response.text

    async def test_a_manager_may_not_read_somebody_who_is_not_their_report(
        self, client: AsyncClient, db_session: AsyncSession, employee
    ) -> None:
        """``leave:approve`` is not a licence over the whole company.

        The companion to the test above, and the more important of the two: the
        permission is unchanged, only the reporting line differs. Full coverage
        of team scoping lives in ``test_team_scoping.py``.
        """
        user, password, _own = await self._linked(db_session, "manager")
        headers = await _sign_in(client, user, password)

        response = await client.get(f"{self.WF}/leave/balances/{employee.id}", headers=headers)
        assert response.status_code == 403, response.text
        assert response.json()["errors"][0]["code"] == "outside_your_team"

    async def test_a_superuser_is_unaffected(
        self, client: AsyncClient, auth_headers: dict[str, str], employee
    ) -> None:
        response = await client.get(f"{self.WF}/leave/balances/{employee.id}", headers=auth_headers)
        assert response.status_code == 200, response.text
