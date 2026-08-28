"""Asset management schemas.

Two properties shape this module.

**No write schema moves custody by naming a holder.** There is no
``assigned_to`` on :class:`AssetUpdate`. Custody changes through
:class:`AssetAssign`, :class:`AssetReturn` and :class:`AssetTransfer`, each of
which writes a transaction — because §8 of the brief is explicit that editing an
asset must not be able to destroy its history, and the way to guarantee that is
to leave the field out of the edit model entirely.

**The employee's view is a separate model.** :class:`MyAsset` carries what a
person needs to know about a thing in their possession. It has no purchase cost,
no vendor and no notes — an employee has no business reading what the company
paid for their laptop, and a schema that never declares the field cannot leak it
by forgetting to.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    AssetCondition,
    AssetEvent,
    AssetStatus,
    MaintenanceStatus,
    MaintenanceType,
    RecordStatus,
)
from app.schemas.common import PaginationParams

_MAX_NOTES = 4000
_MAX_COST = Decimal("99999999.99")


# ----------------------------------------------------------------------
# Categories
# ----------------------------------------------------------------------
class AssetCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    description: str | None
    returnable: bool
    status: RecordStatus


class AssetCategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = Field(default=None, max_length=_MAX_NOTES)
    returnable: bool = Field(
        default=True,
        description="Whether a thing in this category is expected back when its holder leaves.",
    )


class AssetCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=_MAX_NOTES)
    returnable: bool | None = None
    status: RecordStatus | None = None


# ----------------------------------------------------------------------
# The asset itself
# ----------------------------------------------------------------------
class EmployeeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    full_name: str


class AssetBase(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    category_id: uuid.UUID
    asset_type: str | None = Field(default=None, max_length=60)
    brand: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=80)
    serial_number: str | None = Field(default=None, max_length=120)
    purchase_date: date | None = None
    purchase_cost: Decimal | None = Field(default=None, ge=0, le=_MAX_COST, decimal_places=2)
    vendor: str | None = Field(default=None, max_length=150)
    warranty_start: date | None = None
    warranty_end: date | None = None
    warranty_provider: str | None = Field(default=None, max_length=150)
    warranty_reference: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=_MAX_NOTES)

    @model_validator(mode="after")
    def dates_are_ordered(self) -> Self:
        if self.warranty_start and self.warranty_end and self.warranty_end < self.warranty_start:
            raise ValueError("The warranty end date cannot be before the warranty start date")
        if self.purchase_date and self.warranty_start and self.warranty_start < self.purchase_date:
            raise ValueError("The warranty cannot start before the asset was purchased")
        if self.purchase_date and self.purchase_date > date.today():
            raise ValueError("The purchase date cannot be in the future")
        return self


class AssetCreate(AssetBase):
    asset_tag: str = Field(min_length=1, max_length=60)
    condition: AssetCondition
    status: AssetStatus = Field(
        default=AssetStatus.AVAILABLE,
        description="Only available, reserved or under_maintenance may be set at creation; an asset "
        "cannot be born assigned, because there would be no assignment record behind it.",
    )


class AssetUpdate(AssetBase):
    """Details only.

    Deliberately carries no ``status``, no ``condition`` and no holder. Status
    moves through the transition table, condition is recorded at a custody
    event, and custody moves through assign/return/transfer -- each of which
    leaves a record. Allowing any of the three here would let an edit rewrite
    history, which §8 forbids.
    """

    name: str | None = Field(default=None, min_length=2, max_length=150)  # type: ignore[assignment]
    category_id: uuid.UUID | None = None  # type: ignore[assignment]
    asset_tag: str | None = Field(default=None, min_length=1, max_length=60)


class AssetAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    employee: EmployeeSummary | None = None
    assigned_date: date
    expected_return_date: date | None
    condition_at_assignment: AssetCondition
    assigned_by_id: uuid.UUID | None
    notes: str | None
    returned_at: datetime | None


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_code: str
    asset_tag: str
    name: str
    category: AssetCategoryRead
    asset_type: str | None
    brand: str | None
    model: str | None
    serial_number: str | None
    purchase_date: date | None
    purchase_cost: Decimal | None
    vendor: str | None
    warranty_start: date | None
    warranty_end: date | None
    warranty_provider: str | None
    warranty_reference: str | None
    warranty_state: str = Field(
        default="none", description="none, active, expiring_soon or expired. Derived, never stored."
    )
    location: str | None
    condition: AssetCondition
    status: AssetStatus
    notes: str | None
    assigned_to: EmployeeSummary | None = None
    assigned_date: date | None = None
    created_at: datetime
    updated_at: datetime


class AssetDetail(AssetRead):
    """The single-asset view: everything above, plus the trail."""

    current_assignment: AssetAssignmentRead | None = None
    history: list[AssetHistoryEntry] = []
    maintenance: list[MaintenanceRead] = []
    allowed_transitions: list[AssetStatus] = Field(
        default_factory=list,
        description="Statuses this asset may move to from where it is. Computed server-side so the "
        "client never has to hold a copy of the transition table.",
    )


class AssetListParams(PaginationParams):
    search: str | None = Field(
        default=None, max_length=100, description="Matches tag, code, name, serial or model."
    )
    category_id: uuid.UUID | None = None
    status: AssetStatus | None = None
    condition: AssetCondition | None = None
    location: str | None = Field(default=None, max_length=150)
    vendor: str | None = Field(default=None, max_length=150)
    assigned: bool | None = Field(
        default=None, description="True for assets currently held by somebody, False for unassigned."
    )
    employee_id: uuid.UUID | None = Field(
        default=None,
        description="Narrow to one holder. Still subject to the caller's scope -- supplying an id "
        "never widens what is returned.",
    )
    warranty_expiring: bool | None = Field(
        default=None, description="Only assets whose warranty expires within the warning window."
    )


# ----------------------------------------------------------------------
# Custody
# ----------------------------------------------------------------------
class AssetAssign(BaseModel):
    employee_id: uuid.UUID
    assigned_date: date = Field(default_factory=date.today)
    condition_at_assignment: AssetCondition
    expected_return_date: date | None = None
    notes: str | None = Field(default=None, max_length=_MAX_NOTES)

    @model_validator(mode="after")
    def return_is_after_assignment(self) -> Self:
        if self.expected_return_date and self.expected_return_date < self.assigned_date:
            raise ValueError("The expected return date cannot be before the assignment date")
        return self


class AssetReturnInput(BaseModel):
    return_date: date = Field(default_factory=date.today)
    condition_at_return: AssetCondition
    damage_details: str | None = Field(default=None, max_length=_MAX_NOTES)
    missing_accessories: str | None = Field(default=None, max_length=_MAX_NOTES)
    notes: str | None = Field(default=None, max_length=_MAX_NOTES)
    resulting_status: AssetStatus | None = Field(
        default=None,
        description="Where the asset lands. Defaults to available, or under_maintenance when it comes "
        "back damaged.",
    )


class AssetTransferInput(BaseModel):
    to_employee_id: uuid.UUID
    transfer_date: date = Field(default_factory=date.today)
    condition_at_transfer: AssetCondition
    reason: str | None = Field(default=None, max_length=_MAX_NOTES)
    notes: str | None = Field(default=None, max_length=_MAX_NOTES)


class AssetStatusChange(BaseModel):
    status: AssetStatus
    reason: str = Field(min_length=3, max_length=_MAX_NOTES)
    condition: AssetCondition | None = None


class AssetReturnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    assignment_id: uuid.UUID
    returned_by_id: uuid.UUID
    received_by_id: uuid.UUID | None
    return_date: date
    condition_at_return: AssetCondition
    damage_details: str | None
    missing_accessories: str | None
    notes: str | None


class AssetTransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    from_employee_id: uuid.UUID
    to_employee_id: uuid.UUID
    transfer_date: date
    condition_at_transfer: AssetCondition
    reason: str | None
    approved_by_id: uuid.UUID | None
    notes: str | None


# ----------------------------------------------------------------------
# Maintenance
# ----------------------------------------------------------------------
class MaintenanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    maintenance_type: MaintenanceType
    start_date: date
    end_date: date | None
    vendor: str | None
    cost: Decimal | None
    description: str | None
    status: MaintenanceStatus
    notes: str | None


class MaintenanceCreate(BaseModel):
    asset_id: uuid.UUID
    maintenance_type: MaintenanceType
    start_date: date = Field(default_factory=date.today)
    end_date: date | None = None
    vendor: str | None = Field(default=None, max_length=150)
    cost: Decimal | None = Field(default=None, ge=0, le=_MAX_COST, decimal_places=2)
    description: str | None = Field(default=None, max_length=_MAX_NOTES)
    notes: str | None = Field(default=None, max_length=_MAX_NOTES)
    start_now: bool = Field(
        default=False,
        description="Begin immediately, putting the asset under maintenance. Otherwise it is scheduled.",
    )

    @model_validator(mode="after")
    def window_is_ordered(self) -> Self:
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("The end date cannot be before the start date")
        return self


class MaintenanceUpdate(BaseModel):
    status: MaintenanceStatus
    end_date: date | None = None
    cost: Decimal | None = Field(default=None, ge=0, le=_MAX_COST, decimal_places=2)
    vendor: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=_MAX_NOTES)
    resulting_condition: AssetCondition | None = Field(
        default=None, description="The asset's condition once the work is finished."
    )
    resulting_status: AssetStatus | None = Field(
        default=None, description="Where the asset lands on completion. Defaults to available."
    )


class MaintenanceListParams(PaginationParams):
    asset_id: uuid.UUID | None = None
    status: MaintenanceStatus | None = None
    maintenance_type: MaintenanceType | None = None
    due_only: bool | None = Field(
        default=None, description="Scheduled work whose start date has arrived or passed."
    )


# ----------------------------------------------------------------------
# History
# ----------------------------------------------------------------------
class AssetHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event: AssetEvent
    employee_id: uuid.UUID | None
    previous_value: str | None
    new_value: str | None
    notes: str | None
    created_at: datetime
    created_by: uuid.UUID | None


# ----------------------------------------------------------------------
# The employee's own view
# ----------------------------------------------------------------------
class MyAsset(BaseModel):
    """What a person may see about a thing in their possession.

    No purchase cost, no vendor, no internal notes: an employee has no business
    reading what the company paid for their laptop, and the omission is the
    protection rather than a filter somewhere else.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_code: str
    asset_tag: str
    name: str
    category: str
    brand: str | None
    model: str | None
    serial_number: str | None
    assigned_date: date
    expected_return_date: date | None
    condition_at_assignment: AssetCondition
    status: AssetStatus


class TeamAssetRow(BaseModel):
    """One direct report's asset, on the manager screen."""

    model_config = ConfigDict(from_attributes=True)

    assignment_id: uuid.UUID
    asset_id: uuid.UUID
    employee: EmployeeSummary
    asset_code: str
    asset_tag: str
    name: str
    category: str
    status: AssetStatus
    condition: AssetCondition
    assigned_date: date
    expected_return_date: date | None


# ----------------------------------------------------------------------
# Dashboard and reports
# ----------------------------------------------------------------------
class CountByLabel(BaseModel):
    label: str
    count: int


class AssetDashboard(BaseModel):
    total: int
    available: int
    assigned: int
    reserved: int
    under_maintenance: int
    damaged: int
    lost: int
    retired: int
    disposed: int

    by_category: list[CountByLabel] = []
    by_location: list[CountByLabel] = []
    by_status: list[CountByLabel] = []

    warranty_expiring_soon: int = 0
    warranty_expired: int = 0
    maintenance_due: int = 0

    recent_assignments: list[AssetHistoryEntry] = []
    recent_returns: list[AssetHistoryEntry] = []
    recent_transfers: list[AssetHistoryEntry] = []


# ----------------------------------------------------------------------
# Offboarding
# ----------------------------------------------------------------------
class EmployeeAssetClearanceRow(BaseModel):
    """One asset a leaver is holding, as the clearance screen shows it."""

    model_config = ConfigDict(from_attributes=True)

    asset_id: uuid.UUID
    asset_code: str
    asset_tag: str
    name: str
    category: str
    assigned_date: date
    condition: AssetCondition
    returnable: bool = Field(description="Whether this category blocks completion until it is resolved.")
    clearance_status: str = Field(description="assigned, returned, damaged, lost or waived.")


AssetDetail.model_rebuild()
