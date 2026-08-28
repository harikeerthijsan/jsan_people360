"""Asset management: the register, its custody trail and its offboarding link.

Revision ID: 0019_asset_management
Revises: 0018_resignation_offboarding
Create Date: 2026-08-19 09:00:00

Seven tables, eleven permissions, fourteen seeded categories, and one column
added to a table that has been waiting for it.

**The register and the transactions are separate.** ``assets`` holds current
state; ``asset_assignments``, ``asset_returns`` and ``asset_transfers`` hold
what happened. An asset system whose answer to "who has this laptop" is a
mutable column has no answer at all to "who had it in March", which is the
question actually asked -- months later, about a thing that has since been
disposed of.

**Two partial unique indexes carry rules the application also enforces.** One
asset can have at most one *open* assignment, and a serial number is unique
*where it is present* -- most accessories have none, and several NULLs are not
duplicates of each other. Both are written as partial indexes because a plain
UNIQUE constraint cannot express either.

**``asset_clearance.asset_id`` is the offboarding integration**, and it is one
column rather than a second clearance system. The table was written in 0018 with
a docstring saying that if an asset module ever arrived it would supply the rows
and this table would keep recording their return. It has, and it does.

**HR is granted ``assets:view`` and nothing else.** The eight custody and
lifecycle actions go to Administrator and Super Admin. HR needs to see what a
leaver is holding in order to run a clearance; giving them the power to issue,
recall, repair or write off company property is a different job.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.permissions import MODULES_BY_KEY, SYSTEM_ROLES, PermissionAction, action_label, code

revision: str = "0019_asset_management"
down_revision: str | None = "0018_resignation_offboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ASSET_CODE_SEQUENCE = "assets_code_seq"

#: Dropped in reverse dependency order.
_TABLES = (
    "asset_history",
    "asset_maintenance",
    "asset_transfers",
    "asset_returns",
    "asset_assignments",
    "assets",
    "asset_categories",
)

_MODULE = "assets"

#: What an administrator reads on the roles screen before ticking the box.
_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "assets:view": "See the asset register. Narrowed by the reporting line unless the caller also "
    "holds employees:view_all.",
    "assets:create": "Register a new asset.",
    "assets:update": "Amend asset details. Does not include moving custody.",
    "assets:assign": "Issue an available asset to an employee.",
    "assets:return": "Take an asset back and record the condition it came back in.",
    "assets:transfer": "Move custody directly from one employee to another.",
    "assets:maintain": "Schedule, start and complete maintenance.",
    "assets:retire": "Take an asset out of service permanently.",
    "assets:dispose": "Record final disposal. Irreversible.",
    "assets:manage": "Configure asset categories and administer the register.",
    "assets:export": "Export asset reports.",
}

#: name, code, returnable. The starting configuration from §2 of the brief --
#: editable on the categories screen, not a list the code depends on.
#:
#: ``returnable`` is the one judgement here: a laptop is expected back at exit
#: and a SIM usually is, while a consumable headset frequently is not. It only
#: decides whether a clearance row blocks a completion by default; any row can
#: still be waived by an authorized user, and the waiver is audited.
_CATEGORIES: tuple[tuple[str, str, bool], ...] = (
    ("Laptop", "LAPTOP", True),
    ("Desktop", "DESKTOP", True),
    ("Monitor", "MONITOR", True),
    ("Mobile", "MOBILE", True),
    ("Tablet", "TABLET", True),
    ("Keyboard", "KEYBOARD", False),
    ("Mouse", "MOUSE", False),
    ("Headset", "HEADSET", False),
    ("Printer", "PRINTER", True),
    ("Access Card", "ACCESS_CARD", True),
    ("ID Card", "ID_CARD", True),
    ("SIM", "SIM", True),
    ("Software License", "SOFTWARE_LICENSE", True),
    ("Other", "OTHER", True),
)


def upgrade() -> None:
    _create_sequence()
    _create_tables()
    _seed_categories()
    _link_offboarding_clearance()
    _add_permissions()
    _grant_permissions()


def _create_sequence() -> None:
    op.execute(f"CREATE SEQUENCE {ASSET_CODE_SEQUENCE} AS bigint START WITH 1")


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
    # -- Categories ------------------------------------------------------
    op.create_table(
        "asset_categories",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("returnable", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_asset_categories"),
        sa.UniqueConstraint("code", name="uq_asset_categories_code"),
        *_actor_constraints("asset_categories"),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_asset_categories_status"),
        comment="Configurable asset categories.",
    )
    op.create_index("ix_asset_categories_name", "asset_categories", ["name"])
    op.create_index("ix_asset_categories_status", "asset_categories", ["status"])
    op.create_index("ix_asset_categories_deleted_at", "asset_categories", ["deleted_at"])

    # -- Assets ----------------------------------------------------------
    op.create_table(
        "assets",
        sa.Column(
            "asset_code",
            sa.String(length=20),
            server_default=sa.text(f"'AST-' || lpad(nextval('{ASSET_CODE_SEQUENCE}')::text, 6, '0')"),
            nullable=False,
        ),
        sa.Column("asset_tag", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("asset_type", sa.String(length=60), nullable=True),
        sa.Column("brand", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("purchase_cost", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("vendor", sa.String(length=150), nullable=True),
        sa.Column("warranty_start", sa.Date(), nullable=True),
        sa.Column("warranty_end", sa.Date(), nullable=True),
        sa.Column("warranty_provider", sa.String(length=150), nullable=True),
        sa.Column("warranty_reference", sa.String(length=120), nullable=True),
        sa.Column("location", sa.String(length=150), nullable=True),
        sa.Column("condition", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="available", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("current_assignment_id", sa.UUID(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
        sa.UniqueConstraint("asset_code", name="uq_assets_asset_code"),
        sa.UniqueConstraint("asset_tag", name="uq_assets_asset_tag"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["asset_categories.id"], name="fk_assets_category_id_asset_categories"
        ),
        *_actor_constraints("assets"),
        sa.CheckConstraint(
            "status IN ('available','assigned','reserved','under_maintenance','damaged','lost',"
            "'retired','disposed')",
            name="ck_assets_status",
        ),
        sa.CheckConstraint(
            "condition IN ('new','excellent','good','fair','damaged')", name="ck_assets_condition"
        ),
        sa.CheckConstraint(
            "purchase_cost IS NULL OR purchase_cost >= 0", name="ck_assets_purchase_cost_non_negative"
        ),
        sa.CheckConstraint(
            "warranty_end IS NULL OR warranty_start IS NULL OR warranty_end >= warranty_start",
            name="ck_assets_warranty_window_ordered",
        ),
        comment="The asset register: one row per physical thing owned.",
    )
    op.create_index("ix_assets_asset_tag", "assets", ["asset_tag"])
    op.create_index("ix_assets_name", "assets", ["name"])
    op.create_index("ix_assets_category_id", "assets", ["category_id"])
    op.create_index("ix_assets_serial_number", "assets", ["serial_number"])
    op.create_index("ix_assets_status", "assets", ["status"])
    op.create_index("ix_assets_condition", "assets", ["condition"])
    op.create_index("ix_assets_vendor", "assets", ["vendor"])
    op.create_index("ix_assets_location", "assets", ["location"])
    op.create_index("ix_assets_warranty_end", "assets", ["warranty_end"])
    op.create_index("ix_assets_deleted_at", "assets", ["deleted_at"])
    op.create_index("ix_assets_status_category", "assets", ["status", "category_id"])
    # Unique *where present*: most accessories have no serial, and a plain
    # UNIQUE would treat two NULLs as distinct while still blocking nothing
    # useful. This blocks a genuine duplicate and permits any number of blanks.
    op.execute(
        "CREATE UNIQUE INDEX uq_assets_serial_number_present ON assets(serial_number)"
        " WHERE serial_number IS NOT NULL AND deleted_at IS NULL"
    )

    # -- Assignments -----------------------------------------------------
    op.create_table(
        "asset_assignments",
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("assigned_date", sa.Date(), nullable=False),
        sa.Column("expected_return_date", sa.Date(), nullable=True),
        sa.Column("condition_at_assignment", sa.String(length=20), nullable=False),
        sa.Column("assigned_by_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_asset_assignments"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_asset_assignments_asset_id_assets"),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name="fk_asset_assignments_employee_id_employees"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_id"], ["users.id"], name="fk_asset_assignments_assigned_by_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("asset_assignments"),
        sa.CheckConstraint(
            "condition_at_assignment IN ('new','excellent','good','fair','damaged')",
            name="ck_asset_assignments_condition_at_assignment",
        ),
        comment="Custody: who held which asset, and when.",
    )
    op.create_index("ix_asset_assignments_asset_id", "asset_assignments", ["asset_id"])
    op.create_index("ix_asset_assignments_employee_id", "asset_assignments", ["employee_id"])
    op.create_index("ix_asset_assignments_deleted_at", "asset_assignments", ["deleted_at"])
    op.create_index(
        "ix_asset_assignments_employee_returned", "asset_assignments", ["employee_id", "returned_at"]
    )
    op.create_index(
        "ix_asset_assignments_asset_assigned", "asset_assignments", ["asset_id", "assigned_date"]
    )
    # One open assignment per asset. The service refuses a second one with a
    # readable message; this is the half that holds when two requests race.
    op.execute(
        "CREATE UNIQUE INDEX uq_asset_assignments_one_open_per_asset ON asset_assignments(asset_id)"
        " WHERE returned_at IS NULL AND deleted_at IS NULL"
    )

    # The pointer back, added now that the target table exists.
    op.create_foreign_key(
        "fk_assets_current_assignment_id_asset_assignments",
        "assets",
        "asset_assignments",
        ["current_assignment_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -- Returns ---------------------------------------------------------
    op.create_table(
        "asset_returns",
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("returned_by_id", sa.UUID(), nullable=False),
        sa.Column("received_by_id", sa.UUID(), nullable=True),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("condition_at_return", sa.String(length=20), nullable=False),
        sa.Column("damage_details", sa.Text(), nullable=True),
        sa.Column("missing_accessories", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_asset_returns"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_asset_returns_asset_id_assets"),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["asset_assignments.id"],
            name="fk_asset_returns_assignment_id_asset_assignments",
        ),
        sa.ForeignKeyConstraint(
            ["returned_by_id"], ["employees.id"], name="fk_asset_returns_returned_by_id_employees"
        ),
        sa.ForeignKeyConstraint(
            ["received_by_id"], ["users.id"], name="fk_asset_returns_received_by_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("asset_returns"),
        sa.CheckConstraint(
            "condition_at_return IN ('new','excellent','good','fair','damaged')",
            name="ck_asset_returns_condition_at_return",
        ),
        comment="Return transactions against an assignment.",
    )
    op.create_index("ix_asset_returns_asset_id", "asset_returns", ["asset_id"])
    op.create_index("ix_asset_returns_assignment_id", "asset_returns", ["assignment_id"])
    op.create_index("ix_asset_returns_returned_by_id", "asset_returns", ["returned_by_id"])
    op.create_index("ix_asset_returns_deleted_at", "asset_returns", ["deleted_at"])

    # -- Transfers -------------------------------------------------------
    op.create_table(
        "asset_transfers",
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("from_employee_id", sa.UUID(), nullable=False),
        sa.Column("to_employee_id", sa.UUID(), nullable=False),
        sa.Column("transfer_date", sa.Date(), nullable=False),
        sa.Column("condition_at_transfer", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_asset_transfers"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_asset_transfers_asset_id_assets"),
        sa.ForeignKeyConstraint(
            ["from_employee_id"], ["employees.id"],
            name="fk_asset_transfers_from_employee_id_employees",
        ),
        sa.ForeignKeyConstraint(
            ["to_employee_id"], ["employees.id"], name="fk_asset_transfers_to_employee_id_employees"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_id"], ["users.id"], name="fk_asset_transfers_approved_by_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("asset_transfers"),
        sa.CheckConstraint(
            "condition_at_transfer IN ('new','excellent','good','fair','damaged')",
            name="ck_asset_transfers_condition",
        ),
        sa.CheckConstraint(
            "from_employee_id <> to_employee_id", name="ck_asset_transfers_transfer_changes_holder"
        ),
        comment="Custody moving directly between two employees.",
    )
    op.create_index("ix_asset_transfers_asset_id", "asset_transfers", ["asset_id"])
    op.create_index("ix_asset_transfers_from_employee_id", "asset_transfers", ["from_employee_id"])
    op.create_index("ix_asset_transfers_to_employee_id", "asset_transfers", ["to_employee_id"])
    op.create_index("ix_asset_transfers_deleted_at", "asset_transfers", ["deleted_at"])
    op.create_index("ix_asset_transfers_asset_date", "asset_transfers", ["asset_id", "transfer_date"])

    # -- Maintenance -----------------------------------------------------
    op.create_table(
        "asset_maintenance",
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("maintenance_type", sa.String(length=30), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("vendor", sa.String(length=150), nullable=True),
        sa.Column("cost", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="scheduled", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_asset_maintenance"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_asset_maintenance_asset_id_assets"),
        *_actor_constraints("asset_maintenance"),
        sa.CheckConstraint(
            "status IN ('scheduled','in_progress','completed','cancelled')",
            name="ck_asset_maintenance_status",
        ),
        sa.CheckConstraint(
            "maintenance_type IN ('preventive','repair','upgrade','inspection','other')",
            name="ck_asset_maintenance_maintenance_type",
        ),
        sa.CheckConstraint("cost IS NULL OR cost >= 0", name="ck_asset_maintenance_cost_non_negative"),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="ck_asset_maintenance_window_ordered"
        ),
        comment="Maintenance records against an asset.",
    )
    op.create_index("ix_asset_maintenance_asset_id", "asset_maintenance", ["asset_id"])
    op.create_index("ix_asset_maintenance_status", "asset_maintenance", ["status"])
    op.create_index("ix_asset_maintenance_maintenance_type", "asset_maintenance", ["maintenance_type"])
    op.create_index("ix_asset_maintenance_start_date", "asset_maintenance", ["start_date"])
    op.create_index("ix_asset_maintenance_deleted_at", "asset_maintenance", ["deleted_at"])
    op.create_index("ix_asset_maintenance_asset_status", "asset_maintenance", ["asset_id", "status"])

    # -- History ---------------------------------------------------------
    op.create_table(
        "asset_history",
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=True),
        sa.Column("previous_value", sa.String(length=200), nullable=True),
        sa.Column("new_value", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_asset_history"),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_asset_history_asset_id_assets", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name="fk_asset_history_employee_id_employees",
            ondelete="SET NULL",
        ),
        *_actor_constraints("asset_history"),
        sa.CheckConstraint(
            "event IN ('created','updated','assigned','returned','transferred','maintenance_started',"
            "'maintenance_completed','damaged','lost','recovered','retired','disposed','status_changed',"
            "'clearance_waived')",
            name="ck_asset_history_event",
        ),
        comment="Append-only event log for one asset.",
    )
    op.create_index("ix_asset_history_asset_id", "asset_history", ["asset_id"])
    op.create_index("ix_asset_history_event", "asset_history", ["event"])
    op.create_index("ix_asset_history_employee_id", "asset_history", ["employee_id"])
    op.create_index("ix_asset_history_deleted_at", "asset_history", ["deleted_at"])
    op.create_index("ix_asset_history_asset_created", "asset_history", ["asset_id", "created_at"])


def _seed_categories() -> None:
    for name, category_code, returnable in _CATEGORIES:
        op.execute(
            sa.text(
                "INSERT INTO asset_categories(name, code, returnable, status)"
                " VALUES (:name, :code, :returnable, 'active')"
                " ON CONFLICT (code) DO NOTHING"
            ).bindparams(name=name, code=category_code, returnable=returnable)
        )


def _link_offboarding_clearance() -> None:
    """One column, not a second clearance system.

    0018 wrote ``asset_clearance`` with a docstring saying that if an asset
    module ever arrived it would supply the rows and this table would keep
    recording their return. This is that column.
    """
    op.add_column(
        "asset_clearance",
        sa.Column(
            "asset_id",
            sa.UUID(),
            nullable=True,
            comment="The registered asset, when the row was seeded from the register. "
            "NULL for hand-entered lines, which stay supported.",
        ),
    )
    op.create_foreign_key(
        "fk_asset_clearance_asset_id_assets",
        "asset_clearance",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_asset_clearance_asset_id", "asset_clearance", ["asset_id"])


def _add_permissions() -> None:
    """``ON CONFLICT`` because ``reconcile_catalogue`` is reachable at runtime."""
    module = MODULES_BY_KEY[_MODULE]
    for action in module.actions:
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
    on -- HR receiving ``assets:view`` and none of the eight custody actions.

    Custom roles are untouched, for the reason 0016 gives: guessing which of
    them should gain a new power is not this migration's call.
    """
    new_codes = {code(_MODULE, action) for action in MODULES_BY_KEY[_MODULE].actions}
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
    codes = sorted(code(_MODULE, action) for action in MODULES_BY_KEY[_MODULE].actions)
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN"
            " (SELECT id FROM permissions WHERE code = ANY(:codes))"
        ).bindparams(codes=codes)
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:codes)").bindparams(codes=codes))

    op.drop_index("ix_asset_clearance_asset_id", table_name="asset_clearance")
    op.drop_constraint("fk_asset_clearance_asset_id_assets", "asset_clearance", type_="foreignkey")
    op.drop_column("asset_clearance", "asset_id")

    # The self-referential pointer has to go before the tables it ties together.
    op.drop_constraint("fk_assets_current_assignment_id_asset_assignments", "assets", type_="foreignkey")
    for table in _TABLES:
        op.drop_table(table)

    op.execute(f"DROP SEQUENCE IF EXISTS {ASSET_CODE_SEQUENCE}")
