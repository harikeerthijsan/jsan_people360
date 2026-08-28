"""Integration tests for the manager and team-management endpoints.

The shape of almost every test here is the same: two managers with a report
each, and the same request made by both. A manager screen that shows the right
team is not evidence of anything -- a screen with no scoping at all shows the
right team too, plus everybody else's. What these assert is the refusals.

Three refusals matter most, and each has its own reason for existing:

* **Another manager's report.** The reporting line is the rule, and holding
  ``leave:approve`` is not a licence over the company.
* **The manager themselves.** A manager is deliberately not in their own team
  scope, so they cannot approve their own leave through a team screen. Their
  request goes to their own manager, like everybody else's.
* **An unrestricted caller.** An HR administrator's ordinary scope is the whole
  organization. If the manager screens used it, "my team" would silently mean
  "everybody" for the people most likely to open it by accident.
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
from app.core.security import hash_password
from app.models.document import Document
from app.models.document_category import DocumentCategory, DocumentType
from app.models.employee import Employee
from app.models.enums import (
    ApprovalStatus,
    DocumentOwnerType,
    DocumentStatus,
    EmploymentStatus,
    RecordStatus,
)
from app.models.rbac import Role, UserRole
from app.models.user import User
from app.models.workforce import (
    AttendanceRecord,
    AttendanceRegularization,
    LeaveRequest,
    LeaveType,
    Timesheet,
)
from app.services.authorization_service import AuthorizationService
from app.services.scope_service import EmployeeScope, TeamScopeService

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
MANAGER = f"{API}/manager"
EMPLOYEES = f"{API}/employees"
WORKFORCE = f"{API}/workforce"

PASSWORD = "Str0ng!Passw0rd"


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
async def _account(session: AsyncSession, role_key: str | None, label: str) -> User:
    """An active, non-superuser account holding at most one seeded role."""
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

    if role_key is not None:
        role = (await session.execute(select(Role).where(Role.key == role_key))).scalars().first()
        assert role is not None, f"the {role_key} role should have been seeded"
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


async def _sign_in(client: AsyncClient, user: User) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['tokens']['access_token']}"}


class Org:
    """Two managers, two teams, and nothing shared between them."""

    def __init__(
        self,
        *,
        manager_a: Employee,
        manager_a_user: User,
        report_a1: Employee,
        report_a2: Employee,
        manager_b: Employee,
        manager_b_user: User,
        report_b1: Employee,
    ) -> None:
        self.manager_a = manager_a
        self.manager_a_user = manager_a_user
        self.report_a1 = report_a1
        self.report_a2 = report_a2
        self.manager_b = manager_b
        self.manager_b_user = manager_b_user
        self.report_b1 = report_b1


@pytest.fixture
async def org(db_session: AsyncSession) -> Org:
    manager_a_user = await _account(db_session, "manager", "mgr_a")
    manager_a = await _employee(db_session, "manager_a", user=manager_a_user)

    manager_b_user = await _account(db_session, "manager", "mgr_b")
    manager_b = await _employee(db_session, "manager_b", user=manager_b_user)

    return Org(
        manager_a=manager_a,
        manager_a_user=manager_a_user,
        report_a1=await _employee(db_session, "report_a1", manager=manager_a),
        report_a2=await _employee(db_session, "report_a2", manager=manager_a),
        manager_b=manager_b,
        manager_b_user=manager_b_user,
        # Reports to somebody else rather than to nobody: an unmanaged employee
        # would pass a buggy `IS NULL` check that a properly scoped query refuses.
        report_b1=await _employee(db_session, "report_b1", manager=manager_b),
    )


@pytest.fixture
async def headers_a(client: AsyncClient, org: Org) -> dict[str, str]:
    return await _sign_in(client, org.manager_a_user)


@pytest.fixture
async def headers_b(client: AsyncClient, org: Org) -> dict[str, str]:
    return await _sign_in(client, org.manager_b_user)


@pytest.fixture
async def leave_type(db_session: AsyncSession) -> LeaveType:
    record = LeaveType(
        name="Casual Leave",
        code=f"CL{uuid.uuid4().hex[:4].upper()}",
        annual_allocation=Decimal("12.0"),
        status=RecordStatus.ACTIVE,
    )
    db_session.add(record)
    await db_session.flush()
    return record


async def _leave(
    session: AsyncSession, employee: Employee, leave_type: LeaveType, *, days: int = 2
) -> LeaveRequest:
    request = LeaveRequest(
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        from_date=date(2026, 3, 2),
        to_date=date(2026, 3, 1 + days),
        days=Decimal(days),
        reason="Personal",
        status=ApprovalStatus.PENDING.value,
    )
    session.add(request)
    await session.flush()
    return request


async def _timesheet(session: AsyncSession, employee: Employee, *, status: str = "submitted") -> Timesheet:
    week = date(2026, 3, 2)
    sheet = Timesheet(
        employee_id=employee.id,
        week_start_date=week - timedelta(days=week.weekday()),
        status=status,
    )
    session.add(sheet)
    await session.flush()
    return sheet


async def _regularization(session: AsyncSession, employee: Employee) -> AttendanceRegularization:
    request = AttendanceRegularization(
        employee_id=employee.id,
        attendance_date=date(2026, 3, 3),
        reason="Forgot to check in",
        status=ApprovalStatus.PENDING.value,
    )
    session.add(request)
    await session.flush()
    return request


async def _document(session: AsyncSession, employee: Employee) -> Document:
    suffix = uuid.uuid4().hex[:4].upper()
    category = DocumentCategory(name=f"Personal {suffix}", code=f"PER{suffix}", status=RecordStatus.ACTIVE)
    session.add(category)
    await session.flush()

    document_type = DocumentType(
        name=f"Aadhaar {suffix}", code=f"AAD{suffix}", category_id=category.id, status=RecordStatus.ACTIVE
    )
    session.add(document_type)
    await session.flush()

    document = Document(
        name="Aadhaar card",
        category_id=category.id,
        document_type_id=document_type.id,
        owner_type=DocumentOwnerType.EMPLOYEE.value,
        owner_id=employee.id,
        status=DocumentStatus.UPLOADED,
    )
    session.add(document)
    await session.flush()
    return document


def _member_ids(payload: dict) -> set[str]:
    return {str(item["id"]) for item in payload["data"]["items"]}


def _row_employee_ids(payload: dict) -> set[str]:
    return {str(item["employee"]["id"]) for item in payload["data"]["items"]}


# ----------------------------------------------------------------------
class TestScopeResolution:
    """The rule itself, before any endpoint applies it."""

    @staticmethod
    async def _scope(session: AsyncSession, user: User) -> EmployeeScope:
        return await TeamScopeService(session, AuthorizationService(session)).direct_reports_of(user)

    async def test_a_manager_scope_is_their_reports_and_not_themselves(
        self, db_session: AsyncSession, org: Org
    ) -> None:
        scope = await self._scope(db_session, org.manager_a_user)

        assert scope.employee_ids == {org.report_a1.id, org.report_a2.id}
        assert not scope.allows(org.manager_a.id), "a manager is not a member of their own team scope"
        assert not scope.allows(org.report_b1.id)

    async def test_view_all_does_not_widen_a_team_scope(self, db_session: AsyncSession, org: Org) -> None:
        """The property that keeps "my team" from meaning "everybody" for HR."""
        hr_user = await _account(db_session, "hr_admin", "hr")
        hr = await _employee(db_session, "hr_person", user=hr_user)
        hr_report = await _employee(db_session, "hr_report", manager=hr)

        ordinary = await TeamScopeService(db_session, AuthorizationService(db_session)).for_user(hr_user)
        assert ordinary.unrestricted, "HR keeps its organization-wide scope everywhere else"

        team = await self._scope(db_session, hr_user)
        assert not team.unrestricted
        assert team.employee_ids == {hr_report.id}
        assert not team.allows(org.report_b1.id)

    async def test_a_superuser_team_scope_is_still_their_reports(
        self, db_session: AsyncSession, org: Org
    ) -> None:
        root = await _account(db_session, None, "root")
        root.is_superuser = True
        await db_session.flush()

        scope = await self._scope(db_session, root)
        assert scope.employee_ids == frozenset()
        assert scope.visible_employee_ids == frozenset(), "nobody, not everybody"

    async def test_an_account_with_no_employee_record_manages_nobody(
        self, db_session: AsyncSession, org: Org
    ) -> None:
        orphan = await _account(db_session, "manager", "orphan")
        scope = await self._scope(db_session, orphan)

        assert scope.employee_ids == frozenset()
        assert not scope.allows(org.report_a1.id)

    async def test_an_archived_report_leaves_the_team(self, db_session: AsyncSession, org: Org) -> None:
        from app.utils.datetime import utc_now

        org.report_a1.deleted_at = utc_now()
        await db_session.flush()

        scope = await self._scope(db_session, org.manager_a_user)
        assert scope.employee_ids == {org.report_a2.id}

    async def test_a_skip_level_report_is_not_on_the_team(self, db_session: AsyncSession, org: Org) -> None:
        """Direct reports, one hop. A report's own reports are theirs to manage."""
        skip = await _employee(db_session, "skip", manager=org.report_a1)

        scope = await self._scope(db_session, org.manager_a_user)
        assert not scope.allows(skip.id)


# ----------------------------------------------------------------------
class TestDashboard:
    async def test_a_manager_opens_their_own_dashboard(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        response = await client.get(f"{MANAGER}/dashboard", headers=headers_a)
        assert response.status_code == 200, response.text

        data = response.json()["data"]
        assert data["manager"]["id"] == str(org.manager_a.id)
        assert data["team_size"] == 2, "the two direct reports, and not the manager themselves"

    async def test_the_figures_count_only_the_team(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Org,
        leave_type: LeaveType,
        headers_a: dict[str, str],
    ) -> None:
        await _leave(db_session, org.report_a1, leave_type)
        await _leave(db_session, org.report_b1, leave_type)
        await _timesheet(db_session, org.report_b1)
        await _regularization(db_session, org.report_b1)

        response = await client.get(f"{MANAGER}/dashboard", headers=headers_a)
        assert response.status_code == 200, response.text

        data = response.json()["data"]
        assert data["pending_leave_approvals"] == 1, "manager B's team must not be counted"
        assert data["pending_timesheet_approvals"] == 0
        assert data["pending_regularizations"] == 0
        assert _row_employee_ids({"data": {"items": data["leave_awaiting_decision"]}}) == {
            str(org.report_a1.id)
        }

    async def test_a_managers_own_pending_leave_is_not_their_queue(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Org,
        leave_type: LeaveType,
        headers_a: dict[str, str],
    ) -> None:
        """It is waiting on *their* manager, and listing it invites them to decide it."""
        await _leave(db_session, org.manager_a, leave_type)

        response = await client.get(f"{MANAGER}/dashboard", headers=headers_a)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["pending_leave_approvals"] == 0

    async def test_an_employee_role_cannot_open_a_manager_dashboard(
        self, client: AsyncClient, db_session: AsyncSession, org: Org
    ) -> None:
        """Having reports is not the same as being entitled to a manager screen."""
        user = await _account(db_session, "employee", "plain")
        employee = await _employee(db_session, "plain_person", user=user)
        await _employee(db_session, "their_report", manager=employee)

        headers = await _sign_in(client, user)
        response = await client.get(f"{MANAGER}/dashboard", headers=headers)
        assert response.status_code == 403, response.text
        assert response.json()["errors"][0]["message"] == "employees:view"

    async def test_an_account_with_no_employee_record_is_told_why(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _account(db_session, "manager", "integration")
        headers = await _sign_in(client, user)

        response = await client.get(f"{MANAGER}/dashboard", headers=headers)
        assert response.status_code == 403, response.text
        assert response.json()["errors"][0]["code"] == "no_employee_record"

    async def test_an_unauthenticated_caller_gets_401(self, client: AsyncClient) -> None:
        assert (await client.get(f"{MANAGER}/dashboard")).status_code == 401


# ----------------------------------------------------------------------
class TestMyTeam:
    async def test_a_manager_sees_their_direct_reports(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        response = await client.get(f"{MANAGER}/team", headers=headers_a, params={"page_size": 100})
        assert response.status_code == 200, response.text
        assert _member_ids(response.json()) == {str(org.report_a1.id), str(org.report_a2.id)}

    async def test_a_manager_does_not_see_another_managers_employees(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        response = await client.get(f"{MANAGER}/team", headers=headers_a, params={"page_size": 100})
        assert str(org.report_b1.id) not in _member_ids(response.json())

    async def test_each_manager_sees_only_their_own_team(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str], headers_b: dict[str, str]
    ) -> None:
        """The same request, twice, with two different answers."""
        a = await client.get(f"{MANAGER}/team", headers=headers_a, params={"page_size": 100})
        b = await client.get(f"{MANAGER}/team", headers=headers_b, params={"page_size": 100})

        assert _member_ids(a.json()) & _member_ids(b.json()) == set()
        assert _member_ids(b.json()) == {str(org.report_b1.id)}

    async def test_searching_for_somebody_outside_the_team_finds_nothing(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        """No result rather than a leak: the search runs inside the scope."""
        response = await client.get(
            f"{MANAGER}/team",
            headers=headers_a,
            params={"search": org.report_b1.official_email, "page_size": 100},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["items"] == []

    async def test_the_roster_carries_no_salary_or_identifiers(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        response = await client.get(f"{MANAGER}/team", headers=headers_a, params={"page_size": 100})
        row = response.json()["data"]["items"][0]

        for forbidden in ("ctc", "bank_detail", "identification", "addresses", "notes"):
            assert forbidden not in row, f"{forbidden} has no business on a team roster"

    async def test_a_manager_reads_their_own_reports_profile(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        response = await client.get(f"{MANAGER}/team/{org.report_a1.id}", headers=headers_a)
        assert response.status_code == 200, response.text

        data = response.json()["data"]
        assert data["member"]["id"] == str(org.report_a1.id)
        assert "attendance" in data and "leave" in data and "timesheets" in data

    async def test_a_manager_cannot_read_another_managers_report(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        response = await client.get(f"{MANAGER}/team/{org.report_b1.id}", headers=headers_a)
        assert response.status_code == 403, response.text
        assert response.json()["errors"][0]["code"] == "outside_your_team"

    async def test_a_manager_cannot_read_their_own_profile_here(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        """Their own record is the employee portal's job, not the team screen's."""
        response = await client.get(f"{MANAGER}/team/{org.manager_a.id}", headers=headers_a)
        assert response.status_code == 403, response.text

    async def test_an_unknown_id_is_refused_the_same_way(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        """So a 403 never confirms that somebody exists."""
        response = await client.get(f"{MANAGER}/team/{uuid.uuid4()}", headers=headers_a)
        assert response.status_code == 403, response.text
        assert response.json()["errors"][0]["code"] == "outside_your_team"


# ----------------------------------------------------------------------
class TestTeamAttendance:
    async def test_the_register_is_narrowed_to_the_team(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        for employee in (org.manager_a, org.report_a1, org.report_b1):
            db_session.add(AttendanceRecord(employee_id=employee.id, attendance_date=date(2026, 3, 4)))
        await db_session.flush()

        response = await client.get(f"{MANAGER}/attendance", headers=headers_a, params={"page_size": 100})
        assert response.status_code == 200, response.text
        assert _row_employee_ids(response.json()) == {str(org.report_a1.id)}

    async def test_a_manager_cannot_filter_to_another_teams_employee(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        response = await client.get(
            f"{MANAGER}/attendance", headers=headers_a, params={"employee_id": str(org.report_b1.id)}
        )
        assert response.status_code == 403, response.text
        assert response.json()["errors"][0]["code"] == "outside_your_team"

    async def test_a_manager_may_filter_to_their_own_report(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        response = await client.get(
            f"{MANAGER}/attendance", headers=headers_a, params={"employee_id": str(org.report_a1.id)}
        )
        assert response.status_code == 200, response.text

    async def test_there_is_no_endpoint_that_edits_attendance(self) -> None:
        """§4: a manager corrects a day by approving a request, not by editing it."""
        from app.api.v1.routes.manager import router

        writes = {
            route.path  # type: ignore[attr-defined]
            for route in router.routes
            if getattr(route, "methods", set()) & {"POST", "PATCH", "PUT", "DELETE"}
        }
        assert writes == {
            "/manager/attendance/regularizations/{request_id}/decide",
            "/manager/leave/{request_id}/decide",
            "/manager/timesheets/{timesheet_id}/decide",
        }, "the manager module writes decisions and nothing else"


# ----------------------------------------------------------------------
class TestRegularizations:
    async def test_only_the_teams_requests_are_listed(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        await _regularization(db_session, org.report_a1)
        await _regularization(db_session, org.report_b1)

        response = await client.get(f"{MANAGER}/attendance/regularizations", headers=headers_a)
        assert response.status_code == 200, response.text
        assert _row_employee_ids(response.json()) == {str(org.report_a1.id)}

    async def test_a_manager_approves_their_own_teams_correction(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        request = await _regularization(db_session, org.report_a1)

        response = await client.post(
            f"{MANAGER}/attendance/regularizations/{request.id}/decide",
            headers=headers_a,
            json={"approved": True, "notes": "Confirmed with the team"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == ApprovalStatus.APPROVED.value

    async def test_a_manager_cannot_decide_another_teams_correction(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        request = await _regularization(db_session, org.report_b1)

        response = await client.post(
            f"{MANAGER}/attendance/regularizations/{request.id}/decide",
            headers=headers_a,
            json={"approved": True},
        )
        assert response.status_code == 403, response.text

        await db_session.refresh(request)
        assert request.status == ApprovalStatus.PENDING.value, "the refusal must not have decided it"

    async def test_a_manager_cannot_decide_their_own_correction(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        request = await _regularization(db_session, org.manager_a)

        response = await client.post(
            f"{MANAGER}/attendance/regularizations/{request.id}/decide",
            headers=headers_a,
            json={"approved": True},
        )
        assert response.status_code == 403, response.text
        assert response.json()["errors"][0]["code"] == "own_request"


# ----------------------------------------------------------------------
class TestTeamLeave:
    async def test_only_the_teams_leave_is_listed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Org,
        leave_type: LeaveType,
        headers_a: dict[str, str],
    ) -> None:
        await _leave(db_session, org.report_a1, leave_type)
        await _leave(db_session, org.report_b1, leave_type)

        response = await client.get(f"{MANAGER}/leave", headers=headers_a, params={"page_size": 100})
        assert response.status_code == 200, response.text
        assert _row_employee_ids(response.json()) == {str(org.report_a1.id)}

    async def test_a_manager_approves_their_own_teams_leave(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Org,
        leave_type: LeaveType,
        headers_a: dict[str, str],
    ) -> None:
        request = await _leave(db_session, org.report_a1, leave_type)

        response = await client.post(
            f"{MANAGER}/leave/{request.id}/decide",
            headers=headers_a,
            json={"approved": True, "notes": "Enjoy"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == ApprovalStatus.APPROVED.value

    async def test_a_manager_cannot_approve_another_managers_employees_leave(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Org,
        leave_type: LeaveType,
        headers_a: dict[str, str],
    ) -> None:
        """The decision is keyed by request id, so the check has to survive the
        caller never naming an employee at all."""
        request = await _leave(db_session, org.report_b1, leave_type)

        response = await client.post(
            f"{MANAGER}/leave/{request.id}/decide", headers=headers_a, json={"approved": True}
        )
        assert response.status_code == 403, response.text

        await db_session.refresh(request)
        assert request.status == ApprovalStatus.PENDING.value

    async def test_a_manager_cannot_approve_their_own_leave(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Org,
        leave_type: LeaveType,
        headers_a: dict[str, str],
    ) -> None:
        request = await _leave(db_session, org.manager_a, leave_type)

        response = await client.post(
            f"{MANAGER}/leave/{request.id}/decide", headers=headers_a, json={"approved": True}
        )
        assert response.status_code == 403, response.text
        assert response.json()["errors"][0]["code"] == "own_request"

        await db_session.refresh(request)
        assert request.status == ApprovalStatus.PENDING.value

    async def test_rejecting_records_the_comment(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Org,
        leave_type: LeaveType,
        headers_a: dict[str, str],
    ) -> None:
        request = await _leave(db_session, org.report_a1, leave_type)

        response = await client.post(
            f"{MANAGER}/leave/{request.id}/decide",
            headers=headers_a,
            json={"approved": False, "notes": "Release week; please move it"},
        )
        assert response.status_code == 200, response.text

        data = response.json()["data"]
        assert data["status"] == ApprovalStatus.REJECTED.value
        assert data["decision_notes"] == "Release week; please move it"


# ----------------------------------------------------------------------
class TestTeamTimesheets:
    async def test_only_the_teams_timesheets_are_listed(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        await _timesheet(db_session, org.report_a1)
        await _timesheet(db_session, org.report_b1)

        response = await client.get(f"{MANAGER}/timesheets", headers=headers_a, params={"page_size": 100})
        assert response.status_code == 200, response.text
        assert _row_employee_ids(response.json()) == {str(org.report_a1.id)}

    async def test_a_manager_cannot_open_another_teams_timesheet(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        sheet = await _timesheet(db_session, org.report_b1)

        response = await client.get(f"{MANAGER}/timesheets/{sheet.id}", headers=headers_a)
        assert response.status_code == 403, response.text

    async def test_a_manager_approves_their_own_teams_timesheet(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        sheet = await _timesheet(db_session, org.report_a1)

        response = await client.post(
            f"{MANAGER}/timesheets/{sheet.id}/decide", headers=headers_a, json={"approved": True}
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "approved"

    async def test_a_manager_cannot_decide_another_teams_timesheet(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        sheet = await _timesheet(db_session, org.report_b1)

        response = await client.post(
            f"{MANAGER}/timesheets/{sheet.id}/decide", headers=headers_a, json={"approved": True}
        )
        assert response.status_code == 403, response.text

        await db_session.refresh(sheet)
        assert sheet.status == "submitted"

    async def test_returning_a_week_for_correction_is_a_rejection_with_notes(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        sheet = await _timesheet(db_session, org.report_a1)

        response = await client.post(
            f"{MANAGER}/timesheets/{sheet.id}/decide",
            headers=headers_a,
            json={"approved": False, "notes": "Thursday is booked to the wrong project"},
        )
        assert response.status_code == 200, response.text

        data = response.json()["data"]
        assert data["status"] == "rejected"
        assert data["decision_notes"] == "Thursday is booked to the wrong project"

    async def test_a_manager_cannot_decide_their_own_timesheet(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        sheet = await _timesheet(db_session, org.manager_a)

        response = await client.post(
            f"{MANAGER}/timesheets/{sheet.id}/decide", headers=headers_a, json={"approved": True}
        )
        assert response.status_code == 403, response.text
        assert response.json()["errors"][0]["code"] == "own_request"


# ----------------------------------------------------------------------
class TestProjectsAndPerformance:
    async def test_the_project_list_covers_only_the_team(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        response = await client.get(f"{MANAGER}/projects", headers=headers_a)
        assert response.status_code == 200, response.text
        assert response.json()["data"] == [], "nobody on this team is allocated"

    async def test_a_manager_views_their_teams_performance(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        response = await client.get(f"{MANAGER}/performance", headers=headers_a)
        assert response.status_code == 200, response.text

        rows = response.json()["data"]
        assert {row["employee"]["id"] for row in rows} == {
            str(org.report_a1.id),
            str(org.report_a2.id),
        }, "every team member appears, with or without a cycle"

    async def test_performance_does_not_reach_another_team(
        self, client: AsyncClient, org: Org, headers_b: dict[str, str]
    ) -> None:
        response = await client.get(f"{MANAGER}/performance", headers=headers_b)
        assert {row["employee"]["id"] for row in response.json()["data"]} == {str(org.report_b1.id)}

    async def test_a_team_lead_reaches_the_approval_screens(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """The two gates are independent: same scope rule, different grants.

        A Team Lead approves for their team but holds no document permission, so
        they get everything here except the completion figures -- which is
        asserted separately, as a refusal.
        """
        user = await _account(db_session, "team_lead", "lead")
        lead = await _employee(db_session, "lead_person", user=user)
        await _employee(db_session, "lead_report", manager=lead)
        headers = await _sign_in(client, user)

        for path in (
            "/dashboard",
            "/team",
            "/attendance",
            "/leave",
            "/timesheets",
            "/performance",
            "/projects",
        ):
            response = await client.get(f"{MANAGER}{path}", headers=headers)
            assert response.status_code == 200, f"{path}: {response.text}"


# ----------------------------------------------------------------------
class TestTeamCalendar:
    async def test_the_calendar_carries_only_the_teams_leave(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Org,
        leave_type: LeaveType,
        headers_a: dict[str, str],
    ) -> None:
        mine = await _leave(db_session, org.report_a1, leave_type)
        theirs = await _leave(db_session, org.report_b1, leave_type)
        for request in (mine, theirs):
            request.status = ApprovalStatus.APPROVED.value
        await db_session.flush()

        response = await client.get(
            f"{MANAGER}/calendar", headers=headers_a, params={"year": 2026, "month": 3}
        )
        assert response.status_code == 200, response.text

        entries = response.json()["data"]["entries"]
        owners = {entry["employee_id"] for entry in entries if entry["employee_id"]}
        assert owners == {str(org.report_a1.id)}

    async def test_attendance_exceptions_appear(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        db_session.add(
            AttendanceRecord(employee_id=org.report_a1.id, attendance_date=date(2026, 3, 5), status="absent")
        )
        await db_session.flush()

        response = await client.get(
            f"{MANAGER}/calendar", headers=headers_a, params={"year": 2026, "month": 3}
        )
        kinds = {entry["kind"] for entry in response.json()["data"]["entries"]}
        assert "exception" in kinds


# ----------------------------------------------------------------------
class TestDocumentStatus:
    async def test_a_manager_sees_counts_and_never_a_document(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        await _document(db_session, org.report_a1)

        response = await client.get(f"{MANAGER}/documents", headers=headers_a)
        assert response.status_code == 200, response.text

        rows = {row["employee"]["id"]: row for row in response.json()["data"]}
        assert rows[str(org.report_a1.id)]["total"] == 1
        assert rows[str(org.report_a1.id)]["pending"] == 1
        assert set(rows[str(org.report_a1.id)]) == {
            "employee",
            "total",
            "approved",
            "pending",
            "rejected",
        }, "a count, and nothing that names the document"

    async def test_another_teams_documents_are_not_counted(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        await _document(db_session, org.report_b1)

        response = await client.get(f"{MANAGER}/documents", headers=headers_a)
        assert all(row["total"] == 0 for row in response.json()["data"])

    async def test_a_manager_still_cannot_open_the_document_itself(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        """Counts are not a key to the vault. The file stays behind its own scope."""
        stranger_document = await _document(db_session, org.report_b1)

        response = await client.get(f"{API}/documents/{stranger_document.id}", headers=headers_a)
        assert response.status_code == 403, response.text

    async def test_a_seat_without_documents_view_gets_no_completion_figures(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """§12: only if permitted. The Team Lead role does not hold ``documents:view``."""
        user = await _account(db_session, "team_lead", "lead_docs")
        lead = await _employee(db_session, "lead_docs_person", user=user)
        await _employee(db_session, "lead_docs_report", manager=lead)
        headers = await _sign_in(client, user)

        response = await client.get(f"{MANAGER}/documents", headers=headers)
        assert response.status_code == 403, response.text
        assert response.json()["errors"][0]["message"] == "documents:view"


# ----------------------------------------------------------------------
class TestHrAndSuperuserAreUnaffected:
    async def test_hr_keeps_organization_wide_employee_access(
        self, client: AsyncClient, db_session: AsyncSession, org: Org
    ) -> None:
        hr = await _account(db_session, "hr_admin", "hr")
        headers = await _sign_in(client, hr)

        directory = await client.get(EMPLOYEES, headers=headers, params={"page_size": 100})
        assert directory.status_code == 200, directory.text

        listed = {str(item["id"]) for item in directory.json()["data"]["items"]}
        assert {str(org.report_a1.id), str(org.report_b1.id)} <= listed

        assert (await client.get(f"{EMPLOYEES}/{org.report_b1.id}", headers=headers)).status_code == 200

    async def test_hr_keeps_organization_wide_workforce_access(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, leave_type: LeaveType
    ) -> None:
        hr = await _account(db_session, "hr_admin", "hr")
        headers = await _sign_in(client, hr)
        request = await _leave(db_session, org.report_b1, leave_type)

        listing = await client.get(f"{WORKFORCE}/leave", headers=headers, params={"page_size": 100})
        assert str(org.report_b1.id) in {item["employee_id"] for item in listing.json()["data"]["items"]}

        decided = await client.post(
            f"{WORKFORCE}/leave/{request.id}/decide", headers=headers, json={"approved": True}
        )
        assert decided.status_code == 200, decided.text

    async def test_hrs_own_manager_screen_is_their_own_reporting_line(
        self, client: AsyncClient, db_session: AsyncSession, org: Org
    ) -> None:
        """Not a restriction on HR: their org-wide screens are untouched above.

        A team screen that showed HR the whole company would make "my team"
        mean two different things depending on who is looking at it.
        """
        hr_user = await _account(db_session, "hr_admin", "hr")
        hr = await _employee(db_session, "hr_person", user=hr_user)
        hr_report = await _employee(db_session, "hr_report", manager=hr)
        headers = await _sign_in(client, hr_user)

        response = await client.get(f"{MANAGER}/team", headers=headers, params={"page_size": 100})
        assert response.status_code == 200, response.text
        assert _member_ids(response.json()) == {str(hr_report.id)}

    async def test_a_superuser_keeps_full_access_elsewhere(
        self, client: AsyncClient, org: Org, auth_headers: dict[str, str]
    ) -> None:
        assert (await client.get(EMPLOYEES, headers=auth_headers)).status_code == 200
        assert (await client.get(f"{EMPLOYEES}/{org.report_b1.id}", headers=auth_headers)).status_code == 200
        assert (
            await client.get(f"{WORKFORCE}/leave/balances/{org.report_b1.id}", headers=auth_headers)
        ).status_code == 200

    async def test_a_superuser_team_screen_shows_their_own_reports(
        self, client: AsyncClient, org: Org, auth_headers: dict[str, str]
    ) -> None:
        """The bootstrap account manages nobody, so its team screen is empty."""
        response = await client.get(f"{MANAGER}/team", headers=auth_headers, params={"page_size": 100})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["items"] == []


# ----------------------------------------------------------------------
class TestExistingProtectionsAreIntact:
    """The manager layer is additive. Nothing below it may have loosened."""

    async def test_employee_self_service_still_works(
        self, client: AsyncClient, db_session: AsyncSession, org: Org
    ) -> None:
        user = await _account(db_session, "employee", "ess")
        employee = await _employee(db_session, "ess_person", user=user, manager=org.manager_a)
        headers = await _sign_in(client, user)

        me = await client.get(f"{API}/me", headers=headers)
        assert me.status_code == 200, me.text
        assert me.json()["data"]["id"] == str(employee.id)

        dashboard = await client.get(f"{API}/me/dashboard", headers=headers)
        assert dashboard.status_code == 200, dashboard.text

    async def test_an_employee_with_reports_still_reaches_no_manager_screen(
        self, client: AsyncClient, db_session: AsyncSession, org: Org
    ) -> None:
        """The widening the guards were chosen to prevent.

        The base Employee role holds ``attendance:view``, ``leave:view``,
        ``timesheets:view``, ``performance:view`` and ``documents:view`` -- it
        must, or nobody could see their own records. Guarding a team screen with
        any of those would mean that acquiring a direct report silently granted
        access to that person's attendance. Every screen is therefore guarded on
        the permission that means "you act on other people's records".
        """
        user = await _account(db_session, "employee", "ess_denied")
        employee = await _employee(db_session, "ess_denied_person", user=user, manager=org.manager_a)
        report = await _employee(db_session, "ess_denied_report", manager=employee)
        headers = await _sign_in(client, user)

        for path in (
            "/dashboard",
            "/team",
            f"/team/{report.id}",
            "/attendance",
            "/attendance/regularizations",
            "/leave",
            "/timesheets",
            "/projects",
            "/performance",
            "/documents",
            "/calendar?year=2026&month=3",
        ):
            response = await client.get(f"{MANAGER}{path}", headers=headers)
            assert response.status_code == 403, f"{path}: {response.text}"

    async def test_a_managers_own_me_endpoints_are_still_about_them(
        self, client: AsyncClient, db_session: AsyncSession, org: Org, headers_a: dict[str, str]
    ) -> None:
        """``/me`` is the manager, not the manager's team. The two scopes are separate."""
        db_session.add(AttendanceRecord(employee_id=org.report_a1.id, attendance_date=date(2026, 3, 4)))
        db_session.add(AttendanceRecord(employee_id=org.manager_a.id, attendance_date=date(2026, 3, 4)))
        await db_session.flush()

        response = await client.get(f"{API}/me/attendance", headers=headers_a, params={"page_size": 100})
        assert response.status_code == 200, response.text
        assert {item["employee_id"] for item in response.json()["data"]["items"]} == {str(org.manager_a.id)}

    async def test_the_employee_module_idor_guard_still_refuses(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        for path in (
            f"{EMPLOYEES}/{org.report_b1.id}",
            f"{WORKFORCE}/leave/balances/{org.report_b1.id}",
            f"{WORKFORCE}/calendar/{org.report_b1.id}?year=2026&month=3",
        ):
            response = await client.get(path, headers=headers_a)
            assert response.status_code == 403, f"{path}: {response.text}"

    async def test_a_manager_still_reads_their_own_report_through_the_employee_module(
        self, client: AsyncClient, org: Org, headers_a: dict[str, str]
    ) -> None:
        """The manager layer narrows; it must not have narrowed anything else."""
        response = await client.get(f"{EMPLOYEES}/{org.report_a1.id}", headers=headers_a)
        assert response.status_code == 200, response.text


# ----------------------------------------------------------------------
class TestNoManagerIdIsEverAccepted:
    """The structural half of the guarantee, alongside the refusals above."""

    def test_no_manager_route_takes_a_manager_or_user_id(self) -> None:
        from fastapi.routing import APIRoute

        from app.api.v1.routes.manager import router

        offenders: dict[str, list[str]] = {}
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            names = [
                field.name
                for field in (
                    route.dependant.path_params + route.dependant.query_params + route.dependant.body_params
                )
            ]
            named = [name for name in names if name in {"manager_id", "user_id", "reporting_manager_id"}]
            if named:
                offenders[route.path] = named

        assert not offenders, f"the team is derived from the session, never supplied: {offenders}"
