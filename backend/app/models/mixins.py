"""Column mixins shared by the organization master-data models.

These sit above :mod:`app.db.mixins` (which supplies the platform-wide audit
contract) and add the columns every master record has in common, so the nine
master tables cannot drift apart.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, String, Text, text
from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column

from app.models.enums import RECORD_STATUS_SQL_VALUES, RecordStatus


@declarative_mixin
class NamedMasterMixin:
    """A human-readable name, a free-text description and a business status."""

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
        doc="Display name. Trimmed and whitespace-collapsed before persisting.",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RecordStatus.ACTIVE,
        server_default=RecordStatus.ACTIVE.value,
        index=True,
        doc="Business status; see app.models.enums.RecordStatus.",
    )


@declarative_mixin
class CodedMasterMixin(NamedMasterMixin):
    """Adds the short, stable code that other modules reference."""

    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Short stable identifier, normalised to upper case before persisting.",
    )


def status_check() -> CheckConstraint:
    """CHECK constraint restricting ``status`` to the known values.

    The naming convention on the metadata expands ``name="status"`` into
    ``ck_<table>_status``, so every table gets a predictable constraint name.
    """
    return CheckConstraint(f"status IN ({RECORD_STATUS_SQL_VALUES})", name="status")


def unique_ci(index_name: str, column: str) -> Index:
    """Case-insensitive unique index on a single column.

    A plain ``UNIQUE`` constraint would happily accept both ``GIS`` and ``gis``.
    For master data that other modules reference by name, that is a data-quality
    bug rather than a nuance, so uniqueness is enforced on ``lower(column)``.
    """
    return Index(index_name, text(f"lower({column})"), unique=True)


def unique_ci_scoped(index_name: str, parent_column: str, column: str) -> Index:
    """Case-insensitive unique index on a column, scoped to its parent.

    Two practices may both own a "Backend" department; one practice may not own
    two.
    """
    return Index(index_name, text(parent_column), text(f"lower({column})"), unique=True)
