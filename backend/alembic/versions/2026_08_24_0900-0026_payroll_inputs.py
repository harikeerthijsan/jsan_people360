"""Payroll Phase 3: payroll inputs — attendance, leave and overtime integration.

Revision ID: 0026_payroll_inputs
Revises: 0025_payroll_configuration
Create Date: 2026-08-24 09:00:00

Three tables and three permissions, and not one column of money.

**payroll_inputs** holds one employee's prepared summary for one period —
day and hour counts read from the existing attendance, leave and offboarding
modules through a SELECT-only reader. **payroll_input_exceptions** holds the
issues that preparation flagged (a missing check-out, unapproved overtime, a
negative balance): flags, never fixes, because payroll must not modify a
source record. **payroll_input_sources** is the snapshot's honesty: the id
and updated_at of every source row consumed, so "what data was this payroll
built on" stays answerable, and a fingerprint over the same lines lets the
change detector flip an input to requires_review when the sources move.

No seeded role below Administrator receives any of the three permissions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.permissions import MODULES_BY_KEY, SYSTEM_ROLES, PermissionAction, action_label, code

revision: str = "0026_payroll_inputs"
down_revision: str | None = "0025_payroll_configuration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODULE = "payroll"

#: Only the Phase 3 additions; earlier phases' permissions already exist.
_NEW_ACTIONS = (
    PermissionAction.INPUTS_VIEW,
    PermissionAction.INPUTS_PREPARE,
    PermissionAction.INPUTS_REVIEW,
)

_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "payroll:inputs_view": "See prepared payroll inputs: per-employee attendance, leave and "
    "overtime summaries for a period. Carries no salary figures.",
    "payroll:inputs_prepare": "Prepare or refresh payroll inputs from the source modules, and "
    "run change detection.",
    "payroll:inputs_review": "Sign off a payroll input that was flagged for review.",
}

_TABLES = ("payroll_input_sources", "payroll_input_exceptions", "payroll_inputs")


def upgrade() -> None:
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
    # -- Inputs --------------------------------------------------------
    op.create_table(
        "payroll_inputs",
        sa.Column("payroll_period_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="ready", nullable=False),
        sa.Column("eligibility", sa.String(length=20), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=200), nullable=True),
        sa.Column("joining_date", sa.Date(), nullable=True),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("offboarding_status", sa.String(length=30), nullable=True),
        sa.Column("eligible_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("non_eligible_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("proration_required", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("calendar_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("working_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("weekly_off_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("holiday_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("present_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("half_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("absent_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("late_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("early_exit_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "paid_leave_days", sa.Numeric(precision=5, scale=1), server_default="0", nullable=False
        ),
        sa.Column(
            "unpaid_leave_days", sa.Numeric(precision=5, scale=1), server_default="0", nullable=False
        ),
        sa.Column("unpaid_leave_deduction", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("unpaid_leave_basis", sa.String(length=20), nullable=True),
        sa.Column(
            "overtime_hours", sa.Numeric(precision=6, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "approved_overtime_hours",
            sa.Numeric(precision=6, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "pending_overtime_hours",
            sa.Numeric(precision=6, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("overtime_eligible", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("exception_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), server_default="", nullable=False),
        sa.Column("source_changed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prepared_by_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_by_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_inputs"),
        sa.UniqueConstraint(
            "payroll_period_id", "employee_id", name="uq_payroll_inputs_period_employee"
        ),
        sa.ForeignKeyConstraint(
            ["payroll_period_id"],
            ["payroll_periods.id"],
            name="fk_payroll_inputs_payroll_period_id_payroll_periods",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_payroll_inputs_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prepared_by_id"],
            ["users.id"],
            name="fk_payroll_inputs_prepared_by_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
            name="fk_payroll_inputs_reviewed_by_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("payroll_inputs"),
        sa.CheckConstraint(
            "status IN ('ready','requires_review','excluded')", name="ck_payroll_inputs_status"
        ),
        sa.CheckConstraint(
            "eligibility IN ('eligible','not_eligible','suspended')",
            name="ck_payroll_inputs_eligibility",
        ),
        sa.CheckConstraint(
            "unpaid_leave_basis IS NULL OR unpaid_leave_basis IN ('calendar_days','working_days')",
            name="ck_payroll_inputs_unpaid_leave_basis",
        ),
        sa.CheckConstraint("calendar_days >= 0", name="ck_payroll_inputs_calendar_days_non_negative"),
        sa.CheckConstraint("working_days >= 0", name="ck_payroll_inputs_working_days_non_negative"),
        sa.CheckConstraint("eligible_days >= 0", name="ck_payroll_inputs_eligible_days_non_negative"),
        sa.CheckConstraint(
            "overtime_hours >= 0", name="ck_payroll_inputs_overtime_hours_non_negative"
        ),
        comment="Prepared payroll inputs, one row per period and employee.",
    )
    op.create_index("ix_payroll_inputs_payroll_period_id", "payroll_inputs", ["payroll_period_id"])
    op.create_index("ix_payroll_inputs_employee_id", "payroll_inputs", ["employee_id"])
    op.create_index("ix_payroll_inputs_status", "payroll_inputs", ["status"])
    op.create_index("ix_payroll_inputs_deleted_at", "payroll_inputs", ["deleted_at"])
    op.create_index(
        "ix_payroll_inputs_period_status", "payroll_inputs", ["payroll_period_id", "status"]
    )

    # -- Exceptions -----------------------------------------------------
    op.create_table(
        "payroll_input_exceptions",
        sa.Column("input_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("message", sa.String(length=400), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=True),
        sa.Column("source_id", sa.UUID(), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_input_exceptions"),
        sa.ForeignKeyConstraint(
            ["input_id"],
            ["payroll_inputs.id"],
            name="fk_payroll_input_exceptions_input_id_payroll_inputs",
            ondelete="CASCADE",
        ),
        *_actor_constraints("payroll_input_exceptions"),
        sa.CheckConstraint(
            "category IN ('attendance','leave','overtime','compensation')",
            name="ck_payroll_input_exceptions_category",
        ),
        comment="Payroll-impacting issues flagged during input preparation.",
    )
    op.create_index("ix_payroll_input_exceptions_input_id", "payroll_input_exceptions", ["input_id"])
    op.create_index("ix_payroll_input_exceptions_code", "payroll_input_exceptions", ["code"])
    op.create_index(
        "ix_payroll_input_exceptions_deleted_at", "payroll_input_exceptions", ["deleted_at"]
    )
    op.create_index(
        "ix_payroll_input_exceptions_input_category",
        "payroll_input_exceptions",
        ["input_id", "category"],
    )

    # -- Sources -----------------------------------------------------------
    op.create_table(
        "payroll_input_sources",
        sa.Column("input_id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_input_sources"),
        sa.UniqueConstraint(
            "input_id", "source_type", "source_id", name="uq_payroll_input_sources_line"
        ),
        sa.ForeignKeyConstraint(
            ["input_id"],
            ["payroll_inputs.id"],
            name="fk_payroll_input_sources_input_id_payroll_inputs",
            ondelete="CASCADE",
        ),
        *_actor_constraints("payroll_input_sources"),
        sa.CheckConstraint(
            "source_type IN ('attendance','regularization','leave_request')",
            name="ck_payroll_input_sources_source_type",
        ),
        comment="Which source records fed one payroll input, and at what version.",
    )
    op.create_index("ix_payroll_input_sources_input_id", "payroll_input_sources", ["input_id"])
    op.create_index("ix_payroll_input_sources_deleted_at", "payroll_input_sources", ["deleted_at"])


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
