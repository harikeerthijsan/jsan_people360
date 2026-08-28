"""Helpdesk persistence models.

Four tables, and the shape follows one decision: **a ticket is a conversation
with a state, not a form with a status column.** The comment thread is the
substance of a request — what was asked, what was answered, what was agreed —
and the status is bookkeeping over the top of it.

So ``helpdesk_comments`` is a first-class table rather than a text field that
gets appended to, and ``helpdesk_history`` records the state changes separately
from the conversation. Somebody reading a ticket six months later wants the
former; somebody auditing a service desk wants the latter, and neither is
derivable from the other.

Comments carry an ``internal`` flag. An agent noting "payroll says this is a
tax-code problem, do not tell them it is our fault yet" is a real and legitimate
thing to write down, and it is not part of what the requester sees. The employee
read model omits internal comments by construction — see
:class:`app.schemas.helpdesk.MyTicketDetail`.
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
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.enums import (
    RECORD_STATUS_SQL_VALUES,
    TICKET_EVENT_SQL_VALUES,
    TICKET_PRIORITY_SQL_VALUES,
    TICKET_QUEUE_SQL_VALUES,
    TICKET_STATUS_SQL_VALUES,
    RecordStatus,
    TicketPriority,
    TicketStatus,
)

#: ``TKT-000001`` onwards, from a sequence like every other generated identifier
#: here: two people raising a request at once must never be handed the same
#: number, and it is the number they will quote on the phone.
TICKET_CODE_SEQUENCE = "helpdesk_tickets_code_seq"
TICKET_CODE_DEFAULT = f"'TKT-' || lpad(nextval('{TICKET_CODE_SEQUENCE}')::text, 6, '0')"


class HelpdeskCategory(Base, AuditableBase):
    """What a request is about, and which desk it lands on.

    Configurable for the same reason asset categories are: the set varies by
    organization, and a hardcoded list means a migration every time somebody
    wants a new queue. Deactivated rather than deleted, so a two-year-old ticket
    still resolves to a category name.
    """

    __tablename__ = "helpdesk_categories"
    __table_args__ = (
        UniqueConstraint("code", name="uq_helpdesk_categories_code"),
        CheckConstraint(f"status IN ({RECORD_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint(f"queue IN ({TICKET_QUEUE_SQL_VALUES})", name="queue"),
        CheckConstraint("sla_hours IS NULL OR sla_hours > 0", name="sla_hours_positive"),
        {"comment": "Configurable request categories and the desk each routes to."},
    )

    name: Mapped[str] = mapped_column(String(100), index=True)
    code: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    queue: Mapped[str] = mapped_column(String(20), index=True)
    #: Overrides the priority default from ``DEFAULT_SLA_HOURS``. NULL means
    #: "use the priority's default", which is different from a value of zero and
    #: is why this is nullable rather than defaulted.
    sla_hours: Mapped[int | None] = mapped_column(Integer)
    #: Nominated first responder. Nullable: a queue may be answered by whoever
    #: is on duty, and the *permission* decides who may act, not this column.
    default_assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(20), default=RecordStatus.ACTIVE, server_default=RecordStatus.ACTIVE.value, index=True
    )


class HelpdeskTicket(Base, AuditableBase):
    """One request, raised by one employee.

    ``raised_by_id`` is written from the authenticated session and never from a
    request body — see :meth:`HelpdeskService.raise_ticket`. ``raised_for_id``
    exists separately because HR legitimately raises a ticket on somebody's
    behalf after a phone call, and the two ids answer different questions:
    who is asking, and whose problem it is.
    """

    __tablename__ = "helpdesk_tickets"
    __table_args__ = (
        Index("ix_helpdesk_tickets_status_priority", "status", "priority"),
        Index("ix_helpdesk_tickets_queue_status", "queue", "status"),
        Index("ix_helpdesk_tickets_assignee_status", "assigned_to_id", "status"),
        CheckConstraint(f"status IN ({TICKET_STATUS_SQL_VALUES})", name="status"),
        CheckConstraint(f"priority IN ({TICKET_PRIORITY_SQL_VALUES})", name="priority"),
        CheckConstraint(f"queue IN ({TICKET_QUEUE_SQL_VALUES})", name="queue"),
        {"comment": "Employee requests to a service desk."},
    )

    ticket_code: Mapped[str] = mapped_column(
        String(20), unique=True, server_default=text(TICKET_CODE_DEFAULT)
    )
    subject: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text)

    category_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("helpdesk_categories.id", ondelete="RESTRICT"), index=True
    )
    #: Copied from the category when the ticket is raised rather than joined on
    #: read: re-pointing a category at a different desk next year must not
    #: silently move every ticket it ever produced.
    queue: Mapped[str] = mapped_column(String(20))

    raised_by_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    raised_for_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="RESTRICT"),
        index=True,
        doc="Set when somebody raised this on another employee's behalf.",
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    status: Mapped[str] = mapped_column(
        String(30), default=TicketStatus.OPEN, server_default=TicketStatus.OPEN.value, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(20), default=TicketPriority.MEDIUM, server_default=TicketPriority.MEDIUM.value
    )

    #: When a first response is due. Computed once from the category or the
    #: priority default; nothing recalculates it, because a priority raised
    #: after the fact should not quietly reset the clock it was already late on.
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    first_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    #: Document Vault ids. The files stay in the vault; this module links to
    #: them and never stores bytes of its own.
    attachment_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")

    category: Mapped[HelpdeskCategory] = relationship(lazy="joined")
    comments: Mapped[list[HelpdeskComment]] = relationship(
        back_populates="ticket", lazy="selectin", order_by="HelpdeskComment.created_at"
    )


class HelpdeskComment(Base, AuditableBase):
    """One message on a ticket.

    ``internal`` is the important column. An agent's working note is a real
    thing to write down and is not part of what the requester sees; the employee
    read model filters on it, and the *employee-facing schema* has no field that
    could carry one.
    """

    __tablename__ = "helpdesk_comments"
    __table_args__ = (
        Index("ix_helpdesk_comments_ticket_created", "ticket_id", "created_at"),
        {"comment": "The conversation on a ticket."},
    )

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("helpdesk_tickets.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    internal: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        index=True,
        doc="An agent-only note. Never returned by the employee-facing read model.",
    )
    attachment_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")

    ticket: Mapped[HelpdeskTicket] = relationship(back_populates="comments")


class HelpdeskHistory(Base, AuditableBase):
    """Append-only state changes, separate from the conversation."""

    __tablename__ = "helpdesk_history"
    __table_args__ = (
        Index("ix_helpdesk_history_ticket_created", "ticket_id", "created_at"),
        CheckConstraint(f"event IN ({TICKET_EVENT_SQL_VALUES})", name="event"),
        {"comment": "Append-only event log for one ticket."},
    )

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("helpdesk_tickets.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(30), index=True)
    previous_value: Mapped[str | None] = mapped_column(String(200))
    new_value: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
