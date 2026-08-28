"""Remove the practice and department levels of the organizational hierarchy.

Revision ID: 0012_remove_practice_department
Revises: 0011_project_allocations
Create Date: 2026-08-10 09:00:00

The hierarchy becomes ``Business Unit -> Team`` and ``Business Unit ->
Designation``. Practices and departments are removed entirely.

Two levels disappear, so the two masters that hung off a department have to be
re-parented rather than dropped: a designation is on every employee, requisition
and offer, and a team is on every employee. Both are moved up to the business
unit their department ultimately belonged to, which is why the backfill walks
``department -> practice -> business_unit`` *before* anything is dropped.

It also renames the requisition approver ``department_head_id`` to
``second_approver_id``. That column always referenced a *user* rather than the
departments table, so nothing structural depended on it -- only the name stopped
making sense once departments were gone.

**This migration destroys data.** The practice and department tables go, along
with every column that referenced them, including the ``department_id`` recorded
on historical placement rows. The downgrade restores the structure but cannot
restore the values -- there is nowhere left to read them from. Take a dump first.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_remove_practice_department"
down_revision = "0011_project_allocations"
branch_labels = None
depends_on = None


#: Indexed, foreign-keyed references that the downgrade has to rebuild
#: explicitly. ``projects`` and ``job_requisitions`` are absent because their
#: columns were created by raw SQL with no index of their own.
_RESTORED_REFERENCES: tuple[tuple[str, str, str], ...] = (
    ("employees", "practice_id", "practices"),
    ("employees", "department_id", "departments"),
    ("users", "practice_id", "practices"),
    ("users", "department_id", "departments"),
)

#: Tables that merely referenced the two levels and lose their columns outright.
_DROPPED_REFERENCES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("employees", ("practice_id", "department_id")),
    ("users", ("practice_id", "department_id")),
    ("projects", ("practice_id", "department_id")),
    ("job_requisitions", ("practice_id", "department_id")),
)


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Re-parent designations and teams, before their route to a business
    #    unit is destroyed.
    # ------------------------------------------------------------------
    for table in ("designations", "teams"):
        op.add_column(table, sa.Column("business_unit_id", sa.UUID(), nullable=True))
        bind.execute(
            sa.text(
                f"""
                UPDATE {table} AS t
                   SET business_unit_id = p.business_unit_id
                  FROM departments AS d
                  JOIN practices AS p ON p.id = d.practice_id
                 WHERE d.id = t.department_id
                """
            )
        )

    # Anything whose department was already gone has nowhere to go. Rather than
    # fail the migration, park it under the lowest-coded business unit so no
    # record is lost; an administrator can re-file it afterwards.
    fallback = bind.execute(
        sa.text("SELECT id FROM business_units ORDER BY lower(code) LIMIT 1")
    ).scalar()
    if fallback is not None:
        for table in ("designations", "teams"):
            bind.execute(
                sa.text(f"UPDATE {table} SET business_unit_id = :fallback WHERE business_unit_id IS NULL"),
                {"fallback": fallback},
            )

    for table, fk_name in (
        ("designations", "fk_designations_business_unit_id_business_units"),
        ("teams", "fk_teams_business_unit_id_business_units"),
    ):
        op.alter_column(table, "business_unit_id", nullable=False)
        op.create_foreign_key(
            fk_name, table, "business_units", ["business_unit_id"], ["id"], ondelete="RESTRICT"
        )
        op.create_index(f"ix_{table}_business_unit_id", table, ["business_unit_id"], unique=False)

        # The name is unique within the parent, and the parent has changed.
        op.drop_index(f"uq_{table}_department_id_name_lower", table_name=table)
        op.create_index(
            f"uq_{table}_business_unit_id_name_lower",
            table,
            [sa.literal_column("business_unit_id"), sa.literal_column("lower(name)")],
            unique=True,
        )

        op.drop_index(f"ix_{table}_department_id", table_name=table)
        op.drop_constraint(f"fk_{table}_department_id_departments", table, type_="foreignkey")
        op.drop_column(table, "department_id")

    # ------------------------------------------------------------------
    # 2. Placement history tracked the department; it now tracks the team.
    # ------------------------------------------------------------------
    op.add_column("employee_employment_history", sa.Column("team_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_employee_employment_history_team_id_teams",
        "employee_employment_history",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_employee_employment_history_team_id",
        "employee_employment_history",
        ["team_id"],
        unique=False,
    )
    op.drop_index("ix_employee_employment_history_department_id", table_name="employee_employment_history")
    op.drop_constraint(
        "fk_employee_employment_history_department_id_departments",
        "employee_employment_history",
        type_="foreignkey",
    )
    op.drop_column("employee_employment_history", "department_id")

    # A "department transfer" no longer describes anything. Existing rows are
    # relabelled rather than deleted -- history is appended to, never rewritten,
    # and the event did happen; only the word for it has changed.
    op.drop_constraint(
        op.f("ck_employee_employment_history_change_type"), "employee_employment_history"
    )
    bind.execute(
        sa.text(
            "UPDATE employee_employment_history "
            "SET change_type = 'team_transfer' WHERE change_type = 'department_transfer'"
        )
    )
    # ``op.f`` marks the name as final. Without it the metadata naming
    # convention prefixes it a second time and PostgreSQL truncates the
    # result to a hash, so the matching drop above can never find it.
    op.create_check_constraint(
        op.f("ck_employee_employment_history_change_type"),
        "employee_employment_history",
        "change_type IN ('created', 'confirmation', 'promotion', 'team_transfer', "
        "'designation_change', 'grade_change', 'manager_change', 'location_change', "
        "'status_change', 'details_updated')",
    )

    # ------------------------------------------------------------------
    # 3. Composite indexes that named a dropped column.
    # ------------------------------------------------------------------
    op.drop_index("ix_employees_placement", table_name="employees")
    op.drop_index("ix_requisitions_department_created", table_name="job_requisitions")

    # ------------------------------------------------------------------
    # 4. Every remaining reference.
    # ------------------------------------------------------------------
    for table, columns in _DROPPED_REFERENCES:
        for column in columns:
            op.drop_column(table, column)

    op.create_index(
        "ix_employees_placement", "employees", ["business_unit_id", "team_id", "designation_id"]
    )
    op.create_index(
        "ix_requisitions_business_unit_created", "job_requisitions", ["business_unit_id", "created_at"]
    )

    # ------------------------------------------------------------------
    # 5. The requisition approver named after a level that no longer exists.
    #
    #    The column is a reference to a *user*, not to the departments table, so
    #    nothing structural depended on it -- only the name stopped making sense.
    # ------------------------------------------------------------------
    op.alter_column("job_requisitions", "department_head_id", new_column_name="second_approver_id")
    bind.execute(
        sa.text(
            "UPDATE requisition_approvals SET role_name = 'Second approver' "
            "WHERE role_name = 'Department Head'"
        )
    )

    # ------------------------------------------------------------------
    # 6. The tables themselves. Departments first: it points at practices.
    # ------------------------------------------------------------------
    op.drop_table("departments")
    op.drop_table("practices")


def downgrade() -> None:
    """Restore the structure. The values are not recoverable.

    Re-parenting is one-way: a designation records the business unit it now
    belongs to, not the department it used to. Restoring the columns gives back
    the shape of the schema so the chain can be walked, and nothing more.
    """
    op.create_table(
        "practices",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("business_unit_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("deleted_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["business_unit_id"],
            ["business_units.id"],
            name="fk_practices_business_unit_id_business_units",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_practices"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_practices_status"),
    )
    # Every index 0002 built, because its downgrade drops all of them by name.
    for column in ("business_unit_id", "code", "deleted_at", "name", "status"):
        op.create_index(op.f(f"ix_practices_{column}"), "practices", [column], unique=False)
    op.create_index("uq_practices_code_lower", "practices", [sa.literal_column("lower(code)")], unique=True)
    op.create_index(
        "uq_practices_business_unit_id_name_lower",
        "practices",
        [sa.literal_column("business_unit_id"), sa.literal_column("lower(name)")],
        unique=True,
    )

    op.create_table(
        "departments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("practice_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("deleted_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["practice_id"],
            ["practices.id"],
            name="fk_departments_practice_id_practices",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_departments"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_departments_status"),
    )
    for column in ("code", "deleted_at", "name", "practice_id", "status"):
        op.create_index(op.f(f"ix_departments_{column}"), "departments", [column], unique=False)
    op.create_index(
        "uq_departments_code_lower", "departments", [sa.literal_column("lower(code)")], unique=True
    )
    op.create_index(
        "uq_departments_practice_id_name_lower",
        "departments",
        [sa.literal_column("practice_id"), sa.literal_column("lower(name)")],
        unique=True,
    )

    op.get_bind().execute(
        sa.text(
            "UPDATE requisition_approvals SET role_name = 'Department Head' "
            "WHERE role_name = 'Second approver'"
        )
    )
    op.alter_column("job_requisitions", "second_approver_id", new_column_name="department_head_id")

    op.drop_index("ix_requisitions_business_unit_created", table_name="job_requisitions")
    op.drop_index("ix_employees_placement", table_name="employees")

    for table, columns in _DROPPED_REFERENCES:
        for column in columns:
            op.add_column(table, sa.Column(column, sa.UUID(), nullable=True))

    # Dropping a column silently takes its index and foreign key with it, so
    # both have to be put back by hand or the *earlier* migrations' downgrades
    # fail trying to drop things that are no longer there.
    for table, column, parent in _RESTORED_REFERENCES:
        op.create_index(op.f(f"ix_{table}_{column}"), table, [column], unique=False)
        op.create_foreign_key(
            op.f(f"fk_{table}_{column}_{parent}"),
            table,
            parent,
            [column],
            ["id"],
            ondelete="RESTRICT",
        )

    op.create_index(
        "ix_employees_placement", "employees", ["business_unit_id", "department_id", "designation_id"]
    )
    op.create_index(
        "ix_requisitions_department_created", "job_requisitions", ["department_id", "created_at"]
    )

    op.drop_constraint(
        op.f("ck_employee_employment_history_change_type"), "employee_employment_history"
    )
    op.get_bind().execute(
        sa.text(
            "UPDATE employee_employment_history "
            "SET change_type = 'department_transfer' WHERE change_type = 'team_transfer'"
        )
    )
    # ``op.f`` marks the name as final. Without it the metadata naming
    # convention prefixes it a second time and PostgreSQL truncates the
    # result to a hash, so the matching drop above can never find it.
    op.create_check_constraint(
        op.f("ck_employee_employment_history_change_type"),
        "employee_employment_history",
        "change_type IN ('created', 'confirmation', 'promotion', 'department_transfer', "
        "'designation_change', 'grade_change', 'manager_change', 'location_change', "
        "'status_change', 'details_updated')",
    )

    op.add_column("employee_employment_history", sa.Column("department_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_employee_employment_history_department_id", "employee_employment_history", ["department_id"]
    )
    op.create_foreign_key(
        "fk_employee_employment_history_department_id_departments",
        "employee_employment_history",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_index("ix_employee_employment_history_team_id", table_name="employee_employment_history")
    op.drop_constraint(
        "fk_employee_employment_history_team_id_teams", "employee_employment_history", type_="foreignkey"
    )
    op.drop_column("employee_employment_history", "team_id")

    for table in ("designations", "teams"):
        op.add_column(table, sa.Column("department_id", sa.UUID(), nullable=True))
        op.create_index(f"ix_{table}_department_id", table, ["department_id"])
        op.create_foreign_key(
            f"fk_{table}_department_id_departments",
            table,
            "departments",
            ["department_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.drop_index(f"uq_{table}_business_unit_id_name_lower", table_name=table)
        op.create_index(
            f"uq_{table}_department_id_name_lower",
            table,
            [sa.literal_column("department_id"), sa.literal_column("lower(name)")],
            unique=True,
        )
        op.drop_index(f"ix_{table}_business_unit_id", table_name=table)
        op.drop_constraint(f"fk_{table}_business_unit_id_business_units", table, type_="foreignkey")
        op.drop_column(table, "business_unit_id")
