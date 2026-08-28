"""Full & final settlement schemas (Phase 8)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import (
    FinalSettlementStatus,
    SettlementAdjustmentStatus,
    SettlementAdjustmentType,
    SettlementItemCategory,
)
from app.schemas.common import PaginationParams
from app.schemas.payroll import EmployeeSummary

_MAX_MONEY = Decimal("999999999999.99")


class SettlementListParams(PaginationParams):
    status: FinalSettlementStatus | None = None
    search: str | None = Field(default=None, max_length=120)


class EligibleExitRow(BaseModel):
    """An exiting employee as the F&F screen lists them: the offboarding facts
    plus where their settlement has got to (``not_started`` when none)."""

    employee: EmployeeSummary
    department: str | None
    joining_date: date | None
    last_working_date: date
    exit_type: str
    exit_reason: str | None
    offboarding_case_id: uuid.UUID
    offboarding_status: str
    final_period_name: str | None
    settlement_id: uuid.UUID | None
    settlement_status: str
    eligible: bool
    ineligibility_reason: str | None


class SettlementItemRead(BaseModel):
    id: uuid.UUID
    category: SettlementItemCategory
    code: str
    name: str
    basis: str | None
    quantity: Decimal | None
    amount: Decimal
    source: str


class SettlementAdjustmentRead(BaseModel):
    id: uuid.UUID
    adjustment_type: SettlementAdjustmentType
    is_earning: bool
    name: str
    amount: Decimal
    reason: str
    notes: str | None
    status: SettlementAdjustmentStatus
    created_by_name: str | None
    created_at: datetime
    decided_by_name: str | None
    decided_at: datetime | None
    decision_note: str | None


class SettlementAdjustmentCreate(BaseModel):
    adjustment_type: SettlementAdjustmentType
    name: str = Field(min_length=2, max_length=150)
    amount: Decimal = Field(gt=0, le=_MAX_MONEY, decimal_places=2)
    reason: str = Field(min_length=3, max_length=400)
    notes: str | None = Field(default=None, max_length=4000)


class SettlementAdjustmentDecision(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=400)


class SettlementIssue(BaseModel):
    severity: str
    message: str


class LeaveBalanceRow(BaseModel):
    leave_type: str
    code: str
    is_paid: bool
    eligible: Decimal
    used: Decimal
    remaining: Decimal
    #: The application has no leave-encashment policy; this is always False
    #: and encashment is recorded only as an approved adjustment.
    encashable: bool = False


class AssetPositionRow(BaseModel):
    asset_name: str
    asset_tag: str | None
    assignment_status: str
    return_status: str
    recovery_amount: Decimal | None
    recovery_approved: bool


class SettlementRead(BaseModel):
    id: uuid.UUID
    settlement_code: str
    employee: EmployeeSummary
    department: str | None
    status: FinalSettlementStatus
    currency: str
    joining_date: date | None
    last_working_date: date
    exit_type: str
    exit_reason: str | None
    final_period_name: str | None
    final_earnings: Decimal
    approved_encashments: Decimal
    approved_adjustments: Decimal
    final_deductions: Decimal
    settlement_amount: Decimal
    calculated_at: datetime | None
    submitted_at: datetime | None
    review_completed_at: datetime | None
    approved_at: datetime | None
    settled_at: datetime | None
    created_at: datetime


class SettlementDetail(SettlementRead):
    """The review screen: everything the reviewer reads, top to bottom."""

    notes: str | None
    offboarding_case_id: uuid.UUID
    offboarding_status: str
    monthly_gross: Decimal | None
    basic_salary: Decimal | None
    daily_rate: Decimal | None
    paid_through: date | None
    unpaid_salary_days: int
    unpaid_leave_days: Decimal
    overtime_hours: Decimal
    leave_summary: list[LeaveBalanceRow]
    assets: list[AssetPositionRow]
    issues: list[SettlementIssue]
    critical_issue_count: int
    items: list[SettlementItemRead]
    adjustments: list[SettlementAdjustmentRead]
    submitted_by_name: str | None
    review_completed_by_name: str | None
    approved_by_name: str | None
    approval_comment: str | None
    settled_by_name: str | None
    settlement_reference: str | None
    can_approve: bool


class SettlementUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=4000)
    exit_type: str | None = Field(default=None, min_length=2, max_length=40)
    exit_reason: str | None = Field(default=None, max_length=200)


class SettlementApproval(BaseModel):
    comment: str = Field(min_length=3, max_length=400)


class SettlementReopen(BaseModel):
    reason: str = Field(min_length=3, max_length=400)


class SettlementFinalize(BaseModel):
    settlement_reference: str | None = Field(default=None, max_length=100)


class MySettlement(BaseModel):
    """What the employee sees of their own settlement once it is released:
    the figures and their breakdown — never internal comments or issues."""

    settlement_code: str
    status: FinalSettlementStatus
    currency: str
    last_working_date: date
    settled_at: datetime | None
    final_earnings: Decimal
    approved_encashments: Decimal
    approved_adjustments: Decimal
    final_deductions: Decimal
    settlement_amount: Decimal
    items: list[SettlementItemRead]
    settlement_reference: str | None


def snapshot_payload(detail: SettlementDetail) -> dict[str, Any]:
    return detail.model_dump(mode="json")


__all__ = [
    "AssetPositionRow",
    "EligibleExitRow",
    "LeaveBalanceRow",
    "MySettlement",
    "SettlementAdjustmentCreate",
    "SettlementAdjustmentDecision",
    "SettlementAdjustmentRead",
    "SettlementApproval",
    "SettlementDetail",
    "SettlementFinalize",
    "SettlementIssue",
    "SettlementItemRead",
    "SettlementListParams",
    "SettlementRead",
    "SettlementReopen",
    "SettlementUpdate",
    "snapshot_payload",
]
