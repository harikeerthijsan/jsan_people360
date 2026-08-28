"""Helpdesk and announcements: the two modules the screens were pretending to have.

Revision ID: 0020_helpdesk_announcements
Revises: 0019_asset_management
Create Date: 2026-08-20 09:00:00

Six tables, eleven permissions, one new action and eight seeded categories.

Both modules existed as screens before they existed as software. ``/hr/helpdesk``
composed the leave and document approval queues and called them "HR Requests",
and the employee dashboard's ``recent_announcements`` was the notification inbox
with a comment saying the platform had no announcements table and that inventing
one would be a second message system.

That comment was right at the time and is now wrong in an interesting way: an
announcement is *not* a second message system, because it does not replace the
notification -- it is the durable thing a notification points at. A notification
says "something happened that concerns you", is personal and is disposable. An
announcement is the company's position on something, is identical for everybody
it reaches, and has to still be readable in six months when somebody asks what
they were told. Publishing one fans out notifications through the existing
system; nothing here duplicates it.

**``PUBLISH`` is a new action** because drafting a notice and broadcasting it to
the company are different acts with different consequences. HR Executive gets
``announcements:create`` and not ``announcements:publish``: they write, HR Admin
sends. HR Admin gets every announcement action except ``delete`` -- a notice that
went out is a thing that was said, and removing it from the record is an
administrator's call, while archiving it (an ``update``) takes it off the screen.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.permissions import MODULES_BY_KEY, SYSTEM_ROLES, PermissionAction, action_label, code

revision: str = "0020_helpdesk_announcements"
down_revision: str | None = "0019_asset_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TICKET_CODE_SEQUENCE = "helpdesk_tickets_code_seq"

#: Dropped in reverse dependency order.
_TABLES = (
    "announcement_acknowledgements",
    "announcements",
    "helpdesk_history",
    "helpdesk_comments",
    "helpdesk_tickets",
    "helpdesk_categories",
)

_MODULES = ("helpdesk", "announcements")

_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "helpdesk:view": "See requests. Narrowed to your own and your team's unless the caller also "
    "holds employees:view_all.",
    "helpdesk:create": "Raise a request on another employee's behalf. Employees raise their own "
    "through self-service and need no permission for it.",
    "helpdesk:update": "Respond to a request: comment, change status, resolve.",
    "helpdesk:assign": "Assign a request to somebody, or take it yourself.",
    "helpdesk:manage": "Administer the desk: categories, queues and their routing.",
    "helpdesk:export": "Export the request register.",
    "announcements:view": "See published announcements, and drafts if you may create them.",
    "announcements:create": "Write an announcement. Writing is not sending.",
    "announcements:update": "Amend an announcement, or archive one that has run its course.",
    "announcements:publish": "Send an announcement to its audience. Distinct from writing it.",
    "announcements:delete": "Remove an announcement from the record entirely. Archiving is the "
    "ordinary way to take one off the screen.",
}

#: name, code, queue, SLA hours. The starting configuration -- editable on the
#: categories screen, not a list the code depends on.
_CATEGORIES: tuple[tuple[str, str, str, int | None], ...] = (
    ("Payroll query", "PAYROLL", "hr", 24),
    ("Leave query", "LEAVE", "hr", 24),
    ("Employment letter", "LETTER", "hr", 48),
    ("Personal details update", "DETAILS", "hr", 48),
    ("IT support", "IT_SUPPORT", "it", 8),
    ("System access", "ACCESS", "it", 8),
    ("Facilities", "FACILITIES", "facilities", 48),
    ("Something else", "OTHER", "hr", None),
)


def upgrade() -> None:
    _create_sequence()
    _create_helpdesk()
    _create_announcements()
    _seed_categories()
    _add_permissions()
    _grant_permissions()


def _create_sequence() -> None:
    op.execute(f"CREATE SEQUENCE {TICKET_CODE_SEQUENCE} AS bigint START WITH 1")


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


def _create_helpdesk() -> None:
    op.create_table(
        "helpdesk_categories",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("queue", sa.String(length=20), nullable=False),
        sa.Column("sla_hours", sa.Integer(), nullable=True),
        sa.Column("default_assignee_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_helpdesk_categories"),
        sa.UniqueConstraint("code", name="uq_helpdesk_categories_code"),
        sa.ForeignKeyConstraint(
            ["default_assignee_id"], ["users.id"],
            name="fk_helpdesk_categories_default_assignee_id_users", ondelete="SET NULL",
        ),
        *_actor_constraints("helpdesk_categories"),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_helpdesk_categories_status"),
        sa.CheckConstraint(
            "queue IN ('hr','it','admin','finance','facilities')", name="ck_helpdesk_categories_queue"
        ),
        sa.CheckConstraint(
            "sla_hours IS NULL OR sla_hours > 0", name="ck_helpdesk_categories_sla_hours_positive"
        ),
        comment="Configurable request categories and the desk each routes to.",
    )
    op.create_index("ix_helpdesk_categories_name", "helpdesk_categories", ["name"])
    op.create_index("ix_helpdesk_categories_queue", "helpdesk_categories", ["queue"])
    op.create_index("ix_helpdesk_categories_status", "helpdesk_categories", ["status"])
    op.create_index("ix_helpdesk_categories_deleted_at", "helpdesk_categories", ["deleted_at"])

    op.create_table(
        "helpdesk_tickets",
        sa.Column(
            "ticket_code",
            sa.String(length=20),
            server_default=sa.text(f"'TKT-' || lpad(nextval('{TICKET_CODE_SEQUENCE}')::text, 6, '0')"),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("queue", sa.String(length=20), nullable=False),
        sa.Column("raised_by_id", sa.UUID(), nullable=False),
        sa.Column("raised_for_id", sa.UUID(), nullable=True),
        sa.Column("assigned_to_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="open", nullable=False),
        sa.Column("priority", sa.String(length=20), server_default="medium", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("reopen_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "attachment_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_helpdesk_tickets"),
        sa.UniqueConstraint("ticket_code", name="uq_helpdesk_tickets_ticket_code"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["helpdesk_categories.id"],
            name="fk_helpdesk_tickets_category_id_helpdesk_categories",
        ),
        sa.ForeignKeyConstraint(
            ["raised_by_id"], ["employees.id"], name="fk_helpdesk_tickets_raised_by_id_employees"
        ),
        sa.ForeignKeyConstraint(
            ["raised_for_id"], ["employees.id"], name="fk_helpdesk_tickets_raised_for_id_employees"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to_id"], ["users.id"], name="fk_helpdesk_tickets_assigned_to_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("helpdesk_tickets"),
        sa.CheckConstraint(
            "status IN ('open','in_progress','waiting_on_employee','resolved','closed','cancelled',"
            "'reopened')",
            name="ck_helpdesk_tickets_status",
        ),
        sa.CheckConstraint(
            "priority IN ('low','medium','high','urgent')", name="ck_helpdesk_tickets_priority"
        ),
        sa.CheckConstraint(
            "queue IN ('hr','it','admin','finance','facilities')", name="ck_helpdesk_tickets_queue"
        ),
        comment="Employee requests to a service desk.",
    )
    for column in ("subject", "category_id", "raised_by_id", "raised_for_id", "assigned_to_id",
                   "status", "due_at", "deleted_at"):
        op.create_index(f"ix_helpdesk_tickets_{column}", "helpdesk_tickets", [column])
    op.create_index(
        "ix_helpdesk_tickets_status_priority", "helpdesk_tickets", ["status", "priority"]
    )
    op.create_index("ix_helpdesk_tickets_queue_status", "helpdesk_tickets", ["queue", "status"])
    op.create_index(
        "ix_helpdesk_tickets_assignee_status", "helpdesk_tickets", ["assigned_to_id", "status"]
    )

    op.create_table(
        "helpdesk_comments",
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("internal", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "attachment_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_helpdesk_comments"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["helpdesk_tickets.id"],
            name="fk_helpdesk_comments_ticket_id_helpdesk_tickets", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name="fk_helpdesk_comments_author_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("helpdesk_comments"),
        comment="The conversation on a ticket.",
    )
    for column in ("ticket_id", "author_id", "internal", "deleted_at"):
        op.create_index(f"ix_helpdesk_comments_{column}", "helpdesk_comments", [column])
    op.create_index(
        "ix_helpdesk_comments_ticket_created", "helpdesk_comments", ["ticket_id", "created_at"]
    )

    op.create_table(
        "helpdesk_history",
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("event", sa.String(length=30), nullable=False),
        sa.Column("previous_value", sa.String(length=200), nullable=True),
        sa.Column("new_value", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_helpdesk_history"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["helpdesk_tickets.id"],
            name="fk_helpdesk_history_ticket_id_helpdesk_tickets", ondelete="CASCADE",
        ),
        *_actor_constraints("helpdesk_history"),
        sa.CheckConstraint(
            "event IN ('raised','assigned','status_changed','commented','priority_changed',"
            "'category_changed','resolved','reopened','closed')",
            name="ck_helpdesk_history_event",
        ),
        comment="Append-only event log for one ticket.",
    )
    for column in ("ticket_id", "event", "deleted_at"):
        op.create_index(f"ix_helpdesk_history_{column}", "helpdesk_history", [column])
    op.create_index(
        "ix_helpdesk_history_ticket_created", "helpdesk_history", ["ticket_id", "created_at"]
    )


def _create_announcements() -> None:
    op.create_table(
        "announcements",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=True),
        sa.Column("audience", sa.String(length=20), server_default="all", nullable=False),
        sa.Column(
            "target_ids", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("priority", sa.String(length=20), server_default="normal", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("pinned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("requires_acknowledgement", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "attachment_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_announcements"),
        sa.ForeignKeyConstraint(
            ["published_by_id"], ["users.id"], name="fk_announcements_published_by_id_users",
            ondelete="SET NULL",
        ),
        *_actor_constraints("announcements"),
        sa.CheckConstraint(
            "status IN ('draft','scheduled','published','archived')", name="ck_announcements_status"
        ),
        sa.CheckConstraint(
            "audience IN ('all','business_unit','team','location')", name="ck_announcements_audience"
        ),
        sa.CheckConstraint(
            "priority IN ('normal','important','urgent')", name="ck_announcements_priority"
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR published_at IS NULL OR expires_at > published_at",
            name="ck_announcements_expiry_after_publication",
        ),
        comment="Company notices and their audience.",
    )
    for column in ("title", "status", "published_at", "expires_at", "deleted_at"):
        op.create_index(f"ix_announcements_{column}", "announcements", [column])
    op.create_index("ix_announcements_status_published", "announcements", ["status", "published_at"])
    op.create_index("ix_announcements_audience", "announcements", ["audience"])

    op.create_table(
        "announcement_acknowledgements",
        sa.Column("announcement_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_announcement_acknowledgements"),
        sa.UniqueConstraint(
            "announcement_id", "employee_id", name="uq_announcement_acknowledgements_once"
        ),
        sa.ForeignKeyConstraint(
            ["announcement_id"], ["announcements.id"],
            name="fk_announcement_acknowledgements_announcement_id_announcements",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"],
            name="fk_announcement_acknowledgements_employee_id_employees", ondelete="CASCADE",
        ),
        *_actor_constraints("announcement_acknowledgements"),
        comment="Read receipts against an announcement.",
    )
    op.create_index(
        "ix_announcement_acknowledgements_announcement_id",
        "announcement_acknowledgements",
        ["announcement_id"],
    )
    op.create_index(
        "ix_announcement_acknowledgements_employee_id", "announcement_acknowledgements", ["employee_id"]
    )
    op.create_index(
        "ix_announcement_acknowledgements_deleted_at", "announcement_acknowledgements", ["deleted_at"]
    )
    op.create_index("ix_announcement_acks_employee", "announcement_acknowledgements", ["employee_id"])


def _seed_categories() -> None:
    for name, category_code, queue, sla in _CATEGORIES:
        op.execute(
            sa.text(
                "INSERT INTO helpdesk_categories(name, code, queue, sla_hours, status)"
                " VALUES (:name, :code, :queue, :sla, 'active')"
                " ON CONFLICT (code) DO NOTHING"
            ).bindparams(name=name, code=category_code, queue=queue, sla=sla)
        )


def _add_permissions() -> None:
    """``ON CONFLICT`` because ``reconcile_catalogue`` is reachable at runtime."""
    for module_key in _MODULES:
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
    """Grant each seeded role exactly what the catalogue says it holds.

    Derived from ``SYSTEM_ROLES`` so this migration and the catalogue cannot
    disagree about the two grants the access model turns on: HR Executive
    receiving ``announcements:create`` without ``announcements:publish``, and
    Manager receiving ``helpdesk:view`` without ``helpdesk:update``.

    Custom roles are untouched, for the reason 0016 gives.
    """
    new_codes = {
        code(module, action) for module in _MODULES for action in MODULES_BY_KEY[module].actions
    }
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
    codes = sorted(
        code(module, action) for module in _MODULES for action in MODULES_BY_KEY[module].actions
    )
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN"
            " (SELECT id FROM permissions WHERE code = ANY(:codes))"
        ).bindparams(codes=codes)
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:codes)").bindparams(codes=codes))

    for table in _TABLES:
        op.drop_table(table)

    op.execute(f"DROP SEQUENCE IF EXISTS {TICKET_CODE_SEQUENCE}")
