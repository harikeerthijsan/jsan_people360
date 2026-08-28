"""HR administration: the Administrator role, five administrative permissions and leave policy.

Revision ID: 0017_hr_administration
Revises: 0016_manager_team_scoping

Three things, and they belong together because each is half of the same
sentence: *HR is not an administrator.*

**Five new permissions.** ``attendance:manage_all``, ``timesheets:manage_all``,
``leave:override_approval``, ``leave:balance_adjust`` and
``leave:policy_manage``. Every one of them names an action that had no
permission before because the action itself did not exist -- amending somebody's
attendance with no request behind it, deciding a request addressed to their
manager, rewriting a balance by hand, configuring the leave policies. They are
deliberately *not* consequences of ``approve``: a manager approving their own
report's correction and an administrator overwriting a stranger's day are
different powers, and collapsing them is how HR quietly becomes an
administrator.

**An Administrator role**, holding the whole catalogue. It is distinct from
Super Admin in kind: Super Admin carries ``users.is_superuser``, which bypasses
the permission check itself, so an Administrator can be narrowed by editing
their role and a Super Admin cannot. Nothing is granted to any *user* here --
the role exists to be assigned.

**Leave policy columns** on ``leave_types``. §6 of the brief asks for credit
frequency, credit amount, proration and an effective window, and none of them
existed: the table stored an annual figure and nothing about how it is reached.
These extend the table the leave engine already reads rather than adding a
second one, and ``effective_from`` / ``effective_to`` are honoured by
``WorkforceService`` so they are configuration with an effect rather than
configuration with a screen.

Of the five permissions, ``hr_admin`` is granted exactly one:
``leave:policy_manage``. Deciding how much casual leave the company gives is
HR's job by definition; the other four are administrative, and an organization
that wants HR to hold one ticks it on the roles screen. That asymmetry is the
whole point of this migration and is asserted by ``tests/integration/test_hr.py``.

Custom roles are not touched, for the reason 0016 gives: guessing which of them
deserve an administrative power is not something a migration should do silently.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.permissions import (
    MODULES_BY_KEY,
    SYSTEM_ROLES_BY_KEY,
    PermissionAction,
    action_label,
    code,
)

revision: str = "0017_hr_administration"
down_revision: str | None = "0016_manager_team_scoping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: The new permissions, as ``(module, action, description)``. The description is
#: what an administrator reads on the roles screen before ticking the box, so it
#: says what the power *is* rather than restating the code.
NEW_PERMISSIONS: tuple[tuple[str, PermissionAction, str], ...] = (
    (
        "attendance",
        PermissionAction.MANAGE_ALL,
        "Amend any employee's attendance record directly, without a correction "
        "request behind it. Administrative; distinct from approving a request.",
    ),
    (
        "timesheets",
        PermissionAction.MANAGE_ALL,
        "Decide any employee's timesheet, including one addressed to another "
        "manager. Administrative; distinct from approving your own team's.",
    ),
    (
        "leave",
        PermissionAction.OVERRIDE_APPROVAL,
        "Decide a leave request that was addressed to somebody else's manager. "
        "Every override is audited as one.",
    ),
    (
        "leave",
        PermissionAction.POLICY_MANAGE,
        "Configure leave types and the policies behind them: credit frequency, "
        "annual maximum, carry forward, proration and the effective window.",
    ),
    (
        "leave",
        PermissionAction.BALANCE_ADJUST,
        "Correct an employee's leave balance by hand. Every adjustment is "
        "audited with the reason given.",
    ),
)

ADMIN_ROLE_KEY = "admin"

#: The one new permission HR keeps by default.
HR_GRANTS: tuple[tuple[str, str], ...] = (("hr_admin", code("leave", PermissionAction.POLICY_MANAGE)),)

#: Added to ``leave_types``. ``annual_allocation`` already holds the annual
#: maximum and is left alone: the engine reads it, and a second column meaning
#: the same thing is a second answer waiting to disagree with the first.
POLICY_COLUMNS: tuple[tuple[str, sa.types.TypeEngine, str | None, str], ...] = (
    (
        "credit_frequency",
        sa.String(length=20),
        "'annually'",
        "How often the entitlement is credited: monthly, quarterly, annually or none.",
    ),
    (
        "credit_amount",
        sa.Numeric(precision=5, scale=1),
        "0",
        "Days credited each period. Zero means the annual figure is credited whole.",
    ),
    (
        "prorate_on_joining",
        sa.Boolean(),
        "false",
        "Whether a mid-year joiner receives a proportion rather than the full year.",
    ),
    ("effective_from", sa.Date(), None, "First day this policy applies. Null means always."),
    ("effective_to", sa.Date(), None, "Last day this policy applies. Null means indefinitely."),
)

CREDIT_FREQUENCIES = ("monthly", "quarterly", "annually", "none")


def upgrade() -> None:
    _add_permissions()
    _add_admin_role()
    _grant_to_hr()
    _add_policy_columns()


def _add_permissions() -> None:
    """``ON CONFLICT`` because ``reconcile_catalogue`` is reachable at runtime.

    An environment where the code deployed before the migration ran may already
    hold these rows. It never grants them to anybody, so the grants below are
    still this migration's job.
    """
    for module_key, action, description in NEW_PERMISSIONS:
        module = MODULES_BY_KEY[module_key]
        op.execute(
            sa.text(
                "INSERT INTO permissions(code, module, action, permission_group, label, description)"
                " VALUES (:code, :module, :action, :grp, :label, :description)"
                " ON CONFLICT (code) DO NOTHING"
            ).bindparams(
                code=code(module_key, action),
                module=module_key,
                action=action.value,
                grp=module.group.value,
                label=action_label(action, module.label),
                description=description,
            )
        )


def _add_admin_role() -> None:
    """Create Administrator and grant it the whole catalogue.

    Granted by joining on ``permissions`` rather than from a literal list, so
    the role stays complete when a later migration adds a permission -- which is
    the definition of "full application access" and the one place a hard-coded
    list would silently stop being true.
    """
    role = SYSTEM_ROLES_BY_KEY[ADMIN_ROLE_KEY]
    op.execute(
        sa.text(
            "INSERT INTO roles(key, name, description, is_system)"
            " VALUES (:key, :name, :description, true)"
            " ON CONFLICT (key) DO NOTHING"
        ).bindparams(key=role.key, name=role.name, description=role.description)
    )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions(role_id, permission_id)"
            " SELECT r.id, p.id FROM roles r, permissions p"
            " WHERE r.key = :key AND p.deleted_at IS NULL"
            " ON CONFLICT (role_id, permission_id) DO NOTHING"
        ).bindparams(key=role.key)
    )


def _grant_to_hr() -> None:
    for role_key, permission in HR_GRANTS:
        op.execute(
            sa.text(
                "INSERT INTO role_permissions(role_id, permission_id)"
                " SELECT r.id, p.id FROM roles r, permissions p"
                " WHERE r.key = :key AND p.code = :code"
                " ON CONFLICT (role_id, permission_id) DO NOTHING"
            ).bindparams(key=role_key, code=permission)
        )


def _add_policy_columns() -> None:
    for name, column_type, default, comment in POLICY_COLUMNS:
        # A column with a server default is filled for every existing row and can
        # be NOT NULL; the two effective dates have none, because "no window" is
        # the honest answer for every policy that predates this migration and
        # NULL is how the model spells it.
        op.add_column(
            "leave_types",
            sa.Column(
                name,
                column_type,
                nullable=default is None,
                server_default=sa.text(default) if default is not None else None,
                comment=comment,
            ),
        )

    op.create_check_constraint(
        "ck_leave_types_credit_frequency",
        "leave_types",
        sa.text("credit_frequency IN " + str(CREDIT_FREQUENCIES)),
    )
    op.create_check_constraint("ck_leave_types_credit_amount", "leave_types", "credit_amount >= 0")
    # A window that ends before it starts would silently disable the policy, and
    # the screen that produced it would look as though it had saved.
    op.create_check_constraint(
        "ck_leave_types_effective_window",
        "leave_types",
        "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
    )
    # The engine asks "which policies are in force today" on every balance read
    # and on every leave-type list, so the window is an indexed lookup rather
    # than a scan that grows with the number of retired policies.
    op.create_index("ix_leave_types_effective", "leave_types", ["effective_from", "effective_to"])


def downgrade() -> None:
    op.drop_index("ix_leave_types_effective", table_name="leave_types")
    for name in (
        "ck_leave_types_effective_window",
        "ck_leave_types_credit_amount",
        "ck_leave_types_credit_frequency",
    ):
        op.drop_constraint(name, "leave_types", type_="check")
    for name, _type, _default, _comment in reversed(POLICY_COLUMNS):
        op.drop_column("leave_types", name)

    # The grants go first; the foreign key cascades, but being explicit keeps
    # the order safe if that ever changes.
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE key = :key)"
        ).bindparams(key=ADMIN_ROLE_KEY)
    )
    op.execute(sa.text("DELETE FROM roles WHERE key = :key").bindparams(key=ADMIN_ROLE_KEY))

    codes = [code(module_key, action) for module_key, action, _ in NEW_PERMISSIONS]
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN"
            " (SELECT id FROM permissions WHERE code = ANY(:codes))"
        ).bindparams(codes=codes)
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:codes)").bindparams(codes=codes))
