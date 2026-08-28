"""Employment type master -- the contractual basis of an engagement."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.mixins import CodedMasterMixin, status_check, unique_ci


class EmploymentType(Base, AuditableBase, CodedMasterMixin):
    """How a person is engaged: full time, contract, intern and so on."""

    __tablename__ = "employment_types"
    __table_args__ = (
        unique_ci("uq_employment_types_name_lower", "name"),
        unique_ci("uq_employment_types_code_lower", "code"),
        status_check(),
        CheckConstraint("notice_period_days >= 0", name="notice_period_days_non_negative"),
        {"comment": "Contractual basis of an engagement."},
    )

    notice_period_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc=(
            "Notice a person on this contract owes, in calendar days. The "
            "Resignation module reads it here rather than hardcoding a number, "
            "because a consultant's notice and a full-time employee's are not "
            "the same and the difference is a configuration decision. NULL "
            "means 'not configured' and falls back to "
            "app.models.enums.DEFAULT_NOTICE_PERIOD_DAYS -- distinct from 0, "
            "which is a deliberate 'no notice required'."
        ),
    )

    def __repr__(self) -> str:
        return f"<EmploymentType id={self.id} code={self.code!r}>"
