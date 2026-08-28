"""Repositories for payroll reports and full & final settlement (Phase 8).

The settlement repositories own the three F&F tables. :class:`SettlementReader`
and :class:`PayrollReportRepository` are read-only views over other modules'
tables — offboarding, assets, leave, attendance, payroll — written here so the
services never compose SQL against tables they do not own.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetAssignment
from app.models.employee import Employee
from app.models.enums import (
    ApprovalStatus,
    OffboardingCaseStatus,
    PayrollAdjustmentStatus,
    PayrollRecordStatus,
    PayrollRunStatus,
)
from app.models.offboarding import AssetClearance, OffboardingCase, Resignation
from app.models.payroll import (
    PayrollAdjustment,
    PayrollEmployeeRecord,
    PayrollPeriod,
    PayrollRun,
)
from app.models.payroll_settlement import (
    FinalSettlement,
    FinalSettlementAdjustment,
    FinalSettlementItem,
)
from app.models.workforce import AttendanceRecord, LeaveBalance, LeaveRequest, LeaveType
from app.repositories.base import BaseRepository
from app.schemas.payroll_reports import PayrollReportFilters
from app.schemas.payroll_settlement import SettlementListParams


class PayrollReportRepository:
    """Finalized (by default) payroll records with the joins a report needs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def records(self, filters: PayrollReportFilters) -> Sequence[PayrollEmployeeRecord]:
        stmt = (
            select(PayrollEmployeeRecord)
            .join(PayrollRun, PayrollRun.id == PayrollEmployeeRecord.run_id)
            .join(PayrollPeriod, PayrollPeriod.id == PayrollRun.payroll_period_id)
            .join(Employee, Employee.id == PayrollEmployeeRecord.employee_id)
            .where(
                PayrollEmployeeRecord.deleted_at.is_(None),
                PayrollRun.deleted_at.is_(None),
                PayrollRun.status == filters.status.value,
            )
        )
        if filters.period_id is not None:
            stmt = stmt.where(PayrollRun.payroll_period_id == filters.period_id)
        if filters.date_from is not None:
            stmt = stmt.where(PayrollPeriod.end_date >= filters.date_from)
        if filters.date_to is not None:
            stmt = stmt.where(PayrollPeriod.end_date <= filters.date_to)
        if filters.team_id is not None:
            stmt = stmt.where(Employee.team_id == filters.team_id)
        if filters.location_id is not None:
            stmt = stmt.where(Employee.work_location_id == filters.location_id)
        if filters.employee_id is not None:
            stmt = stmt.where(PayrollEmployeeRecord.employee_id == filters.employee_id)
        stmt = stmt.order_by(
            PayrollPeriod.end_date.desc(), Employee.first_name.asc(), Employee.last_name.asc()
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def active_adjustments(self, run_ids: Sequence[uuid.UUID]) -> Sequence[PayrollAdjustment]:
        if not run_ids:
            return []
        stmt = select(PayrollAdjustment).where(
            PayrollAdjustment.deleted_at.is_(None),
            PayrollAdjustment.run_id.in_(list(run_ids)),
            PayrollAdjustment.status == PayrollAdjustmentStatus.ACTIVE.value,
        )
        return (await self.session.execute(stmt)).scalars().unique().all()


class SettlementReader:
    """Read-only access to what a settlement is computed from."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exit_cases(self) -> Sequence[tuple[OffboardingCase, Resignation | None]]:
        """Every non-cancelled offboarding case with its resignation, newest exit first."""
        stmt = (
            select(OffboardingCase, Resignation)
            .outerjoin(Resignation, Resignation.id == OffboardingCase.resignation_id)
            .where(
                OffboardingCase.deleted_at.is_(None),
                OffboardingCase.status != OffboardingCaseStatus.CANCELLED.value,
            )
            .order_by(OffboardingCase.last_working_day.desc())
        )
        rows = (await self.session.execute(stmt)).unique().all()
        return [(case, resignation) for case, resignation in rows]

    async def case(self, case_id: uuid.UUID) -> OffboardingCase | None:
        stmt = select(OffboardingCase).where(
            OffboardingCase.id == case_id, OffboardingCase.deleted_at.is_(None)
        )
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def resignation(self, resignation_id: uuid.UUID) -> Resignation | None:
        stmt = select(Resignation).where(Resignation.id == resignation_id)
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def period_containing(self, day: date) -> PayrollPeriod | None:
        stmt = (
            select(PayrollPeriod)
            .where(
                PayrollPeriod.deleted_at.is_(None),
                PayrollPeriod.start_date <= day,
                PayrollPeriod.end_date >= day,
            )
            .order_by(PayrollPeriod.start_date.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def paid_through(self, employee_id: uuid.UUID) -> date | None:
        """The end of the last *finalized* period that paid this employee."""
        stmt = (
            select(func.max(PayrollPeriod.end_date))
            .select_from(PayrollEmployeeRecord)
            .join(PayrollRun, PayrollRun.id == PayrollEmployeeRecord.run_id)
            .join(PayrollPeriod, PayrollPeriod.id == PayrollRun.payroll_period_id)
            .where(
                PayrollEmployeeRecord.employee_id == employee_id,
                PayrollEmployeeRecord.deleted_at.is_(None),
                PayrollEmployeeRecord.status != PayrollRecordStatus.EXCLUDED.value,
                PayrollRun.status == PayrollRunStatus.FINALIZED.value,
            )
        )
        result: date | None = await self.session.scalar(stmt)
        return result

    async def unpaid_leave_days(self, employee_id: uuid.UUID, start: date, end: date) -> Decimal:
        """Approved unpaid-type leave days inside the window, clipped to it."""
        stmt = (
            select(LeaveRequest)
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
            .where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.deleted_at.is_(None),
                LeaveRequest.status == ApprovalStatus.APPROVED.value,
                LeaveType.is_paid.is_(False),
                LeaveRequest.from_date <= end,
                LeaveRequest.to_date >= start,
            )
        )
        total = Decimal("0")
        for request in (await self.session.execute(stmt)).scalars().all():
            overlap_from = max(request.from_date, start)
            overlap_to = min(request.to_date, end)
            total += Decimal((overlap_to - overlap_from).days + 1)
        return total

    async def overtime_minutes(self, employee_id: uuid.UUID, start: date, end: date) -> int:
        stmt = select(func.coalesce(func.sum(AttendanceRecord.overtime_minutes), 0)).where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.deleted_at.is_(None),
            AttendanceRecord.attendance_date >= start,
            AttendanceRecord.attendance_date <= end,
        )
        return int(await self.session.scalar(stmt) or 0)

    async def leave_balances(
        self, employee_id: uuid.UUID, year: int
    ) -> Sequence[tuple[LeaveBalance, LeaveType]]:
        stmt = (
            select(LeaveBalance, LeaveType)
            .join(LeaveType, LeaveType.id == LeaveBalance.leave_type_id)
            .where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.year == year,
                LeaveBalance.deleted_at.is_(None),
            )
            .order_by(LeaveType.name.asc())
        )
        rows = (await self.session.execute(stmt)).unique().all()
        return [(balance, leave_type) for balance, leave_type in rows]

    async def open_assignments(self, employee_id: uuid.UUID) -> Sequence[tuple[AssetAssignment, Asset]]:
        stmt = (
            select(AssetAssignment, Asset)
            .join(Asset, Asset.id == AssetAssignment.asset_id)
            .where(
                AssetAssignment.employee_id == employee_id,
                AssetAssignment.deleted_at.is_(None),
                AssetAssignment.returned_at.is_(None),
            )
            .order_by(Asset.name.asc())
        )
        rows = (await self.session.execute(stmt)).unique().all()
        return [(assignment, asset) for assignment, asset in rows]

    async def clearances(self, case_id: uuid.UUID) -> Sequence[AssetClearance]:
        stmt = (
            select(AssetClearance)
            .where(AssetClearance.case_id == case_id, AssetClearance.deleted_at.is_(None))
            .order_by(AssetClearance.asset_name.asc())
        )
        return (await self.session.execute(stmt)).scalars().all()


class FinalSettlementRepository(BaseRepository[FinalSettlement]):
    model = FinalSettlement

    async def by_case(self, case_id: uuid.UUID) -> FinalSettlement | None:
        return await self.find(FinalSettlement.offboarding_case_id == case_id)

    async def by_code(self, code: str) -> FinalSettlement | None:
        return await self.find(FinalSettlement.settlement_code == code)

    async def latest_for_employee(self, employee_id: uuid.UUID) -> FinalSettlement | None:
        stmt = (
            self._base_select()
            .where(FinalSettlement.employee_id == employee_id)
            .order_by(FinalSettlement.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def for_cases(self, case_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, FinalSettlement]:
        if not case_ids:
            return {}
        stmt = self._base_select().where(FinalSettlement.offboarding_case_id.in_(list(case_ids)))
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        return {row.offboarding_case_id: row for row in rows}

    async def search(self, params: SettlementListParams) -> tuple[Sequence[FinalSettlement], int]:
        stmt = self._base_select().join(Employee, Employee.id == FinalSettlement.employee_id)
        if params.status:
            stmt = stmt.where(FinalSettlement.status == params.status.value)
        if params.search:
            needle = f"%{params.search.strip()}%"
            stmt = stmt.where(
                or_(
                    Employee.first_name.ilike(needle),
                    Employee.last_name.ilike(needle),
                    Employee.employee_code.ilike(needle),
                    FinalSettlement.settlement_code.ilike(needle),
                )
            )
        total = await self._count_of(stmt)
        stmt = (
            stmt.order_by(FinalSettlement.last_working_date.desc())
            .offset(params.offset)
            .limit(params.page_size)
        )
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        return rows, total

    async def _count_of(self, stmt: Select[tuple[FinalSettlement]]) -> int:
        counted = select(func.count()).select_from(stmt.order_by(None).subquery())
        return int((await self.session.execute(counted)).scalar_one())


class FinalSettlementItemRepository(BaseRepository[FinalSettlementItem]):
    model = FinalSettlementItem

    async def clear_for(self, settlement_id: uuid.UUID) -> None:
        """Items are derived rows: replaced whole on every calculation."""
        stmt = select(FinalSettlementItem).where(FinalSettlementItem.settlement_id == settlement_id)
        for row in (await self.session.execute(stmt)).scalars().all():
            await self.session.delete(row)
        await self.session.flush()


class FinalSettlementAdjustmentRepository(BaseRepository[FinalSettlementAdjustment]):
    model = FinalSettlementAdjustment

    async def for_settlement(self, settlement_id: uuid.UUID) -> Sequence[FinalSettlementAdjustment]:
        stmt = (
            self._base_select()
            .where(FinalSettlementAdjustment.settlement_id == settlement_id)
            .order_by(FinalSettlementAdjustment.created_at.asc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()
