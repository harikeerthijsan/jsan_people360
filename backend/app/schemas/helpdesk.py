"""Helpdesk schemas.

Two properties shape this module.

**The employee's read model cannot carry an internal note.**
:class:`MyTicketComment` has no ``internal`` field, and :class:`MyTicketDetail`
is built from a filtered list. An agent's working note is a legitimate thing to
write down and is not part of what the requester sees; the omission is the
protection, rather than a filter somewhere that has to be remembered.

**No self-service write schema names an employee.** :class:`TicketRaise` has no
``raised_by_id``. The requester comes from the access token, so raising a ticket
in somebody else's name is a thing that cannot be expressed. The administrative
:class:`TicketRaiseFor` does carry an id, deliberately and separately, because
HR taking a request over the phone is a real workflow — and it is guarded by
``helpdesk:create``, which no employee holds.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    RecordStatus,
    TicketEvent,
    TicketPriority,
    TicketQueue,
    TicketStatus,
)
from app.schemas.common import PaginationParams

_MAX_BODY = 8000


# ----------------------------------------------------------------------
# Categories
# ----------------------------------------------------------------------
class TicketCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    description: str | None
    queue: TicketQueue
    sla_hours: int | None
    default_assignee_id: uuid.UUID | None
    status: RecordStatus


class MyTicketCategory(BaseModel):
    """A category as the requester sees it.

    Enough to choose one: name and what it is for. The queue, the SLA clock and
    the default assignee are how the desk is staffed, which is not the
    requester's business -- so the model cannot carry them.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None


class TicketCategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    queue: TicketQueue
    description: str | None = Field(default=None, max_length=_MAX_BODY)
    sla_hours: int | None = Field(default=None, gt=0, le=8760)
    default_assignee_id: uuid.UUID | None = None


class TicketCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    queue: TicketQueue | None = None
    description: str | None = Field(default=None, max_length=_MAX_BODY)
    sla_hours: int | None = Field(default=None, gt=0, le=8760)
    default_assignee_id: uuid.UUID | None = None
    status: RecordStatus | None = None


# ----------------------------------------------------------------------
# Raising
# ----------------------------------------------------------------------
class TicketRaise(BaseModel):
    """What an employee sends. Deliberately has no requester field."""

    category_id: uuid.UUID
    subject: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10, max_length=_MAX_BODY)
    priority: TicketPriority = TicketPriority.MEDIUM
    attachment_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Existing Document Vault ids. Files are uploaded to the vault, not here.",
    )


class TicketRaiseFor(TicketRaise):
    """The administrative form: HR taking a request on somebody's behalf.

    Separate from :class:`TicketRaise` rather than an optional field on it,
    because the difference is a permission (``helpdesk:create``) and a schema
    that carries an id no employee may set is clearer than one that ignores it.
    """

    raised_for_id: uuid.UUID


# ----------------------------------------------------------------------
# Working a ticket
# ----------------------------------------------------------------------
class TicketComment(BaseModel):
    body: str = Field(min_length=1, max_length=_MAX_BODY)
    internal: bool = Field(default=False, description="An agent-only note. Never shown to the requester.")
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)


class MyTicketReply(BaseModel):
    """The requester's reply. Has no ``internal`` field, by construction."""

    body: str = Field(min_length=1, max_length=_MAX_BODY)
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)


class TicketStatusChange(BaseModel):
    status: TicketStatus
    note: str | None = Field(default=None, max_length=_MAX_BODY)
    resolution: str | None = Field(
        default=None,
        max_length=_MAX_BODY,
        description="Required when resolving: what was actually done.",
    )

    @model_validator(mode="after")
    def resolution_accompanies_resolved(self) -> Self:
        if self.status is TicketStatus.RESOLVED and not (self.resolution or "").strip():
            raise ValueError("Resolving a ticket needs a resolution: what was done")
        return self


class TicketAssign(BaseModel):
    assigned_to_id: uuid.UUID | None = Field(
        default=None, description="Null unassigns and returns the ticket to its queue."
    )
    note: str | None = Field(default=None, max_length=_MAX_BODY)


class TicketReclassify(BaseModel):
    category_id: uuid.UUID | None = None
    priority: TicketPriority | None = None
    note: str | None = Field(default=None, max_length=_MAX_BODY)


# ----------------------------------------------------------------------
# Reading -- administrative
# ----------------------------------------------------------------------
class EmployeeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    full_name: str


class TicketCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_id: uuid.UUID | None
    body: str
    internal: bool
    attachment_ids: list[uuid.UUID] = []
    created_at: datetime


class TicketHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event: TicketEvent
    previous_value: str | None
    new_value: str | None
    notes: str | None
    created_at: datetime
    created_by: uuid.UUID | None


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_code: str
    subject: str
    description: str
    category: TicketCategoryRead
    queue: TicketQueue
    raised_by: EmployeeSummary
    raised_for: EmployeeSummary | None = None
    assigned_to_id: uuid.UUID | None
    status: TicketStatus
    priority: TicketPriority
    due_at: datetime | None
    is_overdue: bool = Field(
        default=False, description="Past its first-response due time and still unanswered."
    )
    first_responded_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    resolution: str | None
    reopen_count: int
    attachment_ids: list[uuid.UUID] = []
    created_at: datetime
    updated_at: datetime


class TicketDetail(TicketRead):
    comments: list[TicketCommentRead] = []
    history: list[TicketHistoryEntry] = []
    allowed_transitions: list[TicketStatus] = Field(
        default_factory=list,
        description="Where this ticket may move next. Computed server-side so the client never "
        "holds a copy of the transition table.",
    )


class TicketListParams(PaginationParams):
    search: str | None = Field(default=None, max_length=100, description="Matches code or subject.")
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    queue: TicketQueue | None = None
    category_id: uuid.UUID | None = None
    assigned_to_id: uuid.UUID | None = None
    unassigned: bool | None = Field(default=None, description="Only tickets nobody has picked up.")
    overdue: bool | None = Field(default=None, description="Only tickets past their due time.")
    open_only: bool | None = Field(default=None, description="Exclude closed and cancelled.")
    employee_id: uuid.UUID | None = Field(
        default=None,
        description="Narrow to one requester. Still subject to the caller's scope -- supplying an "
        "id never widens what is returned.",
    )


# ----------------------------------------------------------------------
# Reading -- the employee's own
# ----------------------------------------------------------------------
class MyTicketComment(BaseModel):
    """What the requester sees of the conversation.

    No ``internal`` field: this model is built only from public comments, and a
    schema that cannot carry the flag cannot leak the note.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    attachment_ids: list[uuid.UUID] = []
    created_at: datetime
    from_agent: bool = Field(description="True when somebody other than the requester wrote it.")


class MyTicket(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_code: str
    subject: str
    category: str
    status: TicketStatus
    priority: TicketPriority
    created_at: datetime
    resolved_at: datetime | None
    awaiting_me: bool = Field(default=False, description="The desk is waiting on the requester to reply.")


class MyTicketDetail(MyTicket):
    description: str
    resolution: str | None
    comments: list[MyTicketComment] = []
    can_reply: bool
    can_reopen: bool


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------
class QueueCount(BaseModel):
    label: str
    count: int


class HelpdeskDashboard(BaseModel):
    open_tickets: int
    unassigned: int
    overdue: int
    waiting_on_employee: int
    resolved_today: int
    reopened: int
    by_queue: list[QueueCount] = []
    by_category: list[QueueCount] = []
    by_priority: list[QueueCount] = []
    my_queue: int = Field(default=0, description="Open tickets assigned to the caller.")
