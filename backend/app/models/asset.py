"""Asset register persistence models.

Seven tables, and the shape follows one decision: **the asset row holds the
current state, and the transaction tables hold what happened.** An assignment,
a return and a transfer are each a record of an event, not a column being
overwritten.

That is the difference between an inventory and a register. Setting
``assigned_to = somebody_else`` answers "who has it now" and destroys "who had
it in March", which is the question an asset system exists to answer -- usually
months after the person has left and the laptop has been disposed of.

So ``Asset.current_assignment_id`` is a denormalised pointer *into* the
assignment table rather than a foreign key to an employee. It exists to keep the
list screen from doing a subquery per row; the truth is the assignment record,
and :class:`AssetHistory` is the complete account.

Nothing here is deleted. Retirement and disposal are statuses, and the history
outlives both.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.enums import (
    ASSET_CONDITION_SQL_VALUES,
    ASSET_EVENT_SQL_VALUES,
    ASSET_STATUS_SQL_VALUES,
    MAINTENANCE_STATUS_SQL_VALUES,
    MAINTENANCE_TYPE_SQL_VALUES,
    RECORD_STATUS_SQL_VALUES,
    AssetStatus,
    MaintenanceStatus,
    RecordStatus,
)

#: ``AST-000001`` onwards, from a PostgreSQL sequence, on the same pattern as
#: every other generated identifier here. A sequence rather than a count of
#: existing rows so two concurrent creates can never be handed the same number.
ASSET_CODE_SEQUENCE = "assets_code_seq"
ASSET_CODE_DEFAULT = f"'AST-' || lpad(nextval('{ASSET_CODE_SEQUENCE}')::text, 6, '0')"


class AssetCategory(Base, AuditableBase):
    """Configurable category master -- laptop, monitor, access card.

    A table rather than an enum because §2 of the brief is explicit that the
    frontend must not hardcode the list, and because the set genuinely varies by
    organization. Deactivated rather than deleted, like every other master here:
    a category still referenced by a retired laptop has to keep resolving to a
    name years later.
    """

    __tablename__ = "asset_categories"
    __table_args__ = (
        UniqueConstraint("code", name="uq_asset_categories_code"),
        CheckConstraint(f"status IN ({RECORD_STATUS_SQL_VALUES})", name="status"),
        {"comment": "Configurable asset categories."},
    )

    name: Mapped[str] = mapped_column(String(100), index=True)
    code: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    #: Whether a thing in this category is expected back at exit. A laptop is; a
    #: consumable headset may not be. Drives which rows the offboarding
    #: clearance treats as blocking.
    returnable: Mapped[bool] = mapped_column(
        default=True, server_default="true", doc="Expected back when the holder leaves."
    )
    status: Mapped[str] = mapped_column(
        String(20), default=RecordStatus.ACTIVE, server_default=RecordStatus.ACTIVE.value, index=True
    )


class Asset(Base, AuditableBase):
    """One physical thing the company owns."""

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("asset_tag", name="uq_assets_asset_tag"),
        Index("ix_assets_status_category", "status", "category_id"),
        Index("ix_assets_condition", "condition"),
        CheckConstraint(f"status IN ({ASSET_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint(f"condition IN ({ASSET_CONDITION_SQL_VALUES})", name="condition"),
        CheckConstraint("purchase_cost IS NULL OR purchase_cost >= 0", name="purchase_cost_non_negative"),
        CheckConstraint(
            "warranty_end IS NULL OR warranty_start IS NULL OR warranty_end >= warranty_start",
            name="warranty_window_ordered",
        ),
        {"comment": "The asset register: one row per physical thing owned."},
    )

    asset_code: Mapped[str] = mapped_column(
        String(20), unique=True, server_default=text(ASSET_CODE_DEFAULT), doc="System generated: AST-000001."
    )
    #: The label physically stuck to the thing. Unique, supplied by the
    #: organization, and the identifier a person actually reads off a laptop.
    asset_tag: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("asset_categories.id", ondelete="RESTRICT"), index=True
    )
    asset_type: Mapped[str | None] = mapped_column(String(60))
    brand: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80))
    #: Unique *where present*. Enforced by a partial index rather than a plain
    #: UNIQUE, because most accessories have no serial and several NULLs are not
    #: a duplicate of each other -- see the migration.
    serial_number: Mapped[str | None] = mapped_column(String(120), index=True)

    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    vendor: Mapped[str | None] = mapped_column(String(150), index=True)

    warranty_start: Mapped[date | None] = mapped_column(Date)
    warranty_end: Mapped[date | None] = mapped_column(Date, index=True)
    warranty_provider: Mapped[str | None] = mapped_column(String(150))
    warranty_reference: Mapped[str | None] = mapped_column(String(120))

    location: Mapped[str | None] = mapped_column(String(150), index=True)
    condition: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(
        String(30), default=AssetStatus.AVAILABLE, server_default=AssetStatus.AVAILABLE.value, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    #: Points at the open assignment, or NULL when nobody holds it.
    #:
    #: Denormalised on purpose and kept honest in one place
    #: (``AssetService._set_current_assignment``). Without it, listing 50 assets
    #: with their holders is 50 subqueries; with it, the list is one join. It is
    #: never the source of truth -- ``asset_assignments`` is.
    current_assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("asset_assignments.id", ondelete="SET NULL", use_alter=True),
        doc="The open assignment, or NULL. Denormalised; asset_assignments is the truth.",
    )

    category: Mapped[AssetCategory] = relationship(lazy="joined")


class AssetAssignment(Base, AuditableBase):
    """One period during which one employee held one asset.

    Closed rather than deleted when the asset comes back: ``returned_at`` being
    set is what ends it. Two open assignments for one asset is the condition the
    partial unique index in the migration makes impossible.
    """

    __tablename__ = "asset_assignments"
    __table_args__ = (
        Index("ix_asset_assignments_employee_returned", "employee_id", "returned_at"),
        Index("ix_asset_assignments_asset_assigned", "asset_id", "assigned_date"),
        CheckConstraint(
            f"condition_at_assignment IN ({ASSET_CONDITION_SQL_VALUES})", name="condition_at_assignment"
        ),
        {"comment": "Custody: who held which asset, and when."},
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    assigned_date: Mapped[date] = mapped_column(Date)
    expected_return_date: Mapped[date | None] = mapped_column(Date)
    condition_at_assignment: Mapped[str] = mapped_column(String(20))
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    #: Set when custody ends, by a return or by a transfer out. NULL means the
    #: employee still has it.
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    asset: Mapped[Asset] = relationship(foreign_keys=[asset_id], lazy="joined")


class AssetReturn(Base, AuditableBase):
    """A thing coming back, and the state it came back in.

    A transaction rather than a column change on the assignment, because a
    return carries facts the assignment never had: who physically received it,
    what was missing from the box, what the damage was.
    """

    __tablename__ = "asset_returns"
    __table_args__ = (
        CheckConstraint(f"condition_at_return IN ({ASSET_CONDITION_SQL_VALUES})", name="condition_at_return"),
        {"comment": "Return transactions against an assignment."},
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("asset_assignments.id", ondelete="RESTRICT"), index=True
    )
    returned_by_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    return_date: Mapped[date] = mapped_column(Date)
    condition_at_return: Mapped[str] = mapped_column(String(20))
    damage_details: Mapped[str | None] = mapped_column(Text)
    missing_accessories: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class AssetTransfer(Base, AuditableBase):
    """Custody moving from one employee to another without passing through
    stores.

    Recorded as its own event rather than as a return plus an assignment,
    because "A handed it straight to B" and "A gave it back and B was issued one
    later" are different facts, and the second is not what happened.
    """

    __tablename__ = "asset_transfers"
    __table_args__ = (
        Index("ix_asset_transfers_asset_date", "asset_id", "transfer_date"),
        CheckConstraint(f"condition_at_transfer IN ({ASSET_CONDITION_SQL_VALUES})", name="condition"),
        CheckConstraint("from_employee_id <> to_employee_id", name="transfer_changes_holder"),
        {"comment": "Custody moving directly between two employees."},
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    from_employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    to_employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    transfer_date: Mapped[date] = mapped_column(Date)
    condition_at_transfer: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)


class AssetMaintenance(Base, AuditableBase):
    """A repair, an upgrade or an inspection.

    Drives the asset's status: starting one puts the asset under maintenance,
    completing one releases it. That coupling lives in the service, not here --
    a row in this table is a record, not a trigger.
    """

    __tablename__ = "asset_maintenance"
    __table_args__ = (
        Index("ix_asset_maintenance_asset_status", "asset_id", "status"),
        CheckConstraint(f"status IN ({MAINTENANCE_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint(f"maintenance_type IN ({MAINTENANCE_TYPE_SQL_VALUES})", name="maintenance_type"),
        CheckConstraint("cost IS NULL OR cost >= 0", name="cost_non_negative"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="window_ordered"),
        {"comment": "Maintenance records against an asset."},
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    maintenance_type: Mapped[str] = mapped_column(String(30), index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date)
    vendor: Mapped[str | None] = mapped_column(String(150))
    cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20),
        default=MaintenanceStatus.SCHEDULED,
        server_default=MaintenanceStatus.SCHEDULED.value,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)

    asset: Mapped[Asset] = relationship(lazy="joined")


class AssetHistory(Base, AuditableBase):
    """Append-only. Every event in one asset's life, in one place.

    Distinct from the audit log, which answers "what did this *user* do". This
    answers "what happened to this *thing*", which is the question asked when a
    laptop turns up in a drawer with no label and somebody has to work out whose
    it was. Neither is derivable from the other.

    ``previous_value`` and ``new_value`` are text rather than a typed pair,
    because the column being described changes per event -- a status, a holder,
    a condition -- and a history table that needed a schema change per new event
    type would stop being written to.
    """

    __tablename__ = "asset_history"
    __table_args__ = (
        Index("ix_asset_history_asset_created", "asset_id", "created_at"),
        CheckConstraint(f"event IN ({ASSET_EVENT_SQL_VALUES})", name="event"),
        {"comment": "Append-only event log for one asset."},
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(40), index=True)
    #: The employee the event concerned, when it concerned one.
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    previous_value: Mapped[str | None] = mapped_column(String(200))
    new_value: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
