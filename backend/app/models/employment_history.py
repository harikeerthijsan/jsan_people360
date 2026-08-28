"""Employment history -- the append-only record of an employee's placement.

Each row is the **state after a change**, not a description of the change. That
is the difference between a log and a history: given a date, a snapshot table can
answer "which team were they in?", which is exactly what attendance,
payroll and performance will need to ask about periods that have already closed.

Rows are never updated and never deleted. The opening row (``CREATED``) is
written when the employee is first saved, so the series covers the whole
employment rather than starting at the first amendment.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.enums import EMPLOYMENT_CHANGE_TYPE_SQL_VALUES, EMPLOYMENT_STATUS_SQL_VALUES

if TYPE_CHECKING:
    from app.models.designation import Designation
    from app.models.employee import Employee
    from app.models.grade import Grade
    from app.models.location import Location
    from app.models.team import Team


class EmployeeEmploymentHistory(Base, AuditableBase):
    """One entry in an employee's placement history."""

    __tablename__ = "employee_employment_history"
    __table_args__ = (
        # The profile timeline reads one employee's rows newest first; this is
        # the index that serves it.
        Index("ix_employee_employment_history_employee_effective", "employee_id", "effective_date"),
        CheckConstraint(f"change_type IN ({EMPLOYMENT_CHANGE_TYPE_SQL_VALUES})", name="change_type"),
        CheckConstraint(f"employment_status IN ({EMPLOYMENT_STATUS_SQL_VALUES})", name="employment_status"),
        {"comment": "Append-only history of an employee's organizational placement."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    change_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        doc="What prompted the row; see app.models.enums.EmploymentChangeType.",
    )
    effective_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        doc=(
            "The date the change takes effect, which is not necessarily the date "
            "it was entered -- a transfer is routinely recorded in arrears."
        ),
    )

    # -- State after the change ------------------------------------------
    #
    # RESTRICT, matching `employees`: masters are archived rather than deleted,
    # and history must not be silently hollowed out by a delete that slipped
    # through.
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    designation_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("designations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    grade_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("grades.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    work_location_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    reporting_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="RESTRICT", use_alter=True),
        nullable=True,
        index=True,
    )
    employment_status: Mapped[str] = mapped_column(String(20), nullable=False)

    # -- What changed ------------------------------------------------------
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc=(
            "Human-readable account of the change, composed when the row is "
            "written -- 'Team: Platform to Delivery'. Frozen "
            "at write time so the timeline still reads correctly after a master "
            "record is renamed."
        ),
    )
    reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True, doc="Why the change was made, as entered by the person making it."
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped[Employee] = relationship(
        back_populates="employment_history",
        foreign_keys=[employee_id],
    )
    team: Mapped[Team | None] = relationship(foreign_keys=[team_id], lazy="joined")
    designation: Mapped[Designation | None] = relationship(foreign_keys=[designation_id], lazy="joined")
    grade: Mapped[Grade | None] = relationship(foreign_keys=[grade_id], lazy="joined")
    work_location: Mapped[Location | None] = relationship(foreign_keys=[work_location_id], lazy="joined")
    reporting_manager: Mapped[Employee | None] = relationship(
        foreign_keys=[reporting_manager_id], lazy="joined"
    )

    def __repr__(self) -> str:
        return f"<EmployeeEmploymentHistory id={self.id} type={self.change_type!r} on={self.effective_date}>"
