import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, RequisitionSvc, require
from app.schemas.common import APIResponse, Page
from app.schemas.requisition import (
    AttachmentLink,
    AttachmentRead,
    DashboardStats,
    NotificationRead,
    RequisitionCreate,
    RequisitionListParams,
    RequisitionRead,
    RequisitionUpdate,
    WorkflowAction,
)

router = APIRouter(prefix="/requisitions", tags=["Job Requisitions"])
notification_router = APIRouter(prefix="/notifications", tags=["Notifications"])


@notification_router.get("", response_model=APIResponse[list[NotificationRead]])
async def notifications(
    service: RequisitionSvc, current_user: CurrentUser
) -> APIResponse[list[NotificationRead]]:
    rows = await service.user_notifications(current_user.id)
    return APIResponse.ok([NotificationRead.model_validate(row) for row in rows])


@notification_router.post("/{notification_id}/read", response_model=APIResponse[NotificationRead])
async def mark_notification_read(
    notification_id: uuid.UUID, service: RequisitionSvc, current_user: CurrentUser
) -> APIResponse[NotificationRead]:
    item = await service.mark_notification_read(notification_id, current_user.id)
    return APIResponse.ok(NotificationRead.model_validate(item))


@router.get(
    "/dashboard", dependencies=[require("requisitions:view")], response_model=APIResponse[DashboardStats]
)
async def dashboard(service: RequisitionSvc, current_user: CurrentUser) -> APIResponse[DashboardStats]:
    del current_user
    return APIResponse.ok(await service.dashboard())


@router.get("/export", dependencies=[require("requisitions:view")])
async def export_requisitions(
    service: RequisitionSvc,
    current_user: CurrentUser,
    params: Annotated[RequisitionListParams, Query()],
    format: Literal["csv", "xlsx"] = "xlsx",
) -> Response:
    del current_user
    content, mime = await service.export(params, format)
    ext = "csv" if format == "csv" else "xlsx"
    return Response(
        content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="requisitions.{ext}"'},
    )


@router.get(
    "", dependencies=[require("requisitions:view")], response_model=APIResponse[Page[RequisitionRead]]
)
async def list_requisitions(
    service: RequisitionSvc, current_user: CurrentUser, params: Annotated[RequisitionListParams, Query()]
) -> APIResponse[Page[RequisitionRead]]:
    del current_user
    rows, total = await service.list(params)
    return APIResponse.ok(
        Page.create(
            [RequisitionRead.model_validate(x) for x in rows],
            page=params.page,
            page_size=params.page_size,
            total_items=total,
        )
    )


@router.post(
    "",
    dependencies=[require("requisitions:create")],
    response_model=APIResponse[RequisitionRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_requisition(
    payload: RequisitionCreate, service: RequisitionSvc, current_user: CurrentUser
) -> APIResponse[RequisitionRead]:
    return APIResponse.ok(
        RequisitionRead.model_validate(await service.create(payload, current_user.id)), "Requisition created"
    )


@router.get(
    "/{requisition_id}",
    dependencies=[require("requisitions:view")],
    response_model=APIResponse[RequisitionRead],
)
async def get_requisition(
    requisition_id: uuid.UUID, service: RequisitionSvc, current_user: CurrentUser
) -> APIResponse[RequisitionRead]:
    del current_user
    return APIResponse.ok(RequisitionRead.model_validate(await service.get(requisition_id)))


@router.put(
    "/{requisition_id}",
    dependencies=[require("requisitions:update")],
    response_model=APIResponse[RequisitionRead],
)
async def update_requisition(
    requisition_id: uuid.UUID, payload: RequisitionUpdate, service: RequisitionSvc, current_user: CurrentUser
) -> APIResponse[RequisitionRead]:
    return APIResponse.ok(
        RequisitionRead.model_validate(await service.update(requisition_id, payload, current_user.id))
    )


@router.post(
    "/{requisition_id}/submit",
    dependencies=[require("requisitions:update")],
    response_model=APIResponse[RequisitionRead],
)
async def submit(
    requisition_id: uuid.UUID, service: RequisitionSvc, current_user: CurrentUser
) -> APIResponse[RequisitionRead]:
    return APIResponse.ok(
        RequisitionRead.model_validate(await service.submit(requisition_id, current_user.id))
    )


@router.post(
    "/{requisition_id}/attachments",
    dependencies=[require("requisitions:update")],
    response_model=APIResponse[AttachmentRead],
    status_code=201,
)
async def attach(
    requisition_id: uuid.UUID, payload: AttachmentLink, service: RequisitionSvc, current_user: CurrentUser
) -> APIResponse[AttachmentRead]:
    return APIResponse.ok(
        AttachmentRead.model_validate(await service.attach(requisition_id, payload, current_user.id))
    )


@router.post(
    "/{requisition_id}/{action}",
    dependencies=[require("requisitions:approve")],
    response_model=APIResponse[RequisitionRead],
)
async def workflow(
    requisition_id: uuid.UUID,
    action: Literal["approve", "reject", "send_back", "cancel", "close", "open", "hold", "resume"],
    payload: WorkflowAction,
    service: RequisitionSvc,
    current_user: CurrentUser,
) -> APIResponse[RequisitionRead]:
    return APIResponse.ok(
        RequisitionRead.model_validate(
            await service.act(requisition_id, action, payload.comments, current_user.id)
        )
    )
