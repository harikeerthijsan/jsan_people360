"""Employee codes become JSAN336-style: the organization's own prefix, unpadded.

Revision ID: 0021_jsan_employee_codes
Revises: 0020_helpdesk_announcements
Create Date: 2026-08-20 15:00:00

Two things, and they must move together:

1. The column default changes from ``'EMP-' || lpad(nextval(...), 6, '0')`` to
   ``'JSAN' || nextval(...)``.
2. Every existing ``EMP-``-prefixed code is rewritten to the new pattern,
   keeping its sequence number: EMP-000112 becomes JSAN112.

Rewriting existing rows is deliberate rather than incidental. Employee codes
appear on screens, in exports and in conversation; a register where the first
hundred people are EMP-000042 and the rest are JSAN142 would make the format a
clue to seniority and every lookup a two-pattern search. The number is
preserved, so anything anybody wrote down remains resolvable: the digits in the
old code are the digits in the new one.

Only the employees table changes. No other table stores a copy of the code --
every reference elsewhere is by id, which is the reason this rewrite is safe.

The sequence itself is untouched: it never emitted the prefix, only the number,
so old and new codes continue one numbering.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_jsan_employee_codes"
down_revision: str | None = "0020_helpdesk_announcements"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

NEW_DEFAULT = "'JSAN' || nextval('employees_employee_code_seq')::text"
OLD_DEFAULT = "'EMP-' || lpad(nextval('employees_employee_code_seq')::text, 6, '0')"


def upgrade() -> None:
    op.alter_column(
        "employees",
        "employee_code",
        server_default=sa.text(NEW_DEFAULT),
        existing_type=sa.String(length=20),
        existing_nullable=False,
    )
    # ``ltrim(..., '0')`` needs the number split from the prefix first, and the
    # cast through int both strips the padding and refuses non-numeric tails --
    # a code this UPDATE cannot parse is a code it must not touch.
    op.execute(
        """
        UPDATE employees
        SET employee_code = 'JSAN' || (substring(employee_code from 5))::int::text
        WHERE employee_code ~ '^EMP-[0-9]+$'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE employees
        SET employee_code = 'EMP-' || lpad(substring(employee_code from 5), 6, '0')
        WHERE employee_code ~ '^JSAN[0-9]+$'
        """
    )
    op.alter_column(
        "employees",
        "employee_code",
        server_default=sa.text(OLD_DEFAULT),
        existing_type=sa.String(length=20),
        existing_nullable=False,
    )
