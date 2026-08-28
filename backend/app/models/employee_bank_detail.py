"""Employee bank account details.

Held in its own table rather than on ``employees`` for one reason: it is the
narrowest possible surface for the most sensitive rows in the system. A query
that reads employees does not read this table unless it asks for it, so the
account numbers stay out of exports, list responses and log lines by default.

See :mod:`app.utils.masking` for how the values are presented, and
``docs/EmployeeModule.md`` for what "stored securely" does and does not mean
here.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase

if TYPE_CHECKING:
    from app.models.employee import Employee


class EmployeeBankDetail(Base, AuditableBase):
    """The account an employee is paid into."""

    __tablename__ = "employee_bank_details"
    __table_args__ = (
        Index(
            "uq_employee_bank_details_employee_id",
            "employee_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        {"comment": "Bank account an employee is paid into. Sensitive."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    bank_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_number: Mapped[str] = mapped_column(
        String(34),
        nullable=False,
        doc="Up to 34 characters, the IBAN maximum. Masked in every read response.",
    )
    account_holder_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        doc="When the account is not in the employee's own name.",
    )
    ifsc_code: Mapped[str] = mapped_column(String(11), nullable=False)
    branch_name: Mapped[str] = mapped_column(String(150), nullable=False)

    employee: Mapped[Employee] = relationship(back_populates="bank_detail", foreign_keys=[employee_id])

    def __repr__(self) -> str:
        # Deliberately omits the account number: repr() ends up in tracebacks.
        return f"<EmployeeBankDetail id={self.id} employee_id={self.employee_id}>"
