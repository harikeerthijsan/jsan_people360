import uuid
from typing import Any, Literal

from fastapi import APIRouter, Response

from app.api.deps import CurrentUser, OnboardingSvc, Origin, require
from app.schemas.common import APIResponse
from app.schemas.onboarding import (
    CaseCreate,
    CaseRead,
    ConversionInput,
    DashboardRead,
    DocumentReview,
    PolicyInput,
    ProfileStart,
    ProfileUpdate,
    TaskRead,
    TaskUpdate,
)

router = APIRouter(prefix="/onboarding", tags=["Preboarding & Onboarding"])


@router.get(
    "/dashboard", dependencies=[require("onboarding:view")], response_model=APIResponse[DashboardRead]
)
async def dashboard(service: OnboardingSvc, current_user: CurrentUser) -> APIResponse[DashboardRead]:
    del current_user
    return APIResponse.ok(DashboardRead(**await service.dashboard()))


@router.get("/reports/export", dependencies=[require("onboarding:view")])
async def export_report(
    fmt: Literal["csv", "xlsx"], service: OnboardingSvc, current_user: CurrentUser
) -> Response:
    del current_user
    content, media_type = await service.export(fmt)
    extension = "csv" if fmt == "csv" else "xlsx"
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="onboarding-report.{extension}"'},
    )


@router.post("/profiles", dependencies=[require("onboarding:create")], status_code=201, response_model=None)
async def start(payload: ProfileStart, service: OnboardingSvc, current_user: CurrentUser) -> APIResponse[Any]:
    profile = await service.start(payload, current_user.id)
    return APIResponse.ok(await service.portal(profile.id))


@router.get("/profiles/{profile_id}", dependencies=[require("onboarding:view")], response_model=None)
async def portal(
    profile_id: uuid.UUID, service: OnboardingSvc, current_user: CurrentUser
) -> APIResponse[Any]:
    del current_user
    return APIResponse.ok(await service.portal(profile_id))


@router.put("/profiles/{profile_id}", dependencies=[require("onboarding:update")], response_model=None)
async def update_profile(
    profile_id: uuid.UUID, payload: ProfileUpdate, service: OnboardingSvc, current_user: CurrentUser
) -> APIResponse[Any]:
    return APIResponse.ok(await service.update_profile(profile_id, payload, current_user.id))


@router.post(
    "/profiles/{profile_id}/policies",
    dependencies=[require("onboarding:update")],
    status_code=201,
    response_model=None,
)
async def acknowledge(
    profile_id: uuid.UUID,
    payload: PolicyInput,
    service: OnboardingSvc,
    current_user: CurrentUser,
    origin: Origin,
) -> APIResponse[Any]:
    acknowledgement = await service.acknowledge(profile_id, payload, current_user.id, origin)
    return APIResponse.ok(
        {
            "id": acknowledgement.id,
            "policy_code": acknowledgement.policy_code,
            "acknowledged_at": acknowledgement.acknowledged_at,
        }
    )


@router.post(
    "/profiles/{profile_id}/documents/{document_id}/review",
    dependencies=[require("onboarding:update")],
    response_model=None,
)
async def review_document(
    profile_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: DocumentReview,
    service: OnboardingSvc,
    current_user: CurrentUser,
) -> APIResponse[Any]:
    document = await service.review_document(profile_id, document_id, payload, current_user.id)
    return APIResponse.ok(
        {
            "id": document.id,
            "name": document.name,
            "status": document.status,
            "review_notes": document.review_notes,
        }
    )


@router.post(
    "/profiles/{profile_id}/approve", dependencies=[require("onboarding:update")], response_model=None
)
async def approve_information(
    profile_id: uuid.UUID, service: OnboardingSvc, current_user: CurrentUser
) -> APIResponse[Any]:
    profile = await service.approve_information(profile_id, current_user.id)
    return APIResponse.ok(await service.portal(profile.id))


@router.post(
    "/profiles/{profile_id}/convert",
    dependencies=[require("employees:create")],
    status_code=201,
    response_model=None,
)
async def convert(
    profile_id: uuid.UUID, payload: ConversionInput, service: OnboardingSvc, current_user: CurrentUser
) -> APIResponse[Any]:
    employee = await service.convert(profile_id, payload, current_user.id)
    return APIResponse.ok({"employee_id": employee.id, "employee_code": employee.employee_code})


@router.post(
    "/profiles/{profile_id}/case",
    dependencies=[require("onboarding:create")],
    response_model=APIResponse[CaseRead],
    status_code=201,
)
async def create_case(
    profile_id: uuid.UUID, payload: CaseCreate, service: OnboardingSvc, current_user: CurrentUser
) -> APIResponse[CaseRead]:
    return APIResponse.ok(
        CaseRead.model_validate(await service.create_case(profile_id, payload, current_user.id))
    )


@router.patch(
    "/tasks/{task_id}", dependencies=[require("onboarding:update")], response_model=APIResponse[TaskRead]
)
async def update_task(
    task_id: uuid.UUID, payload: TaskUpdate, service: OnboardingSvc, current_user: CurrentUser
) -> APIResponse[TaskRead]:
    return APIResponse.ok(
        TaskRead.model_validate(await service.update_task(task_id, payload, current_user.id))
    )


@router.post(
    "/cases/{case_id}/complete",
    dependencies=[require("onboarding:update")],
    response_model=APIResponse[CaseRead],
)
async def complete(
    case_id: uuid.UUID, service: OnboardingSvc, current_user: CurrentUser
) -> APIResponse[CaseRead]:
    return APIResponse.ok(CaseRead.model_validate(await service.complete(case_id, current_user.id)))


@router.get("/cases/{case_id}/welcome", dependencies=[require("onboarding:view")], response_model=None)
async def welcome(case_id: uuid.UUID, service: OnboardingSvc, current_user: CurrentUser) -> APIResponse[Any]:
    del current_user
    return APIResponse.ok(await service.welcome(case_id))


@router.get(
    "/cases/{case_id}", dependencies=[require("onboarding:view")], response_model=APIResponse[CaseRead]
)
async def case_detail(
    case_id: uuid.UUID, service: OnboardingSvc, current_user: CurrentUser
) -> APIResponse[CaseRead]:
    del current_user
    return APIResponse.ok(CaseRead.model_validate(await service.case(case_id)))
