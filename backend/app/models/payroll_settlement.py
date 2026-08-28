"""Full & final settlement persistence (Payroll Phase 8).

Three tables and one rule: **the settlement is its components.** A
settlement row carries the employee's exit facts and the four totals, but
the truth lives in its items — one row per computed figure (final salary,
overtime, unpaid leave) and one per approved adjustment — so an auditor can
read back how the settlement amount was reached rather than take one number
on trust. Adjustments are separate rows with a type that fixes their
direction, a mandatory reason and an approval decision; only approved ones
become items.

Nothing here edits an employee, a payroll run or an offboarding case: the
settlement reads them and records what it read. Settling freezes the row and
writes the whole detail into ``final_snapshot``.
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
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.employee import Employee
from app.models.enums import (
    FINAL_SETTLEMENT_STATUS_SQL_VALUES,
    SETTLEMENT_ADJUSTMENT_STATUS_SQL_VALUES,
    SETTLEMENT_ADJUSTMENT_TYPE_SQL_VALUES,
    SETTLEMENT_ITEM_CATEGORY_SQL_VALUES,
    FinalSettlementStatus,
    SettlementAdjustmentStatus,
)
from app.models.offboarding import OffboardingCase
from app.models.payroll import PayrollPeriod
from app.models.user import User


class FinalSettlement(Base, AuditableBase):
    """One employee's full & final settlement, tied to their offboarding case."""

    __tablename__ = "full_final_settlements"
    __table_args__ = (
        UniqueConstraint("offboarding_case_id", name="uq_full_final_settlements_case"),
        UniqueConstraint("settlement_code", name="uq_full_final_settlements_code"),
        CheckConstraint(f"status IN ({FINAL_SETTLEMENT_STATUS_SQL_VALUES})", name="status"),
        Index("ix_full_final_settlements_status_lwd", "status", "last_working_date"),
        {"comment": "Full & final settlements: exit facts, components, workflow, snapshot."},
    )

    settlement_code: Mapped[str] = mapped_column(String(40))
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    offboarding_case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offboarding_cases.id", ondelete="RESTRICT")
    )
    resignation_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("resignations.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=FinalSettlementStatus.DRAFT,
        server_default=FinalSettlementStatus.DRAFT.value,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")

    # -- Exit facts, copied at creation so the settlement keeps saying what
    # -- it was about even if the case is later edited.
    joining_date: Mapped[date | None] = mapped_column(Date)
    last_working_date: Mapped[date] = mapped_column(Date, index=True)
    exit_type: Mapped[str] = mapped_column(String(40), default="resignation", server_default="resignation")
    exit_reason: Mapped[str | None] = mapped_column(String(200))
    final_period_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_periods.id", ondelete="SET NULL")
    )
    compensation_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employee_compensation.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    # -- Calculation inputs as of the last calculation.
    monthly_gross: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    basic_salary: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    daily_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    paid_through: Mapped[date | None] = mapped_column(Date)
    unpaid_salary_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unpaid_leave_days: Mapped[Decimal] = mapped_column(
        Numeric(5, 1), default=Decimal("0"), server_default="0"
    )
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"), server_default="0")
    #: Per-type leave summary, asset positions and review issues, as JSON
    #: read from the leave, asset and offboarding modules at calculation.
    leave_summary: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    assets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")

    # -- The four components, stored separately, and their sum.
    final_earnings: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), server_default="0")
    approved_encashments: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default="0"
    )
    approved_adjustments: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default="0"
    )
    final_deductions: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default="0"
    )
    settlement_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default="0"
    )
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # -- Workflow milestones.
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    review_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_completed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approval_comment: Mapped[str | None] = mapped_column(String(400))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    settlement_reference: Mapped[str | None] = mapped_column(String(100))
    #: The whole detail, frozen at settlement. Immutable thereafter.
    final_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    employee: Mapped[Employee] = relationship(lazy="joined")
    offboarding_case: Mapped[OffboardingCase] = relationship(lazy="selectin")
    final_period: Mapped[PayrollPeriod | None] = relationship(lazy="selectin")
    submitted_by: Mapped[User | None] = relationship(foreign_keys=[submitted_by_id], lazy="selectin")
    review_completed_by: Mapped[User | None] = relationship(
        foreign_keys=[review_completed_by_id], lazy="selectin"
    )
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_id], lazy="selectin")
    settled_by: Mapped[User | None] = relationship(foreign_keys=[settled_by_id], lazy="selectin")
    items: Mapped[list[FinalSettlementItem]] = relationship(
        back_populates="settlement",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="FinalSettlementItem.sort_order",
    )
    adjustments: Mapped[list[FinalSettlementAdjustment]] = relationship(
        back_populates="settlement",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="FinalSettlementAdjustment.created_at",
    )


class FinalSettlementItem(Base, AuditableBase):
    """One figure of a settlement. Rebuilt whole on every calculation."""

    __tablename__ = "full_final_settlement_items"
    __table_args__ = (
        CheckConstraint(f"category IN ({SETTLEMENT_ITEM_CATEGORY_SQL_VALUES})", name="category"),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        {"comment": "Settlement components, one row per figure."},
    )

    settlement_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("full_final_settlements.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(20), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(150))
    basis: Mapped[str | None] = mapped_column(String(300))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    #: ``computed`` from existing data, or the approved adjustment it came from.
    source: Mapped[str] = mapped_column(String(20), default="computed", server_default="computed")
    adjustment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("full_final_settlement_adjustments.id", ondelete="SET NULL"),
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    settlement: Mapped[FinalSettlement] = relationship(back_populates="items")


class FinalSettlementAdjustment(Base, AuditableBase):
    """One proposed addition or recovery, with its reason and its decision.

    Pending until approved; only approved adjustments become settlement
    items. Rejected ones stay on record — the history of what was proposed
    is part of the settlement's trail.
    """

    __tablename__ = "full_final_settlement_adjustments"
    __table_args__ = (
        CheckConstraint(
            f"adjustment_type IN ({SETTLEMENT_ADJUSTMENT_TYPE_SQL_VALUES})", name="adjustment_type"
        ),
        CheckConstraint(f"status IN ({SETTLEMENT_ADJUSTMENT_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint("amount > 0", name="amount_positive"),
        {"comment": "Proposed settlement adjustments with their approval decision."},
    )

    settlement_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("full_final_settlements.id", ondelete="CASCADE"), index=True
    )
    adjustment_type: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(150))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    reason: Mapped[str] = mapped_column(String(400))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20),
        default=SettlementAdjustmentStatus.PENDING,
        server_default=SettlementAdjustmentStatus.PENDING.value,
        index=True,
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(400))

    settlement: Mapped[FinalSettlement] = relationship(back_populates="adjustments")
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_id], lazy="selectin")
