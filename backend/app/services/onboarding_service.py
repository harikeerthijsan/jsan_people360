from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from openpyxl import Workbook
from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.document import Document
from app.models.employee import Employee
from app.models.offer import Offer
from app.models.onboarding import (
    OnboardingCase,
    OnboardingHistory,
    OnboardingTask,
    PolicyAcknowledgement,
    PreboardingProfile,
)
from app.models.recruitment import Candidate, CandidateStageHistory, RecruitmentStage
from app.models.requisition import Notification
from app.repositories.onboarding_repository import (
    CaseRepository,
    OnboardingHistoryRepository,
    PolicyRepository,
    ProfileRepository,
    TaskRepository,
)
from app.schemas.employee import EmployeeCreate
from app.schemas.onboarding import (
    CaseCreate,
    ConversionInput,
    DocumentReview,
    PolicyInput,
    ProfileStart,
    ProfileUpdate,
    TaskUpdate,
)
from app.services.audit_service import AuditService
from app.services.auth_service import RequestOrigin
from app.services.employee_service import EmployeeService
from app.services.mail_service import MailService
from app.utils.datetime import utc_now

REQUIRED_DOCUMENTS = frozenset(
    {
        "photograph",
        "aadhaar",
        "pan",
        "resume",
        "educational certificates",
        "experience letters",
        "bank passbook/cancelled cheque",
    }
)
REQUIRED_POLICIES = frozenset({"employee_handbook", "nda", "company_policies", "code_of_conduct"})


class OnboardingService:
    def __init__(
        self,
        profiles: ProfileRepository,
        cases: CaseRepository,
        tasks: TaskRepository,
        policies: PolicyRepository,
        history: OnboardingHistoryRepository,
        employee_service: EmployeeService,
        audit: AuditService,
        mail: MailService | None = None,
    ) -> None:
        self.profiles, self.cases, self.tasks = profiles, cases, tasks
        self.policies, self.history = policies, history
        self.employee_service, self.audit = employee_service, audit
        # Optional in the established style; the wired product always passes
        # it. Without SMTP configured the invitation lands in the log.
        self.mail = mail
        self.session = profiles.session

    async def start(self, payload: ProfileStart, actor: uuid.UUID) -> PreboardingProfile:
        offer = await self.session.get(Offer, payload.offer_id)
        if not offer or offer.status != "accepted":
            raise ConflictError("Only an accepted offer can enter preboarding.")
        existing = await self.profiles.get_by(offer_id=offer.id)
        if existing:
            return existing
        candidate = await self.session.get(Candidate, offer.candidate_id)
        if candidate is None:
            raise NotFoundError("Candidate")
        profile = PreboardingProfile(
            candidate_id=candidate.id,
            offer_id=offer.id,
            user_id=payload.user_id,
            joining_date=offer.joining_date,
            first_name=candidate.first_name,
            last_name=candidate.last_name,
            personal_email=candidate.email,
            mobile_number=candidate.mobile_number,
        )
        await self.profiles.add(profile, actor_id=actor)
        await self._history(profile.id, "preboarding_started", actor)
        await self._notify(payload.user_id, "Preboarding started", profile, actor)
        await self._audit("onboarding.preboarding_started", profile.id, actor)
        # The invitation goes by email because it cannot go any other way: the
        # joiner has no account, so the inbox every other message uses does not
        # exist for them yet.
        if self.mail is not None and profile.personal_email:
            await self.mail.send_preboarding_invitation(
                to_email=profile.personal_email,
                full_name=f"{profile.first_name} {profile.last_name}",
                portal_url=f"{settings.FRONTEND_BASE_URL.rstrip('/')}/onboarding/portal/{profile.id}",
                joining_date=profile.joining_date.isoformat() if profile.joining_date else None,
            )
        return profile

    async def portal(self, profile_id: uuid.UUID) -> dict[str, Any]:
        profile = await self.profiles.get(profile_id)
        if not profile:
            raise NotFoundError("Preboarding profile")
        documents = await self._documents(profile.candidate_id)
        policies = await self.policies.list(PolicyAcknowledgement.profile_id == profile.id, limit=20)
        case = await self.cases.get_by(profile_id=profile.id)
        return self._profile_data(profile, documents, policies, case)

    async def update_profile(
        self, profile_id: uuid.UUID, payload: ProfileUpdate, actor: uuid.UUID
    ) -> dict[str, Any]:
        profile = await self._profile(profile_id)
        if profile.employee_id:
            raise ConflictError("Converted profiles cannot be edited.")
        values = payload.model_dump(mode="json")
        values.update(joining_date=payload.joining_date, date_of_birth=payload.date_of_birth)
        await self.profiles.update(profile, values, actor_id=actor)
        await self._history(profile.id, "candidate_information_updated", actor)
        await self._audit("onboarding.candidate_updated", profile.id, actor)
        return await self.portal(profile.id)

    async def acknowledge(
        self, profile_id: uuid.UUID, payload: PolicyInput, actor: uuid.UUID, origin: RequestOrigin
    ) -> PolicyAcknowledgement:
        profile = await self._profile(profile_id)
        if await self.policies.get_by(profile_id=profile.id, policy_code=payload.policy_code):
            raise ConflictError("Policy has already been acknowledged.")
        ack = PolicyAcknowledgement(
            profile_id=profile.id,
            policy_code=payload.policy_code,
            policy_name=payload.policy_name,
            acknowledged_at=utc_now(),
            ip_address=origin.ip_address,
            user_agent=origin.user_agent,
        )
        await self.policies.add(ack, actor_id=actor)
        await self._history(profile.id, f"policy_acknowledged:{payload.policy_code}", actor)
        await self._audit("onboarding.policy_acknowledged", profile.id, actor)
        return ack

    async def review_document(
        self,
        profile_id: uuid.UUID,
        document_id: uuid.UUID,
        payload: DocumentReview,
        actor: uuid.UUID,
    ) -> Document:
        profile = await self._profile(profile_id)
        document = await self.session.get(Document, document_id)
        if not document or document.owner_type != "candidate" or document.owner_id != profile.candidate_id:
            raise NotFoundError("Candidate document")
        document.status, document.review_notes = payload.status, payload.comments
        document.reviewed_at, document.reviewed_by, document.updated_by = utc_now(), actor, actor
        await self.session.flush()
        await self._history(profile.id, f"document_{payload.status}", actor, document.name)
        await self._notify(profile.user_id, f"Document {payload.status}", profile, actor)
        await self._audit("onboarding.document_reviewed", profile.id, actor)
        return document

    async def approve_information(self, profile_id: uuid.UUID, actor: uuid.UUID) -> PreboardingProfile:
        profile = await self._profile(profile_id)
        self._validate_information(profile)
        await self._validate_documents(profile)
        await self._validate_policies(profile)
        await self.profiles.update(
            profile, {"information_approved": True, "status": "ready_for_conversion"}, actor_id=actor
        )
        await self._history(profile.id, "preboarding_approved", actor)
        return profile

    async def convert(self, profile_id: uuid.UUID, payload: ConversionInput, actor: uuid.UUID) -> Employee:
        profile = await self._profile(profile_id)
        if not profile.information_approved:
            raise ConflictError("Approve all preboarding information before conversion.")
        if profile.employee_id:
            raise ConflictError("Candidate has already been converted.")
        offer = await self.session.get(Offer, profile.offer_id)
        candidate = await self.session.get(Candidate, profile.candidate_id)
        if offer is None or candidate is None:
            raise NotFoundError("Offer")
        opening = candidate.job_opening
        data = payload.model_dump()
        data.update(
            first_name=profile.first_name,
            last_name=profile.last_name,
            user_id=payload.user_id,
            joining_date=profile.joining_date,
            personal_email=profile.personal_email,
            mobile_number=profile.mobile_number,
            gender=profile.gender,
            date_of_birth=profile.date_of_birth,
            blood_group=profile.blood_group,
            marital_status=profile.marital_status,
            nationality=profile.nationality,
            emergency_contact_name=profile.emergency_contact["name"],
            emergency_contact_number=profile.emergency_contact["phone_number"],
            emergency_contact_relationship=profile.emergency_contact["relationship"],
            addresses=profile.addresses,
            bank_detail=profile.bank_details,
            identification={"aadhaar_number": profile.aadhaar_number, "pan_number": profile.pan_number},
            ctc=offer.ctc,
            work_mode=offer.work_mode,
        )
        for field, value in (
            ("employment_type_id", opening.employment_type_id),
            ("work_location_id", opening.location_id),
            ("reporting_manager_id", offer.reporting_manager_id),
        ):
            if data.get(field) is None:
                data[field] = value
        employee = await self.employee_service.create(EmployeeCreate(**data), actor_id=actor)
        joined = await self.session.scalar(
            select(RecruitmentStage).where(func.lower(RecruitmentStage.name) == "joined")
        )
        if not joined:
            max_sequence = int(await self.session.scalar(select(func.max(RecruitmentStage.sequence))) or 0)
            joined = RecruitmentStage(
                name="Joined", sequence=max_sequence + 1, category="hired", created_by=actor, updated_by=actor
            )
            self.session.add(joined)
            await self.session.flush()
        previous_stage_id = candidate.stage_id
        candidate.stage_id = joined.id
        self.session.add(
            CandidateStageHistory(
                candidate_id=candidate.id,
                from_stage_id=previous_stage_id,
                to_stage_id=joined.id,
                comments="Employee created through onboarding",
                created_by=actor,
                updated_by=actor,
            )
        )
        profile.employee_id, profile.user_id, profile.status = employee.id, payload.user_id, "converted"
        await self.session.flush()
        await self._history(profile.id, "employee_created", actor, employee.employee_code)
        await self._notify(payload.user_id, "Employee record created", profile, actor)
        await self._audit("onboarding.employee_converted", profile.id, actor)
        return employee

    async def create_case(
        self, profile_id: uuid.UUID, payload: CaseCreate, actor: uuid.UUID
    ) -> OnboardingCase:
        profile = await self._profile(profile_id)
        if not profile.employee_id:
            raise ConflictError("Convert the candidate before onboarding starts.")
        if await self.cases.get_by(profile_id=profile.id):
            raise ConflictError("Onboarding case already exists.")
        case = await self.cases.add(
            OnboardingCase(
                profile_id=profile.id,
                employee_id=profile.employee_id,
                status="in_progress",
                started_at=utc_now(),
            ),
            actor_id=actor,
        )
        for item in payload.tasks:
            await self.tasks.add(OnboardingTask(case_id=case.id, **item.model_dump()), actor_id=actor)
            await self._notify(item.owner_id, "Onboarding task assigned", profile, actor)
        profile.status = "onboarding"
        await self._history(profile.id, "onboarding_started", actor, case.id)
        return await self._case(case.id)

    async def update_task(self, task_id: uuid.UUID, payload: TaskUpdate, actor: uuid.UUID) -> OnboardingTask:
        task = await self.tasks.get(task_id)
        if not task:
            raise NotFoundError("Onboarding task")
        values = payload.model_dump()
        values["completed_at"] = utc_now() if payload.status == "completed" else None
        await self.tasks.update(task, values, actor_id=actor)
        await self._recalculate(task.case_id, actor)
        return task

    async def complete(self, case_id: uuid.UUID, actor: uuid.UUID) -> OnboardingCase:
        case = await self._case(case_id)
        if not case.tasks or any(task.status != "completed" for task in case.tasks):
            raise ConflictError("All onboarding tasks must be completed first.")
        await self.cases.update(
            case, {"status": "completed", "progress_percent": 100, "completed_at": utc_now()}, actor_id=actor
        )
        profile = await self._profile(case.profile_id)
        await self.profiles.update(profile, {"status": "completed"}, actor_id=actor)
        await self._history(profile.id, "onboarding_completed", actor, case.id)
        await self._notify(profile.user_id, "Onboarding completed", profile, actor)
        return case

    async def welcome(self, case_id: uuid.UUID) -> dict[str, Any]:
        case = await self._case(case_id)
        if case.status != "completed":
            raise ConflictError("The welcome screen is available after onboarding is completed.")
        employee = await self.session.get(Employee, case.employee_id)
        if employee is None:
            raise NotFoundError("Employee")
        return {
            "employee_id": employee.id,
            "employee_code": employee.employee_code,
            "name": f"{employee.first_name} {employee.last_name}",
            "joining_date": employee.joining_date,
            "reporting_manager": employee.reporting_manager.full_name if employee.reporting_manager else None,
            "team": employee.team.name if employee.team else None,
            "office_location": employee.work_location.name if employee.work_location else None,
            "tasks": [
                {column.key: getattr(task, column.key) for column in task.__table__.columns}
                for task in case.tasks
            ],
        }

    async def case(self, case_id: uuid.UUID) -> OnboardingCase:
        return await self._case(case_id)

    async def dashboard(self) -> dict[str, Any]:
        today, week_end = date.today(), date.today() + timedelta(days=7)

        async def count(model: Any, *criteria: Any) -> int:
            total = await self.session.scalar(
                select(func.count()).select_from(model).where(model.deleted_at.is_(None), *criteria)
            )
            return int(total or 0)

        return {
            "awaiting_preboarding": int(
                await count(PreboardingProfile, PreboardingProfile.status == "information_pending") or 0
            ),
            "pending_documents": await self._pending_document_profiles(),
            "pending_hr_tasks": int(
                await count(
                    OnboardingTask, OnboardingTask.category == "hr", OnboardingTask.status != "completed"
                )
                or 0
            ),
            "pending_it_tasks": int(
                await count(
                    OnboardingTask, OnboardingTask.category == "it", OnboardingTask.status != "completed"
                )
                or 0
            ),
            "pending_manager_tasks": int(
                await count(
                    OnboardingTask, OnboardingTask.category == "manager", OnboardingTask.status != "completed"
                )
                or 0
            ),
            "joining_this_week": int(
                await count(
                    PreboardingProfile,
                    PreboardingProfile.joining_date.between(today, week_end),
                    PreboardingProfile.employee_id.is_(None),
                )
                or 0
            ),
            "delayed_joining": int(
                await count(
                    PreboardingProfile,
                    PreboardingProfile.joining_date < today,
                    PreboardingProfile.employee_id.is_(None),
                )
                or 0
            ),
            "completed_onboarding": int(
                await count(OnboardingCase, OnboardingCase.status == "completed") or 0
            ),
        }

    async def export(self, fmt: str) -> tuple[bytes, str]:
        rows = await self.profiles.list(limit=10000, descending=False)
        data = [["Candidate", "Joining date", "Preboarding status", "Employee ID"]] + [
            [f"{x.first_name} {x.last_name}", str(x.joining_date), x.status, str(x.employee_id or "")]
            for x in rows
        ]
        if fmt == "csv":
            text = io.StringIO()
            csv.writer(text).writerows(data)
            return text.getvalue().encode(), "text/csv"
        book = Workbook()
        sheet = book.active
        for row in data:
            sheet.append(row)
        buffer = io.BytesIO()
        book.save(buffer)
        return buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    async def _case(self, case_id: uuid.UUID) -> OnboardingCase:
        case = await self.cases.detailed(case_id)
        if not case:
            raise NotFoundError("Onboarding case")
        return case

    async def _profile(self, profile_id: uuid.UUID) -> PreboardingProfile:
        profile = await self.profiles.get(profile_id)
        if not profile:
            raise NotFoundError("Preboarding profile")
        return profile

    async def _documents(self, candidate_id: uuid.UUID) -> Sequence[Document]:
        result = await self.session.execute(
            select(Document).where(
                Document.owner_type == "candidate",
                Document.owner_id == candidate_id,
                Document.deleted_at.is_(None),
            )
        )
        return result.scalars().all()

    async def _validate_documents(self, profile: PreboardingProfile) -> None:
        documents = await self._documents(profile.candidate_id)
        approved = {d.name.strip().lower() for d in documents if d.status == "approved"}
        missing = REQUIRED_DOCUMENTS - approved
        if missing:
            raise ConflictError(f"Mandatory documents pending: {', '.join(sorted(missing))}")

    async def _validate_policies(self, profile: PreboardingProfile) -> None:
        items = await self.policies.list(PolicyAcknowledgement.profile_id == profile.id, limit=20)
        missing = REQUIRED_POLICIES - {x.policy_code for x in items}
        if missing:
            raise ConflictError(f"Policy acknowledgements pending: {', '.join(sorted(missing))}")

    def _validate_information(self, profile: PreboardingProfile) -> None:
        required = (
            profile.joining_confirmed,
            profile.date_of_birth,
            profile.gender,
            profile.blood_group,
            profile.marital_status,
            profile.nationality,
            profile.emergency_contact,
            profile.addresses,
            profile.bank_details,
            profile.aadhaar_number,
            profile.pan_number,
        )
        if not all(required):
            raise ConflictError("Complete all mandatory candidate information.")

    async def _recalculate(self, case_id: uuid.UUID, actor: uuid.UUID) -> None:
        case = await self._case(case_id)
        total = len(case.tasks)
        done = sum(x.status == "completed" for x in case.tasks)
        progress = round(done / total * 100) if total else 0
        await self.cases.update(case, {"progress_percent": progress}, actor_id=actor)
        profile = await self._profile(case.profile_id)
        await self._history(
            profile.id, "task_completed" if progress else "task_updated", actor, f"{progress}%"
        )

    async def _pending_document_profiles(self) -> int:
        profiles = await self.profiles.list(PreboardingProfile.employee_id.is_(None), limit=10000)
        pending = 0
        for profile in profiles:
            docs = await self._documents(profile.candidate_id)
            approved = {d.name.lower() for d in docs if d.status == "approved"}
            pending += bool(REQUIRED_DOCUMENTS - approved)
        return pending

    def _profile_data(
        self,
        profile: PreboardingProfile,
        documents: Sequence[Document],
        policies: Sequence[PolicyAcknowledgement],
        case: OnboardingCase | None,
    ) -> dict[str, Any]:
        return {
            "profile": {column.key: getattr(profile, column.key) for column in profile.__table__.columns},
            "documents": [
                {
                    "id": document.id,
                    "name": document.name,
                    "status": document.status,
                    "review_notes": document.review_notes,
                }
                for document in documents
            ],
            "acknowledgements": [
                {
                    "id": policy.id,
                    "policy_code": policy.policy_code,
                    "acknowledged_at": policy.acknowledged_at,
                }
                for policy in policies
            ],
            "required_documents": sorted(REQUIRED_DOCUMENTS),
            "required_policies": sorted(REQUIRED_POLICIES),
            "progress_percent": (
                case.progress_percent if case else self._preboarding_progress(profile, documents, policies)
            ),
            "case_id": case.id if case else None,
        }

    def _preboarding_progress(
        self,
        profile: PreboardingProfile,
        documents: Sequence[Document],
        policies: Sequence[PolicyAcknowledgement],
    ) -> int:
        sections = [
            profile.joining_confirmed,
            bool(
                profile.date_of_birth
                and profile.emergency_contact
                and profile.addresses
                and profile.bank_details
            ),
            len({d.name.lower() for d in documents if d.status == "approved"} & REQUIRED_DOCUMENTS)
            == len(REQUIRED_DOCUMENTS),
            len({p.policy_code for p in policies}) == len(REQUIRED_POLICIES),
        ]
        return sum(bool(x) for x in sections) * 25

    async def _history(
        self, profile_id: uuid.UUID, action: str, actor: uuid.UUID, details: object = None
    ) -> None:
        await self.history.add(
            OnboardingHistory(
                profile_id=profile_id, action=action, details=str(details) if details else None
            ),
            actor_id=actor,
        )

    async def _notify(
        self,
        user_id: uuid.UUID | None,
        title: str,
        profile: PreboardingProfile,
        actor: uuid.UUID,
    ) -> None:
        if user_id:
            self.session.add(
                Notification(
                    user_id=user_id,
                    title=title,
                    message=f"{profile.first_name} {profile.last_name}",
                    link=f"/onboarding/portal/{profile.id}",
                    notification_type="onboarding",
                    created_by=actor,
                    updated_by=actor,
                )
            )
            await self.session.flush()

    async def _audit(self, action: str, entity_id: uuid.UUID, actor: uuid.UUID) -> None:
        await self.audit.record_success(action, actor_id=actor, entity_type="onboarding", entity_id=entity_id)
