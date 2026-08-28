"""Employee addresses.

A separate table rather than two sets of columns on ``employees``: the shape of
an address is identical whichever kind it is, and duplicating eight columns to
distinguish "current" from "permanent" would double every future change to the
address format.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.enums import ADDRESS_TYPE_SQL_VALUES

if TYPE_CHECKING:
    from app.models.employee import Employee


class EmployeeAddress(Base, AuditableBase):
    """One address of one kind for one employee."""

    __tablename__ = "employee_addresses"
    __table_args__ = (
        # One current and one permanent address per employee. Enforced as a
        # partial unique index so an archived row does not block re-entry.
        Index(
            "uq_employee_addresses_employee_id_type",
            "employee_id",
            "address_type",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        CheckConstraint(f"address_type IN ({ADDRESS_TYPE_SQL_VALUES})", name="address_type"),
        {"comment": "Current and permanent addresses of an employee."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="CASCADE: an address is meaningless without the employee it belongs to.",
    )
    address_type: Mapped[str] = mapped_column(
        String(20), nullable=False, doc="current or permanent; see app.models.enums.AddressType."
    )

    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    landmark: Mapped[str | None] = mapped_column(String(150), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)

    employee: Mapped[Employee] = relationship(back_populates="addresses", foreign_keys=[employee_id])

    @property
    def single_line(self) -> str:
        """The address as one comma-separated line, for exports and summaries."""
        parts = [
            self.address_line1,
            self.address_line2,
            self.landmark,
            self.city,
            self.state,
            self.country,
            self.postal_code,
        ]
        return ", ".join(part for part in parts if part)

    def __repr__(self) -> str:
        return f"<EmployeeAddress id={self.id} type={self.address_type!r}>"
