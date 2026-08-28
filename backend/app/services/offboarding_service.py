"""Resignation and offboarding business logic.

Four rules shape this module.

**The employee is never a parameter on the way in.** Every self-service entry
point takes the employee resolved from the access token and nothing else. There
is no ``employee_id`` on :class:`ResignationSubmit` or
:class:`ExitInterviewSubmit` to validate, ignore or forget to check -- which is
what makes submitting somebody else's resignation a thing that cannot be
expressed rather than a thing a guard has to catch.

**Approving and processing are different acts by different people.** A manager
approves a resignation from their own direct report; HR then processes it --
verifies the notice period, settles the last working day, opens the case.
``resignation:approve`` and ``resignation:process`` exist separately for exactly
this reason, and HR Admin deliberately holds the second and not the first.

**The notice period is resolved once and then owned by the record.** It is read
from the employment type when the resignation is submitted and copied onto the
row. A policy change six weeks into somebody's notice must not silently move
their last working day, and reading it live would do precisely that. An
authorized adjustment is a deliberate write, and it is recorded in history with
the reason.

**Nothing is deleted, and completion is not deletion.** An exit sets the
employee inactive and ends their live allocations. Their attendance, leave,
timesheets, projects, performance and documents stay exactly where they were,
because the question "what did this person do here" outlives their employment
by years.

What this module deliberately does *not* do: calculate anything financial. Full
& final is a status and a reference number. No salary, tax, PF, ESI or gratuity
figure is computed here, and none should be until there is a payroll module
entitled to compute it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.models.audit_log import AuditAction
from app.models.document import Document, DocumentVersion
from app.models.document_category import DocumentCategory, DocumentType
from app.models.employee import Employee
from app.models.employment_type import EmploymentType
from app.models.enums import (
    ACTIVE_OFFBOARDING_STATUSES,
    DEFAULT_NOTICE_PERIOD_DAYS,
    SETTLED_ACCESS_STATUSES,
    SETTLED_ASSET_STATUSES,
    SETTLED_TASK_STATUSES,
    TERMINAL_RESIGNATION_STATUSES,
    WITHDRAWABLE_RESIGNATION_STATUSES,
    AccessClearanceStatus,
    AssetReturnStatus,
    EmploymentStatus,
    ExitDocumentType,
    HandoverStatus,
    OffboardingCaseStatus,
    OffboardingDepartment,
    RecordStatus,
    ResignationStatus,
    SettlementStatus,
)
from app.models.offboarding import (
    AccessClearance,
    AssetClearance,
    ExitDocument,
    ExitInterview,
    FinalSettlementTracking,
    HandoverRecord,
    OffboardingCase,
    OffboardingTask,
    Resignation,
    ResignationHistory,
)
from app.models.project import EmployeeAllocation
from app.models.requisition import Notification
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.offboarding_repository import (
    AccessClearanceRepository,
    AssetClearanceRepository,
    ExitDocumentRepository,
    ExitInterviewRepository,
    HandoverRepository,
    OffboardingAnalyticsRepository,
    OffboardingCaseRepository,
    OffboardingTaskRepository,
    ResignationHistoryRepository,
    ResignationRepository,
    SettlementRepository,
)
from app.repositories.requisition_repository import NotificationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.offboarding import (
    AccessClearanceInput,
    AccessClearanceRead,
    AccessClearanceUpdate,
    AssetClearanceInput,
    AssetClearanceRead,
    AssetClearanceUpdate,
    CaseCompletion,
    ClearanceProgress,
    EmployeeSummary,
    ExitDocumentGenerate,
    ExitDocumentRead,
    ExitInterviewListItem,
    ExitInterviewSubmit,
    HandoverInput,
    HandoverRead,
    HrProcess,
    LastWorkingDayChange,
    ManagerDecision,
    MyOffboarding,
    MyPendingAction,
    MyResignation,
    NoticePeriodView,
    OffboardingCaseRead,
    OffboardingListParams,
    OffboardingSummary,
    OffboardingTaskCreate,
    OffboardingTaskRead,
    OffboardingTaskUpdate,
    ResignationCancel,
    ResignationHistoryEntry,
    ResignationListParams,
    ResignationRead,
    ResignationSubmit,
    ResignationWithdraw,
    SettlementRead,
    SettlementUpdate,
)
from app.services.asset_service import AssetService
from app.services.audit_service import AuditService
from app.services.scope_service import EmployeeScope, visible_employee_ids
from app.storage import StorageBackend
from app.utils.datetime import utc_now

logger = get_logger("services.offboarding")

#: The checklist a new case opens with. Configurable in the sense that matters:
#: HR adds, edits, reassigns and waives rows on a live case, and these are the
#: rows it starts from rather than the rows it is limited to.
#:
#: ``offset`` is days *before* the last working day the row is due. IT and Admin
#: land on the day itself -- revoking a laptop a week early is not a clearance
#: process, it is a person unable to do their job -- while handover and the
#: exit interview are deliberately earlier, because both are worthless if they
#: happen on somebody's way out of the door.
DEFAULT_TASKS: tuple[tuple[OffboardingDepartment, str, int], ...] = (
    (OffboardingDepartment.HR, "Verify resignation", 21),
    (OffboardingDepartment.HR, "Confirm last working day", 21),
    (OffboardingDepartment.HR, "Conduct exit interview", 5),
    (OffboardingDepartment.HR, "Final clearance", 0),
    (OffboardingDepartment.HR, "Generate exit documents", 0),
    (OffboardingDepartment.MANAGER, "Knowledge transfer", 10),
    (OffboardingDepartment.MANAGER, "Project handover", 10),
    (OffboardingDepartment.MANAGER, "Documentation handover", 7),
    (OffboardingDepartment.MANAGER, "Team transition", 7),
    (OffboardingDepartment.IT, "Disable official email", 0),
    (OffboardingDepartment.IT, "Disable system access", 0),
    (OffboardingDepartment.IT, "Revoke application access", 0),
    (OffboardingDepartment.IT, "Collect laptop", 0),
    (OffboardingDepartment.IT, "Collect accessories", 0),
    (OffboardingDepartment.ADMIN, "Collect ID card", 0),
    (OffboardingDepartment.ADMIN, "Collect access card", 0),
    (OffboardingDepartment.ADMIN, "Collect company property", 0),
    (OffboardingDepartment.ADMIN, "Confirm asset clearance", 0),
    (OffboardingDepartment.FINANCE, "Final settlement status", -7),
    (OffboardingDepartment.FINANCE, "Expense clearance", 0),
    (OffboardingDepartment.FINANCE, "Pending reimbursements", 0),
)

#: Property a case starts by asking about when the asset register has nothing
#: recorded for the person. The register (Phase 19) seeds the clearance list
#: with what it actually holds; this generic checklist is the fallback for an
#: employee nothing was ever issued to, and ``waived`` is the answer for
#: anything the person never held.
DEFAULT_ASSETS: tuple[str, ...] = (
    "Laptop",
    "Monitor",
    "Mobile",
    "ID Card",
    "Access Card",
    "Accessories",
)

#: system, category.
DEFAULT_ACCESS_ITEMS: tuple[tuple[str, str], ...] = (
    ("Official email", "email"),
    ("VPN", "vpn"),
    ("Business applications", "application"),
    ("Cloud accounts", "cloud"),
    ("Internal systems", "internal"),
)

_EXIT_DOCUMENT_TITLES: dict[ExitDocumentType, str] = {
    ExitDocumentType.EXPERIENCE_LETTER: "Experience Letter",
    ExitDocumentType.RELIEVING_LETTER: "Relieving Letter",
    ExitDocumentType.SERVICE_CERTIFICATE: "Service Certificate",
}

_EXIT_DOCUMENT_CATEGORY_CODE = "EXIT"
_EXIT_DOCUMENT_TYPE_CODE = "EXITDOC"


class OffboardingService:
    """The separation lifecycle, from an employee's resignation to their exit."""

    def __init__(
        self,
        resignations: ResignationRepository,
        history: ResignationHistoryRepository,
        cases: OffboardingCaseRepository,
        tasks: OffboardingTaskRepository,
        handovers: HandoverRepository,
        assets: AssetClearanceRepository,
        access: AccessClearanceRepository,
        interviews: ExitInterviewRepository,
        documents: ExitDocumentRepository,
        settlements: SettlementRepository,
        analytics: OffboardingAnalyticsRepository,
        employees: EmployeeRepository,
        audit: AuditService,
        notifications: NotificationRepository,
        storage: StorageBackend,
        asset_register: AssetService | None = None,
        users: UserRepository | None = None,
    ) -> None:
        self.resignations = resignations
        self.history = history
        self.cases = cases
        self.tasks = tasks
        self.handovers = handovers
        self.assets = assets
        self.access = access
        self.interviews = interviews
        self.documents = documents
        self.settlements = settlements
        self.analytics = analytics
        self.employees = employees
        # Optional in the established style, so unit tests can build the
        # service without it -- but the wired product always passes it: an
        # exit that leaves the login working is a door nobody remembered.
        self.users = users
        self.audit = audit
        self.notifications = notifications
        self.storage = storage
        # Optional so the seeder and the unit tests can build this service
        # without the asset module. Absent, the clearance falls back to the
        # generic checklist it used before the register existed.
        self.asset_register = asset_register
        self.session = resignations.session

    # ==================================================================
    # Employee self-service
    # ==================================================================
    async def submit_resignation(
        self, employee: Employee, payload: ResignationSubmit, *, actor_id: uuid.UUID
    ) -> Resignation:
        """Submit the caller's own resignation.

        ``employee`` is the record behind the access token. Nothing in
        ``payload`` names a person, so there is no id here to trust or distrust.
        """
        if not employee.is_employed:
            raise ConflictError(
                "Your employment record is not active, so a resignation cannot be submitted.",
                error_code="employee_not_active",
            )
        existing = await self.resignations.live_for_employee(employee.id)
        if existing is not None:
            raise ConflictError(
                f"You already have a resignation in progress ({existing.resignation_code}). "
                "Withdraw it before submitting another.",
                error_code="resignation_in_progress",
            )

        notice_days = await self._resolve_notice_days(employee)
        manager_id = employee.reporting_manager_id

        resignation = await self.resignations.add(
            Resignation(
                employee_id=employee.id,
                resignation_date=payload.resignation_date,
                proposed_last_working_day=payload.proposed_last_working_day,
                notice_period_days=notice_days,
                reason=payload.reason,
                comments=payload.comments,
                supporting_document_id=payload.supporting_document_id,
                # Straight to the manager when there is one. An employee with no
                # reporting manager -- a founder, a contractor reporting to
                # nobody -- would otherwise sit in a queue nobody owns, so their
                # resignation goes to HR directly.
                status=(
                    ResignationStatus.MANAGER_REVIEW if manager_id else ResignationStatus.HR_REVIEW
                ).value,
                manager_id=manager_id,
                submitted_at=utc_now(),
            ),
            actor_id=actor_id,
        )
        await self._record_history(
            resignation,
            action="submitted",
            from_status=ResignationStatus.DRAFT,
            to_status=ResignationStatus(resignation.status),
            comments=payload.comments,
            actor_id=actor_id,
        )
        await self._audit(
            AuditAction.RESIGNATION_SUBMITTED,
            resignation,
            actor_id=actor_id,
            description=f"Resignation {resignation.resignation_code} submitted",
        )

        await self._notify_user(
            employee.user_id,
            "Resignation submitted",
            f"{resignation.resignation_code} is with "
            f"{'your manager' if manager_id else 'HR'} for review.",
            resignation,
            actor_id,
        )
        if manager_id:
            await self._notify_employee(
                manager_id,
                "Resignation submitted",
                f"{employee.full_name} has resigned. {resignation.resignation_code} needs your review.",
                resignation,
                actor_id,
            )
        logger.info(
            "Resignation submitted",
            extra={"resignation_id": str(resignation.id), "employee_id": str(employee.id)},
        )
        return await self._reload_resignation(resignation.id)

    async def withdraw_resignation(
        self, employee: Employee, payload: ResignationWithdraw, *, actor_id: uuid.UUID
    ) -> Resignation:
        """An employee takes their own resignation back, before it is approved."""
        resignation = await self.resignations.live_for_employee(employee.id)
        if resignation is None:
            raise NotFoundError("Resignation")
        if resignation.employee_id != employee.id:  # pragma: no cover - defensive
            raise PermissionDeniedError("You can only withdraw your own resignation.")

        status = ResignationStatus(resignation.status)
        if status not in WITHDRAWABLE_RESIGNATION_STATUSES:
            raise ConflictError(
                "A resignation can only be withdrawn before it is approved. " "Ask HR to cancel it instead.",
                error_code="not_withdrawable",
            )

        await self.resignations.update(
            resignation, {"status": ResignationStatus.WITHDRAWN.value}, actor_id=actor_id
        )
        await self._record_history(
            resignation,
            action="withdrawn",
            from_status=status,
            to_status=ResignationStatus.WITHDRAWN,
            comments=payload.comments,
            actor_id=actor_id,
        )
        await self._audit(
            AuditAction.RESIGNATION_WITHDRAWN,
            resignation,
            actor_id=actor_id,
            description=f"Resignation {resignation.resignation_code} withdrawn by the employee",
        )
        if resignation.manager_id:
            await self._notify_employee(
                resignation.manager_id,
                "Resignation withdrawn",
                f"{employee.full_name} has withdrawn {resignation.resignation_code}.",
                resignation,
                actor_id,
            )
        return await self._reload_resignation(resignation.id)

    async def my_resignation(self, employee: Employee) -> Resignation | None:
        """The caller's live resignation, or the most recent one if it is over."""
        live = await self.resignations.live_for_employee(employee.id)
        return live if live is not None else await self.resignations.latest_for_employee(employee.id)

    async def submit_exit_interview(
        self, employee: Employee, payload: ExitInterviewSubmit, *, actor_id: uuid.UUID
    ) -> ExitInterview:
        """The employee's own exit interview. One per case, written once."""
        case = await self._case_for_employee(employee.id)
        if case is None:
            raise ConflictError(
                "An exit interview becomes available once your resignation has been approved.",
                error_code="no_offboarding_case",
            )
        existing = await self.interviews.for_case(case.id)
        if existing is not None and existing.submitted_at is not None:
            raise ConflictError(
                "Your exit interview has already been submitted.", error_code="already_submitted"
            )

        interview = await self.interviews.add(
            ExitInterview(
                case_id=case.id,
                employee_id=employee.id,
                submitted_at=utc_now(),
                **payload.model_dump(),
            ),
            actor_id=actor_id,
        )
        await self._audit(
            AuditAction.EXIT_INTERVIEW_SUBMITTED,
            None,
            actor_id=actor_id,
            entity_type="offboarding_case",
            entity_id=case.id,
            description=f"Exit interview submitted for {case.case_code}",
        )
        await self._advance_case_status(case, ResignationStatus.EXIT_INTERVIEW, actor_id=actor_id)
        if case.hr_owner_id:
            await self._notify_user(
                case.hr_owner_id,
                "Exit interview submitted",
                f"{employee.full_name} has completed their exit interview.",
                None,
                actor_id,
                link=f"/hr/offboarding/{case.id}",
            )
        return interview

    async def my_exit_interview(self, employee: Employee) -> ExitInterview | None:
        case = await self._case_for_employee(employee.id)
        return None if case is None else await self.interviews.for_case(case.id)

    async def my_exit_documents(self, employee: Employee) -> Sequence[ExitDocument]:
        """Only what has been released. A generated-but-unreleased letter is HR's."""
        issued = await self.documents.for_employee(employee.id)
        return [document for document in issued if document.released]

    # ==================================================================
    # Reads: manager, HR and admin
    # ==================================================================
    async def list_resignations(
        self, params: ResignationListParams, *, scope: EmployeeScope | None = None
    ) -> tuple[Sequence[Resignation], int]:
        return await self.resignations.search(params, visible_ids=visible_employee_ids(scope))

    async def get_resignation(
        self, resignation_id: uuid.UUID, *, scope: EmployeeScope | None = None
    ) -> Resignation:
        resignation = await self.resignations.get_detailed(resignation_id)
        if resignation is None:
            raise NotFoundError("Resignation")
        if scope is not None:
            scope.assert_allows(resignation.employee_id)
        return resignation

    async def list_cases(
        self, params: OffboardingListParams, *, scope: EmployeeScope | None = None
    ) -> tuple[Sequence[OffboardingCase], int]:
        return await self.cases.search(params, visible_ids=visible_employee_ids(scope))

    async def get_case(self, case_id: uuid.UUID, *, scope: EmployeeScope | None = None) -> OffboardingCase:
        case = await self.cases.get_detailed(case_id)
        if case is None:
            raise NotFoundError("Offboarding case")
        if scope is not None:
            scope.assert_allows(case.employee_id)
        return case

    # ==================================================================
    # Manager
    # ==================================================================
    async def manager_decision(
        self,
        resignation_id: uuid.UUID,
        payload: ManagerDecision,
        *,
        actor_id: uuid.UUID,
        scope: EmployeeScope,
    ) -> Resignation:
        """Approve or reject a direct report's resignation.

        ``scope`` here is the *manager* scope -- direct reports and not the
        caller -- so a manager approving their own resignation is refused by the
        same check that keeps them out of another team's, rather than by a rule
        somebody had to remember to add.
        """
        resignation = await self.resignations.get_detailed(resignation_id)
        if resignation is None:
            raise NotFoundError("Resignation")
        scope.assert_allows(resignation.employee_id)

        status = ResignationStatus(resignation.status)
        if status is not ResignationStatus.MANAGER_REVIEW:
            raise ConflictError(
                f"This resignation is {status.value.replace('_', ' ')} and is not awaiting your review.",
                error_code="not_awaiting_manager",
            )

        approved = payload.decision == "approve"
        target = ResignationStatus.HR_REVIEW if approved else ResignationStatus.REJECTED
        values: dict[str, Any] = {
            "status": target.value,
            "manager_decided_at": utc_now(),
            "manager_comments": payload.comments,
        }
        if approved and payload.recommended_last_working_day is not None:
            values["recommended_last_working_day"] = payload.recommended_last_working_day
        await self.resignations.update(resignation, values, actor_id=actor_id)

        await self._record_history(
            resignation,
            action=f"manager_{payload.decision}d",
            from_status=status,
            to_status=target,
            comments=payload.comments,
            actor_id=actor_id,
        )
        await self._audit(
            AuditAction.RESIGNATION_MANAGER_DECIDED,
            resignation,
            actor_id=actor_id,
            description=f"Manager {payload.decision}d {resignation.resignation_code}",
            context={"decision": payload.decision},
        )

        employee = await self.employees.get(resignation.employee_id)
        await self._notify_user(
            employee.user_id if employee else None,
            f"Resignation {'approved by your manager' if approved else 'rejected'}",
            payload.comments or f"{resignation.resignation_code} has been reviewed.",
            resignation,
            actor_id,
        )
        return await self._reload_resignation(resignation.id)

    async def record_handover(
        self,
        case_id: uuid.UUID,
        payload: HandoverInput,
        *,
        actor_id: uuid.UUID,
        scope: EmployeeScope | None = None,
    ) -> HandoverRecord:
        """The manager's knowledge-transfer record. One per case, updated in place."""
        case = await self.get_case(case_id, scope=scope)
        record = await self.handovers.for_case(case.id)
        values = payload.model_dump()
        values["attachment_ids"] = [str(item) for item in payload.attachment_ids]
        if payload.status is HandoverStatus.COMPLETED:
            values["completed_at"] = utc_now()

        if record is None:
            record = await self.handovers.add(HandoverRecord(case_id=case.id, **values), actor_id=actor_id)
        else:
            await self.handovers.update(record, values, actor_id=actor_id)

        await self._audit(
            AuditAction.OFFBOARDING_HANDOVER_RECORDED,
            None,
            actor_id=actor_id,
            entity_type="offboarding_case",
            entity_id=case.id,
            description=f"Handover recorded for {case.case_code}",
            context={"status": payload.status.value},
        )
        await self._recalculate(case, actor_id=actor_id)
        return record

    # ==================================================================
    # HR
    # ==================================================================
    async def process_resignation(
        self, resignation_id: uuid.UUID, payload: HrProcess, *, actor_id: uuid.UUID
    ) -> OffboardingCase:
        """HR's step: settle the last working day and open the offboarding case.

        Organization-wide by design -- the route is guarded by
        ``resignation:process``, which is not a permission any team-scoped seat
        holds -- so no scope is applied here.
        """
        resignation = await self.resignations.get_detailed(resignation_id)
        if resignation is None:
            raise NotFoundError("Resignation")

        status = ResignationStatus(resignation.status)
        if status is not ResignationStatus.HR_REVIEW:
            raise ConflictError(
                f"This resignation is {status.value.replace('_', ' ')} and is not awaiting HR review.",
                error_code="not_awaiting_hr",
            )
        if await self.cases.for_resignation(resignation.id) is not None:
            raise ConflictError(
                "An offboarding case already exists for this resignation.", error_code="case_exists"
            )

        employee = await self.employees.get(resignation.employee_id)
        if employee is None:
            raise NotFoundError("Employee")

        last_working_day = (
            payload.approved_last_working_day
            or resignation.recommended_last_working_day
            or resignation.proposed_last_working_day
        )
        if last_working_day < resignation.resignation_date:
            raise ConflictError(
                "The last working day cannot be before the resignation date.",
                error_code="invalid_last_working_day",
            )

        notice_days = resignation.notice_period_days
        adjusted = False
        if payload.notice_period_days is not None and payload.notice_period_days != notice_days:
            if not payload.adjustment_reason:
                raise ConflictError(
                    "A notice-period adjustment needs a reason.", error_code="adjustment_reason_required"
                )
            notice_days = payload.notice_period_days
            adjusted = True

        await self.resignations.update(
            resignation,
            {
                "status": ResignationStatus.APPROVED.value,
                "approved_last_working_day": last_working_day,
                "notice_period_days": notice_days,
                "notice_period_adjusted": adjusted or resignation.notice_period_adjusted,
                "hr_owner_id": actor_id,
                "hr_processed_at": utc_now(),
                "hr_comments": payload.comments,
            },
            actor_id=actor_id,
        )
        await self._record_history(
            resignation,
            action="hr_processed",
            from_status=status,
            to_status=ResignationStatus.APPROVED,
            comments=payload.comments,
            actor_id=actor_id,
        )
        if adjusted:
            await self._record_history(
                resignation,
                action="notice_period_adjusted",
                from_status=ResignationStatus.APPROVED,
                to_status=ResignationStatus.APPROVED,
                comments=f"{resignation.notice_period_days} -> {notice_days} days: "
                f"{payload.adjustment_reason}",
                actor_id=actor_id,
                is_override=True,
            )
            await self._audit(
                AuditAction.NOTICE_PERIOD_ADJUSTED,
                resignation,
                actor_id=actor_id,
                description=f"Notice period adjusted to {notice_days} days",
                context={"reason": payload.adjustment_reason, "days": notice_days},
            )

        case = await self._open_case(resignation, employee, last_working_day, notice_days, actor_id)

        # The employee is serving notice from here: still employed, still on
        # every screen, and visibly on their way out.
        await self._set_employment_status(employee, EmploymentStatus.NOTICE_PERIOD, actor_id=actor_id)

        await self._audit(
            AuditAction.RESIGNATION_PROCESSED,
            resignation,
            actor_id=actor_id,
            description=f"Resignation {resignation.resignation_code} processed; case {case.case_code} opened",
        )
        await self._notify_user(
            employee.user_id,
            "Resignation approved",
            f"Your last working day is {last_working_day.isoformat()}. "
            f"Offboarding case {case.case_code} has been opened.",
            resignation,
            actor_id,
        )
        if resignation.manager_id:
            await self._notify_employee(
                resignation.manager_id,
                "Handover pending",
                f"{employee.full_name} leaves on {last_working_day.isoformat()}. "
                "Please record the knowledge transfer.",
                resignation,
                actor_id,
            )
        return await self._reload_case(case.id)

    async def change_last_working_day(
        self,
        resignation_id: uuid.UUID,
        payload: LastWorkingDayChange,
        *,
        actor_id: uuid.UUID,
        is_override: bool = False,
    ) -> Resignation:
        """Move a settled last working day. Always recorded, with the reason."""
        resignation = await self.resignations.get_detailed(resignation_id)
        if resignation is None:
            raise NotFoundError("Resignation")
        if ResignationStatus(resignation.status) in TERMINAL_RESIGNATION_STATUSES:
            raise ConflictError(
                "This separation is closed and its last working day cannot be changed.",
                error_code="resignation_closed",
            )
        if payload.approved_last_working_day < resignation.resignation_date:
            raise ConflictError(
                "The last working day cannot be before the resignation date.",
                error_code="invalid_last_working_day",
            )

        previous = resignation.approved_last_working_day
        await self.resignations.update(
            resignation, {"approved_last_working_day": payload.approved_last_working_day}, actor_id=actor_id
        )
        case = await self.cases.for_resignation(resignation.id)
        if case is not None:
            await self.cases.update(
                case, {"last_working_day": payload.approved_last_working_day}, actor_id=actor_id
            )

        await self._record_history(
            resignation,
            action="last_working_day_changed",
            from_status=ResignationStatus(resignation.status),
            to_status=ResignationStatus(resignation.status),
            comments=f"{previous.isoformat() if previous else 'unset'} -> "
            f"{payload.approved_last_working_day.isoformat()}: {payload.reason}",
            actor_id=actor_id,
            is_override=is_override,
        )
        await self._audit(
            AuditAction.LAST_WORKING_DAY_CHANGED,
            resignation,
            actor_id=actor_id,
            description=f"Last working day changed to {payload.approved_last_working_day.isoformat()}",
            context={"reason": payload.reason, "override": is_override},
        )
        if is_override:
            await self._audit_override(
                resignation.id,
                actor_id,
                f"Last working day overridden to {payload.approved_last_working_day.isoformat()}",
                payload.reason,
            )

        employee = await self.employees.get(resignation.employee_id)
        await self._notify_user(
            employee.user_id if employee else None,
            "Last working day updated",
            f"Your last working day is now {payload.approved_last_working_day.isoformat()}.",
            resignation,
            actor_id,
        )
        return await self._reload_resignation(resignation.id)

    async def cancel_resignation(
        self,
        resignation_id: uuid.UUID,
        payload: ResignationCancel,
        *,
        actor_id: uuid.UUID,
        is_override: bool = False,
    ) -> Resignation:
        """Cancel an approved separation and put the employee back to work.

        Distinct from an employee's withdrawal: this reverses a decision that
        has already been taken, so it cancels the case with it and restores the
        employment status that the notice period replaced.
        """
        resignation = await self.resignations.get_detailed(resignation_id)
        if resignation is None:
            raise NotFoundError("Resignation")
        status = ResignationStatus(resignation.status)
        if status in TERMINAL_RESIGNATION_STATUSES:
            raise ConflictError("This separation is already closed.", error_code="resignation_closed")

        await self.resignations.update(
            resignation, {"status": ResignationStatus.CANCELLED.value}, actor_id=actor_id
        )
        case = await self.cases.for_resignation(resignation.id)
        if case is not None:
            await self.cases.update(
                case, {"status": OffboardingCaseStatus.CANCELLED.value}, actor_id=actor_id
            )

        employee = await self.employees.get(resignation.employee_id)
        if employee is not None and employee.employment_status == EmploymentStatus.NOTICE_PERIOD.value:
            await self._set_employment_status(employee, EmploymentStatus.ACTIVE, actor_id=actor_id)

        await self._record_history(
            resignation,
            action="cancelled",
            from_status=status,
            to_status=ResignationStatus.CANCELLED,
            comments=payload.reason,
            actor_id=actor_id,
            is_override=is_override,
        )
        await self._audit(
            AuditAction.RESIGNATION_CANCELLED,
            resignation,
            actor_id=actor_id,
            description=f"Resignation {resignation.resignation_code} cancelled",
            context={"reason": payload.reason, "override": is_override},
        )
        if is_override:
            await self._audit_override(resignation.id, actor_id, "Separation cancelled", payload.reason)
        await self._notify_user(
            employee.user_id if employee else None,
            "Resignation cancelled",
            payload.reason,
            resignation,
            actor_id,
        )
        return await self._reload_resignation(resignation.id)

    # ==================================================================
    # The checklist and clearance
    # ==================================================================
    async def update_task(
        self,
        task_id: uuid.UUID,
        payload: OffboardingTaskUpdate,
        *,
        actor_id: uuid.UUID,
        scope: EmployeeScope | None = None,
        may_reassign: bool = False,
    ) -> OffboardingTask:
        """Tick, comment on or reschedule one checklist row.

        ``may_reassign`` is the caller's ``offboarding:manage``. Reassigning a
        row is administration rather than doing the work, so a manager who can
        complete their own task cannot hand it to somebody else.
        """
        task = await self.tasks.get(task_id)
        if task is None:
            raise NotFoundError("Offboarding task")
        case = await self.get_case(task.case_id, scope=scope)

        values = payload.model_dump(exclude_unset=True)
        if "owner_id" in values and not may_reassign:
            raise PermissionDeniedError(
                "Reassigning a task needs offboarding:manage.",
                details=[{"code": "reassign_not_permitted", "message": "owner_id"}],
            )
        if payload.status is not None:
            values["status"] = payload.status.value
            values["completed_at"] = utc_now() if payload.status in SETTLED_TASK_STATUSES else None
        await self.tasks.update(task, values, actor_id=actor_id)

        await self._audit(
            AuditAction.OFFBOARDING_TASK_UPDATED,
            None,
            actor_id=actor_id,
            entity_type="offboarding_task",
            entity_id=task.id,
            description=f"Task '{task.title}' updated on {case.case_code}",
            context={"status": task.status},
        )
        await self._recalculate(case, actor_id=actor_id)
        return task

    async def add_task(
        self, case_id: uuid.UUID, payload: OffboardingTaskCreate, *, actor_id: uuid.UUID
    ) -> OffboardingTask:
        case = await self.get_case(case_id)
        task = await self.tasks.add(
            OffboardingTask(
                case_id=case.id,
                title=payload.title,
                department=payload.department.value,
                owner_id=payload.owner_id,
                due_date=payload.due_date,
                sequence=len(case.tasks) + 1,
            ),
            actor_id=actor_id,
        )
        await self._recalculate(case, actor_id=actor_id)
        return task

    async def add_asset(
        self, case_id: uuid.UUID, payload: AssetClearanceInput, *, actor_id: uuid.UUID
    ) -> AssetClearance:
        case = await self.get_case(case_id)
        asset = await self.assets.add(
            AssetClearance(case_id=case.id, **payload.model_dump()), actor_id=actor_id
        )
        await self._recalculate(case, actor_id=actor_id)
        return asset

    async def update_asset(
        self, asset_id: uuid.UUID, payload: AssetClearanceUpdate, *, actor_id: uuid.UUID
    ) -> AssetClearance:
        asset = await self.assets.get(asset_id)
        if asset is None:
            raise NotFoundError("Asset clearance record")
        case = await self.get_case(asset.case_id)

        values = payload.model_dump(exclude_unset=True)
        values["status"] = payload.status.value
        if payload.status is AssetReturnStatus.RETURNED and payload.return_date is None:
            values["return_date"] = date.today()
        await self.assets.update(asset, values, actor_id=actor_id)

        # The register is the system of record for the thing itself. Marking a
        # laptop returned here has to make it available there, or the two
        # disagree the moment somebody tries to issue it to the next joiner.
        # Rows with no `asset_id` are hand-entered lines and have nothing to
        # update, which is why the link is checked rather than assumed.
        if asset.asset_id is not None and self.asset_register is not None:
            await self.asset_register.resolve_from_clearance(
                asset.asset_id,
                case.employee_id,
                payload.status.value,
                actor_id=actor_id,
                notes=payload.comments,
            )

        await self._audit(
            AuditAction.OFFBOARDING_ASSET_UPDATED,
            None,
            actor_id=actor_id,
            entity_type="offboarding_case",
            entity_id=case.id,
            description=f"Asset '{asset.asset_name}' marked {payload.status.value} on {case.case_code}",
        )
        await self._recalculate(case, actor_id=actor_id)
        return asset

    async def add_access_item(
        self, case_id: uuid.UUID, payload: AccessClearanceInput, *, actor_id: uuid.UUID
    ) -> AccessClearance:
        case = await self.get_case(case_id)
        item = await self.access.add(
            AccessClearance(case_id=case.id, **payload.model_dump()), actor_id=actor_id
        )
        await self._recalculate(case, actor_id=actor_id)
        return item

    async def update_access_item(
        self, item_id: uuid.UUID, payload: AccessClearanceUpdate, *, actor_id: uuid.UUID
    ) -> AccessClearance:
        item = await self.access.get(item_id)
        if item is None:
            raise NotFoundError("Access clearance record")
        case = await self.get_case(item.case_id)

        await self.access.update(
            item,
            {
                "status": payload.status.value,
                "comments": payload.comments,
                "revoked_at": utc_now() if payload.status is AccessClearanceStatus.REVOKED else None,
            },
            actor_id=actor_id,
        )
        await self._audit(
            AuditAction.OFFBOARDING_ACCESS_UPDATED,
            None,
            actor_id=actor_id,
            entity_type="offboarding_case",
            entity_id=case.id,
            description=f"Access '{item.system_name}' marked {payload.status.value} on {case.case_code}",
        )
        await self._recalculate(case, actor_id=actor_id)
        return item

    async def update_settlement(
        self, case_id: uuid.UUID, payload: SettlementUpdate, *, actor_id: uuid.UUID
    ) -> FinalSettlementTracking:
        """Status tracking only. Nothing financial is computed here."""
        case = await self.get_case(case_id)
        record = await self.settlements.for_case(case.id)
        if record is None:
            record = await self.settlements.add(FinalSettlementTracking(case_id=case.id), actor_id=actor_id)
        await self.settlements.update(
            record,
            {
                "status": payload.status.value,
                "settlement_reference": payload.settlement_reference,
                "settlement_date": payload.settlement_date,
                "comments": payload.comments,
            },
            actor_id=actor_id,
        )
        await self._audit(
            AuditAction.SETTLEMENT_STATUS_UPDATED,
            None,
            actor_id=actor_id,
            entity_type="offboarding_case",
            entity_id=case.id,
            description=f"Settlement status set to {payload.status.value} on {case.case_code}",
        )
        return record

    # ==================================================================
    # Exit documents
    # ==================================================================
    async def generate_exit_document(
        self, case_id: uuid.UUID, payload: ExitDocumentGenerate, *, actor_id: uuid.UUID
    ) -> ExitDocument:
        """Render a letter, file it in the Document Vault, record that it exists.

        The PDF goes through the same storage backend and the same
        ``documents`` / ``document_versions`` pair as every other file in the
        platform -- the offer module's ``generate_pdf`` does exactly this, and
        duplicating vault mechanics here would give the product a second place
        where files live.
        """
        case = await self.get_case(case_id)
        employee = await self.employees.get(case.employee_id)
        if employee is None:
            raise NotFoundError("Employee")

        existing = await self.documents.get_by(case_id=case.id, document_type=payload.document_type.value)
        if existing is not None and existing.document_id is not None:
            if payload.release and not existing.released:
                await self.documents.update(existing, {"released": True}, actor_id=actor_id)
                await self._notify_user(
                    employee.user_id,
                    "Exit document available",
                    f"Your {_EXIT_DOCUMENT_TITLES[payload.document_type].lower()} is ready to download.",
                    None,
                    actor_id,
                    link="/employee/offboarding",
                )
            return existing

        pdf = self._render_letter(payload.document_type, employee, case)
        document = await self._file_in_vault(payload.document_type, employee, case, pdf, actor_id)

        record = existing or ExitDocument(
            case_id=case.id, employee_id=employee.id, document_type=payload.document_type.value
        )
        if existing is None:
            await self.documents.add(record, actor_id=actor_id)
        await self.documents.update(
            record,
            {"document_id": document.id, "issued_at": utc_now(), "released": payload.release},
            actor_id=actor_id,
        )

        await self._audit(
            AuditAction.EXIT_DOCUMENT_GENERATED,
            None,
            actor_id=actor_id,
            entity_type="offboarding_case",
            entity_id=case.id,
            description=f"{_EXIT_DOCUMENT_TITLES[payload.document_type]} generated for {case.case_code}",
            context={"document_type": payload.document_type.value, "released": payload.release},
        )
        if payload.release:
            await self._notify_user(
                employee.user_id,
                "Exit document available",
                f"Your {_EXIT_DOCUMENT_TITLES[payload.document_type].lower()} is ready to download.",
                None,
                actor_id,
                link="/employee/offboarding",
            )
        return record

    # ==================================================================
    # Completion
    # ==================================================================
    async def complete_case(
        self, case_id: uuid.UUID, payload: CaseCompletion, *, actor_id: uuid.UUID, may_force: bool = False
    ) -> OffboardingCase:
        """Finish the separation: the employee becomes inactive, nothing is deleted.

        §19 and §20 in one place, and the order matters. Allocations end before
        the status changes so the employee is not left holding a live project
        they can no longer be assigned to, and every historical row -- the
        allocation itself, attendance, leave, timesheets, performance -- is left
        exactly where it is.
        """
        case = await self.get_case(case_id)
        if case.status is OffboardingCaseStatus.COMPLETED.value:
            raise ConflictError("This offboarding is already complete.", error_code="already_completed")

        outstanding = await self._outstanding(case)
        if outstanding and not payload.force:
            raise ConflictError(
                "Clearance is not finished: "
                + ", ".join(f"{count} {label}" for label, count in outstanding.items() if count)
                + ". Waive what does not apply, or force the completion.",
                error_code="clearance_outstanding",
            )
        if outstanding and payload.force and not may_force:
            raise PermissionDeniedError(
                "Completing an offboarding with outstanding clearance needs offboarding:manage.",
                details=[{"code": "force_not_permitted", "message": "force"}],
            )

        employee = await self.employees.get(case.employee_id)
        if employee is None:
            raise NotFoundError("Employee")

        await self._end_allocations(employee.id, case.last_working_day, actor_id=actor_id)

        await self.cases.update(
            case,
            {
                "status": OffboardingCaseStatus.COMPLETED.value,
                "progress_percent": 100,
                "completed_at": utc_now(),
            },
            actor_id=actor_id,
        )
        resignation = await self.resignations.get_detailed(case.resignation_id)
        if resignation is not None:
            await self.resignations.update(
                resignation, {"status": ResignationStatus.COMPLETED.value}, actor_id=actor_id
            )
            await self._record_history(
                resignation,
                action="completed",
                from_status=ResignationStatus(resignation.status),
                to_status=ResignationStatus.COMPLETED,
                comments=payload.comments,
                actor_id=actor_id,
                is_override=bool(outstanding and payload.force),
            )

        await self._set_employment_status(employee, EmploymentStatus.INACTIVE, actor_id=actor_id)

        # The exit ends the login, not only the employment. Authentication
        # checks ``users.is_active`` and nothing else, so leaving the account
        # active would let a departed employee keep signing in indefinitely.
        if employee.user_id and self.users is not None:
            account = await self.users.get(employee.user_id)
            if account is not None and account.is_active:
                await self.users.update(account, {"is_active": False}, actor_id=actor_id)
                await self._audit(
                    AuditAction.USER_DEACTIVATED,
                    None,
                    actor_id=actor_id,
                    entity_type="user",
                    entity_id=account.id,
                    description=f"Login disabled: {employee.employee_code} exited",
                    context={"case_id": str(case.id)},
                )

        await self._audit(
            AuditAction.OFFBOARDING_COMPLETED,
            None,
            actor_id=actor_id,
            entity_type="offboarding_case",
            entity_id=case.id,
            description=f"Offboarding {case.case_code} completed",
            context={"forced": bool(outstanding and payload.force)},
        )
        await self._audit(
            AuditAction.EMPLOYEE_EXITED,
            None,
            actor_id=actor_id,
            entity_type="employee",
            entity_id=employee.id,
            description=f"{employee.employee_code} exited on {case.last_working_day.isoformat()}",
        )
        if outstanding and payload.force:
            await self._audit_override(
                case.id,
                actor_id,
                f"Offboarding {case.case_code} completed with outstanding clearance",
                payload.comments or "No reason given",
            )
        await self._notify_user(
            employee.user_id,
            "Offboarding completed",
            "Your exit formalities are complete. Portal access ends with your exit; "
            "contact HR for any document you still need.",
            None,
            actor_id,
            link="/employee/offboarding",
        )
        logger.info(
            "Offboarding completed",
            extra={"case_id": str(case.id), "employee_id": str(employee.id)},
        )
        return await self._reload_case(case.id)

    # ==================================================================
    # Dashboards
    # ==================================================================
    async def summary(self, *, scope: EmployeeScope | None = None) -> OffboardingSummary:
        visible = visible_employee_ids(scope)
        today = date.today()
        month_end = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        return OffboardingSummary(
            active_resignations=await self.analytics.active_resignation_count(visible_ids=visible),
            pending_manager_review=await self.resignations.count_by_status(
                ResignationStatus.MANAGER_REVIEW, visible_ids=visible
            ),
            pending_hr_review=await self.resignations.count_by_status(
                ResignationStatus.HR_REVIEW, visible_ids=visible
            ),
            serving_notice=await self.analytics.serving_notice_count(visible_ids=visible),
            exiting_this_month=await self.cases.exiting_between(today, month_end, visible_ids=visible),
            pending_clearance=await self.cases.pending_clearance_count(visible_ids=visible),
            exit_interviews_pending=await self.analytics.exit_interviews_pending(visible_ids=visible),
            exit_documents_pending=await self.analytics.exit_documents_pending(visible_ids=visible),
            settlement_pending=await self.analytics.settlement_pending(visible_ids=visible),
        )

    async def clearance_progress(self, case: OffboardingCase) -> ClearanceProgress:
        tasks = list(case.tasks)
        assets = list(case.assets)
        access_items = list(case.access_items)
        settled_tasks = sum(1 for t in tasks if t.status in {s.value for s in SETTLED_TASK_STATUSES})
        settled_assets = sum(1 for a in assets if a.status in {s.value for s in SETTLED_ASSET_STATUSES})
        settled_access = sum(
            1 for a in access_items if a.status in {s.value for s in SETTLED_ACCESS_STATUSES}
        )
        total = len(tasks) + len(assets) + len(access_items)
        settled = settled_tasks + settled_assets + settled_access
        outstanding = sorted(
            {
                OffboardingDepartment(task.department)
                for task in tasks
                if task.status not in {s.value for s in SETTLED_TASK_STATUSES}
            },
            key=lambda item: item.value,
        )
        return ClearanceProgress(
            tasks_total=len(tasks),
            tasks_settled=settled_tasks,
            assets_total=len(assets),
            assets_settled=settled_assets,
            access_total=len(access_items),
            access_settled=settled_access,
            percent=round(settled / total * 100) if total else 0,
            outstanding_departments=outstanding,
        )

    def notice_view(self, resignation: Resignation) -> NoticePeriodView:
        """Every figure §6 asks a screen to show, computed here rather than there.

        ``remaining_days`` is clamped at zero: a notice period that ended last
        week has none left, and a negative count on a dashboard reads as a bug
        rather than as information.
        """
        today = date.today()
        expected = resignation.resignation_date + timedelta(days=resignation.notice_period_days)
        effective = resignation.approved_last_working_day or resignation.proposed_last_working_day
        served = max(0, (min(today, effective) - resignation.resignation_date).days)

        if ResignationStatus(resignation.status) in TERMINAL_RESIGNATION_STATUSES:
            notice_status = "completed" if resignation.status == ResignationStatus.COMPLETED else "closed"
        elif effective < today:
            notice_status = "completed"
        elif resignation.approved_last_working_day is None:
            notice_status = "not_started"
        else:
            notice_status = "serving"

        return NoticePeriodView(
            resignation_date=resignation.resignation_date,
            notice_period_days=resignation.notice_period_days,
            expected_last_working_day=expected,
            proposed_last_working_day=resignation.proposed_last_working_day,
            approved_last_working_day=resignation.approved_last_working_day,
            remaining_days=max(0, (effective - today).days),
            notice_served_days=served,
            notice_status=notice_status,
            notice_period_adjusted=resignation.notice_period_adjusted,
        )

    async def list_exit_interviews(
        self, *, page: int, page_size: int, scope: EmployeeScope | None = None
    ) -> tuple[list[ExitInterviewListItem], int]:
        """Submitted interviews, narrowed to the caller's scope.

        Joined to the employee in one query rather than summarised per row: an
        HR list of twenty interviews would otherwise be twenty-one round trips
        to put a name against each one.
        """
        rows, total = await self.interviews.submitted_with_employees(
            offset=(page - 1) * page_size,
            limit=page_size,
            visible_ids=visible_employee_ids(scope),
        )
        return [
            ExitInterviewListItem(
                id=interview.id,
                case_id=interview.case_id,
                employee=EmployeeSummary(
                    id=employee.id,
                    employee_code=employee.employee_code,
                    full_name=employee.full_name,
                ),
                reason_for_leaving=interview.reason_for_leaving,
                overall_experience=interview.overall_experience,
                would_recommend=interview.would_recommend,
                would_rejoin=interview.would_rejoin,
                submitted_at=interview.submitted_at,
            )
            for interview, employee in rows
        ], total

    # ==================================================================
    # Presentation
    #
    # Assembled here rather than in the routes because each of these needs the
    # database -- an employee summary, the case behind a resignation, the notice
    # figures -- and a route that queries is a route with business logic in it.
    # The employee-facing and administrative shapes are separate models, not one
    # model with fields blanked out.
    # ==================================================================
    async def present_my_resignation(self, resignation: Resignation | None) -> MyResignation | None:
        if resignation is None:
            return None
        status = ResignationStatus(resignation.status)
        return MyResignation(
            id=resignation.id,
            resignation_code=resignation.resignation_code,
            status=status,
            resignation_date=resignation.resignation_date,
            proposed_last_working_day=resignation.proposed_last_working_day,
            approved_last_working_day=resignation.approved_last_working_day,
            reason=resignation.reason,
            comments=resignation.comments,
            supporting_document_id=resignation.supporting_document_id,
            submitted_at=resignation.submitted_at,
            manager_comments=resignation.manager_comments,
            can_withdraw=status in WITHDRAWABLE_RESIGNATION_STATUSES,
            notice=self.notice_view(resignation),
            history=[ResignationHistoryEntry.model_validate(row) for row in resignation.history],
        )

    async def present_resignation(self, resignation: Resignation) -> ResignationRead:
        case = await self.cases.for_resignation(resignation.id)
        return ResignationRead(
            id=resignation.id,
            resignation_code=resignation.resignation_code,
            employee=await self._employee_summary(resignation.employee_id),
            status=ResignationStatus(resignation.status),
            resignation_date=resignation.resignation_date,
            proposed_last_working_day=resignation.proposed_last_working_day,
            recommended_last_working_day=resignation.recommended_last_working_day,
            approved_last_working_day=resignation.approved_last_working_day,
            notice_period_days=resignation.notice_period_days,
            notice_period_adjusted=resignation.notice_period_adjusted,
            reason=resignation.reason,
            comments=resignation.comments,
            supporting_document_id=resignation.supporting_document_id,
            submitted_at=resignation.submitted_at,
            manager_id=resignation.manager_id,
            manager_decided_at=resignation.manager_decided_at,
            manager_comments=resignation.manager_comments,
            hr_owner_id=resignation.hr_owner_id,
            hr_processed_at=resignation.hr_processed_at,
            hr_comments=resignation.hr_comments,
            case_id=case.id if case else None,
            notice=self.notice_view(resignation),
            history=[ResignationHistoryEntry.model_validate(row) for row in resignation.history],
        )

    async def present_case(self, case: OffboardingCase) -> OffboardingCaseRead:
        resignation = await self.resignations.get_detailed(case.resignation_id)
        handover = await self.handovers.for_case(case.id)
        settlement = await self.settlements.for_case(case.id)
        documents = await self.documents.for_case(case.id)
        interview = await self.interviews.for_case(case.id)
        return OffboardingCaseRead(
            id=case.id,
            case_code=case.case_code,
            employee=await self._employee_summary(case.employee_id),
            resignation_id=case.resignation_id,
            resignation_code=resignation.resignation_code if resignation else None,
            resignation_status=ResignationStatus(resignation.status) if resignation else None,
            last_working_day=case.last_working_day,
            notice_period_days=case.notice_period_days,
            hr_owner_id=case.hr_owner_id,
            manager_id=case.manager_id,
            status=OffboardingCaseStatus(case.status),
            progress_percent=case.progress_percent,
            created_at=case.created_at,
            completed_at=case.completed_at,
            tasks=[OffboardingTaskRead.model_validate(task) for task in case.tasks],
            assets=[AssetClearanceRead.model_validate(asset) for asset in case.assets],
            access_items=[AccessClearanceRead.model_validate(item) for item in case.access_items],
            handover=HandoverRead.model_validate(handover) if handover else None,
            settlement=SettlementRead.model_validate(settlement) if settlement else None,
            exit_documents=[ExitDocumentRead.model_validate(doc) for doc in documents],
            exit_interview_submitted=bool(interview and interview.submitted_at),
            clearance=await self.clearance_progress(case),
            notice=self.notice_view(resignation) if resignation else None,
        )

    async def present_my_offboarding(self, employee: Employee) -> MyOffboarding:
        """The employee's own separation, and nothing about anybody else's."""
        resignation = await self.my_resignation(employee)
        case = await self._case_for_employee(employee.id)
        if case is None:
            return MyOffboarding(
                resignation=await self.present_my_resignation(resignation),
                case_code=None,
                last_working_day=None,
                case_status=None,
                clearance=None,
                pending_actions=self._pending_actions(resignation, None, False),
            )

        interview = await self.interviews.for_case(case.id)
        settlement = await self.settlements.for_case(case.id)
        submitted = bool(interview and interview.submitted_at)
        released = [doc for doc in await self.documents.for_case(case.id) if doc.released]
        # Only the rows this employee owns. The IT and Finance rows are somebody
        # else's work and are not theirs to see or to chase.
        mine = [
            task for task in case.tasks if task.owner_id is not None and task.owner_id == employee.user_id
        ]
        return MyOffboarding(
            resignation=await self.present_my_resignation(resignation),
            case_code=case.case_code,
            last_working_day=case.last_working_day,
            case_status=OffboardingCaseStatus(case.status),
            clearance=await self.clearance_progress(case),
            my_tasks=[OffboardingTaskRead.model_validate(task) for task in mine],
            pending_actions=self._pending_actions(resignation, case, submitted),
            exit_interview_submitted=submitted,
            exit_interview_available=(
                case.status == OffboardingCaseStatus.IN_PROGRESS.value and not submitted
            ),
            exit_documents=[ExitDocumentRead.model_validate(doc) for doc in released],
            settlement_status=SettlementStatus(settlement.status) if settlement else None,
        )

    def _pending_actions(
        self, resignation: Resignation | None, case: OffboardingCase | None, interview_done: bool
    ) -> list[MyPendingAction]:
        actions: list[MyPendingAction] = []
        if resignation is None:
            return actions
        status = ResignationStatus(resignation.status)
        if status in {ResignationStatus.MANAGER_REVIEW, ResignationStatus.HR_REVIEW}:
            actions.append(
                MyPendingAction(
                    key="awaiting_review",
                    label="Your resignation is awaiting review.",
                    link="/employee/resignation",
                )
            )
        if case is not None and not interview_done and case.status == OffboardingCaseStatus.IN_PROGRESS.value:
            actions.append(
                MyPendingAction(
                    key="exit_interview",
                    label="Complete your exit interview.",
                    link="/employee/exit-interview",
                )
            )
        return actions

    async def _employee_summary(self, employee_id: uuid.UUID) -> EmployeeSummary:
        employee = await self.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("Employee")
        return EmployeeSummary(
            id=employee.id,
            employee_code=employee.employee_code,
            full_name=employee.full_name,
            designation=employee.designation.name if employee.designation else None,
            team=employee.team.name if employee.team else None,
        )

    # ==================================================================
    # Internals
    # ==================================================================
    async def _resolve_notice_days(self, employee: Employee) -> int:
        """From the employment type, never from a literal at a call site.

        NULL on the master means "not configured" and falls back to the module
        default; 0 means "no notice required", which is a different statement
        and is honoured.
        """
        if employee.employment_type_id is None:
            return DEFAULT_NOTICE_PERIOD_DAYS
        configured = await self.session.scalar(
            select(EmploymentType.notice_period_days).where(EmploymentType.id == employee.employment_type_id)
        )
        return DEFAULT_NOTICE_PERIOD_DAYS if configured is None else int(configured)

    async def _open_case(
        self,
        resignation: Resignation,
        employee: Employee,
        last_working_day: date,
        notice_days: int,
        actor_id: uuid.UUID,
    ) -> OffboardingCase:
        case = await self.cases.add(
            OffboardingCase(
                resignation_id=resignation.id,
                employee_id=employee.id,
                last_working_day=last_working_day,
                notice_period_days=notice_days,
                hr_owner_id=actor_id,
                manager_id=resignation.manager_id or employee.reporting_manager_id,
                status=OffboardingCaseStatus.IN_PROGRESS.value,
            ),
            actor_id=actor_id,
        )

        manager_user_id = await self._manager_user_id(case.manager_id)
        for sequence, (department, title, offset) in enumerate(DEFAULT_TASKS, start=1):
            await self.tasks.add(
                OffboardingTask(
                    case_id=case.id,
                    title=title,
                    department=department.value,
                    # HR rows fall to whoever opened the case and manager rows to
                    # the reporting manager. IT, Admin and Finance rows are
                    # addressed to a department rather than a person -- the
                    # permission decides who may tick them.
                    owner_id=(
                        actor_id
                        if department is OffboardingDepartment.HR
                        else manager_user_id if department is OffboardingDepartment.MANAGER else None
                    ),
                    due_date=last_working_day - timedelta(days=offset),
                    sequence=sequence,
                ),
                actor_id=actor_id,
            )

        await self._seed_asset_clearance(case, employee.id, actor_id)
        for system_name, category in DEFAULT_ACCESS_ITEMS:
            await self.access.add(
                AccessClearance(case_id=case.id, system_name=system_name, category=category),
                actor_id=actor_id,
            )
        await self.handovers.add(HandoverRecord(case_id=case.id), actor_id=actor_id)
        await self.settlements.add(FinalSettlementTracking(case_id=case.id), actor_id=actor_id)

        await self._audit(
            AuditAction.OFFBOARDING_CASE_CREATED,
            None,
            actor_id=actor_id,
            entity_type="offboarding_case",
            entity_id=case.id,
            description=f"Offboarding case {case.case_code} opened for {employee.employee_code}",
        )
        return case

    async def _seed_asset_clearance(
        self, case: OffboardingCase, employee_id: uuid.UUID, actor_id: uuid.UUID
    ) -> None:
        """Fill the clearance list from the asset register.

        When this module was built there was no register, so the list was six
        generic lines -- "Laptop", "Monitor" -- that somebody ticked whether or
        not the person had ever been given one. Now the answer is known, and a
        clearance built from what the employee is actually holding is the whole
        point of §16.

        Two details are deliberate.

        **Non-returnable categories are seeded already waived.** A headset the
        company does not want back should appear on the list -- so nobody
        wonders where it went -- without holding an exit open. Which categories
        those are is configuration (``AssetCategory.returnable``), not a
        judgement made here.

        **The generic list survives as a fallback.** An organization that has
        not populated the register yet, or an employee registered before it
        existed, still gets a clearance prompt rather than an empty screen that
        silently asserts they hold nothing.
        """
        if self.asset_register is None:
            held = []
        else:
            held = await self.asset_register.clearance_rows_for(employee_id)

        if not held:
            for asset_name in DEFAULT_ASSETS:
                await self.assets.add(
                    AssetClearance(case_id=case.id, asset_name=asset_name), actor_id=actor_id
                )
            return

        for row in held:
            returnable = bool(row["returnable"])
            await self.assets.add(
                AssetClearance(
                    case_id=case.id,
                    asset_id=row["asset_id"],
                    asset_name=row["asset_name"],
                    asset_tag=row["asset_tag"],
                    assigned_date=row["assigned_date"],
                    condition=row["condition"],
                    status=(
                        AssetReturnStatus.ASSIGNED.value if returnable else AssetReturnStatus.WAIVED.value
                    ),
                    comments=None if returnable else "Not expected back; the category is not returnable.",
                ),
                actor_id=actor_id,
            )

    async def _outstanding(self, case: OffboardingCase) -> dict[str, int]:
        return {
            "tasks outstanding": await self.tasks.outstanding_count(case.id),
            "assets outstanding": await self.assets.outstanding_count(case.id),
            "access items outstanding": await self.access.outstanding_count(case.id),
        }

    async def _recalculate(self, case: OffboardingCase, *, actor_id: uuid.UUID) -> None:
        """Keep the denormalised percentage honest after every clearance write."""
        refreshed = await self.cases.get_detailed(case.id)
        if refreshed is None:  # pragma: no cover - defensive
            return
        progress = await self.clearance_progress(refreshed)
        if refreshed.progress_percent != progress.percent:
            await self.cases.update(refreshed, {"progress_percent": progress.percent}, actor_id=actor_id)

    async def _advance_case_status(
        self, case: OffboardingCase, target: ResignationStatus, *, actor_id: uuid.UUID
    ) -> None:
        """Move the resignation along as the case reaches a milestone."""
        resignation = await self.resignations.get_detailed(case.resignation_id)
        if resignation is None:
            return
        current = ResignationStatus(resignation.status)
        if current in TERMINAL_RESIGNATION_STATUSES or current is target:
            return
        if current not in ACTIVE_OFFBOARDING_STATUSES:
            return
        await self.resignations.update(resignation, {"status": target.value}, actor_id=actor_id)
        await self._record_history(
            resignation,
            action=f"stage_{target.value}",
            from_status=current,
            to_status=target,
            comments=None,
            actor_id=actor_id,
        )

    async def _set_employment_status(
        self, employee: Employee, status: EmploymentStatus, *, actor_id: uuid.UUID
    ) -> None:
        """Change lifecycle state without touching the record's own history rules.

        Written here rather than through ``EmployeeService.change_status``
        deliberately: that method enforces the transitions the *HR* screens
        allow, and it would refuse notice-period and inactive moves made by the
        offboarding workflow. The employment-history row is still written, so
        the employee's own trail is unchanged.
        """
        if employee.employment_status == status.value:
            return
        employee.employment_status = status.value
        employee.updated_by = actor_id
        await self.session.flush()
        await self._audit(
            AuditAction.EMPLOYEE_STATUS_CHANGED,
            None,
            actor_id=actor_id,
            entity_type="employee",
            entity_id=employee.id,
            description=f"{employee.employee_code} set to {status.value} by offboarding",
        )

    async def _end_allocations(
        self, employee_id: uuid.UUID, last_working_day: date, *, actor_id: uuid.UUID
    ) -> None:
        """Close live project allocations. §20: end them, never delete them."""
        rows = (
            (
                await self.session.execute(
                    select(EmployeeAllocation).where(
                        EmployeeAllocation.employee_id == employee_id,
                        EmployeeAllocation.status == "active",
                        EmployeeAllocation.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .unique()
            .all()
        )
        for allocation in rows:
            allocation.status = "ended"
            allocation.end_date = min(allocation.end_date or last_working_day, last_working_day)
            allocation.updated_by = actor_id
        if rows:
            await self.session.flush()
            logger.info(
                "Allocations ended on exit",
                extra={"employee_id": str(employee_id), "count": len(rows)},
            )

    async def _case_for_employee(self, employee_id: uuid.UUID) -> OffboardingCase | None:
        return await self.cases.for_employee(employee_id)

    async def _manager_user_id(self, manager_employee_id: uuid.UUID | None) -> uuid.UUID | None:
        if manager_employee_id is None:
            return None
        manager = await self.employees.get(manager_employee_id)
        return manager.user_id if manager else None

    async def _record_history(
        self,
        resignation: Resignation,
        *,
        action: str,
        from_status: ResignationStatus | None,
        to_status: ResignationStatus | None,
        comments: str | None,
        actor_id: uuid.UUID,
        is_override: bool = False,
    ) -> None:
        await self.history.add(
            ResignationHistory(
                resignation_id=resignation.id,
                action=action,
                from_status=from_status.value if from_status else None,
                to_status=to_status.value if to_status else None,
                comments=comments,
                is_override=is_override,
            ),
            actor_id=actor_id,
        )

    async def _audit(
        self,
        action: AuditAction,
        resignation: Resignation | None,
        *,
        actor_id: uuid.UUID | None,
        description: str,
        entity_type: str = "resignation",
        entity_id: uuid.UUID | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        await self.audit.record_success(
            action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id or (resignation.id if resignation else None),
            description=description,
            context=context,
        )

    async def _audit_override(
        self, entity_id: uuid.UUID, actor_id: uuid.UUID, description: str, reason: str
    ) -> None:
        """§18: an administrative override is audited *as* an override.

        Recorded in addition to the ordinary action, not instead of it. An admin
        rewriting a last working day and HR settling one through the normal step
        are the same column change and a completely different fact, and a trail
        that cannot tell them apart is not much of a trail.
        """
        await self.audit.record_success(
            AuditAction.OFFBOARDING_OVERRIDDEN,
            actor_id=actor_id,
            entity_type="offboarding",
            entity_id=entity_id,
            description=description,
            context={"reason": reason},
        )

    async def _notify_user(
        self,
        user_id: uuid.UUID | None,
        title: str,
        message: str,
        resignation: Resignation | None,
        actor_id: uuid.UUID,
        *,
        link: str | None = None,
    ) -> None:
        if user_id is None:
            return
        await self.notifications.add(
            Notification(
                user_id=user_id,
                title=title,
                message=message,
                link=link or ("/employee/resignation" if resignation else "/employee/offboarding"),
                notification_type="offboarding",
            ),
            actor_id=actor_id,
        )

    async def _notify_employee(
        self,
        employee_id: uuid.UUID,
        title: str,
        message: str,
        resignation: Resignation | None,
        actor_id: uuid.UUID,
        *,
        link: str | None = None,
    ) -> None:
        employee = await self.employees.get(employee_id)
        if employee is not None and employee.user_id:
            await self._notify_user(
                employee.user_id, title, message, resignation, actor_id, link=link or "/manager/offboarding"
            )

    async def _reload_resignation(self, resignation_id: uuid.UUID) -> Resignation:
        resignation = await self.resignations.get_detailed(resignation_id)
        if resignation is None:  # pragma: no cover - defensive
            raise NotFoundError("Resignation")
        return resignation

    async def _reload_case(self, case_id: uuid.UUID) -> OffboardingCase:
        case = await self.cases.get_detailed(case_id)
        if case is None:  # pragma: no cover - defensive
            raise NotFoundError("Offboarding case")
        return case

    # ------------------------------------------------------------------
    # Exit-document rendering and filing
    # ------------------------------------------------------------------
    def _render_letter(
        self, document_type: ExitDocumentType, employee: Employee, case: OffboardingCase
    ) -> bytes:
        """A plain, factual letter. Deliberately says nothing about performance.

        An experience letter states dates and role. Anything evaluative belongs
        to a human being who is willing to sign their name to it, not to a
        template.
        """
        buffer = BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        joined = employee.joining_date.isoformat()
        left = case.last_working_day.isoformat()
        designation = employee.designation.name if employee.designation else "employee"

        bodies = {
            ExitDocumentType.EXPERIENCE_LETTER: (
                f"This is to certify that {employee.full_name} (employee ID "
                f"{employee.employee_code}) was employed with JSAN Technologies as "
                f"{designation} from {joined} to {left}."
            ),
            ExitDocumentType.RELIEVING_LETTER: (
                f"This is to confirm that {employee.full_name} (employee ID "
                f"{employee.employee_code}) has been relieved from their duties with "
                f"JSAN Technologies with effect from the close of business on {left}, "
                "and that their exit formalities have been completed."
            ),
            ExitDocumentType.SERVICE_CERTIFICATE: (
                f"This is to certify that {employee.full_name} (employee ID "
                f"{employee.employee_code}) rendered service to JSAN Technologies as "
                f"{designation} from {joined} to {left}."
            ),
        }

        story = [
            Paragraph("JSAN Technologies", styles["Title"]),
            Paragraph(_EXIT_DOCUMENT_TITLES[document_type], styles["Heading1"]),
            Spacer(1, 18),
            Paragraph(f"Date: {date.today().isoformat()}", styles["BodyText"]),
            Spacer(1, 12),
            Paragraph("To whom it may concern,", styles["BodyText"]),
            Spacer(1, 12),
            Paragraph(bodies[document_type], styles["BodyText"]),
            Spacer(1, 24),
            Paragraph("We wish them every success in their future endeavours.", styles["BodyText"]),
            Spacer(1, 36),
            Paragraph("For JSAN Technologies", styles["BodyText"]),
            Paragraph("Human Resources", styles["BodyText"]),
        ]
        document.build(story)
        return buffer.getvalue()

    async def _file_in_vault(
        self,
        document_type: ExitDocumentType,
        employee: Employee,
        case: OffboardingCase,
        pdf: bytes,
        actor_id: uuid.UUID,
    ) -> Document:
        category = await self.session.scalar(
            select(DocumentCategory).where(DocumentCategory.code == _EXIT_DOCUMENT_CATEGORY_CODE)
        )
        if category is None:
            category = DocumentCategory(
                name="Exit Documents", code=_EXIT_DOCUMENT_CATEGORY_CODE, status=RecordStatus.ACTIVE
            )
            self.session.add(category)
            await self.session.flush()

        doc_type = await self.session.scalar(
            select(DocumentType).where(DocumentType.code == _EXIT_DOCUMENT_TYPE_CODE)
        )
        if doc_type is None:
            doc_type = DocumentType(
                name="Exit Document",
                code=_EXIT_DOCUMENT_TYPE_CODE,
                category_id=category.id,
                status=RecordStatus.ACTIVE,
            )
            self.session.add(doc_type)
            await self.session.flush()

        document = Document(
            name=f"{_EXIT_DOCUMENT_TITLES[document_type]} - {employee.employee_code}",
            category_id=category.id,
            document_type_id=doc_type.id,
            owner_type="employee",
            owner_id=employee.id,
            version_count=1,
        )
        self.session.add(document)
        await self.session.flush()

        key = f"offboarding/{case.id}/{document_type.value}-{uuid.uuid4()}.pdf"
        stored = await self.storage.save(content=pdf, key=key)
        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            original_filename=f"{document_type.value}-{employee.employee_code}.pdf",
            content_type="application/pdf",
            size_bytes=stored.size_bytes,
            checksum=stored.checksum,
            storage_key=stored.key,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.session.add(version)
        await self.session.flush()
        document.current_version_id = version.id
        await self.session.flush()
        return document
