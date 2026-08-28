import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, InterviewSvc, require
from app.schemas.common import APIResponse, Page
from app.schemas.interview import (
    AttachmentLink,
    AttachmentRead,
    CancelRequest,
    DecisionRequest,
    FeedbackCreate,
    InterviewCreate,
    InterviewDashboard,
    InterviewListParams,
    InterviewRead,
    InterviewUpdate,
    PanelAssign,
    RescheduleRequest,
)

router = APIRouter(prefix="/interviews", tags=["Interview Management"])


@router.get(
    "/dashboard", dependencies=[require("interviews:view")], response_model=APIResponse[InterviewDashboard]
)
async def dashboard(service: InterviewSvc, current_user: CurrentUser) -> APIResponse[InterviewDashboard]:
    del current_user
    return APIResponse.ok(await service.dashboard())


@router.get("/export", dependencies=[require("interviews:view")])
async def export(
    service: InterviewSvc,
    current_user: CurrentUser,
    params: Annotated[InterviewListParams, Query()],
    format: Literal["csv", "xlsx"] = "xlsx",
) -> Response:
    del current_user
    content, mime = await service.export(params, format)
    return Response(
        content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="interviews.{format}"'},
    )


@router.get("", dependencies=[require("interviews:view")], response_model=APIResponse[Page[InterviewRead]])
async def list_interviews(
    service: InterviewSvc, current_user: CurrentUser, params: Annotated[InterviewListParams, Query()]
) -> APIResponse[Page[InterviewRead]]:
    del current_user
    rows, total = await service.list(params)
    return APIResponse.ok(
        Page.create(
            [InterviewRead.model_validate(x) for x in rows],
            page=params.page,
            page_size=params.page_size,
            total_items=total,
        )
    )


@router.post(
    "",
    dependencies=[require("interviews:create")],
    response_model=APIResponse[InterviewRead],
    status_code=status.HTTP_201_CREATED,
)
async def schedule(
    payload: InterviewCreate, service: InterviewSvc, current_user: CurrentUser
) -> APIResponse[InterviewRead]:
    return APIResponse.ok(InterviewRead.model_validate(await service.schedule(payload, current_user.id)))


@router.get(
    "/{interview_id}", dependencies=[require("interviews:view")], response_model=APIResponse[InterviewRead]
)
async def detail(
    interview_id: uuid.UUID, service: InterviewSvc, current_user: CurrentUser
) -> APIResponse[InterviewRead]:
    del current_user
    return APIResponse.ok(InterviewRead.model_validate(await service.get(interview_id)))


@router.put(
    "/{interview_id}", dependencies=[require("interviews:update")], response_model=APIResponse[InterviewRead]
)
async def update(
    interview_id: uuid.UUID, payload: InterviewUpdate, service: InterviewSvc, current_user: CurrentUser
) -> APIResponse[InterviewRead]:
    return APIResponse.ok(
        InterviewRead.model_validate(await service.update(interview_id, payload, current_user.id))
    )


@router.post(
    "/{interview_id}/reschedule",
    dependencies=[require("interviews:update")],
    response_model=APIResponse[InterviewRead],
)
async def reschedule(
    interview_id: uuid.UUID, payload: RescheduleRequest, service: InterviewSvc, current_user: CurrentUser
) -> APIResponse[InterviewRead]:
    return APIResponse.ok(
        InterviewRead.model_validate(await service.reschedule(interview_id, payload, current_user.id))
    )


@router.post(
    "/{interview_id}/cancel",
    dependencies=[require("interviews:update")],
    response_model=APIResponse[InterviewRead],
)
async def cancel(
    interview_id: uuid.UUID, payload: CancelRequest, service: InterviewSvc, current_user: CurrentUser
) -> APIResponse[InterviewRead]:
    return APIResponse.ok(
        InterviewRead.model_validate(await service.cancel(interview_id, payload.comments, current_user.id))
    )


@router.put(
    "/{interview_id}/panel",
    dependencies=[require("interviews:update")],
    response_model=APIResponse[InterviewRead],
)
async def panel(
    interview_id: uuid.UUID, payload: list[PanelAssign], service: InterviewSvc, current_user: CurrentUser
) -> APIResponse[InterviewRead]:
    return APIResponse.ok(
        InterviewRead.model_validate(await service.replace_panel(interview_id, payload, current_user.id))
    )


@router.post(
    "/{interview_id}/feedback",
    dependencies=[require("interviews:update")],
    response_model=APIResponse[InterviewRead],
    status_code=201,
)
async def feedback(
    interview_id: uuid.UUID, payload: FeedbackCreate, service: InterviewSvc, current_user: CurrentUser
) -> APIResponse[InterviewRead]:
    return APIResponse.ok(
        InterviewRead.model_validate(await service.submit_feedback(interview_id, payload, current_user.id))
    )


@router.post(
    "/{interview_id}/decision",
    dependencies=[require("recruitment:approve")],
    response_model=APIResponse[InterviewRead],
)
async def decision(
    interview_id: uuid.UUID, payload: DecisionRequest, service: InterviewSvc, current_user: CurrentUser
) -> APIResponse[InterviewRead]:
    return APIResponse.ok(
        InterviewRead.model_validate(await service.decision(interview_id, payload, current_user.id))
    )


@router.post(
    "/{interview_id}/attachments",
    dependencies=[require("interviews:update")],
    response_model=APIResponse[AttachmentRead],
    status_code=201,
)
async def attachment(
    interview_id: uuid.UUID, payload: AttachmentLink, service: InterviewSvc, current_user: CurrentUser
) -> APIResponse[AttachmentRead]:
    return APIResponse.ok(
        AttachmentRead.model_validate(await service.attach(interview_id, payload, current_user.id))
    )
