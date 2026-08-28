"""Government-issued identifiers held for an employee.

Statutory identifiers (Aadhaar, PAN, UAN, PF, ESI) are unique to a person, so
each is uniquely indexed: two employee records carrying the same Aadhaar is
always a duplicate person rather than a coincidence, and catching it here is far
cheaper than reconciling payroll later.

Like :mod:`app.models.employee_bank_detail`, this lives in its own table so that
reading an employee does not read their identifiers.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase

if TYPE_CHECKING:
    from app.models.employee import Employee


def _unique_identifier(index_name: str, column: str) -> Index:
    """Unique index over the rows that actually hold a value.

    Partial on ``IS NOT NULL`` because most of these identifiers are optional and
    a plain unique index would be satisfied by any number of NULLs but would
    still carry every one of them.
    """
    return Index(
        index_name,
        text(f"upper({column})"),
        unique=True,
        postgresql_where=text(f"{column} IS NOT NULL AND deleted_at IS NULL"),
    )


class EmployeeIdentification(Base, AuditableBase):
    """Statutory and identity documents recorded against an employee."""

    __tablename__ = "employee_identification"
    __table_args__ = (
        Index(
            "uq_employee_identification_employee_id",
            "employee_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        _unique_identifier("uq_employee_identification_aadhaar", "aadhaar_number"),
        _unique_identifier("uq_employee_identification_pan", "pan_number"),
        _unique_identifier("uq_employee_identification_passport", "passport_number"),
        _unique_identifier("uq_employee_identification_uan", "uan_number"),
        _unique_identifier("uq_employee_identification_pf", "pf_number"),
        _unique_identifier("uq_employee_identification_esi", "esi_number"),
        {"comment": "Government-issued identifiers for an employee. Sensitive."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    aadhaar_number: Mapped[str | None] = mapped_column(
        String(12), nullable=True, doc="12 digits, stored without separators. Masked in read responses."
    )
    pan_number: Mapped[str | None] = mapped_column(
        String(10), nullable=True, doc="ABCDE1234F. Masked in read responses."
    )
    passport_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    passport_expiry: Mapped[str | None] = mapped_column(
        String(10), nullable=True, doc="ISO date string; free-form because some passports omit a day."
    )
    driving_license_number: Mapped[str | None] = mapped_column(String(25), nullable=True)

    uan_number: Mapped[str | None] = mapped_column(
        String(12), nullable=True, doc="Universal Account Number for provident fund; 12 digits."
    )
    pf_number: Mapped[str | None] = mapped_column(
        String(30), nullable=True, doc="Establishment PF number; the format varies by region."
    )
    esi_number: Mapped[str | None] = mapped_column(
        String(17), nullable=True, doc="Employees' State Insurance number; 17 digits."
    )

    employee: Mapped[Employee] = relationship(back_populates="identification", foreign_keys=[employee_id])

    def __repr__(self) -> str:
        # Deliberately omits every identifier: repr() ends up in tracebacks.
        return f"<EmployeeIdentification id={self.id} employee_id={self.employee_id}>"
