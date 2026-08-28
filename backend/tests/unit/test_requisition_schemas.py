from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.requisition import RequisitionCreate


def payload():
    ids = [uuid4() for _ in range(11)]
    return {
        "job_title": "Senior Engineer",
        "hiring_type": "new_position",
        "request_type": "new_position",
        "business_unit_id": ids[0],
        "team_id": None,
        "location_id": ids[3],
        "designation_id": ids[4],
        "grade_id": None,
        "employment_type_id": ids[5],
        "openings": 2,
        "experience_min": 3,
        "experience_max": 5,
        "skills": ["Python"],
        "certifications": [],
        "salary_from": Decimal("100"),
        "salary_to": Decimal("200"),
        "budget_approved": True,
        "hiring_manager_id": ids[6],
        "second_approver_id": ids[7],
        "hr_approver_id": ids[8],
        "recruiter_id": None,
        "target_joining_date": date.today() + timedelta(days=30),
        "priority": "high",
        "responsibilities": "Build reliable software",
        "requirements": "Strong engineering experience",
        "working_model": "hybrid",
        "business_justification": "Approved team expansion",
    }


def test_valid_requisition():
    assert RequisitionCreate(**payload()).openings == 2


@pytest.mark.parametrize(
    "change", [{"openings": 0}, {"salary_from": 300, "salary_to": 200}, {"target_joining_date": date.today()}]
)
def test_invalid_requisition(change):
    with pytest.raises(ValidationError):
        RequisitionCreate(**(payload() | change))
