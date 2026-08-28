"""Declarative base for all ORM models.

A explicit constraint naming convention is essential: without it Alembic
generates anonymous constraint names that cannot be reliably dropped in a
downgrade, which makes migrations irreversible.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, declared_attr

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_CAMEL_TO_SNAKE = re.compile(r"(?<!^)(?=[A-Z])")


class Base(DeclarativeBase):
    """Base class shared by every model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # ``eager_defaults`` makes SQLAlchemy fetch server-generated values (our
    # ``created_at`` / ``updated_at`` defaults and ON UPDATE triggers) with a
    # RETURNING clause as part of the INSERT/UPDATE itself.
    #
    # Without it, those columns are left expired and are re-loaded lazily on
    # first access -- which, under asyncio, means blocking IO outside a
    # greenlet context and a `MissingGreenlet` error the moment a response
    # model touches `updated_at`. PostgreSQL supports RETURNING, so this costs
    # nothing extra.
    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        return {"eager_defaults": True}

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Derive ``snake_case`` plural-agnostic table names from the class name."""
        return _CAMEL_TO_SNAKE.sub("_", cls.__name__).lower()

    def to_dict(self, *, exclude: set[str] | None = None) -> dict[str, Any]:
        """Return a plain dict of column values (helpful for audit payloads)."""
        excluded = exclude or set()
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
            if column.name not in excluded
        }

    def __repr__(self) -> str:
        identifier = getattr(self, "id", None)
        return f"<{type(self).__name__} id={identifier}>"
