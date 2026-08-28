"""Remove the eight permission codes no endpoint ever checked.

Revision ID: 0022_prune_dead_permissions
Revises: 0021_jsan_employee_codes
Create Date: 2026-08-21 09:00:00

A permission that no route requires is not a smaller grant -- it is a lie on
the roles screen. ``resignation:create`` suggested HR could raise a
resignation on somebody's behalf (the platform deliberately has no such
endpoint: employees submit their own, identity-guarded). ``exit_documents:view``
was granted to HR Executive and bought them nothing, because reading issued
letters rides on ``offboarding:view``. The full list:

    resignation:create   resignation:update   resignation:export
    offboarding:create   offboarding:export
    exit_interview:manage
    exit_documents:view
    helpdesk:export

``reports:export`` and the four settings/audit codes are deliberately NOT in
this list: this release gave them real endpoints instead.

Hard delete rather than soft: these codes never guarded anything, so there is
no history a soft delete would preserve -- only the illusion of one. The
deletes cascade through ``role_permissions`` explicitly so custom roles are
cleaned too; unlike a live grant, removing a grant that never did anything
changes nobody's actual access.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_prune_dead_permissions"
down_revision: str | None = "0021_jsan_employee_codes"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

DEAD_CODES = [
    "resignation:create",
    "resignation:update",
    "resignation:export",
    "offboarding:create",
    "offboarding:export",
    "exit_interview:manage",
    "exit_documents:view",
    "helpdesk:export",
]

#: What downgrade must restore: (code, module, action, group, label).
_ROWS = [
    ("resignation:create", "resignation", "create", "hr", "Create resignations"),
    ("resignation:update", "resignation", "update", "hr", "Update resignations"),
    ("resignation:export", "resignation", "export", "hr", "Export resignations"),
    ("offboarding:create", "offboarding", "create", "hr", "Create offboarding"),
    ("offboarding:export", "offboarding", "export", "hr", "Export offboarding"),
    ("exit_interview:manage", "exit_interview", "manage", "hr", "Manage exit interviews"),
    ("exit_documents:view", "exit_documents", "view", "hr", "View exit documents"),
    ("helpdesk:export", "helpdesk", "export", "hr", "Export helpdesk"),
]

#: The system-role grants these codes had before removal.
_OLD_GRANTS = {
    "super_admin": DEAD_CODES,
    "admin": DEAD_CODES,
    "hr_admin": DEAD_CODES,
    "hr_executive": ["exit_documents:view"],
}


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM role_permissions rp USING permissions p"
            " WHERE rp.permission_id = p.id AND p.code = ANY(:codes)"
        ).bindparams(codes=DEAD_CODES)
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:codes)").bindparams(codes=DEAD_CODES))


def downgrade() -> None:
    for permission_code, module, action, group, label in _ROWS:
        op.execute(
            sa.text(
                "INSERT INTO permissions(code, module, action, permission_group, label, description)"
                " VALUES (:code, :module, :action, :grp, :label, :label)"
                " ON CONFLICT (code) DO NOTHING"
            ).bindparams(code=permission_code, module=module, action=action, grp=group, label=label)
        )
    for role_key, codes in _OLD_GRANTS.items():
        op.execute(
            sa.text(
                "INSERT INTO role_permissions(role_id, permission_id)"
                " SELECT r.id, p.id FROM roles r, permissions p"
                " WHERE r.key = :key AND p.code = ANY(:codes) AND p.deleted_at IS NULL"
                " ON CONFLICT (role_id, permission_id) DO NOTHING"
            ).bindparams(key=role_key, codes=codes)
        )
