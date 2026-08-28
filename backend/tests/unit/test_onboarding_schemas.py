from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.onboarding import ProfileUpdate


def profile_payload():
    return {
        "joining_date": date.today() + timedelta(days=15),
        "joining_confirmed": True,
        "first_name": "Asha",
        "last_name": "Rao",
        "date_of_birth": date(1995, 5, 5),
        "gender": "female",
        "blood_group": "O+",
        "marital_status": "single",
        "nationality": "Indian",
        "personal_email": "asha@example.com",
        "mobile_number": "+91 9876543210",
        "emergency_contact": {"name": "Anil Rao", "relationship": "Father", "phone_number": "9876543211"},
        "addresses": [
            {
                "address_type": "current",
                "address_line1": "1 Main Road",
                "city": "Hyderabad",
                "state": "Telangana",
                "country": "India",
                "postal_code": "500001",
            },
            {
                "address_type": "permanent",
                "address_line1": "2 Park Road",
                "city": "Hyderabad",
                "state": "Telangana",
                "country": "India",
                "postal_code": "500002",
            },
        ],
        "bank_details": {
            "bank_name": "HDFC Bank",
            "account_holder_name": "Asha Rao",
            "account_number": "123456789012",
            "ifsc_code": "HDFC0001234",
            "branch_name": "Main Branch",
        },
        "aadhaar_number": "234567890123",
        "pan_number": "ABCDE1234F",
    }


def test_complete_profile_is_valid():
    assert ProfileUpdate(**profile_payload()).joining_confirmed is True


def test_both_address_types_are_required():
    values = profile_payload()
    values["addresses"][1]["address_type"] = "current"
    with pytest.raises(ValidationError, match="Current and permanent"):
        ProfileUpdate(**values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("aadhaar_number", "123"),
        ("pan_number", "BADPAN"),
        (
            "bank_details",
            {
                "bank_name": "HDFC Bank",
                "account_holder_name": "Asha Rao",
                "account_number": "123456789012",
                "ifsc_code": "INVALID",
                "branch_name": "Main Branch",
            },
        ),
    ],
)
def test_sensitive_identifiers_are_validated(field, value):
    values = profile_payload()
    values[field] = value
    with pytest.raises(ValidationError):
        ProfileUpdate(**values)
