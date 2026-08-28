"""Business unit master -- the top level of the organizational hierarchy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.mixins import CodedMasterMixin, status_check, unique_ci

if TYPE_CHECKING:
    from app.models.designation import Designation
    from app.models.team import Team


class BusinessUnit(Base, AuditableBase, CodedMasterMixin):
    """A major division of the organization; the parent of teams and designations."""

    __tablename__ = "business_units"
    __table_args__ = (
        unique_ci("uq_business_units_name_lower", "name"),
        unique_ci("uq_business_units_code_lower", "code"),
        status_check(),
        {"comment": "Top level of the organizational hierarchy."},
    )

    teams: Mapped[list[Team]] = relationship(
        back_populates="business_unit",
        foreign_keys="Team.business_unit_id",
        lazy="selectin",
        viewonly=True,
    )
    designations: Mapped[list[Designation]] = relationship(
        back_populates="business_unit",
        foreign_keys="Designation.business_unit_id",
        lazy="selectin",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<BusinessUnit id={self.id} code={self.code!r}>"
