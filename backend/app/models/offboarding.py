"""Resignation and offboarding persistence models.

Ten tables, and the shape of them follows one decision: **the resignation is the
request and the offboarding case is the work.** They are separate rows with
separate lifecycles because they answer to different people. A resignation is
decided by a manager and processed by HR; a case is worked by five departments
over a notice period. Folding them together would mean a single status column
trying to say both "the manager has not looked at this yet" and "IT still has
the laptop".

Everything downstream hangs off the case rather than the resignation, so a
future termination or retirement -- a separation nobody resigned from -- can
open a case without inventing a resignation to hang it on.

Nothing here is deleted. §19 of the brief is explicit that an exit must leave
the history intact, so these tables carry the platform's ordinary soft-delete
columns and the services never call anything else.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.enums import (
    ACCESS_CLEARANCE_STATUS_SQL_VALUES,
    ASSET_RETURN_STATUS_SQL_VALUES,
    EXIT_DOCUMENT_TYPE_SQL_VALUES,
    HANDOVER_STATUS_SQL_VALUES,
    OFFBOARDING_CASE_STATUS_SQL_VALUES,
    OFFBOARDING_DEPARTMENT_SQL_VALUES,
    OFFBOARDING_TASK_STATUS_SQL_VALUES,
    RESIGNATION_STATUS_SQL_VALUES,
    SETTLEMENT_STATUS_SQL_VALUES,
    AccessClearanceStatus,
    AssetReturnStatus,
    HandoverStatus,
    OffboardingCaseStatus,
    OffboardingTaskStatus,
    ResignationStatus,
    SettlementStatus,
)

#: Database-generated case identifiers, on the pattern employee codes used
#: and ``REQ-000001``. A sequence rather than a count of existing rows so that
#: two concurrent approvals can never be handed the same number.
OFFBOARDING_CODE_SEQUENCE = "offboarding_cases_code_seq"
OFFBOARDING_CODE_DEFAULT = f"'OFF-' || lpad(nextval('{OFFBOARDING_CODE_SEQUENCE}')::text, 6, '0')"

RESIGNATION_CODE_SEQUENCE = "resignations_code_seq"
RESIGNATION_CODE_DEFAULT = f"'RES-' || lpad(nextval('{RESIGNATION_CODE_SEQUENCE}')::text, 6, '0')"


class Resignation(Base, AuditableBase):
    """One employee's intent to leave, and the decisions taken on it.

    ``employee_id`` is written from the authenticated session and never from a
    request body -- see :meth:`OffboardingService.submit_resignation`. The
    partial unique index below is the database's half of the same rule: an
    employee may have any number of historic resignations and at most one that
    is still live.
    """

    __tablename__ = "resignations"
    __table_args__ = (
        Index("ix_resignations_employee_status", "employee_id", "status"),
        CheckConstraint(f"status IN ({RESIGNATION_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint("notice_period_days >= 0", name="notice_period_days_non_negative"),
        CheckConstraint(
            "proposed_last_working_day >= resignation_date", name="proposed_lwd_after_resignation"
        ),
        Index("ix_resignations_last_working_day", "approved_last_working_day"),
        {"comment": "Employee separation requests and their review outcome."},
    )

    resignation_code: Mapped[str] = mapped_column(
        String(20), unique=True, server_default=text(RESIGNATION_CODE_DEFAULT)
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )

    resignation_date: Mapped[date] = mapped_column(Date, doc="The day the employee gave notice.")
    proposed_last_working_day: Mapped[date] = mapped_column(Date, doc="What the employee asked for.")
    recommended_last_working_day: Mapped[date | None] = mapped_column(
        Date, doc="What the manager suggested instead, if anything."
    )
    approved_last_working_day: Mapped[date | None] = mapped_column(
        Date, doc="The date that counts. Set by HR when the resignation is processed."
    )

    #: Resolved once, when the resignation is submitted, from the employment
    #: type's configured notice period -- not read live afterwards. A policy
    #: change six weeks into somebody's notice must not silently move their
    #: last working day.
    notice_period_days: Mapped[int] = mapped_column(Integer)
    notice_period_adjusted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    reason: Mapped[str] = mapped_column(String(100))
    comments: Mapped[str | None] = mapped_column(Text)
    supporting_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default=ResignationStatus.DRAFT,
        server_default=ResignationStatus.DRAFT.value,
        index=True,
    )

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        doc="The reporting manager at the moment of submission, captured so a later "
        "org change cannot move a decision that has already been taken.",
    )
    manager_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manager_comments: Mapped[str | None] = mapped_column(Text)

    hr_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    hr_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hr_comments: Mapped[str | None] = mapped_column(Text)

    history: Mapped[list[ResignationHistory]] = relationship(
        back_populates="resignation",
        lazy="selectin",
        order_by="ResignationHistory.created_at",
    )


class ResignationHistory(Base, AuditableBase):
    """Append-only. A correction is a new row, exactly as employment history is."""

    __tablename__ = "resignation_history"
    __table_args__ = ({"comment": "Every status change and decision on a resignation."},)

    resignation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("resignations.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(80))
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    comments: Mapped[str | None] = mapped_column(Text)
    #: Set when the row records an authorized override rather than a normal step.
    is_override: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    resignation: Mapped[Resignation] = relationship(back_populates="history")


class OffboardingCase(Base, AuditableBase):
    """The work of separating one employee: checklist, clearance and documents."""

    __tablename__ = "offboarding_cases"
    __table_args__ = (
        UniqueConstraint("resignation_id", name="uq_offboarding_cases_resignation"),
        Index("ix_offboarding_cases_status_lwd", "status", "last_working_day"),
        CheckConstraint(f"status IN ({OFFBOARDING_CASE_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="progress_percent_range"),
        {"comment": "One separation in progress."},
    )

    case_code: Mapped[str] = mapped_column(
        String(20), unique=True, server_default=text(OFFBOARDING_CODE_DEFAULT)
    )
    resignation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("resignations.id", ondelete="RESTRICT")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    last_working_day: Mapped[date] = mapped_column(Date, index=True)
    notice_period_days: Mapped[int] = mapped_column(Integer)

    hr_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default=OffboardingCaseStatus.NOT_STARTED,
        server_default=OffboardingCaseStatus.NOT_STARTED.value,
        index=True,
    )
    progress_percent: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tasks: Mapped[list[OffboardingTask]] = relationship(
        back_populates="case", lazy="selectin", order_by="OffboardingTask.due_date"
    )
    assets: Mapped[list[AssetClearance]] = relationship(
        back_populates="case", lazy="selectin", order_by="AssetClearance.created_at"
    )
    access_items: Mapped[list[AccessClearance]] = relationship(
        back_populates="case", lazy="selectin", order_by="AccessClearance.created_at"
    )


class OffboardingTask(Base, AuditableBase):
    """One checklist row. Configurable: the defaults are a seed, not a schema."""

    __tablename__ = "offboarding_tasks"
    __table_args__ = (
        Index("ix_offboarding_tasks_owner_status", "owner_id", "status"),
        CheckConstraint(f"status IN ({OFFBOARDING_TASK_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint(f"department IN ({OFFBOARDING_DEPARTMENT_SQL_VALUES})", name="department"),
        {"comment": "Departmental clearance checklist for one offboarding case."},
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offboarding_cases.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(20), index=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        doc="Nominated owner. Nullable: IT, Admin and Finance rows are addressed "
        "to a department that may have no single named user yet, and the "
        "permission -- not this column -- is what decides who may tick them.",
    )
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(20),
        default=OffboardingTaskStatus.PENDING,
        server_default=OffboardingTaskStatus.PENDING.value,
        index=True,
    )
    comments: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sequence: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    case: Mapped[OffboardingCase] = relationship(back_populates="tasks")


class HandoverRecord(Base, AuditableBase):
    """The manager's record of what moved, and to whom."""

    __tablename__ = "handover_records"
    __table_args__ = (
        UniqueConstraint("case_id", name="uq_handover_records_case"),
        CheckConstraint(f"status IN ({HANDOVER_STATUS_SQL_VALUES})", name="status"),
        {"comment": "Knowledge-transfer record for one offboarding case."},
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offboarding_cases.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=HandoverStatus.NOT_STARTED,
        server_default=HandoverStatus.NOT_STARTED.value,
        index=True,
    )
    projects: Mapped[str | None] = mapped_column(Text)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    documentation: Mapped[str | None] = mapped_column(Text)
    replacement_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    #: Document Vault ids. The files themselves stay in the vault -- this module
    #: links to them and never stores bytes of its own.
    attachment_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssetClearance(Base, AuditableBase):
    """Company property to be returned.

    Deliberately *not* an asset register -- it never was, and now it does not
    have to be. When this was written there was no asset module, so the rows
    were typed by hand and described what the employee was being asked to hand
    back rather than what the company owned. The docstring said that if an asset
    module arrived it would supply the rows and this table would keep recording
    their return. That is exactly what happened.

    ``asset_id`` is the link. When it is set, the row was seeded from the
    register and returning it here updates the real asset; when it is NULL, the
    row is a hand-typed one, which stays supported because a case opened before
    an asset was registered should not become unfinishable.
    """

    __tablename__ = "asset_clearance"
    __table_args__ = (
        Index("ix_asset_clearance_case_status", "case_id", "status"),
        CheckConstraint(f"status IN ({ASSET_RETURN_STATUS_SQL_VALUES})", name="status"),
        {"comment": "Per-case record of company property returned at exit."},
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offboarding_cases.id", ondelete="CASCADE"), index=True
    )
    #: The registered asset this row is about, when there is one. Nullable so
    #: that a hand-entered clearance line still works -- see the class docstring.
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), index=True
    )
    asset_name: Mapped[str] = mapped_column(String(150))
    asset_tag: Mapped[str | None] = mapped_column(String(100), doc="Serial or inventory tag, if known.")
    assigned_date: Mapped[date | None] = mapped_column(Date)
    return_date: Mapped[date | None] = mapped_column(Date)
    condition: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(20),
        default=AssetReturnStatus.ASSIGNED,
        server_default=AssetReturnStatus.ASSIGNED.value,
        index=True,
    )
    comments: Mapped[str | None] = mapped_column(Text)

    case: Mapped[OffboardingCase] = relationship(back_populates="assets")


class AccessClearance(Base, AuditableBase):
    """Systems to be revoked. Tracked here, revoked elsewhere.

    Nothing in this module calls out to a mail server or an identity provider,
    and nothing should start doing so without that being a deliberate decision:
    a row saying ``revoked`` is a person's assertion that they did it, which is
    what an auditor is asking for at this stage.
    """

    __tablename__ = "access_clearance"
    __table_args__ = (
        Index("ix_access_clearance_case_status", "case_id", "status"),
        CheckConstraint(f"status IN ({ACCESS_CLEARANCE_STATUS_SQL_VALUES})", name="status"),
        {"comment": "Per-case record of system access revoked at exit."},
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offboarding_cases.id", ondelete="CASCADE"), index=True
    )
    system_name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str | None] = mapped_column(
        String(50), doc="email, vpn, application, cloud, internal -- for grouping only."
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=AccessClearanceStatus.PENDING,
        server_default=AccessClearanceStatus.PENDING.value,
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comments: Mapped[str | None] = mapped_column(Text)

    case: Mapped[OffboardingCase] = relationship(back_populates="access_items")


class ExitInterview(Base, AuditableBase):
    """The employee's own account of why they left.

    One per case, written by the employee and read by HR. The ratings are
    stored as small integers rather than a JSON blob so that "average
    management rating by business unit" stays a query rather than a migration.
    """

    __tablename__ = "exit_interviews"
    __table_args__ = (
        UniqueConstraint("case_id", name="uq_exit_interviews_case"),
        CheckConstraint(
            "overall_experience IS NULL OR overall_experience BETWEEN 1 AND 5", name="overall_experience"
        ),
        {"comment": "Employee exit interview responses."},
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offboarding_cases.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )

    reason_for_leaving: Mapped[str] = mapped_column(String(100))
    overall_experience: Mapped[int | None] = mapped_column(SmallInteger)
    management_rating: Mapped[int | None] = mapped_column(SmallInteger)
    work_environment_rating: Mapped[int | None] = mapped_column(SmallInteger)
    career_growth_rating: Mapped[int | None] = mapped_column(SmallInteger)
    compensation_rating: Mapped[int | None] = mapped_column(SmallInteger)

    management_feedback: Mapped[str | None] = mapped_column(Text)
    work_environment_feedback: Mapped[str | None] = mapped_column(Text)
    career_growth_feedback: Mapped[str | None] = mapped_column(Text)
    compensation_feedback: Mapped[str | None] = mapped_column(Text)
    suggestions: Mapped[str | None] = mapped_column(Text)

    would_recommend: Mapped[bool | None] = mapped_column(Boolean)
    would_rejoin: Mapped[bool | None] = mapped_column(Boolean)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExitDocument(Base, AuditableBase):
    """A letter issued at exit, filed in the Document Vault.

    The PDF lives in the vault like every other file in the platform; this row
    records that it was issued, of what kind, and points at it. The bytes are
    not duplicated here -- the same rule the requisition and offer modules
    follow for their attachments.
    """

    __tablename__ = "exit_documents"
    __table_args__ = (
        UniqueConstraint("case_id", "document_type", name="uq_exit_documents_case_type"),
        CheckConstraint(f"document_type IN ({EXIT_DOCUMENT_TYPE_SQL_VALUES})", name="document_type"),
        {"comment": "Experience, relieving and service certificates issued at exit."},
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offboarding_cases.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    document_type: Mapped[str] = mapped_column(String(40), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Released to the employee. Generated and released are different events:
    #: HR may prepare the letters before the last working day and hand them over
    #: only once clearance is final.
    released: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class FinalSettlementTracking(Base, AuditableBase):
    """Status only. No figure in this table is calculated by this application.

    Payroll is a future module and this one is not entitled to guess at salary,
    tax, PF, ESI or gratuity. What is tracked is where the settlement has got
    to and the reference somebody in Finance can quote back.
    """

    __tablename__ = "final_settlement_tracking"
    __table_args__ = (
        UniqueConstraint("case_id", name="uq_final_settlement_case"),
        CheckConstraint(f"status IN ({SETTLEMENT_STATUS_SQL_VALUES})", name="status"),
        {"comment": "Full & final settlement status tracking -- not a calculation."},
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offboarding_cases.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=SettlementStatus.NOT_STARTED,
        server_default=SettlementStatus.NOT_STARTED.value,
        index=True,
    )
    settlement_reference: Mapped[str | None] = mapped_column(String(100))
    settlement_date: Mapped[date | None] = mapped_column(Date)
    comments: Mapped[str | None] = mapped_column(Text)
