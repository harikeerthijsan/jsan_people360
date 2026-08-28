"""Payroll foundation persistence models.

Six tables, and the shape follows one decision: **a compensation record is a
period, never a mutable number.** A salary revision ends the current record and
opens a new one; both survive, and ``salary_history`` records the change itself
— previous CTC, new CTC, reason, who, when. There is no code path that edits a
past salary, which is what makes "never overwrite salary history" a property of
the design rather than a rule somebody has to remember.

Nothing here calculates. The structures, components and amounts are the inputs
a future payroll run will read; storing them correctly is this phase's whole
job, and a column that looked like a computed net-pay would be a lie until that
phase exists.

Component values are snapshotted onto ``employee_compensation_components`` at
assignment time (calculation type and basis included), so editing a component
master later changes future assignments and never rewrites what somebody was
already promised.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.employee import Employee
from app.models.enums import (
    COMPENSATION_STATUS_SQL_VALUES,
    LEAVE_TREATMENT_SQL_VALUES,
    PAY_FREQUENCY_SQL_VALUES,
    PAYROLL_ADJUSTMENT_STATUS_SQL_VALUES,
    PAYROLL_APPROVAL_ACTION_SQL_VALUES,
    PAYROLL_DAY_BASIS_SQL_VALUES,
    PAYROLL_ELIGIBILITY_REASON_SQL_VALUES,
    PAYROLL_ELIGIBILITY_SQL_VALUES,
    PAYROLL_EXCEPTION_CATEGORY_SQL_VALUES,
    PAYROLL_EXCEPTION_SEVERITY_SQL_VALUES,
    PAYROLL_EXCEPTION_STATUS_SQL_VALUES,
    PAYROLL_INPUT_STATUS_SQL_VALUES,
    PAYROLL_ITEM_TYPE_SQL_VALUES,
    PAYROLL_LINE_SOURCE_SQL_VALUES,
    PAYROLL_PERIOD_STATUS_SQL_VALUES,
    PAYROLL_RECORD_STATUS_SQL_VALUES,
    PAYROLL_RUN_EXCEPTION_TYPE_SQL_VALUES,
    PAYROLL_RUN_STATUS_SQL_VALUES,
    PAYROLL_SOURCE_TYPE_SQL_VALUES,
    PAYSLIP_STATUS_SQL_VALUES,
    PERCENTAGE_BASIS_SQL_VALUES,
    RECORD_STATUS_SQL_VALUES,
    ROUNDING_RULE_SQL_VALUES,
    SALARY_CALCULATION_TYPE_SQL_VALUES,
    SALARY_COMPONENT_TYPE_SQL_VALUES,
    SALARY_STRUCTURE_STATUS_SQL_VALUES,
    UNPAID_LEAVE_TREATMENT_SQL_VALUES,
    WORKING_DAYS_RULE_SQL_VALUES,
    CompensationStatus,
    PayFrequency,
    PayrollAdjustmentStatus,
    PayrollDayBasis,
    PayrollEligibility,
    PayrollExceptionStatus,
    PayrollInputStatus,
    PayrollPeriodStatus,
    PayrollRunStatus,
    PayslipStatus,
    PercentageBasis,
    RecordStatus,
    RoundingRule,
    SalaryStructureStatus,
    UnpaidLeaveTreatment,
    WorkingDaysRule,
)
from app.models.user import User
from app.models.workforce import HolidayCalendar, LeaveType

#: The checks a percentage component must satisfy wherever its snapshot lands.
_PERCENTAGE_COHERENT = "calculation_type <> 'percentage' OR (value <= 100 AND percentage_basis IS NOT NULL)"
_FIXED_HAS_NO_BASIS = "calculation_type <> 'fixed' OR percentage_basis IS NULL"


class SalaryStructure(Base, AuditableBase):
    """A reusable compensation template — which components, paid how often.

    A template rather than a person's pay: assigning one to an employee copies
    its component list into a compensation record, so deactivating or editing
    a structure later never touches anybody's existing salary.
    """

    __tablename__ = "salary_structures"
    __table_args__ = (
        # Case-insensitive uniqueness, like the organization masters: two
        # structures differing only in capitalisation are the same structure.
        Index("uq_salary_structures_name_ci", text("lower(name)"), unique=True),
        CheckConstraint(f"pay_frequency IN ({PAY_FREQUENCY_SQL_VALUES})", name="pay_frequency"),
        CheckConstraint(f"status IN ({SALARY_STRUCTURE_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint("char_length(currency) = 3", name="currency_iso"),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="effective_window_ordered",
        ),
        {"comment": "Reusable salary structure templates."},
    )

    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    pay_frequency: Mapped[str] = mapped_column(
        String(20), default=PayFrequency.MONTHLY, server_default=PayFrequency.MONTHLY.value, index=True
    )
    #: ISO 4217. Stored per structure rather than read from settings so a
    #: structure keeps meaning what it meant if the company default changes.
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    status: Mapped[str] = mapped_column(
        String(20),
        default=SalaryStructureStatus.DRAFT,
        server_default=SalaryStructureStatus.DRAFT.value,
        index=True,
    )
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)

    components: Mapped[list[SalaryStructureComponent]] = relationship(
        back_populates="structure", lazy="selectin", order_by="SalaryStructureComponent.created_at"
    )


class SalaryComponent(Base, AuditableBase):
    """One configurable earning or deduction — Basic, HRA, PF, Tax.

    A table rather than an enum because the brief is explicit that nothing may
    hardcode the list into a calculation. Deactivated rather than deleted: a
    component referenced by last year's compensation has to keep resolving to
    a name.
    """

    __tablename__ = "salary_components"
    __table_args__ = (
        UniqueConstraint("code", name="uq_salary_components_code"),
        CheckConstraint(f"component_type IN ({SALARY_COMPONENT_TYPE_SQL_VALUES})", name="component_type"),
        CheckConstraint(
            f"calculation_type IN ({SALARY_CALCULATION_TYPE_SQL_VALUES})", name="calculation_type"
        ),
        CheckConstraint(
            f"percentage_basis IS NULL OR percentage_basis IN ({PERCENTAGE_BASIS_SQL_VALUES})",
            name="percentage_basis",
        ),
        CheckConstraint("value >= 0", name="value_non_negative"),
        CheckConstraint(_PERCENTAGE_COHERENT, name="percentage_coherent"),
        CheckConstraint(_FIXED_HAS_NO_BASIS, name="fixed_has_no_basis"),
        CheckConstraint(f"status IN ({RECORD_STATUS_SQL_VALUES})", name="status"),
        {"comment": "Configurable compensation components."},
    )

    name: Mapped[str] = mapped_column(String(120), index=True)
    code: Mapped[str] = mapped_column(String(30))
    component_type: Mapped[str] = mapped_column(String(20), index=True)
    calculation_type: Mapped[str] = mapped_column(String(20))
    #: An amount for ``fixed``, a rate (0-100) for ``percentage``. The default
    #: a new assignment starts from; the assignment's own snapshot is the truth.
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), server_default="0")
    #: What a percentage is a percentage of. NULL for fixed amounts.
    percentage_basis: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), default=RecordStatus.ACTIVE, server_default=RecordStatus.ACTIVE.value, index=True
    )

    # -- Pay behaviour flags (Phase 2) ---------------------------------
    #
    # How this component behaves when a payroll run reads it. Flags only:
    # nothing in this phase calculates against them, and no flag is consulted
    # by the Phase 1 snapshot — an existing compensation record means what it
    # meant when it was assigned.
    proration_allowed: Mapped[bool] = mapped_column(
        default=True, server_default="true", doc="May be reduced for a partial period."
    )
    attendance_impact: Mapped[bool] = mapped_column(
        default=False, server_default="false", doc="Reduced by absence when the attendance rule says so."
    )
    leave_impact: Mapped[bool] = mapped_column(
        default=False, server_default="false", doc="Reduced by unpaid leave when the leave rule says so."
    )
    overtime_eligible: Mapped[bool] = mapped_column(
        default=False, server_default="false", doc="Included in the overtime hourly-rate base."
    )
    is_taxable: Mapped[bool] = mapped_column(
        default=True, server_default="true", doc="In scope for the future tax phase. No tax is computed here."
    )


class SalaryStructureComponent(Base, AuditableBase):
    """One component's membership in one structure.

    Membership is what "required components" means at assignment time: every
    component a structure carries must appear in a compensation assigned from
    it. ``default_value`` overrides the component master's default for this
    structure only, and is still only a starting point for the assignment.
    """

    __tablename__ = "salary_structure_components"
    __table_args__ = (
        UniqueConstraint("structure_id", "component_id", name="uq_salary_structure_components_pair"),
        CheckConstraint("default_value IS NULL OR default_value >= 0", name="default_value_non_negative"),
        {"comment": "Which components a salary structure carries."},
    )

    structure_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("salary_structures.id", ondelete="CASCADE"), index=True
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("salary_components.id", ondelete="RESTRICT"), index=True
    )
    default_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    structure: Mapped[SalaryStructure] = relationship(back_populates="components")
    component: Mapped[SalaryComponent] = relationship(lazy="joined")


class EmployeeCompensation(Base, AuditableBase):
    """One period of one employee's pay.

    ``effective_from``/``effective_to`` bound the period; ``effective_to`` NULL
    means it is the current word. The partial unique index below makes two
    open-ended active records for one employee impossible at the database, and
    the service refuses any overlap the index cannot express.
    """

    __tablename__ = "employee_compensation"
    __table_args__ = (
        Index(
            # One open-ended active record per employee, enforced where it
            # cannot be raced: two concurrent assignments both flushing an
            # open period will have one of them refused by PostgreSQL.
            "uq_employee_compensation_open",
            "employee_id",
            unique=True,
            postgresql_where=text("effective_to IS NULL AND status = 'active' AND deleted_at IS NULL"),
        ),
        Index("ix_employee_compensation_employee_from", "employee_id", "effective_from"),
        CheckConstraint(f"status IN ({COMPENSATION_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint("char_length(currency) = 3", name="currency_iso"),
        CheckConstraint("annual_ctc >= 0", name="annual_ctc_non_negative"),
        CheckConstraint("annual_gross >= 0", name="annual_gross_non_negative"),
        CheckConstraint("monthly_gross >= 0", name="monthly_gross_non_negative"),
        CheckConstraint("basic_salary >= 0", name="basic_salary_non_negative"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="effective_window_ordered"
        ),
        {"comment": "Employee compensation records, one per effective period."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    salary_structure_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("salary_structures.id", ondelete="RESTRICT"), index=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    annual_ctc: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    annual_gross: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    monthly_gross: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    basic_salary: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(
        String(20),
        default=CompensationStatus.ACTIVE,
        server_default=CompensationStatus.ACTIVE.value,
        index=True,
    )
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date)

    employee: Mapped[Employee] = relationship(lazy="joined")
    structure: Mapped[SalaryStructure] = relationship(lazy="joined")
    components: Mapped[list[EmployeeCompensationComponent]] = relationship(
        back_populates="compensation",
        lazy="selectin",
        order_by="EmployeeCompensationComponent.created_at",
    )


class EmployeeCompensationComponent(Base, AuditableBase):
    """One component's value inside one compensation record.

    Calculation type and basis are copied from the component master at
    assignment, so the record stays a complete statement of what was agreed
    even if the master is later re-expressed.
    """

    __tablename__ = "employee_compensation_components"
    __table_args__ = (
        UniqueConstraint("compensation_id", "component_id", name="uq_employee_compensation_components_pair"),
        CheckConstraint(
            f"calculation_type IN ({SALARY_CALCULATION_TYPE_SQL_VALUES})", name="calculation_type"
        ),
        CheckConstraint(
            f"percentage_basis IS NULL OR percentage_basis IN ({PERCENTAGE_BASIS_SQL_VALUES})",
            name="percentage_basis",
        ),
        CheckConstraint("value >= 0", name="value_non_negative"),
        CheckConstraint(_PERCENTAGE_COHERENT, name="percentage_coherent"),
        CheckConstraint(_FIXED_HAS_NO_BASIS, name="fixed_has_no_basis"),
        {"comment": "Component values snapshotted onto a compensation record."},
    )

    compensation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employee_compensation.id", ondelete="CASCADE"), index=True
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("salary_components.id", ondelete="RESTRICT"), index=True
    )
    calculation_type: Mapped[str] = mapped_column(String(20))
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    percentage_basis: Mapped[str | None] = mapped_column(String(20))

    compensation: Mapped[EmployeeCompensation] = relationship(back_populates="components")
    component: Mapped[SalaryComponent] = relationship(lazy="joined")


class SalaryHistory(Base, AuditableBase):
    """Append-only record of every salary change.

    Distinct from the audit log, which answers "what did this user do". This
    answers "how did this person's pay move over the years" — the question the
    employee themselves, a future payroll run and an auditor all ask — and it
    survives even if the compensation records are ever archived. No endpoint
    updates or deletes a row here; a correction is a new revision.
    """

    __tablename__ = "salary_history"
    __table_args__ = (
        Index("ix_salary_history_employee_created", "employee_id", "created_at"),
        CheckConstraint("new_annual_ctc >= 0", name="new_ctc_non_negative"),
        CheckConstraint(
            "previous_annual_ctc IS NULL OR previous_annual_ctc >= 0", name="previous_ctc_non_negative"
        ),
        {"comment": "Append-only salary change history."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    #: The compensation record the change produced.
    compensation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employee_compensation.id", ondelete="RESTRICT"), index=True
    )
    #: The record it ended. NULL for the initial assignment.
    previous_compensation_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employee_compensation.id", ondelete="SET NULL")
    )
    previous_annual_ctc: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    new_annual_ctc: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    effective_from: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    changed_by: Mapped[User | None] = relationship(foreign_keys=[changed_by_id], lazy="joined")


# ======================================================================
# Phase 2 — payroll configuration and pay rules
#
# Configuration the future calculation engine will read, and nothing that
# calculates. Two decisions shape it. **The configuration is a singleton row,
# not a settings sprawl**: one typed row whose columns the schema checks,
# guarded by a UNIQUE on a constant column so a second one cannot exist.
# **Important changes never overwrite silently**: every configuration update
# requires a reason and an effective date, and writes one history row per
# changed field before the column moves.
# ======================================================================
class PayrollConfiguration(Base, AuditableBase):
    """The organization's payroll rulebook, one row.

    Weekly offs are stored here and holidays are not: holiday calendars
    already exist in the workforce module, so this row points at one rather
    than growing a second holiday system.
    """

    __tablename__ = "payroll_configurations"
    __table_args__ = (
        # The classic singleton lock: a constant column with a UNIQUE on it.
        # Two live configurations cannot exist however the requests race.
        UniqueConstraint("singleton", name="uq_payroll_configurations_singleton"),
        CheckConstraint("singleton", name="singleton_true"),
        CheckConstraint(f"pay_frequency IN ({PAY_FREQUENCY_SQL_VALUES})", name="pay_frequency"),
        CheckConstraint("period_start_day BETWEEN 1 AND 28", name="period_start_day_range"),
        CheckConstraint("period_end_day BETWEEN 1 AND 31", name="period_end_day_range"),
        CheckConstraint("pay_day BETWEEN 1 AND 31", name="pay_day_range"),
        CheckConstraint("cutoff_day BETWEEN 1 AND 28", name="cutoff_day_range"),
        CheckConstraint("char_length(currency) = 3", name="currency_iso"),
        CheckConstraint(f"working_days_rule IN ({WORKING_DAYS_RULE_SQL_VALUES})", name="working_days_rule"),
        CheckConstraint(f"proration_basis IN ({PAYROLL_DAY_BASIS_SQL_VALUES})", name="proration_basis"),
        CheckConstraint(
            f"unpaid_leave_treatment IN ({UNPAID_LEAVE_TREATMENT_SQL_VALUES})",
            name="unpaid_leave_treatment",
        ),
        CheckConstraint(f"unpaid_leave_basis IN ({PAYROLL_DAY_BASIS_SQL_VALUES})", name="unpaid_leave_basis"),
        CheckConstraint(f"overtime_basis IN ({PERCENTAGE_BASIS_SQL_VALUES})", name="overtime_basis"),
        CheckConstraint("overtime_multiplier > 0", name="overtime_multiplier_positive"),
        CheckConstraint("overtime_min_hours >= 0", name="overtime_min_hours_non_negative"),
        CheckConstraint(
            "overtime_max_hours IS NULL OR overtime_max_hours >= overtime_min_hours",
            name="overtime_window_ordered",
        ),
        CheckConstraint(f"rounding_rule IN ({ROUNDING_RULE_SQL_VALUES})", name="rounding_rule"),
        CheckConstraint(
            "rounding_rule <> 'custom' OR (rounding_precision IS NOT NULL AND rounding_precision > 0)",
            name="custom_rounding_has_precision",
        ),
        CheckConstraint(
            "standard_daily_hours > 0 AND standard_daily_hours <= 24",
            name="standard_daily_hours_range",
        ),
        {"comment": "The payroll configuration singleton."},
    )

    #: Always true; the UNIQUE above is what makes this row the only one.
    singleton: Mapped[bool] = mapped_column(default=True, server_default="true")

    # -- Schedule ------------------------------------------------------
    pay_frequency: Mapped[str] = mapped_column(
        String(20), default=PayFrequency.MONTHLY, server_default=PayFrequency.MONTHLY.value
    )
    #: Day-of-month fields. Capped at 28 where a value must exist in every
    #: month; end and pay days allow 29-31, read as "or the month's last day".
    period_start_day: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    period_end_day: Mapped[int] = mapped_column(Integer, default=31, server_default="31")
    pay_day: Mapped[int] = mapped_column(Integer, default=31, server_default="31")
    cutoff_day: Mapped[int] = mapped_column(Integer, default=25, server_default="25")
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")

    # -- Working days ----------------------------------------------------
    working_days_rule: Mapped[str] = mapped_column(
        String(30), default=WorkingDaysRule.WORKING_DAYS, server_default=WorkingDaysRule.WORKING_DAYS.value
    )
    #: ISO weekday numbers, 0=Monday .. 6=Sunday. JSONB like every other
    #: small list in the platform; validated to 0-6 by the service.
    weekly_off_days: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[5, 6]")
    #: The existing holiday system, referenced rather than duplicated.
    holiday_calendar_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("holiday_calendars.id", ondelete="SET NULL")
    )

    # -- Proration and unpaid leave ---------------------------------------
    proration_basis: Mapped[str] = mapped_column(
        String(20), default=PayrollDayBasis.CALENDAR_DAYS, server_default=PayrollDayBasis.CALENDAR_DAYS.value
    )
    unpaid_leave_treatment: Mapped[str] = mapped_column(
        String(20), default=UnpaidLeaveTreatment.DEDUCT, server_default=UnpaidLeaveTreatment.DEDUCT.value
    )
    unpaid_leave_basis: Mapped[str] = mapped_column(
        String(20), default=PayrollDayBasis.CALENDAR_DAYS, server_default=PayrollDayBasis.CALENDAR_DAYS.value
    )

    # -- Overtime --------------------------------------------------------
    overtime_enabled: Mapped[bool] = mapped_column(default=False, server_default="false")
    overtime_basis: Mapped[str] = mapped_column(
        String(20), default=PercentageBasis.BASIC, server_default=PercentageBasis.BASIC.value
    )
    #: How many hours one working day represents when a monthly amount is
    #: turned into an hourly rate. Configuration, not an assumption baked
    #: into the engine — which is why it lives here and not in a constant.
    standard_daily_hours: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("8.00"), server_default="8.00"
    )
    overtime_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("1.50"), server_default="1.50"
    )
    overtime_min_hours: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("1.00"), server_default="1.00"
    )
    overtime_max_hours: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    overtime_approval_required: Mapped[bool] = mapped_column(default=True, server_default="true")

    # -- Attendance --------------------------------------------------------
    #
    # Settings over the existing attendance module, never a second register.
    # There is no "include overtime" flag here on purpose: overtime inclusion
    # is overtime_enabled above, and two switches for one fact will disagree.
    deduct_absence: Mapped[bool] = mapped_column(default=True, server_default="true")
    deduct_late_arrival: Mapped[bool] = mapped_column(default=False, server_default="false")
    deduct_early_exit: Mapped[bool] = mapped_column(default=False, server_default="false")
    require_approved_attendance: Mapped[bool] = mapped_column(default=True, server_default="true")

    # -- Rounding ----------------------------------------------------------
    rounding_rule: Mapped[str] = mapped_column(
        String(20), default=RoundingRule.NONE, server_default=RoundingRule.NONE.value
    )
    rounding_precision: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    holiday_calendar: Mapped[HolidayCalendar | None] = relationship(lazy="joined")


class PayrollConfigurationHistory(Base, AuditableBase):
    """One field of the configuration changing, append-only.

    A row per changed field rather than a serialized before/after blob,
    because the question actually asked is "when did the rounding rule
    change, from what, and why" — and a blob answers it only after somebody
    writes a diff tool. No endpoint updates or deletes a row here.
    """

    __tablename__ = "payroll_configuration_history"
    __table_args__ = (
        Index("ix_payroll_configuration_history_field_created", "field", "created_at"),
        {"comment": "Append-only payroll configuration change history."},
    )

    configuration_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_configurations.id", ondelete="CASCADE"), index=True
    )
    field: Mapped[str] = mapped_column(String(60), index=True)
    previous_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    effective_from: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    changed_by: Mapped[User | None] = relationship(foreign_keys=[changed_by_id], lazy="joined")


class PayrollPeriod(Base, AuditableBase):
    """One span of dates a future payroll run will cover.

    This phase creates and manages periods; nothing runs one. Status moves
    only along ``PAYROLL_PERIOD_TRANSITIONS``, dates are editable only while
    the period is open, and the service refuses a period whose dates overlap
    any non-cancelled one.
    """

    __tablename__ = "payroll_periods"
    __table_args__ = (
        Index("uq_payroll_periods_name_ci", text("lower(name)"), unique=True),
        Index("ix_payroll_periods_window", "start_date", "end_date"),
        CheckConstraint(f"status IN ({PAYROLL_PERIOD_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint("end_date >= start_date", name="window_ordered"),
        CheckConstraint("pay_date >= start_date", name="pay_date_after_start"),
        {"comment": "Payroll periods; the calculation engine of a later phase runs against one."},
    )

    name: Mapped[str] = mapped_column(String(60), index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date)
    pay_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(20),
        default=PayrollPeriodStatus.OPEN,
        server_default=PayrollPeriodStatus.OPEN.value,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)


class PayrollLeaveRule(Base, AuditableBase):
    """How one existing leave type behaves in payroll.

    References the workforce module's leave types rather than naming leaves —
    "Do not hardcode leave names" is satisfied by there being no name column
    to hardcode into. One rule per leave type; the deduction basis exists
    only for unpaid treatment, and the CHECK below keeps the pair coherent.
    """

    __tablename__ = "payroll_leave_rules"
    __table_args__ = (
        UniqueConstraint("leave_type_id", name="uq_payroll_leave_rules_leave_type"),
        CheckConstraint(f"treatment IN ({LEAVE_TREATMENT_SQL_VALUES})", name="treatment"),
        CheckConstraint(
            f"deduction_basis IS NULL OR deduction_basis IN ({PAYROLL_DAY_BASIS_SQL_VALUES})",
            name="deduction_basis",
        ),
        CheckConstraint("treatment <> 'unpaid' OR deduction_basis IS NOT NULL", name="unpaid_has_basis"),
        CheckConstraint("treatment <> 'paid' OR deduction_basis IS NULL", name="paid_has_no_basis"),
        CheckConstraint(f"status IN ({RECORD_STATUS_SQL_VALUES})", name="status"),
        {"comment": "Payroll treatment of each leave type."},
    )

    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("leave_types.id", ondelete="RESTRICT"), index=True
    )
    treatment: Mapped[str] = mapped_column(String(20))
    deduction_basis: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), default=RecordStatus.ACTIVE, server_default=RecordStatus.ACTIVE.value, index=True
    )

    leave_type: Mapped[LeaveType] = relationship(lazy="joined")


class PayrollEmployeeSetting(Base, AuditableBase):
    """Per-employee payroll settings and eligibility.

    A row exists only where somebody decided something: absence of a row
    means "not configured", never "eligible by default" — the brief is
    explicit that eligibility is not assumed. Overrides are NULL-means-follow:
    a NULL overtime flag defers to the global configuration rather than
    duplicating its value here.

    Deliberately carries no money: the salary is the Phase 1 compensation
    record, referenced by employee rather than copied.
    """

    __tablename__ = "payroll_employee_settings"
    __table_args__ = (
        UniqueConstraint("employee_id", name="uq_payroll_employee_settings_employee"),
        CheckConstraint(f"eligibility IN ({PAYROLL_ELIGIBILITY_SQL_VALUES})", name="eligibility"),
        CheckConstraint(
            "eligibility_reason IS NULL OR eligibility_reason IN "
            f"({PAYROLL_ELIGIBILITY_REASON_SQL_VALUES})",
            name="eligibility_reason",
        ),
        CheckConstraint(
            f"frequency_override IS NULL OR frequency_override IN ({PAY_FREQUENCY_SQL_VALUES})",
            name="frequency_override",
        ),
        CheckConstraint(
            f"proration_override IS NULL OR proration_override IN ({PAYROLL_DAY_BASIS_SQL_VALUES})",
            name="proration_override",
        ),
        {"comment": "Per-employee payroll settings; absence of a row means not configured."},
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    eligibility: Mapped[str] = mapped_column(
        String(20), default=PayrollEligibility.ELIGIBLE, server_default=PayrollEligibility.ELIGIBLE.value
    )
    eligibility_reason: Mapped[str | None] = mapped_column(String(30))
    frequency_override: Mapped[str | None] = mapped_column(String(20))
    proration_override: Mapped[str | None] = mapped_column(String(20))
    #: NULL means "follow the global configuration".
    overtime_eligible: Mapped[bool | None] = mapped_column()
    unpaid_leave_deduction: Mapped[bool | None] = mapped_column()
    payroll_effective_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    employee: Mapped[Employee] = relationship(lazy="joined")


# ======================================================================
# Phase 3 — payroll inputs
#
# The bridge between the source modules and the future calculation engine:
# for one period and one employee, what the attendance, leave and overtime
# records *said* at a known moment. Input data only — no amount on any row
# is money, and nothing here writes back into the modules it reads.
#
# The snapshot discipline is three parts: the summary row (counts), the
# source lines (which records were consumed, and their updated_at at the
# time), and a fingerprint the change detector can recompute cheaply. When
# the sources move after preparation, the input flips to requires_review
# rather than silently feeding stale numbers to a later phase.
# ======================================================================
class PayrollInput(Base, AuditableBase):
    """One employee's prepared payroll input for one period."""

    __tablename__ = "payroll_inputs"
    __table_args__ = (
        UniqueConstraint("payroll_period_id", "employee_id", name="uq_payroll_inputs_period_employee"),
        Index("ix_payroll_inputs_period_status", "payroll_period_id", "status"),
        CheckConstraint(f"status IN ({PAYROLL_INPUT_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint(f"eligibility IN ({PAYROLL_ELIGIBILITY_SQL_VALUES})", name="eligibility"),
        CheckConstraint(
            "unpaid_leave_basis IS NULL OR unpaid_leave_basis IN " f"({PAYROLL_DAY_BASIS_SQL_VALUES})",
            name="unpaid_leave_basis",
        ),
        CheckConstraint("calendar_days >= 0", name="calendar_days_non_negative"),
        CheckConstraint("working_days >= 0", name="working_days_non_negative"),
        CheckConstraint("eligible_days >= 0", name="eligible_days_non_negative"),
        CheckConstraint("overtime_hours >= 0", name="overtime_hours_non_negative"),
        {"comment": "Prepared payroll inputs, one row per period and employee."},
    )

    payroll_period_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_periods.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=PayrollInputStatus.READY,
        server_default=PayrollInputStatus.READY.value,
        index=True,
    )

    # -- Eligibility, joiner/leaver window -------------------------------
    eligibility: Mapped[str] = mapped_column(String(20))
    exclusion_reason: Mapped[str | None] = mapped_column(String(200))
    joining_date: Mapped[date | None] = mapped_column(Date)
    exit_date: Mapped[date | None] = mapped_column(Date)
    offboarding_status: Mapped[str | None] = mapped_column(String(30))
    eligible_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    non_eligible_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    proration_required: Mapped[bool] = mapped_column(default=False, server_default="false")

    # -- Working-day arithmetic (period-wide, from the Phase 2 config) ----
    calendar_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    working_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    weekly_off_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    holiday_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # -- Attendance (approved data, read-only) ----------------------------
    present_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    half_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    absent_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    late_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    early_exit_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # -- Leave (approved requests only) ------------------------------------
    paid_leave_days: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=0, server_default="0")
    unpaid_leave_days: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=0, server_default="0")
    #: Whether unpaid leave deducts for THIS employee (override or global),
    #: and against which day basis. Input facts for the engine, not amounts.
    unpaid_leave_deduction: Mapped[bool] = mapped_column(default=True, server_default="true")
    unpaid_leave_basis: Mapped[str | None] = mapped_column(String(20))

    # -- Overtime ------------------------------------------------------------
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, server_default="0")
    approved_overtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, server_default="0")
    pending_overtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, server_default="0")
    overtime_eligible: Mapped[bool] = mapped_column(default=False, server_default="false")

    # -- Snapshot bookkeeping --------------------------------------------------
    exception_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: SHA-256 over the source record ids and updated_at stamps. The change
    #: detector recomputes it; a difference means the modules moved on.
    source_fingerprint: Mapped[str] = mapped_column(String(64), default="", server_default="")
    source_changed: Mapped[bool] = mapped_column(default=False, server_default="false")
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    prepared_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)

    employee: Mapped[Employee] = relationship(lazy="joined")
    period: Mapped[PayrollPeriod] = relationship(lazy="joined")
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id], lazy="joined")
    exceptions: Mapped[list[PayrollInputException]] = relationship(
        back_populates="input",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="PayrollInputException.created_at",
    )


class PayrollInputException(Base, AuditableBase):
    """One payroll-impacting issue found while preparing an input.

    A flag, never a fix: the brief is explicit that payroll must not modify
    attendance, leave or overtime records, so the only write an exception
    causes is the input's own status turning ``requires_review``.
    """

    __tablename__ = "payroll_input_exceptions"
    __table_args__ = (
        CheckConstraint(f"category IN ({PAYROLL_EXCEPTION_CATEGORY_SQL_VALUES})", name="category"),
        Index("ix_payroll_input_exceptions_input_category", "input_id", "category"),
        {"comment": "Payroll-impacting issues flagged during input preparation."},
    )

    input_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_inputs.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(20))
    code: Mapped[str] = mapped_column(String(60), index=True)
    message: Mapped[str] = mapped_column(String(400))
    #: The record the issue is about, referenced polymorphically — no FK,
    #: because the source may be corrected or removed by its own module.
    source_type: Mapped[str | None] = mapped_column(String(30))
    source_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    occurred_on: Mapped[date | None] = mapped_column(Date)

    input: Mapped[PayrollInput] = relationship(back_populates="exceptions")


class PayrollInputSource(Base, AuditableBase):
    """One source record a payroll input consumed, at a known version.

    The "what data was used" half of the snapshot: the id of the attendance,
    regularization or leave record together with its ``updated_at`` at
    preparation time. No content is copied — the source module keeps owning
    its rows — but a later question about a payroll number can always be
    answered by naming exactly which records fed it.
    """

    __tablename__ = "payroll_input_sources"
    __table_args__ = (
        UniqueConstraint("input_id", "source_type", "source_id", name="uq_payroll_input_sources_line"),
        CheckConstraint(f"source_type IN ({PAYROLL_SOURCE_TYPE_SQL_VALUES})", name="source_type"),
        {"comment": "Which source records fed one payroll input, and at what version."},
    )

    input_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_inputs.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ======================================================================
# Phase 4 — the calculation engine's records
#
# A run belongs to one period, and the engine's output is stored as a full
# breakdown: one record per employee, one line per component/overtime/unpaid
# deduction, each carrying the basis it was computed on. Never only a final
# number — a net pay whose derivation cannot be read back is a dispute the
# organization loses.
# ======================================================================
PAYROLL_RUN_CODE_SEQUENCE = "payroll_runs_code_seq"
PAYROLL_RUN_CODE_DEFAULT = f"'PRUN-' || lpad(nextval('{PAYROLL_RUN_CODE_SEQUENCE}')::text, 6, '0')"


class PayrollRun(Base, AuditableBase):
    """One execution context of the calculation engine for one period.

    Exactly one run per period: recalculation replaces the run's records
    rather than growing a second run, which is what keeps "the August
    payroll" a single answerable thing.
    """

    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("payroll_period_id", name="uq_payroll_runs_period"),
        CheckConstraint(f"status IN ({PAYROLL_RUN_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint("total_gross >= 0", name="total_gross_non_negative"),
        CheckConstraint("total_deductions >= 0", name="total_deductions_non_negative"),
        {"comment": "Payroll runs, one per period."},
    )

    run_code: Mapped[str] = mapped_column(
        String(20), unique=True, server_default=text(PAYROLL_RUN_CODE_DEFAULT)
    )
    payroll_period_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_periods.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=PayrollRunStatus.DRAFT,
        server_default=PayrollRunStatus.DRAFT.value,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")

    employee_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    calculated_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    review_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    excluded_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_gross: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), server_default="0")
    total_deductions: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), default=Decimal("0"), server_default="0"
    )
    total_net: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), server_default="0")

    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    calculated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    # -- Approval workflow (Phase 6). Each milestone keeps its actor and
    # -- moment on the run for direct display; the append-only
    # -- ``payroll_approvals`` trail keeps the full history of cycles.
    review_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_completed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approval_comment: Mapped[str | None] = mapped_column(String(400))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    return_reason: Mapped[str | None] = mapped_column(String(400))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    period: Mapped[PayrollPeriod] = relationship(lazy="joined")
    calculated_by: Mapped[User | None] = relationship(foreign_keys=[calculated_by_id], lazy="joined")
    review_completed_by: Mapped[User | None] = relationship(
        foreign_keys=[review_completed_by_id], lazy="joined"
    )
    submitted_by: Mapped[User | None] = relationship(foreign_keys=[submitted_by_id], lazy="joined")
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_id], lazy="joined")
    returned_by: Mapped[User | None] = relationship(foreign_keys=[returned_by_id], lazy="joined")
    finalized_by: Mapped[User | None] = relationship(foreign_keys=[finalized_by_id], lazy="joined")


class PayrollEmployeeRecord(Base, AuditableBase):
    """One employee's calculated payroll within one run.

    Self-contained on purpose: the day counts it was computed from are copied
    here, because the payroll input it references may be prepared again later
    and this record must keep meaning what it meant when it was calculated.
    """

    __tablename__ = "payroll_employee_records"
    __table_args__ = (
        UniqueConstraint("run_id", "employee_id", name="uq_payroll_employee_records_run_employee"),
        Index("ix_payroll_employee_records_run_status", "run_id", "status"),
        CheckConstraint(f"status IN ({PAYROLL_RECORD_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint("gross_earnings >= 0", name="gross_non_negative"),
        CheckConstraint("total_deductions >= 0", name="deductions_non_negative"),
        {"comment": "Per-employee calculated payroll records."},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    #: The snapshot consumed, and the salary record that applied at the end
    #: of the eligible window. A mid-period revision contributes through the
    #: line items' segment maths; this pointer names the record in force last.
    payroll_input_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_inputs.id", ondelete="SET NULL")
    )
    compensation_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employee_compensation.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(String(20), index=True)
    exception_reason: Mapped[str | None] = mapped_column(String(400))
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")

    gross_earnings: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), server_default="0")
    total_deductions: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default="0"
    )
    net_pay: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), server_default="0")

    # -- Review adjustments (Phase 5) -------------------------------------
    #
    # Sums of the ACTIVE adjustments against this record, maintained by the
    # review service whenever one is created or cancelled. The original
    # columns above are never touched: final pay is derived as
    # gross + adjustment_earnings, deductions + adjustment_deductions.
    adjustment_earnings: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default="0"
    )
    adjustment_deductions: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default="0"
    )

    # -- The facts the amounts were computed from ------------------------
    calendar_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    working_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    eligible_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    present_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    paid_leave_days: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("0"), server_default="0")
    unpaid_leave_days: Mapped[Decimal] = mapped_column(
        Numeric(5, 1), default=Decimal("0"), server_default="0"
    )
    overtime_hours_paid: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("0"), server_default="0"
    )
    proration_basis: Mapped[str | None] = mapped_column(String(20))

    employee: Mapped[Employee] = relationship(lazy="joined")
    run: Mapped[PayrollRun] = relationship(lazy="joined")
    line_items: Mapped[list[PayrollLineItem]] = relationship(
        back_populates="record",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="PayrollLineItem.sort_order",
    )


class PayrollLineItem(Base, AuditableBase):
    """One earning or deduction inside one calculated record.

    ``calculation_basis`` is the human-readable derivation ("40% of basic",
    "15/31 calendar days", "2.00h x 1.5 x 163.04/h") — stored, because the
    question a payslip dispute asks is not "what" but "how".
    """

    __tablename__ = "payroll_line_items"
    __table_args__ = (
        Index("ix_payroll_line_items_record_type", "record_id", "item_type"),
        CheckConstraint(f"item_type IN ({PAYROLL_ITEM_TYPE_SQL_VALUES})", name="item_type"),
        CheckConstraint(f"source IN ({PAYROLL_LINE_SOURCE_SQL_VALUES})", name="source"),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        {"comment": "Component-level payroll lines."},
    )

    record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_employee_records.id", ondelete="CASCADE"), index=True
    )
    item_type: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20))
    #: The component master behind the line, when there is one. Overtime and
    #: the unpaid-leave deduction are engine lines with no master row.
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("salary_components.id", ondelete="SET NULL")
    )
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(120))
    calculation_basis: Mapped[str] = mapped_column(String(200))
    #: The full-period amount before proration, when proration applied.
    original_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    prorated: Mapped[bool] = mapped_column(default=False, server_default="false")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    record: Mapped[PayrollEmployeeRecord] = relationship(back_populates="line_items")


# ======================================================================
# Phase 5 — payroll review
#
# Review is the phase where humans change what payroll will pay, so every
# artefact here is deliberately durable: exceptions are resolved, never
# deleted; adjustments are cancelled, never deleted; comments are append-only;
# and the checklist stores who ticked what. The originals stay untouched —
# an adjustment is an additive row beside the calculation, not an edit to it.
# ======================================================================
class PayrollRunException(Base, AuditableBase):
    """One payroll-impacting issue on one employee within one run.

    Generated by the calculation engine from the input snapshot and its own
    refusals; regenerated on recalculation, with resolutions carried over
    when the same issue reappears unchanged. ``critical`` severity blocks
    review completion until resolved or deliberately waived.
    """

    __tablename__ = "payroll_run_exceptions"
    __table_args__ = (
        Index("ix_payroll_run_exceptions_run_status", "run_id", "status"),
        CheckConstraint(
            f"exception_type IN ({PAYROLL_RUN_EXCEPTION_TYPE_SQL_VALUES})", name="exception_type"
        ),
        CheckConstraint(f"severity IN ({PAYROLL_EXCEPTION_SEVERITY_SQL_VALUES})", name="severity"),
        CheckConstraint(f"status IN ({PAYROLL_EXCEPTION_STATUS_SQL_VALUES})", name="status"),
        {"comment": "Reviewable payroll exceptions, one per issue per employee per run."},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    exception_type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    description: Mapped[str] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(
        String(20),
        default=PayrollExceptionStatus.OPEN,
        server_default=PayrollExceptionStatus.OPEN.value,
        index=True,
    )
    resolution: Mapped[str | None] = mapped_column(String(200))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    employee: Mapped[Employee] = relationship(lazy="joined")
    resolved_by: Mapped[User | None] = relationship(foreign_keys=[resolved_by_id], lazy="joined")


class PayrollAdjustment(Base, AuditableBase):
    """One controlled, additive change to one employee's pay in one run.

    Keyed by run and employee rather than by record, because recalculation
    rebuilds records and an adjustment must survive it — the engine re-applies
    the active adjustments after every rebuild. ``previous_net``/``new_net``
    freeze what the adjustment did at the moment it was made.
    """

    __tablename__ = "payroll_adjustments"
    __table_args__ = (
        Index("ix_payroll_adjustments_run_employee", "run_id", "employee_id"),
        CheckConstraint(f"item_type IN ({PAYROLL_ITEM_TYPE_SQL_VALUES})", name="item_type"),
        CheckConstraint(f"status IN ({PAYROLL_ADJUSTMENT_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint("amount > 0", name="amount_positive"),
        {"comment": "Additive payroll adjustments; cancelled, never deleted."},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    item_type: Mapped[str] = mapped_column(String(20))
    #: Optional link to a component master; a free-named adjustment ("Diwali
    #: bonus") carries only its name.
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("salary_components.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    reason: Mapped[str] = mapped_column(String(400))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20),
        default=PayrollAdjustmentStatus.ACTIVE,
        server_default=PayrollAdjustmentStatus.ACTIVE.value,
        index=True,
    )
    previous_net: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), server_default="0")
    new_net: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), server_default="0")
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(400))

    employee: Mapped[Employee] = relationship(lazy="joined")


class PayrollReviewChecklist(Base, AuditableBase):
    """One checklist item on one run's review.

    Seeded from ``DEFAULT_REVIEW_CHECKLIST`` on first access, so the gate in
    review completion and the screen always agree on what "all items" means.
    Recalculation resets completion — the numbers the reviewer ticked off no
    longer exist.
    """

    __tablename__ = "payroll_review_checklists"
    __table_args__ = (
        UniqueConstraint("run_id", "item_key", name="uq_payroll_review_checklists_run_item"),
        {"comment": "Per-run review checklist items."},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True
    )
    item_key: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(200))
    completed: Mapped[bool] = mapped_column(default=False, server_default="false")
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    completed_by: Mapped[User | None] = relationship(foreign_keys=[completed_by_id], lazy="joined")


class PayrollReviewComment(Base, AuditableBase):
    """One reviewer remark on a run, or on one employee within it.

    Append-only: there is no update or delete endpoint, because a review
    conversation whose past can be rewritten is not a record of the review.
    """

    __tablename__ = "payroll_review_comments"
    __table_args__ = (
        Index("ix_payroll_review_comments_run_created", "run_id", "created_at"),
        {"comment": "Append-only payroll review comments."},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    comment: Mapped[str] = mapped_column(Text)

    employee: Mapped[Employee | None] = relationship(lazy="joined")


class PayrollApproval(Base, AuditableBase):
    """One step of a run's approval trail (Phase 6).

    Append-only, one row per submit, approval, send-back or finalization —
    with the actor, the comment or reason, and the run's headline figures as
    they stood at that moment. A run that cycles through several corrections
    keeps every cycle; nothing here is ever updated or deleted.
    """

    __tablename__ = "payroll_approvals"
    __table_args__ = (
        Index("ix_payroll_approvals_run_created", "run_id", "created_at"),
        CheckConstraint(f"action IN ({PAYROLL_APPROVAL_ACTION_SQL_VALUES})", name="action"),
        {"comment": "Append-only payroll approval trail."},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(20), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    comment: Mapped[str | None] = mapped_column(String(400))
    #: The figures the actor was looking at, frozen into the trail.
    employee_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_gross: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), server_default="0")
    total_deductions: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), default=Decimal("0"), server_default="0"
    )
    total_net: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), server_default="0")

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_id], lazy="joined")


class PayrollFinalSnapshot(Base, AuditableBase):
    """The immutable per-employee record of a finalized payroll (Phase 6).

    Deliberately denormalized: employee name and code, period dates,
    structure name, every line item and adjustment are copied in as plain
    values, because this row must keep saying what was paid even after the
    employee is renamed, the salary revised, or the structure retired. There
    is no update or delete path — a later correction is a new, controlled
    process in a later phase, never an edit here.
    """

    __tablename__ = "payroll_final_snapshots"
    __table_args__ = (
        UniqueConstraint("run_id", "employee_id", name="uq_payroll_final_snapshots_run_employee"),
        CheckConstraint(f"status IN ({PAYROLL_RECORD_STATUS_SQL_VALUES})", name="status"),
        {"comment": "Immutable per-employee snapshots of finalized payroll."},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="RESTRICT"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    #: Identity as of finalization — survives later renames.
    employee_code: Mapped[str] = mapped_column(String(20))
    employee_name: Mapped[str] = mapped_column(String(200))

    period_name: Mapped[str] = mapped_column(String(120))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    pay_date: Mapped[date] = mapped_column(Date)

    status: Mapped[str] = mapped_column(String(20))
    exception_reason: Mapped[str | None] = mapped_column(String(400))
    currency: Mapped[str] = mapped_column(String(3))
    structure_name: Mapped[str | None] = mapped_column(String(150))
    monthly_basic: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    monthly_gross: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    annual_ctc: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    gross_earnings: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), server_default="0")
    total_deductions: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default="0"
    )
    net_pay: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), server_default="0")
    adjustment_earnings: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default="0"
    )
    adjustment_deductions: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default="0"
    )
    final_gross: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), server_default="0")
    final_deductions: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default="0"
    )
    final_net: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), server_default="0")

    #: The full derivation, copied as plain JSON: line items with their
    #: calculation bases, and every adjustment with its reason and status.
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    adjustments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    #: Sign-off as of finalization, denormalized like everything else.
    approved_by_name: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by_name: Mapped[str | None] = mapped_column(String(200))
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    employee: Mapped[Employee] = relationship(lazy="joined")


class Payslip(Base, AuditableBase):
    """One employee's official payslip for one finalized run (Phase 7).

    A payslip is a *document over* the final snapshot, never a second copy
    of the truth: it points at the snapshot it was rendered from, and the
    figures stored here are the snapshot's figures, kept for cheap listing.
    Regeneration replaces the PDF file only; the number and every amount are
    immutable because the snapshot is.
    """

    __tablename__ = "payslips"
    __table_args__ = (
        UniqueConstraint("run_id", "employee_id", name="uq_payslips_run_employee"),
        CheckConstraint(f"status IN ({PAYSLIP_STATUS_SQL_VALUES})", name="status"),
        {"comment": "Official payslips rendered from finalized payroll snapshots."},
    )

    payslip_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="RESTRICT"), index=True
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_employee_records.id", ondelete="RESTRICT")
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_final_snapshots.id", ondelete="RESTRICT")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_periods.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=PayslipStatus.GENERATED, server_default=PayslipStatus.GENERATED.value
    )
    currency: Mapped[str] = mapped_column(String(3))
    gross_earnings: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_deductions: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    net_pay: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    regenerated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    regenerated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    #: Storage handle of the rendered PDF. Opaque; never shown to a user.
    pdf_key: Mapped[str] = mapped_column(String(512))
    pdf_size: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pdf_checksum: Mapped[str | None] = mapped_column(String(64))

    # ``selectin`` for the snapshot and the run on purpose: each of them
    # eagerly joins a wide graph of its own (the snapshot its employee, the
    # run its period and every sign-off user), and joining all of it into one
    # statement alongside the employee's own joins exceeds PostgreSQL's
    # column limit. Two small follow-up queries instead.
    employee: Mapped[Employee] = relationship(lazy="joined")
    period: Mapped[PayrollPeriod] = relationship(lazy="joined")
    snapshot: Mapped[PayrollFinalSnapshot] = relationship(lazy="selectin")
    run: Mapped[PayrollRun] = relationship(lazy="selectin")
