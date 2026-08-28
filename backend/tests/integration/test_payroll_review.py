"""Integration tests for payroll review and adjustments (Phase 5).

The world, inside July 2026 (with June behind it for the comparison):

* **Alma** — clean full-month record: 42,489.13 gross, 40,053.65 net. The
  canvas for adjustments, marking and the reconciliation.
* **Benny** — joins July 15th: absent from June, so the comparison must flag
  him as new rather than pretend a difference of zero.
* **Dara** — excluded from payroll: adjustments against her are refused.
* **Milo** — added only by the tests that need him: no compensation, so the
  engine generates critical exceptions and the review cannot complete.

And the invariants: originals are never edited, exceptions and adjustments
are never deleted, completion is gated, and nothing is auto-rejected.
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
from app.models.workforce import AttendanceRecord

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
PAYROLL = f"{API}/payroll"
PASSWORD = "Str0ng!Passw0rd"

JULY_START = date(2026, 7, 1)
JULY_END = date(2026, 7, 31)


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
        key=f"t_payrev_{suffix}",
        name=f"Payroll Review Test {suffix}",
        description="Granted by the payroll review test suite.",
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
    structure: SalaryStructure
    session: AsyncSession


@pytest.fixture
async def world(db_session: AsyncSession) -> World:
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

    suffix = uuid.uuid4().hex[:6].upper()
    basic = SalaryComponent(
        name="Review Basic",
        code=f"RBAS{suffix}",
        component_type="earning",
        calculation_type="fixed",
        value=Decimal("30000"),
        proration_allowed=True,
        leave_impact=True,
        overtime_eligible=True,
    )
    hra = SalaryComponent(
        name="Review HRA",
        code=f"RHRA{suffix}",
        component_type="earning",
        calculation_type="percentage",
        value=Decimal("40"),
        percentage_basis="basic",
        proration_allowed=True,
    )
    insurance = SalaryComponent(
        name="Review Insurance",
        code=f"RINS{suffix}",
        component_type="deduction",
        calculation_type="fixed",
        value=Decimal("500"),
        proration_allowed=False,
    )
    db_session.add_all([basic, hra, insurance])
    await db_session.flush()

    structure = SalaryStructure(
        name=f"Review Structure {suffix}", pay_frequency="monthly", currency="INR", status="active"
    )
    db_session.add(structure)
    await db_session.flush()

    async def compensation(employee: Employee, *, effective_from: date) -> EmployeeCompensation:
        gross = Decimal("42000")
        comp = EmployeeCompensation(
            employee_id=employee.id,
            salary_structure_id=structure.id,
            currency="INR",
            annual_ctc=gross * 12,
            annual_gross=gross * 12,
            monthly_gross=gross,
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

    admin_user = await _account(db_session, "admin", "rev_adm")
    manager_user = await _account(db_session, "manager", "rev_mgr")
    manager = await _employee(db_session, "manager", joining=date(2023, 1, 1), user=manager_user)
    await compensation(manager, effective_from=date(2026, 1, 1))

    alma_user = await _account(db_session, "employee", "rev_alma")
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
        name=f"June 2026 Review {uuid.uuid4().hex[:6]}",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        pay_date=date(2026, 6, 30),
        status="open",
    )
    period = PayrollPeriod(
        name=f"July 2026 Review {uuid.uuid4().hex[:6]}",
        start_date=JULY_START,
        end_date=JULY_END,
        pay_date=JULY_END,
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
        structure=structure,
        session=db_session,
    )


async def _add_milo(world: World) -> Employee:
    """An employee with no compensation: the engine's critical-exception case."""
    return await _employee(world.session, "milo", joining=date(2024, 6, 1))


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


async def _record(client: AsyncClient, headers: dict[str, str], run_id: str, employee_id: uuid.UUID) -> dict:
    response = await client.get(f"{PAYROLL}/runs/{run_id}/employees/{employee_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _adjust(
    client: AsyncClient,
    headers: dict[str, str],
    run_id: str,
    employee_id: uuid.UUID,
    *,
    item_type: str = "earning",
    amount: str = "1000.00",
    name: str = "Spot bonus",
    reason: str = "Recognition for the release",
) -> dict:
    response = await client.post(
        f"{PAYROLL}/runs/{run_id}/employees/{employee_id}/adjustments",
        json={"item_type": item_type, "name": name, "amount": amount, "reason": reason},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _complete_checklist(client: AsyncClient, headers: dict[str, str], run_id: str) -> None:
    items = (await client.get(f"{PAYROLL}/runs/{run_id}/checklist", headers=headers)).json()["data"]
    for item in items:
        response = await client.patch(
            f"{PAYROLL}/runs/{run_id}/checklist/{item['item_key']}",
            json={"completed": True},
            headers=headers,
        )
        assert response.status_code == 200, response.text


# ----------------------------------------------------------------------
class TestExceptions:
    async def test_engine_generates_graded_exceptions(self, client: AsyncClient, world: World) -> None:
        """Milo has no salary: the engine refuses him and says so as critical
        exceptions, and the run's summary carries the open counts."""
        milo = await _add_milo(world)
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)

        listed = await client.get(f"{PAYROLL}/runs/{run['id']}/exceptions", headers=headers)
        assert listed.status_code == 200, listed.text
        rows = listed.json()["data"]
        milos = [row for row in rows if row["employee"]["id"] == str(milo.id)]
        assert milos, "the refused employee must surface as exceptions"
        assert all(row["status"] == "open" for row in milos)
        assert any(row["severity"] == "critical" for row in milos)
        assert {row["exception_type"] for row in milos} <= {"missing_salary", "missing_input"}
        # Worst first.
        severities = [row["severity"] for row in rows]
        assert severities == sorted(severities)

        summary = (await client.get(f"{PAYROLL}/runs/{run['id']}", headers=headers)).json()["data"]
        assert summary["open_exception_count"] >= 1
        assert summary["open_critical_count"] >= 1

        # Severity filter narrows, never invents.
        critical = await client.get(
            f"{PAYROLL}/runs/{run['id']}/exceptions", params={"severity": "critical"}, headers=headers
        )
        assert all(row["severity"] == "critical" for row in critical.json()["data"])

    async def test_resolution_is_recorded_never_deleted(self, client: AsyncClient, world: World) -> None:
        await _add_milo(world)
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        target = (await client.get(f"{PAYROLL}/runs/{run['id']}/exceptions", headers=headers)).json()["data"][
            0
        ]

        resolved = await client.post(
            f"{PAYROLL}/runs/{run['id']}/exceptions/{target['id']}/resolve",
            json={"resolution": "Contractor — payroll handled off-cycle", "notes": "Confirmed with HR"},
            headers=headers,
        )
        assert resolved.status_code == 200, resolved.text
        body = resolved.json()["data"]
        assert body["status"] == "resolved"
        assert body["resolution"] == "Contractor — payroll handled off-cycle"
        assert body["resolved_by_name"]
        assert body["resolved_at"]

        # Still listed — resolved, not gone.
        rows = (await client.get(f"{PAYROLL}/runs/{run['id']}/exceptions", headers=headers)).json()["data"]
        assert any(row["id"] == target["id"] and row["status"] == "resolved" for row in rows)

        again = await client.post(
            f"{PAYROLL}/runs/{run['id']}/exceptions/{target['id']}/resolve",
            json={"resolution": "Twice"},
            headers=headers,
        )
        assert again.status_code == 409
        assert again.json()["errors"][0]["code"] == "exception_resolved"

    async def test_resolutions_survive_recalculation(self, client: AsyncClient, world: World) -> None:
        """Recalculating regenerates the exceptions; one already resolved and
        unchanged comes back resolved, with its resolution intact."""
        await _add_milo(world)
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        rows = (await client.get(f"{PAYROLL}/runs/{run['id']}/exceptions", headers=headers)).json()["data"]
        target = rows[0]
        await client.post(
            f"{PAYROLL}/runs/{run['id']}/exceptions/{target['id']}/resolve",
            json={"resolution": "Reviewed and waived"},
            headers=headers,
        )

        recalculated = await client.post(f"{PAYROLL}/runs/{run['id']}/recalculate", headers=headers)
        assert recalculated.status_code == 200, recalculated.text

        after = (await client.get(f"{PAYROLL}/runs/{run['id']}/exceptions", headers=headers)).json()["data"]
        match = next(
            row
            for row in after
            if row["employee"]["id"] == target["employee"]["id"]
            and row["exception_type"] == target["exception_type"]
            and row["description"] == target["description"]
        )
        assert match["status"] == "resolved"
        assert match["resolution"] == "Reviewed and waived"
        # The other, untouched exceptions come back open.
        assert any(row["status"] == "open" for row in after)


# ----------------------------------------------------------------------
class TestAdjustments:
    async def test_adjustment_adds_and_preserves_the_original(
        self, client: AsyncClient, world: World
    ) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        before = await _record(client, headers, run["id"], world.alma.id)
        assert before["gross_earnings"] == "42489.13"

        adjustment = await _adjust(client, headers, run["id"], world.alma.id)
        assert adjustment["status"] == "active"
        assert adjustment["previous_net"] == "41989.13"
        assert adjustment["new_net"] == "42989.13"

        after = await _record(client, headers, run["id"], world.alma.id)
        # Original untouched; adjustment and final derived alongside it.
        assert after["gross_earnings"] == "42489.13"
        assert after["net_pay"] == "41989.13"
        assert after["adjustment_earnings"] == "1000.00"
        assert after["final_gross"] == "43489.13"
        assert after["final_net"] == "42989.13"
        assert [a["name"] for a in after["adjustments"]] == ["Spot bonus"]

        # The run's headline totals follow the final amounts.
        summary = (await client.get(f"{PAYROLL}/runs/{run['id']}", headers=headers)).json()["data"]
        assert Decimal(summary["total_net"]) == Decimal(run["total_net"]) + Decimal("1000")

    async def test_adjustment_validation(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        url = f"{PAYROLL}/runs/{run['id']}/employees/{world.alma.id}/adjustments"

        for amount in ("0", "-100"):
            response = await client.post(
                url,
                json={"item_type": "earning", "name": "Bad", "amount": amount, "reason": "Because"},
                headers=headers,
            )
            assert response.status_code == 422, f"amount {amount} must be refused"
        missing_reason = await client.post(
            url,
            json={"item_type": "earning", "name": "Bad", "amount": "100.00", "reason": ""},
            headers=headers,
        )
        assert missing_reason.status_code == 422

    async def test_adjustments_survive_recalculation(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        await _adjust(client, headers, run["id"], world.alma.id)

        recalculated = await client.post(f"{PAYROLL}/runs/{run['id']}/recalculate", headers=headers)
        assert recalculated.status_code == 200, recalculated.text

        after = await _record(client, headers, run["id"], world.alma.id)
        assert after["adjustment_earnings"] == "1000.00"
        assert after["final_net"] == "42989.13"
        assert [a["status"] for a in after["adjustments"]] == ["active"]
        summary = recalculated.json()["data"]["run"]
        assert Decimal(summary["total_net"]) == Decimal(run["total_net"]) + Decimal("1000")

    async def test_cancellation_is_marked_never_deleted(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        adjustment = await _adjust(client, headers, run["id"], world.alma.id)

        cancelled = await client.post(
            f"{PAYROLL}/runs/{run['id']}/adjustments/{adjustment['id']}/cancel",
            json={"reason": "Entered against the wrong employee"},
            headers=headers,
        )
        assert cancelled.status_code == 200, cancelled.text
        body = cancelled.json()["data"]
        assert body["status"] == "cancelled"
        assert body["cancel_reason"] == "Entered against the wrong employee"
        assert body["cancelled_at"]

        # Backed out of the record, kept in the history.
        record = await _record(client, headers, run["id"], world.alma.id)
        assert record["adjustment_earnings"] == "0.00"
        assert record["final_net"] == record["net_pay"]
        listed = (await client.get(f"{PAYROLL}/runs/{run['id']}/adjustments", headers=headers)).json()["data"]
        assert any(row["id"] == adjustment["id"] and row["status"] == "cancelled" for row in listed)

        again = await client.post(
            f"{PAYROLL}/runs/{run['id']}/adjustments/{adjustment['id']}/cancel",
            json={"reason": "Twice"},
            headers=headers,
        )
        assert again.status_code == 409

    async def test_excluded_records_cannot_be_adjusted(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        refused = await client.post(
            f"{PAYROLL}/runs/{run['id']}/employees/{world.dara.id}/adjustments",
            json={"item_type": "earning", "name": "Bonus", "amount": "100.00", "reason": "Because"},
            headers=headers,
        )
        assert refused.status_code == 409
        assert refused.json()["errors"][0]["code"] == "record_excluded"


# ----------------------------------------------------------------------
class TestReviewFlow:
    async def test_record_marking(self, client: AsyncClient, world: World) -> None:
        milo = await _add_milo(world)
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        url = f"{PAYROLL}/runs/{run['id']}/employees"

        marked = await client.post(
            f"{url}/{world.alma.id}/review-mark", json={"status": "reviewed"}, headers=headers
        )
        assert marked.status_code == 200, marked.text
        record = await _record(client, headers, run["id"], world.alma.id)
        assert record["status"] == "reviewed"

        # Only the two review judgements are settable by hand.
        invalid = await client.post(
            f"{url}/{world.alma.id}/review-mark", json={"status": "excluded"}, headers=headers
        )
        assert invalid.status_code == 422
        # An engine-flagged record is not markable — fix the cause instead.
        flagged = await client.post(
            f"{url}/{milo.id}/review-mark", json={"status": "reviewed"}, headers=headers
        )
        assert flagged.status_code == 409
        assert flagged.json()["errors"][0]["code"] == "record_not_markable"

    async def test_checklist_seeds_and_updates(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)

        items = (await client.get(f"{PAYROLL}/runs/{run['id']}/checklist", headers=headers)).json()["data"]
        assert len(items) == 9
        assert all(not item["completed"] for item in items)

        updated = await client.patch(
            f"{PAYROLL}/runs/{run['id']}/checklist/{items[0]['item_key']}",
            json={"completed": True},
            headers=headers,
        )
        assert updated.status_code == 200, updated.text
        first = updated.json()["data"][0]
        assert first["completed"] is True
        assert first["completed_by_name"]
        assert first["completed_at"]

    async def test_completion_is_gated(self, client: AsyncClient, world: World) -> None:
        """With Milo broken: critical exceptions open, his record requiring
        review, the checklist untouched — completion is refused and the
        readiness endpoint names every blocker."""
        await _add_milo(world)
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)

        readiness = (
            await client.get(f"{PAYROLL}/runs/{run['id']}/review-readiness", headers=headers)
        ).json()["data"]
        assert readiness["can_complete"] is False
        assert readiness["open_critical_exceptions"] >= 1
        assert readiness["records_requiring_review"] >= 1
        assert len(readiness["incomplete_checklist_items"]) == 9

        refused = await client.post(f"{PAYROLL}/runs/{run['id']}/complete-review", headers=headers)
        assert refused.status_code == 409
        assert refused.json()["errors"][0]["code"] == "review_not_ready"
        # Ticking the checklist alone does not open the gate.
        await _complete_checklist(client, headers, run["id"])
        still = await client.post(f"{PAYROLL}/runs/{run['id']}/complete-review", headers=headers)
        assert still.status_code == 409

    async def test_completion_promotes_the_run_and_its_records(
        self, client: AsyncClient, world: World
    ) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        assert run["status"] == "calculated"
        await _complete_checklist(client, headers, run["id"])

        completed = await client.post(f"{PAYROLL}/runs/{run['id']}/complete-review", headers=headers)
        assert completed.status_code == 200, completed.text

        summary = (await client.get(f"{PAYROLL}/runs/{run['id']}", headers=headers)).json()["data"]
        assert summary["status"] == "review_complete"
        alma = await _record(client, headers, run["id"], world.alma.id)
        assert alma["status"] == "ready_for_approval"
        dara = await _record(client, headers, run["id"], world.dara.id)
        assert dara["status"] == "excluded", "excluded records stay excluded"

        # Her payslip still answers in self-service after promotion.
        mine = await client.get(f"{API}/me/payroll/records", headers=await _sign_in(client, world.alma_user))
        assert [row["employee"]["id"] for row in mine.json()["data"]] == [str(world.alma.id)]

        # A completed review is not a locked one: an adjustment reopens it.
        await _adjust(client, headers, run["id"], world.alma.id)
        reopened = (await client.get(f"{PAYROLL}/runs/{run['id']}", headers=headers)).json()["data"]
        assert reopened["status"] == "in_review"

    async def test_recalculation_resets_the_checklist(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        await _complete_checklist(client, headers, run["id"])

        recalculated = await client.post(f"{PAYROLL}/runs/{run['id']}/recalculate", headers=headers)
        assert recalculated.status_code == 200, recalculated.text
        items = (await client.get(f"{PAYROLL}/runs/{run['id']}/checklist", headers=headers)).json()["data"]
        assert all(
            not item["completed"] for item in items
        ), "the numbers the reviewer ticked off no longer exist"

    async def test_comments_are_append_only(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)

        on_run = await client.post(
            f"{PAYROLL}/runs/{run['id']}/comments",
            json={"comment": "Totals look right against June."},
            headers=headers,
        )
        assert on_run.status_code == 201, on_run.text
        assert on_run.json()["data"]["author_name"]
        on_alma = await client.post(
            f"{PAYROLL}/runs/{run['id']}/comments",
            json={"comment": "Overtime verified by hand.", "employee_id": str(world.alma.id)},
            headers=headers,
        )
        assert on_alma.status_code == 201, on_alma.text

        rows = (await client.get(f"{PAYROLL}/runs/{run['id']}/comments", headers=headers)).json()["data"]
        assert len(rows) == 2
        scoped = (
            await client.get(
                f"{PAYROLL}/runs/{run['id']}/comments",
                params={"employee_id": str(world.alma.id)},
                headers=headers,
            )
        ).json()["data"]
        assert [row["comment"] for row in scoped] == ["Overtime verified by hand."]
        # No editing surface exists at all.
        comment_id = rows[0]["id"]
        assert (
            await client.delete(f"{PAYROLL}/runs/{run['id']}/comments/{comment_id}", headers=headers)
        ).status_code in (404, 405)


# ----------------------------------------------------------------------
class TestReconciliationAndComparison:
    async def test_reconciliation_totals(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        await _adjust(client, headers, run["id"], world.alma.id, amount="1000.00")
        await _adjust(
            client,
            headers,
            run["id"],
            world.alma.id,
            item_type="deduction",
            amount="200.00",
            name="Canteen recovery",
            reason="July canteen dues",
        )
        doomed = await _adjust(
            client, headers, run["id"], world.benny.id, amount="300.00", name="To be cancelled"
        )
        await client.post(
            f"{PAYROLL}/runs/{run['id']}/adjustments/{doomed['id']}/cancel",
            json={"reason": "Withdrawn"},
            headers=headers,
        )

        body = (await client.get(f"{PAYROLL}/runs/{run['id']}/reconciliation", headers=headers)).json()[
            "data"
        ]
        assert Decimal(body["original_gross"]) == Decimal(run["total_gross"])
        assert body["adjustment_earnings"] == "1000.00"
        assert body["adjustment_deductions"] == "200.00"
        assert Decimal(body["final_gross"]) == Decimal(run["total_gross"]) + Decimal("1000")
        assert Decimal(body["final_net"]) == Decimal(run["total_net"]) + Decimal("800")
        assert body["net_adjustment"] == "800.00"
        assert body["adjustment_count"] == 2
        assert body["cancelled_adjustment_count"] == 1
        assert body["total_adjustment_amount"] == "1200.00"
        assert body["employees_affected"] == 1

    async def test_comparison_highlights_but_never_rejects(self, client: AsyncClient, world: World) -> None:
        """June behind July: Alma's small dip is not notable, a big July
        adjustment makes it notable, and Benny — absent in June — is flagged
        as new. Nothing changes status because of any of it."""
        headers = await _sign_in(client, world.admin_user)
        await _calculated_run(client, headers, world, period=world.june)
        run = await _calculated_run(client, headers, world)

        rows = (await client.get(f"{PAYROLL}/runs/{run['id']}/comparison", headers=headers)).json()["data"]
        by_id = {row["employee"]["id"]: row for row in rows}
        alma = by_id[str(world.alma.id)]
        # June: 42000 gross - 500 = 41500 net. July adds 489.13 overtime —
        # a small rise, well under the 20% threshold.
        assert alma["previous_net"] == "41500.00"
        assert alma["current_net"] == "41989.13"
        assert alma["notable"] is False
        benny = by_id[str(world.benny.id)]
        assert benny["previous_net"] is None
        assert benny["notable"] is True

        # A 20,000 adjustment pushes Alma past the 20% threshold.
        await _adjust(client, headers, run["id"], world.alma.id, amount="20000.00", name="Retention award")
        rows = (await client.get(f"{PAYROLL}/runs/{run['id']}/comparison", headers=headers)).json()["data"]
        alma = next(row for row in rows if row["employee"]["id"] == str(world.alma.id))
        assert alma["current_net"] == "61989.13"
        assert alma["notable"] is True
        # Highlighted, not rejected: the record's status is untouched.
        record = await _record(client, headers, run["id"], world.alma.id)
        assert record["status"] == "calculated"


# ----------------------------------------------------------------------
class TestAccessModel:
    async def test_review_surfaces_require_explicit_grants(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, admin, world)
        adjustment = await _adjust(client, admin, run["id"], world.alma.id)

        hr_user = await _account(db_session, "hr_admin", "rev_hr")
        headers = await _sign_in(client, hr_user)
        run_url = f"{PAYROLL}/runs/{run['id']}"
        # HR gets nothing automatically — reads included.
        for url in (
            f"{run_url}/exceptions",
            f"{run_url}/adjustments",
            f"{run_url}/checklist",
            f"{run_url}/review-readiness",
            f"{run_url}/reconciliation",
            f"{run_url}/comparison",
            f"{run_url}/comments",
        ):
            assert (await client.get(url, headers=headers)).status_code == 403, url

        # review_view alone reads nothing org-wide without employees:view_all.
        # (A roleless account: the seeded hr_admin role already carries
        # employees:view_all, which is exactly the conjunction under test.)
        viewer = await _account(db_session, None, "rev_viewer")
        await _grant(db_session, viewer, "payroll:review_view")
        headers = await _sign_in(client, viewer)
        assert (await client.get(f"{run_url}/exceptions", headers=headers)).status_code == 403

        await _grant(db_session, hr_user, "payroll:review_view")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(f"{run_url}/exceptions", headers=headers)).status_code == 200
        assert (await client.get(f"{run_url}/reconciliation", headers=headers)).status_code == 200
        # Reading is not resolving, adjusting or signing off.
        exceptions = (await client.get(f"{run_url}/exceptions", headers=headers)).json()["data"]
        if exceptions:
            assert (
                await client.post(
                    f"{run_url}/exceptions/{exceptions[0]['id']}/resolve",
                    json={"resolution": "No"},
                    headers=headers,
                )
            ).status_code == 403
        assert (
            await client.post(
                f"{run_url}/employees/{world.alma.id}/adjustments",
                json={"item_type": "earning", "name": "No", "amount": "1.00", "reason": "Nope"},
                headers=headers,
            )
        ).status_code == 403
        assert (
            await client.post(
                f"{run_url}/adjustments/{adjustment['id']}/cancel",
                json={"reason": "Nope"},
                headers=headers,
            )
        ).status_code == 403
        assert (await client.post(f"{run_url}/complete-review", headers=headers)).status_code == 403
        assert (
            await client.patch(
                f"{run_url}/checklist/salaries_valid", json={"completed": True}, headers=headers
            )
        ).status_code == 403

    async def test_an_employee_cannot_reach_the_review(self, client: AsyncClient, world: World) -> None:
        admin = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, admin, world)

        headers = await _sign_in(client, world.alma_user)
        run_url = f"{PAYROLL}/runs/{run['id']}"
        assert (await client.get(f"{run_url}/exceptions", headers=headers)).status_code == 403
        assert (await client.get(f"{run_url}/reconciliation", headers=headers)).status_code == 403
        assert (
            await client.post(
                f"{run_url}/employees/{world.alma.id}/adjustments",
                json={"item_type": "earning", "name": "Mine", "amount": "9999.00", "reason": "Mine"},
                headers=headers,
            )
        ).status_code == 403, "no employee adjusts their own pay"

    async def test_adjustment_scope_stops_at_the_team(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        """The manager holds adjustment_create; Alma reports to them, Benny
        does not. The permission reaches exactly as far as the scope."""
        admin = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, admin, world)

        await _grant(db_session, world.manager_user, "payroll:adjustment_create")
        headers = await _sign_in(client, world.manager_user)
        allowed = await client.post(
            f"{PAYROLL}/runs/{run['id']}/employees/{world.alma.id}/adjustments",
            json={"item_type": "earning", "name": "Team award", "amount": "500.00", "reason": "Q2 award"},
            headers=headers,
        )
        assert allowed.status_code == 201, allowed.text
        forbidden = await client.post(
            f"{PAYROLL}/runs/{run['id']}/employees/{world.benny.id}/adjustments",
            json={"item_type": "earning", "name": "Team award", "amount": "500.00", "reason": "Q2 award"},
            headers=headers,
        )
        assert forbidden.status_code == 403

    async def test_unauthenticated_requests_get_401(self, client: AsyncClient, world: World) -> None:
        run_url = f"{PAYROLL}/runs/{uuid.uuid4()}"
        assert (await client.get(f"{run_url}/exceptions")).status_code == 401
        assert (await client.get(f"{run_url}/reconciliation")).status_code == 401
        assert (await client.post(f"{run_url}/complete-review")).status_code == 401


# ----------------------------------------------------------------------
class TestAudit:
    async def test_review_actions_leave_a_trail(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        adjustment = await _adjust(client, headers, run["id"], world.alma.id)
        await client.post(
            f"{PAYROLL}/runs/{run['id']}/adjustments/{adjustment['id']}/cancel",
            json={"reason": "Withdrawn"},
            headers=headers,
        )
        await client.post(
            f"{PAYROLL}/runs/{run['id']}/employees/{world.alma.id}/review-mark",
            json={"status": "reviewed"},
            headers=headers,
        )
        await client.patch(
            f"{PAYROLL}/runs/{run['id']}/checklist/salaries_valid",
            json={"completed": True},
            headers=headers,
        )
        await client.post(f"{PAYROLL}/runs/{run['id']}/comments", json={"comment": "Noted."}, headers=headers)

        actions = {
            row.action
            for row in (
                (await db_session.execute(select(AuditLog).where(AuditLog.action.like("payroll.%"))))
                .scalars()
                .all()
            )
        }
        assert "payroll.adjustment.created" in actions
        assert "payroll.adjustment.cancelled" in actions
        assert "payroll.record.review_marked" in actions
        assert "payroll.review.checklist_updated" in actions
        assert "payroll.review.commented" in actions
