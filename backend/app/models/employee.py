"""Employee master -- the central entity of the HRMS.

Attendance, leave, projects, performance, documents and payroll will all
reference an employee. That makes two design choices load-bearing:

* **The employee record is the source of truth for HR data**, even where a field
  also exists on the linked :class:`~app.models.user.User`. A user is a login
  identity; an employee is a person the organization employs. The create flow
  pre-fills from the user, and the employee record is authoritative afterwards.
* **Placement changes are never overwritten in place.** Every change to the
  department, designation, grade, reporting manager, work location or employment
  status writes a row to ``employee_employment_history``. The columns here hold
  the *current* state; the history holds how it got there.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.enums import (
    BLOOD_GROUP_SQL_VALUES,
    EMPLOYMENT_STATUS_SQL_VALUES,
    GENDER_SQL_VALUES,
    MARITAL_STATUS_SQL_VALUES,
    WORK_MODE_SQL_VALUES,
    EmploymentStatus,
)
from app.models.mixins import unique_ci

if TYPE_CHECKING:
    from app.models.business_unit import BusinessUnit
    from app.models.designation import Designation
    from app.models.employee_address import EmployeeAddress
    from app.models.employee_bank_detail import EmployeeBankDetail
    from app.models.employee_identification import EmployeeIdentification
    from app.models.employment_history import EmployeeEmploymentHistory
    from app.models.employment_type import EmploymentType
    from app.models.grade import Grade
    from app.models.location import Location
    from app.models.team import Team
    from app.models.user import User

#: Generates JSAN101, JSAN102, ... in the database itself.
#:
#: A sequence rather than ``SELECT max(...) + 1``: two concurrent creates would
#: read the same maximum and produce the same code, and the unique index would
#: then reject one of them for a reason the user cannot act on.
#:
#: Unpadded on purpose -- the organization writes these as JSAN336, not
#: JSAN000336. Migration 0021 changed the format from EMP-000001 and rewrote
#: the existing rows to keep every code on one pattern.
EMPLOYEE_CODE_SEQUENCE = "employees_employee_code_seq"
EMPLOYEE_CODE_DEFAULT = f"'JSAN' || nextval('{EMPLOYEE_CODE_SEQUENCE}')::text"


class Employee(Base, AuditableBase):
    """A person the organization employs."""

    __tablename__ = "employees"
    __table_args__ = (
        Index("ix_employees_name", "first_name", "last_name"),
        Index("ix_employees_status_deleted_at", "employment_status", "deleted_at"),
        # The placement columns a list screen filters on, in the order the
        # filters are applied.
        Index("ix_employees_placement", "business_unit_id", "team_id", "designation_id"),
        unique_ci("uq_employees_official_email_lower", "official_email"),
        CheckConstraint(f"gender IS NULL OR gender IN ({GENDER_SQL_VALUES})", name="gender"),
        CheckConstraint(
            f"blood_group IS NULL OR blood_group IN ({BLOOD_GROUP_SQL_VALUES})",
            name="blood_group",
        ),
        CheckConstraint(
            f"marital_status IS NULL OR marital_status IN ({MARITAL_STATUS_SQL_VALUES})",
            name="marital_status",
        ),
        CheckConstraint(f"employment_status IN ({EMPLOYMENT_STATUS_SQL_VALUES})", name="employment_status"),
        CheckConstraint(f"work_mode IS NULL OR work_mode IN ({WORK_MODE_SQL_VALUES})", name="work_mode"),
        CheckConstraint("ctc IS NULL OR ctc >= 0", name="ctc_non_negative"),
        # An employee cannot report to themselves. The deeper case -- a cycle
        # through several employees -- cannot be expressed as a CHECK and is
        # enforced in the service.
        CheckConstraint(
            "reporting_manager_id IS NULL OR reporting_manager_id <> id", name="manager_not_self"
        ),
        {"comment": "Employee master record; the central entity of the HRMS."},
    )

    # -- Identity ------------------------------------------------------
    employee_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        index=True,
        server_default=text(EMPLOYEE_CODE_DEFAULT),
        doc="System-generated employee identifier (JSAN101). Never editable.",
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", use_alter=True),
        nullable=True,
        unique=True,
        index=True,
        doc=(
            "The login account for this person. Nullable because an employee "
            "record can legitimately exist before an account is provisioned; "
            "unique because one account cannot belong to two employees."
        ),
    )

    # -- Personal information -------------------------------------------
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    blood_group: Mapped[str | None] = mapped_column(String(3), nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(100), nullable=True)

    personal_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    mobile_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    alternate_number: Mapped[str | None] = mapped_column(String(32), nullable=True)

    emergency_contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    emergency_contact_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    emergency_contact_relationship: Mapped[str | None] = mapped_column(String(50), nullable=True)

    photo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # -- Official information -------------------------------------------
    official_email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        index=True,
        doc="Work address. Unique across employees, compared case-insensitively.",
    )
    official_mobile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extension_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    work_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # -- Employment ------------------------------------------------------
    #
    # Every organizational reference is nullable and ON DELETE RESTRICT, for the
    # same reasons as on `users`: an employee can be recorded before the org tree
    # is complete, and master records are archived rather than deleted, so a hard
    # delete that silently unassigned people is not a recovery path.
    joining_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, doc="First day of employment. Required."
    )
    confirmation_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, doc="Set when probation is confirmed."
    )

    employment_type_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employment_types.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_units.id", ondelete="RESTRICT"), nullable=True, index=True
    )
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
        doc="The employee this person reports to. Self-referential.",
    )

    employment_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EmploymentStatus.PROBATION,
        server_default=EmploymentStatus.PROBATION.value,
        index=True,
        doc="Lifecycle state; see app.models.enums.EmploymentStatus.",
    )

    # -- Compensation ----------------------------------------------------
    #
    # Basic only. Payroll -- components, deductions, revisions -- is a later
    # module and will hang off these columns rather than replace them.
    ctc: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        doc="Cost to company, annual. Numeric rather than float: money must not round.",
    )
    salary_grade_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("grades.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        doc=(
            "Pay band, referencing the same Grade master as `grade_id`. Separate "
            "because an employee's job grade and pay band can legitimately "
            "differ -- a promotion often moves one before the other."
        ),
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # -- Relationships ---------------------------------------------------
    #
    # Eager-loaded because the list and profile screens always display the names
    # rather than the ids; lazy loading them would be an N+1 per row.
    user: Mapped[User | None] = relationship(foreign_keys=[user_id], lazy="joined")
    employment_type: Mapped[EmploymentType | None] = relationship(
        foreign_keys=[employment_type_id], lazy="joined"
    )
    business_unit: Mapped[BusinessUnit | None] = relationship(foreign_keys=[business_unit_id], lazy="joined")
    team: Mapped[Team | None] = relationship(foreign_keys=[team_id], lazy="joined")
    designation: Mapped[Designation | None] = relationship(foreign_keys=[designation_id], lazy="joined")
    grade: Mapped[Grade | None] = relationship(foreign_keys=[grade_id], lazy="joined")
    salary_grade: Mapped[Grade | None] = relationship(foreign_keys=[salary_grade_id], lazy="joined")
    work_location: Mapped[Location | None] = relationship(foreign_keys=[work_location_id], lazy="joined")

    # The manager is loaded one level deep only. `join_depth` stops SQLAlchemy
    # walking the whole reporting chain on every read, which on a deep org would
    # be a self-join per level.
    reporting_manager: Mapped[Employee | None] = relationship(
        remote_side="Employee.id",
        foreign_keys=[reporting_manager_id],
        lazy="joined",
        join_depth=1,
    )

    # `selectin` rather than `joined`: these are collections, and joining them
    # would multiply the employee row by the number of children and break
    # LIMIT-based paging.
    addresses: Mapped[list[EmployeeAddress]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    bank_detail: Mapped[EmployeeBankDetail | None] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )
    identification: Mapped[EmployeeIdentification | None] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )
    employment_history: Mapped[list[EmployeeEmploymentHistory]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        # Explicit: a history row points at `employees` twice -- once for whose
        # history it is, once for who they reported to -- and without this
        # SQLAlchemy cannot tell which link defines the collection.
        foreign_keys="EmployeeEmploymentHistory.employee_id",
        # History is only ever read on the profile page, and it grows without
        # bound. Loading it with every employee in a list would be wasteful.
        lazy="noload",
        order_by="EmployeeEmploymentHistory.effective_date.desc()",
    )

    # -- Behaviour -------------------------------------------------------
    @property
    def full_name(self) -> str:
        """Display name, derived rather than stored.

        Storing it alongside the parts would let the two disagree the first time
        someone edits only a surname.
        """
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def initials(self) -> str:
        return f"{self.first_name[:1]}{self.last_name[:1]}".upper()

    @property
    def is_employed(self) -> bool:
        """Whether this person is currently on the books."""
        from app.models.enums import EMPLOYED_STATUSES

        return self.deleted_at is None and self.employment_status in EMPLOYED_STATUSES

    def address_of(self, address_type: str) -> EmployeeAddress | None:
        """The current or permanent address, or ``None`` when not recorded."""
        return next((row for row in self.addresses if row.address_type == address_type), None)

    def __repr__(self) -> str:
        return f"<Employee id={self.id} code={self.employee_code!r} name={self.full_name!r}>"
