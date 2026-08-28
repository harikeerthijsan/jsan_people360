"""Grade master -- the compensation/seniority band of a role."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.mixins import CodedMasterMixin, status_check, unique_ci


class Grade(Base, AuditableBase, CodedMasterMixin):
    """A band such as G1, G2 or M1."""

    __tablename__ = "grades"
    __table_args__ = (
        unique_ci("uq_grades_name_lower", "name"),
        unique_ci("uq_grades_code_lower", "code"),
        CheckConstraint("level >= 1", name="level_positive"),
        status_check(),
        {"comment": "Compensation and seniority bands."},
    )

    level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        doc="Numeric rank used to order grades; 1 is the most junior.",
    )

    def __repr__(self) -> str:
        return f"<Grade id={self.id} code={self.code!r} level={self.level}>"
