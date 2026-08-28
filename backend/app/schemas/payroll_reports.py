"""Payroll report schemas (Phase 8).

Reports read finalized payroll by default — the only official numbers —
and every row names the employee it is about, so the route guards decide
who may see it before a single figure is rendered.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.enums import PayrollRunStatus


class PayrollReportKind(StrEnum):
    SUMMARY = "summary"
    MONTHLY = "monthly"
    EARNINGS = "earnings"
    DEDUCTIONS = "deductions"
    OVERTIME = "overtime"
    UNPAID_LEAVE = "unpaid_leave"


class ReportExportFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"


class PayrollReportFilters(BaseModel):
    """Every report takes the same filters; ``status`` defaults to finalized."""

    period_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    team_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None
    status: PayrollRunStatus = PayrollRunStatus.FINALIZED


class ReportExportParams(PayrollReportFilters):
    """The filters plus the file format, as one query model."""

    format: ReportExportFormat = ReportExportFormat.CSV

    def filters(self) -> PayrollReportFilters:
        return PayrollReportFilters.model_validate(self.model_dump(exclude={"format"}))


class PayrollReportSummary(BaseModel):
    employee_count: int
    run_count: int
    gross_payroll: Decimal
    total_deductions: Decimal
    net_payroll: Decimal
    total_adjustments: Decimal
    total_overtime: Decimal
    total_overtime_hours: Decimal
    total_unpaid_leave: Decimal
    total_unpaid_leave_days: Decimal
    #: Employer contributions are not modelled by this application, so the
    #: employer cost is the gross payroll and is labelled as such.
    total_employer_cost: Decimal
    employer_cost_supported: bool = False
    currency: str


class MonthlyReportRow(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    employee_code: str
    department: str | None
    location: str | None
    period_name: str
    period_end: date
    run_status: PayrollRunStatus
    record_status: str
    gross: Decimal
    deductions: Decimal
    adjustments: Decimal
    net_pay: Decimal
    currency: str


class EarningsReportRow(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    employee_code: str
    department: str | None
    period_name: str
    basic_salary: Decimal
    allowances: Decimal
    bonus: Decimal
    overtime: Decimal
    other_earnings: Decimal
    total_gross: Decimal
    currency: str


class DeductionReportRow(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    employee_code: str
    department: str | None
    period_name: str
    component: str
    code: str | None
    amount: Decimal
    currency: str


class OvertimeReportRow(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    employee_code: str
    department: str | None
    period_name: str
    approved_overtime_hours: Decimal
    overtime_amount: Decimal
    currency: str


class UnpaidLeaveReportRow(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    employee_code: str
    department: str | None
    period_name: str
    unpaid_leave_days: Decimal
    deduction_basis: str | None
    deduction_amount: Decimal
    currency: str


class PayrollReport(BaseModel):
    kind: PayrollReportKind
    filters: PayrollReportFilters
    summary: PayrollReportSummary
    monthly: list[MonthlyReportRow] = Field(default_factory=list)
    earnings: list[EarningsReportRow] = Field(default_factory=list)
    deductions: list[DeductionReportRow] = Field(default_factory=list)
    overtime: list[OvertimeReportRow] = Field(default_factory=list)
    unpaid_leave: list[UnpaidLeaveReportRow] = Field(default_factory=list)


__all__ = [
    "DeductionReportRow",
    "EarningsReportRow",
    "MonthlyReportRow",
    "OvertimeReportRow",
    "PayrollReport",
    "PayrollReportFilters",
    "PayrollReportKind",
    "PayrollReportSummary",
    "ReportExportFormat",
    "ReportExportParams",
    "UnpaidLeaveReportRow",
]
