"""Unit tests for the master-data validation boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.enums import RecordStatus
from app.schemas.business_unit import BusinessUnitCreate, BusinessUnitUpdate
from app.schemas.designation import DesignationCreate
from app.schemas.location import LocationCreate
from app.schemas.masters import MasterListParams, SortOrder
from app.schemas.organization import OrganizationCreate

pytestmark = pytest.mark.unit


def _organization_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
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


class TestNameNormalisation:
    def test_leading_and_trailing_whitespace_is_removed(self) -> None:
        assert BusinessUnitCreate(name="  Technology  ", code="TECH").name == "Technology"

    def test_internal_whitespace_runs_are_collapsed(self) -> None:
        """Otherwise "Web  Development" would slip past the uniqueness check."""
        assert BusinessUnitCreate(name="Web   Development", code="WEB").name == "Web Development"

    def test_a_blank_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BusinessUnitCreate(name="   ", code="TECH")

    def test_a_one_character_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BusinessUnitCreate(name="A", code="TECH")


class TestCodeNormalisation:
    def test_codes_are_upper_cased(self) -> None:
        assert BusinessUnitCreate(name="Technology", code="tech").code == "TECH"

    def test_internal_spaces_become_underscores(self) -> None:
        assert BusinessUnitCreate(name="Full Time", code="full time").code == "FULL_TIME"

    def test_hyphens_and_underscores_are_allowed(self) -> None:
        assert BusinessUnitCreate(name="Technology", code="tech-01_a").code == "TECH-01_A"

    @pytest.mark.parametrize("code", ["-LEADING", "_LEADING", "HAS.DOT", "HAS/SLASH", "HAS@AT"])
    def test_invalid_characters_are_rejected(self, code: str) -> None:
        with pytest.raises(ValidationError):
            BusinessUnitCreate(name="Technology", code=code)

    def test_a_blank_code_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BusinessUnitCreate(name="Technology", code="  ")


class TestDescriptionNormalisation:
    def test_a_blank_description_becomes_none(self) -> None:
        """Storing "" and NULL for the same idea makes downstream checks wrong."""
        assert BusinessUnitCreate(name="Technology", code="TECH", description="   ").description is None

    def test_description_defaults_to_none(self) -> None:
        assert BusinessUnitCreate(name="Technology", code="TECH").description is None


class TestStatus:
    def test_status_defaults_to_active(self) -> None:
        assert BusinessUnitCreate(name="Technology", code="TECH").status is RecordStatus.ACTIVE

    def test_an_unknown_status_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BusinessUnitCreate(name="Technology", code="TECH", status="retired")


class TestUpdateSemantics:
    def test_omitted_fields_are_not_reported_as_set(self) -> None:
        """This is what lets a PATCH leave untouched columns alone."""
        payload = BusinessUnitUpdate(name="Renamed")
        assert payload.model_dump(exclude_unset=True) == {"name": "Renamed"}

    def test_an_empty_update_is_empty(self) -> None:
        assert BusinessUnitUpdate().model_dump(exclude_unset=True) == {}

    def test_unknown_fields_are_rejected(self) -> None:
        """`extra="forbid"` turns a client-side typo into a 422, not a silent no-op."""
        with pytest.raises(ValidationError):
            BusinessUnitUpdate(nmae="typo")


class TestLocationValidation:
    def _payload(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": "Hyderabad HQ",
            "code": "HYD",
            "country": "India",
            "state": "Telangana",
            "city": "Hyderabad",
            "address": "Plot 12, HITEC City, Madhapur",
            "timezone": "Asia/Kolkata",
        }
        payload.update(overrides)
        return payload

    def test_a_valid_location_is_accepted(self) -> None:
        assert LocationCreate(**self._payload()).timezone == "Asia/Kolkata"

    @pytest.mark.parametrize("timezone", ["Mars/Olympus", "IST", "Asia/Kolkatta", ""])
    def test_an_unknown_timezone_is_rejected(self, timezone: str) -> None:
        """A typo here would become a wrong-by-hours bug in attendance later."""
        with pytest.raises(ValidationError):
            LocationCreate(**self._payload(timezone=timezone))

    def test_place_names_are_whitespace_collapsed(self) -> None:
        assert LocationCreate(**self._payload(city="  New   Delhi ")).city == "New Delhi"


class TestDesignationValidation:
    def test_level_must_be_at_least_one(self) -> None:
        with pytest.raises(ValidationError):
            DesignationCreate(
                name="Engineer",
                code="ENG",
                business_unit_id="0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f",
                level=0,
            )

    def test_a_valid_level_is_accepted(self) -> None:
        designation = DesignationCreate(
            name="Engineer",
            code="ENG",
            business_unit_id="0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f",
            level=3,
        )
        assert designation.level == 3


class TestOrganizationValidation:
    def test_a_valid_profile_is_accepted(self) -> None:
        assert OrganizationCreate(**_organization_payload()).currency == "INR"

    def test_currency_is_upper_cased(self) -> None:
        assert OrganizationCreate(**_organization_payload(currency="inr")).currency == "INR"

    @pytest.mark.parametrize("currency", ["RUPEE", "IN", "1NR"])
    def test_a_malformed_currency_is_rejected(self, currency: str) -> None:
        with pytest.raises(ValidationError):
            OrganizationCreate(**_organization_payload(currency=currency))

    def test_gst_and_pan_are_optional(self) -> None:
        organization = OrganizationCreate(**_organization_payload())
        assert organization.gst_number is None
        assert organization.pan_number is None

    def test_a_valid_pan_is_accepted_and_upper_cased(self) -> None:
        organization = OrganizationCreate(**_organization_payload(pan_number="aabcj1234m"))
        assert organization.pan_number == "AABCJ1234M"

    @pytest.mark.parametrize("pan", ["ABCDE1234", "ABCD12345F", "12345ABCDE"])
    def test_a_malformed_pan_is_rejected(self, pan: str) -> None:
        with pytest.raises(ValidationError):
            OrganizationCreate(**_organization_payload(pan_number=pan))

    def test_a_valid_gstin_is_accepted(self) -> None:
        organization = OrganizationCreate(**_organization_payload(gst_number="36AABCJ1234M1ZP"))
        assert organization.gst_number == "36AABCJ1234M1ZP"

    @pytest.mark.parametrize("gstin", ["36AABCJ1234M1Z", "AABCJ1234M1ZP36", "36aabcj1234m1xp"])
    def test_a_malformed_gstin_is_rejected(self, gstin: str) -> None:
        with pytest.raises(ValidationError):
            OrganizationCreate(**_organization_payload(gst_number=gstin))

    def test_a_blank_optional_identifier_becomes_none(self) -> None:
        organization = OrganizationCreate(**_organization_payload(gst_number="  "))
        assert organization.gst_number is None

    def test_website_must_be_a_url(self) -> None:
        with pytest.raises(ValidationError):
            OrganizationCreate(**_organization_payload(website="not a url"))

    def test_a_valid_website_is_stored_as_a_string(self) -> None:
        organization = OrganizationCreate(**_organization_payload(website="https://jsan.example"))
        assert isinstance(organization.website, str)
        assert organization.website.startswith("https://jsan.example")


class TestListParams:
    def test_defaults(self) -> None:
        params = MasterListParams()
        assert params.page == 1
        assert params.page_size == 20
        assert params.sort_by == "name"
        assert params.sort_order is SortOrder.ASC
        assert params.archived is False

    def test_offset_is_derived_from_the_page(self) -> None:
        assert MasterListParams(page=3, page_size=25).offset == 50

    def test_descending_reflects_the_sort_order(self) -> None:
        assert MasterListParams(sort_order="desc").descending is True
        assert MasterListParams(sort_order="asc").descending is False

    def test_a_blank_search_becomes_none(self) -> None:
        assert MasterListParams(search="   ").search is None

    def test_page_size_is_capped(self) -> None:
        """An uncapped page size is an easy way to make the server do too much work."""
        with pytest.raises(ValidationError):
            MasterListParams(page_size=5000)

    def test_page_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            MasterListParams(page=0)
