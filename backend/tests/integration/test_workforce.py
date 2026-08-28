"""Integration tests for Workforce Operations.

The four rules the module rests on are the ones defended here: a day belongs to
one attendance record, leave is counted in working days, balance is held then
spent, and a submitted timesheet is not edited. Each is the kind of rule a later
refactor can break without any signature changing.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.employee import Employee
from app.models.project import Client, EmployeeAllocation, Project, ProjectMember

pytestmark = pytest.mark.integration

BASE = f"{settings.API_V1_PREFIX}/workforce"

TODAY = date.today()
#: A fixed Monday, so "Friday to Monday" means the same thing on every run.
MONDAY = TODAY - timedelta(days=TODAY.weekday() + 14)
FRIDAY = MONDAY - timedelta(days=3)
#: Leave already taken cannot be cancelled, so cancellation is tested ahead of today.
NEXT_MONDAY = TODAY + timedelta(days=7 - TODAY.weekday())


def shift_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Test General",
        "code": f"TG{TODAY.strftime('%d%H')}",
        "shift_type": "general",
        "start_time": "09:30:00",
        "end_time": "18:30:00",
        "grace_minutes": 15,
        "break_minutes": 60,
        "weekly_off": [5, 6],
    }
    payload.update(overrides)
    return payload


def leave_payload(leave_type_id: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "leave_type_id": leave_type_id,
        "from_date": MONDAY.isoformat(),
        "to_date": MONDAY.isoformat(),
        "reason": "Personal work at home.",
    }
    payload.update(overrides)
    return payload


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
async def casual_leave(client: AsyncClient, auth_headers: dict[str, str]) -> dict[str, Any]:
    """The seeded Casual Leave type -- twelve days, no carry forward."""
    response = await client.get(f"{BASE}/leave/types", headers=auth_headers)
    assert response.status_code == 200, response.text
    types = {row["code"]: row for row in response.json()["data"]}
    assert "CL" in types, "migration 0014 should seed the statutory leave types"
    return types["CL"]


@pytest.fixture
async def shift(client: AsyncClient, auth_headers: dict[str, str]) -> dict[str, Any]:
    created = await client.post(f"{BASE}/shifts", json=shift_payload(), headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()["data"]


@pytest.fixture
async def project_id(db_session: AsyncSession, employee: Employee) -> str:
    """A project the employee is allocated to -- hours cannot be booked otherwise."""
    client_record = Client(
        client_name=f"Northwind {uuid.uuid4().hex[:6]}",
        company_name="Northwind Traders Pvt Ltd",
        industry="Retail",
        contact_person="Asha Menon",
        email="asha@northwind.example",
        phone="+91 90000 00000",
        country="India",
        address="Level 4, Prestige Tech Park, Bengaluru",
    )
    db_session.add(client_record)
    await db_session.flush()

    project = Project(
        project_name="Order Management Revamp",
        client_id=client_record.id,
        description="Rebuild the order management workflow.",
        start_date=TODAY - timedelta(days=120),
        status="active",
        project_manager_id=employee.id,
    )
    db_session.add(project)
    await db_session.flush()

    member = ProjectMember(
        project_id=project.id, employee_id=employee.id, role="Engineer", joined_at=TODAY - timedelta(days=90)
    )
    db_session.add(member)
    await db_session.flush()

    db_session.add(
        EmployeeAllocation(
            employee_id=employee.id,
            project_id=project.id,
            member_id=member.id,
            allocation_percentage=Decimal("100.00"),
            start_date=TODAY - timedelta(days=90),
        )
    )
    await db_session.flush()
    return str(project.id)


@pytest.fixture
async def timesheet(
    client: AsyncClient, auth_headers: dict[str, str], employee: Employee, project_id: str
) -> dict[str, Any]:
    saved = await client.post(
        f"{BASE}/timesheets/{employee.id}",
        json={
            "week_start_date": MONDAY.isoformat(),
            "entries": [
                {
                    "project_id": project_id,
                    "work_date": (MONDAY + timedelta(days=offset)).isoformat(),
                    "task": "Order service",
                    "hours": "8.00",
                }
                for offset in range(5)
            ],
        },
        headers=auth_headers,
    )
    assert saved.status_code == 201, saved.text
    return saved.json()["data"]


@pytest.fixture
async def on_shift(
    client: AsyncClient, auth_headers: dict[str, str], employee: Employee, shift: dict[str, Any]
) -> dict[str, Any]:
    assigned = await client.post(
        f"{BASE}/shifts/assign",
        json={
            "employee_id": str(employee.id),
            "shift_id": shift["id"],
            "effective_from": (TODAY - timedelta(days=90)).isoformat(),
        },
        headers=auth_headers,
    )
    assert assigned.status_code == 201, assigned.text
    return assigned.json()["data"]


# ----------------------------------------------------------------------
class TestAuthentication:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/dashboard"),
            ("get", "/shifts"),
            ("post", "/shifts"),
            ("get", "/attendance"),
            ("get", "/leave"),
            ("get", "/leave/types"),
            ("get", "/timesheets"),
            ("get", "/holidays"),
        ],
    )
    async def test_every_route_needs_a_token(self, client: AsyncClient, method: str, path: str) -> None:
        call = getattr(client, method)
        response = await call(f"{BASE}{path}") if method == "get" else await call(f"{BASE}{path}", json={})
        assert response.status_code == 401


# ----------------------------------------------------------------------
class TestShifts:
    async def test_a_shift_code_is_unique(
        self, client: AsyncClient, auth_headers: dict[str, str], shift: dict[str, Any]
    ) -> None:
        duplicate = await client.post(
            f"{BASE}/shifts", json=shift_payload(name="Another"), headers=auth_headers
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["errors"][0]["code"] == "duplicate_code"

    async def test_a_shift_cannot_have_every_day_off(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            f"{BASE}/shifts",
            json=shift_payload(code="ALLOFF", weekly_off=[0, 1, 2, 3, 4, 5, 6]),
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_assigning_a_shift_closes_the_previous_one(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        on_shift: dict[str, Any],
    ) -> None:
        """History is what an old attendance record is read against."""
        second = await client.post(
            f"{BASE}/shifts", json=shift_payload(name="Test Night", code="TN01"), headers=auth_headers
        )
        assert second.status_code == 201

        moved = await client.post(
            f"{BASE}/shifts/assign",
            json={
                "employee_id": str(employee.id),
                "shift_id": second.json()["data"]["id"],
                "effective_from": (TODAY - timedelta(days=30)).isoformat(),
            },
            headers=auth_headers,
        )
        assert moved.status_code == 201, moved.text

        history = await client.get(f"{BASE}/shifts/history/{employee.id}", headers=auth_headers)
        rows = history.json()["data"]
        assert len(rows) == 2, "the earlier assignment must survive, not be overwritten"
        closed = next(row for row in rows if row["id"] == on_shift["id"])
        assert closed["effective_to"] == (TODAY - timedelta(days=31)).isoformat()

    async def test_reassigning_the_same_shift_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, on_shift: dict[str, Any]
    ) -> None:
        repeat = await client.post(
            f"{BASE}/shifts/assign",
            json={
                "employee_id": str(employee.id),
                "shift_id": on_shift["shift_id"],
                "effective_from": TODAY.isoformat(),
            },
            headers=auth_headers,
        )
        assert repeat.status_code == 409
        assert repeat.json()["errors"][0]["code"] == "already_on_shift"


# ----------------------------------------------------------------------
class TestAttendance:
    async def test_a_day_belongs_to_one_record(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, on_shift: dict[str, Any]
    ) -> None:
        first = await client.post(
            f"{BASE}/attendance/{employee.id}/check-in", json={"work_mode": "office"}, headers=auth_headers
        )
        assert first.status_code == 201, first.text

        second = await client.post(
            f"{BASE}/attendance/{employee.id}/check-in", json={"work_mode": "office"}, headers=auth_headers
        )
        assert second.status_code == 409, "a second check-in on the same day must be refused"

    async def test_check_out_records_the_hours_worked(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, on_shift: dict[str, Any]
    ) -> None:
        await client.post(
            f"{BASE}/attendance/{employee.id}/check-in", json={"work_mode": "office"}, headers=auth_headers
        )
        out = await client.post(f"{BASE}/attendance/{employee.id}/check-out", json={}, headers=auth_headers)
        assert out.status_code == 200, out.text
        record = out.json()["data"]
        assert record["check_out_at"] is not None
        assert record["worked_minutes"] >= 0

    async def test_check_out_without_check_in_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.post(
            f"{BASE}/attendance/{employee.id}/check-out", json={}, headers=auth_headers
        )
        assert response.status_code in {404, 409}

    async def test_attendance_cannot_be_marked_for_a_future_day(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        """A record for tomorrow is a prediction, not attendance."""
        response = await client.post(
            f"{BASE}/attendance/{employee.id}/check-in",
            json={"work_mode": "office", "attendance_date": (TODAY + timedelta(days=1)).isoformat()},
            headers=auth_headers,
        )
        assert response.status_code in {409, 422}


# ----------------------------------------------------------------------
class TestRegularization:
    async def test_approval_amends_the_attendance_record(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, on_shift: dict[str, Any]
    ) -> None:
        marked = await client.post(
            f"{BASE}/attendance/{employee.id}/check-in",
            json={"work_mode": "office", "attendance_date": MONDAY.isoformat()},
            headers=auth_headers,
        )
        assert marked.status_code == 201, marked.text

        corrected_out = f"{MONDAY.isoformat()}T18:45:00+05:30"
        requested = await client.post(
            f"{BASE}/regularizations/{employee.id}",
            json={
                "attendance_date": MONDAY.isoformat(),
                "requested_check_out_at": corrected_out,
                "reason": "Forgot to tap out at the end of the day.",
            },
            headers=auth_headers,
        )
        assert requested.status_code == 201, requested.text
        request_id = requested.json()["data"]["id"]

        decided = await client.post(
            f"{BASE}/regularizations/{request_id}/decide",
            json={"approved": True, "notes": "Confirmed with the team lead."},
            headers=auth_headers,
        )
        assert decided.status_code == 200, decided.text
        assert decided.json()["data"]["status"] == "approved"

        listed = await client.get(
            f"{BASE}/attendance",
            params={"employee_id": str(employee.id), "from_date": MONDAY.isoformat()},
            headers=auth_headers,
        )
        record = listed.json()["data"]["items"][0]
        assert record["check_out_at"] is not None, "approving is what amends the record"

    async def test_a_decided_request_is_not_decided_twice(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, on_shift: dict[str, Any]
    ) -> None:
        await client.post(
            f"{BASE}/attendance/{employee.id}/check-in",
            json={"work_mode": "office", "attendance_date": MONDAY.isoformat()},
            headers=auth_headers,
        )
        requested = await client.post(
            f"{BASE}/regularizations/{employee.id}",
            json={
                "attendance_date": MONDAY.isoformat(),
                "requested_check_out_at": f"{MONDAY.isoformat()}T18:45:00+05:30",
                "reason": "Forgot to tap out.",
            },
            headers=auth_headers,
        )
        request_id = requested.json()["data"]["id"]
        await client.post(
            f"{BASE}/regularizations/{request_id}/decide", json={"approved": False}, headers=auth_headers
        )
        again = await client.post(
            f"{BASE}/regularizations/{request_id}/decide", json={"approved": True}, headers=auth_headers
        )
        assert again.status_code == 409


# ----------------------------------------------------------------------
class TestLeave:
    async def test_balances_are_created_on_first_read(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, casual_leave: dict
    ) -> None:
        response = await client.get(f"{BASE}/leave/balances/{employee.id}", headers=auth_headers)
        assert response.status_code == 200, response.text
        balances = {row["leave_type_id"]: row for row in response.json()["data"]}
        casual = balances[casual_leave["id"]]
        assert Decimal(casual["allocated"]) == Decimal("12.0")
        assert Decimal(casual["remaining"]) == Decimal("12.0")

    async def test_unused_days_carry_forward_up_to_the_policy_cap(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        db_session: AsyncSession,
    ) -> None:
        """The two policy fields the audit found write-only, doing their job:
        a carry-forward type moves last year's unused days into this year's
        ``opening_balance``, capped at ``max_carry_forward``; a non-carrying
        type starts the year at zero regardless of what was left.
        """
        from app.models.workforce import LeaveBalance, LeaveType

        this_year = date.today().year
        carrying = LeaveType(
            name="Earned Leave (test)",
            code=f"EL{uuid.uuid4().hex[:5].upper()}",
            annual_allocation=Decimal("18.0"),
            carry_forward=True,
            max_carry_forward=Decimal("5.0"),
        )
        strict = LeaveType(
            name="Use-it-or-lose-it (test)",
            code=f"UL{uuid.uuid4().hex[:5].upper()}",
            annual_allocation=Decimal("6.0"),
            carry_forward=False,
        )
        db_session.add_all([carrying, strict])
        await db_session.flush()
        # Last year: 8 unused days on the carrying type (> the 5-day cap),
        # 6 unused on the strict one.
        db_session.add_all(
            [
                LeaveBalance(
                    employee_id=employee.id,
                    leave_type_id=carrying.id,
                    year=this_year - 1,
                    allocated=Decimal("18.0"),
                    used=Decimal("10.0"),
                ),
                LeaveBalance(
                    employee_id=employee.id,
                    leave_type_id=strict.id,
                    year=this_year - 1,
                    allocated=Decimal("6.0"),
                ),
            ]
        )
        await db_session.flush()

        response = await client.get(f"{BASE}/leave/balances/{employee.id}", headers=auth_headers)
        assert response.status_code == 200, response.text
        balances = {row["leave_type_id"]: row for row in response.json()["data"]}

        carried = balances[str(carrying.id)]
        assert Decimal(carried["opening_balance"]) == Decimal("5.0"), "capped at max_carry_forward"
        assert Decimal(carried["remaining"]) == Decimal("23.0")

        lost = balances[str(strict.id)]
        assert Decimal(lost["opening_balance"]) == Decimal("0.0"), "no carry_forward, no carry"

    async def test_a_mid_year_joiner_is_prorated_when_the_policy_asks(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        db_session: AsyncSession,
    ) -> None:
        """``prorate_on_joining`` counts whole months remaining, joining month
        included. The fixture employee joins 15 January, so a January joiner
        keeps the full year and the proration path is exercised by moving the
        joining date to July: 6 of 12 months -> half the allocation.
        """
        from app.models.workforce import LeaveType

        this_year = date.today().year
        employee.joining_date = date(this_year, 7, 20)
        prorated_type = LeaveType(
            name="Prorated Leave (test)",
            code=f"PL{uuid.uuid4().hex[:5].upper()}",
            annual_allocation=Decimal("12.0"),
            prorate_on_joining=True,
        )
        db_session.add(prorated_type)
        await db_session.flush()

        response = await client.get(f"{BASE}/leave/balances/{employee.id}", headers=auth_headers)
        assert response.status_code == 200, response.text
        balances = {row["leave_type_id"]: row for row in response.json()["data"]}
        assert Decimal(balances[str(prorated_type.id)]["allocated"]) == Decimal("6.0")

    async def test_weekends_are_not_charged_as_leave(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, casual_leave: dict
    ) -> None:
        """Friday to Monday costs two days, not four."""
        applied = await client.post(
            f"{BASE}/leave/{employee.id}",
            json=leave_payload(casual_leave["id"], from_date=FRIDAY.isoformat(), to_date=MONDAY.isoformat()),
            headers=auth_headers,
        )
        assert applied.status_code == 201, applied.text
        assert Decimal(applied.json()["data"]["days"]) == 2

    async def test_a_half_day_costs_half_a_day(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, casual_leave: dict
    ) -> None:
        applied = await client.post(
            f"{BASE}/leave/{employee.id}",
            json=leave_payload(casual_leave["id"], day_part="first_half"),
            headers=auth_headers,
        )
        assert applied.status_code == 201, applied.text
        assert Decimal(applied.json()["data"]["days"]) == Decimal("0.5")

    async def test_balance_is_held_on_apply_and_spent_on_approve(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, casual_leave: dict
    ) -> None:
        applied = await client.post(
            f"{BASE}/leave/{employee.id}", json=leave_payload(casual_leave["id"]), headers=auth_headers
        )
        assert applied.status_code == 201, applied.text
        request_id = applied.json()["data"]["id"]

        held = await self._balance(client, auth_headers, employee, casual_leave)
        assert Decimal(held["pending"]) == Decimal("1.0"), "applying holds the days"
        assert Decimal(held["used"]) == Decimal("0.0")
        assert Decimal(held["remaining"]) == Decimal("11.0")

        decided = await client.post(
            f"{BASE}/leave/{request_id}/decide", json={"approved": True}, headers=auth_headers
        )
        assert decided.status_code == 200, decided.text

        spent = await self._balance(client, auth_headers, employee, casual_leave)
        assert Decimal(spent["pending"]) == Decimal("0.0")
        assert Decimal(spent["used"]) == Decimal("1.0"), "approving spends what was held"
        assert Decimal(spent["remaining"]) == Decimal("11.0")

    async def test_rejecting_releases_the_held_balance(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, casual_leave: dict
    ) -> None:
        applied = await client.post(
            f"{BASE}/leave/{employee.id}", json=leave_payload(casual_leave["id"]), headers=auth_headers
        )
        request_id = applied.json()["data"]["id"]
        await client.post(
            f"{BASE}/leave/{request_id}/decide",
            json={"approved": False, "notes": "Delivery week."},
            headers=auth_headers,
        )
        released = await self._balance(client, auth_headers, employee, casual_leave)
        assert Decimal(released["pending"]) == Decimal("0.0")
        assert Decimal(released["used"]) == Decimal("0.0")
        assert Decimal(released["remaining"]) == Decimal("12.0")

    async def test_cancelling_releases_the_held_balance(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, casual_leave: dict
    ) -> None:
        applied = await client.post(
            f"{BASE}/leave/{employee.id}",
            json=leave_payload(
                casual_leave["id"],
                from_date=NEXT_MONDAY.isoformat(),
                to_date=NEXT_MONDAY.isoformat(),
            ),
            headers=auth_headers,
        )
        assert applied.status_code == 201, applied.text
        cancelled = await client.post(
            f"{BASE}/leave/{applied.json()['data']['id']}/cancel", headers=auth_headers
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["data"]["status"] == "cancelled"

        released = await self._balance(client, auth_headers, employee, casual_leave)
        assert Decimal(released["remaining"]) == Decimal("12.0")

    async def test_overlapping_leave_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, casual_leave: dict
    ) -> None:
        """The held balance is only meaningful if two requests cannot claim the same day."""
        first = await client.post(
            f"{BASE}/leave/{employee.id}",
            json=leave_payload(
                casual_leave["id"],
                from_date=MONDAY.isoformat(),
                to_date=(MONDAY + timedelta(days=2)).isoformat(),
            ),
            headers=auth_headers,
        )
        assert first.status_code == 201, first.text

        overlapping = await client.post(
            f"{BASE}/leave/{employee.id}",
            json=leave_payload(
                casual_leave["id"],
                from_date=(MONDAY + timedelta(days=1)).isoformat(),
                to_date=(MONDAY + timedelta(days=3)).isoformat(),
            ),
            headers=auth_headers,
        )
        assert overlapping.status_code == 409

    async def test_a_request_beyond_the_balance_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, casual_leave: dict
    ) -> None:
        response = await client.post(
            f"{BASE}/leave/{employee.id}",
            json=leave_payload(
                casual_leave["id"],
                from_date=MONDAY.isoformat(),
                to_date=(MONDAY + timedelta(days=60)).isoformat(),
            ),
            headers=auth_headers,
        )
        assert response.status_code == 409

    async def test_leave_cannot_end_before_it_starts(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, casual_leave: dict
    ) -> None:
        response = await client.post(
            f"{BASE}/leave/{employee.id}",
            json=leave_payload(
                casual_leave["id"],
                from_date=MONDAY.isoformat(),
                to_date=(MONDAY - timedelta(days=1)).isoformat(),
            ),
            headers=auth_headers,
        )
        assert response.status_code == 422

    @staticmethod
    async def _balance(
        client: AsyncClient, headers: dict[str, str], employee: Employee, leave_type: dict
    ) -> dict[str, Any]:
        response = await client.get(f"{BASE}/leave/balances/{employee.id}", headers=headers)
        assert response.status_code == 200, response.text
        return next(row for row in response.json()["data"] if row["leave_type_id"] == leave_type["id"])


# ----------------------------------------------------------------------
class TestHolidays:
    async def test_a_holiday_is_not_charged_as_leave(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, casual_leave: dict
    ) -> None:
        holiday = MONDAY + timedelta(days=1)
        created = await client.post(
            f"{BASE}/holidays",
            json={
                "name": f"Test Calendar {MONDAY.year}",
                "year": MONDAY.year,
                "holidays": [
                    {"name": "Founders Day", "holiday_date": holiday.isoformat(), "holiday_type": "public"}
                ],
            },
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text

        applied = await client.post(
            f"{BASE}/leave/{employee.id}",
            json=leave_payload(
                casual_leave["id"],
                from_date=MONDAY.isoformat(),
                to_date=(MONDAY + timedelta(days=2)).isoformat(),
            ),
            headers=auth_headers,
        )
        assert applied.status_code == 201, applied.text
        assert Decimal(applied.json()["data"]["days"]) == 2, "the holiday in the middle is free"

    async def test_the_same_date_cannot_appear_twice(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            f"{BASE}/holidays",
            json={
                "name": "Duplicate Calendar",
                "year": MONDAY.year,
                "holidays": [
                    {"name": "One", "holiday_date": MONDAY.isoformat()},
                    {"name": "Two", "holiday_date": MONDAY.isoformat()},
                ],
            },
            headers=auth_headers,
        )
        assert response.status_code == 422


# ----------------------------------------------------------------------
class TestTimesheets:
    async def test_a_week_must_start_on_a_monday(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.post(
            f"{BASE}/timesheets/{employee.id}",
            json={"week_start_date": (MONDAY + timedelta(days=1)).isoformat(), "entries": []},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_a_day_cannot_hold_more_than_twenty_four_hours(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, project_id: str
    ) -> None:
        response = await client.post(
            f"{BASE}/timesheets/{employee.id}",
            json={
                "week_start_date": MONDAY.isoformat(),
                "entries": [
                    {
                        "project_id": project_id,
                        "work_date": MONDAY.isoformat(),
                        "task": "Build",
                        "hours": "13.00",
                    },
                    {
                        "project_id": project_id,
                        "work_date": MONDAY.isoformat(),
                        "task": "Review",
                        "hours": "12.00",
                    },
                ],
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_the_same_task_cannot_be_booked_twice_on_a_day(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, project_id: str
    ) -> None:
        response = await client.post(
            f"{BASE}/timesheets/{employee.id}",
            json={
                "week_start_date": MONDAY.isoformat(),
                "entries": [
                    {
                        "project_id": project_id,
                        "work_date": MONDAY.isoformat(),
                        "task": "Build",
                        "hours": "4.00",
                    },
                    {
                        "project_id": project_id,
                        "work_date": MONDAY.isoformat(),
                        "task": "Build",
                        "hours": "3.00",
                    },
                ],
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_entries_must_fall_inside_the_week(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, project_id: str
    ) -> None:
        response = await client.post(
            f"{BASE}/timesheets/{employee.id}",
            json={
                "week_start_date": MONDAY.isoformat(),
                "entries": [
                    {
                        "project_id": project_id,
                        "work_date": (MONDAY + timedelta(days=9)).isoformat(),
                        "task": "Build",
                        "hours": "4.00",
                    }
                ],
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_a_submitted_timesheet_is_not_edited(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee, timesheet: dict
    ) -> None:
        submitted = await client.post(f"{BASE}/timesheets/{timesheet['id']}/submit", headers=auth_headers)
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["data"]["status"] == "submitted"

        edited = await client.post(
            f"{BASE}/timesheets/{employee.id}",
            json={"week_start_date": MONDAY.isoformat(), "entries": []},
            headers=auth_headers,
        )
        assert edited.status_code == 409, "an approver must be looking at what they were shown"

    async def test_a_rejected_timesheet_can_be_corrected(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        project_id: str,
        timesheet: dict,
    ) -> None:
        """Rejection is a state the employee sees; saving is what reopens it."""
        await client.post(f"{BASE}/timesheets/{timesheet['id']}/submit", headers=auth_headers)
        rejected = await client.post(
            f"{BASE}/timesheets/{timesheet['id']}/decide",
            json={"approved": False, "notes": "Friday is missing."},
            headers=auth_headers,
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["data"]["status"] == "rejected"
        assert rejected.json()["data"]["decision_notes"] == "Friday is missing."

        corrected = await client.post(
            f"{BASE}/timesheets/{employee.id}",
            json={
                "week_start_date": MONDAY.isoformat(),
                "entries": [
                    {
                        "project_id": project_id,
                        "work_date": (MONDAY + timedelta(days=offset)).isoformat(),
                        "task": "Order service",
                        "hours": "8.00",
                    }
                    for offset in range(5)
                ],
            },
            headers=auth_headers,
        )
        assert corrected.status_code == 201, corrected.text
        assert corrected.json()["data"]["status"] == "draft", "saving reopens the week"

    async def test_an_unsubmitted_timesheet_cannot_be_approved(
        self, client: AsyncClient, auth_headers: dict[str, str], timesheet: dict
    ) -> None:
        response = await client.post(
            f"{BASE}/timesheets/{timesheet['id']}/decide", json={"approved": True}, headers=auth_headers
        )
        assert response.status_code == 409


# ----------------------------------------------------------------------
class TestDashboards:
    async def test_the_dashboard_answers(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        response = await client.get(f"{BASE}/dashboard", headers=auth_headers)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert set(data) >= {"present", "absent", "on_leave", "headcount"}
        assert isinstance(data["by_work_mode"], list)

    async def test_the_calendar_covers_the_month(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.get(
            f"{BASE}/calendar/{employee.id}",
            params={"year": MONDAY.year, "month": MONDAY.month},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        days = response.json()["data"]
        assert 28 <= len(days) <= 31

    @pytest.mark.parametrize("fmt", ["csv", "xlsx", "pdf"])
    async def test_a_report_exports(
        self, client: AsyncClient, auth_headers: dict[str, str], fmt: str
    ) -> None:
        response = await client.get(
            f"{BASE}/reports/export",
            params={
                "report": "attendance",
                "fmt": fmt,
                "from_date": (TODAY - timedelta(days=30)).isoformat(),
                "to_date": TODAY.isoformat(),
            },
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert response.content, "an empty file is not an export"
