"""Integration tests for payroll reports and full & final settlement (Phase 8).

The world, July 2026 finalized, August 2026 open:

* **Alma** — 30,000 basic, 40% HRA, 500 insurance, two unpaid-leave days
  and two overtime hours in July (42,489.13 gross / 40,053.65 net). She
  resigns with a last working day of 15 August 2026, has a laptop on loan,
  twelve days of paid leave with four used, and — in August — two more
  unpaid-leave days and two more overtime hours. Her settlement is the one
  the tests read, gate, approve, settle and try to reach as somebody else.
* **Benny** — joins July 15th; a clean, prorated payroll row.
* **Dara** — excluded from payroll.
* **Milo** — added where a test needs an ineligible exit: no compensation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.asset import Asset, AssetAssignment, AssetCategory
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.enums import EmploymentStatus
from app.models.offboarding import AssetClearance, FinalSettlementTracking, OffboardingCase, Resignation
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
from app.models.workforce import AttendanceRecord, LeaveBalance, LeaveRequest, LeaveType
from app.services.payroll_calendar import period_calendar

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
PAYROLL = f"{API}/payroll"
REPORTS = f"{PAYROLL}/reports"
FNF = f"{PAYROLL}/final-settlement"
PASSWORD = "Str0ng!Passw0rd"

JULY = (date(2026, 7, 1), date(2026, 7, 31))
AUGUST = (date(2026, 8, 1), date(2026, 8, 31))
LWD = date(2026, 8, 15)


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
        key=f"t_fnf_{suffix}",
        name=f"Phase 8 Test {suffix}",
        description="Granted by the Phase 8 test suite.",
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
    benny_user: User
    benny: Employee
    dara: Employee
    july: PayrollPeriod
    august: PayrollPeriod
    lop: LeaveType
    case: OffboardingCase
    session: AsyncSession
    config: PayrollConfiguration


@pytest.fixture
async def world(db_session: AsyncSession) -> World:
    config = (await db_session.execute(select(PayrollConfiguration))).scalars().first()
    assert config is not None
    config.overtime_enabled = True
    config.overtime_approval_required = False
    config.overtime_basis = "basic"
    config.overtime_multiplier = Decimal("1.50")
    config.overtime_min_hours = Decimal("1.00")
    config.standard_daily_hours = Decimal("8.00")
    config.rounding_rule = "none"
    config.proration_basis = "calendar_days"
    config.unpaid_leave_treatment = "deduct"
    config.unpaid_leave_basis = "calendar_days"
    await db_session.flush()

    suffix = uuid.uuid4().hex[:6].upper()
    basic = SalaryComponent(
        name="Basic Salary",
        code=f"BAS{suffix}",
        component_type="earning",
        calculation_type="fixed",
        value=Decimal("30000"),
        proration_allowed=True,
        leave_impact=True,
        overtime_eligible=True,
    )
    hra = SalaryComponent(
        name="House Rent Allowance",
        code=f"HRA{suffix}",
        component_type="earning",
        calculation_type="percentage",
        value=Decimal("40"),
        percentage_basis="basic",
        proration_allowed=True,
    )
    insurance = SalaryComponent(
        name="Insurance",
        code=f"INS{suffix}",
        component_type="deduction",
        calculation_type="fixed",
        value=Decimal("500"),
        proration_allowed=False,
    )
    db_session.add_all([basic, hra, insurance])
    await db_session.flush()
    structure = SalaryStructure(
        name=f"Phase 8 Structure {suffix}", pay_frequency="monthly", currency="INR", status="active"
    )
    db_session.add(structure)
    await db_session.flush()

    async def compensation(employee: Employee, *, effective_from: date) -> None:
        comp = EmployeeCompensation(
            employee_id=employee.id,
            salary_structure_id=structure.id,
            currency="INR",
            annual_ctc=Decimal("504000"),
            annual_gross=Decimal("504000"),
            monthly_gross=Decimal("42000"),
            basic_salary=Decimal("30000"),
            status="active",
            effective_from=effective_from,
        )
        db_session.add(comp)
        await db_session.flush()
        db_session.add_all(
            [
                EmployeeCompensationComponent(
                    compensation_id=comp.id,
                    component_id=basic.id,
                    calculation_type="fixed",
                    value=Decimal("30000"),
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

    admin_user = await _account(db_session, "admin", "p8_adm")
    manager_user = await _account(db_session, "manager", "p8_mgr")
    manager = await _employee(db_session, "manager", joining=date(2023, 1, 1), user=manager_user)
    await compensation(manager, effective_from=date(2026, 1, 1))

    alma_user = await _account(db_session, "employee", "p8_alma")
    alma = await _employee(db_session, "alma", joining=date(2024, 1, 5), user=alma_user, manager=manager)
    await compensation(alma, effective_from=date(2026, 1, 1))
    benny_user = await _account(db_session, "employee", "p8_benny")
    benny = await _employee(db_session, "benny", joining=date(2026, 7, 15), user=benny_user)
    await compensation(benny, effective_from=date(2026, 7, 15))
    dara = await _employee(db_session, "dara", joining=date(2024, 3, 1))
    await compensation(dara, effective_from=date(2026, 1, 1))
    db_session.add(
        PayrollEmployeeSetting(
            employee_id=dara.id, eligibility="not_eligible", eligibility_reason="contractor"
        )
    )

    def overtime_day(employee: Employee, day: date, minutes: int) -> AttendanceRecord:
        check_in = datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)
        return AttendanceRecord(
            employee_id=employee.id,
            attendance_date=day,
            status="present",
            check_in_at=check_in,
            check_out_at=check_in + timedelta(hours=9, minutes=minutes),
            worked_minutes=540 + minutes,
            overtime_minutes=minutes,
        )

    db_session.add(overtime_day(alma, date(2026, 7, 1), 120))
    db_session.add(overtime_day(alma, date(2026, 8, 5), 120))

    lop = LeaveType(
        name=f"Loss of Pay {suffix}",
        code=f"LOP{suffix}",
        annual_allocation=Decimal("0"),
        is_paid=False,
        allows_negative=True,
    )
    paid = LeaveType(
        name=f"Earned Leave {suffix}",
        code=f"EL{suffix}",
        annual_allocation=Decimal("12"),
        is_paid=True,
    )
    db_session.add_all([lop, paid])
    await db_session.flush()
    db_session.add(
        PayrollLeaveRule(leave_type_id=lop.id, treatment="unpaid", deduction_basis="calendar_days")
    )
    db_session.add_all(
        [
            LeaveRequest(
                employee_id=alma.id,
                leave_type_id=lop.id,
                from_date=date(2026, 7, 6),
                to_date=date(2026, 7, 7),
                days=Decimal("2"),
                reason="Unpaid",
                status="approved",
            ),
            LeaveRequest(
                employee_id=alma.id,
                leave_type_id=lop.id,
                from_date=date(2026, 8, 3),
                to_date=date(2026, 8, 4),
                days=Decimal("2"),
                reason="Unpaid",
                status="approved",
            ),
            LeaveBalance(
                employee_id=alma.id,
                leave_type_id=paid.id,
                year=2026,
                opening_balance=Decimal("0"),
                allocated=Decimal("12"),
                used=Decimal("4"),
                pending=Decimal("0"),
            ),
        ]
    )

    july = PayrollPeriod(
        name=f"July 2026 P8 {suffix}", start_date=JULY[0], end_date=JULY[1], pay_date=JULY[1], status="open"
    )
    august = PayrollPeriod(
        name=f"August 2026 P8 {suffix}",
        start_date=AUGUST[0],
        end_date=AUGUST[1],
        pay_date=AUGUST[1],
        status="open",
    )
    db_session.add_all([july, august])
    await db_session.flush()

    # Alma resigns: last working day 15 August, offboarding in progress.
    resignation = Resignation(
        employee_id=alma.id,
        resignation_date=date(2026, 7, 10),
        proposed_last_working_day=LWD,
        approved_last_working_day=LWD,
        notice_period_days=30,
        reason="Relocation",
        status="hr_review",
    )
    db_session.add(resignation)
    await db_session.flush()
    case = OffboardingCase(
        resignation_id=resignation.id,
        employee_id=alma.id,
        last_working_day=LWD,
        notice_period_days=30,
        status="in_progress",
    )
    db_session.add(case)
    await db_session.flush()

    return World(
        admin_user=admin_user,
        manager_user=manager_user,
        manager=manager,
        alma_user=alma_user,
        alma=alma,
        benny_user=benny_user,
        benny=benny,
        dara=dara,
        july=july,
        august=august,
        lop=lop,
        case=case,
        session=db_session,
        config=config,
    )


async def _finalized_july(client: AsyncClient, headers: dict[str, str], world: World) -> dict:
    assert (
        await client.post(f"{PAYROLL}/periods/{world.july.id}/inputs/generate", headers=headers)
    ).status_code == 200
    created = await client.post(
        f"{PAYROLL}/runs", json={"payroll_period_id": str(world.july.id)}, headers=headers
    )
    run = created.json()["data"]
    assert (await client.post(f"{PAYROLL}/runs/{run['id']}/calculate", headers=headers)).status_code == 200
    items = (await client.get(f"{PAYROLL}/runs/{run['id']}/checklist", headers=headers)).json()["data"]
    for item in items:
        await client.patch(
            f"{PAYROLL}/runs/{run['id']}/checklist/{item['item_key']}",
            json={"completed": True},
            headers=headers,
        )
    for step, body in (
        ("complete-review", None),
        ("submit-approval", None),
        ("approve", {"comment": "OK."}),
        ("finalize", {}),
    ):
        response = await client.post(f"{PAYROLL}/runs/{run['id']}/{step}", json=body, headers=headers)
        assert response.status_code == 200, (step, response.text)
    return (await client.get(f"{PAYROLL}/runs/{run['id']}", headers=headers)).json()["data"]


async def _assign_laptop(world: World) -> Asset:
    suffix = uuid.uuid4().hex[:6].upper()
    category = AssetCategory(name=f"Laptops {suffix}", code=f"LAP{suffix}", returnable=True, status="active")
    world.session.add(category)
    await world.session.flush()
    asset = Asset(
        asset_tag=f"LT-{suffix}", name="Laptop", category_id=category.id, condition="good", status="assigned"
    )
    world.session.add(asset)
    await world.session.flush()
    world.session.add(
        AssetAssignment(
            asset_id=asset.id,
            employee_id=world.alma.id,
            assigned_date=date(2025, 1, 10),
            condition_at_assignment="good",
        )
    )
    world.session.add(
        AssetClearance(
            case_id=world.case.id,
            asset_id=asset.id,
            asset_name="Laptop",
            asset_tag=asset.asset_tag,
            status="assigned",
        )
    )
    await world.session.flush()
    return asset


async def _settlement(client: AsyncClient, headers: dict[str, str], world: World) -> dict:
    created = await client.post(f"{FNF}/cases/{world.case.id}", headers=headers)
    assert created.status_code == 201, created.text
    return created.json()["data"]


def _item(detail: dict, code: str) -> dict:
    return next(item for item in detail["items"] if item["code"] == code)


# ======================================================================
class TestReports:
    async def test_monthly_report_and_summary(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _finalized_july(client, headers, world)
        report = (await client.get(f"{REPORTS}/monthly", headers=headers)).json()["data"]
        rows = {row["employee_id"]: row for row in report["monthly"]}
        assert set(rows) == {
            str(world.alma.id),
            str(world.benny.id),
            str(world.manager.id),
        }, "excluded Dara is not a row"
        alma = rows[str(world.alma.id)]
        assert alma["gross"] == "42489.13"
        assert alma["deductions"] == "2435.48"
        assert alma["net_pay"] == "40053.65"
        assert alma["run_status"] == "finalized"
        assert alma["period_name"] == world.july.name
        summary = report["summary"]
        assert summary["employee_count"] == 3
        assert Decimal(summary["net_payroll"]) == Decimal(run["total_net"])
        assert summary["total_overtime"] == "489.13"
        assert summary["total_unpaid_leave"] == "1935.48"
        assert Decimal(summary["total_unpaid_leave_days"]) == 2
        assert summary["employer_cost_supported"] is False

        filtered = (
            await client.get(
                f"{REPORTS}/monthly", params={"employee_id": str(world.alma.id)}, headers=headers
            )
        ).json()["data"]
        assert [row["employee_id"] for row in filtered["monthly"]] == [str(world.alma.id)]
        by_date = (
            await client.get(f"{REPORTS}/monthly", params={"date_from": "2026-08-01"}, headers=headers)
        ).json()["data"]
        assert by_date["monthly"] == []
        # Calculated-but-not-finalized data is not in the official report.
        assert (
            await client.get(f"{REPORTS}/monthly", params={"status": "calculated"}, headers=headers)
        ).json()["data"]["monthly"] == []

    async def test_earnings_deductions_overtime_unpaid_leave(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        await _finalized_july(client, headers, world)

        earnings = {
            row["employee_id"]: row
            for row in (await client.get(f"{REPORTS}/earnings", headers=headers)).json()["data"]["earnings"]
        }
        alma = earnings[str(world.alma.id)]
        assert alma["basic_salary"] == "30000.00"
        assert alma["allowances"] == "12000.00"
        assert alma["overtime"] == "489.13"
        assert alma["bonus"] == "0.00"
        assert alma["total_gross"] == "42489.13"

        deductions = (
            await client.get(
                f"{REPORTS}/deductions", params={"employee_id": str(world.alma.id)}, headers=headers
            )
        ).json()["data"]["deductions"]
        assert {(row["component"], row["amount"]) for row in deductions} == {
            ("Insurance", "500.00"),
            ("Unpaid leave", "1935.48"),
        }

        overtime = (await client.get(f"{REPORTS}/overtime", headers=headers)).json()["data"]["overtime"]
        assert [
            (row["employee_id"], row["approved_overtime_hours"], row["overtime_amount"]) for row in overtime
        ] == [(str(world.alma.id), "2.00", "489.13")]

        unpaid = (await client.get(f"{REPORTS}/unpaid_leave", headers=headers)).json()["data"]["unpaid_leave"]
        assert len(unpaid) == 1
        assert Decimal(unpaid[0]["unpaid_leave_days"]) == 2
        assert unpaid[0]["deduction_amount"] == "1935.48"
        assert "calendar days" in unpaid[0]["deduction_basis"]

    async def test_history_and_exports(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _finalized_july(client, headers, world)
        history = (await client.get(f"{PAYROLL}/history", headers=headers)).json()["data"]["items"]
        assert [row["id"] for row in history] == [run["id"]]
        assert history[0]["finalized_by_name"]

        csv_export = await client.get(f"{REPORTS}/monthly/export", headers=headers)
        assert csv_export.status_code == 200, csv_export.text
        assert csv_export.headers["content-type"].startswith("text/csv")
        assert 'filename="payroll-monthly.csv"' in csv_export.headers["content-disposition"]
        text = csv_export.content.decode("utf-8-sig")
        assert text.splitlines()[0].startswith("Employee,Employee ID,Department")
        assert "Alma Person" in text and "40053.65" in text

        xlsx = await client.get(f"{REPORTS}/earnings/export", params={"format": "xlsx"}, headers=headers)
        assert xlsx.status_code == 200
        assert "spreadsheetml" in xlsx.headers["content-type"]
        assert xlsx.content[:2] == b"PK"

    async def test_report_access_is_explicit(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        await _finalized_july(client, admin, world)

        for user in (world.alma_user, world.manager_user):
            headers = await _sign_in(client, user)
            assert (await client.get(f"{REPORTS}/monthly", headers=headers)).status_code == 403
            assert (await client.get(f"{REPORTS}/monthly/export", headers=headers)).status_code == 403
            assert (await client.get(f"{PAYROLL}/history", headers=headers)).status_code == 403

        hr_user = await _account(db_session, "hr_admin", "p8_hr")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(f"{REPORTS}/summary", headers=headers)).status_code == 403
        await _grant(db_session, hr_user, "payroll:report_view")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(f"{REPORTS}/summary", headers=headers)).status_code == 200
        assert (
            await client.get(f"{REPORTS}/summary/export", headers=headers)
        ).status_code == 403, "viewing is not exporting"
        await _grant(db_session, hr_user, "payroll:report_export")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(f"{REPORTS}/summary/export", headers=headers)).status_code == 200

        assert (await client.get(f"{REPORTS}/monthly")).status_code == 401
        assert (await client.get(f"{REPORTS}/nonsense", headers=admin)).status_code == 422


# ======================================================================
class TestFinalSettlement:
    async def test_eligibility_and_creation(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        exits = (await client.get(FNF, headers=headers)).json()["data"]
        alma = next(row for row in exits if row["employee"]["id"] == str(world.alma.id))
        assert alma["eligible"] is True
        assert alma["settlement_status"] == "not_started"
        assert alma["last_working_date"] == "2026-08-15"
        assert alma["exit_type"] == "resignation"
        assert alma["exit_reason"] == "Relocation"
        assert alma["final_period_name"] == world.august.name

        settlement = await _settlement(client, headers, world)
        assert settlement["status"] == "draft"
        assert settlement["settlement_code"] == f"FNF-202608-{world.alma.employee_code}"
        assert settlement["offboarding_status"] == "in_progress"
        again = await client.post(f"{FNF}/cases/{world.case.id}", headers=headers)
        assert again.status_code == 409
        assert again.json()["errors"][0]["code"] == "settlement_exists"

        exits = (await client.get(FNF, headers=headers)).json()["data"]
        assert (
            next(row for row in exits if row["employee"]["id"] == str(world.alma.id))["settlement_status"]
            == "draft"
        )
        # The offboarding module's tracker follows.
        tracking = (
            (
                await world.session.execute(
                    select(FinalSettlementTracking).where(FinalSettlementTracking.case_id == world.case.id)
                )
            )
            .scalars()
            .first()
        )
        assert tracking is not None and tracking.status == "in_progress"

    async def test_ineligible_exits_are_refused(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, world.admin_user)
        # Milo: an offboarding case but no compensation.
        milo = await _employee(db_session, "milo", joining=date(2024, 6, 1))
        resignation = Resignation(
            employee_id=milo.id,
            resignation_date=date(2026, 7, 1),
            proposed_last_working_day=date(2026, 8, 20),
            approved_last_working_day=date(2026, 8, 20),
            notice_period_days=30,
            reason="Personal",
            status="hr_review",
        )
        db_session.add(resignation)
        await db_session.flush()
        case = OffboardingCase(
            resignation_id=resignation.id,
            employee_id=milo.id,
            last_working_day=date(2026, 8, 20),
            notice_period_days=30,
            status="in_progress",
        )
        db_session.add(case)
        await db_session.flush()
        refused = await client.post(f"{FNF}/cases/{case.id}", headers=headers)
        assert refused.status_code == 409
        assert refused.json()["errors"][0]["code"] == "not_eligible"
        assert "compensation" in refused.json()["message"]

        # An offboarding that has not started is not settleable either.
        world.case.status = "not_started"
        await db_session.flush()
        refused = await client.post(f"{FNF}/cases/{world.case.id}", headers=headers)
        assert refused.status_code == 409
        exits = (await client.get(FNF, headers=headers)).json()["data"]
        alma = next(row for row in exits if row["employee"]["id"] == str(world.alma.id))
        assert alma["eligible"] is False and "not started" in (alma["ineligibility_reason"] or "")
        assert (await client.post(f"{FNF}/cases/{uuid.uuid4()}", headers=headers)).status_code == 404

    async def test_calculation_from_existing_data(self, client: AsyncClient, world: World) -> None:
        """July is paid; August 1-15 is owed: 15 days at 42000/31, minus two
        unpaid-leave days, plus two overtime hours at the configured formula."""
        headers = await _sign_in(client, world.admin_user)
        await _finalized_july(client, headers, world)
        detail = await _settlement(client, headers, world)

        assert detail["paid_through"] == "2026-07-31"
        assert detail["unpaid_salary_days"] == 15
        assert detail["monthly_gross"] == "42000.00"
        rate = (Decimal("42000") / Decimal(31)).quantize(Decimal("0.0001"), ROUND_HALF_UP)
        assert Decimal(detail["daily_rate"]) == rate
        salary = _item(detail, "FINAL_SALARY")
        assert Decimal(salary["amount"]) == (rate * 15).quantize(Decimal("0.01"), ROUND_HALF_UP)
        assert salary["quantity"] == "15.00"
        unpaid = _item(detail, "UNPAID_LEAVE")
        assert Decimal(unpaid["quantity"]) == 2
        assert Decimal(unpaid["amount"]) == (rate * 2).quantize(Decimal("0.01"), ROUND_HALF_UP)
        assert Decimal(detail["unpaid_leave_days"]) == 2

        overtime = _item(detail, "OVERTIME")
        working = len(period_calendar(world.config, AUGUST[0], AUGUST[1]).working_dates)
        hourly = Decimal("30000") / (Decimal(working) * Decimal("8"))
        assert Decimal(overtime["amount"]) == (hourly * Decimal("1.5") * 2).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )
        assert detail["overtime_hours"] == "2.00"

        assert Decimal(detail["final_earnings"]) == Decimal(salary["amount"]) + Decimal(overtime["amount"])
        assert Decimal(detail["final_deductions"]) == Decimal(unpaid["amount"])
        assert detail["approved_encashments"] == "0.00" and detail["approved_adjustments"] == "0.00"
        assert Decimal(detail["settlement_amount"]) == Decimal(detail["final_earnings"]) - Decimal(
            detail["final_deductions"]
        )

        # Leave balances come from the leave module; encashment is never assumed.
        leave = next(row for row in detail["leave_summary"] if row["is_paid"])
        assert leave["eligible"] == "12.0" and leave["used"] == "4.0" and leave["remaining"] == "8.0"
        assert leave["encashable"] is False
        assert any("encashment" in issue["message"] for issue in detail["issues"])
        assert detail["critical_issue_count"] == 0

    async def test_assets_and_adjustments(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        await _finalized_july(client, headers, world)
        await _assign_laptop(world)
        detail = await _settlement(client, headers, world)
        sid = detail["id"]

        laptop = next(row for row in detail["assets"] if row["asset_name"] == "Laptop")
        assert laptop["return_status"] == "assigned" and laptop["recovery_approved"] is False
        assert any(
            "asset" in issue["message"] and issue["severity"] == "critical" for issue in detail["issues"]
        )

        # Proposed adjustments do not count until approved; rejected ones never do.
        base_amount = Decimal(detail["settlement_amount"])
        for body in (
            {
                "adjustment_type": "final_bonus",
                "name": "Exit bonus",
                "amount": "5000.00",
                "reason": "Approved by management",
            },
            {
                "adjustment_type": "leave_encashment",
                "name": "8 days EL",
                "amount": "10838.71",
                "reason": "Per HR decision",
            },
            {
                "adjustment_type": "asset_recovery",
                "name": "Laptop not returned",
                "amount": "25000.00",
                "reason": "Unreturned laptop",
            },
            {
                "adjustment_type": "recovery",
                "name": "Salary advance",
                "amount": "3000.00",
                "reason": "June advance",
            },
        ):
            response = await client.post(f"{FNF}/{sid}/adjustments", json=body, headers=headers)
            assert response.status_code == 201, response.text
        detail = response.json()["data"]
        assert Decimal(detail["settlement_amount"]) == base_amount, "pending adjustments change nothing"
        assert any("awaiting" in issue["message"] for issue in detail["issues"])
        assert (
            await client.post(
                f"{FNF}/{sid}/adjustments",
                json={"adjustment_type": "recovery", "name": "x", "amount": "-5", "reason": "bad"},
                headers=headers,
            )
        ).status_code == 422

        adjustments = {a["name"]: a for a in detail["adjustments"]}
        for name, approve in (
            ("Exit bonus", True),
            ("8 days EL", True),
            ("Laptop not returned", True),
            ("Salary advance", False),
        ):
            response = await client.post(
                f"{FNF}/{sid}/adjustments/{adjustments[name]['id']}/decide",
                json={"approve": approve, "note": "Decided"},
                headers=headers,
            )
            assert response.status_code == 200, response.text
        detail = response.json()["data"]
        assert detail["approved_adjustments"] == "5000.00"
        assert detail["approved_encashments"] == "10838.71"
        assert Decimal(detail["final_deductions"]) == Decimal(
            _item(detail, "UNPAID_LEAVE")["amount"]
        ) + Decimal("25000")
        assert Decimal(detail["settlement_amount"]) == (
            Decimal(detail["final_earnings"])
            + Decimal("10838.71")
            + Decimal("5000")
            - Decimal(detail["final_deductions"])
        )
        assert not any(
            item["name"] == "Salary advance" for item in detail["items"]
        ), "rejected adjustments are excluded"
        laptop = next(row for row in detail["assets"] if row["asset_name"] == "Laptop")
        assert laptop["recovery_approved"] is True and laptop["recovery_amount"] == "25000.00"
        assert detail["critical_issue_count"] == 0
        decided = adjustments["Salary advance"]["id"]
        assert (
            await client.post(
                f"{FNF}/{sid}/adjustments/{decided}/decide", json={"approve": True}, headers=headers
            )
        ).status_code == 409

    async def test_workflow_gates_and_locking(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, world.admin_user)
        await _finalized_july(client, headers, world)
        await _assign_laptop(world)
        detail = await _settlement(client, headers, world)
        sid = detail["id"]

        # Nothing skips: approve/finalize refused from draft.
        assert (
            await client.post(f"{FNF}/{sid}/approve", json={"comment": "Now"}, headers=headers)
        ).status_code == 409
        assert (await client.post(f"{FNF}/{sid}/finalize", json={}, headers=headers)).status_code == 409
        assert (await client.post(f"{FNF}/{sid}/submit", headers=headers)).status_code == 200
        early = await client.post(f"{FNF}/{sid}/approve", json={"comment": "Now"}, headers=headers)
        assert early.status_code == 409 and early.json()["errors"][0]["code"] == "review_incomplete"
        assert (await client.post(f"{FNF}/{sid}/complete-review", headers=headers)).status_code == 200
        blocked = await client.post(f"{FNF}/{sid}/approve", json={"comment": "Now"}, headers=headers)
        assert blocked.status_code == 409 and blocked.json()["errors"][0]["code"] == "approval_blocked"
        assert "asset" in blocked.json()["message"]

        # Clear the laptop, then approve.
        clearance = (
            (await db_session.execute(select(AssetClearance).where(AssetClearance.case_id == world.case.id)))
            .scalars()
            .first()
        )
        assert clearance is not None
        clearance.status = "returned"
        await db_session.flush()
        approved = await client.post(f"{FNF}/{sid}/approve", json={"comment": "All clear."}, headers=headers)
        assert approved.status_code == 200, approved.text
        detail = approved.json()["data"]
        assert (
            detail["status"] == "approved"
            and detail["approved_by_name"]
            and detail["approval_comment"] == "All clear."
        )
        # Approved is frozen until reopened.
        locked = await client.post(
            f"{FNF}/{sid}/adjustments",
            json={"adjustment_type": "recovery", "name": "Late", "amount": "10.00", "reason": "Late"},
            headers=headers,
        )
        assert locked.status_code == 409 and locked.json()["errors"][0]["code"] == "settlement_locked"
        assert (
            await client.post(f"{FNF}/{sid}/reopen", json={"reason": "Recheck"}, headers=headers)
        ).status_code == 200
        assert (await client.get(f"{FNF}/{sid}", headers=headers)).json()["data"]["status"] == "draft"
        for step, body in (("submit", None), ("complete-review", None), ("approve", {"comment": "Final."})):
            assert (await client.post(f"{FNF}/{sid}/{step}", json=body, headers=headers)).status_code == 200

        settled = await client.post(
            f"{FNF}/{sid}/finalize", json={"settlement_reference": "FNF-REF-1"}, headers=headers
        )
        assert settled.status_code == 200, settled.text
        detail = settled.json()["data"]
        assert (
            detail["status"] == "settled"
            and detail["settled_by_name"]
            and detail["settlement_reference"] == "FNF-REF-1"
        )
        amount = detail["settlement_amount"]

        # Read-only from here: every change refused and audited, the snapshot kept.
        for call in (
            client.post(f"{FNF}/{sid}/calculate", headers=headers),
            client.patch(f"{FNF}/{sid}", json={"notes": "x"}, headers=headers),
            client.post(
                f"{FNF}/{sid}/adjustments",
                json={"adjustment_type": "final_bonus", "name": "Late", "amount": "1.00", "reason": "Late"},
                headers=headers,
            ),
            client.post(f"{FNF}/{sid}/submit", headers=headers),
            client.post(f"{FNF}/{sid}/reopen", json={"reason": "No way"}, headers=headers),
            client.post(f"{FNF}/{sid}/finalize", json={}, headers=headers),
        ):
            response = await call
            assert response.status_code == 409, response.text
        assert (await client.delete(f"{FNF}/{sid}", headers=headers)).status_code in (404, 405)
        after = (await client.get(f"{FNF}/{sid}", headers=headers)).json()["data"]
        assert after["settlement_amount"] == amount and after["status"] == "settled"
        from app.models.payroll_settlement import FinalSettlement

        row = (
            (await db_session.execute(select(FinalSettlement).where(FinalSettlement.id == uuid.UUID(sid))))
            .scalars()
            .first()
        )
        assert row is not None and row.final_snapshot is not None
        assert row.final_snapshot["settlement_amount"] == amount
        tracking = (
            (
                await db_session.execute(
                    select(FinalSettlementTracking).where(FinalSettlementTracking.case_id == world.case.id)
                )
            )
            .scalars()
            .first()
        )
        assert (
            tracking is not None
            and tracking.status == "completed"
            and tracking.settlement_reference == "FNF-REF-1"
        )

    async def test_employee_sees_only_own_released_settlement(
        self, client: AsyncClient, world: World
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        await _finalized_july(client, admin, world)
        detail = await _settlement(client, admin, world)
        sid = detail["id"]

        mine = await _sign_in(client, world.alma_user)
        assert (
            await client.get(f"{API}/me/payroll/settlement", headers=mine)
        ).status_code == 404, "not released yet"
        for step, body in (
            ("submit", None),
            ("complete-review", None),
            ("approve", {"comment": "Approved."}),
            ("finalize", {}),
        ):
            assert (await client.post(f"{FNF}/{sid}/{step}", json=body, headers=admin)).status_code == 200

        own = await client.get(f"{API}/me/payroll/settlement", headers=mine)
        assert own.status_code == 200, own.text
        body = own.json()["data"]
        assert body["status"] == "settled" and body["settlement_amount"] == detail["settlement_amount"]
        assert [item["code"] for item in body["items"]]
        for forbidden in ("approval_comment", "issues", "approved_by_name", "adjustments"):
            assert forbidden not in body
        # The administrator surfaces are shut to her, and Benny has nothing.
        assert (await client.get(FNF, headers=mine)).status_code == 403
        assert (await client.get(f"{FNF}/{sid}", headers=mine)).status_code == 403
        assert (
            await client.post(
                f"{FNF}/{sid}/adjustments",
                json={"adjustment_type": "final_bonus", "name": "Me", "amount": "1.00", "reason": "Me"},
                headers=mine,
            )
        ).status_code == 403
        benny = await _sign_in(client, world.benny_user)
        assert (await client.get(f"{API}/me/payroll/settlement", headers=benny)).status_code == 404
        assert (await client.get(f"{API}/me/payroll/settlement")).status_code == 401

    async def test_settlement_permissions_are_explicit(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        await _finalized_july(client, admin, world)
        detail = await _settlement(client, admin, world)
        sid = detail["id"]

        manager = await _sign_in(client, world.manager_user)
        assert (await client.get(FNF, headers=manager)).status_code == 403
        assert (
            await client.get(f"{FNF}/{sid}", headers=manager)
        ).status_code == 403, "the reporting line grants nothing"

        hr_user = await _account(db_session, "hr_admin", "p8_hr2")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(FNF, headers=headers)).status_code == 403
        await _grant(db_session, hr_user, "payroll:settlement_view")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(FNF, headers=headers)).status_code == 200
        assert (await client.get(f"{FNF}/{sid}", headers=headers)).status_code == 200
        assert (await client.post(f"{FNF}/{sid}/calculate", headers=headers)).status_code == 403
        assert (
            await client.post(f"{FNF}/{sid}/approve", json={"comment": "No way"}, headers=headers)
        ).status_code == 403
        assert (await client.post(f"{FNF}/{sid}/finalize", json={}, headers=headers)).status_code == 403
        await _grant(db_session, hr_user, "payroll:settlement_update")
        headers = await _sign_in(client, hr_user)
        assert (await client.post(f"{FNF}/{sid}/calculate", headers=headers)).status_code == 200
        assert (
            await client.post(f"{FNF}/{sid}/approve", json={"comment": "No way"}, headers=headers)
        ).status_code == 403
        assert (await client.get(f"{FNF}/{uuid.uuid4()}", headers=admin)).status_code == 404

    async def test_audit_trail(self, client: AsyncClient, world: World, db_session: AsyncSession) -> None:
        headers = await _sign_in(client, world.admin_user)
        await _finalized_july(client, headers, world)
        await client.get(f"{REPORTS}/monthly", headers=headers)
        await client.get(f"{REPORTS}/monthly/export", headers=headers)
        detail = await _settlement(client, headers, world)
        sid = detail["id"]
        proposed = await client.post(
            f"{FNF}/{sid}/adjustments",
            json={"adjustment_type": "final_bonus", "name": "Bonus", "amount": "100.00", "reason": "Because"},
            headers=headers,
        )
        adjustment_id = proposed.json()["data"]["adjustments"][0]["id"]
        assert (
            await client.post(
                f"{FNF}/{sid}/adjustments/{adjustment_id}/decide", json={"approve": True}, headers=headers
            )
        ).status_code == 200
        for step, body in (
            ("submit", None),
            ("complete-review", None),
            ("approve", {"comment": "Approved."}),
            ("finalize", {}),
        ):
            await client.post(f"{FNF}/{sid}/{step}", json=body, headers=headers)
        assert (await client.post(f"{FNF}/{sid}/calculate", headers=headers)).status_code == 409

        actions = {
            row.action
            for row in (await db_session.execute(select(AuditLog).where(AuditLog.action.like("payroll.%"))))
            .scalars()
            .all()
        }
        assert actions >= {
            "payroll.report.generated",
            "payroll.report.exported",
            "payroll.settlement.created",
            "payroll.settlement.adjustment_added",
            "payroll.settlement.submitted",
            "payroll.settlement.review_completed",
            "payroll.settlement.approved",
            "payroll.settlement.finalized",
            "payroll.settlement.locked_modification_attempt",
        }
