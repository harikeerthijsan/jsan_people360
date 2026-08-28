from datetime import date, timedelta

from httpx import AsyncClient

from app.core.config import settings
from app.models.business_unit import BusinessUnit
from app.models.designation import Designation
from app.models.employment_type import EmploymentType
from app.models.grade import Grade
from app.models.location import Location
from app.models.user import User

BASE = f"{settings.API_V1_PREFIX}/requisitions"


async def test_create_submit_approve_and_notify(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: User,
    business_unit: BusinessUnit,
    designation: Designation,
    grade: Grade,
    location: Location,
    employment_type: EmploymentType,
):
    payload = {
        "job_title": "Platform Engineer",
        "hiring_type": "new_position",
        "request_type": "new_position",
        "business_unit_id": str(business_unit.id),
        "team_id": None,
        "location_id": str(location.id),
        "designation_id": str(designation.id),
        "grade_id": str(grade.id),
        "employment_type_id": str(employment_type.id),
        "openings": 2,
        "experience_min": 3,
        "experience_max": 6,
        "education": "Bachelor degree",
        "skills": ["Python"],
        "certifications": [],
        "salary_from": "100000",
        "salary_to": "200000",
        "budget_approved": True,
        "hiring_manager_id": str(test_user.id),
        "second_approver_id": str(test_user.id),
        "hr_approver_id": str(test_user.id),
        "recruiter_id": None,
        "target_joining_date": str(date.today() + timedelta(days=60)),
        "priority": "high",
        "responsibilities": "Build and operate reliable platform services.",
        "requirements": "Strong Python and distributed systems experience.",
        "benefits": "Flexible work",
        "working_model": "hybrid",
        "business_justification": "Approved capacity for the platform roadmap.",
    }
    created = await client.post(BASE, json=payload, headers=auth_headers)
    assert created.status_code == 201, created.text
    record = created.json()["data"]
    assert record["requisition_code"].startswith("REQ-")
    submitted = await client.post(f"{BASE}/{record['id']}/submit", headers=auth_headers)
    assert submitted.status_code == 200, submitted.text
    for _ in range(3):
        approved = await client.post(
            f"{BASE}/{record['id']}/approve", json={"comments": "Approved"}, headers=auth_headers
        )
        assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["status"] == "approved"
    for action, expected in (("open", "open"), ("hold", "on_hold"), ("resume", "open")):
        response = await client.post(
            f"{BASE}/{record['id']}/{action}", json={"comments": "Lifecycle test"}, headers=auth_headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == expected
    dashboard = await client.get(f"{BASE}/dashboard", headers=auth_headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["data"]["hiring_trend"]
    detail = (await client.get(f"{BASE}/{record['id']}", headers=auth_headers)).json()["data"]
    assert len(detail["approvals"]) == 3
    assert any(item["action"] == "submitted" for item in detail["history"])
    notifications = (
        await client.get(f"{settings.API_V1_PREFIX}/notifications", headers=auth_headers)
    ).json()["data"]
    assert any(item["notification_type"] == "requisition" for item in notifications)
