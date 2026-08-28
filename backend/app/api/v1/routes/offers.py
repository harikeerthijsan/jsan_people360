import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from app.api.deps import CurrentUser, OfferSvc, require
from app.schemas.common import APIResponse, Page
from app.schemas.offer import (
    ApprovalAction,
    ClarificationRequest,
    OfferCreate,
    OfferDashboard,
    OfferListParams,
    OfferRead,
    OfferUpdate,
    ReasonRequest,
    TemplateCreate,
    TemplateRead,
)

router = APIRouter(prefix="/offers", tags=["Offer Management"])


@router.get("/dashboard", dependencies=[require("offers:view")], response_model=APIResponse[OfferDashboard])
async def dashboard(service: OfferSvc, current_user: CurrentUser) -> APIResponse[OfferDashboard]:
    del current_user
    return APIResponse.ok(await service.dashboard())


@router.get(
    "/templates", dependencies=[require("offers:view")], response_model=APIResponse[list[TemplateRead]]
)
async def templates(service: OfferSvc, current_user: CurrentUser) -> APIResponse[list[TemplateRead]]:
    del current_user
    return APIResponse.ok([TemplateRead.model_validate(x) for x in await service.templates_list()])


@router.post(
    "/templates",
    dependencies=[require("offers:create")],
    response_model=APIResponse[TemplateRead],
    status_code=201,
)
async def create_template(
    p: TemplateCreate, service: OfferSvc, current_user: CurrentUser
) -> APIResponse[TemplateRead]:
    return APIResponse.ok(TemplateRead.model_validate(await service.template_create(p, current_user.id)))


@router.get("", dependencies=[require("offers:view")], response_model=APIResponse[Page[OfferRead]])
async def listing(
    service: OfferSvc, current_user: CurrentUser, p: Annotated[OfferListParams, Query()]
) -> APIResponse[Page[OfferRead]]:
    del current_user
    rows, total = await service.list(p)
    return APIResponse.ok(
        Page.create(
            [OfferRead.model_validate(x) for x in rows], page=p.page, page_size=p.page_size, total_items=total
        )
    )


@router.post(
    "", dependencies=[require("offers:create")], response_model=APIResponse[OfferRead], status_code=201
)
async def create(p: OfferCreate, service: OfferSvc, current_user: CurrentUser) -> APIResponse[OfferRead]:
    return APIResponse.ok(OfferRead.model_validate(await service.create(p, current_user.id)))


@router.get("/{oid}", dependencies=[require("offers:view")], response_model=APIResponse[OfferRead])
async def detail(oid: uuid.UUID, service: OfferSvc, current_user: CurrentUser) -> APIResponse[OfferRead]:
    del current_user
    return APIResponse.ok(OfferRead.model_validate(await service.get(oid)))


@router.put("/{oid}", dependencies=[require("offers:update")], response_model=APIResponse[OfferRead])
async def edit(
    oid: uuid.UUID, p: OfferUpdate, service: OfferSvc, current_user: CurrentUser
) -> APIResponse[OfferRead]:
    return APIResponse.ok(OfferRead.model_validate(await service.update(oid, p, current_user.id)))


@router.post("/{oid}/submit", dependencies=[require("offers:update")], response_model=APIResponse[OfferRead])
async def submit(oid: uuid.UUID, service: OfferSvc, current_user: CurrentUser) -> APIResponse[OfferRead]:
    return APIResponse.ok(OfferRead.model_validate(await service.submit(oid, current_user.id)))


@router.post(
    "/{oid}/approval/{action}",
    dependencies=[require("offers:approve")],
    response_model=APIResponse[OfferRead],
)
async def approval(
    oid: uuid.UUID,
    action: Literal["approve", "reject", "send_back"],
    p: ApprovalAction,
    service: OfferSvc,
    current_user: CurrentUser,
) -> APIResponse[OfferRead]:
    return APIResponse.ok(
        OfferRead.model_validate(await service.approval(oid, action, p.comments, current_user.id))
    )


@router.post("/{oid}/pdf", dependencies=[require("offers:view")])
async def pdf(oid: uuid.UUID, service: OfferSvc, current_user: CurrentUser) -> Response:
    doc, content = await service.generate_pdf(oid, current_user.id)
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="offer-{oid}.pdf"', "X-Document-Id": str(doc)},
    )


@router.post(
    "/{oid}/release", dependencies=[require("offers:approve")], response_model=APIResponse[OfferRead]
)
async def release(oid: uuid.UUID, service: OfferSvc, current_user: CurrentUser) -> APIResponse[OfferRead]:
    return APIResponse.ok(OfferRead.model_validate(await service.release(oid, current_user.id)))


@router.post("/{oid}/accept", dependencies=[require("offers:update")], response_model=APIResponse[OfferRead])
async def accept(oid: uuid.UUID, service: OfferSvc, current_user: CurrentUser) -> APIResponse[OfferRead]:
    return APIResponse.ok(
        OfferRead.model_validate(await service.candidate_action(oid, "accept", None, current_user.id))
    )


@router.post("/{oid}/decline", dependencies=[require("offers:update")], response_model=APIResponse[OfferRead])
async def decline(
    oid: uuid.UUID, p: ReasonRequest, service: OfferSvc, current_user: CurrentUser
) -> APIResponse[OfferRead]:
    return APIResponse.ok(
        OfferRead.model_validate(await service.candidate_action(oid, "decline", p.reason, current_user.id))
    )


@router.post(
    "/{oid}/clarification", dependencies=[require("offers:update")], response_model=APIResponse[OfferRead]
)
async def clarification(
    oid: uuid.UUID, p: ClarificationRequest, service: OfferSvc, current_user: CurrentUser
) -> APIResponse[OfferRead]:
    return APIResponse.ok(
        OfferRead.model_validate(
            await service.candidate_action(oid, "clarification", p.message, current_user.id)
        )
    )


@router.post(
    "/{oid}/withdraw", dependencies=[require("offers:approve")], response_model=APIResponse[OfferRead]
)
async def withdraw(
    oid: uuid.UUID, p: ReasonRequest, service: OfferSvc, current_user: CurrentUser
) -> APIResponse[OfferRead]:
    return APIResponse.ok(OfferRead.model_validate(await service.withdraw(oid, p.reason, current_user.id)))
