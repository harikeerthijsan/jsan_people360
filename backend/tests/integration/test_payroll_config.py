"""Integration tests for payroll configuration and pay rules (Phase 2).

Two propositions carry the module, and most of what follows is refusals.

**Configuration is never silently overwritten.** Every update needs a reason
and an effective date, writes one history row per changed field, and the
history has no write surface — the tests assert 405, not 403, because the
routes do not exist.

**Nobody below Administrator holds any of it.** Employee, seeded Manager and
seeded HR Admin are refused every configuration read and write; a custom
grant opens exactly what it names and nothing beside it.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.user import User
from app.models.workforce import LeaveType

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
        assert role is not None, f"the {role_key} role should be seeded"
        session.add(UserRole(user_id=user.id, role_id=role.id))
        await session.flush()
    return user


async def _grant(session: AsyncSession, user: User, *codes: str) -> None:
    suffix = uuid.uuid4().hex[:8]
    role = Role(
        key=f"t_payconf_{suffix}",
        name=f"Payroll Config Test {suffix}",
        description="Granted by the payroll configuration test suite.",
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


async def _leave_type(session: AsyncSession, *, is_paid: bool) -> LeaveType:
    suffix = uuid.uuid4().hex[:6].upper()
    row = LeaveType(
        name=f"Test Leave {suffix}",
        code=f"TL{suffix}",
        annual_allocation=12,
        is_paid=is_paid,
    )
    session.add(row)
    await session.flush()
    return row


def _period_body(**overrides: object) -> dict:
    body = {
        "name": f"Period {uuid.uuid4().hex[:8]}",
        "start_date": "2027-08-01",
        "end_date": "2027-08-31",
        "pay_date": "2027-08-31",
    }
    body.update(overrides)
    return body


@pytest.fixture
async def admin_headers(client: AsyncClient, db_session: AsyncSession) -> dict[str, str]:
    return await _sign_in(client, await _account(db_session, "admin", "conf_adm"))


# ----------------------------------------------------------------------
class TestConfiguration:
    async def test_defaults_are_the_briefs(self, client: AsyncClient, admin_headers: dict) -> None:
        response = await client.get(f"{PAYROLL}/config", headers=admin_headers)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["pay_frequency"] == "monthly"
        assert data["currency"] == "INR"
        assert data["weekly_off_days"] == [5, 6]
        assert data["rounding_rule"] == "none"

    async def test_update_writes_field_level_history(self, client: AsyncClient, admin_headers: dict) -> None:
        effective = (date.today() + timedelta(days=1)).isoformat()
        response = await client.put(
            f"{PAYROLL}/config",
            json={
                "rounding_rule": "nearest_half",
                "overtime_enabled": True,
                "overtime_multiplier": "2.00",
                "reason": "Board-approved policy change",
                "effective_from": effective,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["rounding_rule"] == "nearest_half"
        assert data["overtime_multiplier"] == "2.00"

        history = await client.get(f"{PAYROLL}/config/history", headers=admin_headers)
        assert history.status_code == 200
        entries = history.json()["data"]
        fields = {entry["field"] for entry in entries}
        assert {"rounding_rule", "overtime_enabled", "overtime_multiplier"} <= fields
        rounding = next(entry for entry in entries if entry["field"] == "rounding_rule")
        assert rounding["previous_value"] == "none"
        assert rounding["new_value"] == "nearest_half"
        assert rounding["reason"] == "Board-approved policy change"
        assert rounding["effective_from"] == effective
        assert rounding["changed_by_name"]

    async def test_a_no_op_update_writes_no_history(self, client: AsyncClient, admin_headers: dict) -> None:
        body = {
            "currency": "INR",  # already the value
            "reason": "Nothing actually changes",
            "effective_from": date.today().isoformat(),
        }
        assert (await client.put(f"{PAYROLL}/config", json=body, headers=admin_headers)).status_code == 200
        history = (await client.get(f"{PAYROLL}/config/history", headers=admin_headers)).json()["data"]
        assert all(entry["reason"] != "Nothing actually changes" for entry in history)

    async def test_invalid_updates_are_refused(self, client: AsyncClient, admin_headers: dict) -> None:
        today = date.today().isoformat()

        past = await client.put(
            f"{PAYROLL}/config",
            json={
                "currency": "USD",
                "reason": "Backdated",
                "effective_from": (date.today() - timedelta(days=1)).isoformat(),
            },
            headers=admin_headers,
        )
        assert past.status_code == 422, "an effective date in the past must be refused"

        custom_without_precision = await client.put(
            f"{PAYROLL}/config",
            json={"rounding_rule": "custom", "reason": "No precision", "effective_from": today},
            headers=admin_headers,
        )
        assert custom_without_precision.status_code == 422

        negative_multiplier = await client.put(
            f"{PAYROLL}/config",
            json={"overtime_multiplier": "-1", "reason": "Negative", "effective_from": today},
            headers=admin_headers,
        )
        assert negative_multiplier.status_code == 422

        bad_weekday = await client.put(
            f"{PAYROLL}/config",
            json={"weekly_off_days": [7], "reason": "Bad weekday", "effective_from": today},
            headers=admin_headers,
        )
        assert bad_weekday.status_code == 422

        inverted_overtime = await client.put(
            f"{PAYROLL}/config",
            json={
                "overtime_min_hours": "4.00",
                "overtime_max_hours": "2.00",
                "reason": "Inverted window",
                "effective_from": today,
            },
            headers=admin_headers,
        )
        assert inverted_overtime.status_code == 422

    async def test_history_cannot_be_modified(self, client: AsyncClient, admin_headers: dict) -> None:
        """405, not 403: the write routes do not exist for anybody."""
        path = f"{PAYROLL}/config/history"
        assert (await client.delete(path, headers=admin_headers)).status_code == 405
        assert (await client.put(path, json={}, headers=admin_headers)).status_code == 405


# ----------------------------------------------------------------------
class TestPeriods:
    async def test_create_and_read_back(self, client: AsyncClient, admin_headers: dict) -> None:
        created = await client.post(
            f"{PAYROLL}/periods",
            json=_period_body(name=f"August 2027 {uuid.uuid4().hex[:4]}"),
            headers=admin_headers,
        )
        assert created.status_code == 201, created.text
        period = created.json()["data"]
        assert period["status"] == "open"

        listed = await client.get(f"{PAYROLL}/periods", headers=admin_headers)
        assert listed.status_code == 200
        assert any(row["id"] == period["id"] for row in listed.json()["data"]["items"])

    async def test_overlap_is_refused(self, client: AsyncClient, admin_headers: dict) -> None:
        first = await client.post(
            f"{PAYROLL}/periods",
            json=_period_body(start_date="2027-01-01", end_date="2027-01-31", pay_date="2027-01-31"),
            headers=admin_headers,
        )
        assert first.status_code == 201, first.text
        clash = await client.post(
            f"{PAYROLL}/periods",
            json=_period_body(start_date="2027-01-15", end_date="2027-02-14", pay_date="2027-02-14"),
            headers=admin_headers,
        )
        assert clash.status_code == 409
        assert clash.json()["errors"][0]["code"] == "overlapping_period"

    async def test_invalid_dates_are_refused(self, client: AsyncClient, admin_headers: dict) -> None:
        inverted = await client.post(
            f"{PAYROLL}/periods",
            json=_period_body(start_date="2027-03-31", end_date="2027-03-01", pay_date="2027-03-31"),
            headers=admin_headers,
        )
        assert inverted.status_code == 422
        early_pay = await client.post(
            f"{PAYROLL}/periods",
            json=_period_body(start_date="2027-04-01", end_date="2027-04-30", pay_date="2027-03-15"),
            headers=admin_headers,
        )
        assert early_pay.status_code == 422

    async def test_status_moves_only_along_the_map(self, client: AsyncClient, admin_headers: dict) -> None:
        period_id = (
            await client.post(
                f"{PAYROLL}/periods",
                json=_period_body(start_date="2027-05-01", end_date="2027-05-31", pay_date="2027-05-31"),
                headers=admin_headers,
            )
        ).json()["data"]["id"]
        base = f"{PAYROLL}/periods/{period_id}/status"

        # open cannot jump straight to approved.
        assert (await client.post(f"{base}/approved", headers=admin_headers)).status_code == 409
        for step in ("processing", "under_review", "approved", "finalized"):
            response = await client.post(f"{base}/{step}", headers=admin_headers)
            assert response.status_code == 200, response.text
        # Finalized is terminal.
        assert (await client.post(f"{base}/open", headers=admin_headers)).status_code == 409
        assert (await client.post(f"{base}/cancelled", headers=admin_headers)).status_code == 409

    async def test_only_an_open_period_is_editable(self, client: AsyncClient, admin_headers: dict) -> None:
        period_id = (
            await client.post(
                f"{PAYROLL}/periods",
                json=_period_body(start_date="2027-06-01", end_date="2027-06-30", pay_date="2027-06-30"),
                headers=admin_headers,
            )
        ).json()["data"]["id"]

        edited = await client.put(
            f"{PAYROLL}/periods/{period_id}", json={"pay_date": "2027-07-01"}, headers=admin_headers
        )
        assert edited.status_code == 200, edited.text

        assert (
            await client.post(f"{PAYROLL}/periods/{period_id}/status/processing", headers=admin_headers)
        ).status_code == 200
        locked = await client.put(
            f"{PAYROLL}/periods/{period_id}", json={"pay_date": "2027-07-02"}, headers=admin_headers
        )
        assert locked.status_code == 409
        assert locked.json()["errors"][0]["code"] == "period_not_open"


# ----------------------------------------------------------------------
class TestLeaveRules:
    async def test_paid_and_unpaid_rules(
        self, client: AsyncClient, admin_headers: dict, db_session: AsyncSession
    ) -> None:
        paid = await _leave_type(db_session, is_paid=True)
        unpaid = await _leave_type(db_session, is_paid=False)

        created_paid = await client.post(
            f"{PAYROLL}/rules/leave",
            json={"leave_type_id": str(paid.id), "treatment": "paid"},
            headers=admin_headers,
        )
        assert created_paid.status_code == 201, created_paid.text
        assert created_paid.json()["data"]["deduction_basis"] is None
        assert created_paid.json()["data"]["leave_type_is_paid"] is True

        no_basis = await client.post(
            f"{PAYROLL}/rules/leave",
            json={"leave_type_id": str(unpaid.id), "treatment": "unpaid"},
            headers=admin_headers,
        )
        assert no_basis.status_code == 422, "an unpaid rule must name its deduction basis"

        created_unpaid = await client.post(
            f"{PAYROLL}/rules/leave",
            json={
                "leave_type_id": str(unpaid.id),
                "treatment": "unpaid",
                "deduction_basis": "working_days",
            },
            headers=admin_headers,
        )
        assert created_unpaid.status_code == 201, created_unpaid.text

        duplicate = await client.post(
            f"{PAYROLL}/rules/leave",
            json={"leave_type_id": str(paid.id), "treatment": "paid"},
            headers=admin_headers,
        )
        assert duplicate.status_code == 409

    async def test_update_and_deactivate(
        self, client: AsyncClient, admin_headers: dict, db_session: AsyncSession
    ) -> None:
        leave_type = await _leave_type(db_session, is_paid=False)
        rule_id = (
            await client.post(
                f"{PAYROLL}/rules/leave",
                json={
                    "leave_type_id": str(leave_type.id),
                    "treatment": "unpaid",
                    "deduction_basis": "calendar_days",
                },
                headers=admin_headers,
            )
        ).json()["data"]["id"]

        # Switching to paid clears the basis rather than carrying it along.
        updated = await client.put(
            f"{PAYROLL}/rules/leave/{rule_id}", json={"treatment": "paid"}, headers=admin_headers
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["data"]["deduction_basis"] is None

        deactivated = await client.post(
            f"{PAYROLL}/rules/leave/{rule_id}/status/inactive", headers=admin_headers
        )
        assert deactivated.status_code == 200
        active_only = await client.get(f"{PAYROLL}/rules/leave", headers=admin_headers)
        assert all(row["id"] != rule_id for row in active_only.json()["data"])


# ----------------------------------------------------------------------
class TestComponentFlags:
    async def test_flags_are_stored_and_editable(self, client: AsyncClient, admin_headers: dict) -> None:
        listed = await client.get(f"{PAYROLL}/components", headers=admin_headers)
        assert listed.status_code == 200
        basic = next(row for row in listed.json()["data"] if row["code"] == "BASIC")
        assert basic["proration_allowed"] is True
        assert basic["is_taxable"] is True

        updated = await client.put(
            f"{PAYROLL}/components/{basic['id']}",
            json={"attendance_impact": True, "overtime_eligible": True},
            headers=admin_headers,
        )
        assert updated.status_code == 200, updated.text
        data = updated.json()["data"]
        assert data["attendance_impact"] is True
        assert data["overtime_eligible"] is True


# ----------------------------------------------------------------------
class TestEmployeeSettings:
    async def test_upsert_read_back_and_audit(
        self, client: AsyncClient, admin_headers: dict, db_session: AsyncSession
    ) -> None:
        from app.models.employee import Employee
        from app.models.enums import EmploymentStatus

        employee = Employee(
            first_name="Config",
            last_name="Target",
            official_email=f"config.target.{uuid.uuid4().hex[:8]}@jsan.example",
            joining_date=date(2024, 1, 5),
            employment_status=EmploymentStatus.ACTIVE,
        )
        db_session.add(employee)
        await db_session.flush()

        path = f"{PAYROLL}/employees/{employee.id}/settings"
        before = await client.get(path, headers=admin_headers)
        assert before.status_code == 200
        assert before.json()["data"]["settings"] is None, "absence of a row means not configured"

        saved = await client.put(
            path,
            json={
                "eligibility": "not_eligible",
                "eligibility_reason": "contractor",
                "overtime_eligible": False,
                "payroll_effective_date": "2027-01-01",
            },
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        settings_row = saved.json()["data"]["settings"]
        assert settings_row["eligibility"] == "not_eligible"
        assert settings_row["eligibility_reason"] == "contractor"

        listed = await client.get(f"{PAYROLL}/employee-settings", headers=admin_headers)
        assert listed.status_code == 200
        assert any(row["employee"]["id"] == str(employee.id) for row in listed.json()["data"]["items"])

        entry = (
            (
                await db_session.execute(
                    select(AuditLog)
                    .where(AuditLog.action == AuditAction.EMPLOYEE_PAYROLL_SETTINGS_CHANGED.value)
                    .order_by(AuditLog.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        assert entry is not None
        assert entry.context is not None and entry.context["eligibility"] == "not_eligible"


# ----------------------------------------------------------------------
class TestAccessModel:
    """§20: the whole configuration surface is Administration by default."""

    ALL_READS = (
        "/config",
        "/config/history",
        "/periods",
        "/rules/leave",
        "/employee-settings",
    )

    async def _assert_all_refused(self, client: AsyncClient, headers: dict[str, str]) -> None:
        for path in self.ALL_READS:
            response = await client.get(f"{PAYROLL}{path}", headers=headers)
            assert response.status_code == 403, f"{path} answered {response.status_code}"
        assert (
            await client.put(
                f"{PAYROLL}/config",
                json={"currency": "USD", "reason": "Nope", "effective_from": date.today().isoformat()},
                headers=headers,
            )
        ).status_code == 403
        assert (
            await client.post(f"{PAYROLL}/periods", json=_period_body(), headers=headers)
        ).status_code == 403
        assert (await client.post(f"{PAYROLL}/rules/leave", json={}, headers=headers)).status_code == 403

    async def test_an_employee_is_refused_everything(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, await _account(db_session, "employee", "conf_emp"))
        await self._assert_all_refused(client, headers)

    async def test_a_manager_is_refused_everything(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, await _account(db_session, "manager", "conf_mgr"))
        await self._assert_all_refused(client, headers)

    async def test_seeded_hr_admin_is_refused_everything(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _sign_in(client, await _account(db_session, "hr_admin", "conf_hr"))
        await self._assert_all_refused(client, headers)

    async def test_a_view_grant_opens_reads_and_nothing_else(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _account(db_session, "hr_admin", "conf_hr_view")
        await _grant(db_session, user, "payroll:config_view")
        headers = await _sign_in(client, user)

        assert (await client.get(f"{PAYROLL}/config", headers=headers)).status_code == 200
        assert (await client.get(f"{PAYROLL}/config/history", headers=headers)).status_code == 200
        assert (await client.get(f"{PAYROLL}/periods", headers=headers)).status_code == 200
        assert (await client.get(f"{PAYROLL}/rules/leave", headers=headers)).status_code == 200

        # What was not granted stays shut.
        assert (
            await client.put(
                f"{PAYROLL}/config",
                json={"currency": "USD", "reason": "Nope", "effective_from": date.today().isoformat()},
                headers=headers,
            )
        ).status_code == 403
        assert (
            await client.post(f"{PAYROLL}/periods", json=_period_body(), headers=headers)
        ).status_code == 403
        assert (
            await client.get(f"{PAYROLL}/employee-settings", headers=headers)
        ).status_code == 403, "employee settings need their own grant"

    async def test_a_superuser_bypasses_every_guard(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        assert (await client.get(f"{PAYROLL}/config", headers=auth_headers)).status_code == 200
        assert (await client.get(f"{PAYROLL}/periods", headers=auth_headers)).status_code == 200

    async def test_unauthenticated_requests_get_401(self, client: AsyncClient) -> None:
        assert (await client.get(f"{PAYROLL}/config")).status_code == 401
        assert (await client.get(f"{PAYROLL}/periods")).status_code == 401
