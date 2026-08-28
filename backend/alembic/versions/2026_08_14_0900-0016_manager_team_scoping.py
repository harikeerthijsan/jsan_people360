"""Manager team scoping: the ``employees:view_all`` permission and its grants.

Revision ID: 0016_manager_team_scoping
Revises: 0015_rbac

No schema change -- the reporting line this scopes on is ``employees.
reporting_manager_id``, which has existed since 0004. What is new is one row in
the permission catalogue and the grants that decide who keeps organization-wide
access once the API starts narrowing by reporting line.

The direction of this migration matters. Without it, every role loses org-wide
access the moment the code deploys, because the permission that preserves it
would not exist yet -- HR would open the directory and find their own name in it.
So the grants are written here rather than left to ``reconcile_catalogue``, which
adds permissions but deliberately never hands them to anybody.

Custom roles are not touched. A company that built its own "Regional HR" role
gets it back by ticking one box on the roles screen; guessing which custom roles
deserve organization-wide reach is not something a migration should do silently.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.permissions import (
    MODULES_BY_KEY,
    PermissionAction,
    action_label,
    code,
)

revision: str = "0016_manager_team_scoping"
down_revision: str | None = "0015_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = code("employees", PermissionAction.VIEW_ALL)

#: The seats that keep organization-wide reach. Manager and Team Lead are
#: absent on purpose: narrowing them to their direct reports is the point of
#: this migration. Recruiter and Project Manager are present because their work
#: crosses the org chart -- interview panels and project teams are not reporting
#: lines -- and scoping them would empty the pickers they depend on.
ORG_WIDE_ROLE_KEYS: tuple[str, ...] = (
    "super_admin",
    "hr_admin",
    "hr_executive",
    "recruiter",
    "project_manager",
)


def upgrade() -> None:
    module = MODULES_BY_KEY["employees"]

    # ON CONFLICT rather than a bare INSERT: `reconcile_catalogue` is exposed at
    # runtime and may already have added the row on an environment where the
    # code was deployed before the migration ran.
    op.execute(
        sa.text(
            "INSERT INTO permissions(code, module, action, permission_group, label, description)"
            " VALUES (:code, :module, :action, :grp, :label, :description)"
            " ON CONFLICT (code) DO NOTHING"
        ).bindparams(
            code=PERMISSION,
            module=module.key,
            action=PermissionAction.VIEW_ALL.value,
            grp=module.group.value,
            label=action_label(PermissionAction.VIEW_ALL, module.label),
            description=(
                "See and act on every employee's records rather than only your "
                "own and your direct reports'."
            ),
        )
    )

    op.execute(
        sa.text(
            "INSERT INTO role_permissions(role_id, permission_id)"
            " SELECT r.id, p.id FROM roles r, permissions p"
            " WHERE r.key = ANY(:keys) AND p.code = :code"
            " ON CONFLICT (role_id, permission_id) DO NOTHING"
        ).bindparams(keys=list(ORG_WIDE_ROLE_KEYS), code=PERMISSION)
    )


def downgrade() -> None:
    # The grants go first: the foreign key is ON DELETE CASCADE, but being
    # explicit keeps the intent readable and the order safe if that changes.
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN"
            " (SELECT id FROM permissions WHERE code = :code)"
        ).bindparams(code=PERMISSION)
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = :code").bindparams(code=PERMISSION))
