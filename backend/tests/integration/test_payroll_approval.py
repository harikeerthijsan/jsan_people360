"""Integration tests for payroll approval and finalization (Phase 6).

The world, inside July 2026:

* **Alma** — clean full-month record (42,489.13 gross, 41,989.13 net with
  overtime), the payroll that flows through the whole workflow.
* **Benny** — joins July 15th, prorated.
* **Dara** — excluded; her snapshot must say so.
* **Milo** — added only where a test needs a broken run: no compensation,
  so critical exceptions block the approval gates.

And the invariants: no state can be skipped, no gate can be talked around,
and a finalized payroll never changes — whatever happens to its sources.
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
        key=f"t_payapp_{suffix}",
        name=f"Payroll Approval Test {suffix}",
        description="Granted by the payroll approval test suite.",
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
    session: AsyncSession, label: str, *, joining: date, user: User | None = None
) -> Employee:
    suffix = uuid.uuid4().hex[:8]
    record = Employee(
        first_name=label.title(),
        last_name="Person",
        official_email=f"{label}.{suffix}@jsan.example",
        joining_date=joining,
        employment_status=EmploymentStatus.ACTIVE,
        user_id=user.id if user else None,
    )
    session.add(record)
    await session.flush()
    return record


class World:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)

    admin_user: User
    alma_user: User
    alma: Employee
    benny: Employee
    dara: Employee
    period: PayrollPeriod
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
        name="Approval Basic",
        code=f"ABAS{suffix}",
        component_type="earning",
        calculation_type="fixed",
        value=Decimal("30000"),
        proration_allowed=True,
        leave_impact=True,
        overtime_eligible=True,
    )
    hra = SalaryComponent(
        name="Approval HRA",
        code=f"AHRA{suffix}",
        component_type="earning",
        calculation_type="percentage",
        value=Decimal("40"),
        percentage_basis="basic",
        proration_allowed=True,
    )
    insurance = SalaryComponent(
        name="Approval Insurance",
        code=f"AINS{suffix}",
        component_type="deduction",
        calculation_type="fixed",
        value=Decimal("500"),
        proration_allowed=False,
    )
    db_session.add_all([basic, hra, insurance])
    await db_session.flush()

    structure = SalaryStructure(
        name=f"Approval Structure {suffix}", pay_frequency="monthly", currency="INR", status="active"
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

    admin_user = await _account(db_session, "admin", "app_adm")
    alma_user = await _account(db_session, "employee", "app_alma")
    alma = await _employee(db_session, "alma", joining=date(2024, 1, 5), user=alma_user)
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

    period = PayrollPeriod(
        name=f"July 2026 Approval {uuid.uuid4().hex[:6]}",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
        pay_date=date(2026, 7, 31),
        status="open",
    )
    db_session.add(period)
    await db_session.flush()

    return World(
        admin_user=admin_user,
        alma_user=alma_user,
        alma=alma,
        benny=benny,
        dara=dara,
        period=period,
        session=db_session,
    )


async def _add_milo(world: World) -> Employee:
    return await _employee(world.session, "milo", joining=date(2024, 6, 1))


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


async def _complete_review(client: AsyncClient, headers: dict[str, str], run_id: str) -> None:
    items = (await client.get(f"{PAYROLL}/runs/{run_id}/checklist", headers=headers)).json()["data"]
    for item in items:
        if item["completed"]:
            continue
        ticked = await client.patch(
            f"{PAYROLL}/runs/{run_id}/checklist/{item['item_key']}",
            json={"completed": True},
            headers=headers,
        )
        assert ticked.status_code == 200, ticked.text
    completed = await client.post(f"{PAYROLL}/runs/{run_id}/complete-review", headers=headers)
    assert completed.status_code == 200, completed.text


async def _submitted_run(client: AsyncClient, headers: dict[str, str], world: World) -> dict:
    run = await _calculated_run(client, headers, world)
    await _complete_review(client, headers, run["id"])
    submitted = await client.post(f"{PAYROLL}/runs/{run['id']}/submit-approval", headers=headers)
    assert submitted.status_code == 200, submitted.text
    return submitted.json()["data"]


async def _approved_run(client: AsyncClient, headers: dict[str, str], world: World) -> dict:
    run = await _submitted_run(client, headers, world)
    approved = await client.post(
        f"{PAYROLL}/runs/{run['id']}/approve",
        json={"comment": "Totals verified against June."},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    return approved.json()["data"]


async def _finalized_run(client: AsyncClient, headers: dict[str, str], world: World) -> dict:
    run = await _approved_run(client, headers, world)
    finalized = await client.post(f"{PAYROLL}/runs/{run['id']}/finalize", json={}, headers=headers)
    assert finalized.status_code == 200, finalized.text
    return finalized.json()["data"]


# ----------------------------------------------------------------------
class TestWorkflow:
    async def test_submission_requires_a_completed_review(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)

        refused = await client.post(f"{PAYROLL}/runs/{run['id']}/submit-approval", headers=headers)
        assert refused.status_code == 409
        assert refused.json()["errors"][0]["code"] == "not_review_complete"

        await _complete_review(client, headers, run["id"])
        submitted = await client.post(f"{PAYROLL}/runs/{run['id']}/submit-approval", headers=headers)
        assert submitted.status_code == 200, submitted.text
        body = submitted.json()["data"]
        assert body["status"] == "pending_approval"
        assert body["submitted_by_name"]
        assert body["submitted_at"]
        assert body["review_completed_by_name"]

        # The queue now lists it, enriched.
        queue = (await client.get(f"{PAYROLL}/approval", headers=headers)).json()["data"]["items"]
        assert [row["id"] for row in queue] == [run["id"]]
        # Submitting again is a state violation, not an idempotent no-op.
        again = await client.post(f"{PAYROLL}/runs/{run['id']}/submit-approval", headers=headers)
        assert again.status_code == 409

    async def test_blockers_are_stated_and_enforced(self, client: AsyncClient, world: World) -> None:
        """With Milo broken: the summary names every blocker, and the review
        gate upstream means the run can never even reach submission."""
        await _add_milo(world)
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)

        summary = (await client.get(f"{PAYROLL}/runs/{run['id']}/approval-summary", headers=headers)).json()[
            "data"
        ]
        assert summary["can_approve"] is False
        blockers = " ".join(summary["blockers"])
        assert "critical exception" in blockers
        assert "require review" in blockers
        assert "review has not been completed" in blockers
        assert summary["review"]["review_completed"] is False
        assert summary["review"]["critical_exceptions"] >= 1

        # Neither submission nor approval is reachable.
        assert (
            await client.post(f"{PAYROLL}/runs/{run['id']}/submit-approval", headers=headers)
        ).status_code == 409
        assert (
            await client.post(
                f"{PAYROLL}/runs/{run['id']}/approve", json={"comment": "Not yet"}, headers=headers
            )
        ).status_code == 409

    async def test_approval_requires_pending_state_and_a_comment(
        self, client: AsyncClient, world: World
    ) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        await _complete_review(client, headers, run["id"])

        early = await client.post(
            f"{PAYROLL}/runs/{run['id']}/approve", json={"comment": "Early"}, headers=headers
        )
        assert early.status_code == 409
        assert early.json()["errors"][0]["code"] == "not_pending_approval"

        submitted = await client.post(f"{PAYROLL}/runs/{run['id']}/submit-approval", headers=headers)
        assert submitted.status_code == 200
        no_comment = await client.post(f"{PAYROLL}/runs/{run['id']}/approve", json={}, headers=headers)
        assert no_comment.status_code == 422, "an approval without a comment is refused"

        approved = await client.post(
            f"{PAYROLL}/runs/{run['id']}/approve",
            json={"comment": "Verified against the reconciliation."},
            headers=headers,
        )
        assert approved.status_code == 200, approved.text
        body = approved.json()["data"]
        assert body["status"] == "approved"
        assert body["approved_by_name"]
        assert body["approval_comment"] == "Verified against the reconciliation."

        summary = (await client.get(f"{PAYROLL}/runs/{run['id']}/approval-summary", headers=headers)).json()[
            "data"
        ]
        actions = [step["action"] for step in summary["trail"]]
        assert actions == ["submitted", "approved"]
        assert all(step["actor_name"] for step in summary["trail"])
        assert summary["trail"][-1]["comment"] == "Verified against the reconciliation."

    async def test_return_requires_a_reason_and_reopens_the_workflow(
        self, client: AsyncClient, world: World
    ) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _submitted_run(client, headers, world)

        no_reason = await client.post(f"{PAYROLL}/runs/{run['id']}/return", json={}, headers=headers)
        assert no_reason.status_code == 422

        returned = await client.post(
            f"{PAYROLL}/runs/{run['id']}/return",
            json={"reason": "Overtime for Alma looks off — please re-verify."},
            headers=headers,
        )
        assert returned.status_code == 200, returned.text
        body = returned.json()["data"]
        assert body["status"] == "returned"
        assert body["return_reason"] == "Overtime for Alma looks off — please re-verify."
        assert body["returned_by_name"]

        # Correction goes through the normal workflow: recalculate, review
        # complete again, resubmit. Nothing is altered silently.
        recalculated = await client.post(f"{PAYROLL}/runs/{run['id']}/recalculate", headers=headers)
        assert recalculated.status_code == 200, recalculated.text
        await _complete_review(client, headers, run["id"])
        resubmitted = await client.post(f"{PAYROLL}/runs/{run['id']}/submit-approval", headers=headers)
        assert resubmitted.status_code == 200, resubmitted.text
        assert resubmitted.json()["data"]["status"] == "pending_approval"

        # The trail kept the whole cycle.
        summary = (await client.get(f"{PAYROLL}/runs/{run['id']}/approval-summary", headers=headers)).json()[
            "data"
        ]
        assert [step["action"] for step in summary["trail"]] == ["submitted", "returned", "submitted"]

    async def test_finalization_snapshots_and_locks(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _finalized_run(client, headers, world)
        assert run["status"] == "finalized"
        assert run["finalized_by_name"]
        assert run["finalized_at"]

        # The period locked with the run, and no second run can be opened.
        periods = (await client.get(f"{PAYROLL}/periods", params={"page_size": 100}, headers=headers)).json()[
            "data"
        ]["items"]
        period = next(row for row in periods if row["id"] == str(world.period.id))
        assert period["status"] == "finalized"
        duplicate = await client.post(
            f"{PAYROLL}/runs", json={"payroll_period_id": str(world.period.id)}, headers=headers
        )
        assert duplicate.status_code == 409

        # One immutable snapshot per employee, excluded ones included.
        snapshots = (await client.get(f"{PAYROLL}/runs/{run['id']}/snapshots", headers=headers)).json()[
            "data"
        ]
        by_employee = {row["employee_id"]: row for row in snapshots}
        assert set(by_employee) == {str(world.alma.id), str(world.benny.id), str(world.dara.id)}
        alma = by_employee[str(world.alma.id)]
        assert alma["final_net"] == "41989.13"
        assert alma["employee_name"] == "Alma Person"
        assert alma["approved_by_name"]
        assert alma["finalized_by_name"]
        assert [item["code"] for item in alma["line_items"]]
        assert by_employee[str(world.dara.id)]["status"] == "excluded"

        # Every mutation path is shut, with the lock's own error code.
        run_url = f"{PAYROLL}/runs/{run['id']}"
        recalc = await client.post(f"{run_url}/recalculate", headers=headers)
        assert recalc.status_code == 409
        assert recalc.json()["errors"][0]["code"] == "run_locked"
        adjust = await client.post(
            f"{run_url}/employees/{world.alma.id}/adjustments",
            json={"item_type": "earning", "name": "Late bonus", "amount": "100.00", "reason": "Late"},
            headers=headers,
        )
        assert adjust.status_code == 409
        assert adjust.json()["errors"][0]["code"] == "run_locked"
        assert (
            await client.patch(
                f"{run_url}/checklist/salaries_valid", json={"completed": False}, headers=headers
            )
        ).status_code == 409
        assert (
            await client.post(
                f"{run_url}/employees/{world.alma.id}/review-mark",
                json={"status": "reviewed"},
                headers=headers,
            )
        ).status_code == 409
        # There is no delete, and no generic status setter, to protect.
        assert (await client.delete(run_url, headers=headers)).status_code in (404, 405)
        assert (await client.patch(run_url, json={"status": "draft"}, headers=headers)).status_code in (
            404,
            405,
        )
        # And no further workflow transitions exist out of finalized.
        assert (await client.post(f"{run_url}/submit-approval", headers=headers)).status_code == 409
        assert (
            await client.post(f"{run_url}/approve", json={"comment": "Not yet"}, headers=headers)
        ).status_code == 409
        assert (await client.post(f"{run_url}/finalize", json={}, headers=headers)).status_code == 409

        # History shows the finalized run, read-only.
        history = (await client.get(f"{PAYROLL}/history", headers=headers)).json()["data"]["items"]
        assert [row["id"] for row in history] == [run["id"]]

    async def test_finalized_payroll_survives_source_changes(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        """Salary, attendance, leave — change them all after finalization:
        the snapshot and the run keep saying what was actually paid."""
        headers = await _sign_in(client, world.admin_user)
        run = await _finalized_run(client, headers, world)

        async def fetch_alma() -> dict:
            rows = (await client.get(f"{PAYROLL}/runs/{run['id']}/snapshots", headers=headers)).json()["data"]
            return next(row for row in rows if row["employee_id"] == str(world.alma.id))

        before = await fetch_alma()

        # Salary doubles, the employee is renamed, attendance and leave grow.
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
            name=f"Approval LOP {uuid.uuid4().hex[:6]}",
            code=f"XLOP{uuid.uuid4().hex[:4].upper()}",
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

        after = await fetch_alma()
        assert after == before, "the finalized snapshot must not move"
        assert after["employee_name"] == "Alma Person"
        assert after["final_net"] == "41989.13"

        # The run's own record view is equally frozen, and recalculation —
        # the only path source changes could travel — stays shut.
        record = (
            await client.get(f"{PAYROLL}/runs/{run['id']}/employees/{world.alma.id}", headers=headers)
        ).json()["data"]
        assert record["net_pay"] == "41989.13"
        assert (
            await client.post(f"{PAYROLL}/runs/{run['id']}/recalculate", headers=headers)
        ).status_code == 409

    async def test_state_transitions_cannot_be_bypassed(self, client: AsyncClient, world: World) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _calculated_run(client, headers, world)
        run_url = f"{PAYROLL}/runs/{run['id']}"

        # Calculated: only review completion moves it. Everything else 409s.
        assert (
            await client.post(f"{run_url}/approve", json={"comment": "Not yet"}, headers=headers)
        ).status_code == 409
        assert (
            await client.post(f"{run_url}/return", json={"reason": "Not yet"}, headers=headers)
        ).status_code == 409
        assert (await client.post(f"{run_url}/finalize", json={}, headers=headers)).status_code == 409

        await _complete_review(client, headers, run["id"])
        # Review complete: finalize still refused — approval cannot be skipped.
        finalize_early = await client.post(f"{run_url}/finalize", json={}, headers=headers)
        assert finalize_early.status_code == 409
        assert finalize_early.json()["errors"][0]["code"] == "not_approved"

        assert (await client.post(f"{run_url}/submit-approval", headers=headers)).status_code == 200
        # Pending approval: finalize refused until approved.
        assert (await client.post(f"{run_url}/finalize", json={}, headers=headers)).status_code == 409


# ----------------------------------------------------------------------
class TestAccessModel:
    async def test_hr_needs_explicit_grants_for_every_act(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        run = await _submitted_run(client, admin, world)
        run_url = f"{PAYROLL}/runs/{run['id']}"

        hr_user = await _account(db_session, "hr_admin", "app_hr")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(f"{PAYROLL}/approval", headers=headers)).status_code == 403
        assert (await client.get(f"{PAYROLL}/history", headers=headers)).status_code == 403
        assert (await client.get(f"{run_url}/approval-summary", headers=headers)).status_code == 403
        assert (
            await client.post(f"{run_url}/approve", json={"comment": "Mine"}, headers=headers)
        ).status_code == 403
        assert (
            await client.post(f"{run_url}/return", json={"reason": "Mine"}, headers=headers)
        ).status_code == 403
        assert (await client.post(f"{run_url}/finalize", json={}, headers=headers)).status_code == 403

        # With the explicit grant, HR approves according to that permission.
        await _grant(db_session, hr_user, "payroll:approve", "payroll:approval_view")
        headers = await _sign_in(client, hr_user)
        assert (await client.get(f"{PAYROLL}/approval", headers=headers)).status_code == 200
        approved = await client.post(
            f"{run_url}/approve", json={"comment": "Reviewed and correct."}, headers=headers
        )
        assert approved.status_code == 200, approved.text
        # Approval is not finalization: that grant was not given.
        assert (await client.post(f"{run_url}/finalize", json={}, headers=headers)).status_code == 403

    async def test_managers_and_employees_get_nothing(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        admin = await _sign_in(client, world.admin_user)
        run = await _finalized_run(client, admin, world)
        run_url = f"{PAYROLL}/runs/{run['id']}"

        manager_user = await _account(db_session, "manager", "app_mgr")
        headers = await _sign_in(client, manager_user)
        assert (await client.get(f"{PAYROLL}/approval", headers=headers)).status_code == 403
        assert (
            await client.post(f"{run_url}/approve", json={"comment": "Mine"}, headers=headers)
        ).status_code == 403
        assert (await client.post(f"{run_url}/finalize", json={}, headers=headers)).status_code == 403

        headers = await _sign_in(client, world.alma_user)
        assert (await client.get(f"{PAYROLL}/approval", headers=headers)).status_code == 403
        assert (await client.get(f"{PAYROLL}/history", headers=headers)).status_code == 403
        assert (await client.get(f"{run_url}/snapshots", headers=headers)).status_code == 403
        assert (await client.get(f"{run_url}/approval-summary", headers=headers)).status_code == 403

        # Her own finalized payroll still answers through self-service — and
        # only hers.
        mine = await client.get(f"{API}/me/payroll/records", headers=headers)
        assert mine.status_code == 200
        rows = mine.json()["data"]
        assert [row["employee"]["id"] for row in rows] == [str(world.alma.id)]
        assert rows[0]["final_net"] == "41989.13"

    async def test_unauthenticated_requests_get_401(self, client: AsyncClient) -> None:
        run_url = f"{PAYROLL}/runs/{uuid.uuid4()}"
        assert (await client.get(f"{PAYROLL}/approval")).status_code == 401
        assert (await client.get(f"{PAYROLL}/history")).status_code == 401
        assert (await client.post(f"{run_url}/approve", json={"comment": "Not yet"})).status_code == 401
        assert (await client.post(f"{run_url}/finalize", json={})).status_code == 401


# ----------------------------------------------------------------------
class TestAudit:
    async def test_the_whole_workflow_leaves_a_trail(
        self, client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, world.admin_user)
        run = await _submitted_run(client, headers, world)
        await client.post(
            f"{PAYROLL}/runs/{run['id']}/return", json={"reason": "Check once more."}, headers=headers
        )
        recalculated = await client.post(f"{PAYROLL}/runs/{run['id']}/recalculate", headers=headers)
        assert recalculated.status_code == 200
        await _complete_review(client, headers, run["id"])
        await client.post(f"{PAYROLL}/runs/{run['id']}/submit-approval", headers=headers)
        await client.post(
            f"{PAYROLL}/runs/{run['id']}/approve", json={"comment": "Now correct."}, headers=headers
        )
        await client.post(f"{PAYROLL}/runs/{run['id']}/finalize", json={}, headers=headers)
        # A locked-modification attempt after finalization is itself audited,
        # and the audit row survives the request's rollback.
        assert (
            await client.post(f"{PAYROLL}/runs/{run['id']}/recalculate", headers=headers)
        ).status_code == 409

        actions = {
            row.action
            for row in (
                (await db_session.execute(select(AuditLog).where(AuditLog.action.like("payroll.run.%"))))
                .scalars()
                .all()
            )
        }
        assert "payroll.run.submitted_for_approval" in actions
        assert "payroll.run.returned" in actions
        assert "payroll.run.approved" in actions
        assert "payroll.run.finalized" in actions
        assert "payroll.run.locked_modification_attempt" in actions
