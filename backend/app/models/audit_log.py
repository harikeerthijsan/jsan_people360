"""Append-only audit trail."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.mixins import AuditableBase


class AuditAction(StrEnum):
    """Canonical audit actions.

    Feature modules extend the trail by passing their own dotted string
    (``"employee.created"``); this enum only fixes the platform-level events.
    """

    LOGIN_SUCCEEDED = "auth.login.succeeded"
    LOGIN_FAILED = "auth.login.failed"
    LOGIN_BLOCKED = "auth.login.blocked"
    LOGOUT = "auth.logout"
    TOKEN_REFRESHED = "auth.token.refreshed"
    TOKEN_REUSE_DETECTED = "auth.token.reuse_detected"
    PASSWORD_RESET_REQUESTED = "auth.password.reset_requested"
    PASSWORD_RESET_COMPLETED = "auth.password.reset_completed"
    PASSWORD_CHANGED = "auth.password.changed"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_ACTIVATED = "user.activated"
    USER_DEACTIVATED = "user.deactivated"
    USER_ARCHIVED = "user.archived"
    USER_RESTORED = "user.restored"
    USER_PASSWORD_RESET = "user.password.reset_by_admin"
    USER_PROFILE_UPDATED = "user.profile.updated"

    EMPLOYEE_CREATED = "employee.created"
    EMPLOYEE_UPDATED = "employee.updated"
    EMPLOYEE_CONFIRMED = "employee.confirmed"
    EMPLOYEE_PROMOTED = "employee.promoted"
    EMPLOYEE_TRANSFERRED = "employee.department.transferred"
    EMPLOYEE_DESIGNATION_CHANGED = "employee.designation.changed"
    EMPLOYEE_MANAGER_CHANGED = "employee.manager.changed"
    EMPLOYEE_LOCATION_CHANGED = "employee.location.changed"
    EMPLOYEE_STATUS_CHANGED = "employee.status.changed"
    EMPLOYEE_ARCHIVED = "employee.archived"
    EMPLOYEE_RESTORED = "employee.restored"
    EMPLOYEE_BANK_UPDATED = "employee.bank.updated"
    EMPLOYEE_IDENTIFICATION_UPDATED = "employee.identification.updated"
    #: Reading unmasked bank and identity details. Recorded because the reveal is
    #: the moment the protection is lifted, and an unaudited reveal makes the
    #: masking everywhere else decorative.
    EMPLOYEE_SENSITIVE_VIEWED = "employee.sensitive.viewed"
    EMPLOYEE_EXPORTED = "employee.exported"

    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_VERSION_UPLOADED = "document.version.uploaded"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_REVIEWED = "document.reviewed"
    DOCUMENT_ARCHIVED = "document.archived"
    DOCUMENT_RESTORED = "document.restored"
    #: Downloading and previewing are recorded separately: previewing is
    #: browsing, downloading takes a copy out of the vault to somewhere none of
    #: these controls reach, and an access review cares about the difference.
    DOCUMENT_DOWNLOADED = "document.downloaded"
    DOCUMENT_PREVIEWED = "document.previewed"

    # -- Performance management -------------------------------------
    PERFORMANCE_CYCLE_CREATED = "performance.cycle.created"
    PERFORMANCE_CYCLE_UPDATED = "performance.cycle.updated"
    GOAL_ASSIGNED = "performance.goal.assigned"
    GOAL_UPDATED = "performance.goal.updated"
    GOAL_PROGRESS_RECORDED = "performance.goal.progress"
    SELF_REVIEW_SUBMITTED = "performance.self_review.submitted"
    MANAGER_REVIEW_SUBMITTED = "performance.manager_review.submitted"
    PERFORMANCE_FINALISED = "performance.finalised"
    RECOGNITION_ADDED = "performance.recognition.added"
    FEEDBACK_ADDED = "performance.feedback.added"

    # -- Access control ---------------------------------------------
    ROLE_CREATED = "rbac.role.created"
    ROLE_UPDATED = "rbac.role.updated"
    ROLE_DELETED = "rbac.role.deleted"
    USER_ROLES_ASSIGNED = "rbac.user.roles_assigned"
    PERMISSION_DENIED = "rbac.permission.denied"

    # -- Workforce operations ---------------------------------------
    SHIFT_CREATED = "workforce.shift.created"
    SHIFT_UPDATED = "workforce.shift.updated"
    SHIFT_ASSIGNED = "workforce.shift.assigned"
    ATTENDANCE_CHECKED_IN = "workforce.attendance.checked_in"
    ATTENDANCE_CHECKED_OUT = "workforce.attendance.checked_out"
    REGULARIZATION_REQUESTED = "workforce.regularization.requested"
    REGULARIZATION_DECIDED = "workforce.regularization.decided"
    LEAVE_TYPE_CREATED = "workforce.leave_type.created"
    LEAVE_APPLIED = "workforce.leave.applied"
    LEAVE_DECIDED = "workforce.leave.decided"
    LEAVE_CANCELLED = "workforce.leave.cancelled"
    HOLIDAY_CALENDAR_CREATED = "workforce.holiday_calendar.created"
    TIMESHEET_SAVED = "workforce.timesheet.saved"
    TIMESHEET_SUBMITTED = "workforce.timesheet.submitted"
    TIMESHEET_DECIDED = "workforce.timesheet.decided"

    # -- HR administration ------------------------------------------
    #
    # Deliberately distinct from the ordinary actions above rather than reusing
    # them with a flag. "HR amended this day" and "the employee checked out" are
    # not the same event, and anyone reading the trail six months later is
    # almost always looking for exactly the first kind.
    LEAVE_TYPE_UPDATED = "workforce.leave_type.updated"
    LEAVE_BALANCE_ADJUSTED = "workforce.leave_balance.adjusted"
    LEAVE_DECISION_OVERRIDDEN = "workforce.leave.decision_overridden"
    ATTENDANCE_CORRECTED = "workforce.attendance.corrected"
    TIMESHEET_DECISION_OVERRIDDEN = "workforce.timesheet.decision_overridden"
    HR_REPORT_EXPORTED = "hr.report.exported"
    AUDIT_TRAIL_EXPORTED = "audit.trail.exported"

    # -- Resignation and offboarding --------------------------------
    #
    # A separation is the one workflow where the trail is read back years
    # later -- by the person who left, by whoever verifies their employment, or
    # by a tribunal -- so each step is its own action rather than a generic
    # "updated" with the interesting part buried in the context blob.
    #
    # The three overrides at the end exist because §18 of the brief requires
    # administrative overrides to be auditable *as overrides*: an admin
    # rewriting a last working day and HR settling one through the normal step
    # are the same column change and a completely different fact.
    RESIGNATION_SUBMITTED = "offboarding.resignation.submitted"
    RESIGNATION_WITHDRAWN = "offboarding.resignation.withdrawn"
    RESIGNATION_MANAGER_DECIDED = "offboarding.resignation.manager_decided"
    RESIGNATION_PROCESSED = "offboarding.resignation.processed"
    RESIGNATION_CANCELLED = "offboarding.resignation.cancelled"
    LAST_WORKING_DAY_CHANGED = "offboarding.last_working_day.changed"
    NOTICE_PERIOD_ADJUSTED = "offboarding.notice_period.adjusted"
    OFFBOARDING_CASE_CREATED = "offboarding.case.created"
    OFFBOARDING_TASK_UPDATED = "offboarding.task.updated"
    OFFBOARDING_HANDOVER_RECORDED = "offboarding.handover.recorded"
    OFFBOARDING_ASSET_UPDATED = "offboarding.asset.updated"
    OFFBOARDING_ACCESS_UPDATED = "offboarding.access.updated"
    EXIT_INTERVIEW_SUBMITTED = "offboarding.exit_interview.submitted"
    EXIT_DOCUMENT_GENERATED = "offboarding.exit_document.generated"
    SETTLEMENT_STATUS_UPDATED = "offboarding.settlement.updated"
    OFFBOARDING_COMPLETED = "offboarding.completed"
    EMPLOYEE_EXITED = "offboarding.employee.exited"
    OFFBOARDING_OVERRIDDEN = "offboarding.admin.overridden"

    # -- Asset management -------------------------------------------
    #
    # Custody is the point of these. "Who had this laptop in March" is the
    # question an asset trail exists to answer, and it is asked long after the
    # thing itself has been disposed of -- so every change of hands is its own
    # action rather than a generic update with the interesting part in a blob.
    ASSET_CREATED = "asset.created"
    ASSET_UPDATED = "asset.updated"
    ASSET_ASSIGNED = "asset.assigned"
    ASSET_RETURNED = "asset.returned"
    ASSET_TRANSFERRED = "asset.transferred"
    ASSET_STATUS_CHANGED = "asset.status_changed"
    ASSET_MAINTENANCE_STARTED = "asset.maintenance.started"
    ASSET_MAINTENANCE_COMPLETED = "asset.maintenance.completed"
    ASSET_RETIRED = "asset.retired"
    ASSET_DISPOSED = "asset.disposed"
    ASSET_CLEARANCE_WAIVED = "asset.clearance.waived"
    ASSET_CATEGORY_CHANGED = "asset.category.changed"
    ASSET_EXPORTED = "asset.exported"

    # -- Helpdesk ---------------------------------------------------
    TICKET_RAISED = "helpdesk.ticket.raised"
    TICKET_ASSIGNED = "helpdesk.ticket.assigned"
    TICKET_STATUS_CHANGED = "helpdesk.ticket.status_changed"
    TICKET_COMMENTED = "helpdesk.ticket.commented"
    TICKET_RESOLVED = "helpdesk.ticket.resolved"
    TICKET_REOPENED = "helpdesk.ticket.reopened"
    TICKET_CLOSED = "helpdesk.ticket.closed"
    TICKET_CATEGORY_CHANGED = "helpdesk.category.changed"

    # -- Announcements ----------------------------------------------
    #
    # Publishing is audited separately from creating: one is a draft nobody has
    # seen, the other is a statement made to the whole company, and the second
    # is the one anybody asks about afterwards.
    ANNOUNCEMENT_CREATED = "announcement.created"
    ANNOUNCEMENT_UPDATED = "announcement.updated"
    ANNOUNCEMENT_PUBLISHED = "announcement.published"
    ANNOUNCEMENT_ARCHIVED = "announcement.archived"
    ANNOUNCEMENT_DELETED = "announcement.deleted"

    SETTING_UPDATED = "settings.updated"

    # -- Payroll ------------------------------------------------------
    #
    # Salary is the record most likely to be asked about years later, by the
    # person it pays or by an auditor, so every configuration change and every
    # assignment is its own action. The compensation events carry the previous
    # and new CTC in their context — that pair is the point of the entry —
    # and nothing else: no component breakdown, no bank detail.
    SALARY_STRUCTURE_CREATED = "payroll.structure.created"
    SALARY_STRUCTURE_UPDATED = "payroll.structure.updated"
    SALARY_STRUCTURE_STATUS_CHANGED = "payroll.structure.status_changed"
    SALARY_COMPONENT_CREATED = "payroll.component.created"
    SALARY_COMPONENT_UPDATED = "payroll.component.updated"
    SALARY_COMPONENT_STATUS_CHANGED = "payroll.component.status_changed"
    COMPENSATION_ASSIGNED = "payroll.compensation.assigned"
    SALARY_REVISED = "payroll.compensation.revised"

    # -- Payroll configuration ----------------------------------------
    #
    # Configuration changes are the entries somebody reads when a future
    # payroll run produces a surprising number: "who changed the rounding
    # rule, when, and why". Each carries the changed field names and the
    # stated reason; the field-level previous/new values live in
    # payroll_configuration_history, which is the record of the values
    # themselves rather than of the act.
    PAYROLL_CONFIG_UPDATED = "payroll.config.updated"
    PAYROLL_PERIOD_CREATED = "payroll.period.created"
    PAYROLL_PERIOD_UPDATED = "payroll.period.updated"
    PAYROLL_PERIOD_STATUS_CHANGED = "payroll.period.status_changed"
    PAYROLL_LEAVE_RULE_CHANGED = "payroll.leave_rule.changed"
    EMPLOYEE_PAYROLL_SETTINGS_CHANGED = "payroll.employee_settings.changed"

    # -- Payroll inputs (Phase 3) --------------------------------------
    #
    # Preparation and review are separate acts by possibly separate people,
    # and the flag entry exists because "the source data changed after the
    # snapshot" is precisely the fact an auditor of a wrong payroll asks
    # about. Contexts carry counts and reasons, never salary figures.
    PAYROLL_INPUTS_PREPARED = "payroll.inputs.prepared"
    PAYROLL_INPUT_REVIEWED = "payroll.input.reviewed"
    PAYROLL_INPUTS_FLAGGED = "payroll.inputs.flagged"

    # -- Payroll runs (Phase 4) ----------------------------------------
    #
    # Calculation and recalculation are separate entries because "the numbers
    # were computed" and "the numbers were computed AGAIN" are different facts
    # to an auditor of a payroll dispute. Contexts carry counts and statuses,
    # never amounts.
    PAYROLL_RUN_CREATED = "payroll.run.created"
    PAYROLL_RUN_CALCULATED = "payroll.run.calculated"
    PAYROLL_RUN_RECALCULATED = "payroll.run.recalculated"

    # -- Payroll review (Phase 5) ---------------------------------------
    #
    # Review is where humans change what payroll will pay, so every act is
    # its own entry: who resolved which exception, who added which
    # adjustment and why, who ticked the checklist, who declared the review
    # complete. Contexts carry reasons and adjustment amounts (they are the
    # substance of the act), never whole payslips.
    PAYROLL_EXCEPTION_RESOLVED = "payroll.exception.resolved"
    PAYROLL_ADJUSTMENT_CREATED = "payroll.adjustment.created"
    PAYROLL_ADJUSTMENT_CANCELLED = "payroll.adjustment.cancelled"
    PAYROLL_RECORD_REVIEW_MARKED = "payroll.record.review_marked"
    PAYROLL_CHECKLIST_UPDATED = "payroll.review.checklist_updated"
    PAYROLL_REVIEW_COMPLETED = "payroll.review.completed"
    PAYROLL_REVIEW_COMMENTED = "payroll.review.commented"

    # -- Payroll approval and finalization (Phase 6) --------------------
    #
    # The official sign-off trail. Submission, approval, send-back and
    # finalization each carry actor, comment/reason and the run's totals at
    # that moment. The locked-modification entry records that somebody tried
    # to change a frozen run — written on the failure path and preserved
    # through the request's rollback.
    PAYROLL_RUN_SUBMITTED = "payroll.run.submitted_for_approval"
    PAYROLL_RUN_APPROVED = "payroll.run.approved"
    PAYROLL_RUN_RETURNED = "payroll.run.returned"
    PAYROLL_RUN_FINALIZED = "payroll.run.finalized"
    PAYROLL_LOCKED_MODIFICATION = "payroll.run.locked_modification_attempt"

    # -- Payslips (Phase 7) ----------------------------------------------
    #
    # Who generated, regenerated, viewed (as an administrator) or downloaded
    # which payslip, and who was refused one that was not theirs. Contexts
    # carry payslip numbers and employee ids, never amounts.
    PAYSLIP_GENERATED = "payroll.payslip.generated"
    PAYSLIP_REGENERATED = "payroll.payslip.regenerated"
    PAYSLIP_VIEWED = "payroll.payslip.viewed"
    PAYSLIP_DOWNLOADED = "payroll.payslip.downloaded"
    PAYSLIP_ACCESS_DENIED = "payroll.payslip.access_denied"

    # -- Payroll reports and full & final settlement (Phase 8) ------------
    #
    # Reports: who looked at, and who exported, which report with which
    # filters. Settlements: every workflow act with its actor and reason;
    # the locked-modification entry is written on the failure path.
    PAYROLL_REPORT_GENERATED = "payroll.report.generated"
    PAYROLL_REPORT_EXPORTED = "payroll.report.exported"
    SETTLEMENT_CREATED = "payroll.settlement.created"
    SETTLEMENT_UPDATED = "payroll.settlement.updated"
    SETTLEMENT_CALCULATED = "payroll.settlement.calculated"
    SETTLEMENT_ADJUSTMENT_ADDED = "payroll.settlement.adjustment_added"
    SETTLEMENT_ADJUSTMENT_DECIDED = "payroll.settlement.adjustment_decided"
    SETTLEMENT_SUBMITTED = "payroll.settlement.submitted"
    SETTLEMENT_REVIEWED = "payroll.settlement.review_completed"
    SETTLEMENT_APPROVED = "payroll.settlement.approved"
    SETTLEMENT_REOPENED = "payroll.settlement.reopened"
    SETTLEMENT_FINALIZED = "payroll.settlement.finalized"
    SETTLEMENT_LOCKED_MODIFICATION = "payroll.settlement.locked_modification_attempt"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class AuditLog(Base, AuditableBase):
    """One immutable record of a security- or data-relevant event."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_action_created_at", "action", "created_at"),
        {"comment": "Append-only trail of security and data events."},
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="User who performed the action; NULL for anonymous or system events.",
    )
    actor_email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
        doc="Denormalised so the trail survives the actor being deleted.",
    )

    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AuditOutcome.SUCCESS,
        server_default=AuditOutcome.SUCCESS.value,
    )

    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Structured, non-sensitive detail (changed fields, reason codes).",
    )

    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action!r} outcome={self.outcome!r}>"
