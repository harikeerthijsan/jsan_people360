"""Employee schema validation and masking.

Pure logic: no database, no HTTP. These are the rules that stop a mistyped PAN or
an unmasked account number ever reaching the layers that would have to deal with
them.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.employee import (
    EmployeeBankInput,
    EmployeeBankRead,
    EmployeeCreate,
    EmployeeIdentificationInput,
    EmployeeIdentificationRead,
    EmployeeListParams,
    PromoteEmployeeRequest,
    validate_aadhaar,
    validate_employee_pan,
    validate_ifsc,
)
from app.utils.masking import mask_account_number, mask_tail

UUID_VALUE = "0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f"


def create_payload(**overrides: object) -> dict[str, object]:
    return {
        "first_name": "Priya",
        "last_name": "Sharma",
        "official_email": "priya.sharma@jsan.example",
        "joining_date": "2026-01-15",
        **overrides,
    }


class TestAadhaar:
    def test_accepts_a_well_formed_number(self) -> None:
        assert validate_aadhaar("234567890123") == "234567890123"

    def test_strips_the_separators_people_type(self) -> None:
        assert validate_aadhaar("2345 6789 0123") == "234567890123"
        assert validate_aadhaar("2345-6789-0123") == "234567890123"

    @pytest.mark.parametrize(
        ("value", "why"),
        [
            ("1234567890123", "thirteen digits"),
            ("23456789012", "eleven digits"),
            ("034567890123", "starts with zero"),
            ("134567890123", "starts with one"),
            ("23456789012A", "contains a letter"),
        ],
    )
    def test_rejects_a_malformed_number(self, value: str, why: str) -> None:
        with pytest.raises(ValueError):
            validate_aadhaar(value)

    def test_treats_blank_as_absent(self) -> None:
        assert validate_aadhaar("   ") is None
        assert validate_aadhaar(None) is None


class TestPan:
    def test_upper_cases_and_accepts(self) -> None:
        assert validate_employee_pan(" abcde1234f ") == "ABCDE1234F"

    @pytest.mark.parametrize("value", ["ABCD1234F", "ABCDE12345", "ABCDE1234", "1BCDE1234F"])
    def test_rejects_a_malformed_pan(self, value: str) -> None:
        with pytest.raises(ValueError):
            validate_employee_pan(value)


class TestIfsc:
    def test_upper_cases_and_accepts(self) -> None:
        assert validate_ifsc("hdfc0001234") == "HDFC0001234"

    @pytest.mark.parametrize(
        ("value", "why"),
        [
            ("HDFC1001234", "fifth character is not zero"),
            ("HDF00001234", "only three letters"),
            ("HDFC000123", "too short"),
        ],
    )
    def test_rejects_a_malformed_code(self, value: str, why: str) -> None:
        with pytest.raises(ValueError):
            validate_ifsc(value)


class TestMasking:
    def test_keeps_the_last_four_characters(self) -> None:
        assert mask_account_number("50100123456789") == "XXXXXXXXXX6789"

    def test_masks_a_short_value_entirely(self) -> None:
        """Revealing all of a four-character value would defeat the point."""
        assert mask_tail("1234", visible=4) == "XXXX"

    def test_preserves_the_original_length(self) -> None:
        """So the reader can sanity-check what they entered."""
        assert len(mask_account_number("50100123456789")) == len("50100123456789")

    def test_blank_becomes_none(self) -> None:
        assert mask_tail("  ") is None
        assert mask_tail(None) is None

    def test_the_read_schema_masks_the_account_number(self) -> None:
        read = EmployeeBankRead(
            id=UUID_VALUE,
            bank_name="HDFC Bank",
            account_number="50100123456789",
            ifsc_code="HDFC0001234",
            branch_name="Hitec City",
        )
        assert read.account_number == "XXXXXXXXXX6789"
        assert "123456" not in read.account_number

    def test_the_ifsc_is_not_masked(self) -> None:
        """A branch code identifies a bank, not a person."""
        read = EmployeeBankRead(
            id=UUID_VALUE,
            bank_name="HDFC Bank",
            account_number="50100123456789",
            ifsc_code="HDFC0001234",
            branch_name="Hitec City",
        )
        assert read.ifsc_code == "HDFC0001234"

    def test_the_read_schema_masks_identity_documents(self) -> None:
        read = EmployeeIdentificationRead(
            id=UUID_VALUE,
            aadhaar_number="234567890123",
            pan_number="ABCDE1234F",
            passport_number="M1234567",
            uan_number="100200300400",
        )
        assert read.aadhaar_number == "XXXXXXXX0123"
        assert read.pan_number == "XXXXXX234F"
        assert read.passport_number == "XXXXX567"

    def test_the_read_schema_does_not_mask_payroll_references(self) -> None:
        """UAN already appears on every payslip; masking it helps nobody."""
        read = EmployeeIdentificationRead(id=UUID_VALUE, uan_number="100200300400")
        assert read.uan_number == "100200300400"


class TestEmployeeCreate:
    def test_accepts_a_minimal_payload(self) -> None:
        employee = EmployeeCreate(**create_payload())
        assert employee.employment_status == "probation"

    def test_normalises_the_identifiers(self) -> None:
        employee = EmployeeCreate(
            **create_payload(
                first_name="  Priya  ",
                last_name="Van   Sharma",
                official_email=" Priya@JSAN.EXAMPLE ",
            )
        )
        assert employee.first_name == "Priya"
        assert employee.last_name == "Van Sharma"
        assert employee.official_email == "priya@jsan.example"

    def test_rejects_an_employee_code(self) -> None:
        """It is generated by the database and can never be supplied."""
        with pytest.raises(ValidationError):
            EmployeeCreate(**create_payload(employee_code="EMP-000001"))

    def test_requires_a_joining_date(self) -> None:
        payload = create_payload()
        del payload["joining_date"]
        with pytest.raises(ValidationError):
            EmployeeCreate(**payload)

    def test_rejects_a_joining_date_far_in_the_future(self) -> None:
        far = date.today() + timedelta(days=400)
        with pytest.raises(ValidationError):
            EmployeeCreate(**create_payload(joining_date=far.isoformat()))

    def test_allows_a_joining_date_shortly_in_the_future(self) -> None:
        """Pre-boarding someone before their start date is the normal case."""
        soon = date.today() + timedelta(days=30)
        assert EmployeeCreate(**create_payload(joining_date=soon.isoformat()))

    def test_rejects_two_addresses_of_the_same_type(self) -> None:
        address = {
            "address_type": "current",
            "address_line1": "12 Main Street",
            "city": "Hyderabad",
            "state": "Telangana",
            "country": "India",
            "postal_code": "500081",
        }
        with pytest.raises(ValidationError, match="only one address of each type"):
            EmployeeCreate(**create_payload(addresses=[address, dict(address)]))

    def test_accepts_one_address_of_each_type(self) -> None:
        base = {
            "address_line1": "12 Main Street",
            "city": "Hyderabad",
            "state": "Telangana",
            "country": "India",
            "postal_code": "500081",
        }
        employee = EmployeeCreate(
            **create_payload(
                addresses=[
                    {"address_type": "current", **base},
                    {"address_type": "permanent", **base},
                ]
            )
        )
        assert len(employee.addresses) == 2


class TestPromotion:
    def test_rejects_a_promotion_that_changes_nothing(self) -> None:
        with pytest.raises(ValidationError, match="at least one"):
            PromoteEmployeeRequest()

    def test_accepts_a_ctc_only_promotion(self) -> None:
        assert PromoteEmployeeRequest(ctc="1200000.00").ctc is not None

    def test_defaults_the_effective_date_to_today(self) -> None:
        assert PromoteEmployeeRequest(grade_id=UUID_VALUE).effective_date == date.today()


class TestBankInput:
    def test_normalises_the_account_number(self) -> None:
        bank = EmployeeBankInput(
            bank_name="HDFC Bank",
            account_number=" 5010 0123 4567 89 ",
            ifsc_code="hdfc0001234",
            branch_name="Hitec City",
        )
        assert bank.account_number == "50100123456789"
        assert bank.ifsc_code == "HDFC0001234"

    def test_rejects_a_non_alphanumeric_account_number(self) -> None:
        with pytest.raises(ValidationError):
            EmployeeBankInput(
                bank_name="HDFC Bank",
                account_number="5010/0123",
                ifsc_code="HDFC0001234",
                branch_name="Hitec City",
            )


class TestIdentificationInput:
    def test_normalises_every_identifier(self) -> None:
        identification = EmployeeIdentificationInput(
            aadhaar_number="2345 6789 0123",
            pan_number="abcde1234f",
            uan_number="100 200 300 400",
        )
        assert identification.aadhaar_number == "234567890123"
        assert identification.pan_number == "ABCDE1234F"
        assert identification.uan_number == "100200300400"

    def test_every_field_is_optional(self) -> None:
        assert EmployeeIdentificationInput().aadhaar_number is None

    @pytest.mark.parametrize(
        ("field", "value"),
        [("uan_number", "12345"), ("esi_number", "123"), ("pan_number", "NOTAPAN")],
    )
    def test_rejects_a_malformed_identifier(self, field: str, value: str) -> None:
        with pytest.raises(ValidationError):
            EmployeeIdentificationInput(**{field: value})


class TestListParams:
    def test_defaults_to_employee_code_order(self) -> None:
        """Employees have no `name` column -- theirs is stored in two."""
        assert EmployeeListParams().sort_by == "employee_code"

    def test_rejects_the_master_status_filter(self) -> None:
        """`status` belongs to master data; an employee has `employment_status`."""
        with pytest.raises(ValidationError):
            EmployeeListParams(status="active")

    def test_accepts_the_lifecycle_status(self) -> None:
        assert EmployeeListParams(employment_status="probation").employment_status == "probation"
