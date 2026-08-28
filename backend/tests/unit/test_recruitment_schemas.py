import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.recruitment import CandidateCreate


def payload():
    return {
        "job_opening_id": uuid.uuid4(),
        "source_id": uuid.uuid4(),
        "first_name": "Asha",
        "last_name": "Rao",
        "email": "asha@example.com",
        "mobile_number": "+919876543210",
        "experience_years": Decimal("5.5"),
        "current_ctc": Decimal("900000"),
        "expected_ctc": Decimal("1200000"),
        "notice_period_days": 30,
        "skills": ["Python"],
        "resume_document_id": uuid.uuid4(),
    }


def test_candidate_schema_accepts_valid_candidate():
    assert CandidateCreate(**payload()).email == "asha@example.com"


@pytest.mark.parametrize("field,value", [("experience_years", -1), ("notice_period_days", 366)])
def test_candidate_schema_rejects_invalid_ranges(field, value):
    values = payload()
    values[field] = value
    with pytest.raises(ValidationError):
        CandidateCreate(**values)


def test_candidate_schema_rejects_lower_expected_ctc():
    values = payload()
    values["expected_ctc"] = Decimal("800000")
    with pytest.raises(ValidationError, match="Expected CTC"):
        CandidateCreate(**values)
