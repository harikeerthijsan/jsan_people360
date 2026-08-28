"""Payroll Phase 8: reports and full & final settlement.

Revision ID: 0031_payroll_reports_settlement
Revises: 0030_payslips
Create Date: 2026-08-25 15:00:00

Three tables and seven permissions. Reports need no table of their own —
they are read from finalized payroll runs.

**full_final_settlements** — one per offboarding case (UNIQUE), the exit
facts copied at creation, the calculation inputs, the four component totals
stored separately, the workflow milestones and the immutable snapshot.
**full_final_settlement_items** — one row per figure, rebuilt on each
calculation. **full_final_settlement_adjustments** — proposed additions or
recoveries with a mandatory reason and an approval decision.

No seeded role below Administrator receives any of the seven permissions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.core.permissions import MODULES_BY_KEY, SYSTEM_ROLES, PermissionAction, action_label, code

revision: str = "0031_payroll_reports_settlement"
down_revision: str | None = "0030_payslips"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODULE = "payroll"

_NEW_ACTIONS = (
    PermissionAction.REPORT_VIEW,
    PermissionAction.REPORT_EXPORT,
    PermissionAction.SETTLEMENT_VIEW,
    PermissionAction.SETTLEMENT_CREATE,
    PermissionAction.SETTLEMENT_UPDATE,
    PermissionAction.SETTLEMENT_APPROVE,
    PermissionAction.SETTLEMENT_FINALIZE,
)

_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "payroll:report_view": "See payroll reports across the organization.",
    "payroll:report_export": "Export payroll reports as CSV or XLSX.",
    "payroll:settlement_view": "See full & final settlements and the exiting-employee list.",
    "payroll:settlement_create": "Open a full & final settlement for an exiting employee.",
    "payroll:settlement_update": "Calculate a settlement, propose adjustments, submit it and "
    "complete its review.",
    "payroll:settlement_approve": "Decide adjustments and approve (or reopen) a settlement.",
    "payroll:settlement_finalize": "Settle an approved settlement, freezing it.",
}

_TABLES = (
    "full_final_settlement_items",
    "full_final_settlement_adjustments",
    "full_final_settlements",
)


def _audit_columns() -> list[sa.Column[object]]:
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


def _user_fk(table: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], ["users.id"], name=f"fk_{table}_{column}_users", ondelete="SET NULL"
    )


def _money(name: str) -> sa.Column[object]:
    return sa.Column(name, sa.Numeric(precision=14, scale=2), server_default="0", nullable=False)


def upgrade() -> None:
    op.create_table(
        "full_final_settlements",
        sa.Column("settlement_code", sa.String(length=40), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("offboarding_case_id", sa.UUID(), nullable=False),
        sa.Column("resignation_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("joining_date", sa.Date(), nullable=True),
        sa.Column("last_working_date", sa.Date(), nullable=False),
        sa.Column("exit_type", sa.String(length=40), server_default="resignation", nullable=False),
        sa.Column("exit_reason", sa.String(length=200), nullable=True),
        sa.Column("final_period_id", sa.UUID(), nullable=True),
        sa.Column("compensation_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("monthly_gross", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("basic_salary", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("daily_rate", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("paid_through", sa.Date(), nullable=True),
        sa.Column("unpaid_salary_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "unpaid_leave_days", sa.Numeric(precision=5, scale=1), server_default="0", nullable=False
        ),
        sa.Column("overtime_hours", sa.Numeric(precision=6, scale=2), server_default="0", nullable=False),
        sa.Column("leave_summary", JSONB(), server_default="[]", nullable=False),
        sa.Column("assets", JSONB(), server_default="[]", nullable=False),
        sa.Column("issues", JSONB(), server_default="[]", nullable=False),
        _money("final_earnings"),
        _money("approved_encashments"),
        _money("approved_adjustments"),
        _money("final_deductions"),
        _money("settlement_amount"),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by_id", sa.UUID(), nullable=True),
        sa.Column("review_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_completed_by_id", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("approval_comment", sa.String(length=400), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_by_id", sa.UUID(), nullable=True),
        sa.Column("settlement_reference", sa.String(length=100), nullable=True),
        sa.Column("final_snapshot", JSONB(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_full_final_settlements"),
        sa.UniqueConstraint("offboarding_case_id", name="uq_full_final_settlements_case"),
        sa.UniqueConstraint("settlement_code", name="uq_full_final_settlements_code"),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_full_final_settlements_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["offboarding_case_id"],
            ["offboarding_cases.id"],
            name="fk_full_final_settlements_offboarding_case_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resignation_id"],
            ["resignations.id"],
            name="fk_full_final_settlements_resignation_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["final_period_id"],
            ["payroll_periods.id"],
            name="fk_full_final_settlements_final_period_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["compensation_id"],
            ["employee_compensation.id"],
            name="fk_full_final_settlements_compensation_id",
            ondelete="SET NULL",
        ),
        _user_fk("full_final_settlements", "submitted_by_id"),
        _user_fk("full_final_settlements", "review_completed_by_id"),
        _user_fk("full_final_settlements", "approved_by_id"),
        _user_fk("full_final_settlements", "settled_by_id"),
        *_actor_constraints("full_final_settlements"),
        sa.CheckConstraint(
            "status IN ('draft','under_review','approved','settled')",
            name="ck_full_final_settlements_status",
        ),
        comment="Full & final settlements: exit facts, components, workflow, snapshot.",
    )
    op.create_index("ix_full_final_settlements_employee_id", "full_final_settlements", ["employee_id"])
    op.create_index("ix_full_final_settlements_status", "full_final_settlements", ["status"])
    op.create_index(
        "ix_full_final_settlements_last_working_date", "full_final_settlements", ["last_working_date"]
    )
    op.create_index(
        "ix_full_final_settlements_status_lwd", "full_final_settlements", ["status", "last_working_date"]
    )
    op.create_index("ix_full_final_settlements_deleted_at", "full_final_settlements", ["deleted_at"])

    op.create_table(
        "full_final_settlement_adjustments",
        sa.Column("settlement_id", sa.UUID(), nullable=False),
        sa.Column("adjustment_type", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("reason", sa.String(length=400), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("decided_by_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(length=400), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_full_final_settlement_adjustments"),
        sa.ForeignKeyConstraint(
            ["settlement_id"],
            ["full_final_settlements.id"],
            name="fk_full_final_settlement_adjustments_settlement_id",
            ondelete="CASCADE",
        ),
        _user_fk("full_final_settlement_adjustments", "decided_by_id"),
        *_actor_constraints("full_final_settlement_adjustments"),
        sa.CheckConstraint(
            "adjustment_type IN ('final_bonus','incentive','leave_encashment','other_earning',"
            "'recovery','asset_recovery','other_deduction')",
            name="ck_full_final_settlement_adjustments_adjustment_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="ck_full_final_settlement_adjustments_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_full_final_settlement_adjustments_amount_positive"),
        comment="Proposed settlement adjustments with their approval decision.",
    )
    op.create_index(
        "ix_full_final_settlement_adjustments_settlement_id",
        "full_final_settlement_adjustments",
        ["settlement_id"],
    )
    op.create_index(
        "ix_full_final_settlement_adjustments_status", "full_final_settlement_adjustments", ["status"]
    )
    op.create_index(
        "ix_full_final_settlement_adjustments_deleted_at",
        "full_final_settlement_adjustments",
        ["deleted_at"],
    )

    op.create_table(
        "full_final_settlement_items",
        sa.Column("settlement_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("basis", sa.String(length=300), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("source", sa.String(length=20), server_default="computed", nullable=False),
        sa.Column("adjustment_id", sa.UUID(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_full_final_settlement_items"),
        sa.ForeignKeyConstraint(
            ["settlement_id"],
            ["full_final_settlements.id"],
            name="fk_full_final_settlement_items_settlement_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["adjustment_id"],
            ["full_final_settlement_adjustments.id"],
            name="fk_full_final_settlement_items_adjustment_id",
            ondelete="SET NULL",
        ),
        *_actor_constraints("full_final_settlement_items"),
        sa.CheckConstraint(
            "category IN ('earning','encashment','adjustment','deduction')",
            name="ck_full_final_settlement_items_category",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_full_final_settlement_items_amount_non_negative"),
        comment="Settlement components, one row per figure.",
    )
    op.create_index(
        "ix_full_final_settlement_items_settlement_id", "full_final_settlement_items", ["settlement_id"]
    )
    op.create_index(
        "ix_full_final_settlement_items_category", "full_final_settlement_items", ["category"]
    )
    op.create_index(
        "ix_full_final_settlement_items_deleted_at", "full_final_settlement_items", ["deleted_at"]
    )

    _add_permissions()
    _grant_permissions()


def _add_permissions() -> None:
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
