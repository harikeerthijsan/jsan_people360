"""Demonstration data for every People360 module.

Usage (from ``backend/``, after ``alembic upgrade head`` and ``python -m app.cli.seed``)::

    python -m app.cli.seed_demo

This walks the *real* service layer through each business flow -- a requisition
is submitted and approved by its three approvers, a candidate is interviewed,
offered, accepted and converted, a payroll run is calculated, reviewed, approved,
finalized and paid out -- so what lands in the database is exactly what the
application itself would have written, audit trail and notifications included.

It is additive and re-runnable: every section looks for its own anchor record
(a demo user's email, a requisition title, a period name) and skips itself when
that already exists. Nothing is deleted, and nothing outside the ``demo``
namespace is touched, except that employees with no salary are marked not
eligible for payroll so the demo run can complete.

Demo sign-ins are ``<first>.<last>@demo.jsan.example`` with password
``Demo@12345``. The full list is printed at the end.
"""

from __future__ import annotations

# The seed never wants to email anybody, and the login limiter has no business
# in a script. Both are read by Settings at import time, so they are set first.
import os

os.environ["SMTP_HOST"] = ""
os.environ["RATE_LIMIT_ENABLED"] = "false"

import asyncio
import sys
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.db.session import session_scope
from app.models.asset import AssetCategory
from app.models.business_unit import BusinessUnit
from app.models.designation import Designation
from app.models.document import Document
from app.models.document_category import DocumentType
from app.models.employee import Employee
from app.models.employment_type import EmploymentType
from app.models.enums import (
    AttendanceStatus,
    DocumentOwnerType,
    DocumentStatus,
    EmploymentStatus,
    ExitDocumentType,
    FeedbackCategory,
    FeedbackVisibility,
    GoalPriority,
    GoalStatus,
    HandoverStatus,
    MaintenanceType,
    OffboardingTaskStatus,
    PayrollEligibility,
    PayrollEligibilityReason,
    PayrollItemType,
    PerformanceCycleStatus,
    PerformanceRecommendation,
    RecognitionType,
    RecordStatus,
    SalaryCalculationType,
    SalaryComponentType,
    SalaryStructureStatus,
    SettlementAdjustmentType,
    TicketPriority,
    TicketStatus,
)
from app.models.grade import Grade
from app.models.helpdesk import HelpdeskCategory
from app.models.location import Location
from app.models.payroll import PayrollConfiguration, PayrollPeriod, SalaryComponent
from app.models.performance import PerformanceCycle
from app.models.project import Client
from app.models.rbac import Role, UserRole
from app.models.recruitment import CandidateSource, RecruitmentStage
from app.models.requisition import JobRequisition
from app.models.team import Team
from app.models.user import User
from app.models.workforce import Holiday, HolidayCalendar, LeaveType, Shift
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.document_repository import (
    DocumentRepository,
    DocumentVersionRepository,
)
from app.repositories.employee_repository import EmployeeRepository, EmploymentHistoryRepository
from app.repositories.organization_repository import (
    BusinessUnitRepository,
    DesignationRepository,
    OrganizationRepository,
    TeamRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas.announcement import AnnouncementCreate, AnnouncementPublish
from app.schemas.asset import AssetAssign, AssetCreate, AssetReturnInput, MaintenanceCreate
from app.schemas.designation import DesignationCreate
from app.schemas.document import DocumentReviewRequest, DocumentUploadMetadata
from app.schemas.employee import ChangeStatusRequest, EmployeeCreate
from app.schemas.helpdesk import TicketComment, TicketRaise, TicketStatusChange
from app.schemas.interview import DecisionRequest, FeedbackCreate, InterviewCreate
from app.schemas.offboarding import (
    AccessClearanceUpdate,
    AssetClearanceUpdate,
    CaseCompletion,
    ExitDocumentGenerate,
    ExitInterviewSubmit,
    HandoverInput,
    HrProcess,
    ManagerDecision,
    OffboardingTaskUpdate,
    ResignationSubmit,
)
from app.schemas.offer import OfferCreate
from app.schemas.onboarding import (
    CaseCreate,
    ConversionInput,
    PolicyInput,
    ProfileStart,
    ProfileUpdate,
    TaskCreate,
    TaskUpdate,
)
from app.schemas.payroll import (
    ChecklistItemUpdate,
    CompensationAssign,
    EmployeeSettingsUpsert,
    PayrollAdjustmentCreate,
    PayrollApprovalDecision,
    PayrollFinalizeRequest,
    PayrollPeriodCreate,
    PayrollRunCreate,
    ReviewCommentCreate,
    SalaryComponentCreate,
    SalaryStructureCreate,
)
from app.schemas.payroll_settlement import (
    SettlementAdjustmentCreate,
    SettlementAdjustmentDecision,
    SettlementApproval,
    SettlementFinalize,
)
from app.schemas.performance import (
    FeedbackCreate as PerformanceFeedbackCreate,
    FinalReviewSubmit,
    GoalCreate,
    GoalProgressCreate,
    GoalRatingInput,
    ManagerReviewSubmit,
    PerformanceCycleCreate,
    RecognitionCreate,
    SelfReviewSubmit,
)
from app.schemas.project import AllocationCreate, ClientCreate, ProjectCreate
from app.schemas.recruitment import (
    CandidateCreate,
    NoteCreate,
    OpeningCreate,
    StageMove,
    TalentPoolCreate,
)
from app.schemas.requisition import RequisitionCreate
from app.schemas.team import TeamCreate
from app.schemas.workforce import (
    AttendanceCorrection,
    HolidayCalendarCreate,
    HolidayInput,
    LeaveApply,
    LeaveBalanceAdjustment,
    RegularizationCreate,
    ShiftAssign,
    TimesheetEntryInput,
    TimesheetSave,
)
from app.services.auth_service import RequestOrigin
from app.services.document_service import UploadedFile
from app.services.scope_service import EmployeeScope
from app.storage import get_storage
from app.utils.strings import normalise_email

logger = get_logger("cli.seed_demo")

DEMO_DOMAIN = "demo.jsan.example"
DEMO_PASSWORD = "Demo@12345"  # noqa: S105 - a published demo credential
TODAY = date.today()
ORG_SCOPE = EmployeeScope(unrestricted=True)

# A byte-exact minimal PDF: the vault sniffs magic bytes, so a text file
# renamed .pdf would be refused.
MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R>>endobj\n"
    b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 72 770 Td (People360 demo) Tj ET\nendstream\nendobj\n"
    b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n"
    b"0000000101 00000 n \n0000000188 00000 n \ntrailer<</Size 5/Root 1 0 R>>\nstartxref\n280\n%%EOF\n"
)


def _pdf(label: str) -> bytes:
    """A distinct PDF per label, so the vault's duplicate-content check never fires."""
    return MINIMAL_PDF + b"%% " + label.encode("ascii", "ignore") + b"\n"


# ----------------------------------------------------------------------
# The cast
# ----------------------------------------------------------------------
@dataclass
class Person:
    key: str
    first: str
    last: str
    role: str
    designation: str  # designation code
    team: str  # team name
    bu: str  # business unit code
    grade: str
    joining: date
    manager: str | None = None  # key of another person
    gender: str = "female"
    dob: date = date(1994, 6, 15)
    monthly_basic: int = 40000
    status: EmploymentStatus = EmploymentStatus.ACTIVE
    work_mode: str = "hybrid"
    location: str = "HYD"
    user_id: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None

    @property
    def email(self) -> str:
        return f"{self.first.lower()}.{self.last.lower()}@{DEMO_DOMAIN}"

    @property
    def emp(self) -> uuid.UUID:
        assert self.employee_id is not None, self.key
        return self.employee_id

    @property
    def usr(self) -> uuid.UUID:
        assert self.user_id is not None, self.key
        return self.user_id


PEOPLE: list[Person] = [
    Person(
        "ananya",
        "Ananya",
        "Rao",
        "hr_admin",
        "HRM",
        "People Operations",
        "CORP",
        "M2",
        date(2021, 4, 5),
        gender="female",
        dob=date(1988, 2, 11),
        monthly_basic=85000,
    ),
    Person(
        "rahul",
        "Rahul",
        "Verma",
        "hr_executive",
        "HRE",
        "People Operations",
        "CORP",
        "G2",
        date(2023, 1, 9),
        manager="ananya",
        gender="male",
        dob=date(1995, 9, 30),
        monthly_basic=35000,
    ),
    Person(
        "meera",
        "Meera",
        "Iyer",
        "recruiter",
        "HRE",
        "Talent Acquisition",
        "CORP",
        "G2",
        date(2022, 8, 16),
        manager="ananya",
        gender="female",
        dob=date(1993, 12, 2),
        monthly_basic=38000,
    ),
    Person(
        "fatima",
        "Fatima",
        "Khan",
        "hr_admin",
        "FINOPS",
        "Finance",
        "CORP",
        "G3",
        date(2020, 11, 2),
        manager="ananya",
        gender="female",
        dob=date(1990, 5, 19),
        monthly_basic=60000,
    ),
    Person(
        "vikram",
        "Vikram",
        "Singh",
        "manager",
        "EM",
        "Product Engineering",
        "TECH",
        "M2",
        date(2019, 6, 10),
        gender="male",
        dob=date(1986, 7, 23),
        monthly_basic=110000,
        location="BLR",
    ),
    Person(
        "suresh",
        "Suresh",
        "Kumar",
        "project_manager",
        "PM",
        "Product Engineering",
        "TECH",
        "M1",
        date(2020, 2, 3),
        manager="vikram",
        gender="male",
        dob=date(1989, 3, 14),
        monthly_basic=90000,
    ),
    Person(
        "sneha",
        "Sneha",
        "Patel",
        "team_lead",
        "TL",
        "Product Engineering",
        "TECH",
        "G3",
        date(2021, 9, 20),
        manager="vikram",
        gender="female",
        dob=date(1992, 10, 8),
        monthly_basic=70000,
    ),
    Person(
        "arjun",
        "Arjun",
        "Nair",
        "employee",
        "SE",
        "Product Engineering",
        "TECH",
        "G2",
        date(2026, 1, 15),
        manager="sneha",
        gender="male",
        dob=date(1998, 4, 27),
        monthly_basic=42000,
    ),
    Person(
        "divya",
        "Divya",
        "Menon",
        "employee",
        "SSE",
        "Product Engineering",
        "TECH",
        "G2",
        date(2023, 7, 3),
        manager="sneha",
        gender="female",
        dob=date(1996, 1, 17),
        monthly_basic=55000,
    ),
    Person(
        "karthik",
        "Karthik",
        "Reddy",
        "employee",
        "SE",
        "Product Engineering",
        "TECH",
        "G1",
        date(2024, 3, 18),
        manager="sneha",
        gender="male",
        dob=date(1999, 8, 5),
        monthly_basic=40000,
        work_mode="office",
    ),
    Person(
        "pooja",
        "Pooja",
        "Gupta",
        "employee",
        "SE",
        "Platform Engineering",
        "TECH",
        "G1",
        date(2026, 7, 1),
        manager="vikram",
        gender="female",
        dob=date(2000, 11, 21),
        monthly_basic=38000,
        work_mode="remote",
        location="BLR",
    ),
    Person(
        "rohan",
        "Rohan",
        "Das",
        "employee",
        "SSE",
        "Platform Engineering",
        "TECH",
        "G3",
        date(2022, 2, 14),
        manager="vikram",
        gender="male",
        dob=date(1994, 6, 9),
        monthly_basic=60000,
    ),
]
ENGINEERS = ["arjun", "divya", "karthik", "pooja"]
LEAVER = "rohan"


# ----------------------------------------------------------------------
# Context: session, services, bookkeeping
# ----------------------------------------------------------------------
@dataclass
class Ctx:
    session: AsyncSession
    admin: User
    people: dict[str, Person] = field(default_factory=dict)
    done: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    masters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        s = self.session
        self.audit = deps.get_audit_service(AuditLogRepository(s))
        self.storage = get_storage()
        employees = EmployeeRepository(s)
        self.employees = employees
        self.employee_svc = deps.get_employee_service(
            employees, EmploymentHistoryRepository(s), self.audit, AuditLogRepository(s), UserRepository(s)
        )
        self.team_svc = deps.get_team_service(
            TeamRepository(s), BusinessUnitRepository(s), UserRepository(s), self.audit
        )
        self.designation_svc = deps.get_designation_service(
            DesignationRepository(s), BusinessUnitRepository(s), self.audit
        )
        self.document_svc = deps.get_document_service(
            s,
            DocumentRepository(s),
            DocumentVersionRepository(s),
            self.audit,
            self.storage,
            employees,
            UserRepository(s),
            OrganizationRepository(s),
        )
        self.requisition_svc = deps.get_requisition_service(s, self.audit)
        self.recruitment_svc = deps.get_recruitment_service(s, self.audit)
        self.interview_svc = deps.get_interview_service(s, self.audit)
        self.offer_svc = deps.get_offer_service(s, self.audit, self.storage)
        self.onboarding_svc = deps.get_onboarding_service(s, self.employee_svc, self.audit)
        self.asset_svc = deps.get_asset_service(s, employees, self.audit)
        self.offboarding_svc = deps.get_offboarding_service(
            s, employees, self.audit, self.storage, self.asset_svc
        )
        self.project_svc = deps.get_project_service(s, self.audit)
        self.performance_svc = deps.get_performance_service(s, employees, self.audit)
        self.workforce_svc = deps.get_workforce_service(s, employees, self.audit)
        self.helpdesk_svc = deps.get_helpdesk_service(s, employees, self.audit)
        self.announcement_svc = deps.get_announcement_service(s, employees, self.audit)
        self.payroll_svc = deps.get_payroll_service(s, employees, self.audit)
        self.payroll_config_svc = deps.get_payroll_config_service(s, employees, self.audit)
        self.payroll_input_svc = deps.get_payroll_input_service(s, self.audit)
        self.payroll_run_svc = deps.get_payroll_run_service(s, self.audit)
        self.payroll_review_svc = deps.get_payroll_review_service(s, self.audit)
        self.payroll_approval_svc = deps.get_payroll_approval_service(s, self.audit)
        self.payslip_svc = deps.get_payslip_service(s, self.audit, self.storage)
        self.settlement_svc = deps.get_payroll_settlement_service(s, self.audit)

    @property
    def actor(self) -> uuid.UUID:
        return self.admin.id

    def uid(self, key: str) -> uuid.UUID:
        value = self.people[key].user_id
        assert value is not None, key
        return value

    def eid(self, key: str) -> uuid.UUID:
        value = self.people[key].employee_id
        assert value is not None, key
        return value

    async def employee(self, key: str) -> Employee:
        row = await self.session.get(Employee, self.eid(key))
        assert row is not None
        return row

    async def step(self, name: str, fn: Callable[[], Awaitable[Any]]) -> Any:
        """Run one unit of work inside a savepoint.

        A refused transition (a rule the demo data trips over) rolls back just
        that unit and is reported at the end; everything else carries on.
        """
        try:
            async with self.session.begin_nested():
                result = await fn()
        except Exception as exc:
            reason = getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}"
            if not isinstance(exc, (AppException, PydanticValidationError, ValueError, SQLAlchemyError)):
                logger.exception("Unexpected failure in %s", name)
            self.skipped.append((name, reason.splitlines()[0][:160]))
            logger.warning("Skipped %s: %s", name, reason.splitlines()[0][:160])
            return None
        self.done.append(name)
        return result


# ----------------------------------------------------------------------
# Small lookups
# ----------------------------------------------------------------------
async def _one(session: AsyncSession, stmt: Any) -> Any:
    return (await session.execute(stmt)).scalars().first()


async def _by_code(session: AsyncSession, model: Any, code: str) -> Any:
    return await _one(session, select(model).where(func.lower(model.code) == code.lower()))


def working_days(start: date, end: date, holidays: set[date]) -> list[date]:
    days: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5 and cursor not in holidays:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def next_weekday(weekday: int, after: date) -> date:
    delta = (weekday - after.weekday()) % 7 or 7
    return after + timedelta(days=delta)


# ======================================================================
# 1. Masters the demo leans on
# ======================================================================
async def seed_masters(ctx: Ctx) -> None:
    s = ctx.session
    m = ctx.masters
    for code in ("TECH", "CORP"):
        row = await _by_code(s, BusinessUnit, code)
        if row is None:
            raise RuntimeError(
                "Run `python -m app.cli.seed --sample-data` first: business units are missing."
            )
        m[f"bu:{code}"] = row.id

    async def team(name: str, bu: str) -> None:
        row = await _one(
            s,
            select(Team).where(func.lower(Team.name) == name.lower(), Team.business_unit_id == m[f"bu:{bu}"]),
        )
        if row is None:
            row = await ctx.team_svc.create(
                TeamCreate(name=name, business_unit_id=m[f"bu:{bu}"], description=f"{name} (demo)"),
                actor_id=ctx.actor,
            )
        m[f"team:{name}"] = row.id

    for name, bu in (
        ("People Operations", "CORP"),
        ("Talent Acquisition", "CORP"),
        ("Finance", "CORP"),
        ("Product Engineering", "TECH"),
        ("Platform Engineering", "TECH"),
    ):
        await team(name, bu)

    async def designation(code: str, name: str, bu: str, level: int) -> None:
        row = await _by_code(s, Designation, code)
        if row is None:
            row = await ctx.designation_svc.create(
                DesignationCreate(name=name, code=code, business_unit_id=m[f"bu:{bu}"], level=level),
                actor_id=ctx.actor,
            )
        m[f"desig:{code}"] = row.id

    for code, name, bu, level in (
        ("SE", "Software Engineer", "TECH", 2),
        ("SSE", "Senior Software Engineer", "TECH", 3),
        ("TL", "Team Lead", "TECH", 4),
        ("PM", "Project Manager", "TECH", 4),
        ("EM", "Engineering Manager", "TECH", 5),
        ("HRE", "HR Executive", "CORP", 2),
        ("HRM", "HR Manager", "CORP", 4),
        ("FINOPS", "Finance Operations Executive", "CORP", 3),
    ):
        await designation(code, name, bu, level)

    for code in ("G1", "G2", "G3", "M1", "M2"):
        row = await _by_code(s, Grade, code)
        if row is None:
            level = {"G1": 1, "G2": 2, "G3": 3, "M1": 4, "M2": 5}[code]
            row = Grade(
                name=f"Grade {code}",
                code=code,
                level=level,
                status=RecordStatus.ACTIVE,
                created_by=ctx.actor,
                updated_by=ctx.actor,
            )
            s.add(row)
            await s.flush()
        m[f"grade:{code}"] = row.id

    for code, name, city, state in (
        ("HYD", "Hyderabad", "Hyderabad", "Telangana"),
        ("BLR", "Bengaluru", "Bengaluru", "Karnataka"),
    ):
        row = await _by_code(s, Location, code)
        if row is None:
            row = Location(
                name=f"{name} Office",
                code=code,
                country="India",
                state=state,
                city=city,
                address=f"{name} Tech Park",
                timezone="Asia/Kolkata",
                status=RecordStatus.ACTIVE,
                created_by=ctx.actor,
                updated_by=ctx.actor,
            )
            s.add(row)
            await s.flush()
        m[f"loc:{code}"] = row.id

    full_time = await _by_code(s, EmploymentType, "FULL_TIME")
    if full_time is None:
        full_time = EmploymentType(
            name="Full Time",
            code="FULL_TIME",
            status=RecordStatus.ACTIVE,
            created_by=ctx.actor,
            updated_by=ctx.actor,
        )
        s.add(full_time)
        await s.flush()
    m["etype:FULL_TIME"] = full_time.id

    roles = (await s.execute(select(Role))).scalars().all()
    m["roles"] = {role.key: role.id for role in roles}

    shift = await _by_code(s, Shift, "GEN")
    if shift is None:
        shift = await _one(s, select(Shift).where(Shift.deleted_at.is_(None)).order_by(Shift.created_at))
    m["shift"] = shift.id if shift else None

    for code in ("CL", "SL", "EL"):
        row = await _by_code(s, LeaveType, code)
        m[f"leave:{code}"] = row.id if row else None

    m["doc_type"], m["doc_category"] = await _document_type(s)


async def _document_type(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """A live document type that accepts PDFs and needs no expiry date."""
    types = (
        (await session.execute(select(DocumentType).where(DocumentType.deleted_at.is_(None)))).scalars().all()
    )
    for row in types:
        allowed: list[str] = list(row.allowed_extensions or [])
        if row.requires_expiry:
            continue
        if not allowed or any(ext.lower().strip(". ") == "pdf" for ext in allowed):
            return row.id, row.category_id
    if not types:
        raise RuntimeError("No document types exist. Run `python -m app.cli.seed` first.")
    return types[0].id, types[0].category_id


# ======================================================================
# 2. People: login accounts, roles, employee records
# ======================================================================
async def seed_people(ctx: Ctx) -> None:
    s = ctx.session
    m = ctx.masters
    ctx.people = {p.key: p for p in PEOPLE}

    for p in PEOPLE:
        user = await _one(s, select(User).where(User.email == normalise_email(p.email)))
        if user is None:
            user = User(
                email=normalise_email(p.email),
                username=f"{p.first.lower()}.{p.last.lower()}",
                first_name=p.first,
                last_name=p.last,
                hashed_password=hash_password(DEMO_PASSWORD),
                is_active=True,
                is_superuser=False,
                email_verified_at=datetime.now(UTC),
                password_changed_at=datetime.now(UTC),
                business_unit_id=m[f"bu:{p.bu}"],
                team_id=m[f"team:{p.team}"],
                designation_id=m[f"desig:{p.designation}"],
                grade_id=m[f"grade:{p.grade}"],
                location_id=m[f"loc:{p.location}"],
                employment_type_id=m["etype:FULL_TIME"],
                joining_date=p.joining,
                created_by=ctx.actor,
                updated_by=ctx.actor,
            )
            s.add(user)
            await s.flush()
            role_id = m["roles"].get(p.role) or m["roles"].get("employee")
            if role_id:
                s.add(UserRole(user_id=user.id, role_id=role_id, created_by=ctx.actor, updated_by=ctx.actor))
            if p.role != "employee" and m["roles"].get("employee"):
                s.add(
                    UserRole(
                        user_id=user.id,
                        role_id=m["roles"]["employee"],
                        created_by=ctx.actor,
                        updated_by=ctx.actor,
                    )
                )
            await s.flush()
        p.user_id = user.id

    # Managers before reports, so reporting lines can be set on create.
    order = sorted(PEOPLE, key=lambda p: (p.manager is not None, p.manager == "sneha"))
    for index, p in enumerate(order):
        existing = await _one(s, select(Employee).where(func.lower(Employee.official_email) == p.email))
        if existing is not None:
            p.employee_id = existing.id
            if existing.employment_status in {
                EmploymentStatus.PROBATION.value,
                EmploymentStatus.CONFIRMED.value,
            }:
                # Payroll only reads `active` employees; an earlier pass created them as confirmed.
                async def activate(p: Person = p) -> None:
                    await ctx.employee_svc.change_status(
                        p.emp,
                        ChangeStatusRequest(
                            employment_status=EmploymentStatus.ACTIVE, reason="Confirmed and on payroll"
                        ),
                        actor_id=ctx.actor,
                    )

                await ctx.step(f"activate:{p.key}", activate)
            continue
        n = 10 + index
        payload = EmployeeCreate(
            first_name=p.first,
            last_name=p.last,
            official_email=p.email,
            joining_date=p.joining,
            user_id=p.usr,
            employment_status=p.status,
            gender=p.gender,
            date_of_birth=p.dob,
            blood_group="O+",
            marital_status="single",
            nationality="Indian",
            personal_email=f"{p.first.lower()}.{n}@personal.example",
            mobile_number=f"+91 98{n:02d}0 4{n:02d}21",
            emergency_contact_name=f"{p.first} {p.last} Sr.",
            emergency_contact_number=f"+91 97{n:02d}0 1{n:02d}55",
            emergency_contact_relationship="Parent",
            employment_type_id=m["etype:FULL_TIME"],
            business_unit_id=m[f"bu:{p.bu}"],
            team_id=m[f"team:{p.team}"],
            designation_id=m[f"desig:{p.designation}"],
            grade_id=m[f"grade:{p.grade}"],
            work_location_id=m[f"loc:{p.location}"],
            reporting_manager_id=ctx.people[p.manager].employee_id if p.manager else None,
            work_mode=p.work_mode,
            ctc=Decimal(p.monthly_basic * 12 * 2),
            addresses=[
                {
                    "address_type": "current",
                    "address_line1": f"{n} Jubilee Hills Road",
                    "city": "Hyderabad",
                    "state": "Telangana",
                    "country": "India",
                    "postal_code": "500033",
                },
                {
                    "address_type": "permanent",
                    "address_line1": f"{n} MG Road",
                    "city": "Kochi",
                    "state": "Kerala",
                    "country": "India",
                    "postal_code": "682016",
                },
            ],
            bank_detail={
                "bank_name": "HDFC Bank",
                "account_number": f"5010012345{n:04d}",
                "account_holder_name": f"{p.first} {p.last}",
                "ifsc_code": "HDFC0001234",
                "branch_name": "Jubilee Hills",
            },
            identification={
                "aadhaar_number": f"2345{n:04d}9012",
                "pan_number": f"DEMO{chr(65 + index % 26)}{1000 + n}{chr(65 + index % 26)}",
                "uan_number": f"1001{n:04d}5678",
            },
        )
        employee = await ctx.employee_svc.create(payload, actor_id=ctx.actor)
        p.employee_id = employee.id
        ctx.done.append(f"employee:{p.key}")

    # Team managers point at the engineering manager and HR head.
    for team_name, key in (
        ("Product Engineering", "vikram"),
        ("Platform Engineering", "vikram"),
        ("People Operations", "ananya"),
    ):
        team = await s.get(Team, m[f"team:{team_name}"])
        if team is not None and team.manager_id is None:
            team.manager_id = ctx.uid(key)
    await s.flush()


# ======================================================================
# 3. Documents in the vault
# ======================================================================
async def seed_documents(ctx: Ctx) -> None:
    for key in ("arjun", "divya", "karthik", "pooja", "sneha"):
        p = ctx.people[key]
        for name in ("Offer Letter", "PAN Card"):
            title = f"{name} - {p.first} {p.last}"

            async def upload(title: str = title, p: Person = p, name: str = name) -> None:
                existing = await _one(
                    ctx.session, select(Document).where(Document.name == title, Document.deleted_at.is_(None))
                )
                if existing:
                    return
                doc = await ctx.document_svc.create(
                    DocumentUploadMetadata(
                        name=title,
                        category_id=ctx.masters["doc_category"],
                        document_type_id=ctx.masters["doc_type"],
                        owner_type=DocumentOwnerType.EMPLOYEE,
                        owner_id=p.emp,
                        description=f"{name} (demo)",
                    ),
                    UploadedFile(
                        _pdf(title),
                        f"{name.lower().replace(' ', '-')}-{p.first.lower()}.pdf",
                        "application/pdf",
                    ),
                    actor_id=ctx.actor,
                )
                if name == "PAN Card":
                    await ctx.document_svc.review(
                        doc.id,
                        DocumentReviewRequest(
                            status=DocumentStatus.APPROVED, review_notes="Verified against the original."
                        ),
                        actor_id=ctx.uid("rahul"),
                    )

            await ctx.step(f"document:{title}", upload)


# ======================================================================
# 4. Workforce: shifts, holidays, leave, attendance, regularizations
# ======================================================================
async def seed_workforce(ctx: Ctx) -> None:
    s = ctx.session
    m = ctx.masters

    calendar = await _one(
        s,
        select(HolidayCalendar).where(
            HolidayCalendar.year == TODAY.year, HolidayCalendar.deleted_at.is_(None)
        ),
    )
    if calendar is None:

        async def create_calendar() -> Any:
            return await ctx.workforce_svc.create_calendar(
                HolidayCalendarCreate(
                    name=f"India {TODAY.year}",
                    year=TODAY.year,
                    description="National and regional holidays (demo)",
                    holidays=[
                        HolidayInput(name="Republic Day", holiday_date=date(TODAY.year, 1, 26)),
                        HolidayInput(name="Holi", holiday_date=date(TODAY.year, 3, 4)),
                        HolidayInput(name="Independence Day", holiday_date=date(TODAY.year, 8, 15)),
                        HolidayInput(name="Gandhi Jayanti", holiday_date=date(TODAY.year, 10, 2)),
                        HolidayInput(name="Diwali", holiday_date=date(TODAY.year, 11, 8)),
                        HolidayInput(name="Christmas", holiday_date=date(TODAY.year, 12, 25)),
                    ],
                ),
                actor_id=ctx.actor,
            )

        calendar = await ctx.step("holiday calendar", create_calendar)
    holidays = set(
        (await s.execute(select(Holiday.holiday_date).where(Holiday.deleted_at.is_(None)))).scalars().all()
    )
    m["holidays"] = holidays

    people = list(PEOPLE)
    if m.get("shift"):
        for p in people:

            async def assign(p: Person = p) -> None:
                history = await ctx.workforce_svc.shift_history(p.emp)
                if history:
                    return
                await ctx.workforce_svc.assign_shift(
                    ShiftAssign(
                        employee_id=p.emp,
                        shift_id=m["shift"],
                        effective_from=max(p.joining, date(TODAY.year, 1, 1)),
                    ),
                    actor_id=ctx.actor,
                )

            await ctx.step(f"shift:{p.key}", assign)

    # Entitlements for the year, so leave can be applied for.
    for p in people:
        balances = await ctx.workforce_svc.balances_for(p.emp, TODAY.year)
        if balances and any(b.allocated for b in balances):
            continue
        for code, days in (("CL", 12), ("SL", 8), ("EL", 15)):
            if not m.get(f"leave:{code}"):
                continue

            async def adjust(p: Person = p, code: str = code, days: int = days) -> None:
                await ctx.workforce_svc.adjust_balance(
                    p.emp,
                    LeaveBalanceAdjustment(
                        leave_type_id=m[f"leave:{code}"],
                        year=TODAY.year,
                        days=Decimal(days),
                        reason=f"Annual {code} entitlement credited for {TODAY.year} (demo)",
                    ),
                    actor_id=ctx.actor,
                )

            await ctx.step(f"leave balance:{p.key}:{code}", adjust)

    # Leave requests in every state a manager sees.
    leave_days: dict[str, set[date]] = {p.key: set() for p in people}
    requests = (
        (
            "arjun",
            "EL",
            date(TODAY.year, 8, 10),
            date(TODAY.year, 8, 12),
            "Family wedding in Kochi",
            "sneha",
            True,
        ),
        (
            "karthik",
            "SL",
            date(TODAY.year, 8, 13),
            date(TODAY.year, 8, 13),
            "Fever; doctor advised rest",
            "sneha",
            True,
        ),
        ("pooja", "CL", date(TODAY.year, 8, 5), date(TODAY.year, 8, 5), "Personal errand", "vikram", False),
        (
            "divya",
            "CL",
            TODAY + timedelta(days=7),
            TODAY + timedelta(days=8),
            "Attending a conference",
            None,
            None,
        ),
        ("rahul", "CL", TODAY + timedelta(days=14), TODAY + timedelta(days=14), "House shifting", None, None),
    )
    for key, code, start, end, reason, approver, approved in requests:
        if not m.get(f"leave:{code}"):
            continue
        p = ctx.people[key]

        async def apply(
            p: Person = p,
            code: str = code,
            start: date = start,
            end: date = end,
            reason: str = reason,
            approver: str | None = approver,
            approved: bool | None = approved,
        ) -> None:
            document_id = None
            if code == "SL":
                certificate = await ctx.document_svc.create(
                    DocumentUploadMetadata(
                        name=f"Medical certificate - {p.first} {p.last} {start}",
                        category_id=m["doc_category"],
                        document_type_id=m["doc_type"],
                        owner_type=DocumentOwnerType.EMPLOYEE,
                        owner_id=p.emp,
                        description="Supporting document for sick leave (demo)",
                    ),
                    UploadedFile(
                        _pdf(f"certificate {p.key} {start}"),
                        f"medical-certificate-{p.key}.pdf",
                        "application/pdf",
                    ),
                    actor_id=p.usr,
                )
                document_id = certificate.id
            request = await ctx.workforce_svc.apply_for_leave(
                p.emp,
                LeaveApply(
                    leave_type_id=m[f"leave:{code}"],
                    from_date=start,
                    to_date=end,
                    reason=reason,
                    supporting_document_id=document_id,
                ),
                actor_id=p.usr,
            )
            if approver is not None:
                await ctx.workforce_svc.decide_leave(
                    request.id,
                    bool(approved),
                    "Approved, enjoy." if approved else "Sprint demo that day; please pick another date.",
                    actor_id=ctx.uid(approver),
                )
                if approved:
                    cursor = start
                    while cursor <= end:
                        leave_days[p.key].add(cursor)
                        cursor += timedelta(days=1)

        if not await _has_leave(ctx, p.emp, start):
            await ctx.step(f"leave:{key}:{start}", apply)

    # Attendance history: every working day since July for everybody on the books.
    since = date(TODAY.year, 7, 1)
    for p in people:
        start = max(since, p.joining)
        end = (
            min(TODAY - timedelta(days=1), date(TODAY.year, 7, 31))
            if p.key == LEAVER
            else TODAY - timedelta(days=1)
        )
        workdays = [d for d in working_days(start, end, holidays) if d not in leave_days[p.key]]
        if not workdays:
            continue
        recorded = await _attendance_dates(ctx, p.emp, start, end)
        for index, day in enumerate(workdays):
            if day in recorded:
                continue
            late = index % 9 == 4
            absent = p.key == "karthik" and day == date(TODAY.year, 7, 22)

            async def correct(
                p: Person = p, day: date = day, late: bool = late, absent: bool = absent
            ) -> None:
                if absent:
                    payload = AttendanceCorrection(
                        attendance_date=day,
                        status=AttendanceStatus.ABSENT,
                        reason="No check-in and no leave on record (demo backfill)",
                    )
                else:
                    check_in = datetime.combine(day, time(9, 52 if late else 24), tzinfo=UTC)
                    check_out = datetime.combine(day, time(18, 35 if late else 31), tzinfo=UTC)
                    payload = AttendanceCorrection(
                        attendance_date=day,
                        check_in_at=check_in,
                        check_out_at=check_out,
                        reason="Attendance backfilled from the demo register",
                    )
                await ctx.workforce_svc.correct_attendance(p.emp, payload, actor_id=ctx.actor)

            await ctx.step(f"attendance:{p.key}:{day}", correct)

    # Two regularization requests: one pending, one approved by the lead.
    for key, day, approver in (
        ("divya", date(TODAY.year, 8, 18), None),
        ("karthik", date(TODAY.year, 8, 6), "sneha"),
    ):
        p = ctx.people[key]

        async def regularize(p: Person = p, day: date = day, approver: str | None = approver) -> None:
            request = await ctx.workforce_svc.request_regularization(
                p.emp,
                RegularizationCreate(
                    attendance_date=day,
                    requested_check_out_at=datetime.combine(day, time(18, 45), tzinfo=UTC),
                    reason="Forgot to tap out after the evening release call.",
                ),
                actor_id=p.usr,
            )
            if approver:
                await ctx.workforce_svc.decide_regularization(
                    request.id, True, "Confirmed with the team.", actor_id=ctx.uid(approver)
                )

        if day not in await _regularization_dates(ctx, p.emp):
            await ctx.step(f"regularization:{key}:{day}", regularize)


async def _has_leave(ctx: Ctx, employee_id: uuid.UUID, on: date) -> bool:
    from app.models.workforce import LeaveRequest

    stmt = select(LeaveRequest.id).where(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.from_date <= on,
        LeaveRequest.to_date >= on,
        LeaveRequest.deleted_at.is_(None),
    )
    return (await ctx.session.execute(stmt)).first() is not None


async def _attendance_dates(ctx: Ctx, employee_id: uuid.UUID, start: date, end: date) -> set[date]:
    from app.models.workforce import AttendanceRecord

    stmt = select(AttendanceRecord.attendance_date).where(
        AttendanceRecord.employee_id == employee_id,
        AttendanceRecord.attendance_date.between(start, end),
        AttendanceRecord.deleted_at.is_(None),
    )
    return set((await ctx.session.execute(stmt)).scalars().all())


async def _regularization_dates(ctx: Ctx, employee_id: uuid.UUID) -> set[date]:
    from app.models.workforce import AttendanceRegularization

    stmt = select(AttendanceRegularization.attendance_date).where(
        AttendanceRegularization.employee_id == employee_id, AttendanceRegularization.deleted_at.is_(None)
    )
    return set((await ctx.session.execute(stmt)).scalars().all())


# ======================================================================
# 5. Clients, projects, allocations, timesheets
# ======================================================================
async def seed_projects(ctx: Ctx) -> None:
    s = ctx.session
    m = ctx.masters

    async def client(
        name: str, company: str, industry: str, contact: str, email: str, country: str, address: str
    ) -> Any:
        row = await _one(s, select(Client).where(Client.client_name == name, Client.deleted_at.is_(None)))
        if row is None:
            row = await ctx.project_svc.create_client(
                ClientCreate(
                    client_name=name,
                    company_name=company,
                    industry=industry,
                    contact_person=contact,
                    email=email,
                    phone="+91 40 4000 1234",
                    country=country,
                    address=address,
                    website="https://www.example.com",
                ),
                ctx.actor,
            )
            ctx.done.append(f"client:{name}")
        return row

    northwind = await client(
        "Northwind Retail",
        "Northwind Retail Pvt Ltd",
        "Retail",
        "Priya Raman",
        "priya.raman@northwind.example",
        "India",
        "4th Floor, Brigade Gateway, Bengaluru 560055",
    )
    helix = await client(
        "Helix Health",
        "Helix Health Inc.",
        "Healthcare",
        "Daniel Moore",
        "daniel.moore@helixhealth.example",
        "United States",
        "200 Clarendon St, Boston, MA 02116",
    )

    from app.models.project import Project

    async def project(
        name: str,
        client_id: uuid.UUID,
        description: str,
        start: date,
        end: date | None,
        status: str,
        pm: str,
        stack: list[str],
        priority: str,
    ) -> Any:
        row = await _one(s, select(Project).where(Project.project_name == name, Project.deleted_at.is_(None)))
        if row is None:
            row = await ctx.project_svc.create_project(
                ProjectCreate(
                    project_name=name,
                    client_id=client_id,
                    description=description,
                    start_date=start,
                    end_date=end,
                    status=status,
                    project_manager_id=ctx.eid(pm),
                    delivery_manager_id=ctx.eid("vikram"),
                    work_location_id=m["loc:HYD"],
                    technology_stack=stack,
                    priority=priority,
                ),
                ctx.actor,
            )
            ctx.done.append(f"project:{name}")
        return row

    commerce = await project(
        "Northwind Commerce Platform",
        northwind.id,
        "Re-platform the storefront and order management onto a modern stack.",
        date(TODAY.year, 3, 1),
        date(TODAY.year + 1, 2, 28),
        "active",
        "suresh",
        ["Python", "FastAPI", "React", "PostgreSQL"],
        "high",
    )
    portal = await project(
        "Helix Patient Portal",
        helix.id,
        "Patient-facing portal with appointments, records and secure messaging.",
        date(TODAY.year, 5, 15),
        None,
        "active",
        "suresh",
        ["TypeScript", "Next.js", "FHIR"],
        "critical",
    )
    await project(
        "Internal HR Analytics",
        northwind.id,
        "Dashboards for attrition, hiring velocity and utilisation.",
        date(TODAY.year, 10, 1),
        None,
        "planned",
        "sneha",
        ["Python", "dbt"],
        "medium",
    )
    m["project:commerce"], m["project:portal"] = commerce.id, portal.id

    allocations = (
        ("arjun", commerce, "Backend Engineer", 100),
        ("divya", commerce, "Senior Engineer", 100),
        ("sneha", commerce, "Tech Lead", 50),
        ("karthik", portal, "Frontend Engineer", 60),
        ("karthik", commerce, "Frontend Engineer", 40),
        ("pooja", portal, "Engineer", 100),
        ("rohan", portal, "Senior Engineer", 100),
    )
    for key, proj, role, pct in allocations:
        p = ctx.people[key]

        async def assign(p: Person = p, proj: Any = proj, role: str = role, pct: int = pct) -> None:
            start = max(proj.start_date, p.joining)
            end = date(TODAY.year, 7, 31) if p.key == LEAVER else proj.end_date
            await ctx.project_svc.assign(
                proj.id,
                AllocationCreate(
                    employee_id=p.emp,
                    role=role,
                    allocation_percentage=Decimal(pct),
                    start_date=start,
                    end_date=end,
                    reporting_manager_id=ctx.eid("suresh"),
                    reason="Client delivery staffing (demo)",
                ),
                ctx.actor,
            )

        if not await _allocated(ctx, p.emp, proj.id):
            await ctx.step(f"allocation:{key}:{proj.project_name}", assign)

    # Timesheets: two approved weeks, one submitted, one draft.
    weeks = [monday_of(TODAY) - timedelta(weeks=n) for n in (3, 2, 1, 0)]
    for key, proj, hours in (("arjun", commerce, 8), ("divya", commerce, 8), ("pooja", portal, 8)):
        p = ctx.people[key]
        for index, week in enumerate(weeks):

            async def timesheet(
                p: Person = p, proj: Any = proj, hours: int = hours, week: date = week, index: int = index
            ) -> None:
                days = [week + timedelta(days=d) for d in range(5)]
                days = [
                    d
                    for d in days
                    if d < TODAY
                    and d not in m["holidays"]
                    and d >= p.joining
                    and not await _has_leave(ctx, p.emp, d)
                ]
                if not days:
                    return
                tasks = ["API development", "Code review", "Bug fixes", "Sprint ceremonies", "Feature work"]
                sheet = await ctx.workforce_svc.save_timesheet(
                    p.emp,
                    TimesheetSave(
                        week_start_date=week,
                        entries=[
                            TimesheetEntryInput(
                                project_id=proj.id,
                                work_date=d,
                                task=tasks[i % len(tasks)],
                                hours=Decimal(hours),
                                comments=None,
                            )
                            for i, d in enumerate(days)
                        ],
                    ),
                    actor_id=p.usr,
                )
                if index <= 2:
                    await ctx.workforce_svc.submit_timesheet(sheet.id, actor_id=p.usr)
                if index <= 1:
                    await ctx.workforce_svc.decide_timesheet(
                        sheet.id, True, "Looks right.", actor_id=ctx.uid(p.manager or "vikram")
                    )

            if await _timesheet_exists(ctx, p.emp, week):
                continue
            await ctx.step(f"timesheet:{key}:{week}", timesheet)


async def _allocated(ctx: Ctx, employee_id: uuid.UUID, project_id: uuid.UUID) -> bool:
    from app.models.project import EmployeeAllocation

    stmt = select(EmployeeAllocation.id).where(
        EmployeeAllocation.employee_id == employee_id,
        EmployeeAllocation.project_id == project_id,
        EmployeeAllocation.deleted_at.is_(None),
    )
    return (await ctx.session.execute(stmt)).first() is not None


async def _timesheet_exists(ctx: Ctx, employee_id: uuid.UUID, week: date) -> bool:
    from app.models.workforce import Timesheet

    stmt = select(Timesheet.id).where(
        Timesheet.employee_id == employee_id,
        Timesheet.week_start_date == week,
        Timesheet.deleted_at.is_(None),
    )
    return (await ctx.session.execute(stmt)).first() is not None


# ======================================================================
# 6. Performance: cycle, goals, progress, reviews, recognition, feedback
# ======================================================================
async def seed_performance(ctx: Ctx) -> None:
    s = ctx.session
    fy = f"{TODAY.year}-{str(TODAY.year + 1)[-2:]}"
    cycle = await _one(
        s,
        select(PerformanceCycle).where(
            PerformanceCycle.financial_year == fy, PerformanceCycle.deleted_at.is_(None)
        ),
    )
    if cycle is None:

        async def create() -> Any:
            row = await ctx.performance_svc.create_cycle(
                PerformanceCycleCreate(
                    name=f"Annual Review FY {fy}",
                    financial_year=fy,
                    start_date=date(TODAY.year, 4, 1),
                    end_date=date(TODAY.year + 1, 3, 31),
                    self_review_deadline=date(TODAY.year + 1, 1, 31),
                    manager_review_deadline=date(TODAY.year + 1, 2, 28),
                    hr_review_deadline=date(TODAY.year + 1, 3, 20),
                    description="Company-wide annual performance cycle (demo).",
                ),
                actor_id=ctx.actor,
            )
            await ctx.performance_svc.set_cycle_status(
                row.id, PerformanceCycleStatus.ACTIVE, actor_id=ctx.actor
            )
            return row

        cycle = await ctx.step("performance cycle", create)
        if cycle is None:
            return
    elif cycle.status != PerformanceCycleStatus.ACTIVE.value:
        await ctx.step(
            "activate cycle",
            lambda: ctx.performance_svc.set_cycle_status(
                cycle.id, PerformanceCycleStatus.ACTIVE, actor_id=ctx.actor
            ),
        )

    goals_by_person: dict[str, list[tuple[str, str, str, int, str, int, GoalStatus]]] = {
        "arjun": [
            (
                "Ship the order-management API",
                "Delivery",
                "Deliver the new order service with 90% test coverage.",
                40,
                "high",
                65,
                GoalStatus.IN_PROGRESS,
            ),
            (
                "Reduce checkout p95 latency below 400 ms",
                "Quality",
                "p95 under 400 ms on the load test.",
                30,
                "medium",
                100,
                GoalStatus.COMPLETED,
            ),
            (
                "Complete AWS Developer certification",
                "Learning",
                "Certification passed before December.",
                30,
                "low",
                20,
                GoalStatus.IN_PROGRESS,
            ),
        ],
        "divya": [
            (
                "Lead the payments integration",
                "Delivery",
                "Razorpay and Stripe live in production.",
                60,
                "critical",
                80,
                GoalStatus.IN_PROGRESS,
            ),
            (
                "Mentor two junior engineers",
                "People",
                "Both mentees ship independently by Q4.",
                40,
                "medium",
                50,
                GoalStatus.IN_PROGRESS,
            ),
        ],
        "karthik": [
            (
                "Rebuild the appointments UI",
                "Delivery",
                "New booking flow released to all patients.",
                50,
                "high",
                35,
                GoalStatus.IN_PROGRESS,
            ),
            (
                "Raise front-end test coverage to 80%",
                "Quality",
                "Coverage report shows 80% or more.",
                50,
                "medium",
                0,
                GoalStatus.NOT_STARTED,
            ),
        ],
        "pooja": [
            (
                "Complete onboarding curriculum",
                "Learning",
                "All onboarding modules finished.",
                50,
                "high",
                100,
                GoalStatus.COMPLETED,
            ),
            (
                "Deliver first production feature",
                "Delivery",
                "One feature merged and released.",
                50,
                "medium",
                40,
                GoalStatus.IN_PROGRESS,
            ),
        ],
    }
    from app.models.performance import Goal

    for key, goals in goals_by_person.items():
        p = ctx.people[key]
        for title, category, criteria, weight, priority, pct, status in goals:
            existing = await _one(
                s,
                select(Goal).where(Goal.cycle_id == cycle.id, Goal.employee_id == p.emp, Goal.title == title),
            )
            if existing:
                continue

            async def goal(
                p: Person = p,
                title: str = title,
                category: str = category,
                criteria: str = criteria,
                weight: int = weight,
                priority: str = priority,
                pct: int = pct,
                status: GoalStatus = status,
            ) -> None:
                row = await ctx.performance_svc.assign_goal(
                    GoalCreate(
                        cycle_id=cycle.id,
                        employee_id=p.emp,
                        title=title,
                        description=f"{title}. {criteria}",
                        category=category,
                        success_criteria=criteria,
                        weightage=Decimal(weight),
                        start_date=max(cycle.start_date, p.joining),
                        due_date=date(TODAY.year, 12, 31),
                        priority=GoalPriority(priority),
                        project_id=None,
                    ),
                    actor_id=ctx.uid(p.manager or "vikram"),
                )
                if status is not GoalStatus.NOT_STARTED:
                    await ctx.performance_svc.record_progress(
                        row.id,
                        GoalProgressCreate(
                            completion_percentage=pct, status=status, comments="Progress update (demo)"
                        ),
                        actor_id=p.usr,
                    )

            await ctx.step(f"goal:{key}:{title}", goal)

    # A complete review chain for Divya: self → manager → HR final.
    async def review_chain() -> None:
        p = ctx.people["divya"]
        goals = (
            (await s.execute(select(Goal).where(Goal.cycle_id == cycle.id, Goal.employee_id == p.emp)))
            .scalars()
            .all()
        )
        ratings = [GoalRatingInput(goal_id=g.id, rating=4, comments="On track.") for g in goals]
        await ctx.performance_svc.submit_self_review(
            cycle.id,
            p.emp,
            SelfReviewSubmit(
                overall_rating=4,
                overall_comments="Payments integration shipped on time; mentoring is going well.",
                achievements="Led the payments integration end to end.",
                challenges="Balancing delivery with mentoring time.",
                goal_ratings=ratings,
            ),
            actor_id=p.usr,
        )
        await ctx.performance_svc.submit_manager_review(
            cycle.id,
            p.emp,
            ManagerReviewSubmit(
                overall_rating=5,
                overall_feedback="Consistently exceeds expectations and lifts the team.",
                strengths="Ownership, technical depth, mentoring.",
                improvement_areas="Delegate more of the day-to-day.",
                recommendation=PerformanceRecommendation.PROMOTION,
                goal_ratings=[GoalRatingInput(goal_id=g.id, rating=5) for g in goals],
            ),
            actor_id=ctx.uid("sneha"),
        )
        await ctx.performance_svc.finalise(
            cycle.id,
            p.emp,
            FinalReviewSubmit(
                final_rating=5, comments="Confirmed at 5. Promotion recommended for the next cycle."
            ),
            actor_id=ctx.uid("ananya"),
        )

    from app.models.performance import SelfReview

    if (
        await _one(
            s,
            select(SelfReview).where(
                SelfReview.cycle_id == cycle.id, SelfReview.employee_id == ctx.eid("divya")
            ),
        )
        is None
    ):
        await ctx.step("review chain: divya", review_chain)

    from app.models.performance import ContinuousFeedback, Recognition

    if await _one(s, select(Recognition).where(Recognition.employee_id == ctx.eid("divya"))) is None:
        await ctx.step(
            "recognition: divya",
            lambda: ctx.performance_svc.add_recognition(
                RecognitionCreate(
                    employee_id=ctx.eid("divya"),
                    recognition_type=RecognitionType.STAR_PERFORMER,
                    title="Payments go-live",
                    description="Carried the payments release across the line with zero incidents.",
                    awarded_on=TODAY - timedelta(days=10),
                ),
                actor_id=ctx.uid("vikram"),
            ),
        )
    if (
        await _one(
            s, select(ContinuousFeedback).where(ContinuousFeedback.to_employee_id == ctx.eid("karthik"))
        )
        is None
    ):
        await ctx.step(
            "feedback: karthik",
            lambda: ctx.performance_svc.add_feedback(
                PerformanceFeedbackCreate(
                    to_employee_id=ctx.eid("karthik"),
                    title="Great handover notes",
                    description="The runbook you wrote for the appointments UI saved the on-call a weekend.",
                    category=FeedbackCategory.APPRECIATION,
                    visibility=FeedbackVisibility.MANAGER,
                    feedback_date=TODAY - timedelta(days=3),
                ),
                actor_id=ctx.uid("sneha"),
            ),
        )


# ======================================================================
# 7. Hiring: requisition → opening → candidates → interview → offer → onboarding
# ======================================================================
async def seed_recruitment(ctx: Ctx) -> None:
    s = ctx.session
    m = ctx.masters
    title = "Senior Backend Engineer"
    requisition = await _one(
        s,
        select(JobRequisition).where(JobRequisition.job_title == title, JobRequisition.deleted_at.is_(None)),
    )
    if requisition is not None:
        return  # the whole hiring story hangs off this one requisition

    async def hire() -> None:
        req = await ctx.requisition_svc.create(
            RequisitionCreate(
                job_title=title,
                hiring_type="new_position",
                request_type="new_position",
                business_unit_id=m["bu:TECH"],
                team_id=m["team:Product Engineering"],
                location_id=m["loc:HYD"],
                designation_id=m["desig:SSE"],
                grade_id=m["grade:G3"],
                employment_type_id=m["etype:FULL_TIME"],
                openings=2,
                experience_min=4,
                experience_max=8,
                education="Bachelor's in Computer Science or equivalent",
                skills=["Python", "FastAPI", "PostgreSQL", "AWS"],
                certifications=[],
                salary_from=Decimal("1600000"),
                salary_to=Decimal("2400000"),
                budget_approved=True,
                hiring_manager_id=ctx.uid("vikram"),
                second_approver_id=ctx.uid("suresh"),
                hr_approver_id=ctx.uid("ananya"),
                recruiter_id=ctx.uid("meera"),
                target_joining_date=TODAY + timedelta(days=70),
                priority="high",
                responsibilities=(
                    "Own backend services for the commerce platform: design, build, review and operate them."
                ),
                requirements=(
                    "4+ years with Python web services, strong SQL, and services run in production."
                ),
                benefits="Health insurance, learning budget, hybrid work.",
                working_model="hybrid",
                business_justification=(
                    "Approved headcount for the Northwind commerce roadmap; two open seats."
                ),
            ),
            ctx.uid("meera"),
        )
        await ctx.requisition_svc.submit(req.id, ctx.uid("meera"))
        for approver, comment in (
            ("vikram", "Approved: we need these seats for Q4."),
            ("suresh", "Budget confirmed."),
            ("ananya", "Approved by HR."),
        ):
            await ctx.requisition_svc.act(req.id, "approve", comment, ctx.uid(approver))
        opening = await ctx.recruitment_svc.create_opening(
            OpeningCreate(
                requisition_id=req.id, recruiter_id=ctx.uid("meera"), closing_date=TODAY + timedelta(days=45)
            ),
            ctx.uid("meera"),
        )
        await ctx.recruitment_svc.opening_action(opening.id, "publish", ctx.uid("meera"))
        await ctx.requisition_svc.act(req.id, "open", "Opened for sourcing.", ctx.uid("ananya"))

        sources = (await s.execute(select(CandidateSource))).scalars().all()
        stages = {row.name: row for row in (await s.execute(select(RecruitmentStage))).scalars().all()}
        source_id = sources[0].id

        async def resume(name: str) -> uuid.UUID:
            doc = await ctx.document_svc.create(
                DocumentUploadMetadata(
                    name=f"Resume - {name}",
                    category_id=m["doc_category"],
                    document_type_id=m["doc_type"],
                    owner_type=DocumentOwnerType.USER,
                    owner_id=ctx.uid("meera"),
                    description="Candidate resume (demo)",
                ),
                UploadedFile(
                    _pdf(f"resume {name}"), f"resume-{name.lower().replace(' ', '-')}.pdf", "application/pdf"
                ),
                actor_id=ctx.uid("meera"),
            )
            return doc.id

        async def candidate(
            first: str,
            last: str,
            email: str,
            mobile: str,
            years: str,
            company: str,
            ctc: str,
            expected: str,
            skills: list[str],
        ) -> Any:
            return await ctx.recruitment_svc.create_candidate(
                CandidateCreate(
                    job_opening_id=opening.id,
                    source_id=source_id,
                    recruiter_id=ctx.uid("meera"),
                    first_name=first,
                    last_name=last,
                    email=email,
                    mobile_number=mobile,
                    current_company=company,
                    current_designation="Software Engineer",
                    experience_years=Decimal(years),
                    current_ctc=Decimal(ctc),
                    expected_ctc=Decimal(expected),
                    notice_period_days=30,
                    current_location="Hyderabad",
                    preferred_location="Hyderabad",
                    skills=skills,
                    resume_document_id=await resume(f"{first} {last}"),
                ),
                ctx.uid("meera"),
            )

        aisha = await candidate(
            "Aisha",
            "Sheikh",
            f"aisha.sheikh@{DEMO_DOMAIN}",
            "+91 98111 22334",
            "6",
            "Flipkart",
            "1700000",
            "2200000",
            ["Python", "FastAPI", "PostgreSQL", "AWS"],
        )
        nikhil = await candidate(
            "Nikhil",
            "Joshi",
            "nikhil.joshi@candidates.example",
            "+91 98222 33445",
            "3",
            "Infosys",
            "900000",
            "1500000",
            ["Java", "Spring"],
        )
        tanvi = await candidate(
            "Tanvi",
            "Kulkarni",
            "tanvi.kulkarni@candidates.example",
            "+91 98333 44556",
            "5",
            "Zoho",
            "1400000",
            "1900000",
            ["Python", "Django", "Redis"],
        )

        await ctx.recruitment_svc.add_note(
            aisha.id, NoteCreate(body="Strong backend profile; referred by Divya."), ctx.uid("meera")
        )
        await ctx.recruitment_svc.move_stage(
            aisha.id,
            StageMove(stage_id=stages["Screening"].id, comments="Phone screen cleared."),
            ctx.uid("meera"),
        )
        await ctx.recruitment_svc.move_stage(
            aisha.id,
            StageMove(stage_id=stages["Technical Round 1"].id, comments="Scheduling the technical round."),
            ctx.uid("meera"),
        )
        await ctx.recruitment_svc.move_stage(
            nikhil.id, StageMove(stage_id=stages["Screening"].id, comments="Phone screen."), ctx.uid("meera")
        )
        await ctx.recruitment_svc.move_stage(
            nikhil.id,
            StageMove(stage_id=stages["Rejected"].id, comments="Experience below the bar for this role."),
            ctx.uid("meera"),
        )
        pool = await ctx.recruitment_svc.create_pool(
            TalentPoolCreate(
                name="Backend bench", description="Strong profiles to revisit for future openings."
            ),
            ctx.uid("meera"),
        )
        await ctx.recruitment_svc.add_pool_member(pool.id, tanvi.id, ctx.uid("meera"))

        # Interview next Monday 10:00 IST, one lead and one panel member.
        starts = datetime.combine(next_weekday(0, TODAY), time(4, 30), tzinfo=UTC)
        interview = await ctx.interview_svc.schedule(
            InterviewCreate(
                candidate_id=aisha.id,
                interview_type="technical",
                interview_round="Technical Round 1",
                starts_at=starts,
                ends_at=starts + timedelta(hours=1),
                time_zone="Asia/Kolkata",
                mode="online",
                meeting_link="https://meet.example.com/people360-demo",
                location=None,
                recruiter_notes="Focus on API design and data modelling.",
                panels=[
                    {"employee_id": ctx.eid("sneha"), "panel_role": "lead_interviewer"},
                    {"employee_id": ctx.eid("divya"), "panel_role": "panel_member"},
                ],
            ),
            ctx.uid("meera"),
        )
        scores = [
            {"category": c, "score": v}
            for c, v in (
                ("technical_skills", 9),
                ("communication", 8),
                ("problem_solving", 9),
                ("domain_knowledge", 8),
                ("attitude", 9),
                ("culture_fit", 8),
            )
        ]
        await ctx.interview_svc.submit_feedback(
            interview.id,
            FeedbackCreate(
                interviewer_id=ctx.eid("sneha"),
                scores=scores,
                overall_comments="Excellent depth on API design; hire.",
                recommendation="strong_hire",
            ),
            ctx.uid("sneha"),
        )
        await ctx.interview_svc.submit_feedback(
            interview.id,
            FeedbackCreate(
                interviewer_id=ctx.eid("divya"),
                scores=scores,
                overall_comments="Solid fundamentals, communicates clearly.",
                recommendation="hire",
            ),
            ctx.uid("divya"),
        )
        await ctx.interview_svc.decision(
            interview.id,
            DecisionRequest(decision="final_selection", comments="Unanimous hire."),
            ctx.uid("meera"),
        )

        joining = TODAY + timedelta(days=60)
        ctc = Decimal("2100000")
        offer = await ctx.offer_svc.create(
            OfferCreate(
                candidate_id=aisha.id,
                ctc=ctc,
                joining_date=joining,
                probation_months=6,
                notice_period_days=60,
                reporting_manager_id=ctx.eid("vikram"),
                work_mode="hybrid",
                benefits="Group health insurance, learning budget, hybrid work.",
                leave_policy_summary="12 casual, 8 sick and 15 earned leave days per year.",
                working_hours="9:30 to 18:30, Monday to Friday.",
                confidentiality="Standard confidentiality and IP assignment terms apply.",
                nda_required=True,
                expiry_date=TODAY + timedelta(days=21),
                salary_components=[
                    {"name": "Basic Salary", "component_type": "earning", "annual_amount": Decimal("840000")},
                    {"name": "HRA", "component_type": "earning", "annual_amount": Decimal("420000")},
                    {
                        "name": "Special Allowance",
                        "component_type": "earning",
                        "annual_amount": Decimal("739200"),
                    },
                    {
                        "name": "Provident Fund (employer)",
                        "component_type": "benefit",
                        "annual_amount": Decimal("100800"),
                        "is_employer_contribution": True,
                    },
                ],
                hr_executive_id=ctx.uid("rahul"),
                hr_manager_id=ctx.uid("ananya"),
                business_unit_head_id=ctx.uid("vikram"),
            ),
            ctx.uid("meera"),
        )
        await ctx.offer_svc.submit(offer.id, ctx.uid("meera"))
        for approver in ("rahul", "ananya", "vikram"):
            await ctx.offer_svc.approval(offer.id, "approve", "Approved.", ctx.uid(approver))
        await ctx.offer_svc.release(offer.id, ctx.uid("meera"))
        await ctx.offer_svc.candidate_action(offer.id, "accept", None, ctx.uid("meera"))

        # Preboarding: a portal login for the joiner, documents, policies, conversion.
        joiner = User(
            email=normalise_email(aisha.email),
            username="aisha.sheikh",
            first_name="Aisha",
            last_name="Sheikh",
            hashed_password=hash_password(DEMO_PASSWORD),
            is_active=True,
            is_superuser=False,
            email_verified_at=datetime.now(UTC),
            password_changed_at=datetime.now(UTC),
            created_by=ctx.actor,
            updated_by=ctx.actor,
        )
        s.add(joiner)
        await s.flush()
        if m["roles"].get("employee"):
            s.add(
                UserRole(
                    user_id=joiner.id,
                    role_id=m["roles"]["employee"],
                    created_by=ctx.actor,
                    updated_by=ctx.actor,
                )
            )
        profile = await ctx.onboarding_svc.start(
            ProfileStart(offer_id=offer.id, user_id=joiner.id), ctx.uid("rahul")
        )
        await ctx.onboarding_svc.update_profile(
            profile.id,
            ProfileUpdate(
                joining_date=joining,
                joining_confirmed=True,
                first_name="Aisha",
                last_name="Sheikh",
                date_of_birth=date(1996, 3, 12),
                gender="female",
                blood_group="B+",
                marital_status="single",
                nationality="Indian",
                personal_email=aisha.email,
                mobile_number="+91 98111 22334",
                emergency_contact={
                    "name": "Imran Sheikh",
                    "relationship": "Father",
                    "phone_number": "+91 98111 00011",
                },
                addresses=[
                    {
                        "address_type": "current",
                        "address_line1": "7 Banjara Hills",
                        "city": "Hyderabad",
                        "state": "Telangana",
                        "country": "India",
                        "postal_code": "500034",
                    },
                    {
                        "address_type": "permanent",
                        "address_line1": "21 Residency Road",
                        "city": "Bengaluru",
                        "state": "Karnataka",
                        "country": "India",
                        "postal_code": "560025",
                    },
                ],
                bank_details={
                    "bank_name": "ICICI Bank",
                    "account_holder_name": "Aisha Sheikh",
                    "account_number": "001201234567",
                    "ifsc_code": "ICIC0000012",
                    "branch_name": "Banjara Hills",
                },
                aadhaar_number="345678901234",
                pan_number="DEMOZ9876Q",
            ),
            joiner.id,
        )
        for code, name in (
            ("employee_handbook", "Employee Handbook"),
            ("nda", "Non-disclosure Agreement"),
            ("company_policies", "Company Policies"),
            ("code_of_conduct", "Code of Conduct"),
        ):
            await ctx.onboarding_svc.acknowledge(
                profile.id,
                PolicyInput(policy_code=code, policy_name=name, accepted=True),
                joiner.id,
                RequestOrigin(ip_address="127.0.0.1", user_agent="seed_demo"),
            )
        for name in (
            "Photograph",
            "Aadhaar",
            "PAN",
            "Resume",
            "Educational Certificates",
            "Experience Letters",
            "Bank Passbook/Cancelled Cheque",
        ):
            doc = await ctx.document_svc.create(
                DocumentUploadMetadata(
                    name=name,
                    category_id=m["doc_category"],
                    document_type_id=m["doc_type"],
                    owner_type=DocumentOwnerType.CANDIDATE,
                    owner_id=aisha.id,
                    description="Preboarding document (demo)",
                ),
                UploadedFile(
                    _pdf(f"aisha {name}"),
                    f"{name.lower().replace(' ', '-').replace('/', '-')}.pdf",
                    "application/pdf",
                ),
                actor_id=joiner.id,
            )
            await ctx.document_svc.review(
                doc.id,
                DocumentReviewRequest(status=DocumentStatus.APPROVED, review_notes="Verified."),
                actor_id=ctx.uid("rahul"),
            )
        await ctx.onboarding_svc.approve_information(profile.id, ctx.uid("rahul"))
        employee = await ctx.onboarding_svc.convert(
            profile.id,
            ConversionInput(
                user_id=joiner.id,
                official_email=aisha.email,
                employment_type_id=m["etype:FULL_TIME"],
                business_unit_id=m["bu:TECH"],
                team_id=m["team:Product Engineering"],
                designation_id=m["desig:SSE"],
                grade_id=m["grade:G3"],
                work_location_id=m["loc:HYD"],
                reporting_manager_id=ctx.eid("vikram"),
            ),
            ctx.uid("rahul"),
        )
        case = await ctx.onboarding_svc.create_case(
            profile.id,
            CaseCreate(
                tasks=[
                    TaskCreate(
                        category="hr",
                        title="Welcome session and policy walkthrough",
                        owner_id=ctx.uid("rahul"),
                        due_date=joining,
                    ),
                    TaskCreate(
                        category="it",
                        title="Laptop, email and repository access",
                        owner_id=ctx.uid("fatima"),
                        due_date=joining - timedelta(days=2),
                    ),
                    TaskCreate(
                        category="manager",
                        title="30-60-90 day plan",
                        owner_id=ctx.uid("vikram"),
                        due_date=joining + timedelta(days=7),
                    ),
                    TaskCreate(
                        category="administration",
                        title="ID card and desk allocation",
                        owner_id=ctx.uid("rahul"),
                        due_date=joining,
                    ),
                ]
            ),
            ctx.uid("rahul"),
        )
        first_task = sorted(case.tasks, key=lambda t: t.due_date)[0]
        await ctx.onboarding_svc.update_task(
            first_task.id,
            TaskUpdate(status="completed", comments="Done ahead of joining."),
            ctx.uid("fatima"),
        )
        # Payroll should not expect a salary for somebody who has not joined yet.
        await ctx.payroll_config_svc.upsert_employee_settings(
            employee.id,
            EmployeeSettingsUpsert(
                eligibility=PayrollEligibility.NOT_ELIGIBLE,
                eligibility_reason=PayrollEligibilityReason.PENDING_ONBOARDING,
                notes="Joins later this year; compensation to be set up on joining.",
            ),
            actor_id=ctx.actor,
        )
        ctx.people["aisha"] = Person(
            "aisha",
            "Aisha",
            "Sheikh",
            "employee",
            "SSE",
            "Product Engineering",
            "TECH",
            "G3",
            joining,
            manager="vikram",
            user_id=joiner.id,
            employee_id=employee.id,
        )

    await ctx.step("hiring flow: Senior Backend Engineer", hire)


# ======================================================================
# 8. Assets
# ======================================================================
async def seed_assets(ctx: Ctx) -> None:
    s = ctx.session
    categories = (
        (await s.execute(select(AssetCategory).where(AssetCategory.deleted_at.is_(None)))).scalars().all()
    )
    if not categories:
        return

    def category(*needles: str) -> uuid.UUID:
        for needle in needles:
            for row in categories:
                if needle in row.name.lower():
                    return row.id
        return categories[0].id

    from app.models.asset import Asset

    plan = (
        (
            "DEMO-LT-001",
            'MacBook Pro 14"',
            category("laptop", "computer"),
            "Apple",
            "MacBook Pro M3",
            "arjun",
            "excellent",
        ),
        (
            "DEMO-LT-002",
            "ThinkPad X1 Carbon",
            category("laptop", "computer"),
            "Lenovo",
            "X1 Carbon Gen 11",
            "divya",
            "good",
        ),
        ("DEMO-LT-003", "Dell XPS 15", category("laptop", "computer"), "Dell", "XPS 9530", LEAVER, "good"),
        (
            "DEMO-MN-001",
            'Dell 27" Monitor',
            category("monitor", "display", "peripheral"),
            "Dell",
            "U2723QE",
            "karthik",
            "new",
        ),
        ("DEMO-PH-001", "iPhone 15", category("phone", "mobile"), "Apple", "iPhone 15", None, "good"),
        (
            "DEMO-LT-004",
            'MacBook Air 13"',
            category("laptop", "computer"),
            "Apple",
            "MacBook Air M2",
            None,
            "new",
        ),
    )
    for tag, name, category_id, brand, model, holder, condition in plan:
        if await _one(s, select(Asset).where(Asset.asset_tag == tag)):
            continue

        async def create(
            tag: str = tag,
            name: str = name,
            category_id: uuid.UUID = category_id,
            brand: str = brand,
            model: str = model,
            holder: str | None = holder,
            condition: str = condition,
        ) -> None:
            asset = await ctx.asset_svc.create_asset(
                AssetCreate(
                    name=name,
                    category_id=category_id,
                    asset_tag=tag,
                    condition=condition,
                    brand=brand,
                    model=model,
                    serial_number=f"SN-{tag}",
                    purchase_date=date(TODAY.year - 1, 4, 10),
                    purchase_cost=Decimal("145000.00"),
                    vendor="Ingram Micro",
                    warranty_start=date(TODAY.year - 1, 4, 10),
                    warranty_end=date(TODAY.year + 2, 4, 9),
                    location="Hyderabad",
                ),
                actor_id=ctx.uid("fatima"),
            )
            if holder:
                await ctx.asset_svc.assign(
                    asset.id,
                    AssetAssign(
                        employee_id=ctx.eid(holder),
                        assigned_date=max(ctx.people[holder].joining, date(TODAY.year - 1, 4, 15)),
                        condition_at_assignment=condition,
                        notes="Issued on joining (demo)",
                    ),
                    actor_id=ctx.uid("fatima"),
                )
            if tag == "DEMO-PH-001":
                await ctx.asset_svc.schedule_maintenance(
                    MaintenanceCreate(
                        asset_id=asset.id,
                        maintenance_type=MaintenanceType.REPAIR,
                        start_date=TODAY - timedelta(days=2),
                        vendor="Apple Service Centre",
                        description="Battery replacement",
                        start_now=True,
                    ),
                    actor_id=ctx.uid("fatima"),
                )

        await ctx.step(f"asset:{tag}", create)


# ======================================================================
# 9. Helpdesk and announcements
# ======================================================================
async def seed_helpdesk(ctx: Ctx) -> None:
    s = ctx.session
    categories = {
        row.name.lower(): row
        for row in (await s.execute(select(HelpdeskCategory).where(HelpdeskCategory.deleted_at.is_(None))))
        .scalars()
        .all()
    }
    if not categories:
        return

    def cat(*needles: str) -> Any:
        for needle in needles:
            for name, row in categories.items():
                if needle in name:
                    return row
        return next(iter(categories.values()))

    from app.models.helpdesk import HelpdeskTicket

    tickets = (
        (
            "arjun",
            cat("it"),
            "Laptop battery drains within two hours",
            "The MacBook battery drops from 100% to 20% in about two hours since last week's update.",
            TicketPriority.HIGH,
            "resolve",
        ),
        (
            "divya",
            cat("payroll"),
            "Question about HRA on the July payslip",
            "The HRA amount looks lower than expected for July. Could somebody check the proration?",
            TicketPriority.MEDIUM,
            "progress",
        ),
        (
            "pooja",
            cat("leave"),
            "Casual leave balance not showing",
            "My casual leave balance shows zero on the dashboard although I joined in July.",
            TicketPriority.LOW,
            None,
        ),
    )
    for key, category, subject, description, priority, outcome in tickets:
        if await _one(s, select(HelpdeskTicket).where(HelpdeskTicket.subject == subject)):
            continue
        p = ctx.people[key]

        async def raise_ticket(
            p: Person = p,
            category: Any = category,
            subject: str = subject,
            description: str = description,
            priority: TicketPriority = priority,
            outcome: str | None = outcome,
        ) -> None:
            employee = await ctx.employee(p.key)
            ticket = await ctx.helpdesk_svc.raise_ticket(
                employee,
                TicketRaise(
                    category_id=category.id, subject=subject, description=description, priority=priority
                ),
                actor_id=p.usr,
            )
            if outcome in {"progress", "resolve"}:
                await ctx.helpdesk_svc.change_status(
                    ticket.id,
                    TicketStatusChange(status=TicketStatus.IN_PROGRESS, note="Picked up."),
                    actor_id=ctx.uid("rahul"),
                )
                await ctx.helpdesk_svc.comment(
                    ticket.id,
                    TicketComment(body="Looking into this now; will update you shortly."),
                    actor_id=ctx.uid("rahul"),
                )
            if outcome == "resolve":
                await ctx.helpdesk_svc.change_status(
                    ticket.id,
                    TicketStatusChange(
                        status=TicketStatus.RESOLVED,
                        resolution="Battery replaced under warranty; device returned.",
                    ),
                    actor_id=ctx.uid("rahul"),
                )

        await ctx.step(f"ticket:{subject}", raise_ticket)

    from app.models.announcement import Announcement

    announcements = (
        (
            "Welcome to People360",
            "Our new HR platform is live. Attendance, leave, timesheets, payslips and requests are all "
            "in one place. "
            "Sign in with your work email and explore My Workspace.",
            "Attendance, leave, payslips and requests now live in one place.",
            True,
            False,
            "important",
        ),
        (
            f"Holiday calendar {TODAY.year}",
            "The company holiday calendar for the year has been published. Restricted holidays can be "
            "applied for as leave.",
            "Holiday list published.",
            False,
            True,
            "normal",
        ),
        (
            "Q3 all-hands",
            "Join us for the quarterly all-hands next Thursday at 4 PM in the Hyderabad town hall "
            "and online.",
            "Quarterly all-hands next Thursday.",
            False,
            False,
            "normal",
        ),
    )
    for index, (title, body, summary, pinned, ack, level) in enumerate(announcements):
        if await _one(s, select(Announcement).where(Announcement.title == title)):
            continue

        async def announce(
            title: str = title,
            body: str = body,
            summary: str = summary,
            pinned: bool = pinned,
            ack: bool = ack,
            priority: str = level,
            index: int = index,
        ) -> None:
            row = await ctx.announcement_svc.create(
                AnnouncementCreate(
                    title=title,
                    body=body,
                    summary=summary,
                    pinned=pinned,
                    requires_acknowledgement=ack,
                    priority=priority,
                ),
                actor_id=ctx.uid("ananya"),
            )
            if index < 2:
                await ctx.announcement_svc.publish(row.id, AnnouncementPublish(), actor_id=ctx.uid("ananya"))
                if ack:
                    await ctx.announcement_svc.acknowledge(
                        await ctx.employee("arjun"), row.id, actor_id=ctx.uid("arjun")
                    )

        await ctx.step(f"announcement:{title}", announce)


# ======================================================================
# 10. Payroll: components → structure → compensation → July finalized, August in review
# ======================================================================
async def seed_payroll(ctx: Ctx) -> None:
    s = ctx.session

    config = await _one(s, select(PayrollConfiguration))
    if config is not None:
        config.overtime_enabled = True
        config.overtime_approval_required = False
        config.overtime_multiplier = Decimal("1.50")
        config.standard_daily_hours = Decimal("8.00")
        config.rounding_rule = "nearest_whole"
        config.proration_basis = "calendar_days"
        config.unpaid_leave_treatment = "deduct"
        config.unpaid_leave_basis = "calendar_days"
        await s.flush()

    components: dict[str, uuid.UUID] = {}
    specs = (
        (
            "DEMO_BASIC",
            "Basic Salary",
            SalaryComponentType.EARNING,
            SalaryCalculationType.FIXED,
            Decimal("40000"),
            None,
            {"proration_allowed": True, "leave_impact": True, "overtime_eligible": True},
        ),
        (
            "DEMO_HRA",
            "House Rent Allowance",
            SalaryComponentType.EARNING,
            SalaryCalculationType.PERCENTAGE,
            Decimal("40"),
            "basic",
            {"proration_allowed": True},
        ),
        (
            "DEMO_SPL",
            "Special Allowance",
            SalaryComponentType.EARNING,
            SalaryCalculationType.FIXED,
            Decimal("10000"),
            None,
            {"proration_allowed": True},
        ),
        (
            "DEMO_PF",
            "Provident Fund",
            SalaryComponentType.DEDUCTION,
            SalaryCalculationType.PERCENTAGE,
            Decimal("12"),
            "basic",
            {"proration_allowed": False, "is_taxable": False},
        ),
        (
            "DEMO_PT",
            "Professional Tax",
            SalaryComponentType.DEDUCTION,
            SalaryCalculationType.FIXED,
            Decimal("200"),
            None,
            {"proration_allowed": False, "is_taxable": False},
        ),
    )
    for code, name, ctype, calc, value, basis, extra in specs:
        row = await _by_code(s, SalaryComponent, code)
        if row is None:
            row = await ctx.payroll_svc.create_component(
                SalaryComponentCreate(
                    name=name,
                    code=code,
                    component_type=ctype,
                    calculation_type=calc,
                    value=value,
                    percentage_basis=basis,
                    description=f"{name} (demo)",
                    **extra,
                ),
                actor_id=ctx.uid("fatima"),
            )
            ctx.done.append(f"component:{code}")
        components[code] = row.id

    from app.models.payroll import SalaryStructure

    structure = await _one(
        s,
        select(SalaryStructure).where(
            SalaryStructure.name == "Standard Monthly (Demo)", SalaryStructure.deleted_at.is_(None)
        ),
    )
    if structure is None:
        structure = await ctx.payroll_svc.create_structure(
            SalaryStructureCreate(
                name="Standard Monthly (Demo)",
                description="Basic + HRA + special allowance, PF and PT deducted.",
                components=[{"component_id": cid} for cid in components.values()],
            ),
            actor_id=ctx.uid("fatima"),
        )
        await ctx.payroll_svc.set_structure_status(
            structure.id, SalaryStructureStatus.ACTIVE, actor_id=ctx.uid("fatima")
        )
        ctx.done.append("salary structure")

    # Compensation for everybody in the cast; nobody else is expected to have one.
    for p in PEOPLE:
        current = await ctx.payroll_svc.employee_compensation(p.emp)
        if getattr(current, "current", None) is not None:
            continue
        basic = Decimal(p.monthly_basic)
        hra = (basic * Decimal("0.40")).quantize(Decimal("1"))
        spl = Decimal(p.monthly_basic // 4)
        monthly_gross = basic + hra + spl

        async def assign(
            p: Person = p, basic: Decimal = basic, spl: Decimal = spl, monthly_gross: Decimal = monthly_gross
        ) -> None:
            await ctx.payroll_svc.assign_compensation(
                p.emp,
                CompensationAssign(
                    salary_structure_id=structure.id,
                    effective_from=max(p.joining, date(TODAY.year, 1, 1)),
                    annual_ctc=monthly_gross * 12 + basic * Decimal("0.12") * 12,
                    annual_gross=monthly_gross * 12,
                    monthly_gross=monthly_gross,
                    basic_salary=basic,
                    components=[
                        {"component_id": components["DEMO_BASIC"], "value": basic},
                        {"component_id": components["DEMO_HRA"], "value": Decimal("40")},
                        {"component_id": components["DEMO_SPL"], "value": spl},
                        {"component_id": components["DEMO_PF"], "value": Decimal("12")},
                        {"component_id": components["DEMO_PT"], "value": Decimal("200")},
                    ],
                    reason="Compensation set up for the demo",
                ),
                actor_id=ctx.uid("fatima"),
            )

        await ctx.step(f"compensation:{p.key}", assign)

    # Anybody outside the cast without a salary is excluded so the run can complete.
    from app.models.payroll import EmployeeCompensation, PayrollEmployeeSetting

    with_comp = set(
        (
            await s.execute(
                select(EmployeeCompensation.employee_id).where(EmployeeCompensation.status == "active")
            )
        )
        .scalars()
        .all()
    )
    settled = set((await s.execute(select(PayrollEmployeeSetting.employee_id))).scalars().all())
    others = (await s.execute(select(Employee).where(Employee.deleted_at.is_(None)))).scalars().all()
    excluded = 0
    for employee in others:
        if employee.id in with_comp or employee.id in settled:
            continue
        setting = PayrollEmployeeSetting(
            employee_id=employee.id,
            eligibility=PayrollEligibility.NOT_ELIGIBLE.value,
            eligibility_reason=PayrollEligibilityReason.PAYROLL_EXCLUDED.value,
            notes="No compensation on record; excluded by the demo seed.",
            created_by=ctx.actor,
            updated_by=ctx.actor,
        )
        s.add(setting)
        excluded += 1
    await s.flush()
    if excluded:
        ctx.done.append(f"payroll exclusions: {excluded} employees without a salary")

    async def period(name: str, start: date, end: date, pay: date) -> Any:
        row = await _one(
            s, select(PayrollPeriod).where(PayrollPeriod.name == name, PayrollPeriod.deleted_at.is_(None))
        )
        if row is None:
            row = await ctx.payroll_config_svc.create_period(
                PayrollPeriodCreate(name=name, start_date=start, end_date=end, pay_date=pay),
                actor_id=ctx.uid("fatima"),
            )
            ctx.done.append(f"period:{name}")
        return row

    prev_month_end = TODAY.replace(day=1) - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    this_month_start = TODAY.replace(day=1)
    next_month_start = (this_month_start + timedelta(days=32)).replace(day=1)
    this_month_end = next_month_start - timedelta(days=1)

    july = await period(
        prev_month_start.strftime("%B %Y"),
        prev_month_start,
        prev_month_end,
        this_month_start + timedelta(days=4),
    )
    august = await period(
        this_month_start.strftime("%B %Y"),
        this_month_start,
        this_month_end,
        next_month_start + timedelta(days=4),
    )

    from app.models.payroll import PayrollRun

    async def finalized_run() -> None:
        await ctx.payroll_input_svc.prepare(july.id, actor_id=ctx.uid("fatima"))
        run = await ctx.payroll_run_svc.create_run(
            PayrollRunCreate(payroll_period_id=july.id, notes="Regular monthly run (demo)"),
            actor_id=ctx.uid("fatima"),
        )
        await ctx.payroll_run_svc.calculate(run.id, actor_id=ctx.uid("fatima"), recalculation=False)
        for exc in await ctx.payroll_review_svc.list_exceptions(run.id):
            if getattr(exc, "status", "open") == "open":
                from app.schemas.payroll import PayrollExceptionResolve

                await ctx.payroll_review_svc.resolve_exception(
                    run.id,
                    exc.id,
                    PayrollExceptionResolve(resolution="Reviewed and accepted for the demo run.", notes=None),
                    actor_id=ctx.uid("fatima"),
                )
        await ctx.payroll_review_svc.create_adjustment(
            run.id,
            ctx.eid("divya"),
            PayrollAdjustmentCreate(
                item_type=PayrollItemType.EARNING,
                name="Spot bonus",
                amount=Decimal("5000.00"),
                reason="Payments go-live recognition",
            ),
            actor_id=ctx.uid("fatima"),
        )
        await ctx.payroll_review_svc.add_comment(
            run.id,
            ReviewCommentCreate(comment="Attendance reconciled with the register; one spot bonus added."),
            actor_id=ctx.uid("fatima"),
        )
        for item in await ctx.payroll_review_svc.get_checklist(run.id):
            await ctx.payroll_review_svc.update_checklist(
                run.id, item.item_key, ChecklistItemUpdate(completed=True), actor_id=ctx.uid("fatima")
            )
        await ctx.payroll_review_svc.complete_review(run.id, actor_id=ctx.uid("fatima"))
        await ctx.payroll_approval_svc.submit(run.id, actor_id=ctx.uid("fatima"))
        await ctx.payroll_approval_svc.approve(
            run.id,
            PayrollApprovalDecision(comment="Totals verified against the register and last month."),
            actor_id=ctx.uid("ananya"),
        )
        await ctx.payroll_approval_svc.finalize(
            run.id, PayrollFinalizeRequest(comment="Released to the bank file."), actor_id=ctx.uid("ananya")
        )
        await ctx.payslip_svc.generate_for_run(run.id, actor_id=ctx.uid("fatima"))

    if await _one(s, select(PayrollRun).where(PayrollRun.payroll_period_id == july.id)) is None:
        await ctx.step(f"payroll run: {july.name} (finalized + payslips)", finalized_run)

    async def review_run() -> None:
        await ctx.payroll_input_svc.prepare(august.id, actor_id=ctx.uid("fatima"))
        run = await ctx.payroll_run_svc.create_run(
            PayrollRunCreate(payroll_period_id=august.id, notes="In review (demo)"),
            actor_id=ctx.uid("fatima"),
        )
        await ctx.payroll_run_svc.calculate(run.id, actor_id=ctx.uid("fatima"), recalculation=False)
        await ctx.payroll_review_svc.add_comment(
            run.id,
            ReviewCommentCreate(comment="Calculated; waiting on the attendance close for the last week."),
            actor_id=ctx.uid("fatima"),
        )
        checklist = await ctx.payroll_review_svc.get_checklist(run.id)
        for item in checklist[:3]:
            await ctx.payroll_review_svc.update_checklist(
                run.id, item.item_key, ChecklistItemUpdate(completed=True), actor_id=ctx.uid("fatima")
            )

    existing_run = await _one(s, select(PayrollRun).where(PayrollRun.payroll_period_id == august.id))
    if existing_run is None:
        await ctx.step(f"payroll run: {august.name} (in review)", review_run)
    elif existing_run.status in {"calculated", "requires_review", "in_review", "draft"}:

        async def refresh() -> None:
            await ctx.payroll_input_svc.prepare(august.id, actor_id=ctx.uid("fatima"))
            await ctx.payroll_run_svc.calculate(
                existing_run.id, actor_id=ctx.uid("fatima"), recalculation=True
            )

        await ctx.step(f"payroll run: {august.name} (recalculated)", refresh)


# ======================================================================
# 11. Offboarding and full & final settlement for the leaver
# ======================================================================
async def seed_offboarding(ctx: Ctx) -> None:
    s = ctx.session
    from app.models.offboarding import Resignation

    leaver = await ctx.employee(LEAVER)
    if await _one(s, select(Resignation).where(Resignation.employee_id == leaver.id)):
        return

    async def leave_the_company() -> None:
        lwd = date(TODAY.year, 7, 31) if date(TODAY.year, 7, 31) < TODAY else TODAY - timedelta(days=1)
        resignation = await ctx.offboarding_svc.submit_resignation(
            leaver,
            ResignationSubmit(
                resignation_date=lwd - timedelta(days=45),
                proposed_last_working_day=lwd,
                reason="Relocating abroad",
                comments="Moving to Toronto with family. Happy to help with a thorough handover.",
            ),
            actor_id=ctx.uid(LEAVER),
        )
        await ctx.offboarding_svc.manager_decision(
            resignation.id,
            ManagerDecision(decision="approve", comments="Sorry to see you go, Rohan. Approved."),
            actor_id=ctx.uid("vikram"),
            scope=ORG_SCOPE,
        )
        case = await ctx.offboarding_svc.process_resignation(
            resignation.id,
            HrProcess(approved_last_working_day=lwd, comments="Last working day confirmed."),
            actor_id=ctx.uid("ananya"),
        )
        await ctx.offboarding_svc.record_handover(
            case.id,
            HandoverInput(
                status=HandoverStatus.COMPLETED,
                projects="Helix Patient Portal: appointments service and FHIR sync.",
                responsibilities="On-call rota, release manager for the portal.",
                documentation="Runbooks in the wiki under /portal.",
                replacement_employee_id=ctx.eid("pooja"),
                notes="Walkthrough sessions done with Pooja.",
            ),
            actor_id=ctx.uid(LEAVER),
        )
        case = await ctx.offboarding_svc.get_case(case.id)
        for task in case.tasks:
            await ctx.offboarding_svc.update_task(
                task.id,
                OffboardingTaskUpdate(status=OffboardingTaskStatus.COMPLETED, comments="Done."),
                actor_id=ctx.uid("ananya"),
                may_reassign=True,
            )
        for item in getattr(case, "assets", []) or []:
            await ctx.offboarding_svc.update_asset(
                item.id,
                AssetClearanceUpdate(
                    status="returned", return_date=lwd, condition="good", comments="Returned to IT."
                ),
                actor_id=ctx.uid("fatima"),
            )
        for item in getattr(case, "access_items", None) or getattr(case, "access", []) or []:
            await ctx.offboarding_svc.update_access_item(
                item.id, AccessClearanceUpdate(status="revoked"), actor_id=ctx.uid("fatima")
            )
        # The register itself: the laptop comes back.
        from app.models.asset import Asset

        laptop = await _one(s, select(Asset).where(Asset.asset_tag == "DEMO-LT-003"))
        if laptop is not None and laptop.status == "assigned":
            await ctx.asset_svc.process_return(
                laptop.id,
                AssetReturnInput(return_date=lwd, condition_at_return="good", notes="Returned on exit."),
                actor_id=ctx.uid("fatima"),
            )
        await ctx.offboarding_svc.submit_exit_interview(
            leaver,
            ExitInterviewSubmit(
                reason_for_leaving="Relocation",
                overall_experience=4,
                management_rating=5,
                work_environment_rating=4,
                career_growth_rating=4,
                compensation_rating=3,
                management_feedback="Supportive and transparent.",
                suggestions="More structured learning budget.",
                would_recommend=True,
                would_rejoin=True,
            ),
            actor_id=ctx.uid(LEAVER),
        )
        await ctx.offboarding_svc.generate_exit_document(
            case.id,
            ExitDocumentGenerate(document_type=ExitDocumentType.RELIEVING_LETTER, release=True),
            actor_id=ctx.uid("ananya"),
        )
        await ctx.offboarding_svc.generate_exit_document(
            case.id,
            ExitDocumentGenerate(document_type=ExitDocumentType.EXPERIENCE_LETTER, release=True),
            actor_id=ctx.uid("ananya"),
        )

        # Full & final settlement while the case is still in progress.
        settlement = await ctx.settlement_svc.create(case.id, actor_id=ctx.uid("fatima"))
        settlement = await ctx.settlement_svc.add_adjustment(
            settlement.id,
            SettlementAdjustmentCreate(
                adjustment_type=SettlementAdjustmentType.LEAVE_ENCASHMENT,
                name="Earned leave encashment",
                amount=Decimal("24000.00"),
                reason="12 days of unused earned leave",
            ),
            actor_id=ctx.uid("fatima"),
        )
        for adjustment in settlement.adjustments:
            if adjustment.status == "pending":
                await ctx.settlement_svc.decide_adjustment(
                    settlement.id,
                    adjustment.id,
                    SettlementAdjustmentDecision(approve=True, note="Verified against the leave register."),
                    actor_id=ctx.uid("ananya"),
                )
        await ctx.settlement_svc.submit(settlement.id, actor_id=ctx.uid("fatima"))
        await ctx.settlement_svc.complete_review(settlement.id, actor_id=ctx.uid("fatima"))
        await ctx.settlement_svc.approve(
            settlement.id,
            SettlementApproval(comment="All clearances complete; settlement approved."),
            actor_id=ctx.uid("ananya"),
        )
        await ctx.settlement_svc.finalize(
            settlement.id,
            SettlementFinalize(settlement_reference=f"FNF-{lwd:%Y%m}-ROHAN"),
            actor_id=ctx.uid("fatima"),
        )

        await ctx.offboarding_svc.complete_case(
            case.id,
            CaseCompletion(comments="All clearances done; settlement paid.", force=True),
            actor_id=ctx.uid("ananya"),
            may_force=True,
        )

    await ctx.step("offboarding + final settlement: rohan", leave_the_company)


# ======================================================================
# Orchestration
# ======================================================================
async def run() -> None:
    configure_logging()
    async with session_scope() as session:
        admin = await _one(
            session, select(User).where(User.email == normalise_email(settings.DEFAULT_ADMIN_EMAIL))
        )
        if admin is None:
            raise RuntimeError(
                "The bootstrap administrator does not exist. Run `python -m app.cli.seed` first."
            )
        ctx = Ctx(session=session, admin=admin)

        for label, section in (
            ("masters", seed_masters),
            ("people", seed_people),
            ("documents", seed_documents),
            ("workforce", seed_workforce),
            ("projects", seed_projects),
            ("performance", seed_performance),
            ("recruitment", seed_recruitment),
            ("assets", seed_assets),
            ("helpdesk", seed_helpdesk),
            ("payroll", seed_payroll),
            ("offboarding", seed_offboarding),
        ):
            logger.info("Seeding %s ...", label)
            await section(ctx)

    print("\nDemo data seeded.")
    print(f"  steps completed : {len(ctx.done)}")
    print(f"  steps skipped   : {len(ctx.skipped)}")
    for name, reason in ctx.skipped[:40]:
        print(f"    - {name}: {reason}")
    if len(ctx.skipped) > 40:
        print(f"    ... and {len(ctx.skipped) - 40} more")
    print(f"\nSign-ins (password for all: {DEMO_PASSWORD})")
    for p in PEOPLE:
        print(f"  {p.email:40} {p.role:16} {p.first} {p.last}, {p.designation}")
    if "aisha" in ctx.people:
        print(f"  {ctx.people['aisha'].email:40} {'employee':16} Aisha Sheikh (joiner, preboarding portal)")


def main() -> int:
    try:
        asyncio.run(run())
    except SQLAlchemyError:
        logger.error("Demo seeding failed. Is the database running and migrated?", exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
