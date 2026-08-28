"""Integration tests for the Organization Management module."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.business_unit import BusinessUnit
from app.models.designation import Designation

pytestmark = pytest.mark.integration

API = settings.API_V1_PREFIX
BUSINESS_UNITS = f"{API}/business-units"
DESIGNATIONS = f"{API}/designations"
TEAMS = f"{API}/teams"
GRADES = f"{API}/grades"
LOCATIONS = f"{API}/locations"
ORGANIZATIONS = f"{API}/organizations"


def _business_unit_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": "Consulting", "code": "CONS"}
    payload.update(overrides)
    return payload


class TestEnvelopeAndAuth:
    async def test_list_returns_the_standard_envelope(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(BUSINESS_UNITS, headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"success", "message", "data", "errors"}
        assert body["success"] is True
        assert set(body["data"]) == {"items", "meta"}

    @pytest.mark.parametrize(
        ("method", "url"),
        [
            ("get", BUSINESS_UNITS),
            ("post", BUSINESS_UNITS),
            ("get", GRADES),
            ("post", LOCATIONS),
        ],
    )
    async def test_every_endpoint_requires_authentication(
        self, client: AsyncClient, method: str, url: str
    ) -> None:
        response = await client.get(url) if method == "get" else await client.post(url, json={})
        assert response.status_code == 401


class TestCreate:
    async def test_creates_a_record(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        response = await client.post(BUSINESS_UNITS, headers=auth_headers, json=_business_unit_payload())

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "Consulting"
        assert data["code"] == "CONS"
        assert data["status"] == "active"
        assert data["deleted_at"] is None

    async def test_normalises_name_and_code_before_saving(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            BUSINESS_UNITS,
            headers=auth_headers,
            json=_business_unit_payload(name="  Data   Services  ", code="  data-svc "),
        )

        data = response.json()["data"]
        assert data["name"] == "Data Services"
        assert data["code"] == "DATA-SVC"

    async def test_records_the_creating_user(
        self, client: AsyncClient, auth_headers: dict[str, str], test_user: Any
    ) -> None:
        response = await client.post(BUSINESS_UNITS, headers=auth_headers, json=_business_unit_payload())
        assert response.json()["data"]["created_by"] == str(test_user.id)

    async def test_rejects_an_invalid_payload(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(BUSINESS_UNITS, headers=auth_headers, json={"name": "X"})

        assert response.status_code == 422
        assert response.json()["success"] is False


class TestDuplicateRejection:
    async def test_duplicate_name_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        response = await client.post(
            BUSINESS_UNITS,
            headers=auth_headers,
            json=_business_unit_payload(name=business_unit.name, code="OTHER"),
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "duplicate_name"

    async def test_duplicate_name_is_rejected_case_insensitively(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        """ "GIS" and "gis" are the same master record, not two."""
        response = await client.post(
            BUSINESS_UNITS,
            headers=auth_headers,
            json=_business_unit_payload(name=business_unit.name.upper(), code="OTHER"),
        )
        assert response.status_code == 409

    async def test_duplicate_name_is_rejected_after_whitespace_normalisation(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        response = await client.post(
            BUSINESS_UNITS,
            headers=auth_headers,
            json=_business_unit_payload(name=f"  {business_unit.name}  ", code="OTHER"),
        )
        assert response.status_code == 409

    async def test_duplicate_code_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        response = await client.post(
            BUSINESS_UNITS,
            headers=auth_headers,
            json=_business_unit_payload(name="Something Else", code=business_unit.code.lower()),
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "duplicate_code"

    async def test_an_archived_record_still_reserves_its_code(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        """The unique index covers archived rows, so the message must say so."""
        await client.post(f"{BUSINESS_UNITS}/{business_unit.id}/archive", headers=auth_headers)

        response = await client.post(
            BUSINESS_UNITS,
            headers=auth_headers,
            json=_business_unit_payload(name="Different", code=business_unit.code),
        )

        assert response.status_code == 409
        assert "archived" in response.json()["message"].lower()

    async def test_a_designation_name_may_repeat_across_business_units(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """Designation names are unique per business unit, not globally."""
        first = BusinessUnit(name="Unit One", code="ONE")
        second = BusinessUnit(name="Unit Two", code="TWO")
        db_session.add_all([first, second])
        await db_session.flush()

        created_a = await client.post(
            DESIGNATIONS,
            headers=auth_headers,
            json={"name": "Cloud", "code": "CLOUD-A", "business_unit_id": str(first.id), "level": 2},
        )
        created_b = await client.post(
            DESIGNATIONS,
            headers=auth_headers,
            json={"name": "Cloud", "code": "CLOUD-B", "business_unit_id": str(second.id), "level": 2},
        )

        assert created_a.status_code == 201
        assert created_b.status_code == 201

    async def test_a_designation_name_may_not_repeat_within_one_business_unit(
        self, client: AsyncClient, auth_headers: dict[str, str], designation: Designation
    ) -> None:
        response = await client.post(
            DESIGNATIONS,
            headers=auth_headers,
            json={
                "name": designation.name,
                "code": "OTHER",
                "business_unit_id": str(designation.business_unit_id),
                "level": 3,
            },
        )
        assert response.status_code == 409


class TestReferentialValidation:
    async def test_an_unknown_parent_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            DESIGNATIONS,
            headers=auth_headers,
            json={
                "name": "Orphan",
                "code": "ORPH",
                "business_unit_id": "0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f",
                "level": 2,
            },
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "invalid_business_unit"

    async def test_an_archived_parent_cannot_take_new_children(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        await client.post(f"{BUSINESS_UNITS}/{business_unit.id}/archive", headers=auth_headers)

        response = await client.post(
            DESIGNATIONS,
            headers=auth_headers,
            json={"name": "Late", "code": "LATE", "business_unit_id": str(business_unit.id), "level": 2},
        )
        assert response.status_code == 409

    async def test_an_inactive_parent_cannot_take_new_children(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        await client.patch(
            f"{BUSINESS_UNITS}/{business_unit.id}", headers=auth_headers, json={"status": "inactive"}
        )

        response = await client.post(
            DESIGNATIONS,
            headers=auth_headers,
            json={"name": "Late", "code": "LATE", "business_unit_id": str(business_unit.id), "level": 2},
        )
        assert response.status_code == 409

    async def test_the_parent_is_embedded_in_the_response(
        self, client: AsyncClient, auth_headers: dict[str, str], designation: Designation
    ) -> None:
        """List screens need the parent's name, not another request per row."""
        response = await client.get(f"{DESIGNATIONS}/{designation.id}", headers=auth_headers)

        business_unit = response.json()["data"]["business_unit"]
        assert business_unit["name"] == "Technology Services"
        assert business_unit["code"] == "TECH"

    async def test_the_parent_is_embedded_on_create(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        """A just-created record has no relationship loaded until it is re-read."""
        response = await client.post(
            DESIGNATIONS,
            headers=auth_headers,
            json={"name": "Cloud", "code": "CLOUD", "business_unit_id": str(business_unit.id), "level": 2},
        )

        assert response.status_code == 201
        assert response.json()["data"]["business_unit"]["code"] == "TECH"

    async def test_moving_a_record_returns_its_new_parent(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        designation: Designation,
        db_session: AsyncSession,
    ) -> None:
        """Without a forced re-read the response would echo the previous parent."""
        destination = BusinessUnit(name="Digital Ventures", code="DIGI")
        db_session.add(destination)
        await db_session.flush()

        response = await client.patch(
            f"{DESIGNATIONS}/{designation.id}",
            headers=auth_headers,
            json={"business_unit_id": str(destination.id)},
        )

        assert response.status_code == 200
        assert response.json()["data"]["business_unit"]["code"] == "DIGI"


class TestUpdate:
    async def test_applies_a_partial_update(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        response = await client.patch(
            f"{BUSINESS_UNITS}/{business_unit.id}",
            headers=auth_headers,
            json={"description": "Updated description"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["description"] == "Updated description"
        # Untouched fields survive.
        assert data["name"] == "Technology Services"
        assert data["code"] == "TECH"

    async def test_a_record_may_keep_its_own_name(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        """The uniqueness check must exclude the record being edited."""
        response = await client.patch(
            f"{BUSINESS_UNITS}/{business_unit.id}",
            headers=auth_headers,
            json={"name": business_unit.name, "description": "Same name, new description"},
        )
        assert response.status_code == 200

    async def test_renaming_onto_another_record_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        other = await client.post(BUSINESS_UNITS, headers=auth_headers, json=_business_unit_payload())
        other_id = other.json()["data"]["id"]

        response = await client.patch(
            f"{BUSINESS_UNITS}/{other_id}", headers=auth_headers, json={"name": business_unit.name}
        )
        assert response.status_code == 409

    async def test_an_empty_update_is_a_no_op(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        response = await client.patch(f"{BUSINESS_UNITS}/{business_unit.id}", headers=auth_headers, json={})
        assert response.status_code == 200

    async def test_an_explicit_null_clears_an_optional_field(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        """The only way a client can clear a field it previously set.

        Omitting the key means "leave it alone" under `exclude_unset`, so a
        client that drops empty values -- which `JSON.stringify` does to
        `undefined` -- could never clear one.
        """
        await client.patch(
            f"{BUSINESS_UNITS}/{business_unit.id}",
            headers=auth_headers,
            json={"description": "Something"},
        )

        response = await client.patch(
            f"{BUSINESS_UNITS}/{business_unit.id}", headers=auth_headers, json={"description": None}
        )

        assert response.status_code == 200
        assert response.json()["data"]["description"] is None

    async def test_omitting_a_field_leaves_it_unchanged(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        """The counterpart to the test above: omission must not clear."""
        await client.patch(
            f"{BUSINESS_UNITS}/{business_unit.id}",
            headers=auth_headers,
            json={"description": "Keep me"},
        )

        response = await client.patch(
            f"{BUSINESS_UNITS}/{business_unit.id}", headers=auth_headers, json={"name": "Renamed Unit"}
        )

        assert response.json()["data"]["description"] == "Keep me"

    async def test_an_archived_record_cannot_be_edited(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        await client.post(f"{BUSINESS_UNITS}/{business_unit.id}/archive", headers=auth_headers)

        response = await client.patch(
            f"{BUSINESS_UNITS}/{business_unit.id}", headers=auth_headers, json={"name": "New Name"}
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "record_archived"

    async def test_unknown_record_returns_404(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.patch(
            f"{BUSINESS_UNITS}/0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f",
            headers=auth_headers,
            json={"name": "Nope"},
        )
        assert response.status_code == 404


class TestArchiveAndRestore:
    async def test_archiving_soft_deletes(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        response = await client.post(f"{BUSINESS_UNITS}/{business_unit.id}/archive", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["data"]["deleted_at"] is not None

    async def test_an_archived_record_leaves_the_live_list(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        await client.post(f"{BUSINESS_UNITS}/{business_unit.id}/archive", headers=auth_headers)

        live = await client.get(BUSINESS_UNITS, headers=auth_headers)
        archived = await client.get(BUSINESS_UNITS, headers=auth_headers, params={"archived": "true"})

        live_ids = [row["id"] for row in live.json()["data"]["items"]]
        archived_ids = [row["id"] for row in archived.json()["data"]["items"]]
        assert str(business_unit.id) not in live_ids
        assert str(business_unit.id) in archived_ids

    async def test_an_archived_record_is_still_readable_by_id(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        """A link from the archive list must resolve, not 404."""
        await client.post(f"{BUSINESS_UNITS}/{business_unit.id}/archive", headers=auth_headers)

        response = await client.get(f"{BUSINESS_UNITS}/{business_unit.id}", headers=auth_headers)
        assert response.status_code == 200

    async def test_archiving_twice_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        await client.post(f"{BUSINESS_UNITS}/{business_unit.id}/archive", headers=auth_headers)

        response = await client.post(f"{BUSINESS_UNITS}/{business_unit.id}/archive", headers=auth_headers)
        assert response.status_code == 409

    async def test_a_parent_with_live_children_cannot_be_archived(
        self, client: AsyncClient, auth_headers: dict[str, str], designation: Designation
    ) -> None:
        response = await client.post(
            f"{BUSINESS_UNITS}/{designation.business_unit_id}/archive", headers=auth_headers
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "has_active_children"
        assert "designation" in response.json()["message"]

    async def test_a_parent_can_be_archived_once_its_children_are(
        self, client: AsyncClient, auth_headers: dict[str, str], designation: Designation
    ) -> None:
        await client.post(f"{DESIGNATIONS}/{designation.id}/archive", headers=auth_headers)

        response = await client.post(
            f"{BUSINESS_UNITS}/{designation.business_unit_id}/archive", headers=auth_headers
        )
        assert response.status_code == 200

    async def test_restoring_brings_a_record_back(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        await client.post(f"{BUSINESS_UNITS}/{business_unit.id}/archive", headers=auth_headers)

        response = await client.post(f"{BUSINESS_UNITS}/{business_unit.id}/restore", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["data"]["deleted_at"] is None

    async def test_restoring_a_live_record_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        response = await client.post(f"{BUSINESS_UNITS}/{business_unit.id}/restore", headers=auth_headers)
        assert response.status_code == 409

    async def test_a_child_cannot_be_restored_under_an_archived_parent(
        self, client: AsyncClient, auth_headers: dict[str, str], designation: Designation
    ) -> None:
        await client.post(f"{DESIGNATIONS}/{designation.id}/archive", headers=auth_headers)
        await client.post(f"{BUSINESS_UNITS}/{designation.business_unit_id}/archive", headers=auth_headers)

        response = await client.post(f"{DESIGNATIONS}/{designation.id}/restore", headers=auth_headers)

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "parent_archived"


class TestListing:
    async def _seed(self, client: AsyncClient, headers: dict[str, str], names: list[str]) -> None:
        for index, name in enumerate(names):
            await client.post(
                GRADES,
                headers=headers,
                json={"name": name, "code": f"G{index + 1}", "level": index + 1},
            )

    async def test_pagination_reports_accurate_metadata(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await self._seed(client, auth_headers, ["Alpha", "Bravo", "Charlie", "Delta", "Echo"])

        response = await client.get(GRADES, headers=auth_headers, params={"page": 2, "page_size": 2})

        body = response.json()["data"]
        assert len(body["items"]) == 2
        assert body["meta"] == {
            "page": 2,
            "page_size": 2,
            "total_items": 5,
            "total_pages": 3,
            "has_next": True,
            "has_previous": True,
        }

    async def test_search_matches_name_case_insensitively(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await self._seed(client, auth_headers, ["Alpha", "Bravo", "Charlie"])

        response = await client.get(GRADES, headers=auth_headers, params={"search": "bra"})

        items = response.json()["data"]["items"]
        assert [row["name"] for row in items] == ["Bravo"]

    async def test_search_treats_wildcards_literally(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """An unescaped "%" would match every row instead of none."""
        await self._seed(client, auth_headers, ["Alpha", "Bravo"])

        response = await client.get(GRADES, headers=auth_headers, params={"search": "%"})
        assert response.json()["data"]["items"] == []

    async def test_status_filter(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        await self._seed(client, auth_headers, ["Alpha", "Bravo"])
        listed = await client.get(GRADES, headers=auth_headers)
        first_id = listed.json()["data"]["items"][0]["id"]
        await client.patch(f"{GRADES}/{first_id}", headers=auth_headers, json={"status": "inactive"})

        active = await client.get(GRADES, headers=auth_headers, params={"status": "active"})
        inactive = await client.get(GRADES, headers=auth_headers, params={"status": "inactive"})

        assert len(active.json()["data"]["items"]) == 1
        assert len(inactive.json()["data"]["items"]) == 1

    async def test_sorting_ascending_and_descending(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await self._seed(client, auth_headers, ["Charlie", "Alpha", "Bravo"])

        ascending = await client.get(GRADES, headers=auth_headers, params={"sort_by": "name"})
        descending = await client.get(
            GRADES, headers=auth_headers, params={"sort_by": "name", "sort_order": "desc"}
        )

        assert [r["name"] for r in ascending.json()["data"]["items"]] == ["Alpha", "Bravo", "Charlie"]
        assert [r["name"] for r in descending.json()["data"]["items"]] == ["Charlie", "Bravo", "Alpha"]

    async def test_an_unsupported_sort_column_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Passing the column straight through to SQL would be an injection risk."""
        response = await client.get(GRADES, headers=auth_headers, params={"sort_by": "hashed_password"})

        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "invalid_sort_field"

    async def test_filtering_by_parent(
        self, client: AsyncClient, auth_headers: dict[str, str], designation: Designation
    ) -> None:
        response = await client.get(
            DESIGNATIONS, headers=auth_headers, params={"business_unit_id": str(designation.business_unit_id)}
        )

        items = response.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["id"] == str(designation.id)

    async def test_an_empty_result_set_is_well_formed(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(GRADES, headers=auth_headers, params={"search": "nothing-matches"})

        body = response.json()["data"]
        assert body["items"] == []
        assert body["meta"]["total_items"] == 0
        assert body["meta"]["has_next"] is False


class TestAuditTrail:
    async def _actions(self, session: AsyncSession, entity_type: str) -> list[str]:
        rows = (
            (await session.execute(select(AuditLog).where(AuditLog.entity_type == entity_type)))
            .scalars()
            .all()
        )
        return [row.action for row in rows]

    async def test_create_update_archive_and_restore_are_all_audited(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: Any,
    ) -> None:
        created = await client.post(
            GRADES, headers=auth_headers, json={"name": "Band 1", "code": "B1", "level": 1}
        )
        record_id = created.json()["data"]["id"]

        await client.patch(f"{GRADES}/{record_id}", headers=auth_headers, json={"description": "Updated"})
        await client.post(f"{GRADES}/{record_id}/archive", headers=auth_headers)
        await client.post(f"{GRADES}/{record_id}/restore", headers=auth_headers)

        actions = await self._actions(db_session, "grade")
        assert actions == [
            "organization.grade.created",
            "organization.grade.updated",
            "organization.grade.archived",
            "organization.grade.restored",
        ]

    async def test_the_audit_entry_captures_actor_entity_and_record(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: Any,
    ) -> None:
        created = await client.post(
            GRADES, headers=auth_headers, json={"name": "Band 2", "code": "B2", "level": 2}
        )
        record_id = created.json()["data"]["id"]

        entry = (
            (await db_session.execute(select(AuditLog).where(AuditLog.entity_type == "grade")))
            .scalars()
            .one()
        )

        assert entry.action == "organization.grade.created"
        assert entry.entity_id == record_id
        assert entry.actor_id == test_user.id
        assert entry.outcome == "success"
        assert entry.created_at is not None

    async def test_a_rejected_write_is_not_audited(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        await client.post(GRADES, headers=auth_headers, json={"name": "Band 3", "code": "B3", "level": 1})
        await client.post(GRADES, headers=auth_headers, json={"name": "Band 3", "code": "B4", "level": 2})

        assert await self._actions(db_session, "grade") == ["organization.grade.created"]


class TestHierarchyLifecycle:
    """The hierarchy is two levels: a business unit holds teams and designations."""

    async def test_a_full_hierarchy_can_be_built_through_the_api(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        unit = await client.post(
            BUSINESS_UNITS, headers=auth_headers, json={"name": "Digital", "code": "DIG"}
        )
        unit_id = unit.json()["data"]["id"]

        designation = await client.post(
            DESIGNATIONS,
            headers=auth_headers,
            json={"name": "Research Engineer", "code": "RE", "business_unit_id": unit_id, "level": 3},
        )

        team = await client.post(
            TEAMS,
            headers=auth_headers,
            json={"name": "Applied Research", "business_unit_id": unit_id},
        )

        assert [r.status_code for r in (unit, designation, team)] == [201, 201, 201]
        assert team.json()["data"]["business_unit"]["name"] == "Digital"
        assert designation.json()["data"]["business_unit"]["code"] == "DIG"

    async def test_a_business_unit_cannot_be_archived_while_it_has_teams(
        self, client: AsyncClient, auth_headers: dict[str, str], business_unit: BusinessUnit
    ) -> None:
        await client.post(
            TEAMS, headers=auth_headers, json={"name": "Core", "business_unit_id": str(business_unit.id)}
        )

        response = await client.post(f"{BUSINESS_UNITS}/{business_unit.id}/archive", headers=auth_headers)

        assert response.status_code == 409
        assert "team" in response.json()["message"]


class TestOrganizationProfile:
    def _payload(self, **overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": "JSAN Technologies",
            "legal_name": "JSAN Technologies Private Limited",
            "registration_number": "U72900TG2015PTC098765",
            "timezone": "Asia/Kolkata",
            "currency": "INR",
            "address_line1": "Plot 12, HITEC City",
            "city": "Hyderabad",
            "state": "Telangana",
            "country": "India",
        }
        payload.update(overrides)
        return payload

    async def test_creates_a_profile(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        response = await client.post(ORGANIZATIONS, headers=auth_headers, json=self._payload())

        assert response.status_code == 201
        assert response.json()["data"]["currency"] == "INR"

    async def test_primary_returns_the_configured_profile(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await client.post(ORGANIZATIONS, headers=auth_headers, json=self._payload())

        response = await client.get(f"{ORGANIZATIONS}/primary", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["data"]["name"] == "JSAN Technologies"

    async def test_primary_404s_when_nothing_is_configured(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(f"{ORGANIZATIONS}/primary", headers=auth_headers)
        assert response.status_code == 404

    async def test_duplicate_registration_number_is_rejected(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await client.post(ORGANIZATIONS, headers=auth_headers, json=self._payload())

        response = await client.post(
            ORGANIZATIONS, headers=auth_headers, json=self._payload(name="Another Entity")
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "duplicate_registration_number"
