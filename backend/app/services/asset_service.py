"""Asset management business logic.

Four rules shape this module.

**Custody moves through a transaction, never through a column.** Assigning,
returning and transferring each write a record and each append to the asset's
history. There is no code path that sets a holder directly, and
:class:`~app.schemas.asset.AssetUpdate` has no field that could ask for one --
which is what makes §8 of the brief ("editing must not destroy history") a
property of the design rather than a rule somebody has to remember.

**Status moves only along the transition table.** Every change goes through
:meth:`AssetService._assert_transition`, which consults
``ASSET_STATUS_TRANSITIONS``. A disposed asset cannot come back, a damaged one
cannot become available without passing through maintenance, and nothing
anywhere skips a step by writing the column itself.

**The register is the source of truth for offboarding clearance.** When a case
opens, the clearance rows are seeded from what the employee actually holds, and
resolving one here updates the real asset. §16 says not to build a second
clearance system, and this is the reverse of that: the existing one grows a link
to the register it was always described as waiting for.

**Scope is about the holder, not the asset.** An asset has no employee; its open
assignment does. So a scoped caller sees what their people hold, and an
unassigned laptop in a cupboard belongs to nobody -- correctly invisible to
anyone whose reach is a reporting line.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from openpyxl import Workbook

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.asset import (
    Asset,
    AssetAssignment,
    AssetCategory,
    AssetHistory,
    AssetMaintenance,
    AssetReturn,
    AssetTransfer,
)
from app.models.audit_log import AuditAction
from app.models.employee import Employee
from app.models.enums import (
    ASSET_STATUS_TRANSITIONS,
    ASSIGNABLE_ASSET_STATUSES,
    TERMINAL_ASSET_STATUSES,
    WARRANTY_WARNING_DAYS,
    AssetCondition,
    AssetEvent,
    AssetReturnStatus,
    AssetStatus,
    MaintenanceStatus,
    RecordStatus,
)
from app.models.requisition import Notification
from app.repositories.asset_repository import (
    AssetAnalyticsRepository,
    AssetAssignmentRepository,
    AssetCategoryRepository,
    AssetHistoryRepository,
    AssetMaintenanceRepository,
    AssetRepository,
    AssetReturnRepository,
    AssetTransferRepository,
)
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.requisition_repository import NotificationRepository
from app.schemas.asset import (
    AssetAssign,
    AssetAssignmentRead,
    AssetCategoryCreate,
    AssetCategoryRead,
    AssetCategoryUpdate,
    AssetCreate,
    AssetDashboard,
    AssetDetail,
    AssetHistoryEntry,
    AssetListParams,
    AssetRead,
    AssetReturnInput,
    AssetStatusChange,
    AssetTransferInput,
    AssetUpdate,
    CountByLabel,
    EmployeeAssetClearanceRow,
    EmployeeSummary,
    MaintenanceCreate,
    MaintenanceListParams,
    MaintenanceRead,
    MaintenanceUpdate,
    MyAsset,
    TeamAssetRow,
)
from app.services.audit_service import AuditService
from app.services.scope_service import EmployeeScope, visible_employee_ids
from app.utils.datetime import utc_now

logger = get_logger("services.asset")

#: Reports the export endpoint knows how to build.
REPORTS: tuple[str, ...] = (
    "inventory",
    "assigned",
    "available",
    "by_employee",
    "maintenance",
    "warranty",
    "lost_damaged",
    "movement",
)


class AssetService:
    """The asset register, its custody trail, and its offboarding link."""

    def __init__(
        self,
        assets: AssetRepository,
        categories: AssetCategoryRepository,
        assignments: AssetAssignmentRepository,
        returns: AssetReturnRepository,
        transfers: AssetTransferRepository,
        maintenance: AssetMaintenanceRepository,
        history: AssetHistoryRepository,
        analytics: AssetAnalyticsRepository,
        employees: EmployeeRepository,
        audit: AuditService,
        notifications: NotificationRepository,
    ) -> None:
        self.assets = assets
        self.categories = categories
        self.assignments = assignments
        self.returns = returns
        self.transfers = transfers
        self.maintenance = maintenance
        self.history = history
        self.analytics = analytics
        self.employees = employees
        self.audit = audit
        self.notifications = notifications
        self.session = assets.session

    # ==================================================================
    # Categories
    # ==================================================================
    async def list_categories(self, *, include_inactive: bool = False) -> Sequence[AssetCategory]:
        return await (self.categories.all_categories() if include_inactive else self.categories.active())

    async def create_category(self, payload: AssetCategoryCreate, *, actor_id: uuid.UUID) -> AssetCategory:
        code = payload.code.strip().upper()
        if await self.categories.by_code(code) is not None:
            raise ConflictError(
                f'A category with the code "{code}" already exists.', error_code="duplicate_code"
            )
        category = await self.categories.add(
            AssetCategory(
                name=payload.name.strip(),
                code=code,
                description=payload.description,
                returnable=payload.returnable,
                status=RecordStatus.ACTIVE.value,
            ),
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.ASSET_CATEGORY_CHANGED,
            actor_id=actor_id,
            entity_type="asset_category",
            entity_id=category.id,
            description=f"Created asset category {category.name} ({category.code})",
        )
        return category

    async def update_category(
        self, category_id: uuid.UUID, payload: AssetCategoryUpdate, *, actor_id: uuid.UUID
    ) -> AssetCategory:
        category = await self.categories.get(category_id)
        if category is None:
            raise NotFoundError("Asset category")

        changes = payload.model_dump(exclude_unset=True)
        if changes.get("status") is not None:
            changes["status"] = payload.status.value if payload.status else None
        await self.categories.update(category, changes, actor_id=actor_id)

        await self.audit.record_success(
            AuditAction.ASSET_CATEGORY_CHANGED,
            actor_id=actor_id,
            entity_type="asset_category",
            entity_id=category.id,
            description=f"Updated asset category {category.name}",
            context={"fields": sorted(changes)},
        )
        return category

    # ==================================================================
    # The register
    # ==================================================================
    async def list_assets(
        self, params: AssetListParams, *, scope: EmployeeScope | None = None
    ) -> tuple[Sequence[Asset], int]:
        return await self.assets.search(params, visible_ids=visible_employee_ids(scope))

    async def get_asset(self, asset_id: uuid.UUID, *, scope: EmployeeScope | None = None) -> Asset:
        asset = await self.assets.get_detailed(asset_id)
        if asset is None:
            raise NotFoundError("Asset")
        if scope is not None and not scope.unrestricted:
            await self._assert_asset_in_scope(asset, scope)
        return asset

    async def create_asset(self, payload: AssetCreate, *, actor_id: uuid.UUID) -> Asset:
        if payload.status is AssetStatus.ASSIGNED:
            raise ValidationError(
                "An asset cannot be created as assigned: assign it once it exists, so there is an "
                "assignment record behind the custody.",
                error_code="invalid_initial_status",
            )
        if payload.status in TERMINAL_ASSET_STATUSES:
            raise ValidationError(
                "An asset cannot be created retired or disposed.", error_code="invalid_initial_status"
            )

        await self._assert_category_usable(payload.category_id)
        await self._assert_tag_available(payload.asset_tag)
        if payload.serial_number:
            await self._assert_serial_available(payload.serial_number)

        values = payload.model_dump()
        values["asset_tag"] = payload.asset_tag.strip()
        values["name"] = payload.name.strip()
        values["condition"] = payload.condition.value
        values["status"] = payload.status.value
        if payload.serial_number:
            values["serial_number"] = payload.serial_number.strip()

        asset = await self.assets.add(Asset(**values), actor_id=actor_id)
        await self._record(
            asset,
            AssetEvent.CREATED,
            actor_id=actor_id,
            new_value=asset.status,
            notes=f"Registered as {asset.asset_code}",
        )
        await self.audit.record_success(
            AuditAction.ASSET_CREATED,
            actor_id=actor_id,
            entity_type="asset",
            entity_id=asset.id,
            description=f"Registered asset {asset.asset_code} ({asset.asset_tag})",
        )
        logger.info("Asset created", extra={"asset_id": str(asset.id), "tag": asset.asset_tag})
        return await self._reload(asset.id)

    async def update_asset(self, asset_id: uuid.UUID, payload: AssetUpdate, *, actor_id: uuid.UUID) -> Asset:
        """Details only. Custody and status are not reachable from here."""
        asset = await self.get_asset(asset_id)
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return asset

        if changes.get("asset_tag"):
            await self._assert_tag_available(changes["asset_tag"], exclude_id=asset.id)
            changes["asset_tag"] = changes["asset_tag"].strip()
        if changes.get("serial_number"):
            await self._assert_serial_available(changes["serial_number"], exclude_id=asset.id)
            changes["serial_number"] = changes["serial_number"].strip()
        if changes.get("category_id"):
            await self._assert_category_usable(changes["category_id"])

        await self.assets.update(asset, changes, actor_id=actor_id)
        await self._record(
            asset,
            AssetEvent.UPDATED,
            actor_id=actor_id,
            notes=f"Updated: {', '.join(sorted(changes))}",
        )
        await self.audit.record_success(
            AuditAction.ASSET_UPDATED,
            actor_id=actor_id,
            entity_type="asset",
            entity_id=asset.id,
            description=f"Updated asset {asset.asset_code}",
            context={"fields": sorted(changes)},
        )
        return await self._reload(asset.id)

    # ==================================================================
    # Custody
    # ==================================================================
    async def assign(
        self, asset_id: uuid.UUID, payload: AssetAssign, *, actor_id: uuid.UUID
    ) -> AssetAssignment:
        """Issue an available asset to an employee."""
        asset = await self.get_asset(asset_id)
        status = AssetStatus(asset.status)

        if status not in ASSIGNABLE_ASSET_STATUSES:
            raise ConflictError(
                f"This asset is {status.value.replace('_', ' ')} and cannot be assigned.",
                error_code="asset_not_assignable",
            )
        # Belt and braces with the partial unique index: the index is what holds
        # under a race, this is what produces a readable message.
        if await self.assignments.open_for_asset(asset.id) is not None:
            raise ConflictError("This asset is already assigned to somebody.", error_code="already_assigned")

        employee = await self._assert_employee_active(payload.employee_id)

        assignment = await self.assignments.add(
            AssetAssignment(
                asset_id=asset.id,
                employee_id=employee.id,
                assigned_date=payload.assigned_date,
                expected_return_date=payload.expected_return_date,
                condition_at_assignment=payload.condition_at_assignment.value,
                assigned_by_id=actor_id,
                notes=payload.notes,
            ),
            actor_id=actor_id,
        )
        await self._move(
            asset,
            AssetStatus.ASSIGNED,
            actor_id=actor_id,
            condition=payload.condition_at_assignment,
            assignment_id=assignment.id,
        )
        await self._record(
            asset,
            AssetEvent.ASSIGNED,
            actor_id=actor_id,
            employee_id=employee.id,
            previous_value=status.value,
            new_value=AssetStatus.ASSIGNED.value,
            notes=f"Assigned to {employee.full_name}",
        )
        await self.audit.record_success(
            AuditAction.ASSET_ASSIGNED,
            actor_id=actor_id,
            entity_type="asset",
            entity_id=asset.id,
            description=f"Assigned {asset.asset_code} to {employee.employee_code}",
            context={"employee_id": str(employee.id)},
        )
        await self._notify(
            employee,
            "Asset assigned",
            f"{asset.name} ({asset.asset_tag}) has been assigned to you.",
        )
        return assignment

    async def process_return(
        self, asset_id: uuid.UUID, payload: AssetReturnInput, *, actor_id: uuid.UUID
    ) -> AssetReturn:
        """Take an asset back and record the state it came back in."""
        asset = await self.get_asset(asset_id)
        assignment = await self.assignments.open_for_asset(asset.id)
        if assignment is None:
            raise ConflictError(
                "This asset is not currently assigned, so there is nothing to return.",
                error_code="not_assigned",
            )
        if payload.return_date < assignment.assigned_date:
            raise ValidationError(
                "The return date cannot be before the asset was assigned.",
                error_code="invalid_return_date",
            )

        target = payload.resulting_status or (
            AssetStatus.UNDER_MAINTENANCE
            if payload.condition_at_return is AssetCondition.DAMAGED
            else AssetStatus.AVAILABLE
        )

        record = await self.returns.add(
            AssetReturn(
                asset_id=asset.id,
                assignment_id=assignment.id,
                returned_by_id=assignment.employee_id,
                received_by_id=actor_id,
                return_date=payload.return_date,
                condition_at_return=payload.condition_at_return.value,
                damage_details=payload.damage_details,
                missing_accessories=payload.missing_accessories,
                notes=payload.notes,
            ),
            actor_id=actor_id,
        )
        await self._close_assignment(assignment, actor_id=actor_id)
        await self._move(
            asset, target, actor_id=actor_id, condition=payload.condition_at_return, assignment_id=None
        )
        await self._record(
            asset,
            AssetEvent.RETURNED,
            actor_id=actor_id,
            employee_id=assignment.employee_id,
            previous_value=AssetStatus.ASSIGNED.value,
            new_value=target.value,
            notes=payload.damage_details or payload.notes,
        )
        await self.audit.record_success(
            AuditAction.ASSET_RETURNED,
            actor_id=actor_id,
            entity_type="asset",
            entity_id=asset.id,
            description=f"{asset.asset_code} returned in {payload.condition_at_return.value} condition",
            context={"employee_id": str(assignment.employee_id), "status": target.value},
        )
        await self._sync_clearance(asset, assignment.employee_id, payload.condition_at_return)
        return record

    async def transfer(
        self, asset_id: uuid.UUID, payload: AssetTransferInput, *, actor_id: uuid.UUID
    ) -> AssetTransfer:
        """Move custody straight from one employee to another.

        Recorded as a transfer rather than a return followed by an assignment,
        because "A handed it to B" is what happened and the other is not.
        """
        asset = await self.get_asset(asset_id)
        current = await self.assignments.open_for_asset(asset.id)
        if current is None:
            raise ConflictError(
                "This asset is not currently assigned, so there is nobody to transfer it from. "
                "Assign it instead.",
                error_code="not_assigned",
            )
        if current.employee_id == payload.to_employee_id:
            raise ConflictError("The asset is already assigned to that employee.", error_code="same_holder")

        recipient = await self._assert_employee_active(payload.to_employee_id)
        previous_holder = await self.employees.get(current.employee_id)
        previous_name = previous_holder.full_name if previous_holder else "another employee"

        record = await self.transfers.add(
            AssetTransfer(
                asset_id=asset.id,
                from_employee_id=current.employee_id,
                to_employee_id=recipient.id,
                transfer_date=payload.transfer_date,
                condition_at_transfer=payload.condition_at_transfer.value,
                reason=payload.reason,
                approved_by_id=actor_id,
                notes=payload.notes,
            ),
            actor_id=actor_id,
        )
        # The old custody period ends and a new one opens. Both records survive,
        # which is what makes the history read "A -> B" rather than just "B".
        await self._close_assignment(current, actor_id=actor_id)
        assignment = await self.assignments.add(
            AssetAssignment(
                asset_id=asset.id,
                employee_id=recipient.id,
                assigned_date=payload.transfer_date,
                condition_at_assignment=payload.condition_at_transfer.value,
                assigned_by_id=actor_id,
                notes=f"Transferred from {previous_name}",
            ),
            actor_id=actor_id,
        )
        await self.assets.update(
            asset,
            {"current_assignment_id": assignment.id, "condition": payload.condition_at_transfer.value},
            actor_id=actor_id,
        )
        await self._record(
            asset,
            AssetEvent.TRANSFERRED,
            actor_id=actor_id,
            employee_id=recipient.id,
            previous_value=previous_holder.full_name if previous_holder else None,
            new_value=recipient.full_name,
            notes=payload.reason,
        )
        await self.audit.record_success(
            AuditAction.ASSET_TRANSFERRED,
            actor_id=actor_id,
            entity_type="asset",
            entity_id=asset.id,
            description=f"{asset.asset_code} transferred to {recipient.employee_code}",
            context={
                "from_employee_id": str(current.employee_id),
                "to_employee_id": str(recipient.id),
            },
        )
        await self._notify(
            recipient,
            "Asset transferred to you",
            f"{asset.name} ({asset.asset_tag}) is now assigned to you.",
        )
        if previous_holder:
            await self._notify(
                previous_holder,
                "Asset transferred",
                f"{asset.name} ({asset.asset_tag}) is no longer assigned to you.",
            )
        return record

    async def change_status(
        self, asset_id: uuid.UUID, payload: AssetStatusChange, *, actor_id: uuid.UUID
    ) -> Asset:
        """Move an asset along the transition table, with a reason."""
        asset = await self.get_asset(asset_id)
        previous = AssetStatus(asset.status)

        if payload.status is AssetStatus.ASSIGNED:
            raise ConflictError(
                "Use the assignment endpoint: an asset becomes assigned by being given to somebody, "
                "and that needs an assignment record behind it.",
                error_code="use_assignment",
            )
        await self._move(
            asset, payload.status, actor_id=actor_id, condition=payload.condition, assignment_id=...
        )

        event = {
            AssetStatus.DAMAGED: AssetEvent.DAMAGED,
            AssetStatus.LOST: AssetEvent.LOST,
            AssetStatus.RETIRED: AssetEvent.RETIRED,
            AssetStatus.DISPOSED: AssetEvent.DISPOSED,
        }.get(payload.status, AssetEvent.STATUS_CHANGED)
        # Coming back from lost is a recovery, which is a different fact from a
        # plain status change and is what somebody searches the history for.
        if previous is AssetStatus.LOST and payload.status is not AssetStatus.RETIRED:
            event = AssetEvent.RECOVERED

        await self._record(
            asset,
            event,
            actor_id=actor_id,
            previous_value=previous.value,
            new_value=payload.status.value,
            notes=payload.reason,
        )
        action = {
            AssetStatus.RETIRED: AuditAction.ASSET_RETIRED,
            AssetStatus.DISPOSED: AuditAction.ASSET_DISPOSED,
        }.get(payload.status, AuditAction.ASSET_STATUS_CHANGED)
        await self.audit.record_success(
            action,
            actor_id=actor_id,
            entity_type="asset",
            entity_id=asset.id,
            description=f"{asset.asset_code}: {previous.value} -> {payload.status.value}",
            context={"reason": payload.reason},
        )
        return await self._reload(asset.id)

    # ==================================================================
    # Maintenance
    # ==================================================================
    async def list_maintenance(self, params: MaintenanceListParams) -> tuple[Sequence[AssetMaintenance], int]:
        return await self.maintenance.search(params)

    async def schedule_maintenance(
        self, payload: MaintenanceCreate, *, actor_id: uuid.UUID
    ) -> AssetMaintenance:
        asset = await self.get_asset(payload.asset_id)
        if AssetStatus(asset.status) in TERMINAL_ASSET_STATUSES:
            raise ConflictError(
                "A retired or disposed asset cannot be sent for maintenance.",
                error_code="asset_out_of_service",
            )

        values = payload.model_dump(exclude={"start_now"})
        values["maintenance_type"] = payload.maintenance_type.value
        values["status"] = (
            MaintenanceStatus.IN_PROGRESS.value if payload.start_now else MaintenanceStatus.SCHEDULED.value
        )
        record = await self.maintenance.add(AssetMaintenance(**values), actor_id=actor_id)

        if payload.start_now:
            await self._begin_maintenance(asset, record, actor_id=actor_id)
        return record

    async def update_maintenance(
        self, maintenance_id: uuid.UUID, payload: MaintenanceUpdate, *, actor_id: uuid.UUID
    ) -> AssetMaintenance:
        record = await self.maintenance.get(maintenance_id)
        if record is None:
            raise NotFoundError("Maintenance record")
        asset = await self.get_asset(record.asset_id)
        previous = MaintenanceStatus(record.status)

        if previous in {MaintenanceStatus.COMPLETED, MaintenanceStatus.CANCELLED}:
            raise ConflictError(
                f"This maintenance is already {previous.value} and cannot be changed.",
                error_code="maintenance_closed",
            )

        changes: dict[str, Any] = {"status": payload.status.value}
        for field in ("end_date", "cost", "vendor", "notes"):
            value = getattr(payload, field)
            if value is not None:
                changes[field] = value
        await self.maintenance.update(record, changes, actor_id=actor_id)

        if payload.status is MaintenanceStatus.IN_PROGRESS and previous is MaintenanceStatus.SCHEDULED:
            await self._begin_maintenance(asset, record, actor_id=actor_id)
        elif payload.status is MaintenanceStatus.COMPLETED:
            await self._complete_maintenance(asset, record, payload, actor_id=actor_id)
        elif (
            payload.status is MaintenanceStatus.CANCELLED
            and AssetStatus(asset.status) is AssetStatus.UNDER_MAINTENANCE
        ):
            # A cancelled job leaves the asset where it is unless it was already
            # off the floor for it, in which case it goes back to available.
            await self._move(
                asset, AssetStatus.AVAILABLE, actor_id=actor_id, condition=None, assignment_id=...
            )
        return record

    async def _begin_maintenance(
        self, asset: Asset, record: AssetMaintenance, *, actor_id: uuid.UUID
    ) -> None:
        current = AssetStatus(asset.status)
        if current is AssetStatus.ASSIGNED:
            # Somebody is holding it. Close the custody first, so the register
            # never claims a person has a laptop that is in a repair shop.
            open_assignment = await self.assignments.open_for_asset(asset.id)
            if open_assignment is not None:
                await self._close_assignment(open_assignment, actor_id=actor_id)
        if current is not AssetStatus.UNDER_MAINTENANCE:
            await self._move(
                asset,
                AssetStatus.UNDER_MAINTENANCE,
                actor_id=actor_id,
                condition=None,
                assignment_id=None,
            )
        await self._record(
            asset,
            AssetEvent.MAINTENANCE_STARTED,
            actor_id=actor_id,
            previous_value=current.value,
            new_value=AssetStatus.UNDER_MAINTENANCE.value,
            notes=record.description,
        )
        await self.audit.record_success(
            AuditAction.ASSET_MAINTENANCE_STARTED,
            actor_id=actor_id,
            entity_type="asset",
            entity_id=asset.id,
            description=f"Maintenance started on {asset.asset_code}",
        )

    async def _complete_maintenance(
        self, asset: Asset, record: AssetMaintenance, payload: MaintenanceUpdate, *, actor_id: uuid.UUID
    ) -> None:
        target = payload.resulting_status or AssetStatus.AVAILABLE
        await self._move(
            asset,
            target,
            actor_id=actor_id,
            condition=payload.resulting_condition,
            assignment_id=...,
        )
        await self._record(
            asset,
            AssetEvent.MAINTENANCE_COMPLETED,
            actor_id=actor_id,
            previous_value=AssetStatus.UNDER_MAINTENANCE.value,
            new_value=target.value,
            notes=payload.notes or record.description,
        )
        await self.audit.record_success(
            AuditAction.ASSET_MAINTENANCE_COMPLETED,
            actor_id=actor_id,
            entity_type="asset",
            entity_id=asset.id,
            description=f"Maintenance completed on {asset.asset_code}",
            context={"status": target.value},
        )

    # ==================================================================
    # The employee's own view, and the manager's team
    # ==================================================================
    async def my_assets(self, employee: Employee) -> list[MyAsset]:
        rows = await self.assignments.open_for_employee(employee.id)
        return [
            MyAsset(
                id=row.asset.id,
                asset_code=row.asset.asset_code,
                asset_tag=row.asset.asset_tag,
                name=row.asset.name,
                category=row.asset.category.name,
                brand=row.asset.brand,
                model=row.asset.model,
                serial_number=row.asset.serial_number,
                assigned_date=row.assigned_date,
                expected_return_date=row.expected_return_date,
                condition_at_assignment=AssetCondition(row.condition_at_assignment),
                status=AssetStatus(row.asset.status),
            )
            for row in rows
        ]

    async def team_assets(self, scope: EmployeeScope) -> list[TeamAssetRow]:
        """What the caller's direct reports are holding.

        ``scope.employee_ids`` is the reporting line resolved once per request;
        this never derives its own, so a manager screen and an HR screen use the
        same query with a different filter rather than two implementations.
        """
        rows = await self.assignments.open_for_employees(scope.employee_ids)
        return [
            TeamAssetRow(
                assignment_id=assignment.id,
                asset_id=asset.id,
                employee=EmployeeSummary(
                    id=employee.id, employee_code=employee.employee_code, full_name=employee.full_name
                ),
                asset_code=asset.asset_code,
                asset_tag=asset.asset_tag,
                name=asset.name,
                category=category.name,
                status=AssetStatus(asset.status),
                condition=AssetCondition(asset.condition),
                assigned_date=assignment.assigned_date,
                expected_return_date=assignment.expected_return_date,
            )
            for assignment, asset, category, employee in rows
        ]

    async def assets_for_employee(self, employee_id: uuid.UUID) -> list[EmployeeAssetClearanceRow]:
        """What one person is holding, in the shape the clearance screen wants.

        Used by HR on the offboarding screen and by the register's own
        per-employee report. The caller is responsible for having checked scope;
        this answers the question it was asked.
        """
        rows = await self.assignments.open_for_employee(employee_id)
        return [
            EmployeeAssetClearanceRow(
                asset_id=row.asset.id,
                asset_code=row.asset.asset_code,
                asset_tag=row.asset.asset_tag,
                name=row.asset.name,
                category=row.asset.category.name,
                assigned_date=row.assigned_date,
                condition=AssetCondition(row.asset.condition),
                returnable=row.asset.category.returnable,
                clearance_status="assigned",
            )
            for row in rows
        ]

    # ==================================================================
    # Offboarding integration
    # ==================================================================
    async def clearance_rows_for(self, employee_id: uuid.UUID) -> list[dict[str, Any]]:
        """Seed data for an offboarding case's asset clearance.

        Returns plain dictionaries rather than models on purpose: the
        offboarding service owns ``asset_clearance`` and creates the rows. This
        module supplies what the employee actually holds and stays out of the
        other module's table -- which is what §16 means by not building a second
        clearance system.
        """
        rows = await self.assignments.open_for_employee(employee_id)
        return [
            {
                "asset_id": row.asset.id,
                "asset_name": f"{row.asset.name} ({row.asset.category.name})",
                "asset_tag": row.asset.asset_tag,
                "assigned_date": row.assigned_date,
                "condition": row.asset.condition,
                "returnable": row.asset.category.returnable,
            }
            for row in rows
        ]

    async def resolve_from_clearance(
        self,
        asset_id: uuid.UUID,
        employee_id: uuid.UUID,
        outcome: str,
        *,
        actor_id: uuid.UUID,
        notes: str | None = None,
    ) -> None:
        """Apply an offboarding clearance decision to the real asset.

        The offboarding screen is where a leaver's laptop is actually marked
        returned, and this is what makes that mark true in the register rather
        than only on the case. A waiver is recorded as an event on the asset as
        well as being audited, because "written off during somebody's exit" is a
        fact about the laptop that outlives the case.
        """
        asset = await self.assets.get_detailed(asset_id)
        if asset is None:
            return

        if outcome == "returned":
            assignment = await self.assignments.open_for_asset(asset.id)
            if assignment is not None:
                await self.returns.add(
                    AssetReturn(
                        asset_id=asset.id,
                        assignment_id=assignment.id,
                        returned_by_id=employee_id,
                        received_by_id=actor_id,
                        return_date=date.today(),
                        condition_at_return=asset.condition,
                        notes=notes or "Returned during offboarding clearance.",
                    ),
                    actor_id=actor_id,
                )
                await self._close_assignment(assignment, actor_id=actor_id)
                await self._move(
                    asset, AssetStatus.AVAILABLE, actor_id=actor_id, condition=None, assignment_id=None
                )
            event, target = AssetEvent.RETURNED, AssetStatus.AVAILABLE
        elif outcome in {"damaged", "lost"}:
            target = AssetStatus.DAMAGED if outcome == "damaged" else AssetStatus.LOST
            assignment = await self.assignments.open_for_asset(asset.id)
            if assignment is not None:
                await self._close_assignment(assignment, actor_id=actor_id)
            await self._move(
                asset,
                target,
                actor_id=actor_id,
                condition=AssetCondition.DAMAGED if outcome == "damaged" else None,
                assignment_id=None,
            )
            event = AssetEvent.DAMAGED if outcome == "damaged" else AssetEvent.LOST
        elif outcome == "waived":
            event, target = AssetEvent.CLEARANCE_WAIVED, AssetStatus(asset.status)
            await self.audit.record_success(
                AuditAction.ASSET_CLEARANCE_WAIVED,
                actor_id=actor_id,
                entity_type="asset",
                entity_id=asset.id,
                description=f"Clearance waived for {asset.asset_code} during offboarding",
                context={"employee_id": str(employee_id), "notes": notes},
            )
        else:
            return

        await self._record(
            asset,
            event,
            actor_id=actor_id,
            employee_id=employee_id,
            new_value=target.value,
            notes=notes or f"Offboarding clearance: {outcome}",
        )

    # ==================================================================
    # Dashboard and reports
    # ==================================================================
    async def dashboard(self) -> AssetDashboard:
        counts = await self.assets.status_counts()
        expiring, expired = await self.assets.warranty_counts()
        return AssetDashboard(
            total=sum(counts.values()),
            available=counts.get(AssetStatus.AVAILABLE.value, 0),
            assigned=counts.get(AssetStatus.ASSIGNED.value, 0),
            reserved=counts.get(AssetStatus.RESERVED.value, 0),
            under_maintenance=counts.get(AssetStatus.UNDER_MAINTENANCE.value, 0),
            damaged=counts.get(AssetStatus.DAMAGED.value, 0),
            lost=counts.get(AssetStatus.LOST.value, 0),
            retired=counts.get(AssetStatus.RETIRED.value, 0),
            disposed=counts.get(AssetStatus.DISPOSED.value, 0),
            by_category=[
                CountByLabel(label=name, count=count)
                for name, count in await self.assets.counts_by_category()
            ],
            by_location=[
                CountByLabel(label=name, count=count)
                for name, count in await self.assets.counts_by_location()
            ],
            by_status=[CountByLabel(label=k, count=v) for k, v in sorted(counts.items())],
            warranty_expiring_soon=expiring,
            warranty_expired=expired,
            maintenance_due=await self.maintenance.due_count(),
            recent_assignments=[
                AssetHistoryEntry.model_validate(row)
                for row in await self.history.recent(AssetEvent.ASSIGNED)
            ],
            recent_returns=[
                AssetHistoryEntry.model_validate(row)
                for row in await self.history.recent(AssetEvent.RETURNED)
            ],
            recent_transfers=[
                AssetHistoryEntry.model_validate(row)
                for row in await self.history.recent(AssetEvent.TRANSFERRED)
            ],
        )

    async def export(self, report: str, fmt: str, *, actor_id: uuid.UUID) -> tuple[bytes, str]:
        """Build one of the reports in §20, as CSV or XLSX.

        Reuses the openpyxl/csv approach the employee and workforce exports
        already use rather than introducing a reporting library.
        """
        if report not in REPORTS:
            raise ValidationError(f"Unknown report: {report}", error_code="unknown_report")

        headers, rows = await self._report_rows(report)
        await self.audit.record_success(
            AuditAction.ASSET_EXPORTED,
            actor_id=actor_id,
            entity_type="asset",
            entity_id=None,
            description=f"Exported the {report} asset report as {fmt}",
        )

        if fmt == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(headers)
            writer.writerows(rows)
            return buffer.getvalue().encode("utf-8-sig"), "text/csv"

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = report[:31]
        sheet.append(headers)
        for row in rows:
            sheet.append(list(row))
        stream = io.BytesIO()
        workbook.save(stream)
        return (
            stream.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    async def _report_rows(self, report: str) -> tuple[list[str], list[tuple[Any, ...]]]:
        params = AssetListParams(page=1, page_size=100)
        if report == "assigned":
            params.assigned = True
        elif report == "available":
            params.status = AssetStatus.AVAILABLE
        elif report == "warranty":
            params.warranty_expiring = True

        if report == "maintenance":
            records, _ = await self.maintenance.search(MaintenanceListParams(page=1, page_size=100))
            return (
                ["Asset", "Tag", "Type", "Start", "End", "Vendor", "Cost", "Status"],
                [
                    (
                        record.asset.name,
                        record.asset.asset_tag,
                        record.maintenance_type,
                        record.start_date.isoformat(),
                        record.end_date.isoformat() if record.end_date else "",
                        record.vendor or "",
                        str(record.cost or ""),
                        record.status,
                    )
                    for record in records
                ],
            )

        if report == "movement":
            rows, _ = await self.history.movement(offset=0, limit=500)
            return (
                ["Date", "Event", "Asset", "Employee", "From", "To", "Notes"],
                [
                    (
                        row.created_at.date().isoformat(),
                        row.event,
                        str(row.asset_id),
                        str(row.employee_id or ""),
                        row.previous_value or "",
                        row.new_value or "",
                        row.notes or "",
                    )
                    for row in rows
                ],
            )

        if report == "lost_damaged":
            assets, _ = await self.assets.search(AssetListParams(page=1, page_size=200))
            assets = [
                asset
                for asset in assets
                if asset.status in {AssetStatus.LOST.value, AssetStatus.DAMAGED.value}
            ]
        else:
            assets, _ = await self.assets.search(params)

        holders = await self._holders_for({asset.id for asset in assets})
        return (
            [
                "Asset code",
                "Tag",
                "Name",
                "Category",
                "Brand",
                "Model",
                "Serial",
                "Status",
                "Condition",
                "Location",
                "Vendor",
                "Purchase date",
                "Warranty end",
                "Assigned to",
            ],
            [
                (
                    asset.asset_code,
                    asset.asset_tag,
                    asset.name,
                    asset.category.name,
                    asset.brand or "",
                    asset.model or "",
                    asset.serial_number or "",
                    asset.status,
                    asset.condition,
                    asset.location or "",
                    asset.vendor or "",
                    asset.purchase_date.isoformat() if asset.purchase_date else "",
                    asset.warranty_end.isoformat() if asset.warranty_end else "",
                    holders.get(asset.id, ""),
                )
                for asset in assets
            ],
        )

    # ==================================================================
    # Presentation
    # ==================================================================
    async def present_many(self, assets: Sequence[Asset]) -> list[AssetRead]:
        """Present a page of assets with one query for all their holders.

        ``present`` resolves a holder with two round trips -- the assignment,
        then the employee -- which is fine for the one asset a detail screen
        asks for and is an N+1 for a list of them. Measured: a 25-row page cost
        69 statements this way and 19 for a 5-row page, growing at 2.5 per row.

        This resolves every holder on the page in a single join, then presents
        from the map. The count no longer moves with the page size.
        """
        holders = await self._holder_summaries({asset.id for asset in assets})
        return [
            AssetRead(
                id=asset.id,
                asset_code=asset.asset_code,
                asset_tag=asset.asset_tag,
                name=asset.name,
                category=AssetCategoryRead.model_validate(asset.category),
                asset_type=asset.asset_type,
                brand=asset.brand,
                model=asset.model,
                serial_number=asset.serial_number,
                purchase_date=asset.purchase_date,
                purchase_cost=asset.purchase_cost,
                vendor=asset.vendor,
                warranty_start=asset.warranty_start,
                warranty_end=asset.warranty_end,
                warranty_provider=asset.warranty_provider,
                warranty_reference=asset.warranty_reference,
                warranty_state=self.warranty_state(asset),
                location=asset.location,
                condition=AssetCondition(asset.condition),
                status=AssetStatus(asset.status),
                notes=asset.notes,
                assigned_to=holders.get(asset.id, (None, None))[0],
                assigned_date=holders.get(asset.id, (None, None))[1],
                created_at=asset.created_at,
                updated_at=asset.updated_at,
            )
            for asset in assets
        ]

    async def _holder_summaries(
        self, asset_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[EmployeeSummary, date]]:
        """Every open holder for a set of assets, in one query."""
        if not asset_ids:
            return {}
        from sqlalchemy import select as sa_select

        rows = (
            await self.session.execute(
                sa_select(
                    AssetAssignment.asset_id,
                    AssetAssignment.assigned_date,
                    Employee.id,
                    Employee.employee_code,
                    Employee.first_name,
                    Employee.last_name,
                )
                .join(Employee, Employee.id == AssetAssignment.employee_id)
                .where(
                    AssetAssignment.asset_id.in_(asset_ids),
                    AssetAssignment.returned_at.is_(None),
                    AssetAssignment.deleted_at.is_(None),
                )
            )
        ).all()
        return {
            asset_id: (
                EmployeeSummary(id=employee_id, employee_code=code, full_name=f"{first} {last}"),
                assigned_date,
            )
            for asset_id, assigned_date, employee_id, code, first, last in rows
        }

    async def present(self, asset: Asset) -> AssetRead:
        holder, assigned_on = await self._holder_of(asset)
        return AssetRead(
            id=asset.id,
            asset_code=asset.asset_code,
            asset_tag=asset.asset_tag,
            name=asset.name,
            category=AssetCategoryRead.model_validate(asset.category),
            asset_type=asset.asset_type,
            brand=asset.brand,
            model=asset.model,
            serial_number=asset.serial_number,
            purchase_date=asset.purchase_date,
            purchase_cost=asset.purchase_cost,
            vendor=asset.vendor,
            warranty_start=asset.warranty_start,
            warranty_end=asset.warranty_end,
            warranty_provider=asset.warranty_provider,
            warranty_reference=asset.warranty_reference,
            warranty_state=self.warranty_state(asset),
            location=asset.location,
            condition=AssetCondition(asset.condition),
            status=AssetStatus(asset.status),
            notes=asset.notes,
            assigned_to=holder,
            assigned_date=assigned_on,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )

    async def present_detail(self, asset: Asset) -> AssetDetail:
        base = await self.present(asset)
        assignment = await self.assignments.open_for_asset(asset.id)
        assignment_read = None
        if assignment is not None:
            assignment_read = AssetAssignmentRead(
                id=assignment.id,
                asset_id=assignment.asset_id,
                employee=base.assigned_to,
                assigned_date=assignment.assigned_date,
                expected_return_date=assignment.expected_return_date,
                condition_at_assignment=AssetCondition(assignment.condition_at_assignment),
                assigned_by_id=assignment.assigned_by_id,
                notes=assignment.notes,
                returned_at=assignment.returned_at,
            )
        return AssetDetail(
            **base.model_dump(),
            current_assignment=assignment_read,
            history=[AssetHistoryEntry.model_validate(row) for row in await self.history.for_asset(asset.id)],
            maintenance=[
                MaintenanceRead.model_validate(row) for row in await self.maintenance.for_asset(asset.id)
            ],
            allowed_transitions=sorted(
                ASSET_STATUS_TRANSITIONS.get(AssetStatus(asset.status), frozenset()),
                key=lambda item: item.value,
            ),
        )

    @staticmethod
    def warranty_state(asset: Asset) -> str:
        """Derived on read, never stored -- a stored one is wrong the next morning."""
        if asset.warranty_end is None:
            return "none"
        today = date.today()
        if asset.warranty_end < today:
            return "expired"
        if asset.warranty_end <= today + timedelta(days=WARRANTY_WARNING_DAYS):
            return "expiring_soon"
        return "active"

    # ==================================================================
    # Internals
    # ==================================================================
    def _assert_transition(self, current: AssetStatus, target: AssetStatus) -> None:
        """The only gate on a status change.

        Consults the table rather than a chain of conditionals, so the rules are
        readable as data and a new status cannot silently become reachable from
        everywhere.
        """
        if current is target:
            return
        allowed = ASSET_STATUS_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            readable = ", ".join(sorted(item.value.replace("_", " ") for item in allowed)) or "nothing"
            raise ConflictError(
                f"An asset that is {current.value.replace('_', ' ')} cannot become "
                f"{target.value.replace('_', ' ')}. It can move to: {readable}.",
                error_code="invalid_status_transition",
            )

    async def _move(
        self,
        asset: Asset,
        target: AssetStatus,
        *,
        actor_id: uuid.UUID,
        condition: AssetCondition | None,
        assignment_id: Any,
    ) -> None:
        """Apply a status change after checking it is permitted.

        ``assignment_id`` uses ``...`` to mean "leave it alone", which is
        distinct from ``None`` meaning "clear it" -- the difference between
        completing maintenance on an unassigned asset and returning one.
        """
        self._assert_transition(AssetStatus(asset.status), target)
        changes: dict[str, Any] = {"status": target.value}
        if condition is not None:
            changes["condition"] = condition.value
        if assignment_id is not ...:
            changes["current_assignment_id"] = assignment_id
        await self.assets.update(asset, changes, actor_id=actor_id)

    async def _close_assignment(self, assignment: AssetAssignment, *, actor_id: uuid.UUID) -> None:
        await self.assignments.update(assignment, {"returned_at": utc_now()}, actor_id=actor_id)

    async def _record(
        self,
        asset: Asset,
        event: AssetEvent,
        *,
        actor_id: uuid.UUID,
        employee_id: uuid.UUID | None = None,
        previous_value: str | None = None,
        new_value: str | None = None,
        notes: str | None = None,
    ) -> None:
        await self.history.add(
            AssetHistory(
                asset_id=asset.id,
                event=event.value,
                employee_id=employee_id,
                previous_value=previous_value,
                new_value=new_value,
                notes=notes,
            ),
            actor_id=actor_id,
        )

    async def _sync_clearance(self, asset: Asset, employee_id: uuid.UUID, condition: AssetCondition) -> None:
        """Keep an open offboarding clearance row in step with a return here.

        The two directions of the integration are not symmetric, and this is the
        awkward one. When HR ticks a row on the offboarding screen, that call
        comes through ``resolve_from_clearance`` and this module updates the
        asset -- clean, because offboarding owns its own table and is doing the
        writing. But an administrator can also process the return in the asset
        module, and if nothing did this the case would still claim the laptop
        was outstanding after it had been handed back.

        So this reaches into ``asset_clearance`` for the narrow case of a row
        that is (a) linked to this asset, (b) for this employee's case and (c)
        still open. It is a deliberate, bounded cross-module write rather than a
        second clearance system -- which is what §16 forbids.
        """
        from sqlalchemy import select as sa_select

        from app.models.offboarding import AssetClearance, OffboardingCase

        rows = (
            (
                await self.session.execute(
                    sa_select(AssetClearance)
                    .join(OffboardingCase, OffboardingCase.id == AssetClearance.case_id)
                    .where(
                        AssetClearance.asset_id == asset.id,
                        AssetClearance.deleted_at.is_(None),
                        AssetClearance.status == AssetReturnStatus.ASSIGNED.value,
                        OffboardingCase.employee_id == employee_id,
                        OffboardingCase.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.status = (
                AssetReturnStatus.DAMAGED.value
                if condition is AssetCondition.DAMAGED
                else AssetReturnStatus.RETURNED.value
            )
            row.return_date = date.today()
            row.condition = condition.value
        if rows:
            await self.session.flush()
            logger.info(
                "Offboarding clearance updated from an asset return",
                extra={"asset_id": str(asset.id), "rows": len(rows)},
            )

    async def _assert_category_usable(self, category_id: uuid.UUID) -> None:
        category = await self.categories.get(category_id)
        if category is None:
            raise ValidationError("That asset category does not exist.", error_code="invalid_category")
        if category.status != RecordStatus.ACTIVE.value:
            raise ValidationError(
                f'The category "{category.name}" is inactive and cannot be used for new assets.',
                error_code="inactive_category",
            )

    async def _assert_tag_available(self, tag: str, *, exclude_id: uuid.UUID | None = None) -> None:
        existing = await self.assets.by_tag(tag)
        if existing is not None and existing.id != exclude_id:
            raise ConflictError(
                f'An asset with the tag "{tag.strip()}" already exists ({existing.asset_code}).',
                error_code="duplicate_asset_tag",
            )

    async def _assert_serial_available(self, serial: str, *, exclude_id: uuid.UUID | None = None) -> None:
        existing = await self.assets.by_serial(serial)
        if existing is not None and existing.id != exclude_id:
            raise ConflictError(
                f'An asset with the serial number "{serial.strip()}" already exists '
                f"({existing.asset_code}).",
                error_code="duplicate_serial_number",
            )

    async def _assert_employee_active(self, employee_id: uuid.UUID) -> Employee:
        employee = await self.employees.get(employee_id)
        if employee is None:
            raise ValidationError("That employee does not exist.", error_code="invalid_employee")
        if not employee.is_employed:
            raise ConflictError(
                f"{employee.full_name} has left, so an asset cannot be issued to them.",
                error_code="employee_not_active",
            )
        return employee

    async def _assert_asset_in_scope(self, asset: Asset, scope: EmployeeScope) -> None:
        """A scoped caller reaches an asset only through the person holding it."""
        assignment = await self.assignments.open_for_asset(asset.id)
        if assignment is None or not scope.allows(assignment.employee_id):
            from app.core.exceptions import PermissionDeniedError

            raise PermissionDeniedError(
                "You can only see assets held by yourself and the people who report to you.",
                details=[{"code": "outside_your_team", "message": "asset_id"}],
            )

    async def _holder_of(self, asset: Asset) -> tuple[EmployeeSummary | None, date | None]:
        if asset.current_assignment_id is None:
            return None, None
        assignment = await self.assignments.get(asset.current_assignment_id)
        if assignment is None or assignment.returned_at is not None:
            return None, None
        employee = await self.employees.get(assignment.employee_id)
        if employee is None:
            return None, assignment.assigned_date
        return (
            EmployeeSummary(
                id=employee.id, employee_code=employee.employee_code, full_name=employee.full_name
            ),
            assignment.assigned_date,
        )

    async def _holders_for(self, asset_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Holder names for a page of assets, in one query rather than per row."""
        if not asset_ids:
            return {}
        from sqlalchemy import select

        # first_name/last_name rather than `full_name`: the latter is a Python
        # property on the model and does not exist in the database.
        rows = (
            await self.session.execute(
                select(AssetAssignment.asset_id, Employee.first_name, Employee.last_name)
                .join(Employee, Employee.id == AssetAssignment.employee_id)
                .where(
                    AssetAssignment.asset_id.in_(asset_ids),
                    AssetAssignment.returned_at.is_(None),
                    AssetAssignment.deleted_at.is_(None),
                )
            )
        ).all()
        return {asset_id: f"{first} {last}" for asset_id, first, last in rows}

    async def _notify(self, employee: Employee, title: str, message: str) -> None:
        if not employee.user_id:
            return
        await self.notifications.add(
            Notification(
                user_id=employee.user_id,
                title=title,
                message=message,
                link="/employee/assets",
                notification_type="asset",
            )
        )

    async def _reload(self, asset_id: uuid.UUID) -> Asset:
        asset = await self.assets.get_detailed(asset_id)
        if asset is None:  # pragma: no cover - defensive
            raise NotFoundError("Asset")
        return asset
