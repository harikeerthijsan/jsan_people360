"""Employee self-service API.

Two employees, two accounts, one suite. Almost every test below is the same
request made twice -- once by the person it belongs to, once by somebody else --
because that is the failure this module exists to make impossible and the only
one that is expensive to discover late.

The other half of the coverage is negative in a different way: what the portal
*cannot* do. An employee cannot write an attendance record directly, cannot post
a placement change through their profile, cannot book hours to a project they
are not on, and cannot reissue a letter HR sent them. Each of those is a thing
the underlying modules permit for a caller with the right permission, so each
needs a test proving self-service does not inherit it.

``test_rbac.py`` covers the structural half: that no ``/me`` route accepts an
identity parameter at all.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.document_category import DocumentCategory, DocumentType
from app.models.employee import Employee
from app.models.enums import (
    ApprovalStatus,
    EmploymentStatus,
    RecordStatus,
)
from app.models.project import Client, EmployeeAllocation, Project, ProjectMember
from app.models.rbac import Role, UserRole
from app.models.requisition import Notification
from app.models.user import User
from app.models.workforce import (
    AttendanceRecord,
    HolidayCalendar,
    LeaveRequest,
    LeaveType,
    Shift,
)
from app.storage import get_storage

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
ME = f"{API}/me"
DOCUMENTS = f"{API}/documents"
WORKFORCE = f"{API}/workforce"
EMPLOYEES = f"{API}/employees"

PASSWORD = "Str0ng!Passw0rd"
PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"

TODAY = datetime.now(UTC).date()
MONDAY = TODAY - timedelta(days=TODAY.weekday())


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the vault at a temporary directory, as the vault's own suite does."""
    root = tmp_path / "vault"
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(root))
    get_storage.cache_clear()
    yield root
    get_storage.cache_clear()


async def _account(session: AsyncSession, label: str, *, role_key: str = "employee") -> User:
    """A plain, non-superuser account holding one seeded role."""
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
    assert role is not None, f"the {role_key} role should have been seeded"
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.flush()
    return user


async def _employee_for(
    session: AsyncSession,
    user: User,
    label: str,
    *,
    manager: Employee | None = None,
    location_id: uuid.UUID | None = None,
) -> Employee:
    suffix = uuid.uuid4().hex[:8]
    record = Employee(
        first_name=label.title(),
        last_name="Person",
        official_email=f"{label}.{suffix}@jsan.example",
        joining_date=date(2026, 1, 5),
        employment_status=EmploymentStatus.ACTIVE,
        user_id=user.id,
        reporting_manager_id=manager.id if manager else None,
        work_location_id=location_id,
    )
    session.add(record)
    await session.flush()
    return record


async def _sign_in(client: AsyncClient, user: User) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['tokens']['access_token']}"}


class Pair:
    """Employee A, employee B, and the manager A reports to."""

    def __init__(
        self,
        a_user: User,
        a: Employee,
        b_user: User,
        b: Employee,
        manager_user: User,
        manager: Employee,
    ) -> None:
        self.a_user = a_user
        self.a = a
        self.b_user = b_user
        self.b = b
        self.manager_user = manager_user
        self.manager = manager


@pytest.fixture
async def pair(db_session: AsyncSession) -> Pair:
    manager_user = await _account(db_session, "mgr", role_key="manager")
    manager = await _employee_for(db_session, manager_user, "manager")

    a_user = await _account(db_session, "alice")
    a = await _employee_for(db_session, a_user, "alice", manager=manager)

    # B reports to somebody else entirely, so a scope bug that admits "anyone
    # without a manager" would not pass unnoticed.
    b_user = await _account(db_session, "bob")
    other_manager_user = await _account(db_session, "other", role_key="manager")
    other_manager = await _employee_for(db_session, other_manager_user, "other")
    b = await _employee_for(db_session, b_user, "bob", manager=other_manager)

    return Pair(a_user, a, b_user, b, manager_user, manager)


@pytest.fixture
async def alice(client: AsyncClient, pair: Pair) -> dict[str, str]:
    return await _sign_in(client, pair.a_user)


@pytest.fixture
async def bob(client: AsyncClient, pair: Pair) -> dict[str, str]:
    return await _sign_in(client, pair.b_user)


@pytest.fixture
async def manager_headers(client: AsyncClient, pair: Pair) -> dict[str, str]:
    return await _sign_in(client, pair.manager_user)


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


@pytest.fixture
async def shift(db_session: AsyncSession) -> Shift:
    record = Shift(
        name="General",
        code=f"GEN{uuid.uuid4().hex[:4].upper()}",
        start_time=datetime(2026, 1, 1, 9, 0).time(),
        end_time=datetime(2026, 1, 1, 18, 0).time(),
        weekly_off=[5, 6],
        status=RecordStatus.ACTIVE,
    )
    db_session.add(record)
    await db_session.flush()
    return record


@pytest.fixture
async def document_type(db_session: AsyncSession) -> DocumentType:
    category = DocumentCategory(
        name="Identity", code=f"ID{uuid.uuid4().hex[:6].upper()}", status=RecordStatus.ACTIVE
    )
    db_session.add(category)
    await db_session.flush()

    record = DocumentType(
        name="Passport",
        code=f"PP{uuid.uuid4().hex[:6].upper()}",
        category_id=category.id,
        status=RecordStatus.ACTIVE,
    )
    db_session.add(record)
    await db_session.flush()
    return record


async def _project_for(
    session: AsyncSession, employee: Employee, *, start: date, end: date | None = None
) -> Project:
    """A client, a project, a membership and an allocation for one employee."""
    suffix = uuid.uuid4().hex[:6].upper()
    client_record = Client(
        client_name=f"Client {suffix}",
        company_name=f"Client {suffix} Ltd",
        industry="Technology",
        contact_person="Contact",
        email=f"contact.{suffix.lower()}@client.example",
        phone="9999999999",
        country="India",
        address="1 Client Street",
        status="active",
    )
    session.add(client_record)
    await session.flush()

    project = Project(
        project_name=f"Project {suffix}",
        client_id=client_record.id,
        description="Delivery work",
        start_date=start,
        status="active",
        project_manager_id=employee.id,
    )
    session.add(project)
    await session.flush()

    member = ProjectMember(
        project_id=project.id,
        employee_id=employee.id,
        role="Software Engineer",
        joined_at=start,
    )
    session.add(member)
    await session.flush()

    session.add(
        EmployeeAllocation(
            employee_id=employee.id,
            project_id=project.id,
            member_id=member.id,
            allocation_percentage=Decimal("100.00"),
            start_date=start,
            end_date=end,
            billable=True,
            status="active",
        )
    )
    await session.flush()
    return project


async def _upload_my_document(
    client: AsyncClient, headers: dict[str, str], document_type: DocumentType, **overrides: Any
) -> dict[str, Any]:
    response = await client.post(
        f"{ME}/documents",
        data={
            "name": "Passport",
            "category_id": str(document_type.category_id),
            "document_type_id": str(document_type.id),
            **overrides,
        },
        files={"file": ("passport.pdf", PDF, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


# ======================================================================
# Identity
# ======================================================================
class TestIdentity:
    async def test_the_portal_resolves_the_employee_from_the_session(
        self, client: AsyncClient, pair: Pair, alice: dict[str, str]
    ) -> None:
        response = await client.get(ME, headers=alice)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["id"] == str(pair.a.id)

    async def test_two_employees_get_two_different_records_from_one_url(
        self, client: AsyncClient, pair: Pair, alice: dict[str, str], bob: dict[str, str]
    ) -> None:
        """The whole design in one assertion: the URL is identical, the answer is not."""
        mine = (await client.get(ME, headers=alice)).json()["data"]["id"]
        theirs = (await client.get(ME, headers=bob)).json()["data"]["id"]
        assert mine == str(pair.a.id)
        assert theirs == str(pair.b.id)
        assert mine != theirs

    async def test_an_account_with_no_employee_record_is_refused(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """An integration account is a legitimate thing to be, and not an employee."""
        user = await _account(db_session, "robot")
        headers = await _sign_in(client, user)

        response = await client.get(ME, headers=headers)
        assert response.status_code == 403
        assert response.json()["errors"][0]["code"] == "no_employee_record"

    async def test_the_portal_needs_a_session(self, client: AsyncClient) -> None:
        assert (await client.get(ME)).status_code == 401


# ======================================================================
# 1-5: attendance
# ======================================================================
class TestMyAttendance:
    async def test_an_employee_reads_their_own_attendance(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, alice: dict[str, str]
    ) -> None:
        db_session.add(AttendanceRecord(employee_id=pair.a.id, attendance_date=TODAY, status="present"))
        await db_session.flush()

        response = await client.get(f"{ME}/attendance", headers=alice)
        assert response.status_code == 200, response.text
        rows = response.json()["data"]["items"]
        assert rows
        assert {row["employee_id"] for row in rows} == {str(pair.a.id)}

    async def test_an_employee_never_sees_another_employees_attendance(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, bob: dict[str, str]
    ) -> None:
        """The list is filtered by the session, so B's page simply does not contain A."""
        db_session.add(AttendanceRecord(employee_id=pair.a.id, attendance_date=TODAY, status="present"))
        await db_session.flush()

        response = await client.get(f"{ME}/attendance", headers=bob)
        assert response.status_code == 200, response.text
        assert str(pair.a.id) not in {row["employee_id"] for row in response.json()["data"]["items"]}

    async def test_the_direct_endpoint_still_refuses_a_stranger(
        self, client: AsyncClient, pair: Pair, bob: dict[str, str]
    ) -> None:
        """The portal narrows; it does not replace the module's own guard.

        Included because a reviewer's first question about ``/me`` is "what
        stops them using the old URL instead?" -- and the answer has to be a
        test, not a promise.
        """
        response = await client.post(f"{WORKFORCE}/attendance/{pair.a.id}/check-in", json={}, headers=bob)
        assert response.status_code == 403

    async def test_an_employee_checks_themselves_in(
        self, client: AsyncClient, pair: Pair, alice: dict[str, str]
    ) -> None:
        response = await client.post(f"{ME}/attendance/check-in", json={}, headers=alice)
        assert response.status_code == 201, response.text
        assert response.json()["data"]["employee_id"] == str(pair.a.id)

    async def test_a_check_in_records_the_caller_and_nobody_they_name(
        self, client: AsyncClient, pair: Pair, bob: dict[str, str]
    ) -> None:
        """Sending somebody else's id is not refused -- it is not a field at all.

        ``extra="forbid"`` turns the attempt into a 422, which is a stronger
        outcome than silently ignoring it: the caller is told the field does not
        exist rather than being left believing it worked.
        """
        response = await client.post(
            f"{ME}/attendance/check-in",
            json={"employee_id": str(pair.a.id), "work_mode": "office"},
            headers=bob,
        )
        assert response.status_code == 422, response.text

        # And nothing was written for A.
        listed = await client.get(f"{ME}/attendance", headers=bob)
        assert str(pair.a.id) not in {row["employee_id"] for row in listed.json()["data"]["items"]}

    async def test_an_employee_checks_out_and_gets_their_hours(
        self, client: AsyncClient, alice: dict[str, str]
    ) -> None:
        await client.post(f"{ME}/attendance/check-in", json={}, headers=alice)
        response = await client.post(f"{ME}/attendance/check-out", json={}, headers=alice)

        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert body["check_out_at"] is not None
        assert body["worked_minutes"] >= 0

    async def test_checking_in_twice_is_refused(self, client: AsyncClient, alice: dict[str, str]) -> None:
        await client.post(f"{ME}/attendance/check-in", json={}, headers=alice)
        again = await client.post(f"{ME}/attendance/check-in", json={}, headers=alice)

        assert again.status_code == 409
        assert again.json()["errors"][0]["code"] == "already_checked_in"

    async def test_checking_out_before_checking_in_is_refused(
        self, client: AsyncClient, alice: dict[str, str]
    ) -> None:
        response = await client.post(f"{ME}/attendance/check-out", json={}, headers=alice)
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "not_checked_in"

    async def test_checking_in_again_after_checking_out_is_refused(
        self, client: AsyncClient, alice: dict[str, str]
    ) -> None:
        """The day already has a record, and a second one would double-count."""
        await client.post(f"{ME}/attendance/check-in", json={}, headers=alice)
        await client.post(f"{ME}/attendance/check-out", json={}, headers=alice)

        again = await client.post(f"{ME}/attendance/check-in", json={}, headers=alice)
        assert again.status_code == 409

    async def test_today_reports_which_action_is_available(
        self, client: AsyncClient, alice: dict[str, str]
    ) -> None:
        before = (await client.get(f"{ME}/attendance/today", headers=alice)).json()["data"]
        assert before["can_check_in"] is True
        assert before["can_check_out"] is False

        await client.post(f"{ME}/attendance/check-in", json={}, headers=alice)
        after = (await client.get(f"{ME}/attendance/today", headers=alice)).json()["data"]
        assert after["can_check_in"] is False
        assert after["can_check_out"] is True
        assert after["checked_in"] is True

    async def test_the_calendar_is_the_callers_own_month(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, alice: dict[str, str]
    ) -> None:
        db_session.add(
            AttendanceRecord(
                employee_id=pair.a.id, attendance_date=TODAY, status="present", worked_minutes=480
            )
        )
        await db_session.flush()

        response = await client.get(
            f"{ME}/attendance/calendar",
            params={"year": TODAY.year, "month": TODAY.month},
            headers=alice,
        )
        assert response.status_code == 200, response.text
        days = response.json()["data"]
        assert len(days) >= 28
        today_square = next(day for day in days if day["day"] == TODAY.isoformat())
        assert today_square["attendance_status"] == "present"

    async def test_the_summary_counts_late_arrivals_and_overtime(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, alice: dict[str, str]
    ) -> None:
        db_session.add(
            AttendanceRecord(
                employee_id=pair.a.id,
                attendance_date=TODAY,
                status="present",
                worked_minutes=540,
                late_minutes=15,
                early_exit_minutes=0,
                overtime_minutes=60,
            )
        )
        await db_session.flush()

        response = await client.get(
            f"{ME}/attendance/summary",
            params={"from_date": TODAY.replace(day=1).isoformat(), "to_date": TODAY.isoformat()},
            headers=alice,
        )
        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert body["present_days"] == 1
        assert body["late_arrivals"] == 1
        assert body["overtime_minutes"] == 60


# ======================================================================
# 5: regularization
# ======================================================================
class TestMyRegularizations:
    async def test_an_employee_requests_a_correction_for_themselves(
        self, client: AsyncClient, pair: Pair, alice: dict[str, str]
    ) -> None:
        yesterday = TODAY - timedelta(days=1)
        response = await client.post(
            f"{ME}/attendance/regularization",
            json={
                "attendance_date": yesterday.isoformat(),
                "requested_check_in_at": f"{yesterday.isoformat()}T09:00:00Z",
                "requested_check_out_at": f"{yesterday.isoformat()}T18:00:00Z",
                "reason": "Forgot to check in",
            },
            headers=alice,
        )
        assert response.status_code == 201, response.text
        assert response.json()["data"]["employee_id"] == str(pair.a.id)
        assert response.json()["data"]["status"] == "pending"

    async def test_an_employee_only_sees_their_own_corrections(
        self, client: AsyncClient, pair: Pair, alice: dict[str, str], bob: dict[str, str]
    ) -> None:
        yesterday = TODAY - timedelta(days=1)
        await client.post(
            f"{ME}/attendance/regularization",
            json={
                "attendance_date": yesterday.isoformat(),
                "requested_check_in_at": f"{yesterday.isoformat()}T09:00:00Z",
                "reason": "Forgot to check in",
            },
            headers=alice,
        )

        theirs = await client.get(f"{ME}/attendance/regularizations", headers=bob)
        assert theirs.status_code == 200
        assert theirs.json()["data"]["items"] == []

        mine = await client.get(f"{ME}/attendance/regularizations", headers=alice)
        assert len(mine.json()["data"]["items"]) == 1

    async def test_the_portal_offers_no_way_to_edit_attendance_directly(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, alice: dict[str, str]
    ) -> None:
        """A correction is a request, never a write.

        Asserted against the route table rather than by trying one URL, so a
        future ``PATCH /me/attendance/{id}`` fails this test the day it is added.
        """
        from fastapi.routing import APIRoute

        from app.api.v1.router import api_router

        def walk(router):
            for route in getattr(router, "routes", []):
                inner = getattr(route, "original_router", None)
                if inner is not None:
                    yield from walk(inner)
                elif isinstance(route, APIRoute):
                    yield route

        writes = {
            f"{sorted(route.methods - {'HEAD'})[0]} {route.path}"
            for route in walk(api_router)
            if route.path.startswith("/me/attendance") and route.methods & {"PATCH", "PUT", "DELETE"}
        }
        assert not writes, f"attendance must only be changed through a correction request: {writes}"


# ======================================================================
# 6-9: leave
# ======================================================================
class TestMyLeave:
    async def test_an_employee_reads_their_own_balance(
        self, client: AsyncClient, alice: dict[str, str], leave_type: LeaveType
    ) -> None:
        response = await client.get(f"{ME}/leave/balance", headers=alice)
        assert response.status_code == 200, response.text

        rows = response.json()["data"]
        casual = next(row for row in rows if row["leave_type_id"] == str(leave_type.id))
        assert Decimal(casual["allocated"]) == Decimal("12.0")
        assert Decimal(casual["available"]) == Decimal("12.0")
        assert Decimal(casual["used"]) == Decimal("0")
        assert Decimal(casual["pending"]) == Decimal("0")
        # Accrued is credited plus carried forward; with no carry-forward row it
        # equals the allocation.
        assert Decimal(casual["accrued"]) == Decimal("12.0")

    async def test_balances_are_per_employee(
        self, client: AsyncClient, alice: dict[str, str], bob: dict[str, str], leave_type: LeaveType
    ) -> None:
        """A's spend must not appear in B's balance."""
        await client.post(
            f"{ME}/leave",
            json={
                "leave_type_id": str(leave_type.id),
                "from_date": (MONDAY + timedelta(days=7)).isoformat(),
                "to_date": (MONDAY + timedelta(days=7)).isoformat(),
                "reason": "Personal",
            },
            headers=alice,
        )

        theirs = (await client.get(f"{ME}/leave/balance", headers=bob)).json()["data"]
        casual = next(row for row in theirs if row["leave_type_id"] == str(leave_type.id))
        assert Decimal(casual["pending"]) == Decimal("0")

    async def test_an_employee_applies_for_their_own_leave(
        self, client: AsyncClient, pair: Pair, alice: dict[str, str], leave_type: LeaveType
    ) -> None:
        start = MONDAY + timedelta(days=7)
        response = await client.post(
            f"{ME}/leave",
            json={
                "leave_type_id": str(leave_type.id),
                "from_date": start.isoformat(),
                "to_date": (start + timedelta(days=1)).isoformat(),
                "reason": "Family event",
            },
            headers=alice,
        )
        assert response.status_code == 201, response.text
        body = response.json()["data"]
        assert body["employee_id"] == str(pair.a.id)
        assert body["status"] == "pending"
        assert Decimal(body["days"]) == Decimal("2.0")

    async def test_applying_holds_the_balance(
        self, client: AsyncClient, alice: dict[str, str], leave_type: LeaveType
    ) -> None:
        start = MONDAY + timedelta(days=7)
        await client.post(
            f"{ME}/leave",
            json={
                "leave_type_id": str(leave_type.id),
                "from_date": start.isoformat(),
                "to_date": start.isoformat(),
                "reason": "Personal",
            },
            headers=alice,
        )

        rows = (await client.get(f"{ME}/leave/balance", headers=alice)).json()["data"]
        casual = next(row for row in rows if row["leave_type_id"] == str(leave_type.id))
        assert Decimal(casual["pending"]) == Decimal("1.0")
        assert Decimal(casual["available"]) == Decimal("11.0")

    async def test_an_employee_cannot_apply_for_somebody_else(
        self, client: AsyncClient, pair: Pair, bob: dict[str, str], leave_type: LeaveType
    ) -> None:
        """Two attempts, two different defences.

        Through ``/me`` the body is the workforce module's own ``LeaveApply``,
        which has no employee field: an ``employee_id`` in the JSON is not
        rejected, it is *not read*, and the request applies to the caller. That
        is asserted on the result rather than on a status code, because "the
        field was ignored" and "the field was honoured" both return 201 and only
        the employee on the created request tells them apart.

        Through the module's own URL the id is a path parameter, and there the
        existing guard refuses it outright.
        """
        start = MONDAY + timedelta(days=7)
        payload = {
            "leave_type_id": str(leave_type.id),
            "from_date": start.isoformat(),
            "to_date": start.isoformat(),
            "reason": "Not mine to take",
        }

        smuggled = await client.post(
            f"{ME}/leave", json={**payload, "employee_id": str(pair.a.id)}, headers=bob
        )
        assert smuggled.status_code == 201, smuggled.text
        assert smuggled.json()["data"]["employee_id"] == str(pair.b.id), "applied to the caller"

        direct = await client.post(f"{WORKFORCE}/leave/{pair.a.id}", json=payload, headers=bob)
        assert direct.status_code == 403, direct.text

        # And A's own portal shows nothing was filed on their behalf.
        alice_headers = await _sign_in(client, pair.a_user)
        assert (await client.get(f"{ME}/leave", headers=alice_headers)).json()["data"]["items"] == []

    async def test_an_employee_never_sees_another_employees_leave(
        self, client: AsyncClient, alice: dict[str, str], bob: dict[str, str], leave_type: LeaveType
    ) -> None:
        start = MONDAY + timedelta(days=7)
        await client.post(
            f"{ME}/leave",
            json={
                "leave_type_id": str(leave_type.id),
                "from_date": start.isoformat(),
                "to_date": start.isoformat(),
                "reason": "Personal",
            },
            headers=alice,
        )

        assert (await client.get(f"{ME}/leave", headers=bob)).json()["data"]["items"] == []
        assert len((await client.get(f"{ME}/leave", headers=alice)).json()["data"]["items"]) == 1

    async def test_cancelling_somebody_elses_request_is_refused(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        pair: Pair,
        bob: dict[str, str],
        leave_type: LeaveType,
    ) -> None:
        """The one place a ``/me`` route takes an id -- and it is checked."""
        request = LeaveRequest(
            employee_id=pair.a.id,
            leave_type_id=leave_type.id,
            from_date=MONDAY + timedelta(days=7),
            to_date=MONDAY + timedelta(days=7),
            days=Decimal("1.0"),
            reason="Personal",
            status=ApprovalStatus.PENDING.value,
        )
        db_session.add(request)
        await db_session.flush()

        response = await client.post(f"{ME}/leave/{request.id}/cancel", headers=bob)
        assert response.status_code == 403, response.text

    async def test_an_employee_cancels_their_own_request(
        self, client: AsyncClient, alice: dict[str, str], leave_type: LeaveType
    ) -> None:
        start = MONDAY + timedelta(days=7)
        created = await client.post(
            f"{ME}/leave",
            json={
                "leave_type_id": str(leave_type.id),
                "from_date": start.isoformat(),
                "to_date": start.isoformat(),
                "reason": "Personal",
            },
            headers=alice,
        )
        request_id = created.json()["data"]["id"]

        response = await client.post(f"{ME}/leave/{request_id}/cancel", headers=alice)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "cancelled"

    async def test_overlapping_leave_is_still_refused(
        self, client: AsyncClient, alice: dict[str, str], leave_type: LeaveType
    ) -> None:
        """The portal inherits the module's rules rather than restating them."""
        start = MONDAY + timedelta(days=7)
        payload = {
            "leave_type_id": str(leave_type.id),
            "from_date": start.isoformat(),
            "to_date": (start + timedelta(days=2)).isoformat(),
            "reason": "Personal",
        }
        assert (await client.post(f"{ME}/leave", json=payload, headers=alice)).status_code == 201

        clash = await client.post(f"{ME}/leave", json=payload, headers=alice)
        assert clash.status_code == 409
        assert clash.json()["errors"][0]["code"] == "overlapping_leave"


# ======================================================================
# 10-12: timesheets
# ======================================================================
class TestMyTimesheets:
    async def test_the_week_offers_only_my_allocations(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, alice: dict[str, str]
    ) -> None:
        mine = await _project_for(db_session, pair.a, start=MONDAY - timedelta(days=30))
        theirs = await _project_for(db_session, pair.b, start=MONDAY - timedelta(days=30))

        response = await client.get(f"{ME}/timesheets/current", headers=alice)
        assert response.status_code == 200, response.text

        offered = {row["project_id"] for row in response.json()["data"]["projects"]}
        assert str(mine.id) in offered
        assert str(theirs.id) not in offered

    async def test_an_employee_creates_and_submits_their_own_timesheet(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, alice: dict[str, str]
    ) -> None:
        project = await _project_for(db_session, pair.a, start=MONDAY - timedelta(days=30))

        saved = await client.post(
            f"{ME}/timesheets",
            json={
                "week_start_date": MONDAY.isoformat(),
                "entries": [
                    {
                        "project_id": str(project.id),
                        "work_date": MONDAY.isoformat(),
                        "task": "Implementation",
                        "hours": "8.00",
                        "billable": True,
                    }
                ],
            },
            headers=alice,
        )
        assert saved.status_code == 201, saved.text
        assert saved.json()["data"]["employee_id"] == str(pair.a.id)
        assert saved.json()["data"]["status"] == "draft"

        submitted = await client.post(f"{ME}/timesheets/{saved.json()['data']['id']}/submit", headers=alice)
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["data"]["status"] == "submitted"

    async def test_hours_cannot_be_booked_to_an_unallocated_project(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, alice: dict[str, str]
    ) -> None:
        theirs = await _project_for(db_session, pair.b, start=MONDAY - timedelta(days=30))

        response = await client.post(
            f"{ME}/timesheets",
            json={
                "week_start_date": MONDAY.isoformat(),
                "entries": [
                    {
                        "project_id": str(theirs.id),
                        "work_date": MONDAY.isoformat(),
                        "task": "Implementation",
                        "hours": "8.00",
                    }
                ],
            },
            headers=alice,
        )
        assert response.status_code == 409, response.text
        assert response.json()["errors"][0]["code"] == "not_allocated"

    async def test_hours_cannot_be_booked_outside_the_allocation_window(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, alice: dict[str, str]
    ) -> None:
        """Having once been on a project is not the same as being on it this week."""
        finished = await _project_for(
            db_session,
            pair.a,
            start=MONDAY - timedelta(days=60),
            end=MONDAY - timedelta(days=7),
        )

        response = await client.post(
            f"{ME}/timesheets",
            json={
                "week_start_date": MONDAY.isoformat(),
                "entries": [
                    {
                        "project_id": str(finished.id),
                        "work_date": MONDAY.isoformat(),
                        "task": "Implementation",
                        "hours": "8.00",
                    }
                ],
            },
            headers=alice,
        )
        assert response.status_code == 409, response.text
        assert response.json()["errors"][0]["code"] == "not_allocated"

    async def test_an_employee_never_sees_another_employees_timesheet(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        pair: Pair,
        alice: dict[str, str],
        bob: dict[str, str],
    ) -> None:
        project = await _project_for(db_session, pair.a, start=MONDAY - timedelta(days=30))
        saved = await client.post(
            f"{ME}/timesheets",
            json={
                "week_start_date": MONDAY.isoformat(),
                "entries": [
                    {
                        "project_id": str(project.id),
                        "work_date": MONDAY.isoformat(),
                        "task": "Implementation",
                        "hours": "8.00",
                    }
                ],
            },
            headers=alice,
        )
        timesheet_id = saved.json()["data"]["id"]

        assert (await client.get(f"{ME}/timesheets", headers=bob)).json()["data"]["items"] == []
        assert (await client.get(f"{ME}/timesheets/{timesheet_id}", headers=bob)).status_code == 403
        assert (await client.post(f"{ME}/timesheets/{timesheet_id}/submit", headers=bob)).status_code == 403

    async def test_a_submitted_week_is_not_edited(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, alice: dict[str, str]
    ) -> None:
        project = await _project_for(db_session, pair.a, start=MONDAY - timedelta(days=30))
        entries = [
            {
                "project_id": str(project.id),
                "work_date": MONDAY.isoformat(),
                "task": "Implementation",
                "hours": "8.00",
            }
        ]
        saved = await client.post(
            f"{ME}/timesheets",
            json={"week_start_date": MONDAY.isoformat(), "entries": entries},
            headers=alice,
        )
        await client.post(f"{ME}/timesheets/{saved.json()['data']['id']}/submit", headers=alice)

        again = await client.post(
            f"{ME}/timesheets",
            json={"week_start_date": MONDAY.isoformat(), "entries": entries},
            headers=alice,
        )
        assert again.status_code == 409
        assert again.json()["errors"][0]["code"] == "timesheet_locked"


# ======================================================================
# 13-14: documents
# ======================================================================
class TestMyDocuments:
    async def test_an_employee_uploads_their_own_document(
        self, client: AsyncClient, pair: Pair, alice: dict[str, str], document_type: DocumentType
    ) -> None:
        body = await _upload_my_document(client, alice, document_type)
        assert body["owner_type"] == "employee"
        assert body["owner_id"] == str(pair.a.id)
        assert body["status"] == "uploaded"
        assert body["can_replace"] is True

    async def test_an_upload_cannot_name_a_different_owner(
        self, client: AsyncClient, pair: Pair, bob: dict[str, str], document_type: DocumentType
    ) -> None:
        """The form field is ignored because the endpoint does not declare it.

        A multipart part that no parameter matches is simply not read, so the
        document is filed against the uploader -- the assertion that matters is
        the owner on the result, not the status code.
        """
        response = await client.post(
            f"{ME}/documents",
            data={
                "name": "Passport",
                "category_id": str(document_type.category_id),
                "document_type_id": str(document_type.id),
                "owner_id": str(pair.a.id),
                "owner_type": "employee",
            },
            files={"file": ("passport.pdf", PDF, "application/pdf")},
            headers=bob,
        )
        assert response.status_code == 201, response.text
        assert response.json()["data"]["owner_id"] == str(pair.b.id)

    async def test_an_employee_never_sees_another_employees_documents(
        self, client: AsyncClient, alice: dict[str, str], bob: dict[str, str], document_type: DocumentType
    ) -> None:
        mine = await _upload_my_document(client, alice, document_type)

        assert (await client.get(f"{ME}/documents", headers=bob)).json()["data"]["items"] == []
        for path in ("", "/download", "/preview"):
            response = await client.get(f"{ME}/documents/{mine['id']}{path}", headers=bob)
            assert response.status_code == 403, f"{path}: {response.text}"

    async def test_an_employee_downloads_their_own_document(
        self, client: AsyncClient, alice: dict[str, str], document_type: DocumentType
    ) -> None:
        mine = await _upload_my_document(client, alice, document_type)
        response = await client.get(f"{ME}/documents/{mine['id']}/download", headers=alice)

        assert response.status_code == 200, response.text
        assert response.content == PDF

    async def test_a_rejected_document_can_be_replaced(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        alice: dict[str, str],
        auth_headers: dict[str, str],
        document_type: DocumentType,
    ) -> None:
        """Upload, HR rejects with a reason, employee replaces it."""
        mine = await _upload_my_document(client, alice, document_type)

        reviewed = await client.post(
            f"{DOCUMENTS}/{mine['id']}/review",
            json={"status": "rejected", "review_notes": "The scan is unreadable."},
            headers=auth_headers,
        )
        assert reviewed.status_code == 200, reviewed.text

        seen = (await client.get(f"{ME}/documents/{mine['id']}", headers=alice)).json()["data"]
        assert seen["status"] == "rejected"
        assert seen["review_notes"] == "The scan is unreadable."
        assert seen["can_replace"] is True

        replaced = await client.post(
            f"{ME}/documents/{mine['id']}/replace",
            data={"notes": "Rescanned"},
            files={"file": ("passport.pdf", PDF + b"\n% v2\n", "application/pdf")},
            headers=alice,
        )
        assert replaced.status_code == 201, replaced.text
        assert replaced.json()["data"]["version_count"] == 2

    async def test_a_review_decision_reaches_the_employees_inbox(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        pair: Pair,
        alice: dict[str, str],
        auth_headers: dict[str, str],
        document_type: DocumentType,
    ) -> None:
        """Reuses the existing notification table rather than a new mechanism."""
        mine = await _upload_my_document(client, alice, document_type)
        await client.post(
            f"{DOCUMENTS}/{mine['id']}/review",
            json={"status": "approved"},
            headers=auth_headers,
        )

        rows = (
            (await db_session.execute(select(Notification).where(Notification.user_id == pair.a_user.id)))
            .scalars()
            .all()
        )
        assert any(row.notification_type == "document_approved" for row in rows)

    async def test_an_hr_issued_letter_is_readable_but_not_replaceable(
        self,
        client: AsyncClient,
        pair: Pair,
        alice: dict[str, str],
        auth_headers: dict[str, str],
        document_type: DocumentType,
    ) -> None:
        """An offer letter is the employee's to keep, not theirs to reissue."""
        issued = await client.post(
            DOCUMENTS,
            data={
                "name": "Offer Letter",
                "category_id": str(document_type.category_id),
                "document_type_id": str(document_type.id),
                "owner_type": "employee",
                "owner_id": str(pair.a.id),
            },
            files={"file": ("offer.pdf", PDF, "application/pdf")},
            headers=auth_headers,
        )
        assert issued.status_code == 201, issued.text
        document_id = issued.json()["data"]["id"]

        seen = await client.get(f"{ME}/documents/{document_id}", headers=alice)
        assert seen.status_code == 200
        assert seen.json()["data"]["can_replace"] is False

        refused = await client.post(
            f"{ME}/documents/{document_id}/replace",
            files={"file": ("offer.pdf", PDF + b"\n% mine\n", "application/pdf")},
            headers=alice,
        )
        assert refused.status_code == 409
        assert refused.json()["errors"][0]["code"] == "issued_document"

    async def test_the_upload_form_is_offered_real_types(
        self, client: AsyncClient, alice: dict[str, str], document_type: DocumentType
    ) -> None:
        response = await client.get(f"{ME}/documents/types", headers=alice)
        assert response.status_code == 200, response.text
        assert str(document_type.id) in {row["id"] for row in response.json()["data"]}


# ======================================================================
# 15-16: profile
# ======================================================================
class TestMyProfile:
    async def test_an_employee_updates_the_fields_they_own(
        self, client: AsyncClient, alice: dict[str, str]
    ) -> None:
        response = await client.patch(
            f"{ME}/profile",
            json={
                "personal_email": "Alice.Personal@Example.com",
                "mobile_number": "+91 90000 00001",
                "emergency_contact_name": "Next Of Kin",
                "emergency_contact_number": "+91 90000 00002",
                "emergency_contact_relationship": "Sibling",
            },
            headers=alice,
        )
        assert response.status_code == 200, response.text

        body = response.json()["data"]
        assert body["personal_email"] == "alice.personal@example.com"
        assert body["emergency_contact_relationship"] == "Sibling"

    async def test_an_employee_sets_their_own_address(
        self, client: AsyncClient, alice: dict[str, str]
    ) -> None:
        response = await client.put(
            f"{ME}/profile/address",
            json={
                "address_type": "current",
                "address_line1": "12 Residency Road",
                "city": "Hyderabad",
                "state": "Telangana",
                "country": "India",
                "postal_code": "500081",
            },
            headers=alice,
        )
        assert response.status_code == 200, response.text
        assert any(row["address_type"] == "current" for row in response.json()["data"]["addresses"])

    @pytest.mark.parametrize(
        "field,value",
        [
            ("team_id", "11111111-1111-1111-1111-111111111111"),
            ("designation_id", "11111111-1111-1111-1111-111111111111"),
            ("grade_id", "11111111-1111-1111-1111-111111111111"),
            ("reporting_manager_id", "11111111-1111-1111-1111-111111111111"),
            ("employment_status", "confirmed"),
            ("joining_date", "2020-01-01"),
            ("official_email", "new.official@jsan.example"),
            ("ctc", "9999999"),
            ("employee_code", "EMP-000999"),
        ],
    )
    async def test_a_protected_field_cannot_be_sent(
        self, client: AsyncClient, alice: dict[str, str], field: str, value: str
    ) -> None:
        """Refused as an unknown field, not silently dropped.

        ``extra="forbid"`` is what makes this a 422: an employee who tries to
        promote themselves is told the field does not exist, and nobody is left
        believing a change was applied that was not.
        """
        response = await client.patch(f"{ME}/profile", json={field: value}, headers=alice)
        assert response.status_code == 422, f"{field} should be rejected: {response.text}"

    async def test_a_protected_field_is_unchanged_after_an_allowed_edit(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, alice: dict[str, str]
    ) -> None:
        before = pair.a.employment_status
        await client.patch(f"{ME}/profile", json={"mobile_number": "+91 90000 00003"}, headers=alice)

        await db_session.refresh(pair.a)
        assert pair.a.employment_status == before
        assert pair.a.mobile_number == "+91 90000 00003"

    async def test_the_response_names_what_is_editable(
        self, client: AsyncClient, alice: dict[str, str]
    ) -> None:
        """So the form disables exactly what the server will refuse."""
        body = (await client.get(ME, headers=alice)).json()["data"]
        assert "personal_email" in body["editable_fields"]
        assert "team_id" not in body["editable_fields"]
        assert "employment_status" not in body["editable_fields"]

    async def test_an_employee_cannot_edit_another_employee_through_the_hr_route(
        self, client: AsyncClient, pair: Pair, bob: dict[str, str]
    ) -> None:
        response = await client.patch(
            f"{EMPLOYEES}/{pair.a.id}", json={"mobile_number": "+91 90000 00009"}, headers=bob
        )
        assert response.status_code == 403


# ======================================================================
# 17: projects and holidays
# ======================================================================
class TestMyProjectsAndHolidays:
    async def test_an_employee_sees_their_own_allocations(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, alice: dict[str, str]
    ) -> None:
        project = await _project_for(db_session, pair.a, start=MONDAY - timedelta(days=30))

        response = await client.get(f"{ME}/projects", headers=alice)
        assert response.status_code == 200, response.text

        rows = response.json()["data"]
        assert len(rows) == 1
        assert rows[0]["project_id"] == str(project.id)
        assert rows[0]["role"] == "Software Engineer"
        assert rows[0]["is_current"] is True
        assert rows[0]["client_name"]

    async def test_an_employee_does_not_see_another_employees_allocations(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, bob: dict[str, str]
    ) -> None:
        await _project_for(db_session, pair.a, start=MONDAY - timedelta(days=30))
        assert (await client.get(f"{ME}/projects", headers=bob)).json()["data"] == []

    async def test_holidays_are_scoped_to_the_employees_location(
        self, client: AsyncClient, db_session: AsyncSession, alice: dict[str, str]
    ) -> None:
        """A calendar with no location applies everywhere; another location's does not."""
        from app.models.location import Location
        from app.models.workforce import Holiday

        elsewhere = Location(
            name=f"Chennai {uuid.uuid4().hex[:4]}",
            code=f"MAA{uuid.uuid4().hex[:4].upper()}",
            country="India",
            state="Tamil Nadu",
            city="Chennai",
            address="Guindy",
            timezone="Asia/Kolkata",
            status=RecordStatus.ACTIVE,
        )
        db_session.add(elsewhere)
        await db_session.flush()

        everywhere = HolidayCalendar(
            name=f"National {uuid.uuid4().hex[:4]}", year=TODAY.year, status=RecordStatus.ACTIVE
        )
        local = HolidayCalendar(
            name=f"Chennai only {uuid.uuid4().hex[:4]}",
            year=TODAY.year,
            location_id=elsewhere.id,
            status=RecordStatus.ACTIVE,
        )
        db_session.add_all([everywhere, local])
        await db_session.flush()

        db_session.add_all(
            [
                Holiday(
                    calendar_id=everywhere.id,
                    name="Republic Day",
                    holiday_date=date(TODAY.year, 1, 26),
                    holiday_type="public",
                ),
                Holiday(
                    calendar_id=local.id,
                    name="Pongal",
                    holiday_date=date(TODAY.year, 1, 15),
                    holiday_type="public",
                ),
            ]
        )
        await db_session.flush()

        names = {row["name"] for row in (await client.get(f"{ME}/holidays", headers=alice)).json()["data"]}
        assert "Republic Day" in names
        assert "Pongal" not in names

        # Somebody actually placed in Chennai gets both: theirs and the national one.
        local_user = await _account(db_session, "chennai")
        await _employee_for(db_session, local_user, "chennai", location_id=elsewhere.id)
        local_headers = await _sign_in(client, local_user)

        theirs = {
            row["name"] for row in (await client.get(f"{ME}/holidays", headers=local_headers)).json()["data"]
        }
        assert {"Republic Day", "Pongal"} <= theirs


# ======================================================================
# Dashboard
# ======================================================================
class TestMyDashboard:
    async def test_the_dashboard_is_about_the_caller_only(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        pair: Pair,
        alice: dict[str, str],
        leave_type: LeaveType,
    ) -> None:
        await _project_for(db_session, pair.a, start=MONDAY - timedelta(days=30))
        await _project_for(db_session, pair.b, start=MONDAY - timedelta(days=30))
        db_session.add(AttendanceRecord(employee_id=pair.b.id, attendance_date=TODAY, status="present"))
        await db_session.flush()

        response = await client.get(f"{ME}/dashboard", headers=alice)
        assert response.status_code == 200, response.text

        body = response.json()["data"]
        assert body["employee"]["id"] == str(pair.a.id)
        assert {row["project_id"] for row in body["projects"]} == {
            row["project_id"] for row in (await client.get(f"{ME}/projects", headers=alice)).json()["data"]
        }
        # B checked in, A did not: the dashboard is not a company figure.
        assert body["attendance"]["checked_in"] is False
        assert body["month_summary"]["present_days"] == 0

    async def test_the_dashboard_lists_what_is_outstanding(
        self, client: AsyncClient, alice: dict[str, str]
    ) -> None:
        body = (await client.get(f"{ME}/dashboard", headers=alice)).json()["data"]
        codes = {action["code"] for action in body["pending_actions"]}
        assert "check_in" in codes
        assert "timesheet_missing" in codes

    async def test_the_dashboard_survives_a_non_empty_inbox(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, alice: dict[str, str]
    ) -> None:
        """The regression that shipped: ``MyNotification`` declares ``is_read``
        and the model only had ``read_at``, so the first dashboard read by
        anybody who actually *had* a notification was a 422. Every prior test
        read the dashboard over an empty inbox, which is a measurement of
        nothing -- this one puts a row in first.
        """
        db_session.add(
            Notification(
                user_id=pair.a.user_id,
                title="Your request was resolved",
                message="TKT-000001 has been resolved.",
                link="/employee/helpdesk",
                notification_type="helpdesk",
            )
        )
        await db_session.flush()

        response = await client.get(f"{ME}/dashboard", headers=alice)
        assert response.status_code == 200, response.text
        rows = response.json()["data"]["recent_notifications"]
        assert any(row["title"] == "Your request was resolved" for row in rows)
        assert all(row["is_read"] is False for row in rows)

        await client.post(f"{ME}/attendance/check-in", json={}, headers=alice)
        after = (await client.get(f"{ME}/dashboard", headers=alice)).json()["data"]
        assert "check_in" not in {action["code"] for action in after["pending_actions"]}
        assert "check_out" in {action["code"] for action in after["pending_actions"]}


# ======================================================================
# 18-20: nothing that already worked stopped working
# ======================================================================
class TestExistingAccessIsUnaffected:
    async def test_a_manager_still_approves_for_their_direct_report(
        self,
        client: AsyncClient,
        pair: Pair,
        alice: dict[str, str],
        manager_headers: dict[str, str],
        leave_type: LeaveType,
    ) -> None:
        start = MONDAY + timedelta(days=7)
        applied = await client.post(
            f"{ME}/leave",
            json={
                "leave_type_id": str(leave_type.id),
                "from_date": start.isoformat(),
                "to_date": start.isoformat(),
                "reason": "Personal",
            },
            headers=alice,
        )
        request_id = applied.json()["data"]["id"]

        decided = await client.post(
            f"{WORKFORCE}/leave/{request_id}/decide",
            json={"approved": True, "notes": "Fine"},
            headers=manager_headers,
        )
        assert decided.status_code == 200, decided.text
        assert decided.json()["data"]["status"] == "approved"

    async def test_a_manager_still_sees_their_team_and_not_the_company(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, manager_headers: dict[str, str]
    ) -> None:
        db_session.add_all(
            [
                AttendanceRecord(employee_id=pair.a.id, attendance_date=TODAY, status="present"),
                AttendanceRecord(employee_id=pair.b.id, attendance_date=TODAY, status="present"),
            ]
        )
        await db_session.flush()

        rows = (await client.get(f"{WORKFORCE}/attendance", headers=manager_headers)).json()["data"]["items"]
        visible = {row["employee_id"] for row in rows}
        assert str(pair.a.id) in visible, "a manager sees their direct report"
        assert str(pair.b.id) not in visible, "and nobody else's"

    async def test_a_managers_own_portal_is_still_only_their_own(
        self, client: AsyncClient, db_session: AsyncSession, pair: Pair, manager_headers: dict[str, str]
    ) -> None:
        """``/me`` narrows to self even for somebody whose scope includes reports.

        Without ``just_self`` a manager's personal attendance page would quietly
        include their team's rows, which is a different screen entirely.
        """
        db_session.add(AttendanceRecord(employee_id=pair.a.id, attendance_date=TODAY, status="present"))
        await db_session.flush()

        rows = (await client.get(f"{ME}/attendance", headers=manager_headers)).json()["data"]["items"]
        assert str(pair.a.id) not in {row["employee_id"] for row in rows}

    async def test_hr_and_admin_routes_still_work(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        for path in (EMPLOYEES, f"{WORKFORCE}/attendance", f"{WORKFORCE}/leave", DOCUMENTS):
            response = await client.get(path, headers=auth_headers)
            assert response.status_code == 200, f"{path}: {response.text}"

    async def test_a_superusers_portal_is_still_only_their_own(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict[str, str],
    ) -> None:
        """Unrestricted scope must not turn a personal page into a company one."""
        employee = await _employee_for(db_session, test_user, "root")
        other_user = await _account(db_session, "someone")
        other = await _employee_for(db_session, other_user, "someone")

        db_session.add_all(
            [
                AttendanceRecord(employee_id=employee.id, attendance_date=TODAY, status="present"),
                AttendanceRecord(employee_id=other.id, attendance_date=TODAY, status="present"),
            ]
        )
        await db_session.flush()

        rows = (await client.get(f"{ME}/attendance", headers=auth_headers)).json()["data"]["items"]
        visible = {row["employee_id"] for row in rows}
        assert visible == {str(employee.id)}

    async def test_the_vault_still_refuses_a_stranger_through_its_own_route(
        self, client: AsyncClient, alice: dict[str, str], bob: dict[str, str], document_type: DocumentType
    ) -> None:
        mine = await _upload_my_document(client, alice, document_type)
        assert (await client.get(f"{DOCUMENTS}/{mine['id']}", headers=bob)).status_code == 403
