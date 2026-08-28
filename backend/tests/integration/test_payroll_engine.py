"""Integration tests for the payroll calculation engine (Phase 4).

The world, all inside July 2026 (31 calendar days, 23 working days):

* **Alma** — full month on 30,000 basic: fixed BAS, 40%-of-basic HRA, a fixed
  500 insurance deduction, two days of unpaid leave and two approved overtime
  hours. Every formula on one payslip; the expected numbers below are
  hand-computed.
* **Benny** — joins on the 15th: calendar-day proration, 17/31.
* **Cato** — exits on the 20th: 20/31.
* **Ravi** — salary revised mid-month: 30,000 basic to the 15th, 40,000 from
  the 16th. The period splits into segments, each priced from its own record.
* **Dara** — excluded from payroll, with the reason carried through.
* **Milo** — no compensation at all: the engine refuses, never guesses.
* **Nora** — overtime recorded but not overtime-eligible: flagged upstream,
  refused here.

And the invariants: gross is exactly the sum of earning lines, net is exactly
gross minus deductions, recalculation replaces without duplicating, and the
configured rounding lands on the totals.
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
    EmployeeCompensationComponent,
    PayrollConfiguration,
    PayrollEmployeeSetting,
    PayrollLeaveRule,
    PayrollPeriod,
    SalaryComponent,
    SalaryStructure,
)
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.user import User
from app.models.workforce import AttendanceRecord, LeaveRequest, LeaveType

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
PAYROLL = f"{API}/payroll"
PASSWORD = "Str0ng!Passw0rd"

PERIOD_START = date(2026, 7, 1)
PERIOD_END = date(2026, 7, 31)


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
        key=f"t_payrun_{suffix}",
        name=f"Payroll Engine Test {suffix}",
        description="Granted by the payroll engine test suite.",
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
) -> Employee:
    suffix = uuid.uuid4().hex[:8]
    record = Employee(
        first_name=label.title(),
        last_name="Person",
        official_email=f"{label}.{suffix}@jsan.example",
        joining_date=joining,
        employment_status=EmploymentStatus.ACTIVE,
        user_id=user.id if user else None,
        reporting_manager_id=manager.id if manager else None,
    )
    session.add(record)
    await session.flush()
    return record


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
    ravi: Employee
    dara: Employee
    milo: Employee
    period: PayrollPeriod
    structure: SalaryStructure


@pytest.fixture
async def world(db_session: AsyncSession) -> World:
    # -- Configuration the engine will obey ----------------------------
    config = (await db_session.execute(select(PayrollConfiguration))).scalars().first()
    assert config is not None
    config.overtime_enabled = True
    config.overtime_approval_required = False
    config.overtime_multiplier = Decimal("1.50")
    config.overtime_min_hours = Decimal("1.00")
    config.standard_daily_hours = Decimal("8.00")
    config.rounding_rule = "none"
    config.proration_basis = "calendar_days"
    config.unpaid_leave_treatment = "deduct"
    config.unpaid_leave_basis = "calendar_days"
    await db_session.flush()

    # -- Components with explicit behaviour flags -----------------------
    suffix = uuid.uuid4().hex[:6].upper()
    basic = SalaryComponent(
        name="Engine Basic",
        code=f"EBAS{suffix}",
        component_type="earning",
        calculation_type="fixed",
        value=Decimal("30000"),
        proration_allowed=True,
        leave_impact=True,
        overtime_eligible=True,
    )
    hra = SalaryComponent(
        name="Engine HRA",
        code=f"EHRA{suffix}",
        component_type="earning",
        calculation_type="percentage",
        value=Decimal("40"),
        percentage_basis="basic",
        proration_allowed=True,
    )
    insurance = SalaryComponent(
        name="Engine Insurance",
        code=f"EINS{suffix}",
        component_type="deduction",
        calculation_type="fixed",
        value=Decimal("500"),
        proration_allowed=False,
    )
    db_session.add_all([basic, hra, insurance])
    await db_session.flush()

    structure = SalaryStructure(
        name=f"Engine Structure {suffix}", pay_frequency="monthly", currency="INR", status="active"
    )
    db_session.add(structure)
    await db_session.flush()

    async def compensation(
        employee: Employee,
        *,
        effective_from: date,
        effective_to: date | None = None,
        status: str = "active",
        basic_amount: Decimal = Decimal("30000"),
    ) -> EmployeeCompensation:
        gross = basic_amount + basic_amount * Decimal("0.4")
        comp = EmployeeCompensation(
            employee_id=employee.id,
            salary_structure_id=structure.id,
            currency="INR",
            annual_ctc=gross * 12,
            annual_gross=gross * 12,
            monthly_gross=gross,
            basic_salary=basic_amount,
            status=status,
            effective_from=effective_from,
            effective_to=effective_to,
        )
        db_session.add(comp)
        await db_session.flush()
        db_session.add_all(
            [
                EmployeeCompensationComponent(
                    compensation_id=comp.id,
                    component_id=basic.id,
                    calculation_type="fixed",
                    value=basic_amount,
                ),
                EmployeeCompensationComponent(
                    compensation_id=comp.id,
                    component_id=hra.id,
                    calculation_type="percentage",
                    value=Decimal("40"),
                    percentage_basis="basic",
                ),
                EmployeeCompensationComponent(
                    compensation_id=comp.id,
                    component_id=insurance.id,
                    calculation_type="fixed",
                    value=Decimal("500"),
                ),
            ]
        )
        await db_session.flush()
        return comp

    admin_user = await _account(db_session, "admin", "eng_adm")
    manager_user = await _account(db_session, "manager", "eng_mgr")
    manager = await _employee(db_session, "manager", joining=date(2023, 1, 1), user=manager_user)
    await compensation(manager, effective_from=date(2026, 1, 1))

    # Alma: the full formula menu.
    alma_user = await _account(db_session, "employee", "eng_alma")
    alma = await _employee(db_session, "alma", joining=date(2024, 1, 5), user=alma_user, manager=manager)
    await compensation(alma, effective_from=date(2026, 1, 1))
    check_in = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
    db_session.add_all(
        [
            AttendanceRecord(
                employee_id=alma.id,
                attendance_date=date(2026, 7, 1),
                status="present",
                check_in_at=check_in,
                check_out_at=check_in + timedelta(hours=11),
                worked_minutes=660,
                overtime_minutes=120,
            ),
            AttendanceRecord(
                employee_id=alma.id,
                attendance_date=date(2026, 7, 2),
                status="present",
                check_in_at=check_in + timedelta(days=1),
                check_out_at=check_in + timedelta(days=1, hours=9),
                worked_minutes=540,
            ),
        ]
    )
    lop = LeaveType(
        name=f"Engine LOP {suffix}",
        code=f"ELOP{suffix}",
        annual_allocation=Decimal("0"),
        is_paid=False,
        allows_negative=True,
    )
    db_session.add(lop)
    await db_session.flush()
    db_session.add(
        PayrollLeaveRule(leave_type_id=lop.id, treatment="unpaid", deduction_basis="calendar_days")
    )
    db_session.add(
        LeaveRequest(
            employee_id=alma.id,
            leave_type_id=lop.id,
            from_date=date(2026, 7, 6),
            to_date=date(2026, 7, 7),
            days=Decimal("2"),
            reason="Unpaid",
            status="approved",
        )
    )

    # Benny joins on the 15th; his salary starts the same day.
    benny = await _employee(db_session, "benny", joining=date(2026, 7, 15))
    await compensation(benny, effective_from=date(2026, 7, 15))

    # Cato exits on the 20th.
    cato = await _employee(db_session, "cato", joining=date(2023, 6, 1))
    await compensation(cato, effective_from=date(2026, 1, 1))
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

    # Ravi's salary is revised mid-month: 30,000 to the 15th, 40,000 after.
    ravi = await _employee(db_session, "ravi", joining=date(2023, 2, 1))
    await compensation(
        ravi,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 7, 15),
        status="ended",
    )
    await compensation(ravi, effective_from=date(2026, 7, 16), basic_amount=Decimal("40000"))

    # Dara is excluded; Milo has no salary at all.
    dara = await _employee(db_session, "dara", joining=date(2024, 3, 1))
    await compensation(dara, effective_from=date(2026, 1, 1))
    db_session.add(
        PayrollEmployeeSetting(
            employee_id=dara.id, eligibility="not_eligible", eligibility_reason="contractor"
        )
    )
    milo = await _employee(db_session, "milo", joining=date(2024, 6, 1))

    period = PayrollPeriod(
        name=f"July 2026 Engine {uuid.uuid4().hex[:6]}",
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
        ravi=ravi,
        dara=dara,
        milo=milo,
        period=period,
        structure=structure,
    )


async def _calculated_run(client: AsyncClient, headers: dict[str, str], world: World) -> dict:
    prepared = await client.post(f"{PAYROLL}/periods/{world.period.id}/inputs/generate", headers=headers)
    assert prepared.status_code == 200, prepared.text
    created = await client.post(
        f"{PAYROLL}/runs", json={"payroll_period_id": str(world.period.id)}, headers=headers
    )
    assert created.status_code == 201, created.text
    run = created.json()["data"]
    calculated = await client.post(f"{PAYROLL}/runs/{run['id']}/calculate", headers=headers)
    assert calculated.status_code == 200, calculated.text
    return calculated.json()["data"]["run"]


async def _record(client: AsyncClient, headers: dict[str, str], run_id: str, employee_id: uuid.UUID) -> dict:
    response = await client.get(f"{PAYROLL}/runs/{run_id}/employees/{employee_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _line(record: dict, code_prefix: str) -> dict:
    return next(item for item in record["line_items"] if item["code"].startswith(code_prefix))


# ----------------------------------------------------------------------
class TestCalculation:
    async def test_full_month_with_every_formula(self, client: AsyncClient, world: World) -> None:
        """Alma: fixed, percentage, overtime and unpaid leave, hand-computed.

        BAS 30000; HRA 40% of basic = 12000. Overtime: base 30000 (the one
        overtime-base component), hourly = 30000/(23x8) = 163.0434.., pay =
        hourly x 1.5 x 2h = 489.13. Unpaid: 2d x 30000/31 = 1935.48.
        """
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        alma = await _record(client, headers, run["id"], world.alma.id)

        assert alma["status"] == "calculated"
        assert _line(alma, "EBAS")["amount"] == "30000.00"
        assert _line(alma, "EBAS")["prorated"] is False
        hra = _line(alma, "EHRA")
        assert hra["amount"] == "12000.00"
        assert "% of basic" in hra["calculation_basis"]
        overtime = _line(alma, "OVERTIME_PAY")
        assert overtime["amount"] == "489.13"
        assert "1.50" in overtime["calculation_basis"] and "163.04" in overtime["calculation_basis"]
        assert _line(alma, "EINS")["amount"] == "500.00"
        unpaid = _line(alma, "UNPAID_LEAVE")
        assert unpaid["amount"] == "1935.48"
        assert "calendar days" in unpaid["calculation_basis"]

        assert alma["gross_earnings"] == "42489.13"
        assert alma["total_deductions"] == "2435.48"
        assert alma["net_pay"] == "40053.65"
        assert alma["overtime_hours_paid"] == "2.00"
        assert alma["structure_name"] == world.structure.name
        assert alma["monthly_basic"] == "30000.00"

        # Invariants: gross is exactly the earning lines, net is gross minus
        # deductions.
        earnings = sum(
            Decimal(item["amount"]) for item in alma["line_items"] if item["item_type"] == "earning"
        )
        deductions = sum(
            Decimal(item["amount"]) for item in alma["line_items"] if item["item_type"] == "deduction"
        )
        assert Decimal(alma["gross_earnings"]) == earnings
        assert Decimal(alma["net_pay"]) == Decimal(alma["gross_earnings"]) - Decimal(alma["total_deductions"])
        assert deductions == Decimal(alma["total_deductions"])

    async def test_mid_month_joiner_prorates(self, client: AsyncClient, world: World) -> None:
        """Benny, 17 of 31 calendar days: BAS 16451.61, HRA 6580.65, and the
        non-prorated insurance stays 500."""
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        benny = await _record(client, headers, run["id"], world.benny.id)

        assert benny["status"] == "calculated"
        bas = _line(benny, "EBAS")
        assert bas["amount"] == "16451.61"
        assert bas["prorated"] is True
        assert bas["original_amount"] == "30000.00"
        assert "17/31 calendar days" in bas["calculation_basis"]
        assert _line(benny, "EHRA")["amount"] == "6580.65"
        assert _line(benny, "EINS")["amount"] == "500.00"
        assert benny["gross_earnings"] == "23032.26"
        assert benny["net_pay"] == "22532.26"

    async def test_mid_month_exit_prorates(self, client: AsyncClient, world: World) -> None:
        """Cato, 20 of 31 days: BAS 19354.84, HRA 7741.94."""
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        cato = await _record(client, headers, run["id"], world.cato.id)
        assert cato["status"] == "calculated"
        assert _line(cato, "EBAS")["amount"] == "19354.84"
        assert _line(cato, "EHRA")["amount"] == "7741.94"
        assert cato["gross_earnings"] == "27096.78"
        assert cato["net_pay"] == "26596.78"

    async def test_salary_revision_splits_the_period(self, client: AsyncClient, world: World) -> None:
        """Ravi: 30,000 basic for 15 days, 40,000 for 16.

        BAS = 30000x15/31 + 40000x16/31 = 35161.29;
        HRA = 12000x15/31 + 16000x16/31 = 14064.52. Insurance once.
        """
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        ravi = await _record(client, headers, run["id"], world.ravi.id)

        assert ravi["status"] == "calculated"
        bas = _line(ravi, "EBAS")
        assert bas["amount"] == "35161.29"
        assert "split across salary revision" in bas["calculation_basis"]
        assert _line(ravi, "EHRA")["amount"] == "14064.52"
        assert _line(ravi, "EINS")["amount"] == "500.00"
        assert ravi["gross_earnings"] == "49225.81"
        assert ravi["net_pay"] == "48725.81"
        # The salary record named on the payslip is the one in force last.
        assert ravi["monthly_basic"] == "40000.00"

    async def test_refusals_never_guess(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)

        dara = await _record(client, headers, run["id"], world.dara.id)
        assert dara["status"] == "excluded"
        assert "ontractor" in (dara["exception_reason"] or "")
        assert dara["net_pay"] == "0.00"

        milo = await _record(client, headers, run["id"], world.milo.id)
        assert milo["status"] == "requires_review"
        assert milo["exception_reason"]
        assert milo["net_pay"] == "0.00"
        assert milo["line_items"] == []

        # The run reflects it: totals exist, review count is non-zero, and
        # the run status says so.
        assert run["status"] == "requires_review"
        assert run["review_count"] >= 1
        assert run["excluded_count"] == 1

    async def test_unapproved_overtime_is_never_paid(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        """With approval required and no approved correction, Alma's overtime
        is pending: the input is flagged, and the engine refuses her record
        rather than paying or dropping the hours silently."""
        config = (await db_session.execute(select(PayrollConfiguration))).scalars().first()
        assert config is not None
        config.overtime_approval_required = True
        await db_session.flush()

        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        alma = await _record(client, headers, run["id"], world.alma.id)
        assert alma["status"] == "requires_review"
        assert alma["net_pay"] == "0.00"

    async def test_rounding_follows_configuration(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        config = (await db_session.execute(select(PayrollConfiguration))).scalars().first()
        assert config is not None
        config.rounding_rule = "nearest_whole"
        await db_session.flush()

        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        alma = await _record(client, headers, run["id"], world.alma.id)
        # 42489.13 -> 42489; 2435.48 -> 2435; net = difference of the rounded.
        assert alma["gross_earnings"] == "42489.00"
        assert alma["total_deductions"] == "2435.00"
        assert alma["net_pay"] == "40054.00"

    async def test_recalculation_is_idempotent(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)

        first = await _record(client, headers, run["id"], world.alma.id)
        recalculated = await client.post(f"{PAYROLL}/runs/{run['id']}/recalculate", headers=headers)
        assert recalculated.status_code == 200, recalculated.text
        second = await _record(client, headers, run["id"], world.alma.id)

        assert second["gross_earnings"] == first["gross_earnings"]
        assert second["net_pay"] == first["net_pay"]
        assert len(second["line_items"]) == len(first["line_items"])

        from app.models.payroll import PayrollEmployeeRecord

        count = (
            (
                await db_session.execute(
                    select(PayrollEmployeeRecord).where(
                        PayrollEmployeeRecord.run_id == uuid.UUID(run["id"]),
                        PayrollEmployeeRecord.employee_id == world.alma.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(count) == 1, "recalculation must replace, never duplicate"

    async def test_run_workflow_guards(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)

        # A second run for the same period is refused.
        duplicate = await client.post(
            f"{PAYROLL}/runs", json={"payroll_period_id": str(world.period.id)}, headers=headers
        )
        assert duplicate.status_code == 409
        # Calculate on an already-calculated run points at recalculate.
        again = await client.post(f"{PAYROLL}/runs/{run['id']}/calculate", headers=headers)
        assert again.status_code == 409
        assert again.json()["errors"][0]["code"] == "already_calculated"

    async def test_a_run_without_inputs_is_refused(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        other = PayrollPeriod(
            name=f"August 2026 Engine {uuid.uuid4().hex[:6]}",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            pay_date=date(2026, 8, 31),
            status="open",
        )
        db_session.add(other)
        await db_session.flush()

        headers = await _sign_in(client, world.admin_user)
        run = (
            await client.post(f"{PAYROLL}/runs", json={"payroll_period_id": str(other.id)}, headers=headers)
        ).json()["data"]
        refused = await client.post(f"{PAYROLL}/runs/{run['id']}/calculate", headers=headers)
        assert refused.status_code == 409
        assert refused.json()["errors"][0]["code"] == "inputs_not_prepared"

    async def test_run_totals_are_the_sum_of_records(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        listed = await client.get(
            f"{PAYROLL}/runs/{run['id']}/records", params={"page_size": 100}, headers=headers
        )
        rows = listed.json()["data"]["items"]
        assert Decimal(run["total_gross"]) == sum(Decimal(row["gross_earnings"]) for row in rows)
        assert Decimal(run["total_net"]) == sum(Decimal(row["net_pay"]) for row in rows)


# ----------------------------------------------------------------------
class TestAccessModel:
    async def test_an_employee_sees_own_payroll_and_nothing_else(
        self, client: AsyncClient, world: World
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, admin, world)

        headers = await _sign_in(client, world.alma_user)
        mine = await client.get(f"{API}/me/payroll/records", headers=headers)
        assert mine.status_code == 200
        rows = mine.json()["data"]
        assert len(rows) == 1
        assert rows[0]["employee"]["id"] == str(world.alma.id)
        assert rows[0]["net_pay"] == "40053.65"

        # Her own record answers through the admin path; a stranger's does not.
        assert (
            await client.get(f"{PAYROLL}/runs/{run['id']}/employees/{world.alma.id}", headers=headers)
        ).status_code == 200
        assert (
            await client.get(f"{PAYROLL}/runs/{run['id']}/employees/{world.benny.id}", headers=headers)
        ).status_code == 403
        # Run-wide surfaces and the mutations are shut entirely.
        assert (await client.get(f"{PAYROLL}/runs", headers=headers)).status_code == 403
        assert (
            await client.post(f"{PAYROLL}/runs/{run['id']}/recalculate", headers=headers)
        ).status_code == 403

    async def test_manager_access_follows_team_view(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, admin, world)

        headers = await _sign_in(client, world.manager_user)
        assert (
            await client.get(f"{PAYROLL}/runs/{run['id']}/employees/{world.alma.id}", headers=headers)
        ).status_code == 403, "the reporting line alone grants nothing in payroll"

        await _grant(db_session, world.manager_user, "payroll:team_view")
        headers = await _sign_in(client, world.manager_user)
        assert (
            await client.get(f"{PAYROLL}/runs/{run['id']}/employees/{world.alma.id}", headers=headers)
        ).status_code == 200
        assert (
            await client.get(f"{PAYROLL}/runs/{run['id']}/employees/{world.benny.id}", headers=headers)
        ).status_code == 403

    async def test_hr_access_follows_explicit_grants_only(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, admin, world)

        hr_user = await _account(db_session, "hr_admin", "eng_hr")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(f"{PAYROLL}/runs", headers=headers)).status_code == 403
        assert (
            await client.post(f"{PAYROLL}/runs/{run['id']}/recalculate", headers=headers)
        ).status_code == 403

        await _grant(db_session, hr_user, "payroll:runs_view", "employees:view_all")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(f"{PAYROLL}/runs", headers=headers)).status_code == 200
        assert (await client.get(f"{PAYROLL}/runs/{run['id']}/records", headers=headers)).status_code == 200
        # What was not granted stays shut.
        assert (
            await client.post(f"{PAYROLL}/runs/{run['id']}/recalculate", headers=headers)
        ).status_code == 403
        assert (
            await client.post(
                f"{PAYROLL}/runs", json={"payroll_period_id": str(world.period.id)}, headers=headers
            )
        ).status_code == 403

    async def test_unauthenticated_requests_get_401(self, client: AsyncClient) -> None:
        assert (await client.get(f"{PAYROLL}/runs")).status_code == 401
        assert (await client.get(f"{API}/me/payroll/records")).status_code == 401
