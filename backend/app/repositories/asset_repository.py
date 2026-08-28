"""Persistence for the asset register.

Query shapes only. Which employees' assets a caller may reach is decided by
:mod:`app.services.scope_service` and passed in as ``visible_ids``; this module
applies the filter it is given and never derives one of its own.

Scoping an *asset* is indirect, and that is the one subtlety here: an asset has
no employee, its open assignment does. So a scoped query joins through
``asset_assignments`` and narrows on the holder, which also means an unassigned
asset belongs to nobody and is therefore visible to nobody who is scoped. That
is correct: a laptop in a cupboard is not "yours" or "your team's", and only an
org-wide caller has any business seeing the whole cupboard.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.orm import joinedload

from app.models.asset import (
    Asset,
    AssetAssignment,
    AssetCategory,
    AssetHistory,
    AssetMaintenance,
    AssetReturn,
    AssetTransfer,
)
from app.models.employee import Employee
from app.models.enums import (
    TERMINAL_ASSET_STATUSES,
    WARRANTY_WARNING_DAYS,
    AssetEvent,
    AssetStatus,
    MaintenanceStatus,
    RecordStatus,
)
from app.repositories.base import BaseRepository
from app.schemas.asset import AssetListParams, MaintenanceListParams


def _scoped_to_holders(stmt: Select[Any], visible_ids: Collection[uuid.UUID] | None) -> Select[Any]:
    """Narrow to assets held by employees the caller may see.

    ``None`` means unrestricted. An empty collection is the opposite and must
    not collapse into the same branch: it means the caller is entitled to
    nobody, and the honest answer is an empty page rather than the whole
    register.
    """
    if visible_ids is None:
        return stmt
    if not visible_ids:
        return stmt.where(false())
    open_assignment = (
        select(AssetAssignment.asset_id)
        .where(
            AssetAssignment.returned_at.is_(None),
            AssetAssignment.deleted_at.is_(None),
            AssetAssignment.employee_id.in_(visible_ids),
        )
        .scalar_subquery()
    )
    return stmt.where(Asset.id.in_(open_assignment))


class AssetCategoryRepository(BaseRepository[AssetCategory]):
    model = AssetCategory

    async def active(self) -> Sequence[AssetCategory]:
        return await self.list(
            AssetCategory.status == RecordStatus.ACTIVE.value,
            limit=200,
            order_by="name",
            descending=False,
        )

    async def all_categories(self) -> Sequence[AssetCategory]:
        return await self.list(limit=200, order_by="name", descending=False)

    async def by_code(self, code: str) -> AssetCategory | None:
        return await self.get_by(code=code.strip().upper())

    async def in_use(self, category_id: uuid.UUID) -> bool:
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(Asset)
                .where(Asset.category_id == category_id, Asset.deleted_at.is_(None))
            )
            or 0 > 0
        )


class AssetRepository(BaseRepository[Asset]):
    model = Asset

    def _detailed(self) -> Select[tuple[Asset]]:
        return self._base_select().options(joinedload(Asset.category))

    async def get_detailed(self, asset_id: uuid.UUID) -> Asset | None:
        stmt = self._detailed().where(Asset.id == asset_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def by_tag(self, asset_tag: str) -> Asset | None:
        stmt = self._base_select().where(func.lower(Asset.asset_tag) == asset_tag.strip().lower())
        return (await self.session.execute(stmt)).scalars().first()

    async def by_serial(self, serial_number: str) -> Asset | None:
        stmt = self._base_select().where(func.lower(Asset.serial_number) == serial_number.strip().lower())
        return (await self.session.execute(stmt)).scalars().first()

    async def search(
        self, params: AssetListParams, *, visible_ids: Collection[uuid.UUID] | None = None
    ) -> tuple[Sequence[Asset], int]:
        stmt = _scoped_to_holders(self._detailed(), visible_ids)
        criteria: list[Any] = []

        if params.category_id is not None:
            criteria.append(Asset.category_id == params.category_id)
        if params.status is not None:
            criteria.append(Asset.status == params.status.value)
        if params.condition is not None:
            criteria.append(Asset.condition == params.condition.value)
        if params.location:
            criteria.append(Asset.location.ilike(f"%{params.location}%"))
        if params.vendor:
            criteria.append(Asset.vendor.ilike(f"%{params.vendor}%"))
        if params.warranty_expiring:
            horizon = date.today() + timedelta(days=WARRANTY_WARNING_DAYS)
            criteria.append(Asset.warranty_end.is_not(None))
            criteria.append(Asset.warranty_end <= horizon)
        if params.assigned is not None:
            criteria.append(
                Asset.current_assignment_id.is_not(None)
                if params.assigned
                else Asset.current_assignment_id.is_(None)
            )
        if params.employee_id is not None:
            held = (
                select(AssetAssignment.asset_id)
                .where(
                    AssetAssignment.employee_id == params.employee_id,
                    AssetAssignment.returned_at.is_(None),
                    AssetAssignment.deleted_at.is_(None),
                )
                .scalar_subquery()
            )
            criteria.append(Asset.id.in_(held))
        if params.search:
            term = f"%{params.search.strip()}%"
            criteria.append(
                or_(
                    Asset.asset_tag.ilike(term),
                    Asset.asset_code.ilike(term),
                    Asset.name.ilike(term),
                    Asset.serial_number.ilike(term),
                    Asset.model.ilike(term),
                    Asset.brand.ilike(term),
                )
            )

        stmt = stmt.where(*criteria)
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(Asset.created_at.desc()).offset(params.offset).limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def status_counts(self) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(Asset.status, func.count()).where(Asset.deleted_at.is_(None)).group_by(Asset.status)
            )
        ).all()
        return dict(rows)  # type: ignore[arg-type]

    async def counts_by_category(self) -> list[tuple[str, int]]:
        rows = (
            await self.session.execute(
                select(AssetCategory.name, func.count(Asset.id))
                .join(Asset, Asset.category_id == AssetCategory.id)
                .where(Asset.deleted_at.is_(None))
                .group_by(AssetCategory.name)
                .order_by(func.count(Asset.id).desc())
            )
        ).all()
        return [(name, count) for name, count in rows]

    async def counts_by_location(self) -> list[tuple[str, int]]:
        # One expression object, used in both the projection and the grouping.
        # Building `coalesce(...)` twice produces two expressions that Postgres
        # does not recognise as the same, and the query fails with "column
        # assets.location must appear in the GROUP BY clause".
        location = func.coalesce(Asset.location, "Unspecified")
        rows = (
            await self.session.execute(
                select(location, func.count())
                .where(Asset.deleted_at.is_(None))
                .group_by(location)
                .order_by(func.count().desc())
                .limit(20)
            )
        ).all()
        return [(name, count) for name, count in rows]

    async def warranty_counts(self) -> tuple[int, int]:
        """(expiring within the window, already expired)."""
        today = date.today()
        horizon = today + timedelta(days=WARRANTY_WARNING_DAYS)
        live = [
            Asset.deleted_at.is_(None),
            Asset.warranty_end.is_not(None),
            Asset.status.notin_([s.value for s in TERMINAL_ASSET_STATUSES]),
        ]
        expiring = await self.session.scalar(
            select(func.count())
            .select_from(Asset)
            .where(*live, Asset.warranty_end >= today, Asset.warranty_end <= horizon)
        )
        expired = await self.session.scalar(
            select(func.count()).select_from(Asset).where(*live, Asset.warranty_end < today)
        )
        return int(expiring or 0), int(expired or 0)


class AssetAssignmentRepository(BaseRepository[AssetAssignment]):
    model = AssetAssignment

    async def open_for_asset(self, asset_id: uuid.UUID) -> AssetAssignment | None:
        return await self.find(AssetAssignment.asset_id == asset_id, AssetAssignment.returned_at.is_(None))

    async def open_for_employee(self, employee_id: uuid.UUID) -> Sequence[AssetAssignment]:
        """Everything one person is currently holding, with the asset loaded."""
        stmt = (
            self._base_select()
            .options(joinedload(AssetAssignment.asset).joinedload(Asset.category))
            .where(
                AssetAssignment.employee_id == employee_id,
                AssetAssignment.returned_at.is_(None),
            )
            .order_by(AssetAssignment.assigned_date.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def open_for_employees(
        self, employee_ids: Collection[uuid.UUID]
    ) -> Sequence[tuple[AssetAssignment, Asset, AssetCategory, Employee]]:
        """Every open assignment for a set of people, in one query.

        Joined rather than looped: a manager with fifteen reports would
        otherwise be fifteen round trips to build one screen.
        """
        if not employee_ids:
            return []
        stmt = (
            select(AssetAssignment, Asset, AssetCategory, Employee)
            .join(Asset, Asset.id == AssetAssignment.asset_id)
            .join(AssetCategory, AssetCategory.id == Asset.category_id)
            .join(Employee, Employee.id == AssetAssignment.employee_id)
            .where(
                AssetAssignment.employee_id.in_(employee_ids),
                AssetAssignment.returned_at.is_(None),
                AssetAssignment.deleted_at.is_(None),
            )
            .order_by(Employee.first_name, Asset.name)
        )
        return [(row[0], row[1], row[2], row[3]) for row in (await self.session.execute(stmt)).all()]

    async def history_for_asset(self, asset_id: uuid.UUID) -> Sequence[AssetAssignment]:
        return await self.list(
            AssetAssignment.asset_id == asset_id, limit=200, order_by="assigned_date", descending=True
        )


class AssetReturnRepository(BaseRepository[AssetReturn]):
    model = AssetReturn


class AssetTransferRepository(BaseRepository[AssetTransfer]):
    model = AssetTransfer

    async def for_asset(self, asset_id: uuid.UUID) -> Sequence[AssetTransfer]:
        return await self.list(
            AssetTransfer.asset_id == asset_id, limit=200, order_by="transfer_date", descending=True
        )


class AssetMaintenanceRepository(BaseRepository[AssetMaintenance]):
    model = AssetMaintenance

    async def for_asset(self, asset_id: uuid.UUID) -> Sequence[AssetMaintenance]:
        return await self.list(
            AssetMaintenance.asset_id == asset_id, limit=100, order_by="start_date", descending=True
        )

    async def open_for_asset(self, asset_id: uuid.UUID) -> AssetMaintenance | None:
        return await self.find(
            AssetMaintenance.asset_id == asset_id,
            AssetMaintenance.status == MaintenanceStatus.IN_PROGRESS.value,
        )

    async def search(self, params: MaintenanceListParams) -> tuple[Sequence[AssetMaintenance], int]:
        stmt = self._base_select().options(joinedload(AssetMaintenance.asset).joinedload(Asset.category))
        criteria: list[Any] = []
        if params.asset_id is not None:
            criteria.append(AssetMaintenance.asset_id == params.asset_id)
        if params.status is not None:
            criteria.append(AssetMaintenance.status == params.status.value)
        if params.maintenance_type is not None:
            criteria.append(AssetMaintenance.maintenance_type == params.maintenance_type.value)
        if params.due_only:
            criteria.append(AssetMaintenance.status == MaintenanceStatus.SCHEDULED.value)
            criteria.append(AssetMaintenance.start_date <= date.today())

        stmt = stmt.where(*criteria)
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(AssetMaintenance.start_date.desc())
                    .offset(params.offset)
                    .limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total

    async def due_count(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(AssetMaintenance)
                .where(
                    AssetMaintenance.deleted_at.is_(None),
                    AssetMaintenance.status == MaintenanceStatus.SCHEDULED.value,
                    AssetMaintenance.start_date <= date.today(),
                )
            )
            or 0
        )


class AssetHistoryRepository(BaseRepository[AssetHistory]):
    model = AssetHistory

    async def for_asset(self, asset_id: uuid.UUID, *, limit: int = 200) -> Sequence[AssetHistory]:
        return await self.list(
            AssetHistory.asset_id == asset_id, limit=limit, order_by="created_at", descending=True
        )

    async def recent(self, event: AssetEvent, *, limit: int = 5) -> Sequence[AssetHistory]:
        return await self.list(
            AssetHistory.event == event.value, limit=limit, order_by="created_at", descending=True
        )

    async def movement(
        self, *, offset: int, limit: int, asset_id: uuid.UUID | None = None
    ) -> tuple[Sequence[AssetHistory], int]:
        criteria: list[Any] = [
            AssetHistory.event.in_(
                [AssetEvent.ASSIGNED.value, AssetEvent.RETURNED.value, AssetEvent.TRANSFERRED.value]
            )
        ]
        if asset_id is not None:
            criteria.append(AssetHistory.asset_id == asset_id)
        total = await self.count(*criteria)
        rows = await self.list(*criteria, offset=offset, limit=limit, order_by="created_at", descending=True)
        return rows, total


class AssetAnalyticsRepository:
    """Cross-table counters for the dashboard.

    A plain object rather than a ``BaseRepository`` because none of these
    queries are about one model.
    """

    def __init__(self, session: Any) -> None:
        self.session = session

    async def unassigned_available(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Asset)
                .where(
                    Asset.deleted_at.is_(None),
                    Asset.status == AssetStatus.AVAILABLE.value,
                    Asset.current_assignment_id.is_(None),
                )
            )
            or 0
        )
