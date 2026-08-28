"""Integration tests for manager team scoping.

RBAC answers "may this user do that?". These tests cover the other half --
"to whom?" -- and, like ``test_rbac.py``, the ones that matter are the refusals.
A manager who can approve their own team's leave *and* everybody else's looks
exactly like a working approval screen right up until they open a colleague's
salary conversation.

The shape of every test is the same: three employees -- a manager, somebody who
reports to them, and a stranger who does not -- and the same request made twice.
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
from app.models.workforce import AttendanceRecord, LeaveRequest, LeaveType, Timesheet
from app.services.authorization_service import AuthorizationService
from app.services.scope_service import TeamScopeService

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
EMPLOYEES = f"{API}/employees"
WORKFORCE = f"{API}/workforce"
DOCUMENTS = f"{API}/documents"

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
        first_name=label.title(),
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


class Team:
    """A manager, one direct report, and a stranger who reports elsewhere."""

    def __init__(
        self,
        manager: Employee,
        manager_user: User,
        report: Employee,
        stranger: Employee,
        stranger_manager: Employee,
    ) -> None:
        self.manager = manager
        self.manager_user = manager_user
        self.report = report
        self.stranger = stranger
        self.stranger_manager = stranger_manager


@pytest.fixture
async def org(db_session: AsyncSession) -> Team:
    manager_user = await _account(db_session, "manager", "mgr")
    manager = await _employee(db_session, "manager", user=manager_user)
    report = await _employee(db_session, "report", manager=manager)

    # The stranger reports to somebody else entirely. Not simply unmanaged: an
    # employee with no manager at all would pass a buggy `IS NULL` check that a
    # properly scoped query has to refuse.
    other_manager = await _employee(db_session, "other")
    stranger = await _employee(db_session, "stranger", manager=other_manager)

    return Team(manager, manager_user, report, stranger, other_manager)


@pytest.fixture
async def manager_headers(client: AsyncClient, org: Team) -> dict[str, str]:
    return await _sign_in(client, org.manager_user)


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


def _ids(payload: dict, field: str = "employee_id") -> set[str]:
    return {str(item[field]) for item in payload["data"]["items"]}


# ----------------------------------------------------------------------
class TestScopeResolution:
    """The rule itself, before any endpoint applies it."""

    async def test_a_manager_sees_themselves_and_their_direct_reports(
        self, db_session: AsyncSession, org: Team
    ) -> None:
        scope = await TeamScopeService(db_session, AuthorizationService(db_session)).for_user(
            org.manager_user
        )
        assert not scope.unrestricted
        assert scope.employee_ids == {org.manager.id, org.report.id}
        assert not scope.allows(org.stranger.id)

    async def test_a_skip_level_report_is_out_of_scope(self, db_session: AsyncSession, org: Team) -> None:
        """Direct reports, one hop. A report's own reports are theirs to manage."""
        skip_level = await _employee(db_session, "skip", manager=org.report)

        scope = await TeamScopeService(db_session, AuthorizationService(db_session)).for_user(
            org.manager_user
        )
        assert not scope.allows(skip_level.id)

    async def test_hr_is_unrestricted(self, db_session: AsyncSession, org: Team) -> None:
        hr = await _account(db_session, "hr_admin", "hr")
        scope = await TeamScopeService(db_session, AuthorizationService(db_session)).for_user(hr)

        assert scope.unrestricted
        assert scope.allows(org.stranger.id)
        assert scope.visible_employee_ids is None, "an unrestricted scope applies no filter"

    async def test_a_superuser_is_unrestricted_without_any_role(
        self, db_session: AsyncSession, org: Team
    ) -> None:
        root = await _account(db_session, None, "root")
        root.is_superuser = True
        await db_session.flush()

        scope = await TeamScopeService(db_session, AuthorizationService(db_session)).for_user(root)
        assert scope.unrestricted

    async def test_an_account_with_no_employee_record_reaches_nobody(
        self, db_session: AsyncSession, org: Team
    ) -> None:
        """An IT or integration account is legitimate, and scopes to nothing."""
        orphan = await _account(db_session, "manager", "orphan")

        scope = await TeamScopeService(db_session, AuthorizationService(db_session)).for_user(orphan)
        assert scope.employee_ids == frozenset()
        assert not scope.allows(org.report.id)
        assert (
            scope.visible_employee_ids == frozenset()
        ), "an empty filter must stay empty, not fall back to unrestricted"

    async def test_an_archived_report_leaves_the_scope(self, db_session: AsyncSession, org: Team) -> None:
        from app.utils.datetime import utc_now

        org.report.deleted_at = utc_now()
        await db_session.flush()

        scope = await TeamScopeService(db_session, AuthorizationService(db_session)).for_user(
            org.manager_user
        )
        assert not scope.allows(org.report.id)


# ----------------------------------------------------------------------
class TestEmployeeProfile:
    async def test_a_manager_reads_their_own_report(
        self, client: AsyncClient, org: Team, manager_headers: dict[str, str]
    ) -> None:
        response = await client.get(f"{EMPLOYEES}/{org.report.id}", headers=manager_headers)
        assert response.status_code == 200, response.text

    async def test_a_manager_cannot_read_somebody_elses_report(
        self, client: AsyncClient, org: Team, manager_headers: dict[str, str]
    ) -> None:
        response = await client.get(f"{EMPLOYEES}/{org.stranger.id}", headers=manager_headers)
        assert response.status_code == 403, response.text
        assert response.json()["errors"][0]["code"] == "outside_your_team"

    async def test_a_manager_reads_their_own_profile(
        self, client: AsyncClient, org: Team, manager_headers: dict[str, str]
    ) -> None:
        response = await client.get(f"{EMPLOYEES}/{org.manager.id}", headers=manager_headers)
        assert response.status_code == 200, response.text

    async def test_the_directory_is_narrowed_to_the_team(
        self, client: AsyncClient, org: Team, manager_headers: dict[str, str]
    ) -> None:
        response = await client.get(EMPLOYEES, headers=manager_headers, params={"page_size": 100})
        assert response.status_code == 200, response.text

        listed = {str(item["id"]) for item in response.json()["data"]["items"]}
        assert listed == {str(org.manager.id), str(org.report.id)}

    async def test_the_history_and_audit_tabs_are_scoped_too(
        self, client: AsyncClient, org: Team, manager_headers: dict[str, str]
    ) -> None:
        """A tab is not a different question; the same record is behind all of them."""
        for tab in ("history", "audit", "sensitive"):
            response = await client.get(f"{EMPLOYEES}/{org.stranger.id}/{tab}", headers=manager_headers)
            assert response.status_code == 403, f"{tab}: {response.text}"

    async def test_hr_still_sees_the_whole_directory(
        self, client: AsyncClient, db_session: AsyncSession, org: Team
    ) -> None:
        hr = await _account(db_session, "hr_admin", "hr")
        headers = await _sign_in(client, hr)

        response = await client.get(EMPLOYEES, headers=headers, params={"page_size": 100})
        assert response.status_code == 200, response.text

        listed = {str(item["id"]) for item in response.json()["data"]["items"]}
        assert {str(org.stranger.id), str(org.manager.id)} <= listed

        assert (await client.get(f"{EMPLOYEES}/{org.stranger.id}", headers=headers)).status_code == 200


# ----------------------------------------------------------------------
class TestAttendance:
    async def test_the_register_is_narrowed_to_the_team(
        self, client: AsyncClient, db_session: AsyncSession, org: Team, manager_headers: dict[str, str]
    ) -> None:
        for employee in (org.manager, org.report, org.stranger):
            db_session.add(AttendanceRecord(employee_id=employee.id, attendance_date=date(2026, 3, 4)))
        await db_session.flush()

        response = await client.get(
            f"{WORKFORCE}/attendance", headers=manager_headers, params={"page_size": 100}
        )
        assert response.status_code == 200, response.text
        assert _ids(response.json()) == {str(org.manager.id), str(org.report.id)}

    async def test_a_manager_cannot_read_a_strangers_calendar(
        self, client: AsyncClient, org: Team, manager_headers: dict[str, str]
    ) -> None:
        response = await client.get(
            f"{WORKFORCE}/calendar/{org.stranger.id}",
            headers=manager_headers,
            params={"year": 2026, "month": 3},
        )
        assert response.status_code == 403, response.text

    async def test_a_manager_can_read_their_reports_calendar(
        self, client: AsyncClient, org: Team, manager_headers: dict[str, str]
    ) -> None:
        response = await client.get(
            f"{WORKFORCE}/calendar/{org.report.id}",
            headers=manager_headers,
            params={"year": 2026, "month": 3},
        )
        assert response.status_code == 200, response.text

    async def test_a_manager_cannot_check_in_for_a_stranger(
        self, client: AsyncClient, org: Team, manager_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            f"{WORKFORCE}/attendance/{org.stranger.id}/check-in",
            headers=manager_headers,
            json={"work_mode": "office"},
        )
        assert response.status_code == 403, response.text


# ----------------------------------------------------------------------
class TestLeave:
    async def test_the_list_is_narrowed_to_the_team(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Team,
        leave_type: LeaveType,
        manager_headers: dict[str, str],
    ) -> None:
        for employee in (org.report, org.stranger):
            await _leave(db_session, employee, leave_type)

        response = await client.get(f"{WORKFORCE}/leave", headers=manager_headers, params={"page_size": 100})
        assert response.status_code == 200, response.text
        assert _ids(response.json()) == {str(org.report.id)}

    async def test_a_manager_approves_their_own_reports_leave(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Team,
        leave_type: LeaveType,
        manager_headers: dict[str, str],
    ) -> None:
        request = await _leave(db_session, org.report, leave_type)

        response = await client.post(
            f"{WORKFORCE}/leave/{request.id}/decide",
            headers=manager_headers,
            json={"approved": True},
        )
        assert response.status_code == 200, response.text

    async def test_a_manager_cannot_approve_a_strangers_leave(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Team,
        leave_type: LeaveType,
        manager_headers: dict[str, str],
    ) -> None:
        """The decision is keyed by request id, so the check has to survive the
        caller never naming an employee at all."""
        request = await _leave(db_session, org.stranger, leave_type)

        response = await client.post(
            f"{WORKFORCE}/leave/{request.id}/decide",
            headers=manager_headers,
            json={"approved": True},
        )
        assert response.status_code == 403, response.text

        await db_session.refresh(request)
        assert request.status == ApprovalStatus.PENDING.value, "the refusal must not have decided it"

    async def test_a_manager_cannot_cancel_a_strangers_leave(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Team,
        leave_type: LeaveType,
        manager_headers: dict[str, str],
    ) -> None:
        request = await _leave(db_session, org.stranger, leave_type)

        response = await client.post(f"{WORKFORCE}/leave/{request.id}/cancel", headers=manager_headers)
        assert response.status_code == 403, response.text

    async def test_a_manager_cannot_read_a_strangers_balances(
        self, client: AsyncClient, org: Team, manager_headers: dict[str, str]
    ) -> None:
        response = await client.get(f"{WORKFORCE}/leave/balances/{org.stranger.id}", headers=manager_headers)
        assert response.status_code == 403, response.text

    async def test_hr_can_approve_anybodys_leave(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        org: Team,
        leave_type: LeaveType,
    ) -> None:
        hr = await _account(db_session, "hr_admin", "hr")
        headers = await _sign_in(client, hr)
        request = await _leave(db_session, org.stranger, leave_type)

        response = await client.post(
            f"{WORKFORCE}/leave/{request.id}/decide", headers=headers, json={"approved": True}
        )
        assert response.status_code == 200, response.text


# ----------------------------------------------------------------------
class TestTimesheets:
    @staticmethod
    def _week() -> date:
        today = date(2026, 3, 2)
        return today - timedelta(days=today.weekday())

    async def test_the_list_is_narrowed_to_the_team(
        self, client: AsyncClient, db_session: AsyncSession, org: Team, manager_headers: dict[str, str]
    ) -> None:
        for employee in (org.report, org.stranger):
            db_session.add(Timesheet(employee_id=employee.id, week_start_date=self._week()))
        await db_session.flush()

        response = await client.get(
            f"{WORKFORCE}/timesheets", headers=manager_headers, params={"page_size": 100}
        )
        assert response.status_code == 200, response.text
        assert _ids(response.json()) == {str(org.report.id)}

    async def test_a_manager_cannot_open_a_strangers_timesheet(
        self, client: AsyncClient, db_session: AsyncSession, org: Team, manager_headers: dict[str, str]
    ) -> None:
        sheet = Timesheet(employee_id=org.stranger.id, week_start_date=self._week())
        db_session.add(sheet)
        await db_session.flush()

        response = await client.get(f"{WORKFORCE}/timesheets/{sheet.id}", headers=manager_headers)
        assert response.status_code == 403, response.text

    async def test_a_manager_cannot_decide_a_strangers_timesheet(
        self, client: AsyncClient, db_session: AsyncSession, org: Team, manager_headers: dict[str, str]
    ) -> None:
        sheet = Timesheet(
            employee_id=org.stranger.id,
            week_start_date=self._week(),
            status="submitted",
        )
        db_session.add(sheet)
        await db_session.flush()

        response = await client.post(
            f"{WORKFORCE}/timesheets/{sheet.id}/decide",
            headers=manager_headers,
            json={"approved": True},
        )
        assert response.status_code == 403, response.text

    async def test_a_manager_can_open_their_reports_timesheet(
        self, client: AsyncClient, db_session: AsyncSession, org: Team, manager_headers: dict[str, str]
    ) -> None:
        sheet = Timesheet(employee_id=org.report.id, week_start_date=self._week())
        db_session.add(sheet)
        await db_session.flush()

        response = await client.get(f"{WORKFORCE}/timesheets/{sheet.id}", headers=manager_headers)
        assert response.status_code == 200, response.text


# ----------------------------------------------------------------------
class TestDocuments:
    @staticmethod
    async def _classification(session: AsyncSession) -> DocumentType:
        suffix = uuid.uuid4().hex[:4].upper()
        category = DocumentCategory(
            name=f"Personal {suffix}", code=f"PER{suffix}", status=RecordStatus.ACTIVE
        )
        session.add(category)
        await session.flush()

        document_type = DocumentType(
            name=f"Payslip {suffix}",
            code=f"PAY{suffix}",
            category_id=category.id,
            status=RecordStatus.ACTIVE,
        )
        session.add(document_type)
        await session.flush()
        return document_type

    async def _document(self, session: AsyncSession, owner_type: str, owner_id: uuid.UUID) -> Document:
        document_type = await self._classification(session)
        document = Document(
            name="Payslip",
            category_id=document_type.category_id,
            document_type_id=document_type.id,
            owner_type=owner_type,
            owner_id=owner_id,
            status=DocumentStatus.UPLOADED,
        )
        session.add(document)
        await session.flush()
        return document

    async def test_the_vault_is_narrowed_to_the_team(
        self, client: AsyncClient, db_session: AsyncSession, org: Team, manager_headers: dict[str, str]
    ) -> None:
        mine = await self._document(db_session, DocumentOwnerType.EMPLOYEE.value, org.report.id)
        theirs = await self._document(db_session, DocumentOwnerType.EMPLOYEE.value, org.stranger.id)

        response = await client.get(DOCUMENTS, headers=manager_headers, params={"page_size": 100})
        assert response.status_code == 200, response.text

        listed = {str(item["id"]) for item in response.json()["data"]["items"]}
        assert str(mine.id) in listed
        assert str(theirs.id) not in listed

    async def test_a_manager_cannot_open_a_strangers_document(
        self, client: AsyncClient, db_session: AsyncSession, org: Team, manager_headers: dict[str, str]
    ) -> None:
        document = await self._document(db_session, DocumentOwnerType.EMPLOYEE.value, org.stranger.id)

        assert (await client.get(f"{DOCUMENTS}/{document.id}", headers=manager_headers)).status_code == 403
        assert (
            await client.get(f"{DOCUMENTS}/{document.id}/download", headers=manager_headers)
        ).status_code == 403
        assert (
            await client.get(f"{DOCUMENTS}/{document.id}/versions", headers=manager_headers)
        ).status_code == 403

    async def test_a_document_filed_against_the_user_account_is_scoped_too(
        self, client: AsyncClient, db_session: AsyncSession, org: Team, manager_headers: dict[str, str]
    ) -> None:
        """The vault files against an employee *or* their login account. Scoping
        one and not the other would leave the same paperwork readable."""
        stranger_user = await _account(db_session, None, "stranger_user")
        org.stranger.user_id = stranger_user.id
        await db_session.flush()

        document = await self._document(db_session, DocumentOwnerType.USER.value, stranger_user.id)
        response = await client.get(f"{DOCUMENTS}/{document.id}", headers=manager_headers)
        assert response.status_code == 403, response.text

    async def test_company_documents_stay_readable(
        self, client: AsyncClient, db_session: AsyncSession, org: Team, manager_headers: dict[str, str]
    ) -> None:
        """A policy has no reporting line. Narrowing it would hide the handbook."""
        document = await self._document(db_session, DocumentOwnerType.ORGANIZATION.value, uuid.uuid4())

        response = await client.get(f"{DOCUMENTS}/{document.id}", headers=manager_headers)
        assert response.status_code == 200, response.text
