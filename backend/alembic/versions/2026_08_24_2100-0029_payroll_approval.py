"""Payroll Phase 6: approval and finalization.

Revision ID: 0029_payroll_approval
Revises: 0028_payroll_review
Create Date: 2026-08-24 21:00:00

Two tables, twelve run columns, two new run statuses, five permissions.

**payroll_approvals** — the append-only approval trail: one row per submit,
approval, send-back and finalization, with actor, comment/reason and the
totals as they stood. **payroll_final_snapshots** — the immutable per-employee
record of a finalized payroll, fully denormalized (names, dates, line items,
adjustments, sign-off as plain values) so it keeps saying what was paid even
after source data changes. The run itself gains the workflow milestones:
review completed / submitted / approved / returned / finalized, each with its
actor and moment.

No seeded role below Administrator receives any of the five permissions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.core.permissions import MODULES_BY_KEY, SYSTEM_ROLES, PermissionAction, action_label, code

revision: str = "0029_payroll_approval"
down_revision: str | None = "0028_payroll_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODULE = "payroll"

_NEW_ACTIONS = (
    PermissionAction.APPROVAL_VIEW,
    PermissionAction.APPROVE,
    PermissionAction.RETURN,
    PermissionAction.FINALIZE,
    PermissionAction.FINALIZED_VIEW,
)

_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "payroll:approval_view": "See the payroll approval queue and a run's approval summary.",
    "payroll:approve": "Approve a payroll run submitted for approval. Deliberately separate "
    "from every preparation and review grant.",
    "payroll:return": "Return a submitted payroll run for correction, with a recorded reason.",
    "payroll:finalize": "Finalize an approved payroll run: snapshot it, lock it, close its period.",
    "payroll:finalized_view": "See finalized payroll history and the immutable final snapshots.",
}

_TABLES = ("payroll_final_snapshots", "payroll_approvals")

_RUN_STATUSES_OLD = (
    "'draft','calculating','requires_review','calculated','in_review','review_complete',"
    "'approved','finalized'"
)
_RUN_STATUSES_NEW = (
    "'draft','calculating','requires_review','calculated','in_review','review_complete',"
    "'pending_approval','returned','approved','finalized'"
)

#: (column stem, whether the run column set includes a reason/comment text).
_MILESTONES = ("review_completed", "submitted", "approved", "returned", "finalized")


def _drop_status_check(table: str) -> None:
    """Constraint names may carry the 0027 double-wrapped form; drop by name
    suffix (the definition is no anchor — PostgreSQL normalizes ``IN`` to
    ``= ANY``)."""
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

    for stem in _MILESTONES:
        op.add_column(
            "payroll_runs", sa.Column(f"{stem}_at", sa.DateTime(timezone=True), nullable=True)
        )
        op.add_column("payroll_runs", sa.Column(f"{stem}_by_id", sa.UUID(), nullable=True))
        op.create_foreign_key(
            f"fk_payroll_runs_{stem}_by_id_users",
            "payroll_runs",
            "users",
            [f"{stem}_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.add_column("payroll_runs", sa.Column("approval_comment", sa.String(length=400), nullable=True))
    op.add_column("payroll_runs", sa.Column("return_reason", sa.String(length=400), nullable=True))

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
    # -- Approval trail --------------------------------------------------
    op.create_table(
        "payroll_approvals",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("comment", sa.String(length=400), nullable=True),
        sa.Column("employee_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_gross", sa.Numeric(precision=16, scale=2), server_default="0", nullable=False),
        sa.Column(
            "total_deductions", sa.Numeric(precision=16, scale=2), server_default="0", nullable=False
        ),
        sa.Column("total_net", sa.Numeric(precision=16, scale=2), server_default="0", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_approvals"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["payroll_runs.id"],
            name="fk_payroll_approvals_run_id_payroll_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="fk_payroll_approvals_actor_id_users", ondelete="SET NULL"
        ),
        *_actor_constraints("payroll_approvals"),
        sa.CheckConstraint(
            "action IN ('submitted','approved','returned','finalized')",
            name="ck_payroll_approvals_action",
        ),
        comment="Append-only payroll approval trail.",
    )
    op.create_index("ix_payroll_approvals_run_id", "payroll_approvals", ["run_id"])
    op.create_index("ix_payroll_approvals_action", "payroll_approvals", ["action"])
    op.create_index("ix_payroll_approvals_deleted_at", "payroll_approvals", ["deleted_at"])
    op.create_index("ix_payroll_approvals_run_created", "payroll_approvals", ["run_id", "created_at"])

    # -- Final snapshots -------------------------------------------------
    op.create_table(
        "payroll_final_snapshots",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("employee_code", sa.String(length=20), nullable=False),
        sa.Column("employee_name", sa.String(length=200), nullable=False),
        sa.Column("period_name", sa.String(length=120), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("exception_reason", sa.String(length=400), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("structure_name", sa.String(length=150), nullable=True),
        sa.Column("monthly_basic", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("monthly_gross", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("annual_ctc", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column(
            "gross_earnings", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "total_deductions", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("net_pay", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False),
        sa.Column(
            "adjustment_earnings", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "adjustment_deductions",
            sa.Numeric(precision=14, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("final_gross", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False),
        sa.Column(
            "final_deductions", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("final_net", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False),
        sa.Column("line_items", JSONB(), server_default="[]", nullable=False),
        sa.Column("adjustments", JSONB(), server_default="[]", nullable=False),
        sa.Column("approved_by_name", sa.String(length=200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by_name", sa.String(length=200), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_final_snapshots"),
        sa.UniqueConstraint("run_id", "employee_id", name="uq_payroll_final_snapshots_run_employee"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["payroll_runs.id"],
            name="fk_payroll_final_snapshots_run_id_payroll_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_payroll_final_snapshots_employee_id_employees",
            ondelete="RESTRICT",
        ),
        *_actor_constraints("payroll_final_snapshots"),
        sa.CheckConstraint(
            "status IN ('calculated','requires_review','excluded','reviewed',"
            "'adjustment_required','ready_for_approval')",
            name="ck_payroll_final_snapshots_status",
        ),
        comment="Immutable per-employee snapshots of finalized payroll.",
    )
    op.create_index("ix_payroll_final_snapshots_run_id", "payroll_final_snapshots", ["run_id"])
    op.create_index(
        "ix_payroll_final_snapshots_employee_id", "payroll_final_snapshots", ["employee_id"]
    )
    op.create_index(
        "ix_payroll_final_snapshots_deleted_at", "payroll_final_snapshots", ["deleted_at"]
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

    op.drop_column("payroll_runs", "return_reason")
    op.drop_column("payroll_runs", "approval_comment")
    for stem in reversed(_MILESTONES):
        op.drop_constraint(f"fk_payroll_runs_{stem}_by_id_users", "payroll_runs", type_="foreignkey")
        op.drop_column("payroll_runs", f"{stem}_by_id")
        op.drop_column("payroll_runs", f"{stem}_at")

    # Fold the approval-phase statuses back into the Phase 5 vocabulary
    # before narrowing the constraint again.
    op.execute(
        "UPDATE payroll_runs SET status = 'calculated'"
        " WHERE status IN ('pending_approval','returned')"
    )
    _drop_status_check("payroll_runs")
    op.execute(
        "ALTER TABLE payroll_runs ADD CONSTRAINT ck_payroll_runs_status "
        f"CHECK (status IN ({_RUN_STATUSES_OLD}))"
    )
