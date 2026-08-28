"""Location master -- a physical office or work site."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.mixins import CodedMasterMixin, status_check, unique_ci


class Location(Base, AuditableBase, CodedMasterMixin):
    """An office or work site that employees can be assigned to."""

    __tablename__ = "locations"
    __table_args__ = (
        unique_ci("uq_locations_name_lower", "name"),
        unique_ci("uq_locations_code_lower", "code"),
        status_check(),
        {"comment": "Physical offices and work sites."},
    )

    country: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    address: Mapped[str] = mapped_column(Text, nullable=False, doc="Full postal address.")
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="IANA timezone identifier. Attendance and scheduling resolve against this.",
    )

    def __repr__(self) -> str:
        return f"<Location id={self.id} code={self.code!r}>"
