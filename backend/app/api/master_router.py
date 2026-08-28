"""Factory that builds the six standard endpoints for a master-data entity.

Nine masters times six endpoints is fifty-four routes. Written by hand they
would be fifty-four opportunities for the response envelope, the status codes or
the audit behaviour to drift apart. Built here, every master gets exactly the
same HTTP contract, and each entity's route module stays a short declaration.

The endpoints remain fully described in OpenAPI: the schema classes are passed
in, so ``response_model`` is concrete for every route.

NOTE: this module deliberately does *not* use ``from __future__ import
annotations``. FastAPI reads parameter types from evaluated annotations, and
postponed evaluation would turn the runtime schema variables below into strings
it cannot resolve.
"""

import uuid
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Path, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, require
from app.core.permissions import PermissionAction, code
from app.schemas.common import APIErrorResponse, APIResponse, Page
from app.schemas.masters import MasterListParams
from app.services.master_service import MasterService


def _envelope(model: type[BaseModel], *, paged: bool = False) -> Any:
    """``APIResponse[model]``, or ``APIResponse[Page[model]]``, built from a value.

    The schema classes arrive as arguments, so this parametrisation happens at
    runtime -- which is precisely what keeps ``response_model`` concrete in
    OpenAPI for all nine masters instead of degrading to a bare object. It
    cannot be expressed statically, so the return type is ``Any`` and the one
    unavoidable silence lives here rather than at each of the six routes.
    """
    inner: Any = Page[model] if paged else model  # type: ignore[valid-type]
    return APIResponse[inner]


#: Error responses every master endpoint can produce.
_COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": APIErrorResponse,
        "description": "Validation failed.",
    },
}
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such record."},
}
_CONFLICT: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {
        "model": APIErrorResponse,
        "description": "Duplicate name or code, or a referential rule was violated.",
    },
}


def build_master_router(
    *,
    prefix: str,
    tag: str,
    entity_label: str,
    entity_label_plural: str,
    read_schema: type[BaseModel],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    service_dependency: Any,
    params_schema: type[MasterListParams] = MasterListParams,
    permission_module: str,
) -> APIRouter:
    """Build the List / Get / Create / Update / Archive / Restore endpoints.

    Args:
        prefix: URL segment, e.g. ``/business-units``.
        tag: OpenAPI tag the routes are grouped under.
        entity_label: Singular label used in response messages.
        entity_label_plural: Plural label used in response messages.
        read_schema: Response model for a single record.
        create_schema: Request body for creation.
        update_schema: Request body for a partial update.
        service_dependency: Callable resolving the entity's service.
        params_schema: Query-parameter model; entities with a parent pass an
            extended one that adds the parent filter.
        permission_module: Which module's permissions gate these six routes.
            Required rather than defaulted: a master built without naming one
            would be silently unguarded, and that is the failure this whole
            layer exists to prevent.
    """
    view = require(code(permission_module, PermissionAction.VIEW))
    create = require(code(permission_module, PermissionAction.CREATE))
    update = require(code(permission_module, PermissionAction.UPDATE))
    # Archive and restore move a record in and out of the active set, which
    # is this module's destructive action.
    remove = require(code(permission_module, PermissionAction.DELETE))
    router = APIRouter(prefix=prefix, tags=[tag])

    ServiceDep = Annotated[MasterService[Any, Any, Any, Any], Depends(service_dependency)]
    ListParams = Annotated[params_schema, Query()]  # type: ignore[valid-type]
    RecordId = Annotated[uuid.UUID, Path(description=f"Identifier of the {entity_label.lower()}.")]

    singular = entity_label.lower()
    plural = entity_label_plural.lower()

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    @router.get(
        "",
        dependencies=[view],
        response_model=_envelope(read_schema, paged=True),
        summary=f"List {plural}",
        description=(
            f"Returns a page of {plural} with search, status filtering and sorting. "
            "Live and archived records are never mixed: pass `archived=true` to see "
            "the archive."
        ),
        responses={**_COMMON_ERRORS},
    )
    async def list_records(
        service: ServiceDep,
        current_user: CurrentUser,
        params: ListParams,
    ) -> APIResponse[Any]:
        del current_user  # the require() in this route's dependencies did the authorization
        rows, total = await service.list(params)
        # `params` is the entity's own params class at runtime -- a subclass, so
        # the paging fields are always the base ones.
        paging = cast(MasterListParams, params)
        page = Page.create(
            [read_schema.model_validate(row) for row in rows],
            page=paging.page,
            page_size=paging.page_size,
            total_items=total,
        )
        return APIResponse.ok(page, message=f"{entity_label_plural.capitalize()} retrieved successfully")

    # ------------------------------------------------------------------
    # Get by id
    # ------------------------------------------------------------------
    @router.get(
        "/{record_id}",
        dependencies=[view],
        response_model=_envelope(read_schema),
        summary=f"Get a {singular}",
        description=(
            f"Returns one {singular} by id. Archived records are returned too, so a "
            "link from the archive list or a stale bookmark resolves rather than 404s."
        ),
        responses={**_COMMON_ERRORS, **_NOT_FOUND},
    )
    async def get_record(
        record_id: RecordId,
        service: ServiceDep,
        current_user: CurrentUser,
    ) -> APIResponse[Any]:
        del current_user
        record = await service.get(record_id)
        return APIResponse.ok(
            read_schema.model_validate(record), message=f"{entity_label} retrieved successfully"
        )

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    @router.post(
        "",
        dependencies=[create],
        response_model=_envelope(read_schema),
        status_code=status.HTTP_201_CREATED,
        summary=f"Create a {singular}",
        description=(
            f"Creates a {singular}. Names and codes are trimmed and compared "
            "case-insensitively, so duplicates are rejected with 409 rather than stored."
        ),
        responses={**_COMMON_ERRORS, **_CONFLICT},
    )
    async def create_record(
        payload: create_schema,  # type: ignore[valid-type]
        service: ServiceDep,
        current_user: CurrentUser,
    ) -> APIResponse[Any]:
        record = await service.create(payload, actor_id=current_user.id)
        return APIResponse.ok(
            read_schema.model_validate(record), message=f"{entity_label} created successfully"
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    @router.patch(
        "/{record_id}",
        dependencies=[update],
        response_model=_envelope(read_schema),
        summary=f"Update a {singular}",
        description=(
            "Partial update; omitted fields are left unchanged. Uniqueness is "
            "evaluated against the resulting record, not the submitted fragment."
        ),
        responses={**_COMMON_ERRORS, **_NOT_FOUND, **_CONFLICT},
    )
    async def update_record(
        record_id: RecordId,
        payload: update_schema,  # type: ignore[valid-type]
        service: ServiceDep,
        current_user: CurrentUser,
    ) -> APIResponse[Any]:
        record = await service.update(record_id, payload, actor_id=current_user.id)
        return APIResponse.ok(
            read_schema.model_validate(record), message=f"{entity_label} updated successfully"
        )

    # ------------------------------------------------------------------
    # Archive
    # ------------------------------------------------------------------
    @router.post(
        "/{record_id}/archive",
        dependencies=[remove],
        response_model=_envelope(read_schema),
        summary=f"Archive a {singular}",
        description=(
            f"Soft deletes the {singular}. Rows that reference it keep working. "
            "Refused with 409 when live records still depend on it."
        ),
        responses={**_COMMON_ERRORS, **_NOT_FOUND, **_CONFLICT},
    )
    async def archive_record(
        record_id: RecordId,
        service: ServiceDep,
        current_user: CurrentUser,
    ) -> APIResponse[Any]:
        record = await service.archive(record_id, actor_id=current_user.id)
        return APIResponse.ok(
            read_schema.model_validate(record), message=f"{entity_label} archived successfully"
        )

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------
    @router.post(
        "/{record_id}/restore",
        dependencies=[remove],
        response_model=_envelope(read_schema),
        summary=f"Restore an archived {singular}",
        description=(
            f"Brings an archived {singular} back into use. Refused with 409 when its "
            "parent is itself archived."
        ),
        responses={**_COMMON_ERRORS, **_NOT_FOUND, **_CONFLICT},
    )
    async def restore_record(
        record_id: RecordId,
        service: ServiceDep,
        current_user: CurrentUser,
    ) -> APIResponse[Any]:
        record = await service.restore(record_id, actor_id=current_user.id)
        return APIResponse.ok(
            read_schema.model_validate(record), message=f"{entity_label} restored successfully"
        )

    return router
