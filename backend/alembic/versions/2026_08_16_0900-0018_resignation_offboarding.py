"""Resignation & offboarding: ten tables, fifteen permissions and a notice period.

Revision ID: 0018_resignation_offboarding
Revises: 0017_hr_administration
Create Date: 2026-08-16 09:00:00

Three things, and the third is the one worth reading.

**Ten tables**, split so that the resignation is the *request* and the
offboarding case is the *work*. They have different lifecycles because they
answer to different people -- a manager decides a resignation, five departments
work a case -- and a single status column cannot honestly say both "the manager
has not looked at this" and "IT still has the laptop".

**Fifteen permissions across four modules.** ``resignation`` carries a
``process`` action that no other module has, and ``offboarding``,
``exit_interview`` and ``exit_documents`` carry ``manage``. Both are new
actions, and both exist to keep a distinction the brief is explicit about:
approving a resignation is the *manager's* decision about their own team, and
processing one -- settling the last working day, opening the case, issuing the
letters -- is HR's. Collapsing them into ``update`` would mean either a manager
who can start an offboarding or an HR user who can decide a team's
resignations. HR Admin is therefore granted every resignation action **except**
``approve``, which is the same subtraction 0017 made for the workforce modules
and for the same reason.

**A notice period that is configuration rather than a constant.** §6 of the
brief says not to hardcode one, and nothing in the schema held it: ``employees``
knows a joining date and an employment type, and neither says how much notice a
person owes. ``employment_types.notice_period_days`` is where it belongs --
a consultant's notice and a full-time employee's differ, and that difference is
a property of the contract, not of the person. It is nullable on purpose: NULL
means "not configured" and falls back to a named default, which is a different
statement from 0, meaning "no notice required".

Seeded values are set for the five employment types 0002 creates. They are a
starting configuration, not a policy this code depends on -- every one of them
is editable on the Organization screens.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.permissions import MODULES_BY_KEY, SYSTEM_ROLES, PermissionAction, action_label, code

revision: str = "0018_resignation_offboarding"
down_revision: str | None = "0017_hr_administration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESIGNATION_CODE_SEQUENCE = "resignations_code_seq"
OFFBOARDING_CODE_SEQUENCE = "offboarding_cases_code_seq"

#: Dropped in reverse dependency order.
_TABLES = (
    "final_settlement_tracking",
    "exit_documents",
    "exit_interviews",
    "access_clearance",
    "asset_clearance",
    "handover_records",
    "offboarding_tasks",
    "offboarding_cases",
    "resignation_history",
    "resignations",
)

#: The four new modules. Descriptions are what an administrator reads on the
#: roles screen before ticking a box, so each says what the power *is*.
_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "resignation:view": "See resignation requests, subject to the reporting line.",
    "resignation:create": "Record a resignation on behalf of an employee. Employees submit their own "
    "through self-service and need no permission for it.",
    "resignation:update": "Amend a resignation that has not been completed.",
    "resignation:approve": "Approve or reject a direct report's resignation. The manager's decision; "
    "reaches their own team and stops there.",
    "resignation:process": "HR's step: verify the notice period, settle the last working day and open "
    "the offboarding case. Distinct from approving one.",
    "resignation:export": "Export the resignation register.",
    "offboarding:view": "See offboarding cases and their clearance progress.",
    "offboarding:create": "Open an offboarding case directly, without a resignation behind it.",
    "offboarding:update": "Complete checklist tasks and record a handover. What a manager or a "
    "department owner needs to tick their own rows.",
    "offboarding:manage": "Administer any case: reassign tasks, record asset and access clearance, "
    "update settlement status and complete the offboarding.",
    "offboarding:export": "Export offboarding and clearance reports.",
    "exit_interview:view": "Read completed exit interviews.",
    "exit_interview:manage": "Administer exit interviews across the organization.",
    "exit_documents:view": "See which exit documents have been issued.",
    "exit_documents:manage": "Generate and release experience letters, relieving letters and service "
    "certificates.",
}

_NEW_MODULES = ("resignation", "offboarding", "exit_interview", "exit_documents")

#: code, notice days. Set for what 0002 seeds; a code that is absent is skipped.
_NOTICE_DEFAULTS: tuple[tuple[str, int], ...] = (
    ("FULL_TIME", 60),
    ("CONTRACT", 30),
    ("CONSULTANT", 30),
    ("INTERNSHIP", 15),
    ("FREELANCER", 15),
)


def upgrade() -> None:
    _create_sequences()
    _create_tables()
    _add_notice_period()
    _add_permissions()
    _grant_permissions()


# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------
def _create_sequences() -> None:
    """``OFF-000001`` and ``RES-000001`` come from a sequence, like every other
    generated identifier here: two concurrent approvals must never be handed the
    same number, and ``max(code) + 1`` cannot promise that."""
    op.execute(f"CREATE SEQUENCE {RESIGNATION_CODE_SEQUENCE} AS bigint START WITH 1")
    op.execute(f"CREATE SEQUENCE {OFFBOARDING_CODE_SEQUENCE} AS bigint START WITH 1")


def _audit_columns() -> list[sa.Column[object]]:
    """The platform's audit contract.

    NOTE: no ``use_alter`` on the actor foreign keys. Inside ``op.create_table``
    SQLAlchemy silently *omits* a constraint marked that way -- the trap 0014
    documents -- so the columns would exist with nothing enforcing them.
    """
    return [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.UUID(), nullable=True),
    ]


def _actor_constraints(table: str) -> list[sa.schema.SchemaItem]:
    return [
        sa.ForeignKeyConstraint(
            [column], ["users.id"], name=f"fk_{table}_{column}_users", ondelete="SET NULL"
        )
        for column in ("created_by", "updated_by", "deleted_by")
    ]


def _create_tables() -> None:
    op.create_table(
        "resignations",
        sa.Column(
            "resignation_code",
            sa.String(length=20),
            server_default=sa.text(f"'RES-' || lpad(nextval('{RESIGNATION_CODE_SEQUENCE}')::text, 6, '0')"),
            nullable=False,
        ),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("resignation_date", sa.Date(), nullable=False),
        sa.Column("proposed_last_working_day", sa.Date(), nullable=False),
        sa.Column("recommended_last_working_day", sa.Date(), nullable=True),
        sa.Column("approved_last_working_day", sa.Date(), nullable=True),
        sa.Column("notice_period_days", sa.Integer(), nullable=False),
        sa.Column("notice_period_adjusted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("supporting_document_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="draft", nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manager_id", sa.UUID(), nullable=True),
        sa.Column("manager_decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manager_comments", sa.Text(), nullable=True),
        sa.Column("hr_owner_id", sa.UUID(), nullable=True),
        sa.Column("hr_processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hr_comments", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_resignations"),
        sa.UniqueConstraint("resignation_code", name="uq_resignations_resignation_code"),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name="fk_resignations_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"], ["employees.id"], name="fk_resignations_manager_id_employees",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["hr_owner_id"], ["users.id"], name="fk_resignations_hr_owner_id_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["supporting_document_id"], ["documents.id"],
            name="fk_resignations_supporting_document_id_documents", ondelete="SET NULL",
        ),
        *_actor_constraints("resignations"),
        sa.CheckConstraint(
            "status IN ('draft','submitted','manager_review','hr_review','approved','rejected',"
            "'withdrawn','notice_period','clearance','exit_interview','completed','cancelled')",
            name="ck_resignations_status",
        ),
        sa.CheckConstraint("notice_period_days >= 0", name="ck_resignations_notice_period_days_non_negative"),
        sa.CheckConstraint(
            "proposed_last_working_day >= resignation_date",
            name="ck_resignations_proposed_lwd_after_resignation",
        ),
        comment="Employee separation requests and their review outcome.",
    )
    op.create_index("ix_resignations_employee_id", "resignations", ["employee_id"])
    op.create_index("ix_resignations_status", "resignations", ["status"])
    op.create_index("ix_resignations_deleted_at", "resignations", ["deleted_at"])
    op.create_index("ix_resignations_employee_status", "resignations", ["employee_id", "status"])
    op.create_index("ix_resignations_last_working_day", "resignations", ["approved_last_working_day"])
    # One live resignation per employee. The service refuses a second one with a
    # readable message; this is the half that holds when two requests race.
    op.execute(
        "CREATE UNIQUE INDEX uq_resignations_one_live_per_employee ON resignations(employee_id)"
        " WHERE deleted_at IS NULL AND status NOT IN"
        " ('rejected','withdrawn','completed','cancelled')"
    )

    op.create_table(
        "resignation_history",
        sa.Column("resignation_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("is_override", sa.Boolean(), server_default="false", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_resignation_history"),
        sa.ForeignKeyConstraint(
            ["resignation_id"], ["resignations.id"],
            name="fk_resignation_history_resignation_id_resignations", ondelete="CASCADE",
        ),
        *_actor_constraints("resignation_history"),
        comment="Every status change and decision on a resignation.",
    )
    op.create_index("ix_resignation_history_resignation_id", "resignation_history", ["resignation_id"])
    op.create_index("ix_resignation_history_deleted_at", "resignation_history", ["deleted_at"])

    op.create_table(
        "offboarding_cases",
        sa.Column(
            "case_code",
            sa.String(length=20),
            server_default=sa.text(f"'OFF-' || lpad(nextval('{OFFBOARDING_CODE_SEQUENCE}')::text, 6, '0')"),
            nullable=False,
        ),
        sa.Column("resignation_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("last_working_day", sa.Date(), nullable=False),
        sa.Column("notice_period_days", sa.Integer(), nullable=False),
        sa.Column("hr_owner_id", sa.UUID(), nullable=True),
        sa.Column("manager_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="not_started", nullable=False),
        sa.Column("progress_percent", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_offboarding_cases"),
        sa.UniqueConstraint("case_code", name="uq_offboarding_cases_case_code"),
        sa.UniqueConstraint("resignation_id", name="uq_offboarding_cases_resignation"),
        sa.ForeignKeyConstraint(
            ["resignation_id"], ["resignations.id"],
            name="fk_offboarding_cases_resignation_id_resignations", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name="fk_offboarding_cases_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"], ["employees.id"], name="fk_offboarding_cases_manager_id_employees",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["hr_owner_id"], ["users.id"], name="fk_offboarding_cases_hr_owner_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("offboarding_cases"),
        sa.CheckConstraint(
            "status IN ('not_started','in_progress','completed','cancelled')",
            name="ck_offboarding_cases_status",
        ),
        sa.CheckConstraint(
            "progress_percent BETWEEN 0 AND 100", name="ck_offboarding_cases_progress_percent_range"
        ),
        comment="One separation in progress.",
    )
    op.create_index("ix_offboarding_cases_employee_id", "offboarding_cases", ["employee_id"])
    op.create_index("ix_offboarding_cases_status", "offboarding_cases", ["status"])
    op.create_index("ix_offboarding_cases_hr_owner_id", "offboarding_cases", ["hr_owner_id"])
    op.create_index("ix_offboarding_cases_manager_id", "offboarding_cases", ["manager_id"])
    op.create_index("ix_offboarding_cases_last_working_day", "offboarding_cases", ["last_working_day"])
    op.create_index("ix_offboarding_cases_deleted_at", "offboarding_cases", ["deleted_at"])
    op.create_index(
        "ix_offboarding_cases_status_lwd", "offboarding_cases", ["status", "last_working_day"]
    )

    op.create_table(
        "offboarding_tasks",
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("department", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sequence", sa.SmallInteger(), server_default="0", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_offboarding_tasks"),
        sa.ForeignKeyConstraint(
            ["case_id"], ["offboarding_cases.id"],
            name="fk_offboarding_tasks_case_id_offboarding_cases", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_offboarding_tasks_owner_id_users", ondelete="SET NULL"
        ),
        *_actor_constraints("offboarding_tasks"),
        sa.CheckConstraint(
            "status IN ('pending','in_progress','completed','waived')", name="ck_offboarding_tasks_status"
        ),
        sa.CheckConstraint(
            "department IN ('hr','manager','it','admin','finance')",
            name="ck_offboarding_tasks_department",
        ),
        comment="Departmental clearance checklist for one offboarding case.",
    )
    op.create_index("ix_offboarding_tasks_case_id", "offboarding_tasks", ["case_id"])
    op.create_index("ix_offboarding_tasks_department", "offboarding_tasks", ["department"])
    op.create_index("ix_offboarding_tasks_status", "offboarding_tasks", ["status"])
    op.create_index("ix_offboarding_tasks_deleted_at", "offboarding_tasks", ["deleted_at"])
    op.create_index("ix_offboarding_tasks_owner_status", "offboarding_tasks", ["owner_id", "status"])

    op.create_table(
        "handover_records",
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="not_started", nullable=False),
        sa.Column("projects", sa.Text(), nullable=True),
        sa.Column("responsibilities", sa.Text(), nullable=True),
        sa.Column("documentation", sa.Text(), nullable=True),
        sa.Column("replacement_employee_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "attachment_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_handover_records"),
        sa.UniqueConstraint("case_id", name="uq_handover_records_case"),
        sa.ForeignKeyConstraint(
            ["case_id"], ["offboarding_cases.id"],
            name="fk_handover_records_case_id_offboarding_cases", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replacement_employee_id"], ["employees.id"],
            name="fk_handover_records_replacement_employee_id_employees", ondelete="SET NULL",
        ),
        *_actor_constraints("handover_records"),
        sa.CheckConstraint(
            "status IN ('not_started','in_progress','completed')", name="ck_handover_records_status"
        ),
        comment="Knowledge-transfer record for one offboarding case.",
    )
    op.create_index("ix_handover_records_case_id", "handover_records", ["case_id"])
    op.create_index("ix_handover_records_status", "handover_records", ["status"])
    op.create_index("ix_handover_records_deleted_at", "handover_records", ["deleted_at"])

    op.create_table(
        "asset_clearance",
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("asset_name", sa.String(length=150), nullable=False),
        sa.Column("asset_tag", sa.String(length=100), nullable=True),
        sa.Column("assigned_date", sa.Date(), nullable=True),
        sa.Column("return_date", sa.Date(), nullable=True),
        sa.Column("condition", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="assigned", nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_asset_clearance"),
        sa.ForeignKeyConstraint(
            ["case_id"], ["offboarding_cases.id"],
            name="fk_asset_clearance_case_id_offboarding_cases", ondelete="CASCADE",
        ),
        *_actor_constraints("asset_clearance"),
        sa.CheckConstraint(
            "status IN ('assigned','returned','damaged','lost','waived')", name="ck_asset_clearance_status"
        ),
        comment="Per-case record of company property returned at exit.",
    )
    op.create_index("ix_asset_clearance_case_id", "asset_clearance", ["case_id"])
    op.create_index("ix_asset_clearance_status", "asset_clearance", ["status"])
    op.create_index("ix_asset_clearance_deleted_at", "asset_clearance", ["deleted_at"])
    op.create_index("ix_asset_clearance_case_status", "asset_clearance", ["case_id", "status"])

    op.create_table(
        "access_clearance",
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("system_name", sa.String(length=150), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_access_clearance"),
        sa.ForeignKeyConstraint(
            ["case_id"], ["offboarding_cases.id"],
            name="fk_access_clearance_case_id_offboarding_cases", ondelete="CASCADE",
        ),
        *_actor_constraints("access_clearance"),
        sa.CheckConstraint(
            "status IN ('pending','revoked','not_applicable')", name="ck_access_clearance_status"
        ),
        comment="Per-case record of system access revoked at exit.",
    )
    op.create_index("ix_access_clearance_case_id", "access_clearance", ["case_id"])
    op.create_index("ix_access_clearance_status", "access_clearance", ["status"])
    op.create_index("ix_access_clearance_deleted_at", "access_clearance", ["deleted_at"])
    op.create_index("ix_access_clearance_case_status", "access_clearance", ["case_id", "status"])

    op.create_table(
        "exit_interviews",
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("reason_for_leaving", sa.String(length=100), nullable=False),
        sa.Column("overall_experience", sa.SmallInteger(), nullable=True),
        sa.Column("management_rating", sa.SmallInteger(), nullable=True),
        sa.Column("work_environment_rating", sa.SmallInteger(), nullable=True),
        sa.Column("career_growth_rating", sa.SmallInteger(), nullable=True),
        sa.Column("compensation_rating", sa.SmallInteger(), nullable=True),
        sa.Column("management_feedback", sa.Text(), nullable=True),
        sa.Column("work_environment_feedback", sa.Text(), nullable=True),
        sa.Column("career_growth_feedback", sa.Text(), nullable=True),
        sa.Column("compensation_feedback", sa.Text(), nullable=True),
        sa.Column("suggestions", sa.Text(), nullable=True),
        sa.Column("would_recommend", sa.Boolean(), nullable=True),
        sa.Column("would_rejoin", sa.Boolean(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_exit_interviews"),
        sa.UniqueConstraint("case_id", name="uq_exit_interviews_case"),
        sa.ForeignKeyConstraint(
            ["case_id"], ["offboarding_cases.id"],
            name="fk_exit_interviews_case_id_offboarding_cases", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name="fk_exit_interviews_employee_id_employees",
            ondelete="RESTRICT",
        ),
        *_actor_constraints("exit_interviews"),
        sa.CheckConstraint(
            "overall_experience IS NULL OR overall_experience BETWEEN 1 AND 5",
            name="ck_exit_interviews_overall_experience",
        ),
        comment="Employee exit interview responses.",
    )
    op.create_index("ix_exit_interviews_case_id", "exit_interviews", ["case_id"])
    op.create_index("ix_exit_interviews_employee_id", "exit_interviews", ["employee_id"])
    op.create_index("ix_exit_interviews_deleted_at", "exit_interviews", ["deleted_at"])

    op.create_table(
        "exit_documents",
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released", sa.Boolean(), server_default="false", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_exit_documents"),
        sa.UniqueConstraint("case_id", "document_type", name="uq_exit_documents_case_type"),
        sa.ForeignKeyConstraint(
            ["case_id"], ["offboarding_cases.id"],
            name="fk_exit_documents_case_id_offboarding_cases", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name="fk_exit_documents_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name="fk_exit_documents_document_id_documents",
            ondelete="SET NULL",
        ),
        *_actor_constraints("exit_documents"),
        sa.CheckConstraint(
            "document_type IN ('experience_letter','relieving_letter','service_certificate')",
            name="ck_exit_documents_document_type",
        ),
        comment="Experience, relieving and service certificates issued at exit.",
    )
    op.create_index("ix_exit_documents_case_id", "exit_documents", ["case_id"])
    op.create_index("ix_exit_documents_employee_id", "exit_documents", ["employee_id"])
    op.create_index("ix_exit_documents_document_type", "exit_documents", ["document_type"])
    op.create_index("ix_exit_documents_deleted_at", "exit_documents", ["deleted_at"])

    op.create_table(
        "final_settlement_tracking",
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="not_started", nullable=False),
        sa.Column("settlement_reference", sa.String(length=100), nullable=True),
        sa.Column("settlement_date", sa.Date(), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_final_settlement_tracking"),
        sa.UniqueConstraint("case_id", name="uq_final_settlement_case"),
        sa.ForeignKeyConstraint(
            ["case_id"], ["offboarding_cases.id"],
            name="fk_final_settlement_tracking_case_id_offboarding_cases", ondelete="CASCADE",
        ),
        *_actor_constraints("final_settlement_tracking"),
        sa.CheckConstraint(
            "status IN ('not_started','in_progress','pending_clearance','ready_for_processing','completed')",
            name="ck_final_settlement_tracking_status",
        ),
        comment="Full & final settlement status tracking -- not a calculation.",
    )
    op.create_index("ix_final_settlement_tracking_case_id", "final_settlement_tracking", ["case_id"])
    op.create_index("ix_final_settlement_tracking_status", "final_settlement_tracking", ["status"])
    op.create_index("ix_final_settlement_tracking_deleted_at", "final_settlement_tracking", ["deleted_at"])


def _add_notice_period() -> None:
    op.add_column(
        "employment_types",
        sa.Column(
            "notice_period_days",
            sa.Integer(),
            nullable=True,
            comment=(
                "Notice a person on this contract owes, in calendar days. NULL means "
                "not configured and falls back to the module default; 0 means no "
                "notice is required, which is a different statement."
            ),
        ),
    )
    op.create_check_constraint(
        "notice_period_days_non_negative", "employment_types", "notice_period_days >= 0"
    )
    for employment_code, days in _NOTICE_DEFAULTS:
        op.execute(
            sa.text(
                "UPDATE employment_types SET notice_period_days = :days"
                " WHERE upper(code) = :code AND notice_period_days IS NULL"
            ).bindparams(days=days, code=employment_code)
        )


# ----------------------------------------------------------------------
# Permissions
# ----------------------------------------------------------------------
def _add_permissions() -> None:
    """``ON CONFLICT`` because ``reconcile_catalogue`` is reachable at runtime.

    An environment where the code deployed before the migration ran may already
    hold these rows. It never grants them to anybody, so the grants below are
    still this migration's job.
    """
    for module_key in _NEW_MODULES:
        module = MODULES_BY_KEY[module_key]
        for action in module.actions:
            permission = code(module_key, action)
            op.execute(
                sa.text(
                    "INSERT INTO permissions(code, module, action, permission_group, label, description)"
                    " VALUES (:code, :module, :action, :grp, :label, :description)"
                    " ON CONFLICT (code) DO NOTHING"
                ).bindparams(
                    code=permission,
                    module=module_key,
                    action=PermissionAction(action).value,
                    grp=module.group.value,
                    label=action_label(action, module.label),
                    description=_PERMISSION_DESCRIPTIONS[permission],
                )
            )


def _grant_permissions() -> None:
    """Grant each seeded role exactly what :mod:`app.core.permissions` says it holds.

    Derived from ``SYSTEM_ROLES`` rather than from a literal list here, so the
    migration and the catalogue cannot disagree about which seat gets
    ``resignation:approve`` -- which is the one grant in this release that the
    whole access model turns on.

    Custom roles are untouched, for the reason 0016 gives: guessing which of
    them should gain a new power is not this migration's call.
    """
    new_codes = {code(module, action) for module in _NEW_MODULES for action in MODULES_BY_KEY[module].actions}
    for role in SYSTEM_ROLES:
        granted = sorted(new_codes.intersection(role.permissions))
        if not granted:
            continue
        op.execute(
            sa.text(
                "INSERT INTO role_permissions(role_id, permission_id)"
                " SELECT r.id, p.id FROM roles r, permissions p"
                " WHERE r.key = :key AND p.code = ANY(:codes) AND p.deleted_at IS NULL"
                " ON CONFLICT (role_id, permission_id) DO NOTHING"
            ).bindparams(key=role.key, codes=granted)
        )


# ----------------------------------------------------------------------
def downgrade() -> None:
    codes = sorted(
        code(module, action) for module in _NEW_MODULES for action in MODULES_BY_KEY[module].actions
    )
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN"
            " (SELECT id FROM permissions WHERE code = ANY(:codes))"
        ).bindparams(codes=codes)
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:codes)").bindparams(codes=codes))

    op.drop_constraint("ck_employment_types_notice_period_days_non_negative", "employment_types")
    op.drop_column("employment_types", "notice_period_days")

    for table in _TABLES:
        op.drop_table(table)

    op.execute(f"DROP SEQUENCE IF EXISTS {OFFBOARDING_CODE_SEQUENCE}")
    op.execute(f"DROP SEQUENCE IF EXISTS {RESIGNATION_CODE_SEQUENCE}")
