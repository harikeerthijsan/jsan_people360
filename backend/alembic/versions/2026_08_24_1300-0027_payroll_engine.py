"""Payroll Phase 4: the monthly calculation engine's records.

Revision ID: 0027_payroll_engine
Revises: 0026_payroll_inputs
Create Date: 2026-08-24 13:00:00

Three tables, one configuration column, five permissions.

**payroll_runs** — one per period, UNIQUE-enforced, so "the August payroll"
stays a single answerable thing; recalculation replaces its records rather
than growing a second run. **payroll_employee_records** — one employee's
calculated result, self-contained: the day counts it was computed from are
copied in, because the input snapshot it references may be prepared again.
**payroll_line_items** — the breakdown, one row per earning or deduction,
each carrying the human-readable basis it was computed on. A net pay whose
derivation cannot be read back is a dispute the organization loses.

``standard_daily_hours`` joins the configuration singleton: turning a
monthly amount into an hourly overtime rate needs an hours-per-day figure,
and the engine refuses to assume one — it is configuration like everything
else it obeys.

No seeded role below Administrator receives any of the five permissions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.permissions import MODULES_BY_KEY, SYSTEM_ROLES, PermissionAction, action_label, code

revision: str = "0027_payroll_engine"
down_revision: str | None = "0026_payroll_inputs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODULE = "payroll"
PAYROLL_RUN_CODE_SEQUENCE = "payroll_runs_code_seq"

_NEW_ACTIONS = (
    PermissionAction.RUNS_VIEW,
    PermissionAction.RUN_CREATE,
    PermissionAction.CALCULATE,
    PermissionAction.RECALCULATE,
    PermissionAction.RECORD_VIEW,
)

_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "payroll:runs_view": "See payroll runs, their organization-wide totals and per-employee "
    "results. The heaviest read in the module.",
    "payroll:run_create": "Open a payroll run for a period.",
    "payroll:calculate": "Execute the payroll calculation for a run that has none yet.",
    "payroll:recalculate": "Compute a run's numbers again, replacing what was there.",
    "payroll:record_view": "See one employee's calculated payroll record with its line items.",
}

_TABLES = ("payroll_line_items", "payroll_employee_records", "payroll_runs")


def upgrade() -> None:
    op.add_column(
        "payroll_configurations",
        sa.Column(
            "standard_daily_hours",
            sa.Numeric(precision=4, scale=2),
            server_default="8.00",
            nullable=False,
            comment="Hours one working day represents when a monthly amount becomes an hourly rate.",
        ),
    )
    # Raw SQL: op.create_check_constraint would wrap the name in the naming
    # convention a second time and PostgreSQL would truncate the result.
    op.execute(
        "ALTER TABLE payroll_configurations ADD CONSTRAINT "
        "ck_payroll_configurations_standard_daily_hours_range "
        "CHECK (standard_daily_hours > 0 AND standard_daily_hours <= 24)"
    )

    op.execute(f"CREATE SEQUENCE {PAYROLL_RUN_CODE_SEQUENCE} AS bigint START WITH 1")
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
    # -- Runs -----------------------------------------------------------
    op.create_table(
        "payroll_runs",
        sa.Column(
            "run_code",
            sa.String(length=20),
            server_default=sa.text(
                f"'PRUN-' || lpad(nextval('{PAYROLL_RUN_CODE_SEQUENCE}')::text, 6, '0')"
            ),
            nullable=False,
        ),
        sa.Column("payroll_period_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("employee_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("calculated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("review_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("excluded_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_gross", sa.Numeric(precision=16, scale=2), server_default="0", nullable=False),
        sa.Column(
            "total_deductions", sa.Numeric(precision=16, scale=2), server_default="0", nullable=False
        ),
        sa.Column("total_net", sa.Numeric(precision=16, scale=2), server_default="0", nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calculated_by_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_runs"),
        sa.UniqueConstraint("run_code", name="uq_payroll_runs_run_code"),
        sa.UniqueConstraint("payroll_period_id", name="uq_payroll_runs_period"),
        sa.ForeignKeyConstraint(
            ["payroll_period_id"],
            ["payroll_periods.id"],
            name="fk_payroll_runs_payroll_period_id_payroll_periods",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["calculated_by_id"],
            ["users.id"],
            name="fk_payroll_runs_calculated_by_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("payroll_runs"),
        sa.CheckConstraint(
            "status IN ('draft','calculating','requires_review','calculated','approved','finalized')",
            name="ck_payroll_runs_status",
        ),
        sa.CheckConstraint("total_gross >= 0", name="ck_payroll_runs_total_gross_non_negative"),
        sa.CheckConstraint(
            "total_deductions >= 0", name="ck_payroll_runs_total_deductions_non_negative"
        ),
        comment="Payroll runs, one per period.",
    )
    op.create_index("ix_payroll_runs_payroll_period_id", "payroll_runs", ["payroll_period_id"])
    op.create_index("ix_payroll_runs_status", "payroll_runs", ["status"])
    op.create_index("ix_payroll_runs_deleted_at", "payroll_runs", ["deleted_at"])

    # -- Employee records -------------------------------------------------
    op.create_table(
        "payroll_employee_records",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("payroll_input_id", sa.UUID(), nullable=True),
        sa.Column("compensation_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("exception_reason", sa.String(length=400), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column(
            "gross_earnings", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "total_deductions", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("net_pay", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False),
        sa.Column("calendar_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("working_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("eligible_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("present_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "paid_leave_days", sa.Numeric(precision=5, scale=1), server_default="0", nullable=False
        ),
        sa.Column(
            "unpaid_leave_days", sa.Numeric(precision=5, scale=1), server_default="0", nullable=False
        ),
        sa.Column(
            "overtime_hours_paid", sa.Numeric(precision=6, scale=2), server_default="0", nullable=False
        ),
        sa.Column("proration_basis", sa.String(length=20), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_employee_records"),
        sa.UniqueConstraint("run_id", "employee_id", name="uq_payroll_employee_records_run_employee"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["payroll_runs.id"],
            name="fk_payroll_employee_records_run_id_payroll_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_payroll_employee_records_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payroll_input_id"],
            ["payroll_inputs.id"],
            name="fk_payroll_employee_records_payroll_input_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["compensation_id"],
            ["employee_compensation.id"],
            name="fk_payroll_employee_records_compensation_id",
            ondelete="SET NULL",
        ),
        *_actor_constraints("payroll_employee_records"),
        sa.CheckConstraint(
            "status IN ('calculated','requires_review','excluded')",
            name="ck_payroll_employee_records_status",
        ),
        sa.CheckConstraint(
            "gross_earnings >= 0", name="ck_payroll_employee_records_gross_non_negative"
        ),
        sa.CheckConstraint(
            "total_deductions >= 0", name="ck_payroll_employee_records_deductions_non_negative"
        ),
        comment="Per-employee calculated payroll records.",
    )
    op.create_index("ix_payroll_employee_records_run_id", "payroll_employee_records", ["run_id"])
    op.create_index(
        "ix_payroll_employee_records_employee_id", "payroll_employee_records", ["employee_id"]
    )
    op.create_index("ix_payroll_employee_records_status", "payroll_employee_records", ["status"])
    op.create_index(
        "ix_payroll_employee_records_deleted_at", "payroll_employee_records", ["deleted_at"]
    )
    op.create_index(
        "ix_payroll_employee_records_run_status", "payroll_employee_records", ["run_id", "status"]
    )

    # -- Line items -----------------------------------------------------------
    op.create_table(
        "payroll_line_items",
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("component_id", sa.UUID(), nullable=True),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("calculation_basis", sa.String(length=200), nullable=False),
        sa.Column("original_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("prorated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_line_items"),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["payroll_employee_records.id"],
            name="fk_payroll_line_items_record_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["component_id"],
            ["salary_components.id"],
            name="fk_payroll_line_items_component_id_salary_components",
            ondelete="SET NULL",
        ),
        *_actor_constraints("payroll_line_items"),
        sa.CheckConstraint(
            "item_type IN ('earning','deduction')", name="ck_payroll_line_items_item_type"
        ),
        sa.CheckConstraint(
            "source IN ('component','overtime','unpaid_leave')", name="ck_payroll_line_items_source"
        ),
        sa.CheckConstraint("amount >= 0", name="ck_payroll_line_items_amount_non_negative"),
        comment="Component-level payroll lines.",
    )
    op.create_index("ix_payroll_line_items_record_id", "payroll_line_items", ["record_id"])
    op.create_index("ix_payroll_line_items_deleted_at", "payroll_line_items", ["deleted_at"])
    op.create_index(
        "ix_payroll_line_items_record_type", "payroll_line_items", ["record_id", "item_type"]
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
    op.execute(f"DROP SEQUENCE IF EXISTS {PAYROLL_RUN_CODE_SEQUENCE}")

    # Dropping the column drops its check constraint with it.
    op.drop_column("payroll_configurations", "standard_daily_hours")
