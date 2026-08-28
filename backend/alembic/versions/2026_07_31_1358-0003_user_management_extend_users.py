"""Extend users for the User Management module

Turns the Phase 1 authentication row into a full directory record: a generated
staff code, a username, split names, personal contact details, and the eight
foreign keys that place a person in the organization.

This is an **expand / backfill / contract** migration, not a plain set of
``ADD COLUMN``s. ``users`` already holds rows -- at minimum the bootstrap
administrator -- so the new mandatory columns are added nullable, populated from
the data already present, and only then made ``NOT NULL``. Adding them as
``NOT NULL`` in one step, which is what autogenerate proposes, fails against any
populated database.

``full_name`` is *derived from* rather than dropped alongside the new columns:
it is split into ``first_name`` / ``last_name`` before it is removed, so no name
is lost. It comes back, recomposed, on downgrade.

``job_title`` is dropped outright and superseded by ``designation_id``. Free
text next to a foreign key is exactly the duplication this platform's master
data exists to remove.

Revision ID: 0003_user_management
Revises: 0002_org_masters
Created: 2026-07-31 13:58:31.379497+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_user_management"
down_revision: str | None = "0002_org_masters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

USER_CODE_SEQUENCE = "users_user_code_seq"
USER_CODE_DEFAULT = f"'USR-' || lpad(nextval('{USER_CODE_SEQUENCE}')::text, 6, '0')"

#: Organizational placement. All nullable and all RESTRICT -- see the model.
ORG_FOREIGN_KEYS: tuple[tuple[str, str], ...] = (
    ("business_unit_id", "business_units"),
    ("practice_id", "practices"),
    ("department_id", "departments"),
    ("team_id", "teams"),
    ("designation_id", "designations"),
    ("grade_id", "grades"),
    ("location_id", "locations"),
    ("employment_type_id", "employment_types"),
)


def upgrade() -> None:
    """Expand, backfill, then contract."""

    # ------------------------------------------------------------------
    # 1. Expand -- every new column nullable so existing rows stay valid
    # ------------------------------------------------------------------
    op.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {USER_CODE_SEQUENCE} AS bigint START WITH 1"))

    op.add_column("users", sa.Column("user_code", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("username", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("first_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("personal_email", sa.String(length=320), nullable=True))
    op.add_column("users", sa.Column("gender", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("joining_date", sa.Date(), nullable=True))
    op.add_column(
        "users",
        sa.Column("force_password_change", sa.Boolean(), server_default="false", nullable=False),
    )
    for column, _ in ORG_FOREIGN_KEYS:
        op.add_column("users", sa.Column(column, sa.UUID(), nullable=True))

    # ------------------------------------------------------------------
    # 2. Backfill from the data already present
    # ------------------------------------------------------------------
    # Split the display name on its first space. A single-token name has no
    # surname to recover, so the token is used for both parts: the result reads
    # oddly on purpose, which flags the record for an administrator to correct
    # rather than silently inventing a blank surname.
    op.execute(
        sa.text(
            """
            UPDATE users SET
                first_name = split_part(btrim(full_name), ' ', 1),
                last_name = CASE
                    WHEN position(' ' in btrim(full_name)) = 0
                        THEN split_part(btrim(full_name), ' ', 1)
                    ELSE btrim(substring(btrim(full_name) from position(' ' in btrim(full_name)) + 1))
                END
            """
        )
    )

    # Derive a username from the email local part, stripped to the permitted
    # character set and de-duplicated with a numeric suffix. Two people at
    # different domains can share a local part, and the unique index would
    # otherwise reject the migration itself.
    op.execute(
        sa.text(
            """
            WITH candidate AS (
                SELECT
                    id,
                    created_at,
                    NULLIF(
                        regexp_replace(lower(split_part(email, '@', 1)), '[^a-z0-9._-]', '', 'g'),
                        ''
                    ) AS handle
                FROM users
            ),
            numbered AS (
                SELECT
                    id,
                    COALESCE(handle, 'user') AS handle,
                    ROW_NUMBER() OVER (PARTITION BY handle ORDER BY created_at, id) AS occurrence
                FROM candidate
            )
            UPDATE users AS u
            SET username = CASE
                WHEN n.occurrence = 1 THEN n.handle
                ELSE n.handle || n.occurrence::text
            END
            FROM numbered AS n
            WHERE u.id = n.id
            """
        )
    )

    # Assign staff codes oldest-first, so the bootstrap administrator is
    # USR-000001 and the numbering reads as a join order.
    op.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS position FROM users
            )
            UPDATE users AS u
            SET user_code = 'USR-' || lpad(o.position::text, 6, '0')
            FROM ordered AS o
            WHERE u.id = o.id
            """
        )
    )

    # Advance the sequence past the codes just assigned. `is_called` is false
    # for an empty table because a sequence cannot be set below its minimum.
    op.execute(
        sa.text(
            f"""
            SELECT setval(
                '{USER_CODE_SEQUENCE}',
                GREATEST((SELECT count(*) FROM users), 1),
                (SELECT count(*) FROM users) > 0
            )
            """
        )
    )

    # ------------------------------------------------------------------
    # 3. Contract -- now that every row has a value, enforce it
    # ------------------------------------------------------------------
    op.alter_column("users", "user_code", nullable=False, server_default=sa.text(USER_CODE_DEFAULT))
    op.alter_column("users", "username", nullable=False)
    op.alter_column("users", "first_name", nullable=False)
    op.alter_column("users", "last_name", nullable=False)

    op.create_index(op.f("ix_users_user_code"), "users", ["user_code"], unique=True)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=False)
    op.create_index("uq_users_username_lower", "users", [sa.literal_column("lower(username)")], unique=True)
    op.create_index("ix_users_name", "users", ["first_name", "last_name"], unique=False)

    for column, _ in ORG_FOREIGN_KEYS:
        op.create_index(op.f(f"ix_users_{column}"), "users", [column], unique=False)
    for column, table in ORG_FOREIGN_KEYS:
        op.create_foreign_key(
            op.f(f"fk_users_{column}_{table}"), "users", table, [column], ["id"], ondelete="RESTRICT"
        )

    # Autogenerate does not compare CHECK constraints, so this is declared here
    # explicitly to match the model rather than being silently absent.
    op.create_check_constraint(
        "gender",
        "users",
        "gender IS NULL OR gender IN ('male', 'female', 'other', 'prefer_not_to_say')",
    )

    op.create_table_comment(
        "users",
        "Authenticated principals and directory records of the platform.",
        existing_comment="Authenticated principals of the platform.",
        schema=None,
    )

    op.drop_column("users", "full_name")
    op.drop_column("users", "job_title")


def downgrade() -> None:
    """Recompose the display name, then remove everything this revision added."""

    # Restore the dropped columns, nullable, and rebuild the display name from
    # its parts before re-imposing NOT NULL.
    op.add_column("users", sa.Column("full_name", sa.VARCHAR(length=255), nullable=True))
    op.add_column("users", sa.Column("job_title", sa.VARCHAR(length=150), nullable=True))
    op.execute(sa.text("UPDATE users SET full_name = btrim(first_name || ' ' || last_name)"))
    op.alter_column("users", "full_name", nullable=False)

    op.create_table_comment(
        "users",
        "Authenticated principals of the platform.",
        existing_comment="Authenticated principals and directory records of the platform.",
        schema=None,
    )

    op.drop_constraint(op.f("ck_users_gender"), "users", type_="check")
    for column, table in ORG_FOREIGN_KEYS:
        op.drop_constraint(op.f(f"fk_users_{column}_{table}"), "users", type_="foreignkey")
    for column, _ in ORG_FOREIGN_KEYS:
        op.drop_index(op.f(f"ix_users_{column}"), table_name="users")

    op.drop_index("ix_users_name", table_name="users")
    op.drop_index("uq_users_username_lower", table_name="users")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_user_code"), table_name="users")

    op.drop_column("users", "force_password_change")
    op.drop_column("users", "joining_date")
    for column, _ in reversed(ORG_FOREIGN_KEYS):
        op.drop_column("users", column)
    op.drop_column("users", "date_of_birth")
    op.drop_column("users", "gender")
    op.drop_column("users", "personal_email")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
    op.drop_column("users", "username")
    op.drop_column("users", "user_code")

    op.execute(sa.text(f"DROP SEQUENCE IF EXISTS {USER_CODE_SEQUENCE}"))
