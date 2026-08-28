"""Drop ``employees.shift_id``, a column whose promised future never arrived.

Revision ID: 0023_drop_employees_shift_id
Revises: 0022_prune_dead_permissions
Create Date: 2026-08-21 09:10:00

The column was reserved in Phase 4 for a Shift master that "does not exist
yet", with the note that the shift module would add the foreign key. The shift
module shipped in 0014 -- and modelled the relationship properly as the
``employee_shifts`` assignment table (a person's shift changes over time; a
column can only hold the latest and destroys the history). Nothing ever read
or wrote ``employees.shift_id``; it has been NULL on every row since 0004.

Dropping it is safe precisely because of how it was reserved: no FK, absent
from every write schema, so no code path can be holding it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0023_drop_employees_shift_id"
down_revision: str | None = "0022_prune_dead_permissions"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("employees", "shift_id")


def downgrade() -> None:
    op.add_column("employees", sa.Column("shift_id", PGUUID(as_uuid=True), nullable=True))
