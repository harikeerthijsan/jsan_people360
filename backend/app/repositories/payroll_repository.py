"""Payroll repositories.

Thin by design, like every repository here: they own the SQL and nothing else.
The overlap rule, the required-components rule and the revision workflow live
in :mod:`app.services.payroll_service`; what this module contributes is the
queries those rules are made of — most importantly :meth:`overlapping`, which
is the period-intersection test written once.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import Select, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.employee import Employee
from app.models.enums import (
    ApprovalStatus,
    CompensationStatus,
    EmploymentStatus,
    PayrollAdjustmentStatus,
    PayrollExceptionSeverity,
    PayrollExceptionStatus,
    PayrollPeriodStatus,
    RecordStatus,
)
from app.models.offboarding import OffboardingCase
from app.models.payroll import (
    EmployeeCompensation,
    EmployeeCompensationComponent,
    PayrollAdjustment,
    PayrollApproval,
    PayrollConfiguration,
    PayrollConfigurationHistory,
    PayrollEmployeeRecord,
    PayrollEmployeeSetting,
    PayrollFinalSnapshot,
    PayrollInput,
    PayrollInputException,
    PayrollInputSource,
    PayrollLeaveRule,
    PayrollLineItem,
    PayrollPeriod,
    PayrollReviewChecklist,
    PayrollReviewComment,
    PayrollRun,
    PayrollRunException,
    Payslip,
    SalaryComponent,
    SalaryHistory,
    SalaryStructure,
    SalaryStructureComponent,
)
from app.models.user import User
from app.models.workforce import AttendanceRecord, AttendanceRegularization, LeaveBalance, LeaveRequest
from app.repositories.base import BaseRepository
from app.schemas.payroll import (
    CompensationListParams,
    EmployeeSettingsListParams,
    PayrollInputListParams,
    PayrollRecordListParams,
    PayrollRunListParams,
    PayslipListParams,
    PeriodListParams,
    StructureListParams,
)


class SalaryStructureRepository(BaseRepository[SalaryStructure]):
    model = SalaryStructure

    async def by_name(self, name: str) -> SalaryStructure | None:
        """Case-insensitive lookup, matching the unique index."""
        return await self.find(func.lower(SalaryStructure.name) == name.strip().lower())

    async def search(self, params: StructureListParams) -> tuple[Sequence[SalaryStructure], int]:
        stmt = self._base_select()
        if params.search:
            stmt = stmt.where(SalaryStructure.name.ilike(f"%{params.search.strip()}%"))
        if params.status:
            stmt = stmt.where(SalaryStructure.status == params.status.value)

        total = await self._count_of(stmt)
        stmt = stmt.order_by(SalaryStructure.name.asc()).offset(params.offset).limit(params.limit)
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        return rows, total

    async def _count_of(self, stmt: Select[tuple[SalaryStructure]]) -> int:
        counted = select(func.count()).select_from(stmt.order_by(None).subquery())
        return int((await self.session.execute(counted)).scalar_one())


class SalaryComponentRepository(BaseRepository[SalaryComponent]):
    model = SalaryComponent

    async def by_code(self, code: str) -> SalaryComponent | None:
        return await self.find(SalaryComponent.code == code.strip().upper())

    async def all_components(self, *, include_inactive: bool = False) -> Sequence[SalaryComponent]:
        stmt = self._base_select()
        if not include_inactive:
            stmt = stmt.where(SalaryComponent.status == RecordStatus.ACTIVE.value)
        stmt = stmt.order_by(SalaryComponent.component_type.asc(), SalaryComponent.name.asc())
        return (await self.session.execute(stmt)).scalars().all()

    async def by_ids(self, ids: Sequence[uuid.UUID]) -> Sequence[SalaryComponent]:
        if not ids:
            return []
        stmt = self._base_select().where(SalaryComponent.id.in_(list(ids)))
        return (await self.session.execute(stmt)).scalars().all()


class SalaryStructureComponentRepository(BaseRepository[SalaryStructureComponent]):
    model = SalaryStructureComponent

    async def for_structure(self, structure_id: uuid.UUID) -> Sequence[SalaryStructureComponent]:
        stmt = self._base_select().where(SalaryStructureComponent.structure_id == structure_id)
        return (await self.session.execute(stmt)).scalars().unique().all()


class EmployeeCompensationRepository(BaseRepository[EmployeeCompensation]):
    model = EmployeeCompensation

    async def for_employee(self, employee_id: uuid.UUID) -> Sequence[EmployeeCompensation]:
        """Every period, newest first — the salary screen's spine."""
        stmt = (
            self._base_select()
            .where(EmployeeCompensation.employee_id == employee_id)
            .order_by(EmployeeCompensation.effective_from.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def current_for_employee(self, employee_id: uuid.UUID) -> EmployeeCompensation | None:
        """The active record whose period is still open or latest-starting."""
        stmt = (
            self._base_select()
            .where(
                EmployeeCompensation.employee_id == employee_id,
                EmployeeCompensation.status == CompensationStatus.ACTIVE.value,
            )
            .order_by(EmployeeCompensation.effective_from.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def overlapping(
        self,
        employee_id: uuid.UUID,
        effective_from: date,
        effective_to: date | None,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> EmployeeCompensation | None:
        """The first ACTIVE record whose period intersects [from, to].

        Two periods [a, b] and [c, d] (NULL meaning open-ended) intersect when
        a <= d and c <= b. Written once, here, so the assignment path and the
        revision path cannot disagree about what an overlap is.
        """
        stmt = self._base_select().where(
            EmployeeCompensation.employee_id == employee_id,
            EmployeeCompensation.status == CompensationStatus.ACTIVE.value,
            or_(
                EmployeeCompensation.effective_to.is_(None),
                EmployeeCompensation.effective_to >= effective_from,
            ),
        )
        if effective_to is not None:
            stmt = stmt.where(EmployeeCompensation.effective_from <= effective_to)
        if exclude_id is not None:
            stmt = stmt.where(EmployeeCompensation.id != exclude_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def search_current(
        self, params: CompensationListParams
    ) -> tuple[Sequence[EmployeeCompensation], int]:
        """The admin register: every employee's ACTIVE compensation."""
        stmt = (
            self._base_select()
            .join(Employee, Employee.id == EmployeeCompensation.employee_id)
            .where(EmployeeCompensation.status == CompensationStatus.ACTIVE.value)
        )
        if params.search:
            needle = f"%{params.search.strip()}%"
            stmt = stmt.where(
                or_(
                    Employee.first_name.ilike(needle),
                    Employee.last_name.ilike(needle),
                    Employee.employee_code.ilike(needle),
                )
            )

        counted = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self.session.execute(counted)).scalar_one())

        stmt = (
            stmt.order_by(Employee.first_name.asc(), Employee.last_name.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        return rows, total


class EmployeeCompensationComponentRepository(BaseRepository[EmployeeCompensationComponent]):
    model = EmployeeCompensationComponent


class SalaryHistoryRepository(BaseRepository[SalaryHistory]):
    model = SalaryHistory

    async def for_employee(self, employee_id: uuid.UUID) -> Sequence[SalaryHistory]:
        stmt = (
            self._base_select().where(SalaryHistory.employee_id == employee_id)
            # created_at is the transaction timestamp, so two rows written in
            # one request tie on it; the effective date breaks the tie.
            .order_by(SalaryHistory.created_at.desc(), SalaryHistory.effective_from.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()


# ======================================================================
# Phase 2 — configuration and pay rules
# ======================================================================
class PayrollConfigurationRepository(BaseRepository[PayrollConfiguration]):
    model = PayrollConfiguration

    async def singleton(self) -> PayrollConfiguration | None:
        """The one live configuration row. The UNIQUE(singleton) constraint is
        what guarantees "one", so a bare first() is honest here."""
        return (await self.session.execute(self._base_select())).scalars().first()


class PayrollConfigurationHistoryRepository(BaseRepository[PayrollConfigurationHistory]):
    model = PayrollConfigurationHistory

    async def newest_first(self, *, limit: int = 200) -> Sequence[PayrollConfigurationHistory]:
        stmt = (
            self._base_select()
            .order_by(
                PayrollConfigurationHistory.created_at.desc(),
                PayrollConfigurationHistory.field.asc(),
            )
            .limit(limit)
        )
        return (await self.session.execute(stmt)).scalars().unique().all()


class PayrollPeriodRepository(BaseRepository[PayrollPeriod]):
    model = PayrollPeriod

    async def by_name(self, name: str) -> PayrollPeriod | None:
        """Case-insensitive, matching the unique index."""
        return await self.find(func.lower(PayrollPeriod.name) == name.strip().lower())

    async def search(self, params: PeriodListParams) -> tuple[Sequence[PayrollPeriod], int]:
        stmt = self._base_select()
        if params.status:
            stmt = stmt.where(PayrollPeriod.status == params.status.value)

        counted = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self.session.execute(counted)).scalar_one())

        stmt = stmt.order_by(PayrollPeriod.start_date.desc()).offset(params.offset).limit(params.limit)
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        return rows, total

    async def overlapping(
        self, start_date: date, end_date: date, *, exclude_id: uuid.UUID | None = None
    ) -> PayrollPeriod | None:
        """The first non-cancelled period whose dates intersect [start, end]."""
        stmt = self._base_select().where(
            PayrollPeriod.status != PayrollPeriodStatus.CANCELLED.value,
            PayrollPeriod.start_date <= end_date,
            PayrollPeriod.end_date >= start_date,
        )
        if exclude_id is not None:
            stmt = stmt.where(PayrollPeriod.id != exclude_id)
        return (await self.session.execute(stmt)).scalars().first()


class PayrollLeaveRuleRepository(BaseRepository[PayrollLeaveRule]):
    model = PayrollLeaveRule

    async def by_leave_type(
        self, leave_type_id: uuid.UUID, *, include_deleted: bool = False
    ) -> PayrollLeaveRule | None:
        return await self.find(
            PayrollLeaveRule.leave_type_id == leave_type_id, include_deleted=include_deleted
        )

    async def all_rules(self, *, include_inactive: bool = False) -> Sequence[PayrollLeaveRule]:
        stmt = self._base_select()
        if not include_inactive:
            stmt = stmt.where(PayrollLeaveRule.status == RecordStatus.ACTIVE.value)
        stmt = stmt.order_by(PayrollLeaveRule.created_at.asc())
        return (await self.session.execute(stmt)).scalars().unique().all()


class PayrollInputRepository(BaseRepository[PayrollInput]):
    model = PayrollInput

    async def for_period_employee(self, period_id: uuid.UUID, employee_id: uuid.UUID) -> PayrollInput | None:
        return await self.find(
            PayrollInput.payroll_period_id == period_id, PayrollInput.employee_id == employee_id
        )

    async def for_period(self, period_id: uuid.UUID) -> Sequence[PayrollInput]:
        stmt = self._base_select().where(PayrollInput.payroll_period_id == period_id)
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def for_employee(self, employee_id: uuid.UUID) -> Sequence[PayrollInput]:
        """Every period's input for one employee, newest period first. The
        spine of the employee's own self-service view."""
        stmt = (
            self._base_select()
            .join(PayrollPeriod, PayrollPeriod.id == PayrollInput.payroll_period_id)
            .where(PayrollInput.employee_id == employee_id)
            .order_by(PayrollPeriod.start_date.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def search(
        self, period_id: uuid.UUID, params: PayrollInputListParams
    ) -> tuple[Sequence[PayrollInput], int]:
        stmt = (
            self._base_select()
            .join(Employee, Employee.id == PayrollInput.employee_id)
            .where(PayrollInput.payroll_period_id == period_id)
        )
        if params.status:
            stmt = stmt.where(PayrollInput.status == params.status.value)
        if params.search:
            needle = f"%{params.search.strip()}%"
            stmt = stmt.where(
                or_(
                    Employee.first_name.ilike(needle),
                    Employee.last_name.ilike(needle),
                    Employee.employee_code.ilike(needle),
                )
            )
        if params.business_unit_id:
            stmt = stmt.where(Employee.business_unit_id == params.business_unit_id)
        if params.location_id:
            stmt = stmt.where(Employee.work_location_id == params.location_id)

        counted = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self.session.execute(counted)).scalar_one())

        stmt = (
            stmt.order_by(Employee.first_name.asc(), Employee.last_name.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        return rows, total


class PayrollInputExceptionRepository(BaseRepository[PayrollInputException]):
    model = PayrollInputException

    async def for_period(self, period_id: uuid.UUID) -> Sequence[PayrollInputException]:
        stmt = (
            self._base_select()
            .join(PayrollInput, PayrollInput.id == PayrollInputException.input_id)
            .where(PayrollInput.payroll_period_id == period_id)
            # The period view names each exception's employee; loading that
            # lazily under asyncio is a MissingGreenlet, not a query.
            .options(joinedload(PayrollInputException.input).joinedload(PayrollInput.employee))
            .order_by(PayrollInputException.created_at.asc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def clear_for_input(self, input_id: uuid.UUID) -> None:
        """Replace-on-refresh: exceptions are derived rows, regenerated whole."""
        rows = await self.list(PayrollInputException.input_id == input_id, limit=10_000)
        for row in rows:
            await self.hard_delete(row)


class PayrollInputSourceRepository(BaseRepository[PayrollInputSource]):
    model = PayrollInputSource

    async def for_input(self, input_id: uuid.UUID) -> Sequence[PayrollInputSource]:
        stmt = (
            self._base_select()
            .where(PayrollInputSource.input_id == input_id)
            .order_by(PayrollInputSource.source_type.asc(), PayrollInputSource.source_updated_at.asc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def clear_for_input(self, input_id: uuid.UUID) -> None:
        rows = await self.list(PayrollInputSource.input_id == input_id, limit=10_000)
        for row in rows:
            await self.hard_delete(row)


class PayrollSourceReader:
    """Read-only, batched queries over the modules payroll inputs consume.

    Deliberately not a repository *of* anything: it owns no table. It exists so
    the input service reads attendance, leave, regularizations, balances and
    offboarding through one narrow surface — every method is a SELECT over
    another module's models, and nothing here can write. That is the shape of
    "consume, don't duplicate": the modules keep their logic, payroll keeps a
    reader.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def attendance_between(self, start: date, end: date) -> Sequence[AttendanceRecord]:
        stmt = (
            select(AttendanceRecord)
            .where(
                AttendanceRecord.deleted_at.is_(None),
                AttendanceRecord.attendance_date >= start,
                AttendanceRecord.attendance_date <= end,
            )
            .order_by(AttendanceRecord.attendance_date.asc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def regularizations_between(self, start: date, end: date) -> Sequence[AttendanceRegularization]:
        stmt = select(AttendanceRegularization).where(
            AttendanceRegularization.deleted_at.is_(None),
            AttendanceRegularization.attendance_date >= start,
            AttendanceRegularization.attendance_date <= end,
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def approved_leaves_overlapping(self, start: date, end: date) -> Sequence[LeaveRequest]:
        stmt = select(LeaveRequest).where(
            LeaveRequest.deleted_at.is_(None),
            LeaveRequest.status == ApprovalStatus.APPROVED.value,
            LeaveRequest.from_date <= end,
            LeaveRequest.to_date >= start,
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def balances_for_year(self, year: int) -> Sequence[LeaveBalance]:
        stmt = select(LeaveBalance).where(LeaveBalance.deleted_at.is_(None), LeaveBalance.year == year)
        return (await self.session.execute(stmt)).scalars().all()

    async def offboarding_cases_until(self, end: date) -> Sequence[OffboardingCase]:
        """Every case with a settled last working day up to the period's end.

        Used both to spot exits inside the period and to keep employees whose
        exit predates it out of the run — with a stated reason, not silently.
        """
        stmt = select(OffboardingCase).where(
            OffboardingCase.deleted_at.is_(None), OffboardingCase.last_working_day <= end
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def employees_joined_by(self, end: date) -> Sequence[Employee]:
        """Everyone whose employment could intersect the period."""
        stmt = select(Employee).where(
            Employee.deleted_at.is_(None),
            Employee.joining_date <= end,
            Employee.employment_status.in_(
                [
                    EmploymentStatus.ACTIVE.value,
                    EmploymentStatus.NOTICE_PERIOD.value,
                    EmploymentStatus.RESIGNED.value,
                    EmploymentStatus.INACTIVE.value,
                ]
            ),
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def active_compensation(self) -> Sequence[EmployeeCompensation]:
        stmt = select(EmployeeCompensation).where(
            EmployeeCompensation.deleted_at.is_(None),
            EmployeeCompensation.status == CompensationStatus.ACTIVE.value,
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def all_employee_settings(self) -> Sequence[PayrollEmployeeSetting]:
        stmt = select(PayrollEmployeeSetting).where(PayrollEmployeeSetting.deleted_at.is_(None))
        return (await self.session.execute(stmt)).scalars().all()

    async def compensation_overlapping(self, start: date, end: date) -> Sequence[EmployeeCompensation]:
        """Every compensation record whose period intersects [start, end].

        Ended records included on purpose: a salary revised mid-period is two
        records, and July's payroll must read both — the ended one for the
        first half, the active one for the second.
        """
        stmt = select(EmployeeCompensation).where(
            EmployeeCompensation.deleted_at.is_(None),
            EmployeeCompensation.effective_from <= end,
            or_(
                EmployeeCompensation.effective_to.is_(None),
                EmployeeCompensation.effective_to >= start,
            ),
        )
        return (await self.session.execute(stmt)).scalars().all()


# ======================================================================
# Phase 4 — payroll runs
# ======================================================================
class PayrollRunRepository(BaseRepository[PayrollRun]):
    model = PayrollRun

    async def by_period(self, period_id: uuid.UUID) -> PayrollRun | None:
        return await self.find(PayrollRun.payroll_period_id == period_id)

    async def previous_run(self, before: date) -> PayrollRun | None:
        """The run whose period ended most recently before ``before`` — the
        comparison baseline for period-over-period review."""
        stmt = (
            self._base_select()
            .join(PayrollPeriod, PayrollPeriod.id == PayrollRun.payroll_period_id)
            .where(PayrollPeriod.end_date < before)
            .order_by(PayrollPeriod.end_date.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def search(self, params: PayrollRunListParams) -> tuple[Sequence[PayrollRun], int]:
        stmt = self._base_select()
        if params.status:
            stmt = stmt.where(PayrollRun.status == params.status.value)

        counted = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self.session.execute(counted)).scalar_one())

        stmt = stmt.order_by(PayrollRun.created_at.desc()).offset(params.offset).limit(params.limit)
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        return rows, total


class PayrollEmployeeRecordRepository(BaseRepository[PayrollEmployeeRecord]):
    model = PayrollEmployeeRecord

    async def for_run(self, run_id: uuid.UUID) -> Sequence[PayrollEmployeeRecord]:
        stmt = self._base_select().where(PayrollEmployeeRecord.run_id == run_id)
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def for_run_employee(
        self, run_id: uuid.UUID, employee_id: uuid.UUID
    ) -> PayrollEmployeeRecord | None:
        return await self.find(
            PayrollEmployeeRecord.run_id == run_id, PayrollEmployeeRecord.employee_id == employee_id
        )

    async def for_employee(self, employee_id: uuid.UUID) -> Sequence[PayrollEmployeeRecord]:
        """One employee's records across runs, newest period first."""
        stmt = (
            self._base_select()
            .join(PayrollRun, PayrollRun.id == PayrollEmployeeRecord.run_id)
            .join(PayrollPeriod, PayrollPeriod.id == PayrollRun.payroll_period_id)
            .where(PayrollEmployeeRecord.employee_id == employee_id)
            .order_by(PayrollPeriod.start_date.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def search(
        self, run_id: uuid.UUID, params: PayrollRecordListParams
    ) -> tuple[Sequence[PayrollEmployeeRecord], int]:
        stmt = (
            self._base_select()
            .join(Employee, Employee.id == PayrollEmployeeRecord.employee_id)
            .where(PayrollEmployeeRecord.run_id == run_id)
        )
        if params.status:
            stmt = stmt.where(PayrollEmployeeRecord.status == params.status.value)
        if params.search:
            needle = f"%{params.search.strip()}%"
            stmt = stmt.where(
                or_(
                    Employee.first_name.ilike(needle),
                    Employee.last_name.ilike(needle),
                    Employee.employee_code.ilike(needle),
                )
            )

        counted = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self.session.execute(counted)).scalar_one())

        stmt = (
            stmt.order_by(Employee.first_name.asc(), Employee.last_name.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        return rows, total

    async def clear_for_run(self, run_id: uuid.UUID) -> int:
        """Idempotent recalculation: records are derived rows, replaced whole.
        Line items go with them through the ORM cascade."""
        rows = await self.list(PayrollEmployeeRecord.run_id == run_id, limit=100_000)
        for row in rows:
            await self.hard_delete(row)
        return len(rows)


class PayrollLineItemRepository(BaseRepository[PayrollLineItem]):
    model = PayrollLineItem


# ======================================================================
# Phase 5 — payroll review
# ======================================================================
class PayrollRunExceptionRepository(BaseRepository[PayrollRunException]):
    model = PayrollRunException

    async def for_run(
        self,
        run_id: uuid.UUID,
        *,
        status: str | None = None,
        severity: str | None = None,
    ) -> Sequence[PayrollRunException]:
        stmt = self._base_select().where(PayrollRunException.run_id == run_id)
        if status:
            stmt = stmt.where(PayrollRunException.status == status)
        if severity:
            stmt = stmt.where(PayrollRunException.severity == severity)
        stmt = stmt.order_by(
            # Worst first: critical, error, warning — then stable by creation.
            PayrollRunException.severity.asc(),
            PayrollRunException.created_at.asc(),
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def open_counts(self, run_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        """(open, open critical) per run, one query for a whole listing."""
        if not run_ids:
            return {}
        stmt = (
            select(
                PayrollRunException.run_id,
                func.count(),
                func.count()
                .filter(PayrollRunException.severity == PayrollExceptionSeverity.CRITICAL.value)
                .label("critical"),
            )
            .where(
                PayrollRunException.deleted_at.is_(None),
                PayrollRunException.run_id.in_(list(run_ids)),
                PayrollRunException.status == PayrollExceptionStatus.OPEN.value,
            )
            .group_by(PayrollRunException.run_id)
        )
        rows = (await self.session.execute(stmt)).all()
        return {run_id: (int(total), int(critical)) for run_id, total, critical in rows}

    async def clear_for_run(self, run_id: uuid.UUID) -> None:
        """Regenerated whole on recalculation; resolutions are carried over
        by the engine before this is called."""
        rows = await self.list(PayrollRunException.run_id == run_id, limit=100_000)
        for row in rows:
            await self.hard_delete(row)


class PayrollAdjustmentRepository(BaseRepository[PayrollAdjustment]):
    model = PayrollAdjustment

    async def for_run(
        self,
        run_id: uuid.UUID,
        *,
        employee_id: uuid.UUID | None = None,
        include_cancelled: bool = True,
    ) -> Sequence[PayrollAdjustment]:
        stmt = self._base_select().where(PayrollAdjustment.run_id == run_id)
        if employee_id is not None:
            stmt = stmt.where(PayrollAdjustment.employee_id == employee_id)
        if not include_cancelled:
            stmt = stmt.where(PayrollAdjustment.status == PayrollAdjustmentStatus.ACTIVE.value)
        stmt = stmt.order_by(PayrollAdjustment.created_at.asc())
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def active_counts(self, run_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Active adjustments per run, one query for a whole listing."""
        if not run_ids:
            return {}
        stmt = (
            select(PayrollAdjustment.run_id, func.count())
            .where(
                PayrollAdjustment.deleted_at.is_(None),
                PayrollAdjustment.run_id.in_(list(run_ids)),
                PayrollAdjustment.status == PayrollAdjustmentStatus.ACTIVE.value,
            )
            .group_by(PayrollAdjustment.run_id)
        )
        rows = (await self.session.execute(stmt)).all()
        return {run_id: int(count) for run_id, count in rows}


class PayrollApprovalRepository(BaseRepository[PayrollApproval]):
    """The append-only approval trail: add and read, nothing else."""

    model = PayrollApproval

    async def for_run(self, run_id: uuid.UUID) -> Sequence[PayrollApproval]:
        stmt = (
            self._base_select()
            .where(PayrollApproval.run_id == run_id)
            .order_by(PayrollApproval.created_at.asc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()


class PayrollFinalSnapshotRepository(BaseRepository[PayrollFinalSnapshot]):
    """Immutable finalization snapshots: add and read, nothing else."""

    model = PayrollFinalSnapshot

    async def for_run(self, run_id: uuid.UUID) -> Sequence[PayrollFinalSnapshot]:
        stmt = (
            self._base_select()
            .where(PayrollFinalSnapshot.run_id == run_id)
            .order_by(PayrollFinalSnapshot.employee_name.asc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def for_run_employee(
        self, run_id: uuid.UUID, employee_id: uuid.UUID
    ) -> PayrollFinalSnapshot | None:
        return await self.find(
            PayrollFinalSnapshot.run_id == run_id, PayrollFinalSnapshot.employee_id == employee_id
        )


class PayrollReviewChecklistRepository(BaseRepository[PayrollReviewChecklist]):
    model = PayrollReviewChecklist

    async def for_run(self, run_id: uuid.UUID) -> Sequence[PayrollReviewChecklist]:
        stmt = (
            self._base_select()
            .where(PayrollReviewChecklist.run_id == run_id)
            .order_by(PayrollReviewChecklist.sort_order.asc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def by_key(self, run_id: uuid.UUID, item_key: str) -> PayrollReviewChecklist | None:
        return await self.find(
            PayrollReviewChecklist.run_id == run_id, PayrollReviewChecklist.item_key == item_key
        )


class PayrollReviewCommentRepository(BaseRepository[PayrollReviewComment]):
    model = PayrollReviewComment

    async def for_run(
        self, run_id: uuid.UUID, *, employee_id: uuid.UUID | None = None
    ) -> Sequence[tuple[PayrollReviewComment, str | None]]:
        """Comments with their author's display name, oldest first."""
        stmt = (
            select(PayrollReviewComment, User.first_name, User.last_name)
            .outerjoin(User, User.id == PayrollReviewComment.created_by)
            .where(PayrollReviewComment.deleted_at.is_(None), PayrollReviewComment.run_id == run_id)
        )
        if employee_id is not None:
            stmt = stmt.where(PayrollReviewComment.employee_id == employee_id)
        stmt = stmt.order_by(PayrollReviewComment.created_at.asc())
        rows = (await self.session.execute(stmt)).unique().all()
        return [
            (comment, f"{first} {last}".strip() if first or last else None) for comment, first, last in rows
        ]


class PayrollEmployeeSettingRepository(BaseRepository[PayrollEmployeeSetting]):
    model = PayrollEmployeeSetting

    async def by_employee(
        self, employee_id: uuid.UUID, *, include_deleted: bool = False
    ) -> PayrollEmployeeSetting | None:
        return await self.find(
            PayrollEmployeeSetting.employee_id == employee_id, include_deleted=include_deleted
        )

    async def search(
        self, params: EmployeeSettingsListParams
    ) -> tuple[Sequence[PayrollEmployeeSetting], int]:
        stmt = self._base_select().join(Employee, Employee.id == PayrollEmployeeSetting.employee_id)
        if params.search:
            needle = f"%{params.search.strip()}%"
            stmt = stmt.where(
                or_(
                    Employee.first_name.ilike(needle),
                    Employee.last_name.ilike(needle),
                    Employee.employee_code.ilike(needle),
                )
            )

        counted = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self.session.execute(counted)).scalar_one())

        stmt = (
            stmt.order_by(Employee.first_name.asc(), Employee.last_name.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        return rows, total


class PayslipRepository(BaseRepository[Payslip]):
    """Payslips: add, read and (for regeneration) update the file handle.
    There is no path that changes a number or a payslip number."""

    model = Payslip

    async def _count_of(self, stmt: Select[tuple[Payslip]]) -> int:
        counted = select(func.count()).select_from(stmt.order_by(None).subquery())
        return int((await self.session.execute(counted)).scalar_one())

    def _newest_first(self, stmt: Select[tuple[Payslip]]) -> Select[tuple[Payslip]]:
        return stmt.join(PayrollPeriod, PayrollPeriod.id == Payslip.period_id).order_by(
            PayrollPeriod.end_date.desc(), Payslip.payslip_number.asc()
        )

    async def by_run_employee(self, run_id: uuid.UUID, employee_id: uuid.UUID) -> Payslip | None:
        return await self.find(Payslip.run_id == run_id, Payslip.employee_id == employee_id)

    async def by_number(self, payslip_number: str) -> Payslip | None:
        return await self.find(Payslip.payslip_number == payslip_number)

    async def for_run(self, run_id: uuid.UUID) -> Sequence[Payslip]:
        stmt = self._base_select().where(Payslip.run_id == run_id).order_by(Payslip.payslip_number.asc())
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def for_employee(
        self, employee_id: uuid.UUID, params: PayslipListParams
    ) -> tuple[Sequence[Payslip], int]:
        """One employee's payslips, newest period first."""
        stmt = self._base_select().where(Payslip.employee_id == employee_id)
        total = await self._count_of(stmt)
        rows = (
            (
                await self.session.execute(
                    self._newest_first(stmt).offset(params.offset).limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def search(self, params: PayslipListParams) -> tuple[Sequence[Payslip], int]:
        stmt = self._base_select()
        if params.employee_id is not None:
            stmt = stmt.where(Payslip.employee_id == params.employee_id)
        if params.run_id is not None:
            stmt = stmt.where(Payslip.run_id == params.run_id)
        if params.payslip_number:
            stmt = stmt.where(Payslip.payslip_number.ilike(f"%{params.payslip_number.strip()}%"))
        if params.team_id is not None:
            stmt = stmt.join(Employee, Employee.id == Payslip.employee_id).where(
                Employee.team_id == params.team_id
            )
        if params.month:
            year, month = (int(part) for part in params.month.split("-"))
            period_ids = (
                select(PayrollPeriod.id)
                .where(extract("year", PayrollPeriod.end_date) == year)
                .where(extract("month", PayrollPeriod.end_date) == month)
                .scalar_subquery()
            )
            stmt = stmt.where(Payslip.period_id.in_(period_ids))
        total = await self._count_of(stmt)
        rows = (
            (
                await self.session.execute(
                    self._newest_first(stmt).offset(params.offset).limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total
