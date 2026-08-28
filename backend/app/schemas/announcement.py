"""Announcement schemas.

One property shapes this module: **a draft is not an announcement**. Everything
an employee can read comes from :class:`MyAnnouncement`, which is only ever
built from published rows, and it carries no author, no audience configuration
and no acknowledgement roll. Who a notice was addressed to and who has not yet
read it are the sender's business, not the reader's.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import AnnouncementAudience, AnnouncementPriority, AnnouncementStatus
from app.schemas.common import PaginationParams

_MAX_BODY = 20000


class AnnouncementBase(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=1, max_length=_MAX_BODY)
    summary: str | None = Field(default=None, max_length=300, description="Shown on the dashboard card.")
    audience: AnnouncementAudience = AnnouncementAudience.ALL
    target_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Business units, teams or locations. Empty when the audience is everybody.",
    )
    priority: AnnouncementPriority = AnnouncementPriority.NORMAL
    pinned: bool = False
    requires_acknowledgement: bool = False
    publish_at: datetime | None = Field(
        default=None, description="Schedule it. Omit to publish immediately when published."
    )
    expires_at: datetime | None = None
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def audience_matches_targets(self) -> Self:
        if self.audience is AnnouncementAudience.ALL and self.target_ids:
            raise ValueError("An announcement addressed to everybody cannot also name targets")
        if self.audience is not AnnouncementAudience.ALL and not self.target_ids:
            raise ValueError(
                f"An announcement addressed to a {self.audience.value.replace('_', ' ')} "
                "must name at least one"
            )
        if self.expires_at and self.publish_at and self.expires_at <= self.publish_at:
            raise ValueError("An announcement cannot expire before it is published")
        return self


class AnnouncementCreate(AnnouncementBase):
    pass


class AnnouncementUpdate(BaseModel):
    """Amend a notice. Status moves through publish and archive, not through here."""

    title: str | None = Field(default=None, min_length=3, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=_MAX_BODY)
    summary: str | None = Field(default=None, max_length=300)
    audience: AnnouncementAudience | None = None
    target_ids: list[uuid.UUID] | None = None
    priority: AnnouncementPriority | None = None
    pinned: bool | None = None
    requires_acknowledgement: bool | None = None
    publish_at: datetime | None = None
    expires_at: datetime | None = None
    attachment_ids: list[uuid.UUID] | None = None


class AnnouncementPublish(BaseModel):
    publish_at: datetime | None = Field(
        default=None,
        description="Schedule for later. Omit to publish now, which is the usual case.",
    )


class AcknowledgementRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: uuid.UUID
    employee_name: str
    acknowledged_at: datetime


class AnnouncementRead(BaseModel):
    """The author's view: everything, including who has not read it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str
    summary: str | None
    audience: AnnouncementAudience
    target_ids: list[uuid.UUID] = []
    priority: AnnouncementPriority
    status: AnnouncementStatus
    pinned: bool
    requires_acknowledgement: bool
    publish_at: datetime | None
    published_at: datetime | None
    expires_at: datetime | None
    published_by_id: uuid.UUID | None
    attachment_ids: list[uuid.UUID] = []
    created_at: datetime
    updated_at: datetime

    audience_size: int | None = Field(
        default=None, description="How many employees it reaches. Computed, never stored."
    )
    acknowledged_count: int = 0
    is_live: bool = Field(default=False, description="Published, started, and not expired.")


class AnnouncementDetail(AnnouncementRead):
    acknowledgements: list[AcknowledgementRow] = []


class AnnouncementListParams(PaginationParams):
    status: AnnouncementStatus | None = None
    priority: AnnouncementPriority | None = None
    audience: AnnouncementAudience | None = None
    search: str | None = Field(default=None, max_length=100)


class MyAnnouncement(BaseModel):
    """What an employee reads.

    Built only from published, in-window rows that reach this person. No author,
    no audience configuration, no acknowledgement roll -- who else was told and
    who has not read it are the sender's business.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str
    summary: str | None
    priority: AnnouncementPriority
    pinned: bool
    published_at: datetime | None
    expires_at: datetime | None
    attachment_ids: list[uuid.UUID] = []
    requires_acknowledgement: bool
    acknowledged: bool = Field(default=False, description="Whether this reader has confirmed it.")
