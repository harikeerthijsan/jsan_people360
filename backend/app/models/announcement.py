"""Announcement persistence models.

Two tables, and the decision worth stating is what this is *not*: it is not a
second notification system. The platform already has one, and an announcement
uses it — publishing fans out notifications to the audience. What this adds is
the thing the notification points at: a durable, addressable notice with an
author, an audience, a lifetime and a record of who has read it.

The distinction matters because the two answer different questions. A
notification is "something happened that concerns you", is personal, and is
disposable once read. An announcement is "this is the company's position on
something", is the same text for everybody it reaches, and has to still be
readable in six months when somebody asks what they were told.

**Targeting is by organizational unit, not by role.** "Everyone in Chennai" and
"the engineering business unit" are the questions actually asked. A role-based
audience would send the canteen notice to whoever happens to hold
``leave:approve``, which is nobody's idea of an audience.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.enums import (
    ANNOUNCEMENT_AUDIENCE_SQL_VALUES,
    ANNOUNCEMENT_PRIORITY_SQL_VALUES,
    ANNOUNCEMENT_STATUS_SQL_VALUES,
    AnnouncementAudience,
    AnnouncementPriority,
    AnnouncementStatus,
)


class Announcement(Base, AuditableBase):
    """One notice, addressed to some part of the organization."""

    __tablename__ = "announcements"
    __table_args__ = (
        Index("ix_announcements_status_published", "status", "published_at"),
        Index("ix_announcements_audience", "audience"),
        CheckConstraint(f"status IN ({ANNOUNCEMENT_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint(f"audience IN ({ANNOUNCEMENT_AUDIENCE_SQL_VALUES})", name="audience"),
        CheckConstraint(f"priority IN ({ANNOUNCEMENT_PRIORITY_SQL_VALUES})", name="priority"),
        CheckConstraint(
            "expires_at IS NULL OR published_at IS NULL OR expires_at > published_at",
            name="expiry_after_publication",
        ),
        {"comment": "Company notices and their audience."},
    )

    title: Mapped[str] = mapped_column(String(200), index=True)
    body: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(
        String(300), doc="Shown on the dashboard card; the body is the full notice."
    )

    audience: Mapped[str] = mapped_column(
        String(20), default=AnnouncementAudience.ALL, server_default=AnnouncementAudience.ALL.value
    )
    #: The business units, teams or locations this is addressed to. Empty for
    #: ``ALL``. A list rather than one id because "the Chennai and Bangalore
    #: offices" is one notice, not two.
    target_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")

    priority: Mapped[str] = mapped_column(
        String(20),
        default=AnnouncementPriority.NORMAL,
        server_default=AnnouncementPriority.NORMAL.value,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=AnnouncementStatus.DRAFT,
        server_default=AnnouncementStatus.DRAFT.value,
        index=True,
    )

    #: Pinned notices sort first regardless of date. A separate flag rather than
    #: a fourth priority, because "urgent" and "keep this at the top" are
    #: different requests -- the office move is pinned for a month and is not
    #: urgent on any given morning.
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    #: Whether the reader is asked to confirm they have seen it. Off by default:
    #: asking for an acknowledgement on every notice trains people to click it
    #: without reading, which destroys the value of the ones that matter.
    requires_acknowledgement: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    #: When it becomes visible. Set on publish, or ahead of time when scheduled.
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    attachment_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")

    acknowledgements: Mapped[list[AnnouncementAcknowledgement]] = relationship(
        back_populates="announcement", lazy="selectin"
    )


class AnnouncementAcknowledgement(Base, AuditableBase):
    """One person confirming they have read one notice.

    Unique on (announcement, employee): acknowledging twice is not twice as
    acknowledged, and the constraint is what makes "how many people have read
    the safety policy" a number rather than an estimate.
    """

    __tablename__ = "announcement_acknowledgements"
    __table_args__ = (
        UniqueConstraint("announcement_id", "employee_id", name="uq_announcement_acknowledgements_once"),
        Index("ix_announcement_acks_employee", "employee_id"),
        {"comment": "Read receipts against an announcement."},
    )

    announcement_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("announcements.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    announcement: Mapped[Announcement] = relationship(back_populates="acknowledgements")
