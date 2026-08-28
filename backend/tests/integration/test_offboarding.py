"""Integration tests for resignation and offboarding.

Most of what follows is refusals. A suite that only proved an employee could
resign and HR could process it would be satisfied by an implementation that let
anybody do either, so each capability is paired with the person who must *not*
have it -- and, where the difference is a permission rather than a role, with a
grant that makes the same call succeed.

Three propositions are under test:

**An employee acts only on themselves.** Not "is checked against themselves":
there is no field on any self-service request that names a person, so the
IDOR tests below assert both that the attempt fails *and* that the schema
refuses to carry the id in the first place.

**A manager reaches their own direct reports and stops.** Including the case
that is easy to miss -- their own resignation is outside the manager scope, so
they cannot approve it through the team screen.

**HR is not an administrator.** HR Admin processes a separation and does not
approve one; approving is the manager's decision about their own team.
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
from app.models.audit_log import AuditAction, AuditLog
from app.models.employee import Employee
from app.models.enums import EmploymentStatus, RecordStatus, ResignationStatus
from app.models.offboarding import OffboardingCase, Resignation
from app.models.project import Client, EmployeeAllocation, Project, ProjectMember
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.user import User
from app.schemas.offboarding import ExitInterviewSubmit, ResignationSubmit

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
ME = f"{API}/me"
MANAGER = f"{API}/manager"
OFFBOARDING = f"{API}/offboarding"

PASSWORD = "Str0ng!Passw0rd"
TODAY = date.today()
LAST_DAY = TODAY + timedelta(days=30)


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
        assert role is not None, f"migration 0015/0017/0018 should have seeded the {role_key} role"
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


async def _grant(session: AsyncSession, user: User, *permissions: str) -> None:
    """One account, one extra permission, through a role of its own."""
    role = Role(
        key=f"custom_{uuid.uuid4().hex[:8]}",
        name=f"Custom {uuid.uuid4().hex[:4]}",
        is_system=False,
        status=RecordStatus.ACTIVE,
    )
    session.add(role)
    await session.flush()
    for permission in permissions:
        permission_id = (
            await session.execute(select(Permission.id).where(Permission.code == permission))
        ).scalar_one()
        session.add(RolePermission(role_id=role.id, permission_id=permission_id))
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.flush()


async def _sign_in(client: AsyncClient, user: User) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['tokens']['access_token']}"}


class People:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)

    employee_user: User
    employee: Employee
    manager_user: User
    manager: Employee
    other_manager_user: User
    other_manager: Employee
    stranger_user: User
    stranger: Employee
    hr_user: User
    hr_exec_user: User
    admin_user: User


@pytest.fixture
async def people(db_session: AsyncSession) -> People:
    manager_user = await _account(db_session, "manager", "mgr")
    manager = await _employee(db_session, "manager", user=manager_user)

    employee_user = await _account(db_session, "employee", "emp")
    employee = await _employee(db_session, "employee", user=employee_user, manager=manager)

    other_manager_user = await _account(db_session, "manager", "mgr2")
    other_manager = await _employee(db_session, "other_manager", user=other_manager_user)

    stranger_user = await _account(db_session, "employee", "stranger")
    stranger = await _employee(db_session, "stranger", user=stranger_user, manager=other_manager)

    return People(
        employee_user=employee_user,
        employee=employee,
        manager_user=manager_user,
        manager=manager,
        other_manager_user=other_manager_user,
        other_manager=other_manager,
        stranger_user=stranger_user,
        stranger=stranger,
        hr_user=await _account(db_session, "hr_admin", "hr"),
        hr_exec_user=await _account(db_session, "hr_executive", "hrx"),
        admin_user=await _account(db_session, "admin", "adm"),
    )


async def _submit(client: AsyncClient, headers: dict[str, str], **overrides: object) -> dict:
    body = {
        "resignation_date": TODAY.isoformat(),
        "proposed_last_working_day": LAST_DAY.isoformat(),
        "reason": "Career change",
        "comments": "Thank you for everything.",
    }
    body.update(overrides)  # type: ignore[arg-type]
    response = await client.post(f"{ME}/resignation", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _through_to_case(client: AsyncClient, people: People) -> tuple[dict, dict[str, str]]:
    """Employee resigns -> manager approves -> HR processes. Returns the case."""
    employee_headers = await _sign_in(client, people.employee_user)
    resignation = await _submit(client, employee_headers)

    manager_headers = await _sign_in(client, people.manager_user)
    decision = await client.post(
        f"{MANAGER}/resignations/{resignation['id']}/decision",
        json={"decision": "approve", "comments": "Sorry to see you go."},
        headers=manager_headers,
    )
    assert decision.status_code == 200, decision.text

    hr_headers = await _sign_in(client, people.hr_user)
    processed = await client.post(
        f"{OFFBOARDING}/resignations/{resignation['id']}/process",
        json={"approved_last_working_day": LAST_DAY.isoformat()},
        headers=hr_headers,
    )
    assert processed.status_code == 201, processed.text
    return processed.json()["data"], hr_headers


# ======================================================================
# 1-3. The employee acts on themselves and nobody else
# ======================================================================
class TestEmployeeResignation:
    async def test_an_employee_submits_their_own_resignation(
        self, client: AsyncClient, people: People
    ) -> None:
        headers = await _sign_in(client, people.employee_user)
        data = await _submit(client, headers)

        assert data["status"] == ResignationStatus.MANAGER_REVIEW.value
        assert data["resignation_code"].startswith("RES-")
        assert data["can_withdraw"] is True
        # §6: every notice figure is computed on the server.
        assert data["notice"]["notice_period_days"] >= 0
        assert data["notice"]["remaining_days"] >= 0

    async def test_the_submit_schema_cannot_carry_another_employees_id(self) -> None:
        """The IDOR that matters is the one that cannot be expressed.

        Asserted on the schema rather than over HTTP because that is where the
        property lives: there is no ``employee_id`` to validate, so no guard has
        to remember to check it.
        """
        assert "employee_id" not in ResignationSubmit.model_fields
        assert "employee_id" not in ExitInterviewSubmit.model_fields

    async def test_an_employee_cannot_resign_on_behalf_of_somebody_else(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, people.employee_user)
        response = await client.post(
            f"{ME}/resignation",
            json={
                "resignation_date": TODAY.isoformat(),
                "proposed_last_working_day": LAST_DAY.isoformat(),
                "reason": "Not mine to give",
                "employee_id": str(people.stranger.id),
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text

        # The extra field was ignored, and the row belongs to the caller.
        rows = (
            (
                await db_session.execute(
                    select(Resignation).where(Resignation.employee_id == people.stranger.id)
                )
            )
            .scalars()
            .all()
        )
        assert rows == []
        assert response.json()["data"]["id"] is not None

    async def test_an_employee_sees_only_their_own_resignation(
        self, client: AsyncClient, people: People
    ) -> None:
        employee_headers = await _sign_in(client, people.employee_user)
        await _submit(client, employee_headers)

        stranger_headers = await _sign_in(client, people.stranger_user)
        response = await client.get(f"{ME}/resignation", headers=stranger_headers)
        assert response.status_code == 200
        assert response.json()["data"] is None

    async def test_a_second_live_resignation_is_refused(self, client: AsyncClient, people: People) -> None:
        headers = await _sign_in(client, people.employee_user)
        await _submit(client, headers)
        again = await client.post(
            f"{ME}/resignation",
            json={
                "resignation_date": TODAY.isoformat(),
                "proposed_last_working_day": LAST_DAY.isoformat(),
                "reason": "Again",
            },
            headers=headers,
        )
        assert again.status_code == 409

    async def test_an_employee_withdraws_before_approval(self, client: AsyncClient, people: People) -> None:
        headers = await _sign_in(client, people.employee_user)
        await _submit(client, headers)
        response = await client.post(
            f"{ME}/resignation/withdraw", json={"comments": "Staying"}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == ResignationStatus.WITHDRAWN.value


# ======================================================================
# 4-6. Manager scoping
# ======================================================================
class TestManagerScope:
    async def test_a_manager_sees_their_direct_reports_resignations(
        self, client: AsyncClient, people: People
    ) -> None:
        employee_headers = await _sign_in(client, people.employee_user)
        await _submit(client, employee_headers)

        manager_headers = await _sign_in(client, people.manager_user)
        response = await client.get(f"{MANAGER}/resignations", headers=manager_headers)
        assert response.status_code == 200
        codes = {row["employee"]["id"] for row in response.json()["data"]["items"]}
        assert codes == {str(people.employee.id)}

    async def test_a_manager_cannot_reach_another_managers_team(
        self, client: AsyncClient, people: People
    ) -> None:
        stranger_headers = await _sign_in(client, people.stranger_user)
        resignation = await _submit(client, stranger_headers)

        manager_headers = await _sign_in(client, people.manager_user)
        listed = await client.get(f"{MANAGER}/resignations", headers=manager_headers)
        assert listed.json()["data"]["items"] == []

        decision = await client.post(
            f"{MANAGER}/resignations/{resignation['id']}/decision",
            json={"decision": "approve"},
            headers=manager_headers,
        )
        assert decision.status_code == 403

    async def test_a_manager_approves_their_own_teams_resignation(
        self, client: AsyncClient, people: People
    ) -> None:
        employee_headers = await _sign_in(client, people.employee_user)
        resignation = await _submit(client, employee_headers)

        manager_headers = await _sign_in(client, people.manager_user)
        response = await client.post(
            f"{MANAGER}/resignations/{resignation['id']}/decision",
            json={
                "decision": "approve",
                "comments": "Approved",
                "recommended_last_working_day": LAST_DAY.isoformat(),
            },
            headers=manager_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == ResignationStatus.HR_REVIEW.value

    async def test_a_manager_cannot_approve_their_own_resignation(
        self, client: AsyncClient, people: People
    ) -> None:
        """The manager scope excludes the caller, so this is refused by the
        check that was already there rather than by a special case."""
        manager_headers = await _sign_in(client, people.manager_user)
        resignation = await _submit(client, manager_headers)

        response = await client.post(
            f"{MANAGER}/resignations/{resignation['id']}/decision",
            json={"decision": "approve"},
            headers=manager_headers,
        )
        assert response.status_code == 403

    async def test_an_employee_cannot_use_the_manager_screens(
        self, client: AsyncClient, people: People
    ) -> None:
        headers = await _sign_in(client, people.employee_user)
        assert (await client.get(f"{MANAGER}/resignations", headers=headers)).status_code == 403


# ======================================================================
# 7-10. HR, Admin and Super Admin
# ======================================================================
class TestPermissionBoundaries:
    async def test_hr_processes_a_resignation_and_opens_the_case(
        self, client: AsyncClient, people: People
    ) -> None:
        case, _ = await _through_to_case(client, people)
        assert case["case_code"].startswith("OFF-")
        assert case["status"] == "in_progress"
        # §8: the default checklist covers all five departments.
        assert {task["department"] for task in case["tasks"]} == {
            "hr",
            "manager",
            "it",
            "admin",
            "finance",
        }
        assert case["assets"], "asset clearance rows are seeded"
        assert case["access_items"], "access clearance rows are seeded"
        assert case["settlement"]["status"] == "not_started"

    async def test_hr_admin_cannot_approve_a_resignation(self, client: AsyncClient, people: People) -> None:
        """Approving is the manager's decision about their own team.

        The clearest statement of "HR is not an administrator" in this module:
        HR Admin holds every resignation action except this one.
        """
        assert "resignation:approve" not in SYSTEM_ROLES_BY_KEY["hr_admin"].permissions
        assert "resignation:process" in SYSTEM_ROLES_BY_KEY["hr_admin"].permissions

        employee_headers = await _sign_in(client, people.employee_user)
        resignation = await _submit(client, employee_headers)

        hr_headers = await _sign_in(client, people.hr_user)
        response = await client.post(
            f"{MANAGER}/resignations/{resignation['id']}/decision",
            json={"decision": "approve"},
            headers=hr_headers,
        )
        assert response.status_code == 403

    async def test_an_hr_executive_cannot_process_or_manage(
        self, client: AsyncClient, people: People
    ) -> None:
        employee_headers = await _sign_in(client, people.employee_user)
        resignation = await _submit(client, employee_headers)

        headers = await _sign_in(client, people.hr_exec_user)
        assert (await client.get(f"{OFFBOARDING}/resignations", headers=headers)).status_code == 200
        process = await client.post(
            f"{OFFBOARDING}/resignations/{resignation['id']}/process", json={}, headers=headers
        )
        assert process.status_code == 403

    async def test_a_permission_grant_is_what_changes_the_answer(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        """Nothing checks a role name: the same account is let through once the
        permission is granted."""
        employee_headers = await _sign_in(client, people.employee_user)
        resignation = await _submit(client, employee_headers)
        manager_headers = await _sign_in(client, people.manager_user)
        await client.post(
            f"{MANAGER}/resignations/{resignation['id']}/decision",
            json={"decision": "approve"},
            headers=manager_headers,
        )

        await _grant(db_session, people.hr_exec_user, "resignation:process")
        headers = await _sign_in(client, people.hr_exec_user)
        response = await client.post(
            f"{OFFBOARDING}/resignations/{resignation['id']}/process", json={}, headers=headers
        )
        assert response.status_code == 201, response.text

    async def test_an_admin_reaches_every_offboarding_function(
        self, client: AsyncClient, people: People
    ) -> None:
        case, _ = await _through_to_case(client, people)
        headers = await _sign_in(client, people.admin_user)

        assert (await client.get(f"{OFFBOARDING}/cases", headers=headers)).status_code == 200
        assert (await client.get(f"{OFFBOARDING}/cases/{case['id']}", headers=headers)).status_code == 200
        settlement = await client.put(
            f"{OFFBOARDING}/cases/{case['id']}/settlement",
            json={"status": "in_progress", "settlement_reference": "FNF-1"},
            headers=headers,
        )
        assert settlement.status_code == 200
        document = await client.post(
            f"{OFFBOARDING}/cases/{case['id']}/documents",
            json={"document_type": "experience_letter", "release": True},
            headers=headers,
        )
        assert document.status_code == 201, document.text

    async def test_a_superuser_is_unrestricted(
        self, client: AsyncClient, people: People, auth_headers: dict[str, str]
    ) -> None:
        case, _ = await _through_to_case(client, people)
        assert (await client.get(f"{OFFBOARDING}/summary", headers=auth_headers)).status_code == 200
        assert (
            await client.get(f"{OFFBOARDING}/cases/{case['id']}", headers=auth_headers)
        ).status_code == 200
        assert (await client.get(f"{OFFBOARDING}/exit-interviews", headers=auth_headers)).status_code == 200

    async def test_an_anonymous_caller_gets_401_not_403(self, client: AsyncClient) -> None:
        assert (await client.get(f"{OFFBOARDING}/resignations")).status_code == 401


# ======================================================================
# 11-14. Exit interview and exit documents
# ======================================================================
class TestExitInterviewAndDocuments:
    async def test_an_employee_submits_their_own_exit_interview(
        self, client: AsyncClient, people: People
    ) -> None:
        await _through_to_case(client, people)
        headers = await _sign_in(client, people.employee_user)

        response = await client.post(
            f"{ME}/exit-interview",
            json={
                "reason_for_leaving": "Career change",
                "overall_experience": 4,
                "management_rating": 5,
                "would_recommend": True,
                "would_rejoin": True,
                "suggestions": "More documentation.",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["data"]["submitted_at"] is not None

    async def test_an_exit_interview_is_submitted_once(self, client: AsyncClient, people: People) -> None:
        await _through_to_case(client, people)
        headers = await _sign_in(client, people.employee_user)
        body = {"reason_for_leaving": "Career change", "overall_experience": 4}
        assert (await client.post(f"{ME}/exit-interview", json=body, headers=headers)).status_code == 201
        assert (await client.post(f"{ME}/exit-interview", json=body, headers=headers)).status_code == 409

    async def test_an_employee_cannot_see_another_employees_exit_interview(
        self, client: AsyncClient, people: People
    ) -> None:
        case, _ = await _through_to_case(client, people)
        employee_headers = await _sign_in(client, people.employee_user)
        await client.post(
            f"{ME}/exit-interview",
            json={"reason_for_leaving": "Career change", "overall_experience": 4},
            headers=employee_headers,
        )

        stranger_headers = await _sign_in(client, people.stranger_user)
        # Their own is empty ...
        own = await client.get(f"{ME}/exit-interview", headers=stranger_headers)
        assert own.status_code == 200
        assert own.json()["data"] is None
        # ... and the administrative route is closed to them entirely.
        other = await client.get(f"{OFFBOARDING}/cases/{case['id']}/exit-interview", headers=stranger_headers)
        assert other.status_code == 403

    async def test_hr_reads_completed_exit_interviews(self, client: AsyncClient, people: People) -> None:
        await _through_to_case(client, people)
        employee_headers = await _sign_in(client, people.employee_user)
        await client.post(
            f"{ME}/exit-interview",
            json={"reason_for_leaving": "Career change", "overall_experience": 4},
            headers=employee_headers,
        )

        hr_headers = await _sign_in(client, people.hr_user)
        response = await client.get(f"{OFFBOARDING}/exit-interviews", headers=hr_headers)
        assert response.status_code == 200
        assert response.json()["data"]["meta"]["total_items"] >= 1

    async def test_an_employee_downloads_only_released_documents_of_their_own(
        self, client: AsyncClient, people: People
    ) -> None:
        case, hr_headers = await _through_to_case(client, people)

        # Generated but not released: not the employee's yet.
        await client.post(
            f"{OFFBOARDING}/cases/{case['id']}/documents",
            json={"document_type": "experience_letter", "release": False},
            headers=hr_headers,
        )
        employee_headers = await _sign_in(client, people.employee_user)
        before = await client.get(f"{ME}/exit-documents", headers=employee_headers)
        assert before.json()["data"] == []

        await client.post(
            f"{OFFBOARDING}/cases/{case['id']}/documents",
            json={"document_type": "relieving_letter", "release": True},
            headers=hr_headers,
        )
        after = await client.get(f"{ME}/exit-documents", headers=employee_headers)
        types = {row["document_type"] for row in after.json()["data"]}
        assert types == {"relieving_letter"}

    async def test_another_employee_sees_none_of_those_documents(
        self, client: AsyncClient, people: People
    ) -> None:
        case, hr_headers = await _through_to_case(client, people)
        await client.post(
            f"{OFFBOARDING}/cases/{case['id']}/documents",
            json={"document_type": "relieving_letter", "release": True},
            headers=hr_headers,
        )

        stranger_headers = await _sign_in(client, people.stranger_user)
        response = await client.get(f"{ME}/exit-documents", headers=stranger_headers)
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_an_employee_cannot_reach_another_employees_case(
        self, client: AsyncClient, people: People
    ) -> None:
        case, _ = await _through_to_case(client, people)
        stranger_headers = await _sign_in(client, people.stranger_user)
        assert (
            await client.get(f"{OFFBOARDING}/cases/{case['id']}", headers=stranger_headers)
        ).status_code == 403


# ======================================================================
# 15-19. Completion: what stops, and what survives
# ======================================================================
class TestCompletionAndHistory:
    @staticmethod
    async def _complete(client: AsyncClient, case: dict, headers: dict[str, str]) -> None:
        response = await client.post(
            f"{OFFBOARDING}/cases/{case['id']}/complete",
            json={"comments": "Cleared", "force": True},
            headers=headers,
        )
        assert response.status_code == 200, response.text

    async def test_completion_sets_the_employee_inactive_without_deleting_them(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        case, hr_headers = await _through_to_case(client, people)
        await self._complete(client, case, hr_headers)

        await db_session.refresh(people.employee)
        assert people.employee.employment_status == EmploymentStatus.INACTIVE.value
        assert people.employee.deleted_at is None, "an exit is not a deletion"

        # The separation records survive too.
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(OffboardingCase)
                .where(OffboardingCase.employee_id == people.employee.id)
            )
        ) == 1

    async def test_completion_disables_the_login(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        """The gap the audit found: the exit set ``employment_status`` and
        never touched ``users.is_active`` -- and authentication checks only the
        account. A departed employee could keep signing in indefinitely.
        """
        case, hr_headers = await _through_to_case(client, people)
        await self._complete(client, case, hr_headers)

        await db_session.refresh(people.employee_user)
        assert people.employee_user.is_active is False

        refused = await client.post(
            f"{API}/auth/login",
            json={"email": people.employee_user.email, "password": PASSWORD},
        )
        assert refused.status_code in (401, 403)

    async def test_an_exited_employee_cannot_record_new_attendance(
        self, client: AsyncClient, people: People
    ) -> None:
        case, hr_headers = await _through_to_case(client, people)
        employee_headers = await _sign_in(client, people.employee_user)
        await self._complete(client, case, hr_headers)

        response = await client.post(
            f"{ME}/attendance/check-in", json={"work_mode": "office"}, headers=employee_headers
        )
        # The account check refuses before the domain guard is reached: the
        # exit disabled the login. The 409 guard is covered separately, with
        # the account deliberately reactivated.
        assert response.status_code == 403

    async def test_an_exited_employee_cannot_apply_for_leave(
        self, client: AsyncClient, people: People
    ) -> None:
        case, hr_headers = await _through_to_case(client, people)
        employee_headers = await _sign_in(client, people.employee_user)

        types = await client.get(f"{ME}/leave/types", headers=employee_headers)
        assert types.status_code == 200
        available = types.json()["data"]
        if not available:
            pytest.skip("no leave types seeded in this database")

        await self._complete(client, case, hr_headers)
        response = await client.post(
            f"{ME}/leave",
            json={
                "leave_type_id": available[0]["id"],
                "from_date": (TODAY + timedelta(days=2)).isoformat(),
                "to_date": (TODAY + timedelta(days=3)).isoformat(),
                "reason": "Travel",
            },
            headers=employee_headers,
        )
        assert response.status_code == 403

    async def test_an_exited_employee_cannot_save_a_timesheet(
        self, client: AsyncClient, people: People
    ) -> None:
        case, hr_headers = await _through_to_case(client, people)
        employee_headers = await _sign_in(client, people.employee_user)
        await self._complete(client, case, hr_headers)

        monday = TODAY - timedelta(days=TODAY.weekday())
        response = await client.post(
            f"{ME}/timesheets",
            json={"week_start_date": monday.isoformat(), "entries": []},
            headers=employee_headers,
        )
        assert response.status_code == 403

    async def test_historical_records_survive_and_the_domain_guard_holds(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        """§19 and §21: nothing is deleted, and even a deliberately restored
        login cannot create new operational records.

        The exit disables the account, so the original read-after-exit check
        now happens through the door HR would actually open: reactivating the
        account for a returning alum. Reads answer; the ``employee_exited``
        domain guard still refuses new attendance -- it is the second lock on
        the door, for exactly this case.
        """
        case, hr_headers = await _through_to_case(client, people)
        await self._complete(client, case, hr_headers)

        people.employee_user.is_active = True
        await db_session.flush()
        employee_headers = await _sign_in(client, people.employee_user)

        for path in (f"{ME}/attendance", f"{ME}/leave", f"{ME}/timesheets", f"{ME}/offboarding"):
            response = await client.get(path, headers=employee_headers)
            assert response.status_code == 200, f"{path} -> {response.text}"

        refused = await client.post(
            f"{ME}/attendance/check-in", json={"work_mode": "office"}, headers=employee_headers
        )
        assert refused.status_code == 409
        assert refused.json()["errors"][0]["code"] == "employee_exited"

    async def test_project_allocation_is_ended_not_deleted(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        """§20: end the allocation, keep the history."""
        client_row = Client(
            client_name=f"Client {uuid.uuid4().hex[:6]}",
            company_name="Client Co",
            industry="Technology",
            contact_person="Alex Contact",
            email="contact@client.example",
            phone="+911234567890",
            country="India",
            address="1 Client Street",
            status=RecordStatus.ACTIVE,
        )
        db_session.add(client_row)
        await db_session.flush()
        project = Project(
            project_name=f"Project {uuid.uuid4().hex[:6]}",
            client_id=client_row.id,
            description="Delivery engagement used to prove allocation history survives an exit.",
            project_manager_id=people.manager.id,
            start_date=date(2025, 1, 1),
            status="active",
        )
        db_session.add(project)
        await db_session.flush()
        member = ProjectMember(
            project_id=project.id, employee_id=people.employee.id, role="Engineer", joined_at=date(2025, 1, 1)
        )
        db_session.add(member)
        await db_session.flush()
        allocation = EmployeeAllocation(
            employee_id=people.employee.id,
            project_id=project.id,
            member_id=member.id,
            allocation_percentage=100,
            start_date=date(2025, 1, 1),
            status="active",
            billable=True,
        )
        db_session.add(allocation)
        await db_session.flush()

        case, hr_headers = await _through_to_case(client, people)
        await self._complete(client, case, hr_headers)

        await db_session.refresh(allocation)
        assert allocation.status == "ended"
        assert allocation.deleted_at is None, "allocation history is preserved"
        assert allocation.end_date is not None


# ======================================================================
# 20. Overrides are audited as overrides
# ======================================================================
class TestAuditing:
    async def test_an_administrative_override_is_audited_as_one(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        case, _ = await _through_to_case(client, people)
        admin_headers = await _sign_in(client, people.admin_user)

        moved = await client.post(
            f"{OFFBOARDING}/resignations/{case['resignation_id']}/last-working-day",
            json={
                "approved_last_working_day": (LAST_DAY + timedelta(days=7)).isoformat(),
                "reason": "Project handover needs another week",
            },
            headers=admin_headers,
        )
        assert moved.status_code == 200, moved.text

        overrides = (
            await db_session.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.OFFBOARDING_OVERRIDDEN.value)
            )
        ).scalar_one()
        assert overrides >= 1, "an override must be auditable as an override, not just as an update"

    async def test_a_forced_completion_is_audited_and_recorded_in_history(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        case, hr_headers = await _through_to_case(client, people)
        response = await client.post(
            f"{OFFBOARDING}/cases/{case['id']}/complete",
            json={"comments": "Laptop written off", "force": True},
            headers=hr_headers,
        )
        assert response.status_code == 200

        actions = (
            (
                await db_session.execute(
                    select(AuditLog.action).where(
                        AuditLog.action.in_(
                            [
                                AuditAction.OFFBOARDING_COMPLETED.value,
                                AuditAction.EMPLOYEE_EXITED.value,
                                AuditAction.OFFBOARDING_OVERRIDDEN.value,
                            ]
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        assert AuditAction.OFFBOARDING_COMPLETED.value in actions
        assert AuditAction.EMPLOYEE_EXITED.value in actions
        assert AuditAction.OFFBOARDING_OVERRIDDEN.value in actions

    async def test_completion_is_refused_while_clearance_is_outstanding(
        self, client: AsyncClient, people: People
    ) -> None:
        case, hr_headers = await _through_to_case(client, people)
        response = await client.post(
            f"{OFFBOARDING}/cases/{case['id']}/complete", json={"force": False}, headers=hr_headers
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "clearance_outstanding"

    async def test_the_lifecycle_is_recorded_in_resignation_history(
        self, client: AsyncClient, people: People
    ) -> None:
        case, hr_headers = await _through_to_case(client, people)
        detail = await client.get(f"{OFFBOARDING}/resignations/{case['resignation_id']}", headers=hr_headers)
        actions = [row["action"] for row in detail.json()["data"]["history"]]
        assert actions[0] == "submitted"
        assert "manager_approved" in actions
        assert "hr_processed" in actions


# ======================================================================
# Notice period (§6)
# ======================================================================
class TestNoticePeriod:
    async def test_the_notice_period_comes_from_the_employment_type(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        """Configuration, not a constant. Changing the master changes the answer."""
        from app.models.employment_type import EmploymentType

        employment_type = EmploymentType(
            name=f"Fixed Term {uuid.uuid4().hex[:6]}",
            code=f"FT{uuid.uuid4().hex[:6].upper()}",
            status=RecordStatus.ACTIVE,
            notice_period_days=45,
        )
        db_session.add(employment_type)
        await db_session.flush()
        people.employee.employment_type_id = employment_type.id
        await db_session.flush()

        headers = await _sign_in(client, people.employee_user)
        data = await _submit(client, headers)
        assert data["notice"]["notice_period_days"] == 45

    async def test_an_adjustment_needs_a_reason_and_is_recorded(
        self, client: AsyncClient, people: People
    ) -> None:
        employee_headers = await _sign_in(client, people.employee_user)
        resignation = await _submit(client, employee_headers)
        manager_headers = await _sign_in(client, people.manager_user)
        await client.post(
            f"{MANAGER}/resignations/{resignation['id']}/decision",
            json={"decision": "approve"},
            headers=manager_headers,
        )

        hr_headers = await _sign_in(client, people.hr_user)
        without_reason = await client.post(
            f"{OFFBOARDING}/resignations/{resignation['id']}/process",
            json={"notice_period_days": 15},
            headers=hr_headers,
        )
        assert without_reason.status_code == 409

        with_reason = await client.post(
            f"{OFFBOARDING}/resignations/{resignation['id']}/process",
            json={"notice_period_days": 15, "adjustment_reason": "Mutually agreed early release"},
            headers=hr_headers,
        )
        assert with_reason.status_code == 201, with_reason.text
        assert with_reason.json()["data"]["notice_period_days"] == 15

        detail = await client.get(f"{OFFBOARDING}/resignations/{resignation['id']}", headers=hr_headers)
        history = detail.json()["data"]["history"]
        adjustments = [row for row in history if row["action"] == "notice_period_adjusted"]
        assert adjustments and adjustments[0]["is_override"] is True
