"""Helpdesk and announcement business logic.

Two services in one module because they share one thing: both turn an event
into notifications through the platform's existing inbox, and neither owns a
message system of its own.

**The helpdesk.** Four rules.

*The requester is never a parameter on the way in.* ``raise_ticket`` takes the
employee resolved from the access token. ``raise_ticket_for`` exists separately,
takes an id, and is guarded by ``helpdesk:create`` — which no employee holds.

*Status moves only along the transition table.* A closed ticket is closed. A
resolved one is closed by agreement or comes back as a reopen, which is counted,
because "resolved once, came back" is the number a service desk is judged on.

*An internal note is never returned to the requester.* The employee read model
is built from a repository method that filters them out, and the employee-facing
schema has no field that could carry one. Two independent barriers, because this
is the one leak in a helpdesk that would actually embarrass somebody.

*The SLA clock is set once.* A priority raised after the fact does not reset the
due time it was already late against.

**Announcements.** One rule: *a draft is not an announcement.* Publishing is a
separate act with a separate permission, and it is the moment the notification
fan-out happens. Nothing an employee can read comes from anywhere but published,
in-window, correctly-addressed rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.core.logging import get_logger
from app.models.announcement import Announcement, AnnouncementAcknowledgement
from app.models.audit_log import AuditAction
from app.models.employee import Employee
from app.models.enums import (
    DEFAULT_SLA_HOURS,
    OPEN_TICKET_STATUSES,
    TERMINAL_TICKET_STATUSES,
    TICKET_STATUS_TRANSITIONS,
    AnnouncementStatus,
    RecordStatus,
    TicketEvent,
    TicketPriority,
    TicketQueue,
    TicketStatus,
)
from app.models.helpdesk import HelpdeskCategory, HelpdeskComment, HelpdeskHistory, HelpdeskTicket
from app.models.requisition import Notification
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.helpdesk_repository import (
    AcknowledgementRepository,
    AnnouncementRepository,
    TicketCategoryRepository,
    TicketCommentRepository,
    TicketHistoryRepository,
    TicketRepository,
)
from app.repositories.requisition_repository import NotificationRepository
from app.schemas.announcement import (
    AcknowledgementRow,
    AnnouncementCreate,
    AnnouncementDetail,
    AnnouncementListParams,
    AnnouncementPublish,
    AnnouncementRead,
    AnnouncementUpdate,
    MyAnnouncement,
)
from app.schemas.helpdesk import (
    EmployeeSummary,
    HelpdeskDashboard,
    MyTicket,
    MyTicketComment,
    MyTicketDetail,
    MyTicketReply,
    QueueCount,
    TicketAssign,
    TicketCategoryCreate,
    TicketCategoryRead,
    TicketCategoryUpdate,
    TicketComment,
    TicketCommentRead,
    TicketDetail,
    TicketHistoryEntry,
    TicketListParams,
    TicketRaise,
    TicketRaiseFor,
    TicketRead,
    TicketReclassify,
    TicketStatusChange,
)
from app.services.audit_service import AuditService
from app.services.scope_service import EmployeeScope, visible_employee_ids
from app.utils.datetime import utc_now

logger = get_logger("services.helpdesk")


class HelpdeskService:
    """Employee requests, their queues and their resolution."""

    def __init__(
        self,
        tickets: TicketRepository,
        categories: TicketCategoryRepository,
        comments: TicketCommentRepository,
        history: TicketHistoryRepository,
        employees: EmployeeRepository,
        audit: AuditService,
        notifications: NotificationRepository,
    ) -> None:
        self.tickets = tickets
        self.categories = categories
        self.comments = comments
        self.history = history
        self.employees = employees
        self.audit = audit
        self.notifications = notifications
        self.session = tickets.session

    # ==================================================================
    # Categories
    # ==================================================================
    async def list_categories(self, *, include_inactive: bool = False) -> Sequence[HelpdeskCategory]:
        return await (self.categories.all_categories() if include_inactive else self.categories.active())

    async def create_category(
        self, payload: TicketCategoryCreate, *, actor_id: uuid.UUID
    ) -> HelpdeskCategory:
        code = payload.code.strip().upper()
        if await self.categories.by_code(code) is not None:
            raise ConflictError(
                f'A category with the code "{code}" already exists.', error_code="duplicate_code"
            )
        category = await self.categories.add(
            HelpdeskCategory(
                name=payload.name.strip(),
                code=code,
                description=payload.description,
                queue=payload.queue.value,
                sla_hours=payload.sla_hours,
                default_assignee_id=payload.default_assignee_id,
                status=RecordStatus.ACTIVE.value,
            ),
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.TICKET_CATEGORY_CHANGED,
            actor_id=actor_id,
            entity_type="helpdesk_category",
            entity_id=category.id,
            description=f"Created helpdesk category {category.name} ({category.code})",
        )
        return category

    async def update_category(
        self, category_id: uuid.UUID, payload: TicketCategoryUpdate, *, actor_id: uuid.UUID
    ) -> HelpdeskCategory:
        category = await self.categories.get(category_id)
        if category is None:
            raise NotFoundError("Helpdesk category")
        changes = payload.model_dump(exclude_unset=True)
        for field in ("queue", "status"):
            if changes.get(field) is not None:
                changes[field] = getattr(payload, field).value
        await self.categories.update(category, changes, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.TICKET_CATEGORY_CHANGED,
            actor_id=actor_id,
            entity_type="helpdesk_category",
            entity_id=category.id,
            description=f"Updated helpdesk category {category.name}",
            context={"fields": sorted(changes)},
        )
        return category

    # ==================================================================
    # Raising
    # ==================================================================
    async def raise_ticket(
        self, employee: Employee, payload: TicketRaise, *, actor_id: uuid.UUID
    ) -> HelpdeskTicket:
        """Raise the caller's own request. Nothing here names a person."""
        return await self._create(employee, employee, payload, actor_id=actor_id, on_behalf=False)

    async def raise_ticket_for(
        self, payload: TicketRaiseFor, *, actor_id: uuid.UUID, raiser: Employee | None
    ) -> HelpdeskTicket:
        """HR raising a request on somebody's behalf, after a phone call.

        Guarded by ``helpdesk:create``, which no employee role holds.
        """
        subject = await self.employees.get(payload.raised_for_id)
        if subject is None:
            raise ValidationError("That employee does not exist.", error_code="invalid_employee")
        return await self._create(raiser or subject, subject, payload, actor_id=actor_id, on_behalf=True)

    async def _create(
        self,
        raiser: Employee,
        subject: Employee,
        payload: TicketRaise,
        *,
        actor_id: uuid.UUID,
        on_behalf: bool,
    ) -> HelpdeskTicket:
        category = await self.categories.get(payload.category_id)
        if category is None:
            raise ValidationError("That category does not exist.", error_code="invalid_category")
        if category.status != RecordStatus.ACTIVE.value:
            raise ValidationError(
                f'The category "{category.name}" is no longer available.',
                error_code="inactive_category",
            )

        sla_hours = category.sla_hours or DEFAULT_SLA_HOURS[payload.priority]
        ticket = await self.tickets.add(
            HelpdeskTicket(
                subject=payload.subject.strip(),
                description=payload.description,
                category_id=category.id,
                # Copied, not joined: re-pointing the category at a different
                # desk next year must not move every ticket it ever produced.
                queue=category.queue,
                raised_by_id=raiser.id,
                raised_for_id=subject.id if on_behalf else None,
                assigned_to_id=category.default_assignee_id,
                status=TicketStatus.OPEN.value,
                priority=payload.priority.value,
                due_at=utc_now() + timedelta(hours=sla_hours),
                attachment_ids=[str(item) for item in payload.attachment_ids],
            ),
            actor_id=actor_id,
        )
        await self._record(
            ticket,
            TicketEvent.RAISED,
            actor_id=actor_id,
            new_value=TicketStatus.OPEN.value,
            notes=f"Raised against {category.name}",
        )
        await self.audit.record_success(
            AuditAction.TICKET_RAISED,
            actor_id=actor_id,
            entity_type="helpdesk_ticket",
            entity_id=ticket.id,
            description=f"Ticket {ticket.ticket_code} raised ({category.name})",
            context={"on_behalf": on_behalf},
        )
        if category.default_assignee_id:
            await self._notify_user(
                category.default_assignee_id,
                "New request assigned to you",
                f"{ticket.ticket_code}: {ticket.subject}",
                f"/hr/helpdesk/{ticket.id}",
            )
        if on_behalf:
            await self._notify_employee(
                subject,
                "A request was raised for you",
                f"{ticket.ticket_code}: {ticket.subject}",
            )
        logger.info("Ticket raised", extra={"ticket_id": str(ticket.id), "queue": ticket.queue})
        return await self._reload(ticket.id)

    # ==================================================================
    # Working a ticket
    # ==================================================================
    async def list_tickets(
        self, params: TicketListParams, *, scope: EmployeeScope | None = None
    ) -> tuple[Sequence[HelpdeskTicket], int]:
        return await self.tickets.search(params, visible_ids=visible_employee_ids(scope))

    async def get_ticket(self, ticket_id: uuid.UUID, *, scope: EmployeeScope | None = None) -> HelpdeskTicket:
        ticket = await self.tickets.get_detailed(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket")
        if scope is not None:
            scope.assert_allows(ticket.raised_for_id or ticket.raised_by_id)
        return ticket

    async def comment(
        self, ticket_id: uuid.UUID, payload: TicketComment, *, actor_id: uuid.UUID
    ) -> HelpdeskComment:
        """An agent's message. May be internal."""
        ticket = await self.get_ticket(ticket_id)
        self._assert_open(ticket)

        comment = await self.comments.add(
            HelpdeskComment(
                ticket_id=ticket.id,
                author_id=actor_id,
                body=payload.body,
                internal=payload.internal,
                attachment_ids=[str(item) for item in payload.attachment_ids],
            ),
            actor_id=actor_id,
        )
        # The SLA clock stops on the first *public* answer. An internal note is
        # the desk talking to itself and is not a response to the requester.
        if not payload.internal and ticket.first_responded_at is None:
            await self.tickets.update(ticket, {"first_responded_at": utc_now()}, actor_id=actor_id)

        await self._record(
            ticket,
            TicketEvent.COMMENTED,
            actor_id=actor_id,
            notes="Internal note" if payload.internal else "Replied to the requester",
        )
        await self.audit.record_success(
            AuditAction.TICKET_COMMENTED,
            actor_id=actor_id,
            entity_type="helpdesk_ticket",
            entity_id=ticket.id,
            description=f"Comment added to {ticket.ticket_code}",
            context={"internal": payload.internal},
        )
        if not payload.internal:
            await self._notify_requester(
                ticket, "Your request has an update", f"{ticket.ticket_code}: {ticket.subject}"
            )
        return comment

    async def reply(
        self, employee: Employee, ticket_id: uuid.UUID, payload: MyTicketReply, *, actor_id: uuid.UUID
    ) -> HelpdeskComment:
        """The requester's own reply. Cannot be internal -- the schema has no field."""
        ticket = await self.tickets.get_detailed(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket")
        self._assert_is_requester(ticket, employee)
        self._assert_open(ticket)

        comment = await self.comments.add(
            HelpdeskComment(
                ticket_id=ticket.id,
                author_id=actor_id,
                body=payload.body,
                internal=False,
                attachment_ids=[str(item) for item in payload.attachment_ids],
            ),
            actor_id=actor_id,
        )
        # A reply from the requester un-blocks the desk: the ticket was waiting
        # on them, and now it is not.
        if TicketStatus(ticket.status) is TicketStatus.WAITING_ON_EMPLOYEE:
            await self._move(ticket, TicketStatus.IN_PROGRESS, actor_id=actor_id)
        await self._record(ticket, TicketEvent.COMMENTED, actor_id=actor_id, notes="Requester replied")
        if ticket.assigned_to_id:
            await self._notify_user(
                ticket.assigned_to_id,
                "A requester replied",
                f"{ticket.ticket_code}: {ticket.subject}",
                f"/hr/helpdesk/{ticket.id}",
            )
        return comment

    async def change_status(
        self, ticket_id: uuid.UUID, payload: TicketStatusChange, *, actor_id: uuid.UUID
    ) -> HelpdeskTicket:
        ticket = await self.get_ticket(ticket_id)
        previous = TicketStatus(ticket.status)
        await self._move(ticket, payload.status, actor_id=actor_id, resolution=payload.resolution)

        if payload.note:
            await self.comments.add(
                HelpdeskComment(ticket_id=ticket.id, author_id=actor_id, body=payload.note, internal=False),
                actor_id=actor_id,
            )
        await self._record(
            ticket,
            self._event_for(payload.status),
            actor_id=actor_id,
            previous_value=previous.value,
            new_value=payload.status.value,
            notes=payload.resolution or payload.note,
        )
        await self.audit.record_success(
            self._audit_for(payload.status),
            actor_id=actor_id,
            entity_type="helpdesk_ticket",
            entity_id=ticket.id,
            description=f"{ticket.ticket_code}: {previous.value} -> {payload.status.value}",
        )
        await self._notify_requester(
            ticket,
            f"Your request is {payload.status.value.replace('_', ' ')}",
            f"{ticket.ticket_code}: {ticket.subject}",
        )
        return await self._reload(ticket.id)

    async def reopen(
        self, employee: Employee, ticket_id: uuid.UUID, *, actor_id: uuid.UUID, note: str | None = None
    ) -> HelpdeskTicket:
        """The requester saying it is not fixed.

        Counted, because "resolved once, came back" is the number that tells a
        service desk whether it is actually resolving anything.
        """
        ticket = await self.tickets.get_detailed(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket")
        self._assert_is_requester(ticket, employee)
        if TicketStatus(ticket.status) is not TicketStatus.RESOLVED:
            raise ConflictError("Only a resolved request can be reopened.", error_code="not_resolved")

        await self._move(ticket, TicketStatus.REOPENED, actor_id=actor_id)
        await self.tickets.update(
            ticket,
            {"reopen_count": ticket.reopen_count + 1, "resolved_at": None},
            actor_id=actor_id,
        )
        if note:
            await self.comments.add(
                HelpdeskComment(ticket_id=ticket.id, author_id=actor_id, body=note, internal=False),
                actor_id=actor_id,
            )
        await self._record(
            ticket,
            TicketEvent.REOPENED,
            actor_id=actor_id,
            previous_value=TicketStatus.RESOLVED.value,
            new_value=TicketStatus.REOPENED.value,
            notes=note,
        )
        await self.audit.record_success(
            AuditAction.TICKET_REOPENED,
            actor_id=actor_id,
            entity_type="helpdesk_ticket",
            entity_id=ticket.id,
            description=f"{ticket.ticket_code} reopened by the requester",
        )
        if ticket.assigned_to_id:
            await self._notify_user(
                ticket.assigned_to_id,
                "A request was reopened",
                f"{ticket.ticket_code}: {ticket.subject}",
                f"/hr/helpdesk/{ticket.id}",
            )
        return await self._reload(ticket.id)

    async def assign(
        self, ticket_id: uuid.UUID, payload: TicketAssign, *, actor_id: uuid.UUID
    ) -> HelpdeskTicket:
        ticket = await self.get_ticket(ticket_id)
        self._assert_open(ticket)
        previous = ticket.assigned_to_id

        await self.tickets.update(ticket, {"assigned_to_id": payload.assigned_to_id}, actor_id=actor_id)
        # Picking up an open ticket starts the work. Returning one to the queue
        # does not un-start it.
        if payload.assigned_to_id and TicketStatus(ticket.status) is TicketStatus.OPEN:
            await self._move(ticket, TicketStatus.IN_PROGRESS, actor_id=actor_id)

        await self._record(
            ticket,
            TicketEvent.ASSIGNED,
            actor_id=actor_id,
            previous_value=str(previous) if previous else None,
            new_value=str(payload.assigned_to_id) if payload.assigned_to_id else "unassigned",
            notes=payload.note,
        )
        await self.audit.record_success(
            AuditAction.TICKET_ASSIGNED,
            actor_id=actor_id,
            entity_type="helpdesk_ticket",
            entity_id=ticket.id,
            description=f"{ticket.ticket_code} assigned",
            context={"assigned_to": str(payload.assigned_to_id) if payload.assigned_to_id else None},
        )
        if payload.assigned_to_id and payload.assigned_to_id != previous:
            await self._notify_user(
                payload.assigned_to_id,
                "A request was assigned to you",
                f"{ticket.ticket_code}: {ticket.subject}",
                f"/hr/helpdesk/{ticket.id}",
            )
        return await self._reload(ticket.id)

    async def reclassify(
        self, ticket_id: uuid.UUID, payload: TicketReclassify, *, actor_id: uuid.UUID
    ) -> HelpdeskTicket:
        """Move a ticket to the right category or priority.

        The due time is *not* recomputed. A ticket raised as low and escalated
        to urgent two days later is already two days old, and resetting its
        clock would make a desk look punctual by re-labelling its backlog.
        """
        ticket = await self.get_ticket(ticket_id)
        self._assert_open(ticket)
        changes: dict[str, Any] = {}

        if payload.category_id and payload.category_id != ticket.category_id:
            category = await self.categories.get(payload.category_id)
            if category is None:
                raise ValidationError("That category does not exist.", error_code="invalid_category")
            changes["category_id"] = category.id
            changes["queue"] = category.queue
            await self._record(
                ticket,
                TicketEvent.CATEGORY_CHANGED,
                actor_id=actor_id,
                previous_value=ticket.category.name,
                new_value=category.name,
                notes=payload.note,
            )
        if payload.priority and payload.priority.value != ticket.priority:
            changes["priority"] = payload.priority.value
            await self._record(
                ticket,
                TicketEvent.PRIORITY_CHANGED,
                actor_id=actor_id,
                previous_value=ticket.priority,
                new_value=payload.priority.value,
                notes=payload.note,
            )
        if changes:
            await self.tickets.update(ticket, changes, actor_id=actor_id)
        return await self._reload(ticket.id)

    # ==================================================================
    # The employee's own view
    # ==================================================================
    async def my_tickets(self, employee: Employee) -> list[MyTicket]:
        rows = await self.tickets.for_employee(employee.id)
        return [self._present_my(ticket) for ticket in rows]

    async def my_ticket(self, employee: Employee, ticket_id: uuid.UUID) -> MyTicketDetail:
        ticket = await self.tickets.get_detailed(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket")
        self._assert_is_requester(ticket, employee)

        # From the repository method that filters internal notes, not from the
        # loaded collection: one barrier is a habit, two is a guarantee.
        public = await self.comments.public_for_ticket(ticket.id)
        base = self._present_my(ticket)
        status = TicketStatus(ticket.status)
        return MyTicketDetail(
            **base.model_dump(),
            description=ticket.description,
            resolution=ticket.resolution,
            comments=[
                MyTicketComment(
                    id=row.id,
                    body=row.body,
                    attachment_ids=[uuid.UUID(str(x)) for x in (row.attachment_ids or [])],
                    created_at=row.created_at,
                    from_agent=row.author_id != employee.user_id,
                )
                for row in public
            ],
            can_reply=status not in TERMINAL_TICKET_STATUSES,
            can_reopen=status is TicketStatus.RESOLVED,
        )

    # ==================================================================
    # Presentation
    # ==================================================================
    async def present(self, ticket: HelpdeskTicket) -> TicketRead:
        return TicketRead(
            id=ticket.id,
            ticket_code=ticket.ticket_code,
            subject=ticket.subject,
            description=ticket.description,
            category=TicketCategoryRead.model_validate(ticket.category),
            queue=TicketQueue(ticket.queue),
            raised_by=await self._summary(ticket.raised_by_id),
            raised_for=(await self._summary(ticket.raised_for_id) if ticket.raised_for_id else None),
            assigned_to_id=ticket.assigned_to_id,
            status=TicketStatus(ticket.status),
            priority=TicketPriority(ticket.priority),
            due_at=ticket.due_at,
            is_overdue=self._is_overdue(ticket),
            first_responded_at=ticket.first_responded_at,
            resolved_at=ticket.resolved_at,
            closed_at=ticket.closed_at,
            resolution=ticket.resolution,
            reopen_count=ticket.reopen_count,
            attachment_ids=[uuid.UUID(str(x)) for x in (ticket.attachment_ids or [])],
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )

    async def present_detail(self, ticket: HelpdeskTicket) -> TicketDetail:
        base = await self.present(ticket)
        return TicketDetail(
            **base.model_dump(),
            comments=[TicketCommentRead.model_validate(row) for row in ticket.comments],
            history=[
                TicketHistoryEntry.model_validate(row) for row in await self.history.for_ticket(ticket.id)
            ],
            allowed_transitions=sorted(
                TICKET_STATUS_TRANSITIONS.get(TicketStatus(ticket.status), frozenset()),
                key=lambda item: item.value,
            ),
        )

    async def dashboard(self, *, scope: EmployeeScope | None = None, user_id: uuid.UUID) -> HelpdeskDashboard:
        visible = visible_employee_ids(scope)
        counts = await self.tickets.dashboard_counts(visible_ids=visible)
        return HelpdeskDashboard(
            open_tickets=counts["open"],
            unassigned=counts["unassigned"],
            overdue=counts["overdue"],
            waiting_on_employee=counts["waiting"],
            resolved_today=counts["resolved_today"],
            reopened=counts["reopened"],
            by_queue=[
                QueueCount(label=label, count=count)
                for label, count in await self.tickets.counts_by(HelpdeskTicket.queue, visible_ids=visible)
            ],
            by_priority=[
                QueueCount(label=label, count=count)
                for label, count in await self.tickets.counts_by(HelpdeskTicket.priority, visible_ids=visible)
            ],
            by_category=[
                QueueCount(label=label, count=count)
                for label, count in await self.tickets.counts_by_category(visible_ids=visible)
            ],
            my_queue=await self.tickets.count_where(
                HelpdeskTicket.assigned_to_id == user_id,
                HelpdeskTicket.status.in_([s.value for s in OPEN_TICKET_STATUSES]),
                visible_ids=visible,
            ),
        )

    # ==================================================================
    # Internals
    # ==================================================================
    def _assert_transition(self, current: TicketStatus, target: TicketStatus) -> None:
        if current is target:
            return
        allowed = TICKET_STATUS_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            readable = ", ".join(sorted(x.value.replace("_", " ") for x in allowed)) or "nothing"
            raise ConflictError(
                f"A request that is {current.value.replace('_', ' ')} cannot become "
                f"{target.value.replace('_', ' ')}. It can move to: {readable}.",
                error_code="invalid_status_transition",
            )

    async def _move(
        self,
        ticket: HelpdeskTicket,
        target: TicketStatus,
        *,
        actor_id: uuid.UUID,
        resolution: str | None = None,
    ) -> None:
        self._assert_transition(TicketStatus(ticket.status), target)
        changes: dict[str, Any] = {"status": target.value}
        if target is TicketStatus.RESOLVED:
            changes["resolved_at"] = utc_now()
            if resolution:
                changes["resolution"] = resolution
        elif target is TicketStatus.CLOSED:
            changes["closed_at"] = utc_now()
        await self.tickets.update(ticket, changes, actor_id=actor_id)

    @staticmethod
    def _event_for(status: TicketStatus) -> TicketEvent:
        return {
            TicketStatus.RESOLVED: TicketEvent.RESOLVED,
            TicketStatus.CLOSED: TicketEvent.CLOSED,
            TicketStatus.REOPENED: TicketEvent.REOPENED,
        }.get(status, TicketEvent.STATUS_CHANGED)

    @staticmethod
    def _audit_for(status: TicketStatus) -> AuditAction:
        return {
            TicketStatus.RESOLVED: AuditAction.TICKET_RESOLVED,
            TicketStatus.CLOSED: AuditAction.TICKET_CLOSED,
            TicketStatus.REOPENED: AuditAction.TICKET_REOPENED,
        }.get(status, AuditAction.TICKET_STATUS_CHANGED)

    @staticmethod
    def _is_overdue(ticket: HelpdeskTicket) -> bool:
        return bool(
            ticket.due_at
            and ticket.first_responded_at is None
            and TicketStatus(ticket.status) in OPEN_TICKET_STATUSES
            and ticket.due_at < utc_now()
        )

    def _assert_open(self, ticket: HelpdeskTicket) -> None:
        if TicketStatus(ticket.status) in TERMINAL_TICKET_STATUSES:
            raise ConflictError(
                f"This request is {ticket.status} and can no longer be changed.",
                error_code="ticket_closed",
            )

    @staticmethod
    def _assert_is_requester(ticket: HelpdeskTicket, employee: Employee) -> None:
        """The self-service ownership check.

        Both ids, because a ticket HR raised on somebody's behalf is that
        person's request even though they did not type it.
        """
        if employee.id in {ticket.raised_by_id, ticket.raised_for_id}:
            return
        raise PermissionDeniedError(
            "You can only see your own requests.",
            details=[{"code": "not_your_ticket", "message": "ticket_id"}],
        )

    def _present_my(self, ticket: HelpdeskTicket) -> MyTicket:
        return MyTicket(
            id=ticket.id,
            ticket_code=ticket.ticket_code,
            subject=ticket.subject,
            category=ticket.category.name,
            status=TicketStatus(ticket.status),
            priority=TicketPriority(ticket.priority),
            created_at=ticket.created_at,
            resolved_at=ticket.resolved_at,
            awaiting_me=TicketStatus(ticket.status) is TicketStatus.WAITING_ON_EMPLOYEE,
        )

    async def _summary(self, employee_id: uuid.UUID) -> EmployeeSummary:
        employee = await self.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("Employee")
        return EmployeeSummary(
            id=employee.id, employee_code=employee.employee_code, full_name=employee.full_name
        )

    async def _record(
        self,
        ticket: HelpdeskTicket,
        event: TicketEvent,
        *,
        actor_id: uuid.UUID,
        previous_value: str | None = None,
        new_value: str | None = None,
        notes: str | None = None,
    ) -> None:
        await self.history.add(
            HelpdeskHistory(
                ticket_id=ticket.id,
                event=event.value,
                previous_value=previous_value,
                new_value=new_value,
                notes=notes,
            ),
            actor_id=actor_id,
        )

    async def _notify_user(self, user_id: uuid.UUID, title: str, message: str, link: str) -> None:
        await self.notifications.add(
            Notification(
                user_id=user_id,
                title=title,
                message=message,
                link=link,
                notification_type="helpdesk",
            )
        )

    async def _notify_employee(self, employee: Employee, title: str, message: str) -> None:
        if employee.user_id:
            await self._notify_user(employee.user_id, title, message, "/employee/helpdesk")

    async def _notify_requester(self, ticket: HelpdeskTicket, title: str, message: str) -> None:
        employee = await self.employees.get(ticket.raised_for_id or ticket.raised_by_id)
        if employee is not None:
            await self._notify_employee(employee, title, message)

    async def _reload(self, ticket_id: uuid.UUID) -> HelpdeskTicket:
        ticket = await self.tickets.get_detailed(ticket_id)
        if ticket is None:  # pragma: no cover - defensive
            raise NotFoundError("Ticket")
        return ticket


class AnnouncementService:
    """Company notices: written, published, read and acknowledged."""

    def __init__(
        self,
        announcements: AnnouncementRepository,
        acknowledgements: AcknowledgementRepository,
        employees: EmployeeRepository,
        audit: AuditService,
        notifications: NotificationRepository,
    ) -> None:
        self.announcements = announcements
        self.acknowledgements = acknowledgements
        self.employees = employees
        self.audit = audit
        self.notifications = notifications
        self.session = announcements.session

    # ==================================================================
    # Authoring
    # ==================================================================
    async def list_announcements(self, params: AnnouncementListParams) -> tuple[Sequence[Announcement], int]:
        return await self.announcements.search(params)

    async def get(self, announcement_id: uuid.UUID) -> Announcement:
        announcement = await self.announcements.get_detailed(announcement_id)
        if announcement is None:
            raise NotFoundError("Announcement")
        return announcement

    async def create(self, payload: AnnouncementCreate, *, actor_id: uuid.UUID) -> Announcement:
        await self._assert_targets_exist(payload.audience.value, payload.target_ids)
        announcement = await self.announcements.add(
            Announcement(
                title=payload.title.strip(),
                body=payload.body,
                summary=payload.summary,
                audience=payload.audience.value,
                target_ids=[str(item) for item in payload.target_ids],
                priority=payload.priority.value,
                status=AnnouncementStatus.DRAFT.value,
                pinned=payload.pinned,
                requires_acknowledgement=payload.requires_acknowledgement,
                publish_at=payload.publish_at,
                expires_at=payload.expires_at,
                attachment_ids=[str(item) for item in payload.attachment_ids],
            ),
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.ANNOUNCEMENT_CREATED,
            actor_id=actor_id,
            entity_type="announcement",
            entity_id=announcement.id,
            description=f"Drafted announcement: {announcement.title}",
        )
        return announcement

    async def update(
        self, announcement_id: uuid.UUID, payload: AnnouncementUpdate, *, actor_id: uuid.UUID
    ) -> Announcement:
        announcement = await self.get(announcement_id)
        changes = payload.model_dump(exclude_unset=True)
        for field in ("audience", "priority"):
            if changes.get(field) is not None:
                changes[field] = getattr(payload, field).value
        for field in ("target_ids", "attachment_ids"):
            if changes.get(field) is not None:
                changes[field] = [str(item) for item in changes[field]]
        if changes.get("target_ids") is not None or changes.get("audience") is not None:
            await self._assert_targets_exist(
                changes.get("audience", announcement.audience),
                [uuid.UUID(str(x)) for x in changes.get("target_ids", announcement.target_ids)],
            )

        await self.announcements.update(announcement, changes, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.ANNOUNCEMENT_UPDATED,
            actor_id=actor_id,
            entity_type="announcement",
            entity_id=announcement.id,
            description=f"Updated announcement: {announcement.title}",
            context={"fields": sorted(changes)},
        )
        return announcement

    async def publish(
        self, announcement_id: uuid.UUID, payload: AnnouncementPublish, *, actor_id: uuid.UUID
    ) -> Announcement:
        """Send it. The act the separate permission exists for."""
        announcement = await self.get(announcement_id)
        status = AnnouncementStatus(announcement.status)
        if status is AnnouncementStatus.PUBLISHED:
            raise ConflictError("This announcement is already published.", error_code="already_published")
        if status is AnnouncementStatus.ARCHIVED:
            raise ConflictError(
                "An archived announcement cannot be republished. Copy it into a new one.",
                error_code="announcement_archived",
            )

        now = utc_now()
        scheduled = payload.publish_at is not None and payload.publish_at > now
        await self.announcements.update(
            announcement,
            {
                "status": (
                    AnnouncementStatus.SCHEDULED.value if scheduled else AnnouncementStatus.PUBLISHED.value
                ),
                "publish_at": payload.publish_at or now,
                "published_at": None if scheduled else now,
                "published_by_id": actor_id,
            },
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.ANNOUNCEMENT_PUBLISHED,
            actor_id=actor_id,
            entity_type="announcement",
            entity_id=announcement.id,
            description=f"{'Scheduled' if scheduled else 'Published'}: {announcement.title}",
            context={"scheduled": scheduled},
        )
        if not scheduled:
            await self._fan_out(announcement)
        return await self.get(announcement.id)

    async def archive(self, announcement_id: uuid.UUID, *, actor_id: uuid.UUID) -> Announcement:
        announcement = await self.get(announcement_id)
        await self.announcements.update(
            announcement, {"status": AnnouncementStatus.ARCHIVED.value}, actor_id=actor_id
        )
        await self.audit.record_success(
            AuditAction.ANNOUNCEMENT_ARCHIVED,
            actor_id=actor_id,
            entity_type="announcement",
            entity_id=announcement.id,
            description=f"Archived announcement: {announcement.title}",
        )
        return announcement

    async def delete(self, announcement_id: uuid.UUID, *, actor_id: uuid.UUID) -> None:
        """Remove it from the record. Archiving is the ordinary way to retire one."""
        announcement = await self.get(announcement_id)
        await self.announcements.soft_delete(announcement, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.ANNOUNCEMENT_DELETED,
            actor_id=actor_id,
            entity_type="announcement",
            entity_id=announcement.id,
            description=f"Deleted announcement: {announcement.title}",
        )

    # ==================================================================
    # Reading
    # ==================================================================
    async def for_employee(self, employee: Employee) -> list[MyAnnouncement]:
        """What this person should see, now.

        Anything scheduled whose time has passed is published first. The
        platform has no scheduler, so the first read after the publish time is
        what makes a scheduled notice live -- adequate for a noticeboard, and
        the same call a real scheduler would make.
        """
        await self._publish_due()

        rows = await self.announcements.live_for_employee(employee)
        acknowledged = await self.acknowledgements.for_employee(employee.id, [row.id for row in rows])
        return [
            MyAnnouncement(
                id=row.id,
                title=row.title,
                body=row.body,
                summary=row.summary,
                priority=row.priority,
                pinned=row.pinned,
                published_at=row.published_at,
                expires_at=row.expires_at,
                attachment_ids=[uuid.UUID(str(x)) for x in (row.attachment_ids or [])],
                requires_acknowledgement=row.requires_acknowledgement,
                acknowledged=row.id in acknowledged,
            )
            for row in rows
        ]

    async def acknowledge(
        self, employee: Employee, announcement_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> None:
        """Confirm the reader has seen it. Idempotent."""
        announcement = await self.get(announcement_id)
        if AnnouncementStatus(announcement.status) is not AnnouncementStatus.PUBLISHED:
            raise ConflictError("This announcement is not published.", error_code="not_published")
        if await self.acknowledgements.existing(announcement_id, employee.id) is not None:
            return
        await self.acknowledgements.add(
            AnnouncementAcknowledgement(
                announcement_id=announcement_id,
                employee_id=employee.id,
                acknowledged_at=utc_now(),
            ),
            actor_id=actor_id,
        )

    async def present(self, announcement: Announcement) -> AnnouncementRead:
        now = utc_now()
        return AnnouncementRead(
            **{
                field: getattr(announcement, field)
                for field in (
                    "id",
                    "title",
                    "body",
                    "summary",
                    "priority",
                    "status",
                    "pinned",
                    "requires_acknowledgement",
                    "publish_at",
                    "published_at",
                    "expires_at",
                    "published_by_id",
                    "created_at",
                    "updated_at",
                )
            },
            audience=announcement.audience,
            target_ids=[uuid.UUID(str(x)) for x in (announcement.target_ids or [])],
            attachment_ids=[uuid.UUID(str(x)) for x in (announcement.attachment_ids or [])],
            audience_size=await self.announcements.audience_size(announcement),
            # A count query rather than len() over the relationship: `present`
            # is called on freshly created rows too, and touching a lazy
            # collection on one of those loads outside the async context and
            # surfaces as an opaque 500.
            acknowledged_count=await self.acknowledgements.count_for(announcement.id),
            is_live=(
                announcement.status == AnnouncementStatus.PUBLISHED.value
                and announcement.published_at is not None
                and announcement.published_at <= now
                and (announcement.expires_at is None or announcement.expires_at > now)
            ),
        )

    async def present_detail(self, announcement: Announcement) -> AnnouncementDetail:
        base = await self.present(announcement)
        return AnnouncementDetail(
            **base.model_dump(),
            acknowledgements=[
                AcknowledgementRow(employee_id=eid, employee_name=name, acknowledged_at=when)
                for eid, name, when in await self.acknowledgements.with_names(announcement.id)
            ],
        )

    # ==================================================================
    # Internals
    # ==================================================================
    async def _publish_due(self) -> None:
        for announcement in await self.announcements.due_to_publish():
            await self.announcements.update(
                announcement,
                {
                    "status": AnnouncementStatus.PUBLISHED.value,
                    "published_at": announcement.publish_at or utc_now(),
                },
            )
            await self._fan_out(announcement)
            logger.info("Scheduled announcement published", extra={"announcement_id": str(announcement.id)})

    async def _fan_out(self, announcement: Announcement) -> None:
        """Notify the audience through the platform's existing inbox.

        This is the whole reason an announcement is not a second message
        system: the notification is the delivery, and the announcement is the
        thing it points at.
        """
        recipients = await self.announcements.recipient_user_ids(announcement)
        for user_id in recipients:
            await self.notifications.add(
                Notification(
                    user_id=user_id,
                    title=announcement.title,
                    message=announcement.summary or announcement.title,
                    link="/employee/announcements",
                    notification_type="announcement",
                )
            )
        logger.info(
            "Announcement fanned out",
            extra={"announcement_id": str(announcement.id), "recipients": len(recipients)},
        )

    async def _assert_targets_exist(self, audience: str, target_ids: Sequence[uuid.UUID]) -> None:
        """A notice addressed to a team that does not exist reaches nobody, silently."""
        from app.models.business_unit import BusinessUnit
        from app.models.enums import AnnouncementAudience as Audience
        from app.models.location import Location
        from app.models.team import Team

        if not target_ids:
            return
        model = {
            Audience.BUSINESS_UNIT.value: BusinessUnit,
            Audience.TEAM.value: Team,
            Audience.LOCATION.value: Location,
        }.get(audience)
        if model is None:
            return

        from sqlalchemy import func as sa_func, select as sa_select

        found = await self.session.scalar(
            sa_select(sa_func.count()).select_from(model).where(model.id.in_(target_ids))
        )
        if int(found or 0) != len(set(target_ids)):
            raise ValidationError(
                "One or more of the selected audiences does not exist.",
                error_code="invalid_audience_target",
            )
