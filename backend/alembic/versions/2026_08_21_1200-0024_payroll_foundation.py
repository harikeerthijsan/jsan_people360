"""Payroll foundation: salary structures, components and employee compensation.

Revision ID: 0024_payroll_foundation
Revises: 0023_drop_employees_shift_id
Create Date: 2026-08-21 12:00:00

Six tables, seven permissions, and one partial unique index that carries the
module's central rule at the database: one employee cannot have two open-ended
active compensation records, however the requests race.

**A compensation record is a period, never a mutable number.** A revision ends
the current record and opens a new one; ``salary_history`` records the change,
its reason and its author, append-only. No endpoint updates or deletes either.

**No seeded role below Administrator receives any payroll permission.**
Salary is the record RBAC exists for, and the brief is explicit: HR manages
compensation only through payroll permissions ticked on purpose, and a
manager's reporting line grants nothing here — ``payroll:team_view`` is the
deliberate, separate grant for that. Administrator and Super Admin hold the
whole catalogue, so they receive all seven, and nobody else receives anything.

**Nothing calculates.** These tables store the inputs a later payroll phase
will compute against; the phase that creates them deliberately does not.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.permissions import MODULES_BY_KEY, SYSTEM_ROLES, PermissionAction, action_label, code

revision: str = "0024_payroll_foundation"
down_revision: str | None = "0023_drop_employees_shift_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODULE = "payroll"

#: The seven actions this migration shipped with, frozen. Deliberately NOT
#: ``MODULES_BY_KEY["payroll"].actions``: the registry keeps growing (Phase 2
#: added six more), and a migration must describe its own moment rather than
#: whatever the code says on the day it happens to run.
_ACTIONS = (
    PermissionAction.VIEW,
    PermissionAction.CREATE,
    PermissionAction.UPDATE,
    PermissionAction.HISTORY_VIEW,
    PermissionAction.STRUCTURE_MANAGE,
    PermissionAction.COMPONENT_MANAGE,
    PermissionAction.TEAM_VIEW,
)

#: Dropped in reverse dependency order.
_TABLES = (
    "salary_history",
    "employee_compensation_components",
    "employee_compensation",
    "salary_structure_components",
    "salary_components",
    "salary_structures",
)

#: What an administrator reads on the roles screen before ticking the box.
_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "payroll:view": "See employee compensation. Scoped by the reporting line unless the caller "
    "also holds employees:view_all.",
    "payroll:create": "Assign compensation to an employee.",
    "payroll:update": "Revise an employee's salary. Every revision is recorded in the history.",
    "payroll:history_view": "See an employee's salary change history.",
    "payroll:structure_manage": "Create, edit, activate and deactivate salary structures.",
    "payroll:component_manage": "Create, edit, activate and deactivate salary components.",
    "payroll:team_view": "See direct reports' compensation. The explicit grant for managers — "
    "the reporting line alone opens nothing in payroll.",
}

_PERCENTAGE_COHERENT = (
    "calculation_type <> 'percentage' OR (value <= 100 AND percentage_basis IS NOT NULL)"
)
_FIXED_HAS_NO_BASIS = "calculation_type <> 'fixed' OR percentage_basis IS NULL"

#: name, code, type, calculation, value, basis. The starting configuration from
#: §2 of the brief — editable on the components screen, not a list any
#: calculation depends on. Values are defaults a new assignment starts from.
_COMPONENTS: tuple[tuple[str, str, str, str, str, str | None], ...] = (
    ("Basic Salary", "BASIC", "earning", "fixed", "0", None),
    ("House Rent Allowance", "HRA", "earning", "percentage", "40", "basic"),
    ("Conveyance Allowance", "CONVEYANCE", "earning", "fixed", "0", None),
    ("Medical Allowance", "MEDICAL", "earning", "fixed", "0", None),
    ("Special Allowance", "SPECIAL", "earning", "fixed", "0", None),
    ("Bonus", "BONUS", "earning", "fixed", "0", None),
    ("Commission", "COMMISSION", "earning", "fixed", "0", None),
    ("Overtime", "OVERTIME", "earning", "fixed", "0", None),
    ("Income Tax", "TAX", "deduction", "fixed", "0", None),
    ("Provident Fund", "PF", "deduction", "percentage", "12", "basic"),
    ("Insurance", "INSURANCE", "deduction", "fixed", "0", None),
    ("Professional Tax", "PROF_TAX", "deduction", "fixed", "0", None),
    ("Other Deduction", "OTHER_DEDUCTION", "deduction", "fixed", "0", None),
)


def upgrade() -> None:
    _create_tables()
    _seed_components()
    _add_permissions()
    _grant_permissions()


def _audit_columns() -> list[sa.Column[object]]:
    """The platform's audit contract.

    NOTE: no ``use_alter`` on the actor foreign keys. Inside ``op.create_table``
    SQLAlchemy silently *omits* a constraint marked that way — the trap 0014
    documents — so the columns would exist with nothing enforcing them.
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
    # -- Structures ------------------------------------------------------
    op.create_table(
        "salary_structures",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pay_frequency", sa.String(length=20), server_default="monthly", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_salary_structures"),
        *_actor_constraints("salary_structures"),
        sa.CheckConstraint(
            "pay_frequency IN ('monthly','weekly','biweekly')",
            name="ck_salary_structures_pay_frequency",
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','inactive')", name="ck_salary_structures_status"
        ),
        sa.CheckConstraint("char_length(currency) = 3", name="ck_salary_structures_currency_iso"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_salary_structures_effective_window_ordered",
        ),
        comment="Reusable salary structure templates.",
    )
    op.create_index("ix_salary_structures_name", "salary_structures", ["name"])
    op.create_index("ix_salary_structures_pay_frequency", "salary_structures", ["pay_frequency"])
    op.create_index("ix_salary_structures_status", "salary_structures", ["status"])
    op.create_index("ix_salary_structures_deleted_at", "salary_structures", ["deleted_at"])
    op.create_index(
        "uq_salary_structures_name_ci", "salary_structures", [sa.text("lower(name)")], unique=True
    )

    # -- Components ------------------------------------------------------
    op.create_table(
        "salary_components",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("component_type", sa.String(length=20), nullable=False),
        sa.Column("calculation_type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("percentage_basis", sa.String(length=20), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_salary_components"),
        sa.UniqueConstraint("code", name="uq_salary_components_code"),
        *_actor_constraints("salary_components"),
        sa.CheckConstraint(
            "component_type IN ('earning','deduction')", name="ck_salary_components_component_type"
        ),
        sa.CheckConstraint(
            "calculation_type IN ('fixed','percentage')",
            name="ck_salary_components_calculation_type",
        ),
        sa.CheckConstraint(
            "percentage_basis IS NULL OR percentage_basis IN ('basic','gross')",
            name="ck_salary_components_percentage_basis",
        ),
        sa.CheckConstraint("value >= 0", name="ck_salary_components_value_non_negative"),
        sa.CheckConstraint(_PERCENTAGE_COHERENT, name="ck_salary_components_percentage_coherent"),
        sa.CheckConstraint(_FIXED_HAS_NO_BASIS, name="ck_salary_components_fixed_has_no_basis"),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_salary_components_status"),
        comment="Configurable compensation components.",
    )
    op.create_index("ix_salary_components_name", "salary_components", ["name"])
    op.create_index("ix_salary_components_component_type", "salary_components", ["component_type"])
    op.create_index("ix_salary_components_status", "salary_components", ["status"])
    op.create_index("ix_salary_components_deleted_at", "salary_components", ["deleted_at"])

    # -- Structure membership ---------------------------------------------
    op.create_table(
        "salary_structure_components",
        sa.Column("structure_id", sa.UUID(), nullable=False),
        sa.Column("component_id", sa.UUID(), nullable=False),
        sa.Column("default_value", sa.Numeric(precision=12, scale=2), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_salary_structure_components"),
        sa.UniqueConstraint(
            "structure_id", "component_id", name="uq_salary_structure_components_pair"
        ),
        sa.ForeignKeyConstraint(
            ["structure_id"],
            ["salary_structures.id"],
            name="fk_salary_structure_components_structure_id_salary_structures",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["component_id"],
            ["salary_components.id"],
            name="fk_salary_structure_components_component_id_salary_components",
            ondelete="RESTRICT",
        ),
        *_actor_constraints("salary_structure_components"),
        sa.CheckConstraint(
            "default_value IS NULL OR default_value >= 0",
            name="ck_salary_structure_components_default_value_non_negative",
        ),
        comment="Which components a salary structure carries.",
    )
    op.create_index(
        "ix_salary_structure_components_structure_id", "salary_structure_components", ["structure_id"]
    )
    op.create_index(
        "ix_salary_structure_components_component_id", "salary_structure_components", ["component_id"]
    )
    op.create_index(
        "ix_salary_structure_components_deleted_at", "salary_structure_components", ["deleted_at"]
    )

    # -- Employee compensation --------------------------------------------
    op.create_table(
        "employee_compensation",
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("salary_structure_id", sa.UUID(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("annual_ctc", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("annual_gross", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("monthly_gross", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("basic_salary", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_employee_compensation"),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_employee_compensation_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["salary_structure_id"],
            ["salary_structures.id"],
            name="fk_employee_compensation_salary_structure_id_salary_structures",
            ondelete="RESTRICT",
        ),
        *_actor_constraints("employee_compensation"),
        sa.CheckConstraint("status IN ('active','ended')", name="ck_employee_compensation_status"),
        sa.CheckConstraint(
            "char_length(currency) = 3", name="ck_employee_compensation_currency_iso"
        ),
        sa.CheckConstraint("annual_ctc >= 0", name="ck_employee_compensation_annual_ctc_non_negative"),
        sa.CheckConstraint(
            "annual_gross >= 0", name="ck_employee_compensation_annual_gross_non_negative"
        ),
        sa.CheckConstraint(
            "monthly_gross >= 0", name="ck_employee_compensation_monthly_gross_non_negative"
        ),
        sa.CheckConstraint(
            "basic_salary >= 0", name="ck_employee_compensation_basic_salary_non_negative"
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_employee_compensation_effective_window_ordered",
        ),
        comment="Employee compensation records, one per effective period.",
    )
    op.create_index("ix_employee_compensation_employee_id", "employee_compensation", ["employee_id"])
    op.create_index(
        "ix_employee_compensation_salary_structure_id", "employee_compensation", ["salary_structure_id"]
    )
    op.create_index("ix_employee_compensation_status", "employee_compensation", ["status"])
    op.create_index(
        "ix_employee_compensation_effective_from", "employee_compensation", ["effective_from"]
    )
    op.create_index("ix_employee_compensation_deleted_at", "employee_compensation", ["deleted_at"])
    op.create_index(
        "ix_employee_compensation_employee_from",
        "employee_compensation",
        ["employee_id", "effective_from"],
    )
    # One open-ended active record per employee, enforced where two concurrent
    # assignments cannot talk their way past it.
    op.create_index(
        "uq_employee_compensation_open",
        "employee_compensation",
        ["employee_id"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL AND status = 'active' AND deleted_at IS NULL"),
    )

    # -- Compensation components -------------------------------------------
    op.create_table(
        "employee_compensation_components",
        sa.Column("compensation_id", sa.UUID(), nullable=False),
        sa.Column("component_id", sa.UUID(), nullable=False),
        sa.Column("calculation_type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("percentage_basis", sa.String(length=20), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_employee_compensation_components"),
        sa.UniqueConstraint(
            "compensation_id", "component_id", name="uq_employee_compensation_components_pair"
        ),
        # Hand-shortened: the convention-derived names exceed PostgreSQL's
        # 63-character identifier limit and would be silently truncated.
        sa.ForeignKeyConstraint(
            ["compensation_id"],
            ["employee_compensation.id"],
            name="fk_compensation_components_compensation_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["component_id"],
            ["salary_components.id"],
            name="fk_compensation_components_component_id",
            ondelete="RESTRICT",
        ),
        *_actor_constraints("employee_compensation_components"),
        sa.CheckConstraint(
            "calculation_type IN ('fixed','percentage')",
            name="ck_employee_compensation_components_calculation_type",
        ),
        sa.CheckConstraint(
            "percentage_basis IS NULL OR percentage_basis IN ('basic','gross')",
            name="ck_employee_compensation_components_percentage_basis",
        ),
        sa.CheckConstraint(
            "value >= 0", name="ck_employee_compensation_components_value_non_negative"
        ),
        sa.CheckConstraint(
            _PERCENTAGE_COHERENT, name="ck_employee_compensation_components_percentage_coherent"
        ),
        sa.CheckConstraint(
            _FIXED_HAS_NO_BASIS, name="ck_employee_compensation_components_fixed_has_no_basis"
        ),
        comment="Component values snapshotted onto a compensation record.",
    )
    op.create_index(
        "ix_employee_compensation_components_compensation_id",
        "employee_compensation_components",
        ["compensation_id"],
    )
    op.create_index(
        "ix_employee_compensation_components_component_id",
        "employee_compensation_components",
        ["component_id"],
    )
    op.create_index(
        "ix_employee_compensation_components_deleted_at",
        "employee_compensation_components",
        ["deleted_at"],
    )

    # -- Salary history ------------------------------------------------------
    op.create_table(
        "salary_history",
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("compensation_id", sa.UUID(), nullable=False),
        sa.Column("previous_compensation_id", sa.UUID(), nullable=True),
        sa.Column("previous_annual_ctc", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("new_annual_ctc", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by_id", sa.UUID(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_salary_history"),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_salary_history_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["compensation_id"],
            ["employee_compensation.id"],
            name="fk_salary_history_compensation_id_employee_compensation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_compensation_id"],
            ["employee_compensation.id"],
            # Hand-shortened for the 63-character identifier limit.
            name="fk_salary_history_previous_compensation_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_id"],
            ["users.id"],
            name="fk_salary_history_changed_by_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("salary_history"),
        sa.CheckConstraint("new_annual_ctc >= 0", name="ck_salary_history_new_ctc_non_negative"),
        sa.CheckConstraint(
            "previous_annual_ctc IS NULL OR previous_annual_ctc >= 0",
            name="ck_salary_history_previous_ctc_non_negative",
        ),
        comment="Append-only salary change history.",
    )
    op.create_index("ix_salary_history_employee_id", "salary_history", ["employee_id"])
    op.create_index("ix_salary_history_compensation_id", "salary_history", ["compensation_id"])
    op.create_index("ix_salary_history_deleted_at", "salary_history", ["deleted_at"])
    op.create_index(
        "ix_salary_history_employee_created", "salary_history", ["employee_id", "created_at"]
    )


def _seed_components() -> None:
    for name, component_code, component_type, calculation, value, basis in _COMPONENTS:
        op.execute(
            sa.text(
                "INSERT INTO salary_components"
                "(name, code, component_type, calculation_type, value, percentage_basis, status)"
                " VALUES (:name, :code, :ctype, :calc, CAST(:value AS numeric(12,2)), :basis, 'active')"
                " ON CONFLICT (code) DO NOTHING"
            ).bindparams(
                name=name,
                code=component_code,
                ctype=component_type,
                calc=calculation,
                value=value,
                basis=basis,
            )
        )


def _add_permissions() -> None:
    """``ON CONFLICT`` because ``reconcile_catalogue`` is reachable at runtime."""
    module = MODULES_BY_KEY[_MODULE]
    for action in _ACTIONS:
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
    """Grant each seeded role exactly what the catalogue says it holds.

    Derived from ``SYSTEM_ROLES`` rather than a literal list, so this migration
    and the catalogue cannot disagree about the grant the access model turns
    on — which for payroll is that only Administrator and Super Admin receive
    anything at all.

    Custom roles are untouched, for the reason 0016 gives: guessing which of
    them should gain a new power is not this migration's call.
    """
    new_codes = {code(_MODULE, action) for action in _ACTIONS}
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
    codes = sorted(code(_MODULE, action) for action in _ACTIONS)
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN"
            " (SELECT id FROM permissions WHERE code = ANY(:codes))"
        ).bindparams(codes=codes)
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:codes)").bindparams(codes=codes))

    for table in _TABLES:
        op.drop_table(table)
