import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response

from app.api.deps import CurrentUser, ProjectSvc, require, require_team_scope
from app.schemas.common import APIResponse, Page
from app.schemas.project import (
    AllocationChange,
    AllocationCreate,
    AllocationRead,
    AllocationRemove,
    ClientCreate,
    ClientRead,
    ClientUpdate,
    DashboardRead,
    HistoryRead,
    ListParams,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["Project & Client Allocation"])


@router.get("/dashboard", dependencies=[require("projects:view")], response_model=APIResponse[DashboardRead])
async def dashboard(service: ProjectSvc, current_user: CurrentUser) -> APIResponse[DashboardRead]:
    del current_user
    return APIResponse.ok(DashboardRead(**await service.dashboard()))


@router.get("/bench", dependencies=[require("projects:view")], response_model=None)
async def bench(service: ProjectSvc, current_user: CurrentUser) -> APIResponse[Any]:
    del current_user
    return APIResponse.ok(await service.bench())


@router.get("/reports/export", dependencies=[require("projects:export")])
async def export(
    report: Literal["clients", "projects", "allocations", "bench", "utilization"],
    fmt: Literal["csv", "xlsx"],
    service: ProjectSvc,
    current_user: CurrentUser,
) -> Response:
    del current_user
    content, media = await service.export(report, fmt)
    return Response(
        content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{report}.{fmt}"'}
    )


@router.get("/clients", dependencies=[require("projects:view")], response_model=APIResponse[Page[ClientRead]])
async def clients(
    service: ProjectSvc, current_user: CurrentUser, params: Annotated[ListParams, Query()]
) -> APIResponse[Page[ClientRead]]:
    del current_user
    rows, total = await service.list_clients(params)
    return APIResponse.ok(
        Page.create(
            [ClientRead.model_validate(x) for x in rows],
            page=params.page,
            page_size=params.page_size,
            total_items=total,
        )
    )


@router.post(
    "/clients",
    dependencies=[require("projects:create")],
    response_model=APIResponse[ClientRead],
    status_code=201,
)
async def create_client(
    payload: ClientCreate, service: ProjectSvc, current_user: CurrentUser
) -> APIResponse[ClientRead]:
    return APIResponse.ok(ClientRead.model_validate(await service.create_client(payload, current_user.id)))


@router.get(
    "/clients/{client_id}", dependencies=[require("projects:view")], response_model=APIResponse[ClientRead]
)
async def client(
    client_id: uuid.UUID, service: ProjectSvc, current_user: CurrentUser
) -> APIResponse[ClientRead]:
    del current_user
    return APIResponse.ok(ClientRead.model_validate(await service.get_client(client_id)))


@router.put(
    "/clients/{client_id}", dependencies=[require("projects:update")], response_model=APIResponse[ClientRead]
)
async def update_client(
    client_id: uuid.UUID, payload: ClientUpdate, service: ProjectSvc, current_user: CurrentUser
) -> APIResponse[ClientRead]:
    return APIResponse.ok(
        ClientRead.model_validate(await service.update_client(client_id, payload, current_user.id))
    )


@router.delete("/clients/{client_id}", dependencies=[require("projects:delete")], status_code=204)
async def delete_client(client_id: uuid.UUID, service: ProjectSvc, current_user: CurrentUser) -> Response:
    await service.archive_client(client_id, current_user.id)
    return Response(status_code=204)


@router.get("/clients/{client_id}/dashboard", dependencies=[require("projects:view")], response_model=None)
async def client_dashboard(
    client_id: uuid.UUID, service: ProjectSvc, current_user: CurrentUser
) -> APIResponse[Any]:
    del current_user
    data = await service.client_dashboard(client_id)
    data["client"] = ClientRead.model_validate(data["client"]).model_dump(mode="json")
    return APIResponse.ok(data)


@router.get(
    "/employees/{employee_id}/allocation-history",
    # Scoped as well as permissioned: `projects:view` says the caller may use
    # the projects module, not that they may read this particular person's
    # placement history. Every seat that holds it -- Manager, Team Lead, Project
    # Manager, HR -- could otherwise read anybody's by changing the id.
    dependencies=[require("projects:view"), require_team_scope()],
    response_model=APIResponse[list[HistoryRead]],
)
async def history(
    employee_id: uuid.UUID, service: ProjectSvc, current_user: CurrentUser
) -> APIResponse[list[HistoryRead]]:
    del current_user
    return APIResponse.ok(
        [HistoryRead.model_validate(x) for x in await service.allocation_history(employee_id)]
    )


@router.post(
    "/allocations/{allocation_id}/change",
    dependencies=[require("projects:update")],
    response_model=APIResponse[AllocationRead],
)
async def change(
    allocation_id: uuid.UUID, payload: AllocationChange, service: ProjectSvc, current_user: CurrentUser
) -> APIResponse[AllocationRead]:
    return APIResponse.ok(
        AllocationRead.model_validate(await service.change(allocation_id, payload, current_user.id))
    )


@router.post(
    "/allocations/{allocation_id}/remove",
    dependencies=[require("projects:update")],
    response_model=APIResponse[AllocationRead],
)
async def remove(
    allocation_id: uuid.UUID, payload: AllocationRemove, service: ProjectSvc, current_user: CurrentUser
) -> APIResponse[AllocationRead]:
    return APIResponse.ok(
        AllocationRead.model_validate(await service.remove(allocation_id, payload, current_user.id))
    )


@router.get("", dependencies=[require("projects:view")], response_model=APIResponse[Page[ProjectRead]])
async def projects(
    service: ProjectSvc, current_user: CurrentUser, params: Annotated[ListParams, Query()]
) -> APIResponse[Page[ProjectRead]]:
    del current_user
    rows, total = await service.list_projects(params)
    return APIResponse.ok(
        Page.create(
            [ProjectRead.model_validate(x) for x in rows],
            page=params.page,
            page_size=params.page_size,
            total_items=total,
        )
    )


@router.post(
    "", dependencies=[require("projects:create")], response_model=APIResponse[ProjectRead], status_code=201
)
async def create_project(
    payload: ProjectCreate, service: ProjectSvc, current_user: CurrentUser
) -> APIResponse[ProjectRead]:
    return APIResponse.ok(ProjectRead.model_validate(await service.create_project(payload, current_user.id)))


@router.get("/{project_id}", dependencies=[require("projects:view")], response_model=APIResponse[ProjectRead])
async def project(
    project_id: uuid.UUID, service: ProjectSvc, current_user: CurrentUser
) -> APIResponse[ProjectRead]:
    del current_user
    return APIResponse.ok(ProjectRead.model_validate(await service.get_project(project_id)))


@router.put(
    "/{project_id}", dependencies=[require("projects:update")], response_model=APIResponse[ProjectRead]
)
async def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, service: ProjectSvc, current_user: CurrentUser
) -> APIResponse[ProjectRead]:
    return APIResponse.ok(
        ProjectRead.model_validate(await service.update_project(project_id, payload, current_user.id))
    )


@router.get("/{project_id}/dashboard", dependencies=[require("projects:view")], response_model=None)
async def project_dashboard(
    project_id: uuid.UUID, service: ProjectSvc, current_user: CurrentUser
) -> APIResponse[Any]:
    del current_user
    data = await service.project_dashboard(project_id)
    data["project"] = ProjectRead.model_validate(data["project"]).model_dump(mode="json")
    data["team_members"] = [
        AllocationRead.model_validate(x).model_dump(mode="json") for x in data["team_members"]
    ]
    data["upcoming_end_dates"] = [
        AllocationRead.model_validate(x).model_dump(mode="json") for x in data["upcoming_end_dates"]
    ]
    return APIResponse.ok(data)


@router.post(
    "/{project_id}/allocations",
    dependencies=[require("projects:update")],
    response_model=APIResponse[AllocationRead],
    status_code=201,
)
async def assign(
    project_id: uuid.UUID, payload: AllocationCreate, service: ProjectSvc, current_user: CurrentUser
) -> APIResponse[AllocationRead]:
    return APIResponse.ok(
        AllocationRead.model_validate(await service.assign(project_id, payload, current_user.id))
    )
