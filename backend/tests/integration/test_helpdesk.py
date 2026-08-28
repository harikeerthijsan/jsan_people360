"""Integration tests for the helpdesk and for announcements.

Three propositions are under test.

**An internal note never reaches the requester.** This is the one leak in a
helpdesk that would actually embarrass somebody, and it is asserted twice: on
the schema, which has no field that could carry the flag, and over HTTP against
a ticket that really has an internal note on it.

**A draft is not an announcement.** HR Executive can write one and cannot send
it, and an unpublished notice reaches nobody's dashboard.

**Targeting works both ways.** An announcement addressed to one team reaches
that team and, more importantly, does not reach anybody else.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.permissions import SYSTEM_ROLES_BY_KEY
from app.core.security import hash_password
from app.models.announcement import Announcement
from app.models.audit_log import AuditAction, AuditLog
from app.models.business_unit import BusinessUnit
from app.models.employee import Employee
from app.models.enums import EmploymentStatus, RecordStatus, TicketStatus
from app.models.helpdesk import HelpdeskCategory
from app.models.rbac import Role, UserRole
from app.models.team import Team
from app.models.user import User
from app.utils.datetime import utc_now

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
HELPDESK = f"{API}/helpdesk"
ANNOUNCEMENTS = f"{API}/announcements"
PASSWORD = "Str0ng!Passw0rd"


# ----------------------------------------------------------------------
# Fixtures
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
        assert role is not None, f"the {role_key} role should be seeded"
        session.add(UserRole(user_id=user.id, role_id=role.id))
        await session.flush()
    return user


async def _employee(
    session: AsyncSession,
    label: str,
    *,
    user: User | None = None,
    manager: Employee | None = None,
    team: Team | None = None,
    business_unit: BusinessUnit | None = None,
) -> Employee:
    suffix = uuid.uuid4().hex[:8]
    record = Employee(
        first_name=label.replace("_", " ").title(),
        last_name="Person",
        official_email=f"{label}.{suffix}@jsan.example",
        joining_date=utc_now().date(),
        employment_status=EmploymentStatus.ACTIVE,
        user_id=user.id if user else None,
        reporting_manager_id=manager.id if manager else None,
        team_id=team.id if team else None,
        business_unit_id=business_unit.id if business_unit else None,
    )
    session.add(record)
    await session.flush()
    return record


async def _sign_in(client: AsyncClient, user: User) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['tokens']['access_token']}"}


class People:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)

    admin_user: User
    hr_user: User
    hr_exec_user: User
    manager_user: User
    manager: Employee
    employee_user: User
    employee: Employee
    stranger_user: User
    stranger: Employee
    team: Team
    other_team: Team


@pytest.fixture
async def people(db_session: AsyncSession) -> People:
    business_unit = BusinessUnit(
        name=f"BU {uuid.uuid4().hex[:6]}",
        code=f"BU{uuid.uuid4().hex[:4].upper()}",
        status=RecordStatus.ACTIVE,
    )
    db_session.add(business_unit)
    await db_session.flush()

    # Teams carry no `code` -- they are named within a business unit.
    team = Team(
        name=f"Team {uuid.uuid4().hex[:6]}",
        business_unit_id=business_unit.id,
        status=RecordStatus.ACTIVE,
    )
    other_team = Team(
        name=f"Other {uuid.uuid4().hex[:6]}",
        business_unit_id=business_unit.id,
        status=RecordStatus.ACTIVE,
    )
    db_session.add_all([team, other_team])
    await db_session.flush()

    manager_user = await _account(db_session, "manager", "mgr")
    manager = await _employee(db_session, "manager", user=manager_user, team=team)

    employee_user = await _account(db_session, "employee", "emp")
    employee = await _employee(
        db_session,
        "employee",
        user=employee_user,
        manager=manager,
        team=team,
        business_unit=business_unit,
    )

    other_manager = await _employee(db_session, "other_manager")
    stranger_user = await _account(db_session, "employee", "stranger")

    return People(
        admin_user=await _account(db_session, "admin", "adm"),
        hr_user=await _account(db_session, "hr_admin", "hr"),
        hr_exec_user=await _account(db_session, "hr_executive", "hrx"),
        manager_user=manager_user,
        manager=manager,
        employee_user=employee_user,
        employee=employee,
        stranger_user=stranger_user,
        stranger=await _employee(
            db_session, "stranger", user=stranger_user, manager=other_manager, team=other_team
        ),
        team=team,
        other_team=other_team,
    )


@pytest.fixture
async def category(db_session: AsyncSession) -> HelpdeskCategory:
    row = HelpdeskCategory(
        name=f"Payroll {uuid.uuid4().hex[:4]}",
        code=f"PAY{uuid.uuid4().hex[:5].upper()}",
        queue="hr",
        sla_hours=24,
        status=RecordStatus.ACTIVE,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _raise(
    client: AsyncClient, headers: dict[str, str], category: HelpdeskCategory, **overrides: object
) -> dict:
    body = {
        "category_id": str(category.id),
        "subject": "My payslip is wrong",
        "description": "The tax deduction looks too high this month.",
        "priority": "medium",
    }
    body.update(overrides)  # type: ignore[arg-type]
    response = await client.post(f"{API}/me/helpdesk", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


# ======================================================================
# Raising and ownership
# ======================================================================
class TestRaisingRequests:
    async def test_an_employee_raises_their_own_request(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        headers = await _sign_in(client, people.employee_user)
        data = await _raise(client, headers, category)
        assert data["ticket_code"].startswith("TKT-")
        assert data["status"] == TicketStatus.OPEN.value

    async def test_the_self_service_schema_cannot_name_a_requester(self) -> None:
        """The IDOR that matters is the one that cannot be expressed."""
        from app.schemas.helpdesk import TicketRaise

        assert "raised_by_id" not in TicketRaise.model_fields
        assert "raised_for_id" not in TicketRaise.model_fields

    async def test_an_employee_sees_only_their_own_requests(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        mine = await _sign_in(client, people.employee_user)
        ticket = await _raise(client, mine, category)

        stranger = await _sign_in(client, people.stranger_user)
        assert (await client.get(f"{API}/me/helpdesk", headers=stranger)).json()["data"] == []
        assert (await client.get(f"{API}/me/helpdesk/{ticket['id']}", headers=stranger)).status_code == 403
        # And the administrative queue is closed to them entirely.
        assert (await client.get(HELPDESK, headers=stranger)).status_code == 403

    async def test_an_employee_cannot_raise_on_somebody_elses_behalf(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        headers = await _sign_in(client, people.employee_user)
        response = await client.post(
            HELPDESK,
            json={
                "category_id": str(category.id),
                "subject": "Not my request",
                "description": "Raised in somebody else's name.",
                "raised_for_id": str(people.stranger.id),
            },
            headers=headers,
        )
        assert response.status_code == 403

    async def test_hr_can_raise_on_somebody_elses_behalf(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        """A request taken over the phone is a real workflow."""
        headers = await _sign_in(client, people.hr_user)
        response = await client.post(
            HELPDESK,
            json={
                "category_id": str(category.id),
                "subject": "Payslip query taken by phone",
                "description": "Employee called about their tax code.",
                "raised_for_id": str(people.employee.id),
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["data"]["raised_for"]["id"] == str(people.employee.id)

        # And the person it is for can see it.
        employee = await _sign_in(client, people.employee_user)
        codes = {
            row["ticket_code"]
            for row in (await client.get(f"{API}/me/helpdesk", headers=employee)).json()["data"]
        }
        assert response.json()["data"]["ticket_code"] in codes

    async def test_an_inactive_category_cannot_be_used(
        self, client: AsyncClient, people: People, category: HelpdeskCategory, db_session: AsyncSession
    ) -> None:
        category.status = RecordStatus.INACTIVE.value
        await db_session.flush()

        headers = await _sign_in(client, people.employee_user)
        response = await client.post(
            f"{API}/me/helpdesk",
            json={
                "category_id": str(category.id),
                "subject": "Retired category",
                "description": "This should not be accepted at all.",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "inactive_category"


# ======================================================================
# The internal note -- the leak that would matter
# ======================================================================
class TestInternalNotesNeverReachTheRequester:
    async def test_the_employee_schema_has_no_internal_field(self) -> None:
        from app.schemas.helpdesk import MyTicketComment, MyTicketReply

        assert "internal" not in MyTicketComment.model_fields
        assert "internal" not in MyTicketReply.model_fields

    async def test_an_internal_note_is_absent_from_the_employee_view(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        employee = await _sign_in(client, people.employee_user)
        ticket = await _raise(client, employee, category)

        hr = await _sign_in(client, people.hr_user)
        secret = "PRIVATE-NOTE-DO-NOT-SHOW-THE-REQUESTER"
        public = "We are looking into this for you."
        for body, internal in ((secret, True), (public, False)):
            response = await client.post(
                f"{HELPDESK}/{ticket['id']}/comments",
                json={"body": body, "internal": internal},
                headers=hr,
            )
            assert response.status_code == 201, response.text

        mine = await client.get(f"{API}/me/helpdesk/{ticket['id']}", headers=employee)
        assert mine.status_code == 200
        assert secret not in mine.text, "an internal note reached the requester"
        assert public in mine.text, "the public reply is missing"

        # The agent view has both.
        agent = await client.get(f"{HELPDESK}/{ticket['id']}", headers=hr)
        assert secret in agent.text


# ======================================================================
# Working a ticket
# ======================================================================
class TestWorkingTickets:
    async def test_status_moves_along_the_transition_table(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        employee = await _sign_in(client, people.employee_user)
        ticket = await _raise(client, employee, category)
        hr = await _sign_in(client, people.hr_user)

        jump = await client.post(
            f"{HELPDESK}/{ticket['id']}/status",
            json={"status": "closed"},
            headers=hr,
        )
        assert jump.status_code == 409
        assert jump.json()["errors"][0]["code"] == "invalid_status_transition"

    async def test_resolving_needs_a_resolution(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        employee = await _sign_in(client, people.employee_user)
        ticket = await _raise(client, employee, category)
        hr = await _sign_in(client, people.hr_user)

        without = await client.post(
            f"{HELPDESK}/{ticket['id']}/status", json={"status": "resolved"}, headers=hr
        )
        assert without.status_code == 422

        with_one = await client.post(
            f"{HELPDESK}/{ticket['id']}/status",
            json={"status": "resolved", "resolution": "Tax code corrected in payroll."},
            headers=hr,
        )
        assert with_one.status_code == 200, with_one.text
        assert with_one.json()["data"]["resolved_at"] is not None

    async def test_the_requester_can_reopen_and_it_is_counted(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        employee = await _sign_in(client, people.employee_user)
        ticket = await _raise(client, employee, category)
        hr = await _sign_in(client, people.hr_user)
        await client.post(
            f"{HELPDESK}/{ticket['id']}/status",
            json={"status": "resolved", "resolution": "Fixed."},
            headers=hr,
        )

        reopened = await client.post(
            f"{API}/me/helpdesk/{ticket['id']}/reopen",
            params={"note": "Still wrong on this month's payslip."},
            headers=employee,
        )
        assert reopened.status_code == 200, reopened.text

        detail = (await client.get(f"{HELPDESK}/{ticket['id']}", headers=hr)).json()["data"]
        assert detail["status"] == TicketStatus.REOPENED.value
        assert detail["reopen_count"] == 1

    async def test_a_stranger_cannot_reopen_somebody_elses_ticket(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        employee = await _sign_in(client, people.employee_user)
        ticket = await _raise(client, employee, category)
        hr = await _sign_in(client, people.hr_user)
        await client.post(
            f"{HELPDESK}/{ticket['id']}/status",
            json={"status": "resolved", "resolution": "Fixed."},
            headers=hr,
        )

        stranger = await _sign_in(client, people.stranger_user)
        assert (
            await client.post(f"{API}/me/helpdesk/{ticket['id']}/reopen", headers=stranger)
        ).status_code == 403

    async def test_a_requester_reply_unblocks_the_desk(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        employee = await _sign_in(client, people.employee_user)
        ticket = await _raise(client, employee, category)
        hr = await _sign_in(client, people.hr_user)
        await client.post(
            f"{HELPDESK}/{ticket['id']}/status",
            json={"status": "waiting_on_employee", "note": "Could you send last month's payslip?"},
            headers=hr,
        )

        reply = await client.post(
            f"{API}/me/helpdesk/{ticket['id']}/reply",
            json={"body": "Attached."},
            headers=employee,
        )
        assert reply.status_code == 201, reply.text

        detail = (await client.get(f"{HELPDESK}/{ticket['id']}", headers=hr)).json()["data"]
        assert detail["status"] == TicketStatus.IN_PROGRESS.value

    async def test_assignment_starts_the_work(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        employee = await _sign_in(client, people.employee_user)
        ticket = await _raise(client, employee, category)

        hr = await _sign_in(client, people.hr_user)
        response = await client.post(
            f"{HELPDESK}/{ticket['id']}/assign",
            json={"assigned_to_id": str(people.hr_user.id)},
            headers=hr,
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == TicketStatus.IN_PROGRESS.value

    async def test_escalating_does_not_reset_the_clock(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        """A desk should not look punctual by re-labelling its backlog."""
        employee = await _sign_in(client, people.employee_user)
        ticket = await _raise(client, employee, category)
        original_due = ticket_due = None

        hr = await _sign_in(client, people.hr_user)
        detail = (await client.get(f"{HELPDESK}/{ticket['id']}", headers=hr)).json()["data"]
        original_due = detail["due_at"]

        await client.post(f"{HELPDESK}/{ticket['id']}/reclassify", json={"priority": "urgent"}, headers=hr)
        after = (await client.get(f"{HELPDESK}/{ticket['id']}", headers=hr)).json()["data"]
        assert after["priority"] == "urgent"
        assert after["due_at"] == original_due
        del ticket_due


# ======================================================================
# Access control
# ======================================================================
class TestHelpdeskAccessControl:
    async def test_a_manager_sees_their_teams_requests_and_cannot_answer(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        employee = await _sign_in(client, people.employee_user)
        ticket = await _raise(client, employee, category)

        manager = await _sign_in(client, people.manager_user)
        listed = await client.get(HELPDESK, headers=manager)
        assert listed.status_code == 200
        assert ticket["ticket_code"] in {row["ticket_code"] for row in listed.json()["data"]["items"]}

        refused = await client.post(
            f"{HELPDESK}/{ticket['id']}/comments", json={"body": "I will handle this"}, headers=manager
        )
        assert refused.status_code == 403

    async def test_a_manager_cannot_see_another_teams_requests(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        stranger = await _sign_in(client, people.stranger_user)
        ticket = await _raise(client, stranger, category)

        manager = await _sign_in(client, people.manager_user)
        listed = await client.get(HELPDESK, headers=manager)
        assert ticket["ticket_code"] not in {row["ticket_code"] for row in listed.json()["data"]["items"]}
        assert (await client.get(f"{HELPDESK}/{ticket['id']}", headers=manager)).status_code == 403

    def test_the_manager_grant_is_view_only(self) -> None:
        held = {p for p in SYSTEM_ROLES_BY_KEY["manager"].permissions if p.startswith("helpdesk:")}
        assert held == {"helpdesk:view"}

    async def test_hr_executive_cannot_configure_the_desk(self, client: AsyncClient, people: People) -> None:
        headers = await _sign_in(client, people.hr_exec_user)
        response = await client.post(
            f"{HELPDESK}/categories",
            json={"name": "New queue", "code": f"NQ{uuid.uuid4().hex[:5].upper()}", "queue": "hr"},
            headers=headers,
        )
        assert response.status_code == 403

    async def test_an_anonymous_caller_gets_401(self, client: AsyncClient) -> None:
        assert (await client.get(HELPDESK)).status_code == 401

    async def test_an_employee_can_list_categories_through_the_portal(
        self, client: AsyncClient, people: People, category: HelpdeskCategory
    ) -> None:
        """The regression that shipped: the raise dialog read the desk's
        categories endpoint, which sits behind ``helpdesk:view`` -- so an
        employee saw an empty dropdown and could never submit a request.

        The portal has its own list now. It must answer without any helpdesk
        permission, and its read model must not leak how the desk is staffed.
        """
        employee = await _sign_in(client, people.employee_user)

        refused = await client.get(f"{HELPDESK}/categories", headers=employee)
        assert refused.status_code == 403

        allowed = await client.get(f"{API}/me/helpdesk/categories", headers=employee)
        assert allowed.status_code == 200
        rows = allowed.json()["data"]
        assert category.name in {row["name"] for row in rows}
        for row in rows:
            assert set(row) == {"id", "name", "description"}


# ======================================================================
# Announcements
# ======================================================================
class TestAnnouncements:
    @staticmethod
    async def _draft(client: AsyncClient, headers: dict[str, str], **overrides: object) -> dict:
        body = {
            "title": "Office closed on Friday",
            "body": "The Chennai office will be closed for maintenance.",
            "summary": "Office closed Friday.",
            "audience": "all",
        }
        body.update(overrides)  # type: ignore[arg-type]
        response = await client.post(ANNOUNCEMENTS, json=body, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()["data"]

    async def test_a_draft_reaches_nobody(self, client: AsyncClient, people: People) -> None:
        hr = await _sign_in(client, people.hr_user)
        draft = await self._draft(client, hr)
        assert draft["status"] == "draft"

        employee = await _sign_in(client, people.employee_user)
        mine = await client.get(f"{API}/me/announcements", headers=employee)
        assert mine.status_code == 200
        assert draft["id"] not in {row["id"] for row in mine.json()["data"]}

    async def test_publishing_makes_it_visible(self, client: AsyncClient, people: People) -> None:
        hr = await _sign_in(client, people.hr_user)
        draft = await self._draft(client, hr)
        published = await client.post(f"{ANNOUNCEMENTS}/{draft['id']}/publish", json={}, headers=hr)
        assert published.status_code == 200, published.text
        assert published.json()["data"]["status"] == "published"

        employee = await _sign_in(client, people.employee_user)
        mine = await client.get(f"{API}/me/announcements", headers=employee)
        assert draft["id"] in {row["id"] for row in mine.json()["data"]}

    async def test_hr_executive_can_write_but_not_send(self, client: AsyncClient, people: People) -> None:
        """The grant the access model turns on."""
        held = {p for p in SYSTEM_ROLES_BY_KEY["hr_executive"].permissions if p.startswith("announcements:")}
        assert "announcements:create" in held
        assert "announcements:publish" not in held

        headers = await _sign_in(client, people.hr_exec_user)
        draft = await self._draft(client, headers)
        refused = await client.post(f"{ANNOUNCEMENTS}/{draft['id']}/publish", json={}, headers=headers)
        assert refused.status_code == 403

    async def test_a_targeted_announcement_reaches_only_its_audience(
        self, client: AsyncClient, people: People
    ) -> None:
        hr = await _sign_in(client, people.hr_user)
        draft = await self._draft(
            client,
            hr,
            title="Team offsite",
            audience="team",
            target_ids=[str(people.team.id)],
        )
        await client.post(f"{ANNOUNCEMENTS}/{draft['id']}/publish", json={}, headers=hr)

        member = await _sign_in(client, people.employee_user)
        seen = {
            row["id"] for row in (await client.get(f"{API}/me/announcements", headers=member)).json()["data"]
        }
        assert draft["id"] in seen, "the addressed team did not receive it"

        outsider = await _sign_in(client, people.stranger_user)
        unseen = {
            row["id"]
            for row in (await client.get(f"{API}/me/announcements", headers=outsider)).json()["data"]
        }
        assert draft["id"] not in unseen, "an announcement reached somebody outside its audience"

    async def test_an_audience_must_name_a_target(self, client: AsyncClient, people: People) -> None:
        hr = await _sign_in(client, people.hr_user)
        response = await client.post(
            ANNOUNCEMENTS,
            json={"title": "Nowhere", "body": "Addressed to a team with no team.", "audience": "team"},
            headers=hr,
        )
        assert response.status_code == 422

    async def test_a_target_that_does_not_exist_is_refused(self, client: AsyncClient, people: People) -> None:
        """A notice addressed to a team that does not exist reaches nobody, silently."""
        hr = await _sign_in(client, people.hr_user)
        response = await client.post(
            ANNOUNCEMENTS,
            json={
                "title": "Ghost team",
                "body": "Addressed to nothing.",
                "audience": "team",
                "target_ids": [str(uuid.uuid4())],
            },
            headers=hr,
        )
        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "invalid_audience_target"

    async def test_acknowledgement_is_idempotent(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        hr = await _sign_in(client, people.hr_user)
        draft = await self._draft(client, hr, requires_acknowledgement=True)
        await client.post(f"{ANNOUNCEMENTS}/{draft['id']}/publish", json={}, headers=hr)

        employee = await _sign_in(client, people.employee_user)
        for _ in range(3):
            response = await client.post(
                f"{API}/me/announcements/{draft['id']}/acknowledge", headers=employee
            )
            assert response.status_code == 200, response.text

        from app.models.announcement import AnnouncementAcknowledgement

        count = (
            await db_session.execute(
                select(func.count())
                .select_from(AnnouncementAcknowledgement)
                .where(AnnouncementAcknowledgement.announcement_id == uuid.UUID(draft["id"]))
            )
        ).scalar_one()
        assert count == 1, "acknowledging three times recorded more than once"

        detail = (await client.get(f"{ANNOUNCEMENTS}/{draft['id']}", headers=hr)).json()["data"]
        assert detail["acknowledged_count"] == 1
        assert detail["audience_size"] >= 1

    async def test_an_expired_announcement_drops_off(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        hr = await _sign_in(client, people.hr_user)
        draft = await self._draft(client, hr, title="Yesterday's news")
        await client.post(f"{ANNOUNCEMENTS}/{draft['id']}/publish", json={}, headers=hr)

        # Backdate *both*: the CHECK constraint refuses an expiry before the
        # publication it belongs to, which is correct and is why an expired
        # notice has to be one that was published earlier still.
        row = (
            (await db_session.execute(select(Announcement).where(Announcement.id == uuid.UUID(draft["id"]))))
            .scalars()
            .one()
        )
        row.published_at = utc_now() - timedelta(days=2)
        row.expires_at = utc_now() - timedelta(days=1)
        await db_session.flush()

        employee = await _sign_in(client, people.employee_user)
        seen = {
            r["id"] for r in (await client.get(f"{API}/me/announcements", headers=employee)).json()["data"]
        }
        assert draft["id"] not in seen

    async def test_publishing_notifies_the_audience(self, client: AsyncClient, people: People) -> None:
        """The integration: an announcement delivers through the existing inbox."""
        hr = await _sign_in(client, people.hr_user)
        draft = await self._draft(client, hr, title="Delivered by notification")
        await client.post(f"{ANNOUNCEMENTS}/{draft['id']}/publish", json={}, headers=hr)

        employee = await _sign_in(client, people.employee_user)
        inbox = await client.get(f"{API}/notifications", headers=employee)
        assert inbox.status_code == 200
        assert "Delivered by notification" in inbox.text

    async def test_an_archived_announcement_cannot_be_republished(
        self, client: AsyncClient, people: People
    ) -> None:
        hr = await _sign_in(client, people.hr_user)
        draft = await self._draft(client, hr)
        await client.post(f"{ANNOUNCEMENTS}/{draft['id']}/publish", json={}, headers=hr)
        await client.post(f"{ANNOUNCEMENTS}/{draft['id']}/archive", headers=hr)

        again = await client.post(f"{ANNOUNCEMENTS}/{draft['id']}/publish", json={}, headers=hr)
        assert again.status_code == 409
        assert again.json()["errors"][0]["code"] == "announcement_archived"

    async def test_hr_admin_cannot_delete(self, client: AsyncClient, people: People) -> None:
        """A notice that went out is a thing that was said. Archiving retires it."""
        assert "announcements:delete" not in SYSTEM_ROLES_BY_KEY["hr_admin"].permissions

        hr = await _sign_in(client, people.hr_user)
        draft = await self._draft(client, hr)
        assert (await client.delete(f"{ANNOUNCEMENTS}/{draft['id']}", headers=hr)).status_code == 403

        admin = await _sign_in(client, people.admin_user)
        assert (await client.delete(f"{ANNOUNCEMENTS}/{draft['id']}", headers=admin)).status_code == 204


# ======================================================================
# Audit
# ======================================================================
class TestAuditing:
    async def test_the_lifecycle_is_audited(
        self, client: AsyncClient, people: People, category: HelpdeskCategory, db_session: AsyncSession
    ) -> None:
        employee = await _sign_in(client, people.employee_user)
        ticket = await _raise(client, employee, category)
        hr = await _sign_in(client, people.hr_user)
        await client.post(
            f"{HELPDESK}/{ticket['id']}/assign",
            json={"assigned_to_id": str(people.hr_user.id)},
            headers=hr,
        )
        await client.post(
            f"{HELPDESK}/{ticket['id']}/status",
            json={"status": "resolved", "resolution": "Done."},
            headers=hr,
        )

        actions = (
            (await db_session.execute(select(AuditLog.action).where(AuditLog.action.like("helpdesk.%"))))
            .scalars()
            .all()
        )
        for expected in (
            AuditAction.TICKET_RAISED,
            AuditAction.TICKET_ASSIGNED,
            AuditAction.TICKET_RESOLVED,
        ):
            assert expected.value in actions, f"{expected.value} was not audited"

    async def test_publishing_is_audited_separately_from_writing(
        self, client: AsyncClient, people: People, db_session: AsyncSession
    ) -> None:
        hr = await _sign_in(client, people.hr_user)
        draft = await TestAnnouncements._draft(client, hr)
        await client.post(f"{ANNOUNCEMENTS}/{draft['id']}/publish", json={}, headers=hr)

        actions = (
            (await db_session.execute(select(AuditLog.action).where(AuditLog.action.like("announcement.%"))))
            .scalars()
            .all()
        )
        assert AuditAction.ANNOUNCEMENT_CREATED.value in actions
        assert AuditAction.ANNOUNCEMENT_PUBLISHED.value in actions
