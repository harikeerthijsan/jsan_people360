"""Payroll Phase 7: payslips.

Revision ID: 0030_payslips
Revises: 0029_payroll_approval
Create Date: 2026-08-25 09:00:00

One table and three permissions.

**payslips** — one official payslip per employee per finalized run,
UNIQUE-enforced both on the (run, employee) pair and on the payslip number.
Every foreign key is RESTRICT: a payslip that outlives its snapshot, run or
employee would be a document about nothing. The figures stored here are the
snapshot's, copied once for cheap listing; the document file is the only
thing regeneration may replace.

No seeded role below Administrator receives any of the three permissions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.permissions import MODULES_BY_KEY, SYSTEM_ROLES, PermissionAction, action_label, code

revision: str = "0030_payslips"
down_revision: str | None = "0029_payroll_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODULE = "payroll"

_NEW_ACTIONS = (
    PermissionAction.PAYSLIP_VIEW,
    PermissionAction.PAYSLIP_GENERATE,
    PermissionAction.PAYSLIP_DOWNLOAD,
)

_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "payroll:payslip_view": "See payslips: the organization-wide list and any employee's payslip "
    "within scope.",
    "payroll:payslip_generate": "Generate payslips from a finalized run and regenerate a payslip's "
    "document file. Never changes a payroll figure.",
    "payroll:payslip_download": "Download another employee's payslip PDF.",
}


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


def upgrade() -> None:
    op.create_table(
        "payslips",
        sa.Column("payslip_number", sa.String(length=40), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="generated", nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("gross_earnings", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("total_deductions", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("net_pay", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by_id", sa.UUID(), nullable=True),
        sa.Column("regenerated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("regenerated_by_id", sa.UUID(), nullable=True),
        sa.Column("pdf_key", sa.String(length=512), nullable=False),
        sa.Column("pdf_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pdf_checksum", sa.String(length=64), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_payslips"),
        sa.UniqueConstraint("payslip_number", name="uq_payslips_payslip_number"),
        sa.UniqueConstraint("run_id", "employee_id", name="uq_payslips_run_employee"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["payroll_runs.id"], name="fk_payslips_run_id_payroll_runs", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["payroll_employee_records.id"],
            name="fk_payslips_record_id_payroll_employee_records",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["payroll_final_snapshots.id"],
            name="fk_payslips_snapshot_id_payroll_final_snapshots",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name="fk_payslips_employee_id_employees", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["payroll_periods.id"],
            name="fk_payslips_period_id_payroll_periods",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["generated_by_id"], ["users.id"], name="fk_payslips_generated_by_id_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["regenerated_by_id"],
            ["users.id"],
            name="fk_payslips_regenerated_by_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("payslips"),
        sa.CheckConstraint("status IN ('generated')", name="ck_payslips_status"),
        comment="Official payslips rendered from finalized payroll snapshots.",
    )
    op.create_index("ix_payslips_payslip_number", "payslips", ["payslip_number"])
    op.create_index("ix_payslips_run_id", "payslips", ["run_id"])
    op.create_index("ix_payslips_employee_id", "payslips", ["employee_id"])
    op.create_index("ix_payslips_period_id", "payslips", ["period_id"])
    op.create_index("ix_payslips_deleted_at", "payslips", ["deleted_at"])

    _add_permissions()
    _grant_permissions()


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
    op.drop_table("payslips")
