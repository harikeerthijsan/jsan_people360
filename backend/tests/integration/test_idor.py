"""Insecure-direct-object-reference tests: the production-hardening sweep.

Two suites, and the first is the one that matters over time.

**The coverage sweep** enumerates every route in the application that takes an
``{employee_id}`` and calls each one as a plain employee, pointed at a
*different* employee. Nothing may answer 2xx. It is written against the live
route table rather than a hand-maintained list, so an endpoint added next month
is tested the day it is merged -- the same property that makes
``TestGuardCoverage`` in ``test_rbac`` worth having.

A refusal is 401, 403 or 404. A 422 is also accepted, but reluctantly and with
a caveat stated here rather than buried: FastAPI validates the request body
while it solves dependencies, so a malformed body can be rejected *before* the
authorization guard runs. A 422 therefore proves the request did not succeed,
not that a guard exists. That is why the second suite sends **valid** bodies to
the endpoints that would otherwise create real data for somebody else -- an
attendance record, a leave request, a timesheet, a correction. Those four are
where an IDOR would not merely leak but forge.

The static half of the same question -- "is a guard *declared* on this route" --
is already answered by ``TestGuardCoverage``. Runtime refusal and declared guard
together are what make the claim.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import ClassVar

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.security import hash_password
from app.models.employee import Employee
from app.models.enums import EmploymentStatus
from app.models.rbac import Role, UserRole
from app.models.user import User

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
PASSWORD = "Str0ng!Passw0rd"

#: What a refusal may look like. 405 appears because the sweep tries every
#: method a path declares and some paths declare more than one.
REFUSALS = frozenset({401, 403, 404, 405, 409, 422})

#: How many routes currently reject an empty body before their authorization
#: guard runs. Pinned rather than ignored: a rise means a new endpoint whose
#: refusal this sweep has not actually proved.
_EXPECTED_SOFT_REFUSALS = 1

#: Paths whose ``{employee_id}`` is *not* an employee the caller could be.
#: Nothing is excluded for being inconvenient -- only where the segment names
#: something else entirely.
NOT_AN_EMPLOYEE_ID: frozenset[str] = frozenset()


async def _account(session: AsyncSession, role_key: str, label: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"{label}_{suffix}",
        first_name=label.title(),
        last_name="Tester",
        email=f"{label}.{suffix}@jsan.example",
        hashed_password=hash_password(PASSWORD),
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()
    role = (await session.execute(select(Role).where(Role.key == role_key))).scalars().first()
    assert role is not None, f"the {role_key} role should be seeded"
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.flush()
    return user


async def _employee(
    session: AsyncSession, label: str, *, user: User | None = None, manager: Employee | None = None
) -> Employee:
    suffix = uuid.uuid4().hex[:8]
    record = Employee(
        first_name=label.title(),
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


class Pair:
    """Two unrelated employees: the attacker, and the person they reach for."""

    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)

    attacker_user: User
    attacker: Employee
    victim_user: User
    victim: Employee
    manager_a_user: User
    manager_b_user: User
    victim_of_b: Employee


@pytest.fixture
async def pair(db_session: AsyncSession) -> Pair:
    manager_a_user = await _account(db_session, "manager", "mgra")
    manager_a = await _employee(db_session, "manager_a", user=manager_a_user)

    manager_b_user = await _account(db_session, "manager", "mgrb")
    manager_b = await _employee(db_session, "manager_b", user=manager_b_user)

    attacker_user = await _account(db_session, "employee", "attacker")
    victim_user = await _account(db_session, "employee", "victim")

    return Pair(
        attacker_user=attacker_user,
        attacker=await _employee(db_session, "attacker", user=attacker_user, manager=manager_a),
        victim_user=victim_user,
        victim=await _employee(db_session, "victim", user=victim_user, manager=manager_b),
        manager_a_user=manager_a_user,
        manager_b_user=manager_b_user,
        victim_of_b=await _employee(db_session, "victim_b", manager=manager_b),
    )


def _all_routes() -> list[APIRoute]:
    """Every registered API route.

    Walks ``original_router`` because included routers are kept nested rather
    than flattened into ``app.routes`` -- reading ``app.routes`` directly finds
    one route and silently passes a sweep that has tested nothing. This is the
    same walk ``TestGuardCoverage`` uses, and for the same reason.
    """

    def walk(router: object) -> list[APIRoute]:
        found: list[APIRoute] = []
        for route in getattr(router, "routes", []):
            inner = getattr(route, "original_router", None)
            if inner is not None:
                found.extend(walk(inner))
            elif isinstance(route, APIRoute):
                found.append(route)
        return found

    return walk(api_router)


def _employee_id_routes() -> list[tuple[str, str]]:
    """(method, path) for every route with an ``{employee_id}`` segment."""
    found: list[tuple[str, str]] = []
    for route in _all_routes():
        if "{employee_id}" not in route.path or route.path in NOT_AN_EMPLOYEE_ID:
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            found.append((method, f"{settings.API_V1_PREFIX}{route.path}"))
    return sorted(found)


# ======================================================================
# Static coverage: is a scope guard declared at all?
# ======================================================================
class TestScopeCoverage:
    """Every ``{employee_id}`` route is scoped, or is listed here with a reason.

    The runtime sweep below can be fooled: a random id in another path segment
    can 404 before the authorization guard is reached, and an empty body can
    422 before it. That is exactly how five unscoped routes survived until this
    audit -- ``/performance/reviews/{cycle_id}/{employee_id}`` answered 404 for
    a made-up cycle and looked safe.

    This test cannot be fooled that way, because it reads the route table
    instead of calling it. It is the scope counterpart to
    ``TestGuardCoverage``: that one asks "is there a permission", this one asks
    "is there an answer to *whose record*".
    """

    #: Routes that are organization-wide by design. Each is guarded by a
    #: permission that is itself org-wide -- an administrative action, or one
    #: paired with ``employees:view_all`` -- so a reporting-line narrowing would
    #: be wrong rather than missing.
    ORG_WIDE: ClassVar[dict[str, str]] = {
        "/hr/employees/{employee_id}": "require_org_wide: employees:view AND employees:view_all.",
        "/hr/attendance/{employee_id}/correct": "attendance:manage_all is administrative by definition.",
        "/hr/leave/balances/{employee_id}/adjust": "leave:balance_adjust is administrative by definition.",
        "/manager/team/{employee_id}": "Checked against ManagerScope in the handler before any read; "
        "asserted at runtime by TestManagerCannotReachAnotherTeam.",
    }

    def test_every_employee_id_route_is_scoped_or_listed(self) -> None:
        unscoped: list[str] = []
        for route in _all_routes():
            if "{employee_id}" not in route.path or route.path in self.ORG_WIDE:
                continue
            scoped = any(
                getattr(getattr(dependency, "dependency", None), "__rbac_scope__", None)
                for dependency in route.dependencies
            )
            if not scoped:
                unscoped.append(route.path)

        assert not unscoped, (
            "these routes take an employee id with no scope guard -- add "
            "require_team_scope() or require_self_or(...), or list them in ORG_WIDE "
            f"with the reason: {sorted(set(unscoped))}"
        )

    def test_the_allowlist_has_not_gone_stale(self) -> None:
        """A path that no longer exists must not sit here granting exemption."""
        live = {route.path for route in _all_routes()}
        assert not set(self.ORG_WIDE) - live, f"stale entries: {set(self.ORG_WIDE) - live}"


# ======================================================================
# The sweep
# ======================================================================
class TestEmployeeCannotReachAnotherEmployee:
    async def test_the_sweep_covers_every_employee_id_route(self) -> None:
        """A guard against the guard: if this ever finds nothing, it is broken."""
        routes = _employee_id_routes()
        assert len(routes) >= 20, f"expected the employee-id surface to be large, found {routes}"

    async def test_no_employee_id_route_answers_a_stranger(self, client: AsyncClient, pair: Pair) -> None:
        headers = await _sign_in(client, pair.attacker_user)
        victim = str(pair.victim.id)

        leaked: list[str] = []
        soft: list[str] = []
        for method, path in _employee_id_routes():
            url = path.replace("{employee_id}", victim)
            # Any other id segment is filled with a random uuid: the point is
            # the employee id, and a well-formed stranger id elsewhere keeps the
            # request from failing for the wrong reason.
            while "{" in url:
                start = url.index("{")
                end = url.index("}", start)
                url = url[:start] + str(uuid.uuid4()) + url[end + 1 :]

            response = await client.request(method, url, headers=headers, json={})
            if response.status_code < 400:
                leaked.append(f"{method} {path} -> {response.status_code}")
            elif response.status_code == 422:
                soft.append(f"{method} {path}")
            elif response.status_code not in REFUSALS:
                leaked.append(f"{method} {path} -> {response.status_code} (unexpected)")

        assert not leaked, "an employee reached another employee's record:\n" + "\n".join(leaked)

        # `soft` holds the routes that answered 422: the body was rejected
        # before the guard was reached, so this sweep proved only that the
        # request failed, not that it was refused *for the right reason*.
        # TestScopeCoverage answers that statically for all of them, and
        # TestWritesAreRefusedWithValidBodies answers it with real bodies for
        # the four that would forge rather than leak. Asserted rather than
        # printed so the number is visible when it changes, without pytest
        # having to run with -s.
        assert len(soft) <= _EXPECTED_SOFT_REFUSALS, (
            f"{len(soft)} route(s) now answer 422 before their guard is reached "
            f"(was {_EXPECTED_SOFT_REFUSALS}): {soft}. Each needs a valid-body test "
            "or a scope guard confirmed by TestScopeCoverage."
        )

    async def test_a_stranger_profile_is_refused_specifically(self, client: AsyncClient, pair: Pair) -> None:
        headers = await _sign_in(client, pair.attacker_user)
        response = await client.get(f"{API}/employees/{pair.victim.id}", headers=headers)
        assert response.status_code == 403

    async def test_the_sensitive_reveal_is_refused(self, client: AsyncClient, pair: Pair) -> None:
        """The one endpoint that returns an unmasked Aadhaar and account number."""
        headers = await _sign_in(client, pair.attacker_user)
        response = await client.get(f"{API}/employees/{pair.victim.id}/sensitive", headers=headers)
        assert response.status_code == 403

    async def test_own_record_is_still_reachable(self, client: AsyncClient, pair: Pair) -> None:
        """The refusals above must not be a blanket 403 on everything."""
        headers = await _sign_in(client, pair.attacker_user)
        assert (await client.get(f"{API}/me/attendance", headers=headers)).status_code == 200
        assert (await client.get(f"{API}/me/leave/balance", headers=headers)).status_code == 200
        assert (await client.get(f"{API}/users/me", headers=headers)).status_code == 200


# ======================================================================
# Writes, with bodies good enough to have worked
# ======================================================================
class TestWritesAreRefusedWithValidBodies:
    """The four endpoints where an IDOR would forge rather than leak.

    Each body below is one the server would accept for the caller's own record,
    so a 403 here is the authorization guard refusing and not the validator.
    """

    async def test_cannot_check_in_as_another_employee(self, client: AsyncClient, pair: Pair) -> None:
        headers = await _sign_in(client, pair.attacker_user)
        response = await client.post(
            f"{API}/workforce/attendance/{pair.victim.id}/check-in",
            json={"work_mode": "office"},
            headers=headers,
        )
        assert response.status_code == 403, response.text

    async def test_cannot_apply_for_leave_as_another_employee(self, client: AsyncClient, pair: Pair) -> None:
        headers = await _sign_in(client, pair.attacker_user)
        types = await client.get(f"{API}/me/leave/types", headers=headers)
        available = types.json()["data"]
        if not available:
            pytest.skip("no leave types seeded")
        response = await client.post(
            f"{API}/workforce/leave/{pair.victim.id}",
            json={
                "leave_type_id": available[0]["id"],
                "from_date": (date.today() + timedelta(days=3)).isoformat(),
                "to_date": (date.today() + timedelta(days=4)).isoformat(),
                "reason": "Forged",
            },
            headers=headers,
        )
        assert response.status_code == 403, response.text

    async def test_cannot_save_a_timesheet_as_another_employee(self, client: AsyncClient, pair: Pair) -> None:
        headers = await _sign_in(client, pair.attacker_user)
        monday = date.today() - timedelta(days=date.today().weekday())
        response = await client.post(
            f"{API}/workforce/timesheets/{pair.victim.id}",
            json={"week_start_date": monday.isoformat(), "entries": []},
            headers=headers,
        )
        assert response.status_code == 403, response.text

    async def test_cannot_request_a_correction_as_another_employee(
        self, client: AsyncClient, pair: Pair
    ) -> None:
        headers = await _sign_in(client, pair.attacker_user)
        response = await client.post(
            f"{API}/workforce/regularizations/{pair.victim.id}",
            json={
                "attendance_date": (date.today() - timedelta(days=1)).isoformat(),
                "reason": "Forged correction request",
                "requested_check_in_at": f"{(date.today() - timedelta(days=1)).isoformat()}T09:00:00Z",
                "requested_check_out_at": f"{(date.today() - timedelta(days=1)).isoformat()}T18:00:00Z",
            },
            headers=headers,
        )
        assert response.status_code == 403, response.text


# ======================================================================
# Manager A against Manager B's team
# ======================================================================
class TestManagerCannotReachAnotherTeam:
    async def test_no_employee_id_route_answers_another_managers_team(
        self, client: AsyncClient, pair: Pair
    ) -> None:
        """A manager holds the approve permissions, so only scope stops them."""
        headers = await _sign_in(client, pair.manager_a_user)
        victim = str(pair.victim_of_b.id)

        leaked: list[str] = []
        for method, path in _employee_id_routes():
            url = path.replace("{employee_id}", victim)
            while "{" in url:
                start = url.index("{")
                end = url.index("}", start)
                url = url[:start] + str(uuid.uuid4()) + url[end + 1 :]
            response = await client.request(method, url, headers=headers, json={})
            if response.status_code < 400:
                leaked.append(f"{method} {path} -> {response.status_code}")

        assert not leaked, "a manager reached another manager's team:\n" + "\n".join(leaked)

    async def test_the_team_profile_route_is_scoped(self, client: AsyncClient, pair: Pair) -> None:
        headers = await _sign_in(client, pair.manager_a_user)
        response = await client.get(f"{API}/manager/team/{pair.victim_of_b.id}", headers=headers)
        assert response.status_code == 403

    async def test_a_manager_still_reaches_their_own_report(self, client: AsyncClient, pair: Pair) -> None:
        headers = await _sign_in(client, pair.manager_a_user)
        response = await client.get(f"{API}/manager/team/{pair.attacker.id}", headers=headers)
        assert response.status_code == 200, response.text
