"""Employee Management API.

Exercises the real HTTP stack against a real database. The emphasis is on the
things that would be expensive to get wrong: that history is written for every
placement change and never overwritten, that sensitive values are masked on the
way out, and that the guards actually refuse what they claim to.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.business_unit import BusinessUnit
from app.models.designation import Designation
from app.models.employee import Employee
from app.models.employment_type import EmploymentType
from app.models.enums import RecordStatus
from app.models.grade import Grade
from app.models.location import Location
from app.models.team import Team
from app.models.user import User

pytestmark = pytest.mark.asyncio

BASE = f"{settings.API_V1_PREFIX}/employees"


def payload(**overrides: Any) -> dict[str, Any]:
    """A minimal valid create payload, with a unique work address."""
    suffix = uuid.uuid4().hex[:10]
    return {
        "first_name": "Arjun",
        "last_name": "Rao",
        "official_email": f"arjun.{suffix}@jsan.example",
        "joining_date": "2026-02-01",
        **overrides,
    }


async def create_employee(client: AsyncClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    response = await client.post(BASE, json=payload(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


# ----------------------------------------------------------------------
class TestAuthentication:
    async def test_every_route_needs_a_token(self, client: AsyncClient) -> None:
        assert (await client.get(BASE)).status_code == 401
        assert (await client.post(BASE, json=payload())).status_code == 401
        assert (await client.get(f"{BASE}/dashboard")).status_code == 401


# ----------------------------------------------------------------------
class TestCreate:
    async def test_creates_an_employee(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        data = await create_employee(client, auth_headers)

        assert data["full_name"] == "Arjun Rao"
        assert data["employment_status"] == "probation"
        assert data["deleted_at"] is None

    async def test_generates_a_sequential_employee_code(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        first = await create_employee(client, auth_headers)
        second = await create_employee(client, auth_headers)

        assert first["employee_code"].startswith("JSAN")
        assert first["employee_code"][4:].isdigit()
        assert int(second["employee_code"][4:]) == int(first["employee_code"][4:]) + 1

    async def test_an_employee_code_cannot_be_supplied(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(BASE, json=payload(employee_code="EMP-999999"), headers=auth_headers)
        assert response.status_code == 422

    async def test_trims_and_normalises_input(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        data = await create_employee(client, auth_headers, first_name="  Arjun  ", last_name="Van   Rao")
        assert data["first_name"] == "Arjun"
        assert data["last_name"] == "Van Rao"

    async def test_rejects_a_duplicate_official_email(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        existing = await create_employee(client, auth_headers)

        response = await client.post(
            BASE, json=payload(official_email=existing["official_email"].upper()), headers=auth_headers
        )

        assert response.status_code == 409
        body = response.json()
        assert body["errors"][0]["code"] == "duplicate_official_email"
        assert existing["employee_code"] in body["message"]

    async def test_creates_the_satellite_records(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        data = await create_employee(
            client,
            auth_headers,
            addresses=[
                {
                    "address_type": "current",
                    "address_line1": "12 Main Street",
                    "city": "Hyderabad",
                    "state": "Telangana",
                    "country": "India",
                    "postal_code": "500081",
                }
            ],
            bank_detail={
                "bank_name": "HDFC Bank",
                "account_number": "50100123456789",
                "ifsc_code": "HDFC0001234",
                "branch_name": "Hitec City",
            },
            identification={"aadhaar_number": "234567890123", "pan_number": "ABCDE1234F"},
        )

        assert len(data["addresses"]) == 1
        assert data["bank_detail"]["bank_name"] == "HDFC Bank"
        assert data["identification"] is not None

    async def test_links_an_organizational_placement(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        team: Team,
        designation: Designation,
        grade: Grade,
        location: Location,
        employment_type: EmploymentType,
    ) -> None:
        data = await create_employee(
            client,
            auth_headers,
            team_id=str(team.id),
            designation_id=str(designation.id),
            grade_id=str(grade.id),
            work_location_id=str(location.id),
            employment_type_id=str(employment_type.id),
        )

        organization = data["organization"]
        assert organization["team"]["name"] == team.name
        assert organization["designation"]["name"] == designation.name
        assert organization["work_location"]["name"] == location.name

    async def test_creates_when_the_master_is_not_already_in_the_session(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        team: Team,
    ) -> None:
        """The condition every real request runs under.

        The fixtures leave their records in the session's identity map, so a
        relationship read resolves without SQL and a *lazy* load is never
        attempted. A live request has no such luck: the record has to come from
        the database, and reading it off a freshly constructed entity issues a
        lazy SELECT that raises MissingGreenlet under asyncio.

        Expunging first is what makes this test exercise the same path as the
        server rather than a friendlier one.
        """
        team_id = str(team.id)
        db_session.expunge_all()

        response = await client.post(BASE, json=payload(team_id=team_id), headers=auth_headers)

        assert response.status_code == 201, response.text
        assert response.json()["data"]["organization"]["team"]["id"] == team_id

    async def test_rejects_an_archived_master_reference(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, grade: Grade
    ) -> None:
        grade.status = RecordStatus.INACTIVE
        await db_session.flush()

        response = await client.post(BASE, json=payload(grade_id=str(grade.id)), headers=auth_headers)

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "invalid_organization_reference"
        assert "grade" in response.json()["message"]

    async def test_rejects_an_unknown_master_reference(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(BASE, json=payload(team_id=str(uuid.uuid4())), headers=auth_headers)
        assert response.status_code == 409

    async def test_writes_the_opening_history_row(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """The series covers the whole employment, not just its amendments."""
        data = await create_employee(client, auth_headers)

        response = await client.get(f"{BASE}/{data['id']}/history", headers=auth_headers)
        history = response.json()["data"]

        assert len(history) == 1
        assert history[0]["change_type"] == "created"
        assert history[0]["effective_date"] == "2026-02-01"


class TestUserLink:
    async def test_links_a_user_account(
        self, client: AsyncClient, auth_headers: dict[str, str], inactive_user: User
    ) -> None:
        data = await create_employee(client, auth_headers, user_id=str(inactive_user.id))
        assert data["user"]["username"] == inactive_user.username

    async def test_one_account_cannot_belong_to_two_employees(
        self, client: AsyncClient, auth_headers: dict[str, str], inactive_user: User
    ) -> None:
        first = await create_employee(client, auth_headers, user_id=str(inactive_user.id))

        response = await client.post(BASE, json=payload(user_id=str(inactive_user.id)), headers=auth_headers)

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "user_already_linked"
        assert first["employee_code"] in response.json()["message"]

    async def test_rejects_an_unknown_account(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(BASE, json=payload(user_id=str(uuid.uuid4())), headers=auth_headers)
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "invalid_user_reference"


# ----------------------------------------------------------------------
class TestMasking:
    @pytest.fixture
    async def with_sensitive(self, client: AsyncClient, auth_headers: dict[str, str]) -> dict[str, Any]:
        return await create_employee(
            client,
            auth_headers,
            bank_detail={
                "bank_name": "HDFC Bank",
                "account_number": "50100123456789",
                "ifsc_code": "HDFC0001234",
                "branch_name": "Hitec City",
            },
            identification={"aadhaar_number": "234567890123", "pan_number": "ABCDE1234F"},
        )

    async def test_the_create_response_is_already_masked(self, with_sensitive: dict[str, Any]) -> None:
        assert with_sensitive["bank_detail"]["account_number"] == "XXXXXXXXXX6789"
        assert with_sensitive["identification"]["aadhaar_number"] == "XXXXXXXX0123"

    async def test_the_detail_response_is_masked(
        self, client: AsyncClient, auth_headers: dict[str, str], with_sensitive: dict[str, Any]
    ) -> None:
        response = await client.get(f"{BASE}/{with_sensitive['id']}", headers=auth_headers)
        data = response.json()["data"]

        assert data["identification"]["pan_number"] == "XXXXXX234F"
        assert "50100123456789" not in response.text
        assert "234567890123" not in response.text

    async def test_the_list_response_never_carries_a_raw_value(
        self, client: AsyncClient, auth_headers: dict[str, str], with_sensitive: dict[str, Any]
    ) -> None:
        response = await client.get(BASE, params={"page_size": 100}, headers=auth_headers)
        assert "50100123456789" not in response.text
        assert "ABCDE1234F" not in response.text

    async def test_the_reveal_endpoint_returns_the_real_values(
        self, client: AsyncClient, auth_headers: dict[str, str], with_sensitive: dict[str, Any]
    ) -> None:
        response = await client.get(f"{BASE}/{with_sensitive['id']}/sensitive", headers=auth_headers)
        data = response.json()["data"]

        assert data["bank_detail"]["account_number"] == "50100123456789"
        assert data["identification"]["aadhaar_number"] == "234567890123"
        assert data["identification"]["pan_number"] == "ABCDE1234F"

    async def test_revealing_is_audited(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        with_sensitive: dict[str, Any],
    ) -> None:
        """An unaudited reveal would make the masking everywhere else decorative."""
        await client.get(f"{BASE}/{with_sensitive['id']}/sensitive", headers=auth_headers)

        entries = (
            (await db_session.execute(select(AuditLog).where(AuditLog.action == "employee.sensitive.viewed")))
            .scalars()
            .all()
        )

        assert len(entries) == 1
        assert entries[0].entity_id == with_sensitive["id"]
        assert entries[0].actor_id is not None

    async def test_the_audit_entry_never_quotes_the_value(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        with_sensitive: dict[str, Any],
    ) -> None:
        await client.put(
            f"{BASE}/{with_sensitive['id']}/identification",
            json={"aadhaar_number": "345678901234"},
            headers=auth_headers,
        )

        entries = (
            (
                await db_session.execute(
                    select(AuditLog).where(AuditLog.action == "employee.identification.updated")
                )
            )
            .scalars()
            .all()
        )

        assert entries
        for entry in entries:
            assert "345678901234" not in (entry.description or "")
            assert "345678901234" not in str(entry.context)


class TestIdentifierUniqueness:
    async def test_two_employees_cannot_share_an_aadhaar(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        first = await create_employee(client, auth_headers, identification={"aadhaar_number": "234567890123"})

        response = await client.post(
            BASE,
            json=payload(identification={"aadhaar_number": "234567890123"}),
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "duplicate_identifier"
        assert first["employee_code"] in response.json()["message"]

    async def test_the_message_does_not_repeat_the_identifier(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await create_employee(client, auth_headers, identification={"pan_number": "ABCDE1234F"})

        response = await client.post(
            BASE, json=payload(identification={"pan_number": "ABCDE1234F"}), headers=auth_headers
        )

        assert "ABCDE1234F" not in response.json()["message"]

    async def test_a_pan_is_compared_case_insensitively(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await create_employee(client, auth_headers, identification={"pan_number": "ABCDE1234F"})

        response = await client.post(
            BASE, json=payload(identification={"pan_number": "abcde1234f"}), headers=auth_headers
        )
        assert response.status_code == 409


# ----------------------------------------------------------------------
class TestListing:
    async def test_lists_employees(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.get(BASE, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["meta"]["total_items"] >= 1

    async def test_search_matches_the_full_name(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        """The parts are stored separately; the obvious search must still work."""
        response = await client.get(BASE, params={"search": "Priya Sharma"}, headers=auth_headers)
        codes = [row["employee_code"] for row in response.json()["data"]["items"]]
        assert employee.employee_code in codes

    async def test_search_matches_the_employee_code(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.get(BASE, params={"search": employee.employee_code}, headers=auth_headers)
        assert response.json()["data"]["meta"]["total_items"] == 1

    async def test_filters_by_status(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.get(BASE, params={"employment_status": "probation"}, headers=auth_headers)
        statuses = {row["employment_status"] for row in response.json()["data"]["items"]}
        assert statuses == {"probation"}

    async def test_filters_by_team(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        team: Team,
    ) -> None:
        response = await client.get(BASE, params={"team_id": str(team.id)}, headers=auth_headers)
        assert response.json()["data"]["meta"]["total_items"] == 1

    async def test_filters_by_joining_date_range(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        inside = await client.get(
            BASE, params={"joined_from": "2026-01-01", "joined_to": "2026-01-31"}, headers=auth_headers
        )
        outside = await client.get(BASE, params={"joined_from": "2027-01-01"}, headers=auth_headers)

        assert inside.json()["data"]["meta"]["total_items"] == 1
        assert outside.json()["data"]["meta"]["total_items"] == 0

    async def test_rejects_an_inverted_date_range(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(
            BASE, params={"joined_from": "2026-06-01", "joined_to": "2026-01-01"}, headers=auth_headers
        )
        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "invalid_date_range"

    async def test_rejects_an_unsupported_sort_column(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(BASE, params={"sort_by": "ctc"}, headers=auth_headers)
        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "invalid_sort_field"

    async def test_rejects_the_master_status_filter(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Silently ignoring an unknown filter would be worse than refusing it."""
        response = await client.get(BASE, params={"status": "active"}, headers=auth_headers)
        assert response.status_code == 422

    async def test_live_and_archived_are_never_mixed(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        await client.post(f"{BASE}/{employee.id}/archive", headers=auth_headers)

        live = await client.get(BASE, headers=auth_headers)
        archived = await client.get(BASE, params={"archived": "true"}, headers=auth_headers)

        assert live.json()["data"]["meta"]["total_items"] == 0
        assert archived.json()["data"]["meta"]["total_items"] == 1


# ----------------------------------------------------------------------
class TestUpdate:
    async def test_updates_a_plain_field(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.patch(
            f"{BASE}/{employee.id}", json={"nationality": "Indian"}, headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["nationality"] == "Indian"

    async def test_a_plain_update_writes_no_history(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        """History is for placement, not for correcting a phone number."""
        await client.patch(f"{BASE}/{employee.id}", json={"nationality": "Indian"}, headers=auth_headers)

        history = (await client.get(f"{BASE}/{employee.id}/history", headers=auth_headers)).json()["data"]
        assert history == []

    async def test_a_placement_change_writes_history(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        designation: Designation,
    ) -> None:
        await client.patch(
            f"{BASE}/{employee.id}",
            json={"designation_id": str(designation.id), "change_reason": "Role clarified"},
            headers=auth_headers,
        )

        history = (await client.get(f"{BASE}/{employee.id}/history", headers=auth_headers)).json()["data"]
        assert len(history) == 1
        assert history[0]["change_type"] == "designation_change"
        assert history[0]["reason"] == "Role clarified"

    async def test_resubmitting_the_current_value_writes_no_history(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        team: Team,
    ) -> None:
        """A row saying nothing changed is worse than no row: it reads as though
        something did."""
        response = await client.patch(
            f"{BASE}/{employee.id}",
            json={"team_id": str(team.id)},
            headers=auth_headers,
        )
        assert response.status_code == 200

        history = (await client.get(f"{BASE}/{employee.id}/history", headers=auth_headers)).json()["data"]
        assert history == []

    async def test_a_genuine_change_alongside_a_no_op_still_writes_history(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        team: Team,
        designation: Designation,
    ) -> None:
        await client.patch(
            f"{BASE}/{employee.id}",
            json={"team_id": str(team.id), "designation_id": str(designation.id)},
            headers=auth_headers,
        )

        history = (await client.get(f"{BASE}/{employee.id}/history", headers=auth_headers)).json()["data"]
        assert len(history) == 1
        # Only the designation moved, so only the designation is named.
        assert "Designation" in history[0]["summary"]
        assert "Team" not in history[0]["summary"]

    async def test_resubmitting_the_current_status_is_not_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        """An edit form posts the whole record, including the unchanged status.

        Treating that as "already on probation" made the form impossible to
        save. The dedicated status endpoint still refuses a no-op, where asking
        for a change that is not a change really is a mistake.
        """
        response = await client.patch(
            f"{BASE}/{employee.id}",
            json={"employment_status": "probation", "nationality": "Indian"},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["data"]["nationality"] == "Indian"

        history = (await client.get(f"{BASE}/{employee.id}/history", headers=auth_headers)).json()["data"]
        assert history == []

    async def test_a_real_status_change_through_the_update_is_still_checked(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        await client.post(
            f"{BASE}/{employee.id}/status", json={"employment_status": "resigned"}, headers=auth_headers
        )

        response = await client.patch(
            f"{BASE}/{employee.id}", json={"employment_status": "probation"}, headers=auth_headers
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "invalid_status_transition"

    async def test_rejects_a_duplicate_official_email(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        other = await create_employee(client, auth_headers)

        response = await client.patch(
            f"{BASE}/{employee.id}",
            json={"official_email": other["official_email"]},
            headers=auth_headers,
        )
        assert response.status_code == 409

    async def test_an_archived_employee_cannot_be_edited(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        await client.post(f"{BASE}/{employee.id}/archive", headers=auth_headers)

        response = await client.patch(
            f"{BASE}/{employee.id}", json={"nationality": "Indian"}, headers=auth_headers
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "record_archived"


# ----------------------------------------------------------------------
class TestLifecycle:
    async def test_confirms_an_employee_on_probation(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.post(
            f"{BASE}/{employee.id}/confirm",
            json={"effective_date": "2026-07-15", "reason": "Probation completed"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["employment_status"] == "confirmed"
        assert data["confirmation_date"] == "2026-07-15"

    async def test_only_an_employee_on_probation_can_be_confirmed(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        await client.post(f"{BASE}/{employee.id}/confirm", json={}, headers=auth_headers)

        response = await client.post(f"{BASE}/{employee.id}/confirm", json={}, headers=auth_headers)
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "not_on_probation"

    async def test_transfers_to_another_team(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        db_session: AsyncSession,
        team: Team,
    ) -> None:
        target = Team(
            name="Product Engineering",
            business_unit_id=team.business_unit_id,
            status=RecordStatus.ACTIVE,
        )
        db_session.add(target)
        await db_session.flush()

        response = await client.post(
            f"{BASE}/{employee.id}/transfer",
            json={"team_id": str(target.id), "reason": "Reorganisation"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["data"]["organization"]["team"]["name"] == "Product Engineering"

    async def test_the_transfer_summary_names_both_teams(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        db_session: AsyncSession,
        team: Team,
    ) -> None:
        """The summary is frozen at write time so a later rename cannot rewrite it."""
        target = Team(
            name="Product Engineering",
            business_unit_id=team.business_unit_id,
            status=RecordStatus.ACTIVE,
        )
        db_session.add(target)
        await db_session.flush()

        await client.post(
            f"{BASE}/{employee.id}/transfer",
            json={"team_id": str(target.id)},
            headers=auth_headers,
        )

        history = (await client.get(f"{BASE}/{employee.id}/history", headers=auth_headers)).json()["data"]
        summary = history[0]["summary"]

        assert "Platform Engineering" in summary
        assert "Product Engineering" in summary
        # A UUID leaking into the summary is the failure this asserts against.
        assert str(target.id) not in summary

    async def test_transferring_to_the_same_team_is_refused(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        team: Team,
    ) -> None:
        response = await client.post(
            f"{BASE}/{employee.id}/transfer",
            json={"team_id": str(team.id)},
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "already_in_team"

    async def test_promotes_an_employee(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        designation: Designation,
        grade: Grade,
    ) -> None:
        response = await client.post(
            f"{BASE}/{employee.id}/promote",
            json={
                "designation_id": str(designation.id),
                "grade_id": str(grade.id),
                "ctc": "1450000.00",
                "reason": "Annual cycle",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        history = (await client.get(f"{BASE}/{employee.id}/history", headers=auth_headers)).json()["data"]
        assert history[0]["change_type"] == "promotion"

    async def test_an_empty_promotion_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.post(f"{BASE}/{employee.id}/promote", json={}, headers=auth_headers)
        assert response.status_code == 422

    async def test_changes_the_reporting_manager(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        manager = await create_employee(client, auth_headers)

        response = await client.post(
            f"{BASE}/{employee.id}/manager",
            json={"reporting_manager_id": manager["id"]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["data"]["reporting_manager"]["employee_code"] == manager["employee_code"]

    async def test_an_employee_cannot_report_to_themselves(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.post(
            f"{BASE}/{employee.id}/manager",
            json={"reporting_manager_id": str(employee.id)},
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "manager_is_self"

    async def test_a_reporting_loop_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        """A cycle makes every org-chart query non-terminating."""
        manager = await create_employee(client, auth_headers)

        await client.post(
            f"{BASE}/{employee.id}/manager",
            json={"reporting_manager_id": manager["id"]},
            headers=auth_headers,
        )
        response = await client.post(
            f"{BASE}/{manager['id']}/manager",
            json={"reporting_manager_id": str(employee.id)},
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "reporting_cycle"

    async def test_an_indirect_reporting_loop_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        middle = await create_employee(client, auth_headers)
        top = await create_employee(client, auth_headers)

        await client.post(
            f"{BASE}/{employee.id}/manager",
            json={"reporting_manager_id": middle["id"]},
            headers=auth_headers,
        )
        await client.post(
            f"{BASE}/{middle['id']}/manager",
            json={"reporting_manager_id": top["id"]},
            headers=auth_headers,
        )

        # top -> employee would close the loop employee -> middle -> top -> employee
        response = await client.post(
            f"{BASE}/{top['id']}/manager",
            json={"reporting_manager_id": str(employee.id)},
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "reporting_cycle"

    async def test_activate_and_deactivate(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        deactivated = await client.post(f"{BASE}/{employee.id}/deactivate", headers=auth_headers)
        assert deactivated.json()["data"]["employment_status"] == "inactive"

        activated = await client.post(f"{BASE}/{employee.id}/activate", headers=auth_headers)
        assert activated.json()["data"]["employment_status"] == "active"

    async def test_setting_the_current_status_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.post(
            f"{BASE}/{employee.id}/status",
            json={"employment_status": "probation"},
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "already_in_status"

    async def test_a_former_employee_cannot_re_enter_the_joining_lifecycle(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        await client.post(
            f"{BASE}/{employee.id}/status",
            json={"employment_status": "resigned"},
            headers=auth_headers,
        )

        response = await client.post(
            f"{BASE}/{employee.id}/status",
            json={"employment_status": "probation"},
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "invalid_status_transition"

    async def test_a_former_employee_can_be_reactivated(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        await client.post(
            f"{BASE}/{employee.id}/status",
            json={"employment_status": "resigned"},
            headers=auth_headers,
        )
        response = await client.post(f"{BASE}/{employee.id}/activate", headers=auth_headers)
        assert response.status_code == 200


# ----------------------------------------------------------------------
class TestHistory:
    async def test_every_change_appends_rather_than_replaces(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        designation: Designation,
        grade: Grade,
    ) -> None:
        # Created through the API, so the opening row is present too.
        employee_id = (await create_employee(client, auth_headers))["id"]

        await client.post(f"{BASE}/{employee_id}/confirm", json={}, headers=auth_headers)
        await client.post(
            f"{BASE}/{employee_id}/designation",
            json={"designation_id": str(designation.id)},
            headers=auth_headers,
        )
        await client.post(
            f"{BASE}/{employee_id}/promote", json={"grade_id": str(grade.id)}, headers=auth_headers
        )

        history = (await client.get(f"{BASE}/{employee_id}/history", headers=auth_headers)).json()["data"]

        # created + confirmation + designation + promotion
        assert len(history) == 4
        assert {row["change_type"] for row in history} == {
            "created",
            "confirmation",
            "designation_change",
            "promotion",
        }

    async def test_history_is_newest_first(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        await client.post(
            f"{BASE}/{employee.id}/confirm", json={"effective_date": "2026-06-01"}, headers=auth_headers
        )

        history = (await client.get(f"{BASE}/{employee.id}/history", headers=auth_headers)).json()["data"]
        dates = [row["effective_date"] for row in history]
        assert dates == sorted(dates, reverse=True)

    async def test_a_history_row_records_the_state_after_the_change(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        designation: Designation,
    ) -> None:
        await client.post(
            f"{BASE}/{employee.id}/designation",
            json={"designation_id": str(designation.id)},
            headers=auth_headers,
        )

        history = (await client.get(f"{BASE}/{employee.id}/history", headers=auth_headers)).json()["data"]
        assert history[0]["designation"]["name"] == designation.name
        assert history[0]["employment_status"] == "probation"

    async def test_there_is_no_endpoint_that_edits_history(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        """The module's central promise, asserted at the HTTP surface."""
        url = f"{BASE}/{employee.id}/history"
        assert (await client.patch(url, json={}, headers=auth_headers)).status_code == 405
        assert (await client.delete(url, headers=auth_headers)).status_code == 405
        assert (await client.put(url, json={}, headers=auth_headers)).status_code == 405


# ----------------------------------------------------------------------
class TestArchiveAndRestore:
    async def test_archives_and_restores(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        archived = await client.post(f"{BASE}/{employee.id}/archive", headers=auth_headers)
        assert archived.json()["data"]["deleted_at"] is not None

        restored = await client.post(f"{BASE}/{employee.id}/restore", headers=auth_headers)
        assert restored.json()["data"]["deleted_at"] is None

    async def test_archiving_twice_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        await client.post(f"{BASE}/{employee.id}/archive", headers=auth_headers)
        response = await client.post(f"{BASE}/{employee.id}/archive", headers=auth_headers)
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "already_archived"

    async def test_a_manager_with_reports_cannot_be_archived(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        manager = await create_employee(client, auth_headers)
        await client.post(
            f"{BASE}/{employee.id}/manager",
            json={"reporting_manager_id": manager["id"]},
            headers=auth_headers,
        )

        response = await client.post(f"{BASE}/{manager['id']}/archive", headers=auth_headers)

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "has_direct_reports"
        # The message is shown to a person, so the verb has to agree with the count.
        assert "1 employee still reports to" in response.json()["message"]

    async def test_the_direct_report_message_agrees_in_the_plural(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        manager = await create_employee(client, auth_headers)
        second = await create_employee(client, auth_headers)

        for report in (str(employee.id), second["id"]):
            await client.post(
                f"{BASE}/{report}/manager",
                json={"reporting_manager_id": manager["id"]},
                headers=auth_headers,
            )

        response = await client.post(f"{BASE}/{manager['id']}/archive", headers=auth_headers)
        assert "2 employees still report to" in response.json()["message"]

    async def test_an_archived_employee_is_still_readable(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        """So a stale bookmark resolves rather than 404ing confusingly."""
        await client.post(f"{BASE}/{employee.id}/archive", headers=auth_headers)
        response = await client.get(f"{BASE}/{employee.id}", headers=auth_headers)
        assert response.status_code == 200


# ----------------------------------------------------------------------
class TestExport:
    async def test_exports_csv(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.get(f"{BASE}/export", params={"format": "csv"}, headers=auth_headers)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]

        body = response.content.decode("utf-8-sig")
        assert "Employee ID" in body
        assert employee.employee_code in body

    async def test_exports_xlsx(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.get(f"{BASE}/export", params={"format": "xlsx"}, headers=auth_headers)

        assert response.status_code == 200
        assert "spreadsheetml" in response.headers["content-type"]
        # An xlsx file is a zip archive; check the magic bytes rather than parse it.
        assert response.content[:2] == b"PK"

    async def test_the_export_carries_no_sensitive_value(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Not even masked: a masked value in a spreadsheet is pure noise."""
        await create_employee(
            client,
            auth_headers,
            bank_detail={
                "bank_name": "HDFC Bank",
                "account_number": "50100123456789",
                "ifsc_code": "HDFC0001234",
                "branch_name": "Hitec City",
            },
            identification={"aadhaar_number": "234567890123"},
        )

        body = (
            await client.get(f"{BASE}/export", params={"format": "csv"}, headers=auth_headers)
        ).content.decode("utf-8-sig")

        assert "50100123456789" not in body
        assert "234567890123" not in body
        assert "XXXX" not in body
        assert "Account" not in body

    async def test_the_export_honours_the_filters(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        await create_employee(client, auth_headers, first_name="Excluded", last_name="Person")

        body = (
            await client.get(
                f"{BASE}/export",
                params={"format": "csv", "search": "Priya"},
                headers=auth_headers,
            )
        ).content.decode("utf-8-sig")

        assert "Priya" in body
        assert "Excluded" not in body

    async def test_the_export_is_audited(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        await client.get(f"{BASE}/export", params={"format": "csv"}, headers=auth_headers)

        entries = (
            (await db_session.execute(select(AuditLog).where(AuditLog.action == "employee.exported")))
            .scalars()
            .all()
        )
        assert len(entries) == 1


# ----------------------------------------------------------------------
class TestDashboard:
    async def test_returns_the_headline_figures(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.get(f"{BASE}/dashboard", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total_employees"] == 1
        assert data["employed"] == 1
        assert data["on_probation"] == 1
        assert data["archived"] == 0

    async def test_breaks_down_by_business_unit(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        employee: Employee,
        business_unit: BusinessUnit,
    ) -> None:
        response = await client.get(f"{BASE}/dashboard", headers=auth_headers)
        breakdown = response.json()["data"]["by_business_unit"]
        assert breakdown == [{"label": business_unit.name, "count": 1}]

    async def test_an_archived_employee_leaves_the_headcount(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        await client.post(f"{BASE}/{employee.id}/archive", headers=auth_headers)

        data = (await client.get(f"{BASE}/dashboard", headers=auth_headers)).json()["data"]
        assert data["total_employees"] == 0
        assert data["archived"] == 1


# ----------------------------------------------------------------------
class TestAuditTrail:
    async def test_every_action_is_audited(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        employee: Employee,
        designation: Designation,
    ) -> None:
        await client.patch(f"{BASE}/{employee.id}", json={"nationality": "Indian"}, headers=auth_headers)
        await client.post(f"{BASE}/{employee.id}/confirm", json={}, headers=auth_headers)
        await client.post(
            f"{BASE}/{employee.id}/designation",
            json={"designation_id": str(designation.id)},
            headers=auth_headers,
        )
        await client.post(f"{BASE}/{employee.id}/archive", headers=auth_headers)
        await client.post(f"{BASE}/{employee.id}/restore", headers=auth_headers)

        actions = {
            row.action
            for row in (
                (await db_session.execute(select(AuditLog).where(AuditLog.action.like("employee.%"))))
                .scalars()
                .all()
            )
        }

        assert {
            "employee.updated",
            "employee.confirmed",
            "employee.designation.changed",
            "employee.archived",
            "employee.restored",
        } <= actions

    async def test_a_rejected_write_is_not_audited(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """The request rolls back, so the trail records only what happened."""
        before = len(
            (await db_session.execute(select(AuditLog).where(AuditLog.action == "employee.created")))
            .scalars()
            .all()
        )

        response = await client.post(BASE, json=payload(team_id=str(uuid.uuid4())), headers=auth_headers)
        assert response.status_code == 409

        after = len(
            (await db_session.execute(select(AuditLog).where(AuditLog.action == "employee.created")))
            .scalars()
            .all()
        )
        assert after == before


# ----------------------------------------------------------------------
class TestNotFound:
    async def test_unknown_employee_returns_404(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(f"{BASE}/{uuid.uuid4()}", headers=auth_headers)
        assert response.status_code == 404

    async def test_a_malformed_id_is_a_validation_error(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(f"{BASE}/not-a-uuid", headers=auth_headers)
        assert response.status_code == 422

    async def test_the_dashboard_route_is_not_captured_by_the_id_route(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Registered before /{employee_id}, or "dashboard" would be parsed as a UUID."""
        response = await client.get(f"{BASE}/dashboard", headers=auth_headers)
        assert response.status_code == 200
