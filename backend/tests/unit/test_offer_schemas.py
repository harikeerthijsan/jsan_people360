import uuid
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.offer import OfferCreate


def offer_payload():
    return {
        "candidate_id": uuid.uuid4(),
        "ctc": 1_200_000,
        "joining_date": date.today() + timedelta(days=30),
        "probation_months": 6,
        "notice_period_days": 30,
        "work_mode": "hybrid",
        "benefits": "Medical insurance",
        "leave_policy_summary": "Company leave policy",
        "working_hours": "Nine hours",
        "confidentiality": "Confidentiality terms",
        "expiry_date": date.today() + timedelta(days=10),
        "salary_components": [
            {"name": "Basic Salary", "component_type": "fixed", "annual_amount": 600_000},
            {"name": "HRA", "component_type": "allowance", "annual_amount": 300_000},
            {"name": "Special Allowance", "component_type": "allowance", "annual_amount": 300_000},
        ],
        "hr_executive_id": uuid.uuid4(),
        "hr_manager_id": uuid.uuid4(),
        "business_unit_head_id": uuid.uuid4(),
    }


def test_valid_offer_compensation():
    assert OfferCreate(**offer_payload()).ctc == 1_200_000


def test_offer_requires_mandatory_salary_components():
    values = offer_payload()
    values["salary_components"][2]["name"] = "Bonus"
    with pytest.raises(ValidationError, match="Special Allowance"):
        OfferCreate(**values)


def test_offer_components_must_equal_ctc():
    values = offer_payload()
    values["salary_components"][0]["annual_amount"] = 500_000
    with pytest.raises(ValidationError, match="equal CTC"):
        OfferCreate(**values)


def test_offer_expiry_must_precede_joining():
    values = offer_payload()
    values["expiry_date"] = values["joining_date"]
    with pytest.raises(ValidationError, match="before joining"):
        OfferCreate(**values)
