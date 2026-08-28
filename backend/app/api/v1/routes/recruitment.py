import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, RecruitmentSvc, require
from app.schemas.common import APIResponse, Page
from app.schemas.recruitment import (
    CandidateCreate,
    CandidateDocumentRead,
    CandidateListParams,
    CandidateRead,
    CandidateUpdate,
    DocumentLink,
    DuplicateResult,
    NoteCreate,
    NoteRead,
    OpeningCreate,
    OpeningRead,
    PoolMember,
    RecruitmentDashboard,
    SourceRead,
    StageCreate,
    StageMove,
    StageRead,
    TalentPoolCreate,
    TalentPoolRead,
)

router = APIRouter(prefix="/recruitment", tags=["Recruitment ATS"])


@router.get(
    "/dashboard", dependencies=[require("recruitment:view")], response_model=APIResponse[RecruitmentDashboard]
)
async def dashboard(service: RecruitmentSvc, current_user: CurrentUser) -> APIResponse[RecruitmentDashboard]:
    del current_user
    return APIResponse.ok(await service.dashboard())


@router.get("/references", dependencies=[require("recruitment:view")], response_model=None)
async def references(service: RecruitmentSvc, current_user: CurrentUser) -> APIResponse[Any]:
    del current_user
    sources, stages = await service.references()
    return APIResponse.ok(
        {
            "sources": [SourceRead.model_validate(x) for x in sources],
            "stages": [StageRead.model_validate(x) for x in stages],
        }
    )


@router.post(
    "/stages",
    dependencies=[require("recruitment:update")],
    response_model=APIResponse[StageRead],
    status_code=201,
)
async def create_stage(
    payload: StageCreate, service: RecruitmentSvc, current_user: CurrentUser
) -> APIResponse[StageRead]:
    return APIResponse.ok(StageRead.model_validate(await service.create_stage(payload, current_user.id)))


@router.get(
    "/openings", dependencies=[require("recruitment:view")], response_model=APIResponse[list[OpeningRead]]
)
async def openings(service: RecruitmentSvc, current_user: CurrentUser) -> APIResponse[list[OpeningRead]]:
    del current_user
    return APIResponse.ok([OpeningRead.model_validate(x) for x in await service.list_openings()])


@router.post(
    "/openings",
    dependencies=[require("recruitment:create")],
    response_model=APIResponse[OpeningRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_opening(
    payload: OpeningCreate, service: RecruitmentSvc, current_user: CurrentUser
) -> APIResponse[OpeningRead]:
    return APIResponse.ok(OpeningRead.model_validate(await service.create_opening(payload, current_user.id)))


@router.post(
    "/openings/{opening_id}/{action}",
    dependencies=[require("recruitment:update")],
    response_model=APIResponse[OpeningRead],
)
async def opening_action(
    opening_id: uuid.UUID,
    action: Literal["publish", "close", "cancel", "fill"],
    service: RecruitmentSvc,
    current_user: CurrentUser,
) -> APIResponse[OpeningRead]:
    return APIResponse.ok(
        OpeningRead.model_validate(await service.opening_action(opening_id, action, current_user.id))
    )


@router.get("/candidates/export", dependencies=[require("recruitment:export")])
async def export_candidates(
    service: RecruitmentSvc,
    current_user: CurrentUser,
    params: Annotated[CandidateListParams, Query()],
    format: Literal["csv", "xlsx"] = "xlsx",
) -> Response:
    del current_user
    content, mime = await service.export(params, format)
    return Response(
        content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="candidates.{format}"'},
    )


@router.get(
    "/candidates/duplicates",
    dependencies=[require("recruitment:view")],
    response_model=APIResponse[DuplicateResult],
)
async def duplicates(
    email: str, mobile: str, service: RecruitmentSvc, current_user: CurrentUser
) -> APIResponse[DuplicateResult]:
    del current_user
    rows = await service.duplicates(email, mobile)
    return APIResponse.ok(DuplicateResult(duplicates=[CandidateRead.model_validate(x) for x in rows]))


@router.get(
    "/candidates", dependencies=[require("recruitment:view")], response_model=APIResponse[Page[CandidateRead]]
)
async def candidates(
    service: RecruitmentSvc, current_user: CurrentUser, params: Annotated[CandidateListParams, Query()]
) -> APIResponse[Page[CandidateRead]]:
    del current_user
    rows, total = await service.search(params)
    return APIResponse.ok(
        Page.create(
            [CandidateRead.model_validate(x) for x in rows],
            page=params.page,
            page_size=params.page_size,
            total_items=total,
        )
    )


@router.post(
    "/candidates",
    dependencies=[require("recruitment:create")],
    response_model=APIResponse[CandidateRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_candidate(
    payload: CandidateCreate, service: RecruitmentSvc, current_user: CurrentUser
) -> APIResponse[CandidateRead]:
    return APIResponse.ok(
        CandidateRead.model_validate(await service.create_candidate(payload, current_user.id))
    )


@router.get(
    "/candidates/{candidate_id}",
    dependencies=[require("recruitment:view")],
    response_model=APIResponse[CandidateRead],
)
async def candidate(
    candidate_id: uuid.UUID, service: RecruitmentSvc, current_user: CurrentUser
) -> APIResponse[CandidateRead]:
    del current_user
    return APIResponse.ok(CandidateRead.model_validate(await service.get_candidate(candidate_id)))


@router.put(
    "/candidates/{candidate_id}",
    dependencies=[require("recruitment:update")],
    response_model=APIResponse[CandidateRead],
)
async def update_candidate(
    candidate_id: uuid.UUID, payload: CandidateUpdate, service: RecruitmentSvc, current_user: CurrentUser
) -> APIResponse[CandidateRead]:
    return APIResponse.ok(
        CandidateRead.model_validate(await service.update_candidate(candidate_id, payload, current_user.id))
    )


@router.post(
    "/candidates/{candidate_id}/stage",
    dependencies=[require("recruitment:update")],
    response_model=APIResponse[CandidateRead],
)
async def move_stage(
    candidate_id: uuid.UUID, payload: StageMove, service: RecruitmentSvc, current_user: CurrentUser
) -> APIResponse[CandidateRead]:
    return APIResponse.ok(
        CandidateRead.model_validate(await service.move_stage(candidate_id, payload, current_user.id))
    )


@router.post(
    "/candidates/{candidate_id}/documents",
    dependencies=[require("recruitment:update")],
    response_model=APIResponse[CandidateDocumentRead],
    status_code=201,
)
async def link_document(
    candidate_id: uuid.UUID, payload: DocumentLink, service: RecruitmentSvc, current_user: CurrentUser
) -> APIResponse[CandidateDocumentRead]:
    return APIResponse.ok(
        CandidateDocumentRead.model_validate(
            await service.link_document(candidate_id, payload, current_user.id)
        )
    )


@router.post(
    "/candidates/{candidate_id}/notes",
    dependencies=[require("recruitment:update")],
    response_model=APIResponse[NoteRead],
    status_code=201,
)
async def add_note(
    candidate_id: uuid.UUID, payload: NoteCreate, service: RecruitmentSvc, current_user: CurrentUser
) -> APIResponse[NoteRead]:
    return APIResponse.ok(
        NoteRead.model_validate(await service.add_note(candidate_id, payload, current_user.id))
    )


@router.get(
    "/talent-pools",
    dependencies=[require("recruitment:view")],
    response_model=APIResponse[list[TalentPoolRead]],
)
async def pools(service: RecruitmentSvc, current_user: CurrentUser) -> APIResponse[list[TalentPoolRead]]:
    del current_user
    return APIResponse.ok([TalentPoolRead.model_validate(x) for x in await service.list_pools()])


@router.post(
    "/talent-pools",
    dependencies=[require("recruitment:create")],
    response_model=APIResponse[TalentPoolRead],
    status_code=201,
)
async def create_pool(
    payload: TalentPoolCreate, service: RecruitmentSvc, current_user: CurrentUser
) -> APIResponse[TalentPoolRead]:
    return APIResponse.ok(TalentPoolRead.model_validate(await service.create_pool(payload, current_user.id)))


@router.post(
    "/talent-pools/{pool_id}/members",
    dependencies=[require("recruitment:update")],
    status_code=201,
    response_model=None,
)
async def add_pool_member(
    pool_id: uuid.UUID, payload: PoolMember, service: RecruitmentSvc, current_user: CurrentUser
) -> APIResponse[Any]:
    item = await service.add_pool_member(pool_id, payload.candidate_id, current_user.id)
    return APIResponse.ok(
        {
            "id": str(item.id),
            "candidate_id": str(item.candidate_id),
            "talent_pool_id": str(item.talent_pool_id),
        }
    )
