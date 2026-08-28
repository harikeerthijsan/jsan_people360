"""Designation master -- a job title within a business unit."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.mixins import CodedMasterMixin, status_check, unique_ci, unique_ci_scoped

if TYPE_CHECKING:
    from app.models.business_unit import BusinessUnit


class Designation(Base, AuditableBase, CodedMasterMixin):
    """A job title such as Software Engineer or Project Manager."""

    __tablename__ = "designations"
    __table_args__ = (
        unique_ci("uq_designations_code_lower", "code"),
        unique_ci_scoped("uq_designations_business_unit_id_name_lower", "business_unit_id", "name"),
        CheckConstraint("level >= 1", name="level_positive"),
        status_check(),
        {"comment": "Job titles within a business unit."},
    )

    business_unit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_units.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        doc="Seniority rank; 1 is the most junior. Used for ordering, not for authorisation.",
    )

    business_unit: Mapped[BusinessUnit] = relationship(
        back_populates="designations",
        foreign_keys=[business_unit_id],
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<Designation id={self.id} code={self.code!r} level={self.level}>"
