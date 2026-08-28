"""Integration tests for payroll input preparation (Phase 3).

The world the fixtures build, all inside July 2026:

* **Alma** — present three days (one with 2h overtime, one missing its
  check-out), a pending attendance correction, and two days of approved
  unpaid leave. The exception machine's whole menu.
* **Benny** — joins on the 15th: a joiner needing proration and nothing else.
* **Cato** — last working day on the 20th, offboarding case open: a leaver.
* **Dara** — marked not eligible (contractor) in the Phase 2 settings.
* **Edda** — left in January and inactive: not this period's business at all.

Everything asserted is a count of days or hours; the tests also assert what
must NOT happen — no salary figure anywhere in an input payload, no source
record modified, and nobody below an explicit grant seeing anything.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.employee import Employee
from app.models.enums import EmploymentStatus
from app.models.offboarding import OffboardingCase, Resignation
from app.models.payroll import (
    EmployeeCompensation,
    PayrollEmployeeSetting,
    PayrollLeaveRule,
    PayrollPeriod,
    SalaryStructure,
)
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.user import User
from app.models.workforce import AttendanceRecord, AttendanceRegularization, LeaveRequest, LeaveType

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
PAYROLL = f"{API}/payroll"
PASSWORD = "Str0ng!Passw0rd"

PERIOD_START = date(2026, 7, 1)
PERIOD_END = date(2026, 7, 31)
#: July 2026 has 31 calendar days; with Saturday/Sunday off, 23 working days.
WORKING_DAYS = 23


# ----------------------------------------------------------------------
# Fixture helpers
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
        assert role is not None
        session.add(UserRole(user_id=user.id, role_id=role.id))
        await session.flush()
    return user


async def _grant(session: AsyncSession, user: User, *codes: str) -> None:
    suffix = uuid.uuid4().hex[:8]
    role = Role(
        key=f"t_payin_{suffix}",
        name=f"Payroll Inputs Test {suffix}",
        description="Granted by the payroll inputs test suite.",
        is_system=False,
        status="active",
    )
    session.add(role)
    await session.flush()
    rows = (await session.execute(select(Permission).where(Permission.code.in_(list(codes))))).scalars().all()
    assert {row.code for row in rows} == set(codes)
    for row in rows:
        session.add(RolePermission(role_id=role.id, permission_id=row.id))
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.flush()


async def _sign_in(client: AsyncClient, user: User) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['tokens']['access_token']}"}


async def _employee(
    session: AsyncSession,
    label: str,
    *,
    joining: date,
    user: User | None = None,
    manager: Employee | None = None,
    status: EmploymentStatus = EmploymentStatus.ACTIVE,
) -> Employee:
    suffix = uuid.uuid4().hex[:8]
    record = Employee(
        first_name=label.title(),
        last_name="Person",
        official_email=f"{label}.{suffix}@jsan.example",
        joining_date=joining,
        employment_status=status,
        user_id=user.id if user else None,
        reporting_manager_id=manager.id if manager else None,
    )
    session.add(record)
    await session.flush()
    return record


async def _compensation(session: AsyncSession, employee: Employee, effective_from: date) -> None:
    structure = SalaryStructure(
        name=f"Inputs {uuid.uuid4().hex[:8]}", pay_frequency="monthly", currency="INR", status="active"
    )
    session.add(structure)
    await session.flush()
    session.add(
        EmployeeCompensation(
            employee_id=employee.id,
            salary_structure_id=structure.id,
            currency="INR",
            annual_ctc=Decimal("500000.00"),
            annual_gross=Decimal("460000.00"),
            monthly_gross=Decimal("38333.33"),
            basic_salary=Decimal("20000.00"),
            status="active",
            effective_from=effective_from,
        )
    )
    await session.flush()


def _attendance(
    employee: Employee,
    on: date,
    *,
    overtime_minutes: int = 0,
    missing_check_out: bool = False,
) -> AttendanceRecord:
    check_in = datetime(on.year, on.month, on.day, 9, 0, tzinfo=UTC)
    return AttendanceRecord(
        employee_id=employee.id,
        attendance_date=on,
        status="present",
        check_in_at=check_in,
        check_out_at=None if missing_check_out else check_in + timedelta(hours=9),
        worked_minutes=540,
        overtime_minutes=overtime_minutes,
    )


class World:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)

    admin_user: User
    manager_user: User
    manager: Employee
    alma_user: User
    alma: Employee
    benny: Employee
    cato: Employee
    dara: Employee
    period: PayrollPeriod
    unpaid_type: LeaveType


@pytest.fixture
async def world(db_session: AsyncSession) -> World:
    admin_user = await _account(db_session, "admin", "in_adm")

    manager_user = await _account(db_session, "manager", "in_mgr")
    manager = await _employee(db_session, "manager", joining=date(2023, 1, 1), user=manager_user)
    await _compensation(db_session, manager, date(2026, 1, 1))

    alma_user = await _account(db_session, "employee", "in_alma")
    alma = await _employee(db_session, "alma", joining=date(2024, 1, 5), user=alma_user, manager=manager)
    await _compensation(db_session, alma, date(2026, 1, 1))

    benny = await _employee(db_session, "benny", joining=date(2026, 7, 15))
    await _compensation(db_session, benny, date(2026, 7, 15))

    cato = await _employee(db_session, "cato", joining=date(2023, 6, 1))
    await _compensation(db_session, cato, date(2026, 1, 1))
    resignation = Resignation(
        employee_id=cato.id,
        resignation_date=date(2026, 6, 1),
        proposed_last_working_day=date(2026, 7, 20),
        approved_last_working_day=date(2026, 7, 20),
        notice_period_days=30,
        reason="Personal",
        status="hr_review",
    )
    db_session.add(resignation)
    await db_session.flush()
    db_session.add(
        OffboardingCase(
            resignation_id=resignation.id,
            employee_id=cato.id,
            last_working_day=date(2026, 7, 20),
            notice_period_days=30,
        )
    )

    dara = await _employee(db_session, "dara", joining=date(2024, 3, 1))
    await _compensation(db_session, dara, date(2026, 1, 1))
    db_session.add(
        PayrollEmployeeSetting(
            employee_id=dara.id, eligibility="not_eligible", eligibility_reason="contractor"
        )
    )

    # Edda left in January and is inactive: no input row at all.
    edda = await _employee(db_session, "edda", joining=date(2022, 1, 1), status=EmploymentStatus.INACTIVE)
    edda_resignation = Resignation(
        employee_id=edda.id,
        resignation_date=date(2025, 12, 1),
        proposed_last_working_day=date(2026, 1, 15),
        approved_last_working_day=date(2026, 1, 15),
        notice_period_days=30,
        reason="Personal",
        status="completed",
    )
    db_session.add(edda_resignation)
    await db_session.flush()
    db_session.add(
        OffboardingCase(
            resignation_id=edda_resignation.id,
            employee_id=edda.id,
            last_working_day=date(2026, 1, 15),
            notice_period_days=30,
            status="completed",
        )
    )

    # Alma's July: three present days, one missing its check-out and one with
    # two hours of overtime; a pending correction; two days of unpaid leave.
    db_session.add(_attendance(alma, date(2026, 7, 1), overtime_minutes=120))
    db_session.add(_attendance(alma, date(2026, 7, 2)))
    db_session.add(_attendance(alma, date(2026, 7, 3), missing_check_out=True))
    db_session.add(
        AttendanceRegularization(
            employee_id=alma.id,
            attendance_date=date(2026, 7, 3),
            reason="Forgot to check out",
            status="pending",
        )
    )
    unpaid_type = LeaveType(
        name=f"Loss of Pay {uuid.uuid4().hex[:6]}",
        code=f"LOP{uuid.uuid4().hex[:6].upper()}",
        annual_allocation=Decimal("0"),
        is_paid=False,
        allows_negative=True,
    )
    db_session.add(unpaid_type)
    await db_session.flush()
    db_session.add(
        PayrollLeaveRule(leave_type_id=unpaid_type.id, treatment="unpaid", deduction_basis="working_days")
    )
    db_session.add(
        LeaveRequest(
            employee_id=alma.id,
            leave_type_id=unpaid_type.id,
            from_date=date(2026, 7, 6),
            to_date=date(2026, 7, 7),
            days=Decimal("2"),
            reason="Unpaid break",
            status="approved",
        )
    )

    period = PayrollPeriod(
        name=f"July 2026 {uuid.uuid4().hex[:6]}",
        start_date=PERIOD_START,
        end_date=PERIOD_END,
        pay_date=PERIOD_END,
        status="open",
    )
    db_session.add(period)
    await db_session.flush()

    return World(
        admin_user=admin_user,
        manager_user=manager_user,
        manager=manager,
        alma_user=alma_user,
        alma=alma,
        benny=benny,
        cato=cato,
        dara=dara,
        period=period,
        unpaid_type=unpaid_type,
    )


async def _prepare(client: AsyncClient, headers: dict[str, str], period_id: uuid.UUID) -> dict:
    response = await client.post(f"{PAYROLL}/periods/{period_id}/inputs/generate", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _detail(
    client: AsyncClient, headers: dict[str, str], period_id: uuid.UUID, employee_id: uuid.UUID
) -> dict:
    response = await client.get(f"{PAYROLL}/periods/{period_id}/inputs/{employee_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ----------------------------------------------------------------------
class TestPreparation:
    async def test_the_whole_world_prepares_correctly(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        result = await _prepare(client, headers, world.period.id)
        # manager + alma + benny + cato + dara; edda skipped entirely.
        assert result["prepared"] == 5
        assert result["excluded"] == 1

        # -- Alma: the exception menu -----------------------------------
        alma = await _detail(client, headers, world.period.id, world.alma.id)
        assert alma["status"] == "requires_review"
        assert alma["calendar_days"] == 31
        assert alma["working_days"] == WORKING_DAYS
        assert alma["weekly_off_days"] == 8
        assert alma["present_days"] == 3
        assert alma["late_days"] == 0
        assert alma["paid_leave_days"] == "0.0"
        assert alma["unpaid_leave_days"] == "2.0"
        assert alma["unpaid_leave_basis"] == "calendar_days"
        assert alma["absent_days"] == WORKING_DAYS - 3 - 2
        assert alma["overtime_hours"] == "2.00"
        assert alma["approved_overtime_hours"] == "0.00"
        assert alma["pending_overtime_hours"] == "2.00"
        codes = {item["code"] for item in alma["exceptions"]}
        assert codes == {
            "missing_check_out",
            "unresolved_regularization",
            "unapproved_overtime",
            "overtime_not_eligible",
        }
        assert alma["exception_count"] == len(alma["exceptions"])
        # The snapshot names its sources: 3 attendance + 1 correction + 1 leave.
        assert len(alma["sources"]) == 5

        # -- Benny: a joiner --------------------------------------------
        benny = await _detail(client, headers, world.period.id, world.benny.id)
        assert benny["status"] == "ready"
        assert benny["proration_required"] is True
        assert benny["eligible_days"] == 17
        assert benny["non_eligible_days"] == 14
        assert benny["joining_date"] == "2026-07-15"

        # -- Cato: a leaver ----------------------------------------------
        cato = await _detail(client, headers, world.period.id, world.cato.id)
        assert cato["exit_date"] == "2026-07-20"
        assert cato["offboarding_status"] == "not_started"
        assert cato["proration_required"] is True
        assert cato["eligible_days"] == 20

        # -- Dara: excluded, with the reason stated ----------------------
        dara = await _detail(client, headers, world.period.id, world.dara.id)
        assert dara["status"] == "excluded"
        assert dara["eligibility"] == "not_eligible"
        assert "ontractor" in (dara["exclusion_reason"] or "")

        # -- Edda: not this period's business ----------------------------
        listed = await client.get(
            f"{PAYROLL}/periods/{world.period.id}/inputs",
            params={"page_size": 100},
            headers=headers,
        )
        names = {row["employee"]["full_name"] for row in listed.json()["data"]["items"]}
        assert not any("Edda" in name for name in names)

    async def test_no_salary_figure_leaks_into_inputs(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        await _prepare(client, headers, world.period.id)
        detail = await client.get(
            f"{PAYROLL}/periods/{world.period.id}/inputs/{world.alma.id}", headers=headers
        )
        for field in ("annual_ctc", "monthly_gross", "basic_salary", "annual_gross"):
            assert field not in detail.text

    async def test_preparation_never_modifies_source_records(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        before = (
            await db_session.execute(
                select(AttendanceRecord.id, AttendanceRecord.updated_at).where(
                    AttendanceRecord.employee_id == world.alma.id
                )
            )
        ).all()
        headers = await _sign_in(client, world.admin_user)
        await _prepare(client, headers, world.period.id)
        after = (
            await db_session.execute(
                select(AttendanceRecord.id, AttendanceRecord.updated_at).where(
                    AttendanceRecord.employee_id == world.alma.id
                )
            )
        ).all()
        assert before == after

    async def test_a_cancelled_period_cannot_be_prepared(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        assert (
            await client.post(f"{PAYROLL}/periods/{world.period.id}/status/cancelled", headers=headers)
        ).status_code == 200
        refused = await client.post(f"{PAYROLL}/periods/{world.period.id}/inputs/generate", headers=headers)
        assert refused.status_code == 409
        assert refused.json()["errors"][0]["code"] == "period_not_preparable"


# ----------------------------------------------------------------------
class TestChangeDetectionAndReview:
    async def test_changed_sources_flag_the_input(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, world.admin_user)
        await _prepare(client, headers, world.period.id)

        benny_before = await _detail(client, headers, world.period.id, world.benny.id)
        assert benny_before["status"] == "ready"

        # A new approved leave lands after the snapshot.
        db_session.add(
            LeaveRequest(
                employee_id=world.benny.id,
                leave_type_id=world.unpaid_type.id,
                from_date=date(2026, 7, 21),
                to_date=date(2026, 7, 21),
                days=Decimal("1"),
                reason="Late arrival of leave",
                status="approved",
            )
        )
        await db_session.flush()

        detected = await client.post(
            f"{PAYROLL}/periods/{world.period.id}/inputs/detect-changes", headers=headers
        )
        assert detected.status_code == 200, detected.text
        data = detected.json()["data"]
        assert data["flagged"] == 1
        assert data["flagged_employees"][0]["id"] == str(world.benny.id)

        benny_after = await _detail(client, headers, world.period.id, world.benny.id)
        assert benny_after["status"] == "requires_review"
        assert benny_after["source_changed"] is True

        # Detecting again without further changes flags nothing new.
        second = await client.post(
            f"{PAYROLL}/periods/{world.period.id}/inputs/detect-changes", headers=headers
        )
        assert second.json()["data"]["flagged"] == 0

    async def test_review_signs_off_a_flagged_input(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        await _prepare(client, headers, world.period.id)
        alma = await _detail(client, headers, world.period.id, world.alma.id)
        assert alma["status"] == "requires_review"

        reviewed = await client.post(
            f"{PAYROLL}/inputs/{alma['id']}/review",
            json={"note": "Checked with the team lead; the day is genuine."},
            headers=headers,
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["data"]["status"] == "ready"
        assert reviewed.json()["data"]["reviewed_by_name"]

        # A ready input cannot be reviewed again.
        again = await client.post(f"{PAYROLL}/inputs/{alma['id']}/review", json={}, headers=headers)
        assert again.status_code == 409

    async def test_refresh_recomputes_and_resets_review(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, world.admin_user)
        await _prepare(client, headers, world.period.id)

        db_session.add(
            LeaveRequest(
                employee_id=world.benny.id,
                leave_type_id=world.unpaid_type.id,
                from_date=date(2026, 7, 21),
                to_date=date(2026, 7, 22),
                days=Decimal("2"),
                reason="Unpaid break",
                status="approved",
            )
        )
        await db_session.flush()

        result = await _prepare(client, headers, world.period.id)
        assert result["prepared"] == 5
        benny = await _detail(client, headers, world.period.id, world.benny.id)
        assert benny["unpaid_leave_days"] == "2.0"
        assert benny["source_changed"] is False


# ----------------------------------------------------------------------
class TestAccessModel:
    async def test_an_employee_sees_own_input_and_nobody_elses(
        self, client: AsyncClient, world: World
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        await _prepare(client, admin, world.period.id)

        headers = await _sign_in(client, world.alma_user)
        mine = await client.get(f"{API}/me/payroll/inputs", headers=headers)
        assert mine.status_code == 200
        rows = mine.json()["data"]
        assert len(rows) == 1 and rows[0]["employee"]["id"] == str(world.alma.id)

        # Own record answers through the admin path too — it is her own data.
        own = await client.get(f"{PAYROLL}/periods/{world.period.id}/inputs/{world.alma.id}", headers=headers)
        assert own.status_code == 200
        # A stranger's does not.
        stranger = await client.get(
            f"{PAYROLL}/periods/{world.period.id}/inputs/{world.benny.id}", headers=headers
        )
        assert stranger.status_code == 403
        # And the period-wide surfaces are shut entirely.
        assert (
            await client.get(f"{PAYROLL}/periods/{world.period.id}/inputs", headers=headers)
        ).status_code == 403
        assert (
            await client.post(f"{PAYROLL}/periods/{world.period.id}/inputs/generate", headers=headers)
        ).status_code == 403

    async def test_a_seeded_manager_sees_nothing(self, client: AsyncClient, world: World) -> None:
        admin = await _sign_in(client, world.admin_user)
        await _prepare(client, admin, world.period.id)

        headers = await _sign_in(client, world.manager_user)
        assert (
            await client.get(f"{PAYROLL}/periods/{world.period.id}/inputs/{world.alma.id}", headers=headers)
        ).status_code == 403, "the reporting line alone grants nothing in payroll"

    async def test_team_view_reaches_reports_and_stops_there(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        await _prepare(client, admin, world.period.id)

        await _grant(db_session, world.manager_user, "payroll:team_view")
        headers = await _sign_in(client, world.manager_user)
        assert (
            await client.get(f"{PAYROLL}/periods/{world.period.id}/inputs/{world.alma.id}", headers=headers)
        ).status_code == 200
        assert (
            await client.get(f"{PAYROLL}/periods/{world.period.id}/inputs/{world.benny.id}", headers=headers)
        ).status_code == 403

    async def test_hr_access_follows_explicit_grants_only(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        await _prepare(client, admin, world.period.id)

        hr_user = await _account(db_session, "hr_admin", "in_hr")
        headers = await _sign_in(client, hr_user)
        assert (
            await client.get(f"{PAYROLL}/periods/{world.period.id}/inputs", headers=headers)
        ).status_code == 403

        await _grant(db_session, hr_user, "payroll:inputs_view", "employees:view_all")
        headers = await _sign_in(client, hr_user)
        assert (
            await client.get(f"{PAYROLL}/periods/{world.period.id}/inputs", headers=headers)
        ).status_code == 200
        assert (
            await client.get(f"{PAYROLL}/periods/{world.period.id}/exceptions", headers=headers)
        ).status_code == 200
        # What was not granted stays shut: preparing and reviewing.
        assert (
            await client.post(f"{PAYROLL}/periods/{world.period.id}/inputs/generate", headers=headers)
        ).status_code == 403
        alma = await _detail(client, admin, world.period.id, world.alma.id)
        assert (
            await client.post(f"{PAYROLL}/inputs/{alma['id']}/review", json={}, headers=headers)
        ).status_code == 403

    async def test_a_superuser_bypasses_every_guard(
        self, client: AsyncClient, world: World, auth_headers: dict[str, str]
    ) -> None:
        result = await client.post(
            f"{PAYROLL}/periods/{world.period.id}/inputs/generate", headers=auth_headers
        )
        assert result.status_code == 200
        assert (
            await client.get(f"{PAYROLL}/periods/{world.period.id}/inputs", headers=auth_headers)
        ).status_code == 200

    async def test_unauthenticated_requests_get_401(self, client: AsyncClient, world: World) -> None:
        assert (await client.get(f"{PAYROLL}/periods/{world.period.id}/inputs")).status_code == 401
        assert (await client.get(f"{API}/me/payroll/inputs")).status_code == 401
