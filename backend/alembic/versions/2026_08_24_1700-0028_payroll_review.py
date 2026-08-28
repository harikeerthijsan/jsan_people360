"""Payroll Phase 5: review, exceptions, adjustments.

Revision ID: 0028_payroll_review
Revises: 0027_payroll_engine
Create Date: 2026-08-24 17:00:00

Four tables, two record columns, two widened status vocabularies, five
permissions.

**payroll_run_exceptions** — severity-graded issues the engine found, one
per issue per employee per run. Resolved with a recorded reason, never
deleted; the run cannot complete review while a critical one is open.
**payroll_adjustments** — additive corrections keyed by run and employee so
they survive record rebuilds; cancelled rather than deleted. The engine's
calculated amounts stay untouched — the record gains two adjustment columns
and final pay is derived where displayed. **payroll_review_checklists** —
per-run sign-off items gating completion. **payroll_review_comments** —
append-only reviewer conversation.

No seeded role below Administrator receives any of the five permissions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.permissions import MODULES_BY_KEY, SYSTEM_ROLES, PermissionAction, action_label, code

revision: str = "0028_payroll_review"
down_revision: str | None = "0027_payroll_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODULE = "payroll"

_NEW_ACTIONS = (
    PermissionAction.REVIEW_VIEW,
    PermissionAction.EXCEPTION_RESOLVE,
    PermissionAction.ADJUSTMENT_CREATE,
    PermissionAction.ADJUSTMENT_UPDATE,
    PermissionAction.REVIEW_COMPLETE,
)

_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "payroll:review_view": "See the payroll review surface: exceptions, adjustments, checklist, "
    "reconciliation and the previous-period comparison.",
    "payroll:exception_resolve": "Resolve a payroll exception with a recorded reason.",
    "payroll:adjustment_create": "Add an additive manual adjustment to an employee's payroll.",
    "payroll:adjustment_update": "Cancel a payroll adjustment (cancelled, never deleted).",
    "payroll:review_complete": "Work the review checklist, mark records and sign off a run's "
    "review once its gates are met.",
}

_TABLES = (
    "payroll_review_comments",
    "payroll_review_checklists",
    "payroll_adjustments",
    "payroll_run_exceptions",
)

#: Status vocabularies before and after this phase, for the paired
#: DROP/ADD of the check constraints (raw SQL: op.create_check_constraint
#: would wrap the name in the naming convention a second time).
_RUN_STATUSES_OLD = "'draft','calculating','requires_review','calculated','approved','finalized'"
_RUN_STATUSES_NEW = (
    "'draft','calculating','requires_review','calculated','in_review','review_complete',"
    "'approved','finalized'"
)
_RECORD_STATUSES_OLD = "'calculated','requires_review','excluded'"
_RECORD_STATUSES_NEW = (
    "'calculated','requires_review','excluded','reviewed','adjustment_required',"
    "'ready_for_approval'"
)


def _drop_status_check(table: str) -> None:
    """0027 created these inside ``create_table``, where the naming convention
    wrapped the given name a second time (``ck_payroll_runs_ck_payroll_runs_
    status``). Drop every status check by its name suffix rather than guessing
    the mangled form; the definition itself is no anchor either, because
    PostgreSQL normalizes ``IN`` to ``= ANY``."""
    op.execute(
        f"""
        DO $$
        DECLARE con text;
        BEGIN
          FOR con IN SELECT conname FROM pg_constraint
           WHERE conrelid = '{table}'::regclass AND contype = 'c'
             AND conname LIKE '%status'
          LOOP
            EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I', con);
          END LOOP;
        END $$;
        """
    )


def upgrade() -> None:
    _drop_status_check("payroll_runs")
    op.execute(
        "ALTER TABLE payroll_runs ADD CONSTRAINT ck_payroll_runs_status "
        f"CHECK (status IN ({_RUN_STATUSES_NEW}))"
    )
    _drop_status_check("payroll_employee_records")
    op.execute(
        "ALTER TABLE payroll_employee_records ADD CONSTRAINT ck_payroll_employee_records_status "
        f"CHECK (status IN ({_RECORD_STATUSES_NEW}))"
    )

    for column in ("adjustment_earnings", "adjustment_deductions"):
        op.add_column(
            "payroll_employee_records",
            sa.Column(
                column,
                sa.Numeric(precision=14, scale=2),
                server_default="0",
                nullable=False,
                comment="Additive review-phase amount; the calculated originals stay untouched.",
            ),
        )
    op.execute(
        "ALTER TABLE payroll_employee_records ADD CONSTRAINT "
        "ck_payroll_employee_records_adjustment_earnings_non_negative "
        "CHECK (adjustment_earnings >= 0)"
    )
    op.execute(
        "ALTER TABLE payroll_employee_records ADD CONSTRAINT "
        "ck_payroll_employee_records_adjustment_deductions_non_negative "
        "CHECK (adjustment_deductions >= 0)"
    )

    _create_tables()
    _add_permissions()
    _grant_permissions()


def _audit_columns() -> list[sa.Column[object]]:
    """The platform's audit contract. No ``use_alter`` — the 0014 trap."""
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
    # -- Exceptions -----------------------------------------------------
    op.create_table(
        "payroll_run_exceptions",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("exception_type", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=400), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("resolution", sa.String(length=200), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_run_exceptions"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["payroll_runs.id"],
            name="fk_payroll_run_exceptions_run_id_payroll_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_payroll_run_exceptions_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_id"],
            ["users.id"],
            name="fk_payroll_run_exceptions_resolved_by_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("payroll_run_exceptions"),
        sa.CheckConstraint(
            "exception_type IN ('missing_salary','invalid_compensation','missing_attendance',"
            "'unresolved_correction','unapproved_overtime','invalid_leave',"
            "'negative_leave_balance','invalid_component','calculation_mismatch',"
            "'missing_input','other')",
            name="ck_payroll_run_exceptions_exception_type",
        ),
        sa.CheckConstraint(
            "severity IN ('warning','error','critical')",
            name="ck_payroll_run_exceptions_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open','resolved')", name="ck_payroll_run_exceptions_status"
        ),
        comment="Reviewable payroll exceptions, one per issue per employee per run.",
    )
    op.create_index("ix_payroll_run_exceptions_run_id", "payroll_run_exceptions", ["run_id"])
    op.create_index(
        "ix_payroll_run_exceptions_employee_id", "payroll_run_exceptions", ["employee_id"]
    )
    op.create_index(
        "ix_payroll_run_exceptions_exception_type", "payroll_run_exceptions", ["exception_type"]
    )
    op.create_index("ix_payroll_run_exceptions_severity", "payroll_run_exceptions", ["severity"])
    op.create_index("ix_payroll_run_exceptions_status", "payroll_run_exceptions", ["status"])
    op.create_index(
        "ix_payroll_run_exceptions_deleted_at", "payroll_run_exceptions", ["deleted_at"]
    )
    op.create_index(
        "ix_payroll_run_exceptions_run_status", "payroll_run_exceptions", ["run_id", "status"]
    )

    # -- Adjustments ----------------------------------------------------
    op.create_table(
        "payroll_adjustments",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("component_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("reason", sa.String(length=400), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("previous_net", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False),
        sa.Column("new_net", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False),
        sa.Column("cancelled_by_id", sa.UUID(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=400), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_adjustments"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["payroll_runs.id"],
            name="fk_payroll_adjustments_run_id_payroll_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_payroll_adjustments_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["component_id"],
            ["salary_components.id"],
            name="fk_payroll_adjustments_component_id_salary_components",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by_id"],
            ["users.id"],
            name="fk_payroll_adjustments_cancelled_by_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("payroll_adjustments"),
        sa.CheckConstraint(
            "item_type IN ('earning','deduction')", name="ck_payroll_adjustments_item_type"
        ),
        sa.CheckConstraint(
            "status IN ('active','cancelled')", name="ck_payroll_adjustments_status"
        ),
        sa.CheckConstraint("amount > 0", name="ck_payroll_adjustments_amount_positive"),
        comment="Additive payroll adjustments; cancelled, never deleted.",
    )
    op.create_index("ix_payroll_adjustments_run_id", "payroll_adjustments", ["run_id"])
    op.create_index("ix_payroll_adjustments_employee_id", "payroll_adjustments", ["employee_id"])
    op.create_index("ix_payroll_adjustments_status", "payroll_adjustments", ["status"])
    op.create_index("ix_payroll_adjustments_deleted_at", "payroll_adjustments", ["deleted_at"])
    op.create_index(
        "ix_payroll_adjustments_run_employee", "payroll_adjustments", ["run_id", "employee_id"]
    )

    # -- Review checklist -----------------------------------------------
    op.create_table(
        "payroll_review_checklists",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("item_key", sa.String(length=60), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("completed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("completed_by_id", sa.UUID(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_review_checklists"),
        sa.UniqueConstraint("run_id", "item_key", name="uq_payroll_review_checklists_run_item"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["payroll_runs.id"],
            name="fk_payroll_review_checklists_run_id_payroll_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_id"],
            ["users.id"],
            name="fk_payroll_review_checklists_completed_by_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("payroll_review_checklists"),
        comment="Per-run review checklist items.",
    )
    op.create_index("ix_payroll_review_checklists_run_id", "payroll_review_checklists", ["run_id"])
    op.create_index(
        "ix_payroll_review_checklists_deleted_at", "payroll_review_checklists", ["deleted_at"]
    )

    # -- Review comments ------------------------------------------------
    op.create_table(
        "payroll_review_comments",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_review_comments"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["payroll_runs.id"],
            name="fk_payroll_review_comments_run_id_payroll_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_payroll_review_comments_employee_id_employees",
            ondelete="RESTRICT",
        ),
        *_actor_constraints("payroll_review_comments"),
        comment="Append-only payroll review comments.",
    )
    op.create_index("ix_payroll_review_comments_run_id", "payroll_review_comments", ["run_id"])
    op.create_index(
        "ix_payroll_review_comments_employee_id", "payroll_review_comments", ["employee_id"]
    )
    op.create_index(
        "ix_payroll_review_comments_deleted_at", "payroll_review_comments", ["deleted_at"]
    )
    op.create_index(
        "ix_payroll_review_comments_run_created",
        "payroll_review_comments",
        ["run_id", "created_at"],
    )


def _add_permissions() -> None:
    """``ON CONFLICT`` because ``reconcile_catalogue`` is reachable at runtime."""
    module = MODULES_BY_KEY[_MODULE]
    for action in _NEW_ACTIONS:
        permission = code(_MODULE, action)
        op.execute(
            sa.text(
                "INSERT INTO permissions(code, module, action, permission_group, label, description)"
                " VALUES (:code, :module, :action, :grp, :label, :description)"
                " ON CONFLICT (code) DO NOTHING"
            ).bindparams(
                code=permission,
                module=_MODULE,
                action=PermissionAction(action).value,
                grp=module.group.value,
                label=action_label(action, module.label),
                description=_PERMISSION_DESCRIPTIONS[permission],
            )
        )


def _grant_permissions() -> None:
    """Derived from ``SYSTEM_ROLES``: Administrator and Super Admin, nobody else."""
    new_codes = {code(_MODULE, action) for action in _NEW_ACTIONS}
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


def downgrade() -> None:
    codes = sorted(code(_MODULE, action) for action in _NEW_ACTIONS)
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN"
            " (SELECT id FROM permissions WHERE code = ANY(:codes))"
        ).bindparams(codes=codes)
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:codes)").bindparams(codes=codes))

    for table in _TABLES:
        op.drop_table(table)

    # Dropping the columns drops their check constraints with them.
    op.drop_column("payroll_employee_records", "adjustment_deductions")
    op.drop_column("payroll_employee_records", "adjustment_earnings")

    # Fold the review-phase statuses back into the Phase 4 vocabulary before
    # narrowing the constraints again.
    op.execute(
        "UPDATE payroll_employee_records SET status = 'calculated'"
        " WHERE status IN ('reviewed','adjustment_required','ready_for_approval')"
    )
    op.execute(
        "UPDATE payroll_runs SET status = 'calculated'"
        " WHERE status IN ('in_review','review_complete')"
    )
    _drop_status_check("payroll_employee_records")
    op.execute(
        "ALTER TABLE payroll_employee_records ADD CONSTRAINT ck_payroll_employee_records_status "
        f"CHECK (status IN ({_RECORD_STATUSES_OLD}))"
    )
    _drop_status_check("payroll_runs")
    op.execute(
        "ALTER TABLE payroll_runs ADD CONSTRAINT ck_payroll_runs_status "
        f"CHECK (status IN ({_RUN_STATUSES_OLD}))"
    )
