"""Integration tests for payslips and employee self-service (Phase 7).

The world, inside July 2026 (with June behind it for history):

* **Alma** — clean full-month record, 42,489.13 gross / 41,989.13 net with
  overtime; the payslip the tests read, download and try to steal.
* **Benny** — joins July 15th; the other employee whose payslip Alma must
  never reach.
* **Dara** — excluded; no payslip is ever generated for her.

And the invariants: only finalized payroll becomes a payslip, the number
and every figure are immutable, regeneration replaces the file alone, and
nothing about one employee's pay reaches another.
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
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.enums import EmploymentStatus
from app.models.payroll import (
    EmployeeCompensation,
    EmployeeCompensationComponent,
    PayrollConfiguration,
    PayrollEmployeeSetting,
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
ME = f"{API}/me/payroll/payslips"
PASSWORD = "Str0ng!Passw0rd"


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
        key=f"t_payslip_{suffix}",
        name=f"Payslip Test {suffix}",
        description="Granted by the payslip test suite.",
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
    dara: Employee
    period: PayrollPeriod
    june: PayrollPeriod
    session: AsyncSession


@pytest.fixture
async def world(db_session: AsyncSession) -> World:
    config = (await db_session.execute(select(PayrollConfiguration))).scalars().first()
    assert config is not None
    config.overtime_enabled = True
    config.overtime_approval_required = False
    config.overtime_multiplier = Decimal("1.50")
    config.standard_daily_hours = Decimal("8.00")
    config.rounding_rule = "none"
    config.proration_basis = "calendar_days"
    config.unpaid_leave_treatment = "deduct"
    config.unpaid_leave_basis = "calendar_days"
    await db_session.flush()

    suffix = uuid.uuid4().hex[:6].upper()
    basic = SalaryComponent(
        name="Payslip Basic",
        code=f"PBAS{suffix}",
        component_type="earning",
        calculation_type="fixed",
        value=Decimal("30000"),
        proration_allowed=True,
        leave_impact=True,
        overtime_eligible=True,
    )
    hra = SalaryComponent(
        name="Payslip HRA",
        code=f"PHRA{suffix}",
        component_type="earning",
        calculation_type="percentage",
        value=Decimal("40"),
        percentage_basis="basic",
        proration_allowed=True,
    )
    insurance = SalaryComponent(
        name="Payslip Insurance",
        code=f"PINS{suffix}",
        component_type="deduction",
        calculation_type="fixed",
        value=Decimal("500"),
        proration_allowed=False,
    )
    db_session.add_all([basic, hra, insurance])
    await db_session.flush()

    structure = SalaryStructure(
        name=f"Payslip Structure {suffix}", pay_frequency="monthly", currency="INR", status="active"
    )
    db_session.add(structure)
    await db_session.flush()

    async def compensation(employee: Employee, *, effective_from: date) -> EmployeeCompensation:
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
        return comp

    admin_user = await _account(db_session, "admin", "ps_adm")
    manager_user = await _account(db_session, "manager", "ps_mgr")
    manager = await _employee(db_session, "manager", joining=date(2023, 1, 1), user=manager_user)
    await compensation(manager, effective_from=date(2026, 1, 1))

    alma_user = await _account(db_session, "employee", "ps_alma")
    alma = await _employee(db_session, "alma", joining=date(2024, 1, 5), user=alma_user, manager=manager)
    await compensation(alma, effective_from=date(2026, 1, 1))
    check_in = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
    db_session.add(
        AttendanceRecord(
            employee_id=alma.id,
            attendance_date=date(2026, 7, 1),
            status="present",
            check_in_at=check_in,
            check_out_at=check_in + timedelta(hours=11),
            worked_minutes=660,
            overtime_minutes=120,
        )
    )

    benny = await _employee(db_session, "benny", joining=date(2026, 7, 15))
    await compensation(benny, effective_from=date(2026, 7, 15))

    dara = await _employee(db_session, "dara", joining=date(2024, 3, 1))
    await compensation(dara, effective_from=date(2026, 1, 1))
    db_session.add(
        PayrollEmployeeSetting(
            employee_id=dara.id, eligibility="not_eligible", eligibility_reason="contractor"
        )
    )

    june = PayrollPeriod(
        name=f"June 2026 Payslips {uuid.uuid4().hex[:6]}",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        pay_date=date(2026, 6, 30),
        status="open",
    )
    period = PayrollPeriod(
        name=f"July 2026 Payslips {uuid.uuid4().hex[:6]}",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
        pay_date=date(2026, 7, 31),
        status="open",
    )
    db_session.add_all([june, period])
    await db_session.flush()

    return World(
        admin_user=admin_user,
        manager_user=manager_user,
        manager=manager,
        alma_user=alma_user,
        alma=alma,
        benny=benny,
        dara=dara,
        period=period,
        june=june,
        session=db_session,
    )


async def _calculated_run(
    client: AsyncClient, headers: dict[str, str], world: World, *, period: PayrollPeriod | None = None
) -> dict:
    target = period or world.period
    prepared = await client.post(f"{PAYROLL}/periods/{target.id}/inputs/generate", headers=headers)
    assert prepared.status_code == 200, prepared.text
    created = await client.post(
        f"{PAYROLL}/runs", json={"payroll_period_id": str(target.id)}, headers=headers
    )
    assert created.status_code == 201, created.text
    run = created.json()["data"]
    calculated = await client.post(f"{PAYROLL}/runs/{run['id']}/calculate", headers=headers)
    assert calculated.status_code == 200, calculated.text
    return calculated.json()["data"]["run"]


async def _approved_run(
    client: AsyncClient, headers: dict[str, str], world: World, *, period: PayrollPeriod | None = None
) -> dict:
    run = await _calculated_run(client, headers, world, period=period)
    items = (await client.get(f"{PAYROLL}/runs/{run['id']}/checklist", headers=headers)).json()["data"]
    for item in items:
        await client.patch(
            f"{PAYROLL}/runs/{run['id']}/checklist/{item['item_key']}",
            json={"completed": True},
            headers=headers,
        )
    assert (
        await client.post(f"{PAYROLL}/runs/{run['id']}/complete-review", headers=headers)
    ).status_code == 200
    assert (
        await client.post(f"{PAYROLL}/runs/{run['id']}/submit-approval", headers=headers)
    ).status_code == 200
    approved = await client.post(
        f"{PAYROLL}/runs/{run['id']}/approve", json={"comment": "Checked."}, headers=headers
    )
    assert approved.status_code == 200, approved.text
    return approved.json()["data"]


async def _finalized_run(
    client: AsyncClient, headers: dict[str, str], world: World, *, period: PayrollPeriod | None = None
) -> dict:
    run = await _approved_run(client, headers, world, period=period)
    finalized = await client.post(f"{PAYROLL}/runs/{run['id']}/finalize", json={}, headers=headers)
    assert finalized.status_code == 200, finalized.text
    return finalized.json()["data"]


async def _generated(
    client: AsyncClient, headers: dict[str, str], world: World, *, period: PayrollPeriod | None = None
) -> tuple[dict, dict[str, dict]]:
    """A finalized run with payslips, keyed by employee id."""
    run = await _finalized_run(client, headers, world, period=period)
    generated = await client.post(f"{PAYROLL}/runs/{run['id']}/payslips/generate", headers=headers)
    assert generated.status_code == 200, generated.text
    return run, {row["employee"]["id"]: row for row in generated.json()["data"]["payslips"]}


# ----------------------------------------------------------------------
class TestGeneration:
    async def test_generates_from_finalized_payroll(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _finalized_run(client, headers, world)

        generated = await client.post(f"{PAYROLL}/runs/{run['id']}/payslips/generate", headers=headers)
        assert generated.status_code == 200, generated.text
        body = generated.json()["data"]
        assert body["generated"] == 3, "Alma, Benny and the manager; Dara is excluded"
        assert body["skipped_excluded"] == 1
        assert body["already_existed"] == 0

        by_employee = {row["employee"]["id"]: row for row in body["payslips"]}
        alma = by_employee[str(world.alma.id)]
        assert alma["payslip_number"] == f"PS-2026-07-{world.alma.employee_code}"
        assert alma["gross_earnings"] == "42489.13"
        assert alma["total_deductions"] == "500.00"
        assert alma["net_pay"] == "41989.13"
        assert alma["payroll_month"] == "July 2026"
        assert alma["status"] == "generated"
        numbers = [row["payslip_number"] for row in body["payslips"]]
        assert len(set(numbers)) == len(numbers)

        # The values are the snapshot's, exactly.
        snapshots = (await client.get(f"{PAYROLL}/runs/{run['id']}/snapshots", headers=headers)).json()[
            "data"
        ]
        snapshot = next(row for row in snapshots if row["employee_id"] == str(world.alma.id))
        assert snapshot["final_net"] == alma["net_pay"]

        # Generating again invents nothing and duplicates nothing.
        again = (await client.post(f"{PAYROLL}/runs/{run['id']}/payslips/generate", headers=headers)).json()[
            "data"
        ]
        assert again["generated"] == 0
        assert again["already_existed"] == 3

    async def test_refused_for_anything_but_finalized_payroll(
        self, client: AsyncClient, world: World
    ) -> None:
        headers = await _sign_in(client, world.admin_user)
        # A freshly created draft run: no numbers at all.
        created = await client.post(
            f"{PAYROLL}/runs", json={"payroll_period_id": str(world.june.id)}, headers=headers
        )
        draft = created.json()["data"]
        refused = await client.post(f"{PAYROLL}/runs/{draft['id']}/payslips/generate", headers=headers)
        assert refused.status_code == 409
        assert refused.json()["errors"][0]["code"] == "not_finalized"

        # Approved but not finalized: still not official.
        approved = await _approved_run(client, headers, world)
        refused = await client.post(f"{PAYROLL}/runs/{approved['id']}/payslips/generate", headers=headers)
        assert refused.status_code == 409
        assert refused.json()["errors"][0]["code"] == "not_finalized"

    async def test_pdf_carries_the_payroll(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        _run, payslips = await _generated(client, headers, world)
        alma = payslips[str(world.alma.id)]

        downloaded = await client.get(
            f"{PAYROLL}/employees/{world.alma.id}/payslips/{alma['id']}/download", headers=headers
        )
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.headers["content-type"] == "application/pdf"
        assert alma["payslip_number"] in downloaded.headers["content-disposition"]
        pdf = downloaded.content
        assert pdf.startswith(b"%PDF")
        # Uncompressed page streams: the words on the page are in the bytes.
        assert alma["payslip_number"].encode() in pdf
        assert b"Alma Person" in pdf
        assert b"41,989.13" in pdf
        assert b"42,489.13" in pdf
        assert b"Payslip Basic" in pdf
        assert b"Overtime" in pdf
        assert b"rupees" in pdf

    async def test_regeneration_replaces_only_the_file(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        _run, payslips = await _generated(client, headers, world)
        alma = payslips[str(world.alma.id)]

        regenerated = await client.post(f"{PAYROLL}/payslips/{alma['id']}/regenerate", headers=headers)
        assert regenerated.status_code == 200, regenerated.text
        body = regenerated.json()["data"]
        assert body["payslip_number"] == alma["payslip_number"]
        assert body["gross_earnings"] == alma["gross_earnings"]
        assert body["total_deductions"] == alma["total_deductions"]
        assert body["net_pay"] == alma["net_pay"]
        assert body["regenerated_at"] is not None
        assert body["generated_at"] == alma["generated_at"]

        listed = (
            await client.get(
                f"{PAYROLL}/payslips", params={"employee_id": str(world.alma.id)}, headers=headers
            )
        ).json()["data"]
        assert listed["meta"]["total_items"] == 1, "regeneration never creates a second payslip"

    async def test_source_changes_never_reach_old_payslips(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        """Salary doubled, employee renamed, attendance and leave added after
        finalization — then regenerate: the payslip says what it always said."""
        headers = await _sign_in(client, world.admin_user)
        _run, payslips = await _generated(client, headers, world)
        alma = payslips[str(world.alma.id)]
        url = f"{PAYROLL}/employees/{world.alma.id}/payslips/{alma['id']}"
        before = (await client.get(url, headers=headers)).json()["data"]

        comp = (
            (
                await db_session.execute(
                    select(EmployeeCompensation).where(EmployeeCompensation.employee_id == world.alma.id)
                )
            )
            .scalars()
            .first()
        )
        assert comp is not None
        comp.basic_salary = Decimal("60000")
        comp.monthly_gross = Decimal("84000")
        world.alma.first_name = "Almarena"
        check_in = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
        db_session.add(
            AttendanceRecord(
                employee_id=world.alma.id,
                attendance_date=date(2026, 7, 20),
                status="present",
                check_in_at=check_in,
                check_out_at=check_in + timedelta(hours=12),
                worked_minutes=720,
                overtime_minutes=240,
            )
        )
        lop = LeaveType(
            name=f"Payslip LOP {uuid.uuid4().hex[:6]}",
            code=f"PLOP{uuid.uuid4().hex[:4].upper()}",
            annual_allocation=Decimal("0"),
            is_paid=False,
            allows_negative=True,
        )
        db_session.add(lop)
        await db_session.flush()
        db_session.add(
            LeaveRequest(
                employee_id=world.alma.id,
                leave_type_id=lop.id,
                from_date=date(2026, 7, 22),
                to_date=date(2026, 7, 24),
                days=Decimal("3"),
                reason="Late-filed leave",
                status="approved",
            )
        )
        await db_session.flush()

        assert (
            await client.post(f"{PAYROLL}/payslips/{alma['id']}/regenerate", headers=headers)
        ).status_code == 200
        after = (await client.get(url, headers=headers)).json()["data"]
        for key in (
            "payslip_number",
            "gross_earnings",
            "total_deductions",
            "net_pay",
            "earnings",
            "deductions",
            "amount_in_words",
        ):
            assert after[key] == before[key], key
        assert after["employee_details"]["name"] == "Alma Person"
        pdf = (await client.get(f"{url}/download", headers=headers)).content
        assert b"41,989.13" in pdf and b"Alma Person" in pdf


# ----------------------------------------------------------------------
class TestSelfService:
    async def test_employee_sees_and_downloads_only_their_own(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        _run, payslips = await _generated(client, admin, world)
        alma = payslips[str(world.alma.id)]
        benny = payslips[str(world.benny.id)]

        headers = await _sign_in(client, world.alma_user)
        listed = await client.get(ME, headers=headers)
        assert listed.status_code == 200, listed.text
        rows = listed.json()["data"]["items"]
        assert [row["id"] for row in rows] == [alma["id"]]
        assert rows[0]["net_pay"] == "41989.13"

        detail = await client.get(f"{ME}/{alma['id']}", headers=headers)
        assert detail.status_code == 200, detail.text
        body = detail.json()["data"]
        assert body["employee_details"]["name"] == "Alma Person"
        assert body["employee_details"]["employee_code"] == world.alma.employee_code
        assert body["employee_details"]["bank_name"] is None
        assert body["pay_frequency"] == "monthly"
        assert body["period_start"] == "2026-07-01"
        assert body["amount_in_words"].startswith("Forty-one thousand nine hundred eighty-nine rupees")
        assert {line["name"] for line in body["earnings"]} >= {"Payslip Basic", "Payslip HRA", "Overtime"}
        assert [line["name"] for line in body["deductions"]] == ["Payslip Insurance"]
        # Nothing internal leaks: no audit, no run internals, no ids of others.
        assert "exception" not in detail.text
        assert str(world.benny.id) not in detail.text

        downloaded = await client.get(f"{ME}/{alma['id']}/download", headers=headers)
        assert downloaded.status_code == 200
        assert downloaded.content.startswith(b"%PDF")

        # Her own payslip also answers on the administrator path (it is hers).
        assert (
            await client.get(f"{PAYROLL}/employees/{world.alma.id}/payslips/{alma['id']}", headers=headers)
        ).status_code == 200

        # Benny's does not — not by his id, not by a forged one, not through
        # the administrator path.
        assert (await client.get(f"{ME}/{benny['id']}", headers=headers)).status_code == 404
        assert (await client.get(f"{ME}/{benny['id']}/download", headers=headers)).status_code == 404
        assert (await client.get(f"{ME}/{uuid.uuid4()}", headers=headers)).status_code == 404
        assert (
            await client.get(f"{PAYROLL}/employees/{world.benny.id}/payslips/{benny['id']}", headers=headers)
        ).status_code == 403
        # ...and pointing at her own employee id with Benny's payslip id is a 404, not a leak.
        assert (
            await client.get(f"{PAYROLL}/employees/{world.alma.id}/payslips/{benny['id']}", headers=headers)
        ).status_code == 404

        denied = (
            (
                await db_session.execute(
                    select(AuditLog).where(AuditLog.action == "payroll.payslip.access_denied")
                )
            )
            .scalars()
            .all()
        )
        assert len(denied) >= 3, "each refused attempt leaves a trace"

    async def test_history_is_newest_first_and_paginated(self, client: AsyncClient, world: World) -> None:
        admin = await _sign_in(client, world.admin_user)
        await _generated(client, admin, world, period=world.june)
        await _generated(client, admin, world)

        headers = await _sign_in(client, world.alma_user)
        rows = (await client.get(ME, headers=headers)).json()["data"]
        assert rows["meta"]["total_items"] == 2
        assert [row["payroll_month"] for row in rows["items"]] == ["July 2026", "June 2026"]
        assert rows["items"][0]["payslip_number"] == f"PS-2026-07-{world.alma.employee_code}"
        assert rows["items"][1]["payslip_number"] == f"PS-2026-06-{world.alma.employee_code}"

        page = (await client.get(ME, params={"page": 2, "page_size": 1}, headers=headers)).json()["data"]
        assert page["meta"]["total_items"] == 2
        assert [row["payroll_month"] for row in page["items"]] == ["June 2026"]

    async def test_employee_cannot_administer_payslips(self, client: AsyncClient, world: World) -> None:
        admin = await _sign_in(client, world.admin_user)
        run, payslips = await _generated(client, admin, world)
        alma = payslips[str(world.alma.id)]

        headers = await _sign_in(client, world.alma_user)
        assert (await client.get(f"{PAYROLL}/payslips", headers=headers)).status_code == 403
        assert (
            await client.post(f"{PAYROLL}/runs/{run['id']}/payslips/generate", headers=headers)
        ).status_code == 403
        assert (
            await client.post(f"{PAYROLL}/payslips/{alma['id']}/regenerate", headers=headers)
        ).status_code == 403
        assert (await client.get(f"{PAYROLL}/runs", headers=headers)).status_code == 403
        # There is no write surface on a payslip at all.
        assert (
            await client.put(f"{ME}/{alma['id']}", json={"net_pay": "99999.00"}, headers=headers)
        ).status_code in (404, 405)
        assert (await client.delete(f"{ME}/{alma['id']}", headers=headers)).status_code in (404, 405)


# ----------------------------------------------------------------------
class TestAccessModel:
    async def test_hr_follows_explicit_grants(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        run, payslips = await _generated(client, admin, world)
        alma = payslips[str(world.alma.id)]
        detail_url = f"{PAYROLL}/employees/{world.alma.id}/payslips/{alma['id']}"

        hr_user = await _account(db_session, "hr_admin", "ps_hr")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(f"{PAYROLL}/payslips", headers=headers)).status_code == 403
        assert (await client.get(detail_url, headers=headers)).status_code == 403
        assert (await client.get(f"{detail_url}/download", headers=headers)).status_code == 403
        assert (
            await client.post(f"{PAYROLL}/runs/{run['id']}/payslips/generate", headers=headers)
        ).status_code == 403

        await _grant(db_session, hr_user, "payroll:payslip_view")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(f"{PAYROLL}/payslips", headers=headers)).status_code == 200
        assert (await client.get(detail_url, headers=headers)).status_code == 200
        # Viewing is not downloading, and neither is generating.
        assert (await client.get(f"{detail_url}/download", headers=headers)).status_code == 403
        assert (
            await client.post(f"{PAYROLL}/payslips/{alma['id']}/regenerate", headers=headers)
        ).status_code == 403

        await _grant(db_session, hr_user, "payroll:payslip_download")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(f"{detail_url}/download", headers=headers)).status_code == 200

    async def test_manager_needs_team_view(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        _run, payslips = await _generated(client, admin, world)
        alma = payslips[str(world.alma.id)]
        benny = payslips[str(world.benny.id)]

        headers = await _sign_in(client, world.manager_user)
        assert (await client.get(f"{PAYROLL}/payslips", headers=headers)).status_code == 403
        assert (
            await client.get(f"{PAYROLL}/employees/{world.alma.id}/payslips/{alma['id']}", headers=headers)
        ).status_code == 403, "the reporting line alone grants nothing in payroll"

        await _grant(db_session, world.manager_user, "payroll:team_view")
        headers = await _sign_in(client, world.manager_user)
        assert (
            await client.get(f"{PAYROLL}/employees/{world.alma.id}/payslips/{alma['id']}", headers=headers)
        ).status_code == 200
        assert (
            await client.get(f"{PAYROLL}/employees/{world.benny.id}/payslips/{benny['id']}", headers=headers)
        ).status_code == 403
        assert (await client.get(f"{PAYROLL}/payslips", headers=headers)).status_code == 403

    async def test_admin_filters_the_register(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        await _generated(client, headers, world, period=world.june)
        _run, payslips = await _generated(client, headers, world)
        alma = payslips[str(world.alma.id)]

        everything = (await client.get(f"{PAYROLL}/payslips", headers=headers)).json()["data"]
        assert everything["meta"]["total_items"] == 5, "June: Alma + manager; July: + Benny"
        assert everything["items"][0]["payroll_month"] == "July 2026"

        by_month = (
            await client.get(f"{PAYROLL}/payslips", params={"month": "2026-06"}, headers=headers)
        ).json()["data"]
        assert by_month["meta"]["total_items"] == 2
        by_employee = (
            await client.get(
                f"{PAYROLL}/payslips", params={"employee_id": str(world.alma.id)}, headers=headers
            )
        ).json()["data"]
        assert by_employee["meta"]["total_items"] == 2
        by_number = (
            await client.get(
                f"{PAYROLL}/payslips", params={"payslip_number": alma["payslip_number"]}, headers=headers
            )
        ).json()["data"]
        assert [row["id"] for row in by_number["items"]] == [alma["id"]]
        assert (
            await client.get(f"{PAYROLL}/payslips", params={"month": "July"}, headers=headers)
        ).status_code == 422

    async def test_generic_employee_api_exposes_no_salary(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        await _generated(client, headers, world)
        profile = await client.get(f"{API}/employees/{world.alma.id}", headers=headers)
        assert profile.status_code == 200
        text = profile.text.lower()
        for needle in ("basic_salary", "annual_ctc", "net_pay", "gross_earnings", "payslip"):
            assert needle not in text, needle

    async def test_unauthenticated_requests_get_401(self, client: AsyncClient) -> None:
        assert (await client.get(ME)).status_code == 401
        assert (await client.get(f"{ME}/{uuid.uuid4()}/download")).status_code == 401
        assert (await client.get(f"{PAYROLL}/payslips")).status_code == 401


# ----------------------------------------------------------------------
class TestAudit:
    async def test_every_act_leaves_a_trail(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        _run, payslips = await _generated(client, admin, world)
        alma = payslips[str(world.alma.id)]
        url = f"{PAYROLL}/employees/{world.alma.id}/payslips/{alma['id']}"
        await client.get(url, headers=admin)
        await client.get(f"{url}/download", headers=admin)
        await client.post(f"{PAYROLL}/payslips/{alma['id']}/regenerate", headers=admin)
        mine = await _sign_in(client, world.alma_user)
        await client.get(f"{ME}/{uuid.uuid4()}", headers=mine)

        rows = (
            (await db_session.execute(select(AuditLog).where(AuditLog.action.like("payroll.payslip.%"))))
            .scalars()
            .all()
        )
        actions = {row.action for row in rows}
        assert actions >= {
            "payroll.payslip.generated",
            "payroll.payslip.viewed",
            "payroll.payslip.downloaded",
            "payroll.payslip.regenerated",
            "payroll.payslip.access_denied",
        }
        # Contexts name the payslip and the employee — never an amount.
        for row in rows:
            blob = str(row.context or {}) + (row.description or "")
            assert "41989" not in blob and "41,989" not in blob
