"""Runtime application settings stored in the database.

These are *tenant/business* settings that operators change without a redeploy
(company name, date format, working week...). Infrastructure configuration --
secrets, connection strings, ports -- belongs in the environment, never here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.mixins import AuditableBase


class AppSetting(Base, AuditableBase):
    """A single key/value configuration entry."""

    __tablename__ = "app_settings"
    __table_args__ = ({"comment": "Operator-editable runtime configuration."},)

    key: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        unique=True,
        index=True,
        doc="Dotted, namespaced key, e.g. 'company.name'.",
    )
    value: Mapped[dict[str, Any] | list[Any] | str | int | float | bool | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="JSON-encoded value; JSONB keeps the type intact without casting.",
    )
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="general",
        server_default="general",
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        doc="Public settings may be served to unauthenticated clients.",
    )
    is_editable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        doc="System-managed settings are locked against operator edits.",
    )

    def __repr__(self) -> str:
        return f"<AppSetting key={self.key!r}>"
