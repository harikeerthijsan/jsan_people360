from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.business_unit import BusinessUnit
from app.models.designation import Designation
from app.models.document import Document
from app.models.document_category import DocumentCategory, DocumentType
from app.models.employment_type import EmploymentType
from app.models.grade import Grade
from app.models.location import Location
from app.models.offer import Offer
from app.models.recruitment import Candidate, CandidateSource, JobOpening, RecruitmentStage
from app.models.requisition import JobRequisition
from app.models.user import User

BASE = f"{settings.API_V1_PREFIX}/onboarding"
REQUIRED_DOCUMENTS = [
    "Photograph",
    "Aadhaar",
    "PAN",
    "Resume",
    "Educational Certificates",
    "Experience Letters",
    "Bank Passbook/Cancelled Cheque",
]


async def test_complete_preboarding_conversion_and_onboarding_workflow(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
    business_unit: BusinessUnit,
    designation: Designation,
    grade: Grade,
    location: Location,
    employment_type: EmploymentType,
):
    requisition = JobRequisition(
        job_title="Onboarding Engineer",
        hiring_type="new_position",
        request_type="new_position",
        status="approved",
        business_unit_id=business_unit.id,
        location_id=location.id,
        designation_id=designation.id,
        grade_id=grade.id,
        employment_type_id=employment_type.id,
        openings=1,
        experience_min=1,
        skills=["Python"],
        certifications=[],
        budget_approved=True,
        hiring_manager_id=test_user.id,
        second_approver_id=test_user.id,
        hr_approver_id=test_user.id,
        target_joining_date=date.today() + timedelta(days=20),
        priority="high",
        responsibilities="Build",
        requirements="Python",
        working_model="hybrid",
        business_justification="Growth",
    )
    db_session.add(requisition)
    await db_session.flush()
    opening = JobOpening(requisition_id=requisition.id, status="open")
    db_session.add(opening)
    await db_session.flush()
    source = await db_session.scalar(select(CandidateSource).limit(1))
    selected = await db_session.scalar(
        select(RecruitmentStage).where(func.lower(RecruitmentStage.name) == "selected")
    )
    candidate = Candidate(
        job_opening_id=opening.id,
        source_id=source.id,
        stage_id=selected.id,
        first_name="Asha",
        last_name="Rao",
        email="asha.onboarding@example.com",
        mobile_number="9876543210",
    )
    db_session.add(candidate)
    await db_session.flush()
    offer = Offer(
        candidate_id=candidate.id,
        job_opening_id=opening.id,
        status="accepted",
        ctc=1_200_000,
        joining_date=date.today() + timedelta(days=20),
        probation_months=6,
        notice_period_days=30,
        work_mode="hybrid",
        benefits="Insurance",
        leave_policy_summary="Policy",
        working_hours="Nine hours",
        confidentiality="Confidential",
        expiry_date=date.today() + timedelta(days=5),
    )
    db_session.add(offer)
    category = DocumentCategory(name="Onboarding", code="ONB", status="active")
    db_session.add(category)
    await db_session.flush()
    document_type = DocumentType(
        name="Onboarding document", code="ONBDOC", category_id=category.id, status="active"
    )
    db_session.add(document_type)
    await db_session.flush()
    db_session.add_all(
        [
            Document(
                name=name,
                category_id=category.id,
                document_type_id=document_type.id,
                owner_type="candidate",
                owner_id=candidate.id,
                status="approved",
            )
            for name in REQUIRED_DOCUMENTS
        ]
    )
    await db_session.flush()

    started = await client.post(
        f"{BASE}/profiles",
        json={"offer_id": str(offer.id), "user_id": str(test_user.id)},
        headers=auth_headers,
    )
    assert started.status_code == 201, started.text
    profile_id = started.json()["data"]["profile"]["id"]
    profile = {
        "joining_date": str(offer.joining_date),
        "joining_confirmed": True,
        "first_name": "Asha",
        "last_name": "Rao",
        "date_of_birth": "1995-05-05",
        "gender": "female",
        "blood_group": "O+",
        "marital_status": "single",
        "nationality": "Indian",
        "personal_email": candidate.email,
        "mobile_number": candidate.mobile_number,
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
    updated = await client.put(f"{BASE}/profiles/{profile_id}", json=profile, headers=auth_headers)
    assert updated.status_code == 200, updated.text
    for code in ("employee_handbook", "nda", "company_policies", "code_of_conduct"):
        response = await client.post(
            f"{BASE}/profiles/{profile_id}/policies",
            json={"policy_code": code, "policy_name": code.replace("_", " ").title(), "accepted": True},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
    approved = await client.post(f"{BASE}/profiles/{profile_id}/approve", headers=auth_headers)
    assert approved.status_code == 200, approved.text
    converted = await client.post(
        f"{BASE}/profiles/{profile_id}/convert",
        json={"user_id": str(test_user.id), "official_email": test_user.email},
        headers=auth_headers,
    )
    assert converted.status_code == 201, converted.text
    assert converted.json()["data"]["employee_code"].startswith("JSAN")
    created_case = await client.post(
        f"{BASE}/profiles/{profile_id}/case",
        json={
            "tasks": [
                {
                    "category": "hr",
                    "title": "Welcome session",
                    "owner_id": str(test_user.id),
                    "due_date": str(offer.joining_date),
                }
            ]
        },
        headers=auth_headers,
    )
    assert created_case.status_code == 201, created_case.text
    case = created_case.json()["data"]
    task_id = case["tasks"][0]["id"]
    completed_task = await client.patch(
        f"{BASE}/tasks/{task_id}", json={"status": "completed", "comments": "Done"}, headers=auth_headers
    )
    assert completed_task.status_code == 200, completed_task.text
    completed_case = await client.post(f"{BASE}/cases/{case['id']}/complete", headers=auth_headers)
    assert completed_case.status_code == 200, completed_case.text
    assert completed_case.json()["data"]["progress_percent"] == 100
    welcome = await client.get(f"{BASE}/cases/{case['id']}/welcome", headers=auth_headers)
    assert welcome.status_code == 200, welcome.text
    assert welcome.json()["data"]["employee_code"].startswith("JSAN")


async def test_onboarding_dashboard_requires_authentication(client: AsyncClient):
    response = await client.get(f"{BASE}/dashboard")
    assert response.status_code == 401
