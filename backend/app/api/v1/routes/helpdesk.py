"""Helpdesk and announcement endpoints.

The employee routers carry no ``require(...)`` guard, like everything else under
``/me``: raising a request about your own payslip and reading a notice addressed
to you are things a permission should never be able to take away. Ownership is
checked by identity — ``_assert_is_requester`` for a ticket, and the audience
query for an announcement, which only ever returns rows that reach this person.

The administrative routers carry the module permissions. Two grants are worth
naming because the whole access model rests on them:

* **Manager holds ``helpdesk:view`` and not ``helpdesk:update``.** A manager
  whose team has three open payroll tickets should know; answering them is the
  desk's job, not theirs.
* **HR Executive holds ``announcements:create`` and not
  ``announcements:publish``.** They write; HR Admin sends. Drafting a notice and
  broadcasting it to the company are different acts.

Route order matters as elsewhere: static segments precede the ``/{id}`` forms.

NOTE: no ``from __future__ import annotations`` -- FastAPI reads parameter types
from evaluated annotations, and postponed evaluation breaks ``Annotated[...,
Query()]``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    AnnouncementSvc,
    CurrentEmployee,
    CurrentScope,
    CurrentUser,
    HelpdeskSvc,
    require,
)
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementDetail,
    AnnouncementListParams,
    AnnouncementPublish,
    AnnouncementRead,
    AnnouncementUpdate,
    MyAnnouncement,
)
from app.schemas.common import APIErrorResponse, APIResponse, MessageData, Page
from app.schemas.helpdesk import (
    HelpdeskDashboard,
    MyTicket,
    MyTicketCategory,
    MyTicketDetail,
    MyTicketReply,
    TicketAssign,
    TicketCategoryCreate,
    TicketCategoryRead,
    TicketCategoryUpdate,
    TicketComment,
    TicketCommentRead,
    TicketDetail,
    TicketListParams,
    TicketRaise,
    TicketRaiseFor,
    TicketRead,
    TicketReclassify,
    TicketStatusChange,
)

router = APIRouter(prefix="/helpdesk", tags=["Helpdesk"])
announcements_router = APIRouter(prefix="/announcements", tags=["Announcements"])
me_router = APIRouter(prefix="/me", tags=["Employee Self-Service"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_403_FORBIDDEN: {
        "model": APIErrorResponse,
        "description": "Missing the permission, or the record is outside your reach.",
    },
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such record."},
    status.HTTP_409_CONFLICT: {
        "model": APIErrorResponse,
        "description": "A workflow rule was violated -- an invalid status transition, or a closed ticket.",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": APIErrorResponse,
        "description": "Validation failed.",
    },
}

TicketParams = Annotated[TicketListParams, Query()]
AnnouncementParams = Annotated[AnnouncementListParams, Query()]


# ======================================================================
# Employee: my requests
# ======================================================================
@me_router.get(
    "/helpdesk/categories",
    response_model=APIResponse[list[MyTicketCategory]],
    summary="Categories I can raise a request under",
    description=(
        "Active categories only, and a read model that carries just enough to choose one. "
        "How each queue is staffed is the desk's endpoint, behind the desk's permission."
    ),
    responses={**_ERRORS},
)
async def my_categories(
    employee: CurrentEmployee, service: HelpdeskSvc
) -> APIResponse[list[MyTicketCategory]]:
    del employee  # Identity-guarded like the rest of /me; no permission to hold.
    rows = await service.list_categories()
    return APIResponse.ok([MyTicketCategory.model_validate(row) for row in rows])


@me_router.get(
    "/helpdesk",
    response_model=APIResponse[list[MyTicket]],
    summary="My requests",
    description="Requests the caller raised, and any raised on their behalf.",
    responses={**_ERRORS},
)
async def my_tickets(employee: CurrentEmployee, service: HelpdeskSvc) -> APIResponse[list[MyTicket]]:
    return APIResponse.ok(await service.my_tickets(employee))


@me_router.post(
    "/helpdesk",
    response_model=APIResponse[MyTicket],
    status_code=status.HTTP_201_CREATED,
    summary="Raise a request",
    description=("The requester is taken from the access token; there is no field here that names a person."),
    responses={**_ERRORS},
)
async def raise_ticket(
    payload: TicketRaise,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: HelpdeskSvc,
) -> APIResponse[MyTicket]:
    ticket = await service.raise_ticket(employee, payload, actor_id=current_user.id)
    detail = await service.my_ticket(employee, ticket.id)
    return APIResponse.ok(
        MyTicket(**{k: getattr(detail, k) for k in MyTicket.model_fields}), message="Request raised"
    )


@me_router.get(
    "/helpdesk/{ticket_id}",
    response_model=APIResponse[MyTicketDetail],
    summary="One of my requests",
    description="Internal agent notes are never included: the read model cannot carry one.",
    responses={**_ERRORS},
)
async def my_ticket(
    ticket_id: uuid.UUID, employee: CurrentEmployee, service: HelpdeskSvc
) -> APIResponse[MyTicketDetail]:
    return APIResponse.ok(await service.my_ticket(employee, ticket_id))


@me_router.post(
    "/helpdesk/{ticket_id}/reply",
    response_model=APIResponse[MessageData],
    status_code=status.HTTP_201_CREATED,
    summary="Reply to my request",
    responses={**_ERRORS},
)
async def reply_to_ticket(
    ticket_id: uuid.UUID,
    payload: MyTicketReply,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: HelpdeskSvc,
) -> APIResponse[MessageData]:
    await service.reply(employee, ticket_id, payload, actor_id=current_user.id)
    return APIResponse.ok(MessageData(detail="Reply added"), message="Reply added")


@me_router.post(
    "/helpdesk/{ticket_id}/reopen",
    response_model=APIResponse[MyTicketDetail],
    summary="Reopen a resolved request",
    description="Available to the requester when a request was resolved and the problem persists.",
    responses={**_ERRORS},
)
async def reopen_ticket(
    ticket_id: uuid.UUID,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: HelpdeskSvc,
    note: Annotated[str | None, Query(max_length=4000)] = None,
) -> APIResponse[MyTicketDetail]:
    await service.reopen(employee, ticket_id, actor_id=current_user.id, note=note)
    return APIResponse.ok(await service.my_ticket(employee, ticket_id), message="Request reopened")


# ======================================================================
# Employee: my announcements
# ======================================================================
@me_router.get(
    "/announcements",
    response_model=APIResponse[list[MyAnnouncement]],
    summary="Announcements for me",
    description=(
        "Published, in-window notices addressed to this employee's business unit, team, location "
        "or to everybody. Pinned first, then most recent."
    ),
    responses={**_ERRORS},
)
async def my_announcements(
    employee: CurrentEmployee, service: AnnouncementSvc
) -> APIResponse[list[MyAnnouncement]]:
    return APIResponse.ok(await service.for_employee(employee))


@me_router.post(
    "/announcements/{announcement_id}/acknowledge",
    response_model=APIResponse[MessageData],
    summary="Acknowledge an announcement",
    description="Idempotent: acknowledging twice is not twice as acknowledged.",
    responses={**_ERRORS},
)
async def acknowledge_announcement(
    announcement_id: uuid.UUID,
    employee: CurrentEmployee,
    current_user: CurrentUser,
    service: AnnouncementSvc,
) -> APIResponse[MessageData]:
    await service.acknowledge(employee, announcement_id, actor_id=current_user.id)
    return APIResponse.ok(MessageData(detail="Acknowledged"), message="Acknowledged")


# ======================================================================
# Helpdesk: categories and dashboard (before /{ticket_id})
# ======================================================================
@router.get(
    "/categories",
    dependencies=[require("helpdesk:view")],
    response_model=APIResponse[list[TicketCategoryRead]],
    summary="Request categories",
    responses={**_ERRORS},
)
async def list_categories(
    current_user: CurrentUser,
    service: HelpdeskSvc,
    include_inactive: Annotated[bool, Query()] = False,
) -> APIResponse[list[TicketCategoryRead]]:
    del current_user
    rows = await service.list_categories(include_inactive=include_inactive)
    return APIResponse.ok([TicketCategoryRead.model_validate(row) for row in rows])


@router.post(
    "/categories",
    dependencies=[require("helpdesk:manage")],
    response_model=APIResponse[TicketCategoryRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a request category",
    responses={**_ERRORS},
)
async def create_category(
    payload: TicketCategoryCreate, current_user: CurrentUser, service: HelpdeskSvc
) -> APIResponse[TicketCategoryRead]:
    category = await service.create_category(payload, actor_id=current_user.id)
    return APIResponse.ok(TicketCategoryRead.model_validate(category), message="Category created")


@router.patch(
    "/categories/{category_id}",
    dependencies=[require("helpdesk:manage")],
    response_model=APIResponse[TicketCategoryRead],
    summary="Update or deactivate a category",
    responses={**_ERRORS},
)
async def update_category(
    category_id: uuid.UUID,
    payload: TicketCategoryUpdate,
    current_user: CurrentUser,
    service: HelpdeskSvc,
) -> APIResponse[TicketCategoryRead]:
    category = await service.update_category(category_id, payload, actor_id=current_user.id)
    return APIResponse.ok(TicketCategoryRead.model_validate(category), message="Category updated")


@router.get(
    "/dashboard",
    dependencies=[require("helpdesk:view")],
    response_model=APIResponse[HelpdeskDashboard],
    summary="Helpdesk dashboard",
    description="Queue depth, overdue work and the caller's own assignments.",
    responses={**_ERRORS},
)
async def dashboard(
    scope: CurrentScope, current_user: CurrentUser, service: HelpdeskSvc
) -> APIResponse[HelpdeskDashboard]:
    return APIResponse.ok(await service.dashboard(scope=scope, user_id=current_user.id))


# ======================================================================
# Helpdesk: the queue
# ======================================================================
@router.get(
    "",
    dependencies=[require("helpdesk:view")],
    response_model=APIResponse[Page[TicketRead]],
    summary="Requests",
    description=(
        "Narrowed to the requesters the caller may see unless they hold employees:view_all -- so a "
        "manager sees their team's requests and an HR agent sees the whole desk."
    ),
    responses={**_ERRORS},
)
async def list_tickets(
    params: TicketParams, scope: CurrentScope, current_user: CurrentUser, service: HelpdeskSvc
) -> APIResponse[Page[TicketRead]]:
    del current_user
    if params.employee_id is not None:
        scope.assert_allows(params.employee_id)
    rows, total = await service.list_tickets(params, scope=scope)
    items = [await service.present(row) for row in rows]
    return APIResponse.ok(Page.create(items, page=params.page, page_size=params.page_size, total_items=total))


@router.post(
    "",
    dependencies=[require("helpdesk:create")],
    response_model=APIResponse[TicketRead],
    status_code=status.HTTP_201_CREATED,
    summary="Raise a request on somebody's behalf",
    description="For a request taken over the phone. Employees raise their own through /me.",
    responses={**_ERRORS},
)
async def raise_for(
    payload: TicketRaiseFor,
    current_user: CurrentUser,
    service: HelpdeskSvc,
) -> APIResponse[TicketRead]:
    ticket = await service.raise_ticket_for(payload, actor_id=current_user.id, raiser=None)
    return APIResponse.ok(await service.present(ticket), message="Request raised")


@router.get(
    "/{ticket_id}",
    dependencies=[require("helpdesk:view")],
    response_model=APIResponse[TicketDetail],
    summary="One request, with its conversation and history",
    responses={**_ERRORS},
)
async def get_ticket(
    ticket_id: uuid.UUID, scope: CurrentScope, current_user: CurrentUser, service: HelpdeskSvc
) -> APIResponse[TicketDetail]:
    del current_user
    ticket = await service.get_ticket(ticket_id, scope=scope)
    return APIResponse.ok(await service.present_detail(ticket))


@router.post(
    "/{ticket_id}/comments",
    dependencies=[require("helpdesk:update")],
    response_model=APIResponse[TicketCommentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Comment on a request",
    description="Set internal to keep the note off the requester's view entirely.",
    responses={**_ERRORS},
)
async def comment(
    ticket_id: uuid.UUID,
    payload: TicketComment,
    current_user: CurrentUser,
    service: HelpdeskSvc,
) -> APIResponse[TicketCommentRead]:
    row = await service.comment(ticket_id, payload, actor_id=current_user.id)
    return APIResponse.ok(TicketCommentRead.model_validate(row), message="Comment added")


@router.post(
    "/{ticket_id}/status",
    dependencies=[require("helpdesk:update")],
    response_model=APIResponse[TicketRead],
    summary="Change a request's status",
    description="Validated against the transition table. Resolving one needs a resolution.",
    responses={**_ERRORS},
)
async def change_status(
    ticket_id: uuid.UUID,
    payload: TicketStatusChange,
    current_user: CurrentUser,
    service: HelpdeskSvc,
) -> APIResponse[TicketRead]:
    ticket = await service.change_status(ticket_id, payload, actor_id=current_user.id)
    return APIResponse.ok(await service.present(ticket), message="Status updated")


@router.post(
    "/{ticket_id}/assign",
    dependencies=[require("helpdesk:assign")],
    response_model=APIResponse[TicketRead],
    summary="Assign a request",
    description="Pass null to return it to its queue.",
    responses={**_ERRORS},
)
async def assign(
    ticket_id: uuid.UUID,
    payload: TicketAssign,
    current_user: CurrentUser,
    service: HelpdeskSvc,
) -> APIResponse[TicketRead]:
    ticket = await service.assign(ticket_id, payload, actor_id=current_user.id)
    return APIResponse.ok(await service.present(ticket), message="Request assigned")


@router.post(
    "/{ticket_id}/reclassify",
    dependencies=[require("helpdesk:update")],
    response_model=APIResponse[TicketRead],
    summary="Change a request's category or priority",
    description="The due time is not recomputed: escalating a late ticket does not reset its clock.",
    responses={**_ERRORS},
)
async def reclassify(
    ticket_id: uuid.UUID,
    payload: TicketReclassify,
    current_user: CurrentUser,
    service: HelpdeskSvc,
) -> APIResponse[TicketRead]:
    ticket = await service.reclassify(ticket_id, payload, actor_id=current_user.id)
    return APIResponse.ok(await service.present(ticket), message="Request updated")


# ======================================================================
# Announcements
# ======================================================================
@announcements_router.get(
    "",
    dependencies=[require("announcements:view")],
    response_model=APIResponse[Page[AnnouncementRead]],
    summary="Announcements",
    description="Everything, including drafts. Employees read theirs through /me/announcements.",
    responses={**_ERRORS},
)
async def list_announcements(
    params: AnnouncementParams, current_user: CurrentUser, service: AnnouncementSvc
) -> APIResponse[Page[AnnouncementRead]]:
    del current_user
    rows, total = await service.list_announcements(params)
    items = [await service.present(row) for row in rows]
    return APIResponse.ok(Page.create(items, page=params.page, page_size=params.page_size, total_items=total))


@announcements_router.post(
    "",
    dependencies=[require("announcements:create")],
    response_model=APIResponse[AnnouncementRead],
    status_code=status.HTTP_201_CREATED,
    summary="Draft an announcement",
    description="Creates it as a draft. Sending it is a separate act with a separate permission.",
    responses={**_ERRORS},
)
async def create_announcement(
    payload: AnnouncementCreate, current_user: CurrentUser, service: AnnouncementSvc
) -> APIResponse[AnnouncementRead]:
    announcement = await service.create(payload, actor_id=current_user.id)
    return APIResponse.ok(await service.present(announcement), message="Announcement drafted")


@announcements_router.get(
    "/{announcement_id}",
    dependencies=[require("announcements:view")],
    response_model=APIResponse[AnnouncementDetail],
    summary="One announcement, with its acknowledgements",
    responses={**_ERRORS},
)
async def get_announcement(
    announcement_id: uuid.UUID, current_user: CurrentUser, service: AnnouncementSvc
) -> APIResponse[AnnouncementDetail]:
    del current_user
    announcement = await service.get(announcement_id)
    return APIResponse.ok(await service.present_detail(announcement))


@announcements_router.patch(
    "/{announcement_id}",
    dependencies=[require("announcements:update")],
    response_model=APIResponse[AnnouncementRead],
    summary="Amend an announcement",
    responses={**_ERRORS},
)
async def update_announcement(
    announcement_id: uuid.UUID,
    payload: AnnouncementUpdate,
    current_user: CurrentUser,
    service: AnnouncementSvc,
) -> APIResponse[AnnouncementRead]:
    announcement = await service.update(announcement_id, payload, actor_id=current_user.id)
    return APIResponse.ok(await service.present(announcement), message="Announcement updated")


@announcements_router.post(
    "/{announcement_id}/publish",
    dependencies=[require("announcements:publish")],
    response_model=APIResponse[AnnouncementRead],
    summary="Publish an announcement",
    description=(
        "Sends it to its audience through the notification inbox. Pass publish_at to schedule it. "
        "Deliberately a separate permission from writing one."
    ),
    responses={**_ERRORS},
)
async def publish_announcement(
    announcement_id: uuid.UUID,
    payload: AnnouncementPublish,
    current_user: CurrentUser,
    service: AnnouncementSvc,
) -> APIResponse[AnnouncementRead]:
    announcement = await service.publish(announcement_id, payload, actor_id=current_user.id)
    return APIResponse.ok(await service.present(announcement), message="Announcement published")


@announcements_router.post(
    "/{announcement_id}/archive",
    dependencies=[require("announcements:update")],
    response_model=APIResponse[AnnouncementRead],
    summary="Archive an announcement",
    description="Takes it off the screen. The record of what was said remains.",
    responses={**_ERRORS},
)
async def archive_announcement(
    announcement_id: uuid.UUID, current_user: CurrentUser, service: AnnouncementSvc
) -> APIResponse[AnnouncementRead]:
    announcement = await service.archive(announcement_id, actor_id=current_user.id)
    return APIResponse.ok(await service.present(announcement), message="Announcement archived")


@announcements_router.delete(
    "/{announcement_id}",
    dependencies=[require("announcements:delete")],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an announcement",
    description="Removes it from the record. Archiving is the ordinary way to retire one.",
    responses={**_ERRORS},
)
async def delete_announcement(
    announcement_id: uuid.UUID, current_user: CurrentUser, service: AnnouncementSvc
) -> Response:
    await service.delete(announcement_id, actor_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
