"""Payroll reports (Phase 8).

Every report is a projection of payroll employee records — by default the
records of *finalized* runs, the only official numbers — joined to the
employee's department and location. Nothing is recomputed: a report row is
the record's own figures and its own line items, classified for display.

Classification is by what the engine recorded, never by assumption: an
overtime line is one the engine sourced from overtime, an unpaid-leave
deduction is one it sourced from unpaid leave, a bonus is an active review
adjustment, and "basic salary" is the earning component whose code or name
says so — everything else an employee earns is an allowance. The report
states that rule rather than hiding it.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from openpyxl import Workbook

from app.models.audit_log import AuditAction
from app.models.enums import PayrollItemType, PayrollLineSource, PayrollRecordStatus, PayrollRunStatus
from app.models.payroll import PayrollAdjustment, PayrollEmployeeRecord
from app.repositories.payroll_settlement_repository import PayrollReportRepository
from app.schemas.payroll_reports import (
    DeductionReportRow,
    EarningsReportRow,
    MonthlyReportRow,
    OvertimeReportRow,
    PayrollReport,
    PayrollReportFilters,
    PayrollReportKind,
    PayrollReportSummary,
    ReportExportFormat,
    UnpaidLeaveReportRow,
)
from app.services.audit_service import AuditService

_ZERO = Decimal("0.00")
_BASIC_MARKERS = ("basic", "bas")


def _is_basic(code: str, name: str) -> bool:
    haystack = f"{code} {name}".lower()
    return any(marker in haystack for marker in _BASIC_MARKERS)


class PayrollReportService:
    def __init__(self, records: PayrollReportRepository, audit: AuditService) -> None:
        self.records = records
        self.audit = audit

    async def report(
        self, kind: PayrollReportKind, filters: PayrollReportFilters, *, actor_id: uuid.UUID
    ) -> PayrollReport:
        report = await self._build(kind, filters)
        await self.audit.record_success(
            AuditAction.PAYROLL_REPORT_GENERATED,
            actor_id=actor_id,
            entity_type="payroll_report",
            entity_id=None,
            description=f"Generated the {kind.value} payroll report",
            context=self._filter_context(filters),
        )
        return report

    async def export(
        self,
        kind: PayrollReportKind,
        filters: PayrollReportFilters,
        fmt: ReportExportFormat,
        *,
        actor_id: uuid.UUID,
    ) -> tuple[bytes, str, str]:
        """(content, media type, filename). CSV, or XLSX through the openpyxl
        approach the asset and employee exports already use."""
        report = await self._build(kind, filters)
        headers, rows = self._tabular(report)
        await self.audit.record_success(
            AuditAction.PAYROLL_REPORT_EXPORTED,
            actor_id=actor_id,
            entity_type="payroll_report",
            entity_id=None,
            description=f"Exported the {kind.value} payroll report as {fmt.value}",
            context={**self._filter_context(filters), "rows": len(rows)},
        )
        filename = f"payroll-{kind.value}.{fmt.value}"
        if fmt == ReportExportFormat.CSV:
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(headers)
            writer.writerows(rows)
            return buffer.getvalue().encode("utf-8-sig"), "text/csv", filename
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = kind.value[:31]
        sheet.append(headers)
        for row in rows:
            sheet.append([str(cell) if isinstance(cell, Decimal) else cell for cell in row])
        stream = io.BytesIO()
        workbook.save(stream)
        return (
            stream.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename,
        )

    # ------------------------------------------------------------------
    async def _build(self, kind: PayrollReportKind, filters: PayrollReportFilters) -> PayrollReport:
        records = [
            r for r in await self.records.records(filters) if r.status != PayrollRecordStatus.EXCLUDED.value
        ]
        adjustments = await self.records.active_adjustments(list({r.run_id for r in records}))
        by_record: dict[tuple[uuid.UUID, uuid.UUID], list[PayrollAdjustment]] = {}
        for adjustment in adjustments:
            by_record.setdefault((adjustment.run_id, adjustment.employee_id), []).append(adjustment)

        report = PayrollReport(kind=kind, filters=filters, summary=self._summary(records, by_record))
        if kind == PayrollReportKind.MONTHLY:
            report.monthly = [self._monthly_row(r, by_record) for r in records]
        elif kind == PayrollReportKind.EARNINGS:
            report.earnings = [self._earnings_row(r, by_record) for r in records]
        elif kind == PayrollReportKind.DEDUCTIONS:
            report.deductions = [row for r in records for row in self._deduction_rows(r, by_record)]
        elif kind == PayrollReportKind.OVERTIME:
            report.overtime = [row for r in records if (row := self._overtime_row(r)) is not None]
        elif kind == PayrollReportKind.UNPAID_LEAVE:
            report.unpaid_leave = [
                leave_row for r in records if (leave_row := self._unpaid_leave_row(r)) is not None
            ]
        return report

    @staticmethod
    def _adjustment_sums(
        record: PayrollEmployeeRecord,
        by_record: dict[tuple[uuid.UUID, uuid.UUID], list[PayrollAdjustment]],
    ) -> tuple[Decimal, Decimal]:
        earning = _ZERO
        deduction = _ZERO
        for adjustment in by_record.get((record.run_id, record.employee_id), []):
            if adjustment.item_type == PayrollItemType.EARNING.value:
                earning += adjustment.amount
            else:
                deduction += adjustment.amount
        return earning, deduction

    def _summary(
        self,
        records: Sequence[PayrollEmployeeRecord],
        by_record: dict[tuple[uuid.UUID, uuid.UUID], list[PayrollAdjustment]],
    ) -> PayrollReportSummary:
        gross = sum((r.gross_earnings + r.adjustment_earnings for r in records), _ZERO)
        deductions = sum((r.total_deductions + r.adjustment_deductions for r in records), _ZERO)
        adjustments = sum((r.adjustment_earnings + r.adjustment_deductions for r in records), _ZERO)
        overtime = _ZERO
        unpaid = _ZERO
        for record in records:
            for line in record.line_items:
                if line.source == PayrollLineSource.OVERTIME.value:
                    overtime += line.amount
                elif line.source == PayrollLineSource.UNPAID_LEAVE.value:
                    unpaid += line.amount
        del by_record
        return PayrollReportSummary(
            employee_count=len({r.employee_id for r in records}),
            run_count=len({r.run_id for r in records}),
            gross_payroll=gross,
            total_deductions=deductions,
            net_payroll=gross - deductions,
            total_adjustments=adjustments,
            total_overtime=overtime,
            total_overtime_hours=sum((r.overtime_hours_paid for r in records), _ZERO),
            total_unpaid_leave=unpaid,
            total_unpaid_leave_days=sum((r.unpaid_leave_days for r in records), _ZERO),
            total_employer_cost=gross,
            employer_cost_supported=False,
            currency=records[0].currency if records else "INR",
        )

    @staticmethod
    def _identity(record: PayrollEmployeeRecord) -> dict[str, Any]:
        employee = record.employee
        return {
            "employee_id": employee.id,
            "employee_name": employee.full_name,
            "employee_code": employee.employee_code,
            "department": employee.team.name if employee.team is not None else None,
            "period_name": record.run.period.name,
            "currency": record.currency,
        }

    def _monthly_row(
        self,
        record: PayrollEmployeeRecord,
        by_record: dict[tuple[uuid.UUID, uuid.UUID], list[PayrollAdjustment]],
    ) -> MonthlyReportRow:
        earning, deduction = self._adjustment_sums(record, by_record)
        employee = record.employee
        return MonthlyReportRow(
            **self._identity(record),
            location=employee.work_location.name if employee.work_location is not None else None,
            period_end=record.run.period.end_date,
            run_status=PayrollRunStatus(record.run.status),
            record_status=record.status,
            gross=record.gross_earnings + record.adjustment_earnings,
            deductions=record.total_deductions + record.adjustment_deductions,
            adjustments=earning - deduction,
            net_pay=(
                record.gross_earnings
                + record.adjustment_earnings
                - record.total_deductions
                - record.adjustment_deductions
            ),
        )

    def _earnings_row(
        self,
        record: PayrollEmployeeRecord,
        by_record: dict[tuple[uuid.UUID, uuid.UUID], list[PayrollAdjustment]],
    ) -> EarningsReportRow:
        basic = allowances = overtime = other = _ZERO
        for line in record.line_items:
            if line.item_type != PayrollItemType.EARNING.value:
                continue
            if line.source == PayrollLineSource.OVERTIME.value:
                overtime += line.amount
            elif line.source == PayrollLineSource.COMPONENT.value:
                if _is_basic(line.code, line.name):
                    basic += line.amount
                else:
                    allowances += line.amount
            else:
                other += line.amount
        bonus, _deduction = self._adjustment_sums(record, by_record)
        return EarningsReportRow(
            **self._identity(record),
            basic_salary=basic,
            allowances=allowances,
            bonus=bonus,
            overtime=overtime,
            other_earnings=other,
            total_gross=record.gross_earnings + record.adjustment_earnings,
        )

    def _deduction_rows(
        self,
        record: PayrollEmployeeRecord,
        by_record: dict[tuple[uuid.UUID, uuid.UUID], list[PayrollAdjustment]],
    ) -> list[DeductionReportRow]:
        identity = self._identity(record)
        rows = [
            DeductionReportRow(**identity, component=line.name, code=line.code, amount=line.amount)
            for line in record.line_items
            if line.item_type == PayrollItemType.DEDUCTION.value
        ]
        rows += [
            DeductionReportRow(
                **identity, component=f"{adjustment.name} (adjustment)", code=None, amount=adjustment.amount
            )
            for adjustment in by_record.get((record.run_id, record.employee_id), [])
            if adjustment.item_type == PayrollItemType.DEDUCTION.value
        ]
        return rows

    def _overtime_row(self, record: PayrollEmployeeRecord) -> OvertimeReportRow | None:
        amount = sum(
            (line.amount for line in record.line_items if line.source == PayrollLineSource.OVERTIME.value),
            _ZERO,
        )
        if record.overtime_hours_paid <= 0 and amount == 0:
            return None
        return OvertimeReportRow(
            **self._identity(record),
            approved_overtime_hours=record.overtime_hours_paid,
            overtime_amount=amount,
        )

    def _unpaid_leave_row(self, record: PayrollEmployeeRecord) -> UnpaidLeaveReportRow | None:
        lines = [line for line in record.line_items if line.source == PayrollLineSource.UNPAID_LEAVE.value]
        if record.unpaid_leave_days <= 0 and not lines:
            return None
        return UnpaidLeaveReportRow(
            **self._identity(record),
            unpaid_leave_days=record.unpaid_leave_days,
            deduction_basis=lines[0].calculation_basis if lines else None,
            deduction_amount=sum((line.amount for line in lines), _ZERO),
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _filter_context(filters: PayrollReportFilters) -> dict[str, Any]:
        return {key: str(value) for key, value in filters.model_dump(exclude_none=True).items()}

    @staticmethod
    def _tabular(report: PayrollReport) -> tuple[list[str], list[tuple[Any, ...]]]:
        if report.kind == PayrollReportKind.MONTHLY:
            return (
                [
                    "Employee",
                    "Employee ID",
                    "Department",
                    "Location",
                    "Payroll Period",
                    "Gross",
                    "Deductions",
                    "Adjustments",
                    "Net Pay",
                    "Payroll Status",
                    "Currency",
                ],
                [
                    (
                        r.employee_name,
                        r.employee_code,
                        r.department,
                        r.location,
                        r.period_name,
                        r.gross,
                        r.deductions,
                        r.adjustments,
                        r.net_pay,
                        r.run_status.value,
                        r.currency,
                    )
                    for r in report.monthly
                ],
            )
        if report.kind == PayrollReportKind.EARNINGS:
            return (
                [
                    "Employee",
                    "Employee ID",
                    "Department",
                    "Payroll Period",
                    "Basic Salary",
                    "Allowances",
                    "Bonus",
                    "Overtime",
                    "Other Earnings",
                    "Total Gross",
                    "Currency",
                ],
                [
                    (
                        r.employee_name,
                        r.employee_code,
                        r.department,
                        r.period_name,
                        r.basic_salary,
                        r.allowances,
                        r.bonus,
                        r.overtime,
                        r.other_earnings,
                        r.total_gross,
                        r.currency,
                    )
                    for r in report.earnings
                ],
            )
        if report.kind == PayrollReportKind.DEDUCTIONS:
            return (
                [
                    "Deduction Component",
                    "Code",
                    "Amount",
                    "Employee",
                    "Employee ID",
                    "Department",
                    "Payroll Period",
                    "Currency",
                ],
                [
                    (
                        r.component,
                        r.code,
                        r.amount,
                        r.employee_name,
                        r.employee_code,
                        r.department,
                        r.period_name,
                        r.currency,
                    )
                    for r in report.deductions
                ],
            )
        if report.kind == PayrollReportKind.OVERTIME:
            return (
                [
                    "Employee",
                    "Employee ID",
                    "Department",
                    "Payroll Period",
                    "Approved Overtime Hours",
                    "Overtime Amount",
                    "Currency",
                ],
                [
                    (
                        r.employee_name,
                        r.employee_code,
                        r.department,
                        r.period_name,
                        r.approved_overtime_hours,
                        r.overtime_amount,
                        r.currency,
                    )
                    for r in report.overtime
                ],
            )
        if report.kind == PayrollReportKind.UNPAID_LEAVE:
            return (
                [
                    "Employee",
                    "Employee ID",
                    "Department",
                    "Payroll Period",
                    "Unpaid Leave Days",
                    "Deduction Basis",
                    "Deduction Amount",
                    "Currency",
                ],
                [
                    (
                        r.employee_name,
                        r.employee_code,
                        r.department,
                        r.period_name,
                        r.unpaid_leave_days,
                        r.deduction_basis,
                        r.deduction_amount,
                        r.currency,
                    )
                    for r in report.unpaid_leave
                ],
            )
        summary = report.summary
        return (
            ["Metric", "Value"],
            [
                ("Employees", summary.employee_count),
                ("Runs", summary.run_count),
                ("Gross payroll", summary.gross_payroll),
                ("Total deductions", summary.total_deductions),
                ("Net payroll", summary.net_payroll),
                ("Total adjustments", summary.total_adjustments),
                ("Total overtime", summary.total_overtime),
                ("Total overtime hours", summary.total_overtime_hours),
                ("Total unpaid leave", summary.total_unpaid_leave),
                ("Total unpaid leave days", summary.total_unpaid_leave_days),
                ("Employer cost (gross; contributions not modelled)", summary.total_employer_cost),
                ("Currency", summary.currency),
            ],
        )
