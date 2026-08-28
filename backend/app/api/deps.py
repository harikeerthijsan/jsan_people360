"""Dependency injection wiring.

FastAPI's ``Depends`` is the composition root of the application. Every layer is
constructed here and injected downwards, so nothing below the API layer
constructs its own collaborators. That is what makes services unit-testable
with plain fakes.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.context import set_actor_id
from app.core.exceptions import (
    AccountInactiveError,
    AuthenticationError,
    InvalidTokenError,
    PermissionDeniedError,
)
from app.core.permissions import assert_known
from app.core.security import decode_access_token, get_subject_id
from app.db.session import SessionFactory
from app.models.employee import Employee
from app.models.user import User
from app.repositories.app_setting_repository import AppSettingRepository
from app.repositories.asset_repository import (
    AssetAnalyticsRepository,
    AssetAssignmentRepository,
    AssetCategoryRepository,
    AssetHistoryRepository,
    AssetMaintenanceRepository,
    AssetRepository,
    AssetReturnRepository,
    AssetTransferRepository,
)
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.document_repository import (
    DocumentCategoryRepository,
    DocumentRepository,
    DocumentTypeRepository,
    DocumentVersionRepository,
)
from app.repositories.employee_repository import EmployeeRepository, EmploymentHistoryRepository
from app.repositories.helpdesk_repository import (
    AcknowledgementRepository,
    AnnouncementRepository,
    TicketCategoryRepository,
    TicketCommentRepository,
    TicketHistoryRepository,
    TicketRepository,
)
from app.repositories.interview_repository import (
    FeedbackRepository,
    InterviewAttachmentRepository,
    InterviewRepository,
    PanelRepository,
    ScheduleHistoryRepository,
    ScoreRepository,
)
from app.repositories.offboarding_repository import (
    AccessClearanceRepository,
    AssetClearanceRepository,
    ExitDocumentRepository,
    ExitInterviewRepository,
    HandoverRepository,
    OffboardingAnalyticsRepository,
    OffboardingCaseRepository as SeparationCaseRepository,
    OffboardingTaskRepository as SeparationTaskRepository,
    ResignationHistoryRepository,
    ResignationRepository,
    SettlementRepository,
    SettlementRepository as OffboardingSettlementRepository,
)
from app.repositories.offer_repository import (
    ApprovalRepository as OfferApprovalRepository,
    ComponentRepository,
    HistoryRepository as OfferHistoryRepository,
    OfferRepository,
    TemplateRepository,
    VersionRepository,
)
from app.repositories.onboarding_repository import (
    CaseRepository as OnboardingCaseRepository,
    OnboardingHistoryRepository,
    PolicyRepository,
    ProfileRepository,
    TaskRepository as OnboardingTaskRepository,
)
from app.repositories.organization_repository import (
    BusinessUnitRepository,
    DesignationRepository,
    EmploymentTypeRepository,
    GradeRepository,
    LocationRepository,
    OrganizationRepository,
    TeamRepository,
)
from app.repositories.payroll_repository import (
    EmployeeCompensationComponentRepository,
    EmployeeCompensationRepository,
    PayrollAdjustmentRepository,
    PayrollApprovalRepository,
    PayrollConfigurationHistoryRepository,
    PayrollConfigurationRepository,
    PayrollEmployeeRecordRepository,
    PayrollEmployeeSettingRepository,
    PayrollFinalSnapshotRepository,
    PayrollInputExceptionRepository,
    PayrollInputRepository,
    PayrollInputSourceRepository,
    PayrollLeaveRuleRepository,
    PayrollLineItemRepository,
    PayrollPeriodRepository,
    PayrollReviewChecklistRepository,
    PayrollReviewCommentRepository,
    PayrollRunExceptionRepository,
    PayrollRunRepository,
    PayrollSourceReader,
    PayslipRepository,
    SalaryComponentRepository,
    SalaryHistoryRepository,
    SalaryStructureComponentRepository,
    SalaryStructureRepository,
)
from app.repositories.payroll_settlement_repository import (
    FinalSettlementAdjustmentRepository,
    FinalSettlementItemRepository,
    FinalSettlementRepository,
    PayrollReportRepository,
    SettlementReader,
)
from app.repositories.performance_repository import (
    FeedbackRepository as PerformanceFeedbackRepository,
    FinalReviewRepository,
    GoalProgressRepository,
    GoalRatingRepository,
    GoalRepository,
    ManagerReviewRepository,
    PerformanceAnalyticsRepository,
    PerformanceCycleRepository,
    PerformanceHistoryRepository,
    RecognitionRepository,
    SelfReviewRepository,
)
from app.repositories.project_repository import (
    AllocationHistoryRepository as ProjectAllocationHistoryRepository,
    AllocationRepository as ProjectAllocationRepository,
    ClientRepository,
    MemberRepository as ProjectMemberRepository,
    ProjectRepository,
)
from app.repositories.rbac_repository import (
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
    UserRoleRepository,
)
from app.repositories.recruitment_repository import (
    CandidateDocumentRepository,
    CandidateRepository,
    NoteRepository,
    OpeningRepository,
    PoolMemberRepository,
    SkillRepository,
    SourceRepository,
    StageHistoryRepository,
    StageRepository,
    TalentPoolRepository,
)
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.requisition_repository import (
    ApprovalRepository,
    AttachmentRepository,
    HistoryRepository,
    NotificationRepository,
    RequisitionRepository,
)
from app.repositories.user_repository import UserRepository
from app.repositories.workforce_repository import (
    AttendanceRepository,
    EmployeeShiftRepository,
    HolidayRepository,
    LeaveBalanceRepository,
    LeaveRequestRepository,
    LeaveTypeRepository,
    RegularizationRepository,
    ShiftRepository,
    TimesheetRepository,
    WorkforceAnalyticsRepository,
)
from app.services.asset_service import AssetService
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService, RequestOrigin
from app.services.authorization_service import AuthorizationService
from app.services.document_dashboard_service import DocumentDashboardService
from app.services.document_master_service import DocumentCategoryService, DocumentTypeService
from app.services.document_service import DocumentService
from app.services.employee_dashboard_service import EmployeeDashboardService
from app.services.employee_service import EmployeeService
from app.services.health_service import HealthService
from app.services.helpdesk_service import AnnouncementService, HelpdeskService
from app.services.hr_service import HrService
from app.services.interview_service import InterviewService
from app.services.mail_service import MailService
from app.services.manager_service import ManagerService
from app.services.offboarding_service import OffboardingService
from app.services.offer_service import OfferService
from app.services.onboarding_service import OnboardingService
from app.services.organization_service import (
    BusinessUnitService,
    DesignationService,
    EmploymentTypeService,
    GradeService,
    LocationService,
    OrganizationService,
    TeamService,
)
from app.services.payroll_approval_service import PayrollApprovalService
from app.services.payroll_config_service import PayrollConfigService
from app.services.payroll_input_service import PayrollInputService
from app.services.payroll_report_service import PayrollReportService
from app.services.payroll_review_service import PayrollReviewService
from app.services.payroll_run_service import PayrollRunService
from app.services.payroll_service import PayrollService
from app.services.payroll_settlement_service import PayrollSettlementService
from app.services.payslip_service import PayslipService
from app.services.performance_service import PerformanceService
from app.services.project_service import ProjectService
from app.services.recruitment_service import RecruitmentService
from app.services.requisition_service import RequisitionService
from app.services.role_service import RoleService
from app.services.scope_service import ORG_WIDE_PERMISSION, EmployeeScope, TeamScopeService
from app.services.self_service_service import SelfServiceService
from app.services.token_service import TokenService
from app.services.user_service import UserService
from app.services.workforce_service import WorkforceService
from app.storage import StorageBackend, get_storage

# ``auto_error=False`` so a missing header produces our envelope, not FastAPI's.
bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token issued by /auth/login.")


# ----------------------------------------------------------------------
# Unit of work
# ----------------------------------------------------------------------
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Provide a request-scoped session that is the transaction boundary.

    The session commits when the endpoint returns normally and rolls back on any
    exception, so services and repositories never manage transactions.

    One exception class opts out of the rollback: a failure flagged
    ``preserve_writes`` (see :class:`app.core.exceptions.AppException`) commits
    instead. A refused login must keep its failed-attempt counter and audit row,
    and a replayed refresh token must keep its family revoked — security
    bookkeeping that only exists on the failure path would otherwise be erased
    by the very refusal it records.
    """
    session = SessionFactory()
    try:
        yield session
        await session.commit()
    except Exception as exc:
        if getattr(exc, "preserve_writes", False):
            try:
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
        else:
            await session.rollback()
        raise
    finally:
        await session.close()


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


# ----------------------------------------------------------------------
# Repositories
# ----------------------------------------------------------------------
def get_user_repository(session: DbSession) -> UserRepository:
    return UserRepository(session)


def get_refresh_token_repository(session: DbSession) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def get_audit_log_repository(session: DbSession) -> AuditLogRepository:
    return AuditLogRepository(session)


def get_app_setting_repository(session: DbSession) -> AppSettingRepository:
    return AppSettingRepository(session)


def get_organization_repository(session: DbSession) -> OrganizationRepository:
    return OrganizationRepository(session)


def get_business_unit_repository(session: DbSession) -> BusinessUnitRepository:
    return BusinessUnitRepository(session)


def get_team_repository(session: DbSession) -> TeamRepository:
    return TeamRepository(session)


def get_location_repository(session: DbSession) -> LocationRepository:
    return LocationRepository(session)


def get_employment_type_repository(session: DbSession) -> EmploymentTypeRepository:
    return EmploymentTypeRepository(session)


def get_designation_repository(session: DbSession) -> DesignationRepository:
    return DesignationRepository(session)


def get_grade_repository(session: DbSession) -> GradeRepository:
    return GradeRepository(session)


def get_document_repository(session: DbSession) -> DocumentRepository:
    return DocumentRepository(session)


def get_document_version_repository(session: DbSession) -> DocumentVersionRepository:
    return DocumentVersionRepository(session)


def get_document_category_repository(session: DbSession) -> DocumentCategoryRepository:
    return DocumentCategoryRepository(session)


def get_document_type_repository(session: DbSession) -> DocumentTypeRepository:
    return DocumentTypeRepository(session)


def get_employee_repository(session: DbSession) -> EmployeeRepository:
    return EmployeeRepository(session)


def get_employment_history_repository(session: DbSession) -> EmploymentHistoryRepository:
    return EmploymentHistoryRepository(session)


UserRepo = Annotated[UserRepository, Depends(get_user_repository)]
RefreshTokenRepo = Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)]
AuditLogRepo = Annotated[AuditLogRepository, Depends(get_audit_log_repository)]
AppSettingRepo = Annotated[AppSettingRepository, Depends(get_app_setting_repository)]

OrganizationRepo = Annotated[OrganizationRepository, Depends(get_organization_repository)]
BusinessUnitRepo = Annotated[BusinessUnitRepository, Depends(get_business_unit_repository)]
TeamRepo = Annotated[TeamRepository, Depends(get_team_repository)]
LocationRepo = Annotated[LocationRepository, Depends(get_location_repository)]
EmploymentTypeRepo = Annotated[EmploymentTypeRepository, Depends(get_employment_type_repository)]
DesignationRepo = Annotated[DesignationRepository, Depends(get_designation_repository)]
GradeRepo = Annotated[GradeRepository, Depends(get_grade_repository)]

DocumentRepo = Annotated[DocumentRepository, Depends(get_document_repository)]
DocumentVersionRepo = Annotated[DocumentVersionRepository, Depends(get_document_version_repository)]
DocumentCategoryRepo = Annotated[DocumentCategoryRepository, Depends(get_document_category_repository)]
DocumentTypeRepo = Annotated[DocumentTypeRepository, Depends(get_document_type_repository)]

EmployeeRepo = Annotated[EmployeeRepository, Depends(get_employee_repository)]
EmploymentHistoryRepo = Annotated[EmploymentHistoryRepository, Depends(get_employment_history_repository)]


# ----------------------------------------------------------------------
# Services
# ----------------------------------------------------------------------
def get_audit_service(repository: AuditLogRepo) -> AuditService:
    return AuditService(repository)


def get_mail_service() -> MailService:
    return MailService()


def get_token_service(
    repository: RefreshTokenRepo,
    audit_service: Annotated[AuditService, Depends(get_audit_service)],
) -> TokenService:
    # The audit service is what lets token-reuse detection land in the trail
    # rather than only in the server log.
    return TokenService(repository, audit_service)


def get_user_service(
    repository: UserRepo,
    audit_service: Annotated[AuditService, Depends(get_audit_service)],
    team_repository: Annotated[TeamRepository, Depends(get_team_repository)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
) -> UserService:
    # The team repository and token service are what let the service refuse an
    # archive that would orphan a managed team, and end the sessions of an
    # account it has just disabled.
    return UserService(repository, audit_service, team_repository, token_service)


def get_auth_service(
    user_repository: UserRepo,
    user_service: Annotated[UserService, Depends(get_user_service)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    audit_service: Annotated[AuditService, Depends(get_audit_service)],
    mail_service: Annotated[MailService, Depends(get_mail_service)],
) -> AuthService:
    return AuthService(
        user_repository=user_repository,
        user_service=user_service,
        token_service=token_service,
        audit_service=audit_service,
        mail_service=mail_service,
    )


def get_health_service(session: DbSession) -> HealthService:
    return HealthService(session)


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]
AuthSvc = Annotated[AuthService, Depends(get_auth_service)]
HealthSvc = Annotated[HealthService, Depends(get_health_service)]
TokenSvc = Annotated[TokenService, Depends(get_token_service)]
UserSvc = Annotated[UserService, Depends(get_user_service)]


# ----------------------------------------------------------------------
# Organization master-data services
#
# Services that validate a parent reference receive that parent's repository,
# not its service. Depending on a sibling service would couple the two together
# and, for a deep hierarchy, build a chain of services on every request.
# ----------------------------------------------------------------------
def get_organization_service(repository: OrganizationRepo, audit_service: AuditSvc) -> OrganizationService:
    return OrganizationService(repository, audit_service)


def get_business_unit_service(repository: BusinessUnitRepo, audit_service: AuditSvc) -> BusinessUnitService:
    return BusinessUnitService(repository, audit_service)


def get_team_service(
    repository: TeamRepo,
    business_unit_repository: BusinessUnitRepo,
    user_repository: UserRepo,
    audit_service: AuditSvc,
) -> TeamService:
    return TeamService(repository, business_unit_repository, user_repository, audit_service)


def get_location_service(repository: LocationRepo, audit_service: AuditSvc) -> LocationService:
    return LocationService(repository, audit_service)


def get_employment_type_service(
    repository: EmploymentTypeRepo, audit_service: AuditSvc
) -> EmploymentTypeService:
    return EmploymentTypeService(repository, audit_service)


def get_designation_service(
    repository: DesignationRepo,
    business_unit_repository: BusinessUnitRepo,
    audit_service: AuditSvc,
) -> DesignationService:
    return DesignationService(repository, business_unit_repository, audit_service)


def get_grade_service(repository: GradeRepo, audit_service: AuditSvc) -> GradeService:
    return GradeService(repository, audit_service)


# ----------------------------------------------------------------------
# Employee Management
#
# The employee service receives the user repository, not the user service: it
# only needs to confirm that a login account exists before linking it, and
# depending on the sibling service would couple the two modules together.
# ----------------------------------------------------------------------
def get_employee_service(
    repository: EmployeeRepo,
    history_repository: EmploymentHistoryRepo,
    audit_service: AuditSvc,
    audit_log_repository: AuditLogRepo,
    user_repository: UserRepo,
) -> EmployeeService:
    return EmployeeService(
        repository, history_repository, audit_service, audit_log_repository, user_repository
    )


def get_employee_dashboard_service(repository: EmployeeRepo) -> EmployeeDashboardService:
    return EmployeeDashboardService(repository)


EmployeeSvc = Annotated[EmployeeService, Depends(get_employee_service)]
EmployeeDashboardSvc = Annotated[EmployeeDashboardService, Depends(get_employee_dashboard_service)]


# ----------------------------------------------------------------------
# Document vault
#
# The service receives the storage *backend*, not a path. That is what makes
# object storage a one-line change here rather than a service rewrite.
#
# The owner repositories are for confirming an owner exists and resolving its
# display name -- repositories rather than services, because this module has no
# business applying another module's rules.
# ----------------------------------------------------------------------
def get_storage_backend() -> StorageBackend:
    return get_storage()


Storage = Annotated[StorageBackend, Depends(get_storage_backend)]


def get_document_service(
    session: DbSession,
    repository: DocumentRepo,
    version_repository: DocumentVersionRepo,
    audit_service: AuditSvc,
    storage: Storage,
    employee_repository: EmployeeRepo,
    user_repository: UserRepo,
    organization_repository: OrganizationRepo,
) -> DocumentService:
    return DocumentService(
        repository,
        version_repository,
        audit_service,
        storage,
        employee_repository=employee_repository,
        user_repository=user_repository,
        organization_repository=organization_repository,
        # Constructed here rather than promoted to its own dependency: the vault
        # only ever asks a candidate whether it exists and what it is called.
        candidate_repository=CandidateRepository(session),
        # The shared in-app inbox, so a review decision reaches the person whose
        # document it is rather than only the audit trail.
        notification_repository=NotificationRepository(session),
    )


def get_document_dashboard_service(repository: DocumentRepo) -> DocumentDashboardService:
    return DocumentDashboardService(repository)


def get_document_category_service(
    repository: DocumentCategoryRepo,
    audit_service: AuditSvc,
    document_repository: DocumentRepo,
    type_repository: DocumentTypeRepo,
) -> DocumentCategoryService:
    return DocumentCategoryService(repository, audit_service, document_repository, type_repository)


def get_document_type_service(
    repository: DocumentTypeRepo,
    category_repository: DocumentCategoryRepo,
    audit_service: AuditSvc,
    document_repository: DocumentRepo,
) -> DocumentTypeService:
    return DocumentTypeService(repository, category_repository, audit_service, document_repository)


DocumentSvc = Annotated[DocumentService, Depends(get_document_service)]
DocumentDashboardSvc = Annotated[DocumentDashboardService, Depends(get_document_dashboard_service)]


def get_requisition_service(session: DbSession, audit_service: AuditSvc) -> RequisitionService:
    return RequisitionService(
        RequisitionRepository(session),
        ApprovalRepository(session),
        AttachmentRepository(session),
        HistoryRepository(session),
        NotificationRepository(session),
        audit_service,
    )


RequisitionSvc = Annotated[RequisitionService, Depends(get_requisition_service)]


def get_recruitment_service(session: DbSession, audit_service: AuditSvc) -> RecruitmentService:
    return RecruitmentService(
        OpeningRepository(session),
        CandidateRepository(session),
        SourceRepository(session),
        StageRepository(session),
        CandidateDocumentRepository(session),
        SkillRepository(session),
        StageHistoryRepository(session),
        NoteRepository(session),
        TalentPoolRepository(session),
        PoolMemberRepository(session),
        NotificationRepository(session),
        audit_service,
    )


RecruitmentSvc = Annotated[RecruitmentService, Depends(get_recruitment_service)]


def get_interview_service(session: DbSession, audit_service: AuditSvc) -> InterviewService:
    return InterviewService(
        InterviewRepository(session),
        PanelRepository(session),
        FeedbackRepository(session),
        ScoreRepository(session),
        ScheduleHistoryRepository(session),
        InterviewAttachmentRepository(session),
        NotificationRepository(session),
        audit_service,
    )


InterviewSvc = Annotated[InterviewService, Depends(get_interview_service)]


def get_offer_service(session: DbSession, audit_service: AuditSvc, storage: Storage) -> OfferService:
    return OfferService(
        OfferRepository(session),
        VersionRepository(session),
        OfferApprovalRepository(session),
        OfferHistoryRepository(session),
        ComponentRepository(session),
        TemplateRepository(session),
        NotificationRepository(session),
        audit_service,
        storage,
    )


OfferSvc = Annotated[OfferService, Depends(get_offer_service)]


def get_onboarding_service(
    session: DbSession, employee_service: EmployeeSvc, audit_service: AuditSvc
) -> OnboardingService:
    return OnboardingService(
        ProfileRepository(session),
        OnboardingCaseRepository(session),
        OnboardingTaskRepository(session),
        PolicyRepository(session),
        OnboardingHistoryRepository(session),
        employee_service,
        audit_service,
        MailService(),
    )


OnboardingSvc = Annotated[OnboardingService, Depends(get_onboarding_service)]


def get_offboarding_service(
    session: DbSession,
    employee_repository: EmployeeRepo,
    audit_service: AuditSvc,
    storage: Storage,
    asset_service: AssetSvc,
) -> OffboardingService:
    """Resignation and offboarding.

    One service rather than two because the resignation and the case it opens
    are one workflow: approving the first creates the second, and completing the
    second closes the first. Splitting them would mean each reaching into the
    other on every transition.

    The offboarding case repositories are aliased on import -- the onboarding
    module already exports a ``OnboardingCaseRepository`` and the two names are
    one character apart, which is exactly the kind of collision that produces a
    bug nobody sees in review.
    """
    return OffboardingService(
        ResignationRepository(session),
        ResignationHistoryRepository(session),
        SeparationCaseRepository(session),
        SeparationTaskRepository(session),
        HandoverRepository(session),
        AssetClearanceRepository(session),
        AccessClearanceRepository(session),
        ExitInterviewRepository(session),
        ExitDocumentRepository(session),
        SettlementRepository(session),
        OffboardingAnalyticsRepository(session),
        employee_repository,
        audit_service,
        NotificationRepository(session),
        storage,
        asset_service,
        UserRepository(session),
    )


OffboardingSvc = Annotated[OffboardingService, Depends(get_offboarding_service)]


def get_asset_service(
    session: DbSession,
    employee_repository: EmployeeRepo,
    audit_service: AuditSvc,
) -> AssetService:
    """The asset register, its custody trail and its offboarding link.

    One service rather than several because the tables interlock: assigning
    writes an assignment *and* moves the asset's status *and* appends to its
    history, and splitting that across services would mean each reaching into
    the others on every custody change.
    """
    return AssetService(
        AssetRepository(session),
        AssetCategoryRepository(session),
        AssetAssignmentRepository(session),
        AssetReturnRepository(session),
        AssetTransferRepository(session),
        AssetMaintenanceRepository(session),
        AssetHistoryRepository(session),
        AssetAnalyticsRepository(session),
        employee_repository,
        audit_service,
        NotificationRepository(session),
    )


AssetSvc = Annotated[AssetService, Depends(get_asset_service)]


def get_payroll_service(
    session: DbSession,
    employee_repository: EmployeeRepo,
    audit_service: AuditSvc,
) -> PayrollService:
    """Salary structures, components and employee compensation.

    One service because the rules interlock: an assignment reads the structure,
    validates its components, refuses an overlap and writes the history row in
    one transaction, and splitting that would mean each half reaching into the
    other on every salary change.
    """
    return PayrollService(
        SalaryStructureRepository(session),
        SalaryComponentRepository(session),
        SalaryStructureComponentRepository(session),
        EmployeeCompensationRepository(session),
        EmployeeCompensationComponentRepository(session),
        SalaryHistoryRepository(session),
        employee_repository,
        audit_service,
    )


PayrollSvc = Annotated[PayrollService, Depends(get_payroll_service)]


def get_payroll_config_service(
    session: DbSession,
    employee_repository: EmployeeRepo,
    audit_service: AuditSvc,
) -> PayrollConfigService:
    """The payroll rulebook: configuration, periods, leave rules, settings.

    Separate from :func:`get_payroll_service` because the two answer different
    questions — "what is this person paid" versus "how does payroll behave" —
    and the permissions that open them are deliberately different grants.
    """
    return PayrollConfigService(
        PayrollConfigurationRepository(session),
        PayrollConfigurationHistoryRepository(session),
        PayrollPeriodRepository(session),
        PayrollLeaveRuleRepository(session),
        PayrollEmployeeSettingRepository(session),
        EmployeeCompensationRepository(session),
        LeaveTypeRepository(session),
        HolidayRepository(session),
        employee_repository,
        audit_service,
    )


PayrollConfigSvc = Annotated[PayrollConfigService, Depends(get_payroll_config_service)]


def get_payroll_input_service(
    session: DbSession,
    audit_service: AuditSvc,
) -> PayrollInputService:
    """Payroll input preparation: the read-only bridge over attendance, leave
    and overtime that the future calculation engine will consume."""
    return PayrollInputService(
        PayrollInputRepository(session),
        PayrollInputExceptionRepository(session),
        PayrollInputSourceRepository(session),
        PayrollSourceReader(session),
        PayrollPeriodRepository(session),
        PayrollConfigurationRepository(session),
        PayrollLeaveRuleRepository(session),
        audit_service,
    )


PayrollInputSvc = Annotated[PayrollInputService, Depends(get_payroll_input_service)]


def get_payroll_run_service(
    session: DbSession,
    audit_service: AuditSvc,
) -> PayrollRunService:
    """The calculation engine: runs, records and line items, computed from
    the Phase 3 snapshots under the Phase 1-2 configuration."""
    return PayrollRunService(
        PayrollRunRepository(session),
        PayrollEmployeeRecordRepository(session),
        PayrollLineItemRepository(session),
        PayrollInputRepository(session),
        PayrollPeriodRepository(session),
        PayrollConfigurationRepository(session),
        EmployeeCompensationRepository(session),
        PayrollSourceReader(session),
        audit_service,
        PayrollRunExceptionRepository(session),
        PayrollAdjustmentRepository(session),
        PayrollReviewChecklistRepository(session),
    )


PayrollRunSvc = Annotated[PayrollRunService, Depends(get_payroll_run_service)]


def get_payroll_review_service(
    session: DbSession,
    audit_service: AuditSvc,
) -> PayrollReviewService:
    """Phase 5: exception resolution, adjustments, checklist, reconciliation."""
    return PayrollReviewService(
        PayrollRunRepository(session),
        PayrollEmployeeRecordRepository(session),
        PayrollRunExceptionRepository(session),
        PayrollAdjustmentRepository(session),
        PayrollReviewChecklistRepository(session),
        PayrollReviewCommentRepository(session),
        audit_service,
    )


PayrollReviewSvc = Annotated[PayrollReviewService, Depends(get_payroll_review_service)]


def get_payroll_approval_service(
    session: DbSession,
    audit_service: AuditSvc,
) -> PayrollApprovalService:
    """Phase 6: the approval queue, decisions, and finalization."""
    return PayrollApprovalService(
        PayrollRunRepository(session),
        PayrollEmployeeRecordRepository(session),
        PayrollRunExceptionRepository(session),
        PayrollAdjustmentRepository(session),
        PayrollReviewChecklistRepository(session),
        PayrollPeriodRepository(session),
        EmployeeCompensationRepository(session),
        PayrollApprovalRepository(session),
        PayrollFinalSnapshotRepository(session),
        audit_service,
    )


PayrollApprovalSvc = Annotated[PayrollApprovalService, Depends(get_payroll_approval_service)]


def get_payslip_service(
    session: DbSession,
    audit_service: AuditSvc,
    storage: Annotated[StorageBackend, Depends(get_storage_backend)],
) -> PayslipService:
    """Phase 7: payslips rendered from finalized payroll snapshots."""
    return PayslipService(
        PayslipRepository(session),
        PayrollRunRepository(session),
        PayrollFinalSnapshotRepository(session),
        PayrollEmployeeRecordRepository(session),
        OrganizationRepository(session),
        PayrollConfigurationRepository(session),
        storage,
        audit_service,
    )


PayslipSvc = Annotated[PayslipService, Depends(get_payslip_service)]


def get_payroll_report_service(session: DbSession, audit_service: AuditSvc) -> PayrollReportService:
    """Phase 8: reports over finalized payroll."""
    return PayrollReportService(PayrollReportRepository(session), audit_service)


PayrollReportSvc = Annotated[PayrollReportService, Depends(get_payroll_report_service)]


def get_payroll_settlement_service(session: DbSession, audit_service: AuditSvc) -> PayrollSettlementService:
    """Phase 8: full & final settlement over the offboarding, asset, leave and payroll data."""
    return PayrollSettlementService(
        FinalSettlementRepository(session),
        FinalSettlementItemRepository(session),
        FinalSettlementAdjustmentRepository(session),
        SettlementReader(session),
        EmployeeCompensationRepository(session),
        PayrollConfigurationRepository(session),
        OffboardingSettlementRepository(session),
        audit_service,
    )


PayrollSettlementSvc = Annotated[PayrollSettlementService, Depends(get_payroll_settlement_service)]


def get_helpdesk_service(
    session: DbSession, employee_repository: EmployeeRepo, audit_service: AuditSvc
) -> HelpdeskService:
    """Employee requests, their queues and their resolution."""
    return HelpdeskService(
        TicketRepository(session),
        TicketCategoryRepository(session),
        TicketCommentRepository(session),
        TicketHistoryRepository(session),
        employee_repository,
        audit_service,
        NotificationRepository(session),
    )


HelpdeskSvc = Annotated[HelpdeskService, Depends(get_helpdesk_service)]


def get_announcement_service(
    session: DbSession, employee_repository: EmployeeRepo, audit_service: AuditSvc
) -> AnnouncementService:
    """Company notices.

    Separate from the helpdesk despite sharing a module: they have nothing in
    common except that both deliver through the notification inbox, and a single
    service holding both would be two unrelated objects sharing a constructor.
    """
    return AnnouncementService(
        AnnouncementRepository(session),
        AcknowledgementRepository(session),
        employee_repository,
        audit_service,
        NotificationRepository(session),
    )


AnnouncementSvc = Annotated[AnnouncementService, Depends(get_announcement_service)]


def get_project_service(session: DbSession, audit_service: AuditSvc) -> ProjectService:
    return ProjectService(
        ClientRepository(session),
        ProjectRepository(session),
        ProjectMemberRepository(session),
        ProjectAllocationRepository(session),
        ProjectAllocationHistoryRepository(session),
        audit_service,
    )


ProjectSvc = Annotated[ProjectService, Depends(get_project_service)]


def get_performance_service(
    session: DbSession, employee_repository: EmployeeRepo, audit_service: AuditSvc
) -> PerformanceService:
    """Eleven repositories, constructed here so the service stays testable.

    The module spans cycles, goals, three review stages, recognition, feedback
    and history; each has its own query surface, and injecting them separately
    is what lets a unit test hand in a fake for one of them.
    """
    return PerformanceService(
        PerformanceCycleRepository(session),
        GoalRepository(session),
        GoalProgressRepository(session),
        GoalRatingRepository(session),
        SelfReviewRepository(session),
        ManagerReviewRepository(session),
        FinalReviewRepository(session),
        RecognitionRepository(session),
        PerformanceFeedbackRepository(session),
        PerformanceHistoryRepository(session),
        PerformanceAnalyticsRepository(session),
        employee_repository,
        audit_service,
        NotificationRepository(session),
    )


PerformanceSvc = Annotated[PerformanceService, Depends(get_performance_service)]


def get_workforce_service(
    session: DbSession, employee_repository: EmployeeRepo, audit_service: AuditSvc
) -> WorkforceService:
    """Attendance, leave and timesheets share one service because they share a day.

    A leave day suppresses an absence, a holiday is not counted against leave,
    and a timesheet is read against attendance for the same date -- splitting
    them into three services would mean three of them reaching into each other.
    """
    return WorkforceService(
        ShiftRepository(session),
        EmployeeShiftRepository(session),
        AttendanceRepository(session),
        RegularizationRepository(session),
        LeaveTypeRepository(session),
        LeaveBalanceRepository(session),
        LeaveRequestRepository(session),
        HolidayRepository(session),
        TimesheetRepository(session),
        WorkforceAnalyticsRepository(session),
        employee_repository,
        audit_service,
        ProjectAllocationRepository(session),
        NotificationRepository(session),
        # Read-only, and only to answer "has this person already left?" -- §21
        # of the separation brief. Attendance, leave and timesheets stay
        # readable afterwards; it is creating a *new* one that is refused.
        SeparationCaseRepository(session),
    )


WorkforceSvc = Annotated[WorkforceService, Depends(get_workforce_service)]


def get_role_service(
    session: DbSession,
    user_repository: UserRepo,
    authorization: AuthzSvc,
    audit_service: AuditSvc,
) -> RoleService:
    return RoleService(
        RoleRepository(session),
        PermissionRepository(session),
        RolePermissionRepository(session),
        UserRoleRepository(session),
        user_repository,
        authorization,
        audit_service,
    )


RoleSvc = Annotated[RoleService, Depends(get_role_service)]


OrganizationSvc = Annotated[OrganizationService, Depends(get_organization_service)]
BusinessUnitSvc = Annotated[BusinessUnitService, Depends(get_business_unit_service)]
TeamSvc = Annotated[TeamService, Depends(get_team_service)]
LocationSvc = Annotated[LocationService, Depends(get_location_service)]
EmploymentTypeSvc = Annotated[EmploymentTypeService, Depends(get_employment_type_service)]
DesignationSvc = Annotated[DesignationService, Depends(get_designation_service)]
GradeSvc = Annotated[GradeService, Depends(get_grade_service)]


# ----------------------------------------------------------------------
# Request metadata
# ----------------------------------------------------------------------
def get_request_origin(request: Request) -> RequestOrigin:
    """Extract client provenance, honouring a reverse proxy's forwarding header."""
    forwarded = request.headers.get("x-forwarded-for")
    ip_address = (
        forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
    )
    return RequestOrigin(ip_address=ip_address, user_agent=request.headers.get("user-agent"))


def get_refresh_token_from_cookie(request: Request) -> str | None:
    """Read the refresh token from its HttpOnly cookie."""
    return request.cookies.get(settings.REFRESH_COOKIE_NAME)


Origin = Annotated[RequestOrigin, Depends(get_request_origin)]
RefreshCookie = Annotated[str | None, Depends(get_refresh_token_from_cookie)]


# ----------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    repository: UserRepo,
) -> User:
    """Resolve the authenticated user from the bearer access token.

    Authentication only -- authorization is the *separate* ``require()``
    dependency layered on top of this one, exactly as planned when this was
    written in Phase 1. That layering is why RBAC's arrival in Phase 15 did
    not change a single route signature.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("You need to sign in to continue.")

    payload = decode_access_token(credentials.credentials)
    user = await repository.get(get_subject_id(payload))

    if user is None:
        raise InvalidTokenError("The account linked to this session no longer exists.")
    if not user.is_active:
        raise AccountInactiveError()

    set_actor_id(user.id)
    return user


async def get_optional_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    repository: UserRepo,
) -> User | None:
    """Same as :func:`get_current_user` but tolerates anonymous callers."""
    if credentials is None or not credentials.credentials:
        return None
    try:
        return await get_current_user(credentials, repository)
    except AuthenticationError:
        return None


CurrentUser = Annotated[User, Depends(get_current_user)]


# ----------------------------------------------------------------------
# Authorization
# ----------------------------------------------------------------------
def get_authorization_service(session: DbSession) -> AuthorizationService:
    return AuthorizationService(session)


AuthzSvc = Annotated[AuthorizationService, Depends(get_authorization_service)]


def get_scope_service(session: DbSession, authorization: AuthzSvc) -> TeamScopeService:
    return TeamScopeService(session, authorization)


ScopeSvc = Annotated[TeamScopeService, Depends(get_scope_service)]


async def get_current_scope(
    user: CurrentUser, service: Annotated[TeamScopeService, Depends(get_scope_service)]
) -> EmployeeScope:
    """Whose records this request may reach.

    Resolved once and injected, rather than re-derived wherever it is needed:
    two derivations of the same rule are two chances for them to disagree, and
    the disagreement would be silent in exactly the direction that leaks data.
    """
    return await service.for_user(user)


CurrentScope = Annotated[EmployeeScope, Depends(get_current_scope)]


# ----------------------------------------------------------------------
# Employee self service
#
# The one dependency that turns "who is signed in" into "whose employee record
# is this". Every ``/me`` endpoint takes it, and none of them accept an employee
# id at all -- which is what makes an IDOR impossible there rather than merely
# guarded against.
# ----------------------------------------------------------------------
async def get_current_employee(user: CurrentUser, repository: EmployeeRepo) -> Employee:
    """The employee record behind the signed-in account.

    A 403 rather than a 404 when there is none: an account with no employee
    record -- an integration account, an IT administrator -- is a legitimate
    thing to be, and the honest answer is "the employee portal is not for this
    account", not "your profile is missing".
    """
    employee = await repository.get_by(user_id=user.id)
    if employee is None:
        raise PermissionDeniedError(
            "This account is not linked to an employee record, so the employee portal is unavailable.",
            details=[{"code": "no_employee_record", "message": "user_id"}],
        )
    return employee


#: Tag read by the RBAC coverage test. A ``/me`` route is not unguarded: it is
#: guarded by identity rather than by permission, because the subject of the
#: request is always the caller and there is no other record it can reach.
get_current_employee.__rbac_self_service__ = True  # type: ignore[attr-defined]

CurrentEmployee = Annotated[Employee, Depends(get_current_employee)]


async def get_self_scope(user: CurrentUser, employee: CurrentEmployee) -> EmployeeScope:
    """The scope a ``/me`` request runs in: this person, nobody else.

    Passed into the shared services so their existing scope checks do the
    enforcing. Self-service does not get its own copy of "may I see this row?".
    """
    return EmployeeScope.just_self(employee.id, user.id)


SelfScope = Annotated[EmployeeScope, Depends(get_self_scope)]


def get_self_service(
    session: DbSession,
    announcement_service: AnnouncementSvc,
    workforce: Annotated[WorkforceService, Depends(get_workforce_service)],
    documents: Annotated[DocumentService, Depends(get_document_service)],
    employees: Annotated[EmployeeService, Depends(get_employee_service)],
) -> SelfServiceService:
    """Composed from the modules it presents, never from their repositories.

    The portal owns no rules of its own: a check-in is the workforce module's
    check-in and an upload is the vault's upload. What it owns is the
    composition -- which of them a personal dashboard needs, and the fact that
    every one of them is called for the caller and only the caller.
    """
    return SelfServiceService(
        workforce=workforce,
        documents=documents,
        employees=employees,
        allocations=ProjectAllocationRepository(session),
        document_types=DocumentTypeRepository(session),
        notifications=NotificationRepository(session),
        announcements=announcement_service,
    )


SelfServiceSvc = Annotated[SelfServiceService, Depends(get_self_service)]


# ----------------------------------------------------------------------
# Manager and team management
#
# The manager screens run in a scope of their own: the caller's direct reports,
# and deliberately not the caller. It is resolved by the same service and the
# same query as ``CurrentScope`` -- there is one definition of "who reports to
# me" -- and differs only in which people the resulting scope admits.
# ----------------------------------------------------------------------
async def get_manager_scope(
    user: CurrentUser, service: Annotated[TeamScopeService, Depends(get_scope_service)]
) -> EmployeeScope:
    """Whose records a manager screen may reach: their reporting line, exactly.

    Narrower than :func:`get_current_scope` in two directions at once. It leaves
    the caller out, so a manager cannot approve their own leave through a team
    screen; and it applies to a holder of ``employees:view_all`` as well, so an
    HR administrator opening a team screen sees the team they actually manage
    rather than the company. Their organization-wide access is untouched on the
    HR screens, which is where it is meant to be used.
    """
    return await service.direct_reports_of(user)


ManagerScope = Annotated[EmployeeScope, Depends(get_manager_scope)]


def get_manager_service(
    session: DbSession,
    workforce: Annotated[WorkforceService, Depends(get_workforce_service)],
    employees: Annotated[EmployeeService, Depends(get_employee_service)],
    performance: Annotated[PerformanceService, Depends(get_performance_service)],
    documents: Annotated[DocumentService, Depends(get_document_service)],
) -> ManagerService:
    """Composed from the modules it presents, never from their repositories.

    The one exception is the allocation repository, for the same reason the
    employee portal takes it: what a team screen needs from Project Allocation
    is a set-shaped read of who is on what today, and asking the project service
    for it would mean adding a method there whose only caller is here.
    """
    return ManagerService(
        workforce=workforce,
        employees=employees,
        performance=performance,
        documents=documents,
        allocations=ProjectAllocationRepository(session),
    )


ManagerSvc = Annotated[ManagerService, Depends(get_manager_service)]


# ----------------------------------------------------------------------
# HR administration
#
# Composed from the modules it presents plus the repositories whose only use
# here is a COUNT. The authorization service is injected because the HR
# dashboard's sections are graduated by permission -- it *reads* the caller's
# permission set to decide which blocks to build, which is a use of the existing
# RBAC system rather than a second one.
# ----------------------------------------------------------------------
def get_hr_service(
    session: DbSession,
    authorization: AuthzSvc,
    employees: Annotated[EmployeeService, Depends(get_employee_service)],
    workforce: Annotated[WorkforceService, Depends(get_workforce_service)],
    documents: Annotated[DocumentService, Depends(get_document_service)],
    performance: Annotated[PerformanceService, Depends(get_performance_service)],
    projects: Annotated[ProjectService, Depends(get_project_service)],
    employee_repository: EmployeeRepo,
    document_repository: DocumentRepo,
    audit_log_repository: AuditLogRepo,
) -> HrService:
    return HrService(
        authorization=authorization,
        employees=employees,
        workforce=workforce,
        documents=documents,
        performance=performance,
        projects=projects,
        employee_repository=employee_repository,
        document_repository=document_repository,
        leave_requests=LeaveRequestRepository(session),
        regularizations=RegularizationRepository(session),
        analytics=WorkforceAnalyticsRepository(session),
        allocations=ProjectAllocationRepository(session),
        audit_logs=audit_log_repository,
        requisitions=RequisitionRepository(session),
        candidates=CandidateRepository(session),
        interviews=InterviewRepository(session),
        offers=OfferRepository(session),
        onboarding_cases=OnboardingCaseRepository(session),
    )


HrSvc = Annotated[HrService, Depends(get_hr_service)]


def require(*permissions: str, require_all: bool = True) -> Any:
    """Build a dependency that refuses the request unless the caller may make it.

    Used as a route-level dependency rather than a parameter, because the guard
    has no return value the handler wants::

        @router.get("/", dependencies=[require("employees:view")])

    The permission strings are validated **now**, at import time. A guard naming
    a permission that does not exist is unsatisfiable, and an unsatisfiable
    guard is indistinguishable from a correctly locked endpoint until somebody
    who should have access is refused.
    """
    assert_known(*permissions)

    async def _guard(user: CurrentUser, authorization: AuthzSvc) -> None:
        await authorization.assert_can(user, *permissions, require_all=require_all)

    # Tagged so the route table can be introspected: the coverage test walks
    # every route looking for this attribute, which is what stops a new endpoint
    # being merged without a guard.
    _guard.__rbac_permissions__ = tuple(permissions)  # type: ignore[attr-defined]
    _guard.__rbac_require_all__ = require_all  # type: ignore[attr-defined]
    return Depends(_guard)


def require_self_or(*escalating: str) -> Any:
    """Guard an ``/{employee_id}`` route: your own record, or your team's.

    Permissions answer "may you call this endpoint". They say nothing about
    *whose* row is being asked for, which is how an Employee-role account could
    read another person's leave balances and attendance simply by changing the
    id in the URL.

    This closes that at the route, where the identity check belongs -- the
    service still answers the question it was asked, it just no longer answers
    it for strangers. Three gates, in order:

    1. Your own record is always yours.
    2. Somebody else's needs one of ``escalating`` -- a manager's
       ``leave:approve``, HR's ``attendance:export``. Acting on other people's
       records is precisely what those permissions are for.
    3. Holding one is no longer enough on its own. The record must also be in
       the caller's :class:`~app.services.scope_service.EmployeeScope`, so a
       manager's ``leave:approve`` reaches their direct reports and stops there.
       ``employees:view_all`` -- HR, Super Admin -- makes the scope unrestricted
       and this gate a no-op.

    Gate 2 is kept rather than folded into gate 3 on purpose. Without it, an
    employee who happens to have direct reports but holds only the base Employee
    role would start seeing their reports' records, which is a widening, not the
    narrowing this function exists for.
    """
    assert_known(*escalating)

    async def _guard(
        employee_id: uuid.UUID,
        user: CurrentUser,
        authorization: AuthzSvc,
        scope: CurrentScope,
    ) -> None:
        if user.is_superuser or scope.is_self(employee_id):
            return

        held = await authorization.permissions_for(user)
        if not held.intersection(escalating):
            raise PermissionDeniedError(
                "You can only view your own record.",
                details=[{"code": "not_your_record", "message": "employee_id"}],
            )

        scope.assert_allows(employee_id)

    _guard.__rbac_permissions__ = tuple(escalating)  # type: ignore[attr-defined]
    _guard.__rbac_scope__ = "self_or_permission"  # type: ignore[attr-defined]
    return Depends(_guard)


def require_team_scope() -> Any:
    """Guard an ``/{employee_id}`` route that is already permission-guarded.

    The employee module's routes all sit behind ``employees:view`` or
    ``employees:update``, which four different seats hold for four different
    reasons. This adds the missing half: whichever of them is calling, the
    record has to be one they are entitled to -- their own, or somebody who
    reports to them -- unless they hold ``employees:view_all``.

    Used *alongside* ``require(...)``, never instead of it. On its own it would
    let anybody signed in reach their own profile through an endpoint whose
    permission they do not hold.
    """

    async def _guard(employee_id: uuid.UUID, scope: CurrentScope) -> None:
        scope.assert_allows(employee_id)

    _guard.__rbac_scope__ = "team"  # type: ignore[attr-defined]
    return Depends(_guard)


def require_org_wide(*permissions: str) -> Any:
    """Guard a screen that is about the whole organization rather than a team.

    The conjunction of "may you use this module" and "does the reporting line
    stop narrowing what you see" -- which is exactly what a name like
    ``attendance:view_all`` means. It is spelled as
    ``require("attendance:view", "employees:view_all")`` rather than as a
    permission of its own on purpose.

    ``employees:view_all`` is the platform's *only* scoping permission, and
    :mod:`app.services.scope_service` is built around there being one. A
    per-module ``view_all`` would mean a per-module scope resolver, two answers
    to "whose records may I reach", and a second RBAC system living beside the
    first. Grant or withhold ``employees:view_all`` and every HR screen widens
    or narrows together, which is the behaviour an administrator ticking one box
    is expecting.

    Note what this does *not* do: it grants nothing. An HR user who holds
    ``attendance:view`` but not ``employees:view_all`` is refused here and still
    sees their own attendance through ``/me`` and their team's through
    ``/manager`` -- the narrower screens are unaffected.
    """
    return require(*permissions, ORG_WIDE_PERMISSION)


def require_any(*permissions: str) -> Any:
    """Satisfied by holding any one of these. Use where an endpoint genuinely
    serves two audiences -- a list an approver and an applicant both read."""
    return require(*permissions, require_all=False)


OptionalUser = Annotated[User | None, Depends(get_optional_current_user)]
