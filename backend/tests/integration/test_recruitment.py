from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.business_unit import BusinessUnit
from app.models.designation import Designation
from app.models.document import Document
from app.models.document_category import DocumentCategory, DocumentType
from app.models.employee import Employee
from app.models.employment_type import EmploymentType
from app.models.grade import Grade
from app.models.location import Location
from app.models.recruitment import CandidateSource, RecruitmentStage
from app.models.requisition import JobRequisition
from app.models.user import User

BASE = f"{settings.API_V1_PREFIX}/recruitment"


async def test_ats_opening_candidate_duplicate_and_stage_workflow(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
    business_unit: BusinessUnit,
    designation: Designation,
    grade: Grade,
    location: Location,
    employment_type: EmploymentType,
    employee: Employee,
):
    requisition = JobRequisition(
        job_title="ATS Engineer",
        hiring_type="new_position",
        request_type="new_position",
        status="approved",
        business_unit_id=business_unit.id,
        location_id=location.id,
        designation_id=designation.id,
        grade_id=grade.id,
        employment_type_id=employment_type.id,
        openings=1,
        experience_min=2,
        skills=["Python"],
        certifications=[],
        budget_approved=True,
        hiring_manager_id=test_user.id,
        second_approver_id=test_user.id,
        hr_approver_id=test_user.id,
        target_joining_date=date.today() + timedelta(days=30),
        priority="high",
        responsibilities="Build services",
        requirements="Python",
        working_model="hybrid",
        business_justification="Growth",
    )
    category = DocumentCategory(name="Recruitment", code="REC", status="active")
    db_session.add(category)
    await db_session.flush()
    document_type = DocumentType(name="Resume", code="RES", category_id=category.id, status="active")
    db_session.add(document_type)
    await db_session.flush()
    resume = Document(
        name="Resume",
        category_id=category.id,
        document_type_id=document_type.id,
        owner_type="user",
        owner_id=test_user.id,
    )
    db_session.add_all([requisition, resume])
    await db_session.flush()
    source = (
        await db_session.execute(select(CandidateSource).where(CandidateSource.name == "LinkedIn"))
    ).scalar_one()
    screening = (
        await db_session.execute(select(RecruitmentStage).where(RecruitmentStage.name == "Screening"))
    ).scalar_one()

    opening_response = await client.post(
        f"{BASE}/openings", json={"requisition_id": str(requisition.id)}, headers=auth_headers
    )
    assert opening_response.status_code == 201, opening_response.text
    opening = opening_response.json()["data"]
    published = await client.post(f"{BASE}/openings/{opening['id']}/publish", headers=auth_headers)
    assert published.status_code == 200

    payload = {
        "job_opening_id": opening["id"],
        "source_id": str(source.id),
        "first_name": "Asha",
        "last_name": "Rao",
        "email": "asha.rao@example.com",
        "mobile_number": "+919876543210",
        "experience_years": 5,
        "current_ctc": 900000,
        "expected_ctc": 1200000,
        "notice_period_days": 30,
        "skills": ["Python", "FastAPI"],
        "resume_document_id": str(resume.id),
    }
    created = await client.post(f"{BASE}/candidates", json=payload, headers=auth_headers)
    assert created.status_code == 201, created.text
    candidate = created.json()["data"]
    assert candidate["candidate_code"].startswith("CAN-")
    assert candidate["stage"]["name"] == "Applied"
    duplicate = await client.post(f"{BASE}/candidates", json=payload, headers=auth_headers)
    assert duplicate.status_code == 409
    moved = await client.post(
        f"{BASE}/candidates/{candidate['id']}/stage",
        json={"stage_id": str(screening.id), "comments": "Passed screening"},
        headers=auth_headers,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["data"]["stage"]["name"] == "Screening"
    note = await client.post(
        f"{BASE}/candidates/{candidate['id']}/notes",
        json={"body": "Strong profile", "is_internal": True},
        headers=auth_headers,
    )
    assert note.status_code == 201, note.text
    dashboard = await client.get(f"{BASE}/dashboard", headers=auth_headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["data"]["total_applicants"] == 1
    pool = await client.post(f"{BASE}/talent-pools", json={"name": "Python Engineers"}, headers=auth_headers)
    assert pool.status_code == 201, pool.text
    membership = await client.post(
        f"{BASE}/talent-pools/{pool.json()['data']['id']}/members",
        json={"candidate_id": candidate["id"]},
        headers=auth_headers,
    )
    assert membership.status_code == 201, membership.text

    starts_at = datetime.now(UTC) + timedelta(days=2)
    interview_payload = {
        "candidate_id": candidate["id"],
        "interview_type": "technical",
        "interview_round": "Technical Round 1",
        "starts_at": starts_at.isoformat(),
        "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
        "time_zone": "Asia/Kolkata",
        "mode": "online",
        "meeting_link": "https://meet.example.com/interview",
        "panels": [
            {
                "employee_id": str(employee.id),
                "designation_id": str(designation.id),
                "panel_role": "lead_interviewer",
            }
        ],
    }
    scheduled = await client.post(
        f"{settings.API_V1_PREFIX}/interviews", json=interview_payload, headers=auth_headers
    )
    assert scheduled.status_code == 201, scheduled.text
    interview = scheduled.json()["data"]
    assert interview["interview_code"].startswith("INT-")
    conflict = await client.post(
        f"{settings.API_V1_PREFIX}/interviews", json=interview_payload, headers=auth_headers
    )
    assert conflict.status_code == 409
    categories = [
        "technical_skills",
        "communication",
        "problem_solving",
        "domain_knowledge",
        "attitude",
        "culture_fit",
    ]
    feedback = await client.post(
        f"{settings.API_V1_PREFIX}/interviews/{interview['id']}/feedback",
        json={
            "interviewer_id": str(employee.id),
            "overall_comments": "Strong candidate",
            "recommendation": "hire",
            "scores": [{"category": x, "score": 8} for x in categories],
        },
        headers=auth_headers,
    )
    assert feedback.status_code == 201, feedback.text
    assert feedback.json()["data"]["overall_score"] == 8
    decision_response = await client.post(
        f"{settings.API_V1_PREFIX}/interviews/{interview['id']}/decision",
        json={"decision": "final_selection", "comments": "Selected"},
        headers=auth_headers,
    )
    assert decision_response.status_code == 200, decision_response.text
    assert decision_response.json()["data"]["status"] == "completed"
