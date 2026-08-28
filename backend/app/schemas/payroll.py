"""Payroll foundation schemas.

Two properties shape this module.

**The employee's view is the same shape as the administrator's.** Unlike
assets, there is nothing about a person's own compensation they must not see —
it is their salary. What separates the audiences is *whose* records a request
reaches, and that is the route guards' job, not a thinner read model's.

**Every money field is validated at the edge.** Non-negative, bounded by what
the columns can hold, two decimal places. A percentage component must carry a
basis and stay within 0-100, a fixed one must not carry a basis — validated
here for the request shape, revalidated in the service against the component
master, and constrained again in PostgreSQL.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    CompensationStatus,
    LeaveTreatment,
    PayFrequency,
    PayrollAdjustmentStatus,
    PayrollApprovalAction,
    PayrollDayBasis,
    PayrollEligibility,
    PayrollEligibilityReason,
    PayrollExceptionCategory,
    PayrollExceptionSeverity,
    PayrollExceptionStatus,
    PayrollInputStatus,
    PayrollItemType,
    PayrollLineSource,
    PayrollPeriodStatus,
    PayrollRecordStatus,
    PayrollRunExceptionType,
    PayrollRunStatus,
    PayrollSourceType,
    PayslipStatus,
    PercentageBasis,
    RecordStatus,
    RoundingRule,
    SalaryCalculationType,
    SalaryComponentType,
    SalaryStructureStatus,
    UnpaidLeaveTreatment,
    WorkingDaysRule,
)
from app.schemas.common import PaginationParams

_MAX_TEXT = 4000
#: Numeric(12,2) holds component values; Numeric(14,2) holds the money totals.
_MAX_COMPONENT_VALUE = Decimal("9999999999.99")
_MAX_MONEY = Decimal("999999999999.99")

_CURRENCY_PATTERN = r"^[A-Z]{3}$"


# ----------------------------------------------------------------------
# Components
# ----------------------------------------------------------------------
class SalaryComponentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    component_type: SalaryComponentType
    calculation_type: SalaryCalculationType
    value: Decimal
    percentage_basis: PercentageBasis | None
    description: str | None
    status: RecordStatus
    # Pay behaviour flags (Phase 2). Read by a later calculation phase.
    proration_allowed: bool
    attendance_impact: bool
    leave_impact: bool
    overtime_eligible: bool
    is_taxable: bool
    created_at: datetime
    updated_at: datetime


class _ComponentRules(BaseModel):
    """The coherence rules a component definition must satisfy."""

    @staticmethod
    def _check(
        calculation_type: SalaryCalculationType | None,
        value: Decimal | None,
        basis: PercentageBasis | None,
    ) -> None:
        if calculation_type == SalaryCalculationType.PERCENTAGE:
            if basis is None:
                raise ValueError("A percentage component must name the base it applies to")
            if value is not None and value > 100:
                raise ValueError("A percentage cannot exceed 100")
        if calculation_type == SalaryCalculationType.FIXED and basis is not None:
            raise ValueError("A fixed amount does not take a percentage base")


class SalaryComponentCreate(_ComponentRules):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    component_type: SalaryComponentType
    calculation_type: SalaryCalculationType
    value: Decimal = Field(ge=0, le=_MAX_COMPONENT_VALUE, decimal_places=2)
    percentage_basis: PercentageBasis | None = None
    description: str | None = Field(default=None, max_length=_MAX_TEXT)
    proration_allowed: bool = True
    attendance_impact: bool = False
    leave_impact: bool = False
    overtime_eligible: bool = False
    is_taxable: bool = True

    @model_validator(mode="after")
    def coherent(self) -> Self:
        self._check(self.calculation_type, self.value, self.percentage_basis)
        return self


class SalaryComponentUpdate(_ComponentRules):
    """Partial update. The final state is revalidated in the service, because
    coherence is a property of the whole row rather than of the fields sent."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    calculation_type: SalaryCalculationType | None = None
    value: Decimal | None = Field(default=None, ge=0, le=_MAX_COMPONENT_VALUE, decimal_places=2)
    percentage_basis: PercentageBasis | None = None
    description: str | None = Field(default=None, max_length=_MAX_TEXT)
    proration_allowed: bool | None = None
    attendance_impact: bool | None = None
    leave_impact: bool | None = None
    overtime_eligible: bool | None = None
    is_taxable: bool | None = None


# ----------------------------------------------------------------------
# Structures
# ----------------------------------------------------------------------
class StructureComponentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    component: SalaryComponentRead
    default_value: Decimal | None


class SalaryStructureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    pay_frequency: PayFrequency
    currency: str
    status: SalaryStructureStatus
    effective_from: date | None
    effective_to: date | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class SalaryStructureDetail(SalaryStructureRead):
    components: list[StructureComponentRead]


class StructureComponentInput(BaseModel):
    component_id: uuid.UUID
    default_value: Decimal | None = Field(default=None, ge=0, le=_MAX_COMPONENT_VALUE, decimal_places=2)


class _StructureWindow(BaseModel):
    @staticmethod
    def _check_window(effective_from: date | None, effective_to: date | None) -> None:
        if effective_from and effective_to and effective_to < effective_from:
            raise ValueError("The effective end date cannot be before the start date")


class SalaryStructureCreate(_StructureWindow):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=_MAX_TEXT)
    pay_frequency: PayFrequency = PayFrequency.MONTHLY
    currency: str = Field(default="INR", pattern=_CURRENCY_PATTERN)
    effective_from: date | None = None
    effective_to: date | None = None
    components: list[StructureComponentInput] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        self._check_window(self.effective_from, self.effective_to)
        seen = {item.component_id for item in self.components}
        if len(seen) != len(self.components):
            raise ValueError("A component appears more than once in this structure")
        return self


class SalaryStructureUpdate(_StructureWindow):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=_MAX_TEXT)
    pay_frequency: PayFrequency | None = None
    currency: str | None = Field(default=None, pattern=_CURRENCY_PATTERN)
    effective_from: date | None = None
    effective_to: date | None = None
    components: list[StructureComponentInput] | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        self._check_window(self.effective_from, self.effective_to)
        if self.components is not None:
            seen = {item.component_id for item in self.components}
            if len(seen) != len(self.components):
                raise ValueError("A component appears more than once in this structure")
        return self


class StructureListParams(PaginationParams):
    search: str | None = Field(default=None, max_length=120)
    status: SalaryStructureStatus | None = None


# ----------------------------------------------------------------------
# Employee compensation
# ----------------------------------------------------------------------
class EmployeeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    full_name: str


class CompensationComponentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    component_id: uuid.UUID
    name: str = Field(description="Resolved from the component master for display.")
    code: str
    component_type: SalaryComponentType
    calculation_type: SalaryCalculationType
    value: Decimal
    percentage_basis: PercentageBasis | None


class CompensationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    structure: SalaryStructureRead
    currency: str
    annual_ctc: Decimal
    annual_gross: Decimal
    monthly_gross: Decimal
    basic_salary: Decimal
    status: CompensationStatus
    effective_from: date
    effective_to: date | None
    components: list[CompensationComponentRead]
    created_at: datetime


class EmployeeCompensationData(BaseModel):
    """Everything one employee's salary screen needs: who, and every period."""

    employee: EmployeeSummary
    current: CompensationRead | None
    records: list[CompensationRead]


class CompensationListRow(BaseModel):
    """One row of the admin payroll register: an employee's current pay."""

    id: uuid.UUID
    employee: EmployeeSummary
    structure_name: str
    currency: str
    annual_ctc: Decimal
    monthly_gross: Decimal
    status: CompensationStatus
    effective_from: date
    effective_to: date | None


class CompensationListParams(PaginationParams):
    search: str | None = Field(default=None, max_length=120)


class CompensationComponentInput(BaseModel):
    """One component's agreed value.

    Only the value is supplied: calculation type and basis are snapshotted
    from the component master by the service, so a client cannot re-express a
    percentage component as a fixed amount by mislabelling it.
    """

    component_id: uuid.UUID
    value: Decimal = Field(ge=0, le=_MAX_COMPONENT_VALUE, decimal_places=2)


class _CompensationMoney(BaseModel):
    currency: str = Field(default="INR", pattern=_CURRENCY_PATTERN)
    annual_ctc: Decimal = Field(gt=0, le=_MAX_MONEY, decimal_places=2)
    annual_gross: Decimal = Field(ge=0, le=_MAX_MONEY, decimal_places=2)
    monthly_gross: Decimal = Field(ge=0, le=_MAX_MONEY, decimal_places=2)
    basic_salary: Decimal = Field(ge=0, le=_MAX_MONEY, decimal_places=2)
    components: list[CompensationComponentInput] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        seen = {item.component_id for item in self.components}
        if len(seen) != len(self.components):
            raise ValueError("A component appears more than once")
        return self


class CompensationAssign(_CompensationMoney):
    salary_structure_id: uuid.UUID
    effective_from: date
    effective_to: date | None = None
    reason: str | None = Field(default=None, max_length=_MAX_TEXT)

    @model_validator(mode="after")
    def window_ordered(self) -> Self:
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("The effective end date cannot be before the start date")
        return self


class SalaryRevision(_CompensationMoney):
    """A revision ends the current record and opens this one.

    The reason is mandatory here and optional on assignment, because a change
    to somebody's pay is a decision with a why, and the history screen's
    Reason column must never be blank for one.
    """

    salary_structure_id: uuid.UUID
    effective_from: date
    reason: str = Field(min_length=3, max_length=_MAX_TEXT)


class SalaryHistoryRead(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    previous_annual_ctc: Decimal | None
    new_annual_ctc: Decimal
    currency: str
    effective_from: date
    reason: str | None
    changed_by_name: str | None
    created_at: datetime


# ======================================================================
# Phase 2 — payroll configuration and pay rules
# ======================================================================
class PayrollConfigRead(BaseModel):
    id: uuid.UUID
    pay_frequency: PayFrequency
    period_start_day: int
    period_end_day: int
    pay_day: int
    cutoff_day: int
    currency: str
    working_days_rule: WorkingDaysRule
    weekly_off_days: list[int]
    holiday_calendar_id: uuid.UUID | None
    holiday_calendar_name: str | None
    proration_basis: PayrollDayBasis
    unpaid_leave_treatment: UnpaidLeaveTreatment
    unpaid_leave_basis: PayrollDayBasis
    overtime_enabled: bool
    overtime_basis: PercentageBasis
    overtime_multiplier: Decimal
    overtime_min_hours: Decimal
    overtime_max_hours: Decimal | None
    overtime_approval_required: bool
    standard_daily_hours: Decimal
    deduct_absence: bool
    deduct_late_arrival: bool
    deduct_early_exit: bool
    require_approved_attendance: bool
    rounding_rule: RoundingRule
    rounding_precision: Decimal | None
    updated_at: datetime


class PayrollConfigUpdate(BaseModel):
    """Partial update of the configuration singleton.

    Every update carries a reason and an effective date, because §13 of the
    brief is explicit: important payroll configuration is never silently
    overwritten. Cross-field coherence (custom rounding needs a precision,
    the overtime window must be ordered) is checked in the service against
    the *final* state, since a partial payload cannot see it.
    """

    pay_frequency: PayFrequency | None = None
    period_start_day: int | None = Field(default=None, ge=1, le=28)
    period_end_day: int | None = Field(default=None, ge=1, le=31)
    pay_day: int | None = Field(default=None, ge=1, le=31)
    cutoff_day: int | None = Field(default=None, ge=1, le=28)
    currency: str | None = Field(default=None, pattern=_CURRENCY_PATTERN)
    working_days_rule: WorkingDaysRule | None = None
    weekly_off_days: list[int] | None = Field(default=None, max_length=7)
    holiday_calendar_id: uuid.UUID | None = None
    #: Explicit detach, because ``holiday_calendar_id=None`` is
    #: indistinguishable from "field not sent" in a partial update.
    clear_holiday_calendar: bool = False
    proration_basis: PayrollDayBasis | None = None
    unpaid_leave_treatment: UnpaidLeaveTreatment | None = None
    unpaid_leave_basis: PayrollDayBasis | None = None
    overtime_enabled: bool | None = None
    overtime_basis: PercentageBasis | None = None
    overtime_multiplier: Decimal | None = Field(default=None, gt=0, le=Decimal("10"), decimal_places=2)
    overtime_min_hours: Decimal | None = Field(default=None, ge=0, le=Decimal("24"), decimal_places=2)
    overtime_max_hours: Decimal | None = Field(default=None, ge=0, le=Decimal("99"), decimal_places=2)
    clear_overtime_max_hours: bool = False
    overtime_approval_required: bool | None = None
    standard_daily_hours: Decimal | None = Field(default=None, gt=0, le=Decimal("24"), decimal_places=2)
    deduct_absence: bool | None = None
    deduct_late_arrival: bool | None = None
    deduct_early_exit: bool | None = None
    require_approved_attendance: bool | None = None
    rounding_rule: RoundingRule | None = None
    rounding_precision: Decimal | None = Field(default=None, gt=0, le=Decimal("1000"), decimal_places=2)

    reason: str = Field(min_length=3, max_length=_MAX_TEXT)
    effective_from: date

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.weekly_off_days is not None:
            if any(day < 0 or day > 6 for day in self.weekly_off_days):
                raise ValueError("Weekly off days are ISO weekday numbers, 0 (Monday) to 6 (Sunday)")
            if len(set(self.weekly_off_days)) != len(self.weekly_off_days):
                raise ValueError("A weekday appears more than once in the weekly off list")
        if self.effective_from < date.today():
            raise ValueError("The effective date cannot be in the past")
        return self


class PayrollConfigHistoryRead(BaseModel):
    id: uuid.UUID
    field: str
    previous_value: str | None
    new_value: str | None
    effective_from: date
    reason: str
    changed_by_name: str | None
    created_at: datetime


# ----------------------------------------------------------------------
# Periods
# ----------------------------------------------------------------------
class PayrollPeriodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    pay_date: date
    status: PayrollPeriodStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime


class _PeriodWindow(BaseModel):
    @staticmethod
    def _check(start: date | None, end: date | None, pay: date | None) -> None:
        if start and end and end < start:
            raise ValueError("The period cannot end before it starts")
        if start and pay and pay < start:
            raise ValueError("The pay date cannot be before the period starts")


class PayrollPeriodCreate(_PeriodWindow):
    name: str = Field(min_length=2, max_length=60)
    start_date: date
    end_date: date
    pay_date: date
    notes: str | None = Field(default=None, max_length=_MAX_TEXT)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        self._check(self.start_date, self.end_date, self.pay_date)
        return self


class PayrollPeriodUpdate(_PeriodWindow):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    start_date: date | None = None
    end_date: date | None = None
    pay_date: date | None = None
    notes: str | None = Field(default=None, max_length=_MAX_TEXT)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        self._check(self.start_date, self.end_date, self.pay_date)
        return self


class PeriodListParams(PaginationParams):
    status: PayrollPeriodStatus | None = None


# ----------------------------------------------------------------------
# Leave rules
# ----------------------------------------------------------------------
class LeaveRuleRead(BaseModel):
    id: uuid.UUID
    leave_type_id: uuid.UUID
    leave_type_name: str
    leave_type_code: str
    #: The leave module's own paid flag, shown for context so a rule that
    #: contradicts it is a visible decision rather than an accident.
    leave_type_is_paid: bool
    treatment: LeaveTreatment
    deduction_basis: PayrollDayBasis | None
    description: str | None
    status: RecordStatus
    updated_at: datetime


class _LeaveRuleRules(BaseModel):
    @staticmethod
    def _check(treatment: LeaveTreatment | None, basis: PayrollDayBasis | None) -> None:
        if treatment == LeaveTreatment.UNPAID and basis is None:
            raise ValueError("An unpaid rule must say which day basis the deduction uses")


class LeaveRuleCreate(_LeaveRuleRules):
    leave_type_id: uuid.UUID
    treatment: LeaveTreatment
    deduction_basis: PayrollDayBasis | None = None
    description: str | None = Field(default=None, max_length=_MAX_TEXT)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        self._check(self.treatment, self.deduction_basis)
        return self


class LeaveRuleUpdate(_LeaveRuleRules):
    treatment: LeaveTreatment | None = None
    deduction_basis: PayrollDayBasis | None = None
    description: str | None = Field(default=None, max_length=_MAX_TEXT)


# ----------------------------------------------------------------------
# Employee payroll settings
# ----------------------------------------------------------------------
class EmployeeSettingsRead(BaseModel):
    id: uuid.UUID
    employee: EmployeeSummary
    eligibility: PayrollEligibility
    eligibility_reason: PayrollEligibilityReason | None
    frequency_override: PayFrequency | None
    proration_override: PayrollDayBasis | None
    overtime_eligible: bool | None
    unpaid_leave_deduction: bool | None
    payroll_effective_date: date | None
    notes: str | None
    updated_at: datetime


class EmployeeSettingsData(BaseModel):
    """One employee's settings screen: who, whether Phase 1 pay exists, and
    the settings row — or None, which means "not configured", never a default."""

    employee: EmployeeSummary
    has_active_compensation: bool
    settings: EmployeeSettingsRead | None


class EmployeeSettingsUpsert(BaseModel):
    eligibility: PayrollEligibility = PayrollEligibility.ELIGIBLE
    eligibility_reason: PayrollEligibilityReason | None = None
    frequency_override: PayFrequency | None = None
    proration_override: PayrollDayBasis | None = None
    #: NULL means "follow the global configuration".
    overtime_eligible: bool | None = None
    unpaid_leave_deduction: bool | None = None
    payroll_effective_date: date | None = None
    notes: str | None = Field(default=None, max_length=_MAX_TEXT)


class EmployeeSettingsListParams(PaginationParams):
    search: str | None = Field(default=None, max_length=120)


# ======================================================================
# Phase 3 — payroll inputs
# ======================================================================
class PayrollExceptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: PayrollExceptionCategory
    code: str
    message: str
    source_type: str | None
    source_id: uuid.UUID | None
    occurred_on: date | None


class PayrollInputSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_type: PayrollSourceType
    source_id: uuid.UUID
    source_updated_at: datetime


class PayrollInputRead(BaseModel):
    """One employee's prepared input for one period. Counts and flags only —
    no field on this model is an amount of money."""

    id: uuid.UUID
    period: PayrollPeriodRead
    employee: EmployeeSummary
    status: PayrollInputStatus
    eligibility: PayrollEligibility
    exclusion_reason: str | None
    joining_date: date | None
    exit_date: date | None
    offboarding_status: str | None
    eligible_days: int
    non_eligible_days: int
    proration_required: bool
    calendar_days: int
    working_days: int
    weekly_off_days: int
    holiday_days: int
    present_days: int
    half_days: int
    absent_days: int
    late_days: int
    early_exit_days: int
    paid_leave_days: Decimal
    unpaid_leave_days: Decimal
    unpaid_leave_deduction: bool
    unpaid_leave_basis: PayrollDayBasis | None
    overtime_hours: Decimal
    approved_overtime_hours: Decimal
    pending_overtime_hours: Decimal
    overtime_eligible: bool
    exception_count: int
    source_changed: bool
    prepared_at: datetime
    reviewed_at: datetime | None
    reviewed_by_name: str | None
    review_note: str | None


class PayrollInputDetail(PayrollInputRead):
    exceptions: list[PayrollExceptionRead]
    sources: list[PayrollInputSourceRead]


class PayrollInputListParams(PaginationParams):
    status: PayrollInputStatus | None = None
    search: str | None = Field(default=None, max_length=120)
    business_unit_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None


class PayrollInputReview(BaseModel):
    note: str | None = Field(default=None, max_length=_MAX_TEXT)


class PayrollInputPrepareResult(BaseModel):
    prepared: int
    ready: int
    requires_review: int
    excluded: int
    removed: int = Field(description="Inputs deleted because their employee left the period's scope.")


class PayrollChangeDetectionResult(BaseModel):
    checked: int
    flagged: int
    flagged_employees: list[EmployeeSummary]


class PeriodExceptionRow(BaseModel):
    """One exception with its employee, for the period-wide exceptions view."""

    employee: EmployeeSummary
    category: PayrollExceptionCategory
    code: str
    message: str
    source_type: str | None
    occurred_on: date | None


# ======================================================================
# Phase 4 — payroll runs and calculated records
# ======================================================================
class PayrollRunRead(BaseModel):
    id: uuid.UUID
    run_code: str
    period: PayrollPeriodRead
    status: PayrollRunStatus
    currency: str
    employee_count: int
    calculated_count: int
    review_count: int
    excluded_count: int
    total_gross: Decimal
    total_deductions: Decimal
    total_net: Decimal
    calculated_at: datetime | None
    calculated_by_name: str | None
    notes: str | None
    created_at: datetime
    #: Review surface (Phase 5): open exceptions, worst first.
    open_exception_count: int = 0
    open_critical_count: int = 0
    #: Approval workflow (Phase 6): each milestone's actor and moment, plus
    #: the count of active adjustments where a listing enriches it.
    review_completed_at: datetime | None = None
    review_completed_by_name: str | None = None
    submitted_at: datetime | None = None
    submitted_by_name: str | None = None
    approved_at: datetime | None = None
    approved_by_name: str | None = None
    approval_comment: str | None = None
    returned_at: datetime | None = None
    returned_by_name: str | None = None
    return_reason: str | None = None
    finalized_at: datetime | None = None
    finalized_by_name: str | None = None
    adjustment_count: int = 0


class PayrollRunCreate(BaseModel):
    payroll_period_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=_MAX_TEXT)


class PayrollRunListParams(PaginationParams):
    status: PayrollRunStatus | None = None


class PayrollLineItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_type: PayrollItemType
    source: PayrollLineSource
    code: str
    name: str
    calculation_basis: str
    original_amount: Decimal | None
    prorated: bool
    amount: Decimal


class PayrollRecordRead(BaseModel):
    """One employee's calculated payroll. Amounts exist only on records whose
    status is ``calculated``; a refused calculation carries its reason and
    zeros, never a guess."""

    id: uuid.UUID
    run_id: uuid.UUID
    employee: EmployeeSummary
    status: PayrollRecordStatus
    exception_reason: str | None
    currency: str
    gross_earnings: Decimal
    total_deductions: Decimal
    net_pay: Decimal
    #: Review adjustments (Phase 5). The original columns above are never
    #: touched; final pay is original plus adjustments, derived here.
    adjustment_earnings: Decimal
    adjustment_deductions: Decimal
    final_gross: Decimal
    final_deductions: Decimal
    final_net: Decimal
    calendar_days: int
    working_days: int
    eligible_days: int
    present_days: int
    paid_leave_days: Decimal
    unpaid_leave_days: Decimal
    overtime_hours_paid: Decimal
    proration_basis: PayrollDayBasis | None


class PayrollAdjustmentRead(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    employee: EmployeeSummary
    item_type: PayrollItemType
    name: str
    amount: Decimal
    reason: str
    notes: str | None
    status: PayrollAdjustmentStatus
    previous_net: Decimal
    new_net: Decimal
    created_at: datetime
    cancelled_at: datetime | None
    cancel_reason: str | None


class PayrollRecordDetail(PayrollRecordRead):
    period: PayrollPeriodRead
    structure_name: str | None
    monthly_basic: Decimal | None
    monthly_gross: Decimal | None
    annual_ctc: Decimal | None
    line_items: list[PayrollLineItemRead]
    adjustments: list[PayrollAdjustmentRead] = Field(default_factory=list)


class PayrollRecordListParams(PaginationParams):
    status: PayrollRecordStatus | None = None
    search: str | None = Field(default=None, max_length=120)


class PayrollCalculationResult(BaseModel):
    run: PayrollRunRead
    calculated: int
    requires_review: int
    excluded: int


# ======================================================================
# Phase 5 — payroll review
# ======================================================================
class PayrollRunExceptionRead(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    employee: EmployeeSummary
    exception_type: PayrollRunExceptionType
    severity: PayrollExceptionSeverity
    description: str
    status: PayrollExceptionStatus
    resolution: str | None
    resolution_notes: str | None
    resolved_by_name: str | None
    resolved_at: datetime | None
    created_at: datetime


class PayrollExceptionResolve(BaseModel):
    resolution: str = Field(min_length=3, max_length=200)
    notes: str | None = Field(default=None, max_length=_MAX_TEXT)


class PayrollAdjustmentCreate(BaseModel):
    item_type: PayrollItemType
    name: str = Field(min_length=2, max_length=120)
    amount: Decimal = Field(gt=0, le=_MAX_MONEY, decimal_places=2)
    reason: str = Field(min_length=3, max_length=400)
    notes: str | None = Field(default=None, max_length=_MAX_TEXT)


class PayrollAdjustmentCancel(BaseModel):
    reason: str = Field(min_length=3, max_length=400)


class PayrollRecordReviewMark(BaseModel):
    status: PayrollRecordStatus
    note: str | None = Field(default=None, max_length=_MAX_TEXT)


class ChecklistItemRead(BaseModel):
    item_key: str
    label: str
    completed: bool
    completed_by_name: str | None
    completed_at: datetime | None


class ChecklistItemUpdate(BaseModel):
    completed: bool


class ReviewCommentRead(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    employee: EmployeeSummary | None
    comment: str
    author_name: str | None
    created_at: datetime


class ReviewCommentCreate(BaseModel):
    comment: str = Field(min_length=1, max_length=_MAX_TEXT)
    employee_id: uuid.UUID | None = None


class ReviewReadiness(BaseModel):
    """Why a run can or cannot complete its review — shown, never guessed."""

    can_complete: bool
    open_critical_exceptions: int
    records_requiring_review: int
    records_adjustment_required: int
    incomplete_checklist_items: list[str]


class PayrollReconciliation(BaseModel):
    run_id: uuid.UUID
    currency: str
    original_gross: Decimal
    adjustment_earnings: Decimal
    final_gross: Decimal
    original_deductions: Decimal
    adjustment_deductions: Decimal
    final_deductions: Decimal
    original_net: Decimal
    net_adjustment: Decimal
    final_net: Decimal
    adjustment_count: int
    cancelled_adjustment_count: int
    total_adjustment_amount: Decimal
    employees_affected: int


class PayrollComparisonRow(BaseModel):
    """One employee's current run versus the previous period's run."""

    employee: EmployeeSummary
    previous_gross: Decimal | None
    current_gross: Decimal
    gross_difference: Decimal | None
    previous_deductions: Decimal | None
    current_deductions: Decimal
    deduction_difference: Decimal | None
    previous_net: Decimal | None
    current_net: Decimal
    net_difference: Decimal | None
    #: True when the net moved by more than the review threshold (or the
    #: employee is new to payroll) — highlighted, never auto-rejected.
    notable: bool


# ======================================================================
# Phase 6 — payroll approval and finalization
# ======================================================================
class PayrollApprovalRead(BaseModel):
    """One step of the append-only approval trail."""

    id: uuid.UUID
    run_id: uuid.UUID
    action: PayrollApprovalAction
    actor_name: str | None
    comment: str | None
    employee_count: int
    total_gross: Decimal
    total_deductions: Decimal
    total_net: Decimal
    created_at: datetime


class PayrollApprovalDecision(BaseModel):
    """The approve act. The comment is mandatory: an approval that cannot
    say why it approved is not a record of a decision."""

    comment: str = Field(min_length=3, max_length=400)


class PayrollReturnRequest(BaseModel):
    """Send a submitted run back for correction, with the reason on record."""

    reason: str = Field(min_length=3, max_length=400)


class PayrollFinalizeRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=400)


class ApprovalEmployeeSummary(BaseModel):
    included: int
    excluded: int
    with_adjustments: int
    with_exceptions: int


class ApprovalReviewSummary(BaseModel):
    review_completed: bool
    reviewer_name: str | None
    critical_exceptions: int
    error_exceptions: int
    warning_exceptions: int
    open_exceptions: int
    adjustment_count: int


class PayrollApprovalSummary(BaseModel):
    """Everything an approver needs on one screen — including, verbatim,
    every reason the run cannot be approved yet."""

    run: PayrollRunRead
    employees: ApprovalEmployeeSummary
    review: ApprovalReviewSummary
    #: Human-readable blockers; empty exactly when ``can_approve`` is true
    #: (state permitting). The backend re-checks on approve regardless.
    blockers: list[str] = Field(default_factory=list)
    can_approve: bool
    trail: list[PayrollApprovalRead] = Field(default_factory=list)


class PayrollSnapshotRead(BaseModel):
    """One employee's immutable finalized payroll."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    period_name: str
    period_start: date
    period_end: date
    pay_date: date
    status: PayrollRecordStatus
    exception_reason: str | None
    currency: str
    structure_name: str | None
    monthly_basic: Decimal | None
    monthly_gross: Decimal | None
    annual_ctc: Decimal | None
    gross_earnings: Decimal
    total_deductions: Decimal
    net_pay: Decimal
    adjustment_earnings: Decimal
    adjustment_deductions: Decimal
    final_gross: Decimal
    final_deductions: Decimal
    final_net: Decimal
    line_items: list[dict[str, Any]]
    adjustments: list[dict[str, Any]]
    approved_by_name: str | None
    approved_at: datetime | None
    finalized_by_name: str | None
    finalized_at: datetime


# ======================================================================
# Phase 7 — payslips
# ======================================================================
class PayslipListParams(PaginationParams):
    """Admin filters. Employees get none of these: /me filters by session."""

    employee_id: uuid.UUID | None = None
    #: ``YYYY-MM`` of the period end — "the August payslips".
    month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    #: Department is the employee's team, as the org chart calls it.
    team_id: uuid.UUID | None = None
    payslip_number: str | None = Field(default=None, max_length=40)
    run_id: uuid.UUID | None = None


class PayslipRead(BaseModel):
    """A payslip in a list: what it is and what it paid, no breakdown."""

    id: uuid.UUID
    payslip_number: str
    run_id: uuid.UUID
    employee: EmployeeSummary
    period: PayrollPeriodRead
    payroll_month: str
    status: PayslipStatus
    currency: str
    gross_earnings: Decimal
    total_deductions: Decimal
    net_pay: Decimal
    generated_at: datetime
    regenerated_at: datetime | None


class PayslipEmployer(BaseModel):
    name: str | None
    address: str | None
    logo_url: str | None


class PayslipEmployee(BaseModel):
    name: str
    employee_code: str
    department: str | None
    designation: str | None
    joining_date: date | None
    #: Bank name and the last four digits only — enough to recognise the
    #: account, never enough to use it.
    bank_name: str | None
    account_masked: str | None


class PayslipLine(BaseModel):
    name: str
    code: str | None
    calculation_basis: str | None
    amount: Decimal


class PayslipDetail(PayslipRead):
    """The complete payslip, exactly as the PDF renders it."""

    employer: PayslipEmployer
    employee_details: PayslipEmployee
    period_start: date
    period_end: date
    pay_date: date
    pay_frequency: PayFrequency
    earnings: list[PayslipLine]
    deductions: list[PayslipLine]
    amount_in_words: str
    generated_by_name: str | None
    structure_name: str | None


class PayslipGenerationResult(BaseModel):
    run_id: uuid.UUID
    generated: int
    already_existed: int
    skipped_excluded: int
    payslips: list[PayslipRead] = Field(default_factory=list)


__all__ = [
    "ApprovalEmployeeSummary",
    "ApprovalReviewSummary",
    "ChecklistItemRead",
    "ChecklistItemUpdate",
    "CompensationAssign",
    "CompensationComponentInput",
    "CompensationComponentRead",
    "CompensationListParams",
    "CompensationListRow",
    "CompensationRead",
    "EmployeeCompensationData",
    "EmployeeSettingsData",
    "EmployeeSettingsListParams",
    "EmployeeSettingsRead",
    "EmployeeSettingsUpsert",
    "EmployeeSummary",
    "LeaveRuleCreate",
    "LeaveRuleRead",
    "LeaveRuleUpdate",
    "PayrollAdjustmentCancel",
    "PayrollAdjustmentCreate",
    "PayrollAdjustmentRead",
    "PayrollApprovalDecision",
    "PayrollApprovalRead",
    "PayrollApprovalSummary",
    "PayrollCalculationResult",
    "PayrollChangeDetectionResult",
    "PayrollComparisonRow",
    "PayrollConfigHistoryRead",
    "PayrollConfigRead",
    "PayrollConfigUpdate",
    "PayrollExceptionRead",
    "PayrollExceptionResolve",
    "PayrollFinalizeRequest",
    "PayrollInputDetail",
    "PayrollInputListParams",
    "PayrollInputPrepareResult",
    "PayrollInputRead",
    "PayrollInputReview",
    "PayrollInputSourceRead",
    "PayrollLineItemRead",
    "PayrollPeriodCreate",
    "PayrollPeriodRead",
    "PayrollPeriodUpdate",
    "PayrollReconciliation",
    "PayrollRecordDetail",
    "PayrollRecordListParams",
    "PayrollRecordRead",
    "PayrollRecordReviewMark",
    "PayrollReturnRequest",
    "PayrollRunCreate",
    "PayrollRunExceptionRead",
    "PayrollRunListParams",
    "PayrollRunRead",
    "PayrollSnapshotRead",
    "PayslipDetail",
    "PayslipEmployee",
    "PayslipEmployer",
    "PayslipGenerationResult",
    "PayslipLine",
    "PayslipListParams",
    "PayslipRead",
    "PeriodExceptionRow",
    "PeriodListParams",
    "ReviewCommentCreate",
    "ReviewCommentRead",
    "ReviewReadiness",
    "SalaryComponentCreate",
    "SalaryComponentRead",
    "SalaryComponentUpdate",
    "SalaryHistoryRead",
    "SalaryRevision",
    "SalaryStructureCreate",
    "SalaryStructureDetail",
    "SalaryStructureRead",
    "SalaryStructureUpdate",
    "StructureComponentInput",
    "StructureComponentRead",
    "StructureListParams",
]
