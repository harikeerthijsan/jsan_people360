"""Payroll Phase 2: configuration, periods, pay rules and employee settings.

Revision ID: 0025_payroll_configuration
Revises: 0024_payroll_foundation
Create Date: 2026-08-21 16:00:00

Five tables, five columns on an existing one, six permissions — and nothing
that calculates.

**The configuration is a singleton row**, seeded here with the brief's
defaults (monthly, INR), and locked by UNIQUE on a constant column so a
second live configuration cannot exist however requests race. Changes flow
through ``payroll_configuration_history`` — one append-only row per changed
field, with reason and effective date — never through a silent overwrite.

**Existing systems are referenced, not duplicated.** The configuration points
at the workforce module's holiday calendars; the leave rules point at its
leave types; the employee settings row carries no money because the salary is
the Phase 1 compensation record.

**The five component flags extend ``salary_components`` in place** rather
than growing a parallel rule table, because they are properties of the
component. Existing compensation snapshots are untouched — the flags are read
by a future calculation phase, never by Phase 1's records.

**No seeded role below Administrator receives any of the six permissions.**
Employee, Manager and the HR roles are refused the whole configuration
surface; access exists only where an administrator grants it on purpose.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.permissions import MODULES_BY_KEY, SYSTEM_ROLES, PermissionAction, action_label, code

revision: str = "0025_payroll_configuration"
down_revision: str | None = "0024_payroll_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODULE = "payroll"

#: Only the Phase 2 additions; Phase 1's seven already exist.
_NEW_ACTIONS = (
    PermissionAction.CONFIG_VIEW,
    PermissionAction.CONFIG_MANAGE,
    PermissionAction.PERIOD_MANAGE,
    PermissionAction.RULE_MANAGE,
    PermissionAction.EMPLOYEE_SETTINGS_VIEW,
    PermissionAction.EMPLOYEE_SETTINGS_UPDATE,
)

_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "payroll:config_view": "See the payroll configuration, periods, rules and their history.",
    "payroll:config_manage": "Change the payroll configuration. Every change is history-recorded "
    "with a reason and an effective date.",
    "payroll:period_manage": "Create payroll periods and move them along their workflow.",
    "payroll:rule_manage": "Configure how each leave type behaves in payroll.",
    "payroll:employee_settings_view": "See per-employee payroll settings and eligibility. "
    "Carries no salary figures.",
    "payroll:employee_settings_update": "Change per-employee payroll settings and eligibility.",
}

#: Dropped in reverse dependency order.
_TABLES = (
    "payroll_configuration_history",
    "payroll_employee_settings",
    "payroll_leave_rules",
    "payroll_periods",
    "payroll_configurations",
)

_COMPONENT_FLAGS = (
    ("proration_allowed", "true", "May be reduced for a partial period."),
    ("attendance_impact", "false", "Reduced by absence when the attendance rule says so."),
    ("leave_impact", "false", "Reduced by unpaid leave when the leave rule says so."),
    ("overtime_eligible", "false", "Included in the overtime hourly-rate base."),
    ("is_taxable", "true", "In scope for the future tax phase. No tax is computed here."),
)


def upgrade() -> None:
    # The action column was sized for single-verb actions;
    # "employee_settings_update" is a longer name for a narrower power.
    op.alter_column("permissions", "action", type_=sa.String(length=40))
    _extend_salary_components()
    _create_tables()
    _seed_configuration()
    _add_permissions()
    _grant_permissions()


def _extend_salary_components() -> None:
    for column, default, comment in _COMPONENT_FLAGS:
        op.add_column(
            "salary_components",
            sa.Column(column, sa.Boolean(), server_default=default, nullable=False, comment=comment),
        )


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
    # -- Configuration singleton ------------------------------------------
    op.create_table(
        "payroll_configurations",
        sa.Column("singleton", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("pay_frequency", sa.String(length=20), server_default="monthly", nullable=False),
        sa.Column("period_start_day", sa.Integer(), server_default="1", nullable=False),
        sa.Column("period_end_day", sa.Integer(), server_default="31", nullable=False),
        sa.Column("pay_day", sa.Integer(), server_default="31", nullable=False),
        sa.Column("cutoff_day", sa.Integer(), server_default="25", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column(
            "working_days_rule", sa.String(length=30), server_default="working_days", nullable=False
        ),
        sa.Column(
            "weekly_off_days",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[5, 6]'::jsonb"),
            nullable=False,
        ),
        sa.Column("holiday_calendar_id", sa.UUID(), nullable=True),
        sa.Column(
            "proration_basis", sa.String(length=20), server_default="calendar_days", nullable=False
        ),
        sa.Column(
            "unpaid_leave_treatment", sa.String(length=20), server_default="deduct", nullable=False
        ),
        sa.Column(
            "unpaid_leave_basis", sa.String(length=20), server_default="calendar_days", nullable=False
        ),
        sa.Column("overtime_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("overtime_basis", sa.String(length=20), server_default="basic", nullable=False),
        sa.Column(
            "overtime_multiplier", sa.Numeric(precision=4, scale=2), server_default="1.50", nullable=False
        ),
        sa.Column(
            "overtime_min_hours", sa.Numeric(precision=4, scale=2), server_default="1.00", nullable=False
        ),
        sa.Column("overtime_max_hours", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("overtime_approval_required", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("deduct_absence", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("deduct_late_arrival", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deduct_early_exit", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("require_approved_attendance", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("rounding_rule", sa.String(length=20), server_default="none", nullable=False),
        sa.Column("rounding_precision", sa.Numeric(precision=6, scale=2), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_configurations"),
        sa.UniqueConstraint("singleton", name="uq_payroll_configurations_singleton"),
        sa.ForeignKeyConstraint(
            ["holiday_calendar_id"],
            ["holiday_calendars.id"],
            name="fk_payroll_configurations_holiday_calendar_id",
            ondelete="SET NULL",
        ),
        *_actor_constraints("payroll_configurations"),
        sa.CheckConstraint("singleton", name="ck_payroll_configurations_singleton_true"),
        sa.CheckConstraint(
            "pay_frequency IN ('monthly','weekly','biweekly')",
            name="ck_payroll_configurations_pay_frequency",
        ),
        sa.CheckConstraint(
            "period_start_day BETWEEN 1 AND 28", name="ck_payroll_configurations_period_start_day_range"
        ),
        sa.CheckConstraint(
            "period_end_day BETWEEN 1 AND 31", name="ck_payroll_configurations_period_end_day_range"
        ),
        sa.CheckConstraint("pay_day BETWEEN 1 AND 31", name="ck_payroll_configurations_pay_day_range"),
        sa.CheckConstraint(
            "cutoff_day BETWEEN 1 AND 28", name="ck_payroll_configurations_cutoff_day_range"
        ),
        sa.CheckConstraint("char_length(currency) = 3", name="ck_payroll_configurations_currency_iso"),
        sa.CheckConstraint(
            "working_days_rule IN ('calendar_days','working_days','custom_working_days')",
            name="ck_payroll_configurations_working_days_rule",
        ),
        sa.CheckConstraint(
            "proration_basis IN ('calendar_days','working_days')",
            name="ck_payroll_configurations_proration_basis",
        ),
        sa.CheckConstraint(
            "unpaid_leave_treatment IN ('deduct','ignore')",
            name="ck_payroll_configurations_unpaid_leave_treatment",
        ),
        sa.CheckConstraint(
            "unpaid_leave_basis IN ('calendar_days','working_days')",
            name="ck_payroll_configurations_unpaid_leave_basis",
        ),
        sa.CheckConstraint(
            "overtime_basis IN ('basic','gross')", name="ck_payroll_configurations_overtime_basis"
        ),
        sa.CheckConstraint(
            "overtime_multiplier > 0", name="ck_payroll_configurations_overtime_multiplier_positive"
        ),
        sa.CheckConstraint(
            "overtime_min_hours >= 0",
            name="ck_payroll_configurations_overtime_min_hours_non_negative",
        ),
        sa.CheckConstraint(
            "overtime_max_hours IS NULL OR overtime_max_hours >= overtime_min_hours",
            name="ck_payroll_configurations_overtime_window_ordered",
        ),
        sa.CheckConstraint(
            "rounding_rule IN ('none','nearest_whole','nearest_half','custom')",
            name="ck_payroll_configurations_rounding_rule",
        ),
        sa.CheckConstraint(
            "rounding_rule <> 'custom' OR (rounding_precision IS NOT NULL AND rounding_precision > 0)",
            name="ck_payroll_configurations_custom_rounding_has_precision",
        ),
        comment="The payroll configuration singleton.",
    )
    op.create_index(
        "ix_payroll_configurations_deleted_at", "payroll_configurations", ["deleted_at"]
    )

    # -- Configuration history ----------------------------------------------
    op.create_table(
        "payroll_configuration_history",
        sa.Column("configuration_id", sa.UUID(), nullable=False),
        sa.Column("field", sa.String(length=60), nullable=False),
        sa.Column("previous_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_by_id", sa.UUID(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_configuration_history"),
        sa.ForeignKeyConstraint(
            ["configuration_id"],
            ["payroll_configurations.id"],
            name="fk_payroll_configuration_history_configuration_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_id"],
            ["users.id"],
            name="fk_payroll_configuration_history_changed_by_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("payroll_configuration_history"),
        comment="Append-only payroll configuration change history.",
    )
    op.create_index(
        "ix_payroll_configuration_history_configuration_id",
        "payroll_configuration_history",
        ["configuration_id"],
    )
    op.create_index(
        "ix_payroll_configuration_history_field", "payroll_configuration_history", ["field"]
    )
    op.create_index(
        "ix_payroll_configuration_history_deleted_at",
        "payroll_configuration_history",
        ["deleted_at"],
    )
    op.create_index(
        "ix_payroll_configuration_history_field_created",
        "payroll_configuration_history",
        ["field", "created_at"],
    )

    # -- Periods ------------------------------------------------------------
    op.create_table(
        "payroll_periods",
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_periods"),
        *_actor_constraints("payroll_periods"),
        sa.CheckConstraint(
            "status IN ('open','processing','under_review','approved','finalized','cancelled')",
            name="ck_payroll_periods_status",
        ),
        sa.CheckConstraint("end_date >= start_date", name="ck_payroll_periods_window_ordered"),
        sa.CheckConstraint("pay_date >= start_date", name="ck_payroll_periods_pay_date_after_start"),
        comment="Payroll periods; the calculation engine of a later phase runs against one.",
    )
    op.create_index("ix_payroll_periods_name", "payroll_periods", ["name"])
    op.create_index("ix_payroll_periods_status", "payroll_periods", ["status"])
    op.create_index("ix_payroll_periods_start_date", "payroll_periods", ["start_date"])
    op.create_index("ix_payroll_periods_deleted_at", "payroll_periods", ["deleted_at"])
    op.create_index("ix_payroll_periods_window", "payroll_periods", ["start_date", "end_date"])
    op.create_index(
        "uq_payroll_periods_name_ci", "payroll_periods", [sa.text("lower(name)")], unique=True
    )

    # -- Leave rules ----------------------------------------------------------
    op.create_table(
        "payroll_leave_rules",
        sa.Column("leave_type_id", sa.UUID(), nullable=False),
        sa.Column("treatment", sa.String(length=20), nullable=False),
        sa.Column("deduction_basis", sa.String(length=20), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_leave_rules"),
        sa.UniqueConstraint("leave_type_id", name="uq_payroll_leave_rules_leave_type"),
        sa.ForeignKeyConstraint(
            ["leave_type_id"],
            ["leave_types.id"],
            name="fk_payroll_leave_rules_leave_type_id_leave_types",
            ondelete="RESTRICT",
        ),
        *_actor_constraints("payroll_leave_rules"),
        sa.CheckConstraint("treatment IN ('paid','unpaid')", name="ck_payroll_leave_rules_treatment"),
        sa.CheckConstraint(
            "deduction_basis IS NULL OR deduction_basis IN ('calendar_days','working_days')",
            name="ck_payroll_leave_rules_deduction_basis",
        ),
        sa.CheckConstraint(
            "treatment <> 'unpaid' OR deduction_basis IS NOT NULL",
            name="ck_payroll_leave_rules_unpaid_has_basis",
        ),
        sa.CheckConstraint(
            "treatment <> 'paid' OR deduction_basis IS NULL",
            name="ck_payroll_leave_rules_paid_has_no_basis",
        ),
        sa.CheckConstraint(
            "status IN ('active','inactive')", name="ck_payroll_leave_rules_status"
        ),
        comment="Payroll treatment of each leave type.",
    )
    op.create_index("ix_payroll_leave_rules_leave_type_id", "payroll_leave_rules", ["leave_type_id"])
    op.create_index("ix_payroll_leave_rules_status", "payroll_leave_rules", ["status"])
    op.create_index("ix_payroll_leave_rules_deleted_at", "payroll_leave_rules", ["deleted_at"])

    # -- Employee settings ------------------------------------------------------
    op.create_table(
        "payroll_employee_settings",
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("eligibility", sa.String(length=20), server_default="eligible", nullable=False),
        sa.Column("eligibility_reason", sa.String(length=30), nullable=True),
        sa.Column("frequency_override", sa.String(length=20), nullable=True),
        sa.Column("proration_override", sa.String(length=20), nullable=True),
        sa.Column("overtime_eligible", sa.Boolean(), nullable=True),
        sa.Column("unpaid_leave_deduction", sa.Boolean(), nullable=True),
        sa.Column("payroll_effective_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payroll_employee_settings"),
        sa.UniqueConstraint("employee_id", name="uq_payroll_employee_settings_employee"),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_payroll_employee_settings_employee_id_employees",
            ondelete="RESTRICT",
        ),
        *_actor_constraints("payroll_employee_settings"),
        sa.CheckConstraint(
            "eligibility IN ('eligible','not_eligible','suspended')",
            name="ck_payroll_employee_settings_eligibility",
        ),
        sa.CheckConstraint(
            "eligibility_reason IS NULL OR eligibility_reason IN "
            "('active_employee','exited_employee','contractor','payroll_excluded','pending_onboarding')",
            name="ck_payroll_employee_settings_eligibility_reason",
        ),
        sa.CheckConstraint(
            "frequency_override IS NULL OR frequency_override IN ('monthly','weekly','biweekly')",
            name="ck_payroll_employee_settings_frequency_override",
        ),
        sa.CheckConstraint(
            "proration_override IS NULL OR proration_override IN ('calendar_days','working_days')",
            name="ck_payroll_employee_settings_proration_override",
        ),
        comment="Per-employee payroll settings; absence of a row means not configured.",
    )
    op.create_index(
        "ix_payroll_employee_settings_employee_id", "payroll_employee_settings", ["employee_id"]
    )
    op.create_index(
        "ix_payroll_employee_settings_deleted_at", "payroll_employee_settings", ["deleted_at"]
    )


def _seed_configuration() -> None:
    """The singleton, with the brief's defaults. Every column has a server
    default, so inserting the lock column is inserting the row."""
    op.execute(
        sa.text(
            "INSERT INTO payroll_configurations (singleton) VALUES (true)"
            " ON CONFLICT (singleton) DO NOTHING"
        )
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
    """Derived from ``SYSTEM_ROLES``, which for these six codes means
    Administrator and Super Admin and nobody else."""
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

    for column, _default, _comment in _COMPONENT_FLAGS:
        op.drop_column("salary_components", column)

    op.alter_column("permissions", "action", type_=sa.String(length=20))
