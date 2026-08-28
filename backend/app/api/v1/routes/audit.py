"""The audit trail, readable.

The trail has been written since Phase 1 -- every guard, every custody change,
every export appends to it -- but until now the only way to read it was one
per-employee endpoint guarded by an employees permission. ``audit:view`` and
``audit:export`` sat in the catalogue with nothing behind them, which meant the
roles screen promised administrators a capability the API could not deliver.

Read-only by construction: there is no POST, PATCH or DELETE here and no
service method that could back one. The trail is append-only and the appends
happen where the audited actions happen.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import AuditLogRepo, AuditSvc, CurrentUser, require
from app.models.audit_log import AuditAction
from app.schemas.audit import AuditLogRead
from app.schemas.common import APIErrorResponse, APIResponse, Page, PaginationParams

router = APIRouter(prefix="/audit", tags=["Audit Trail"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": APIErrorResponse, "description": "Not authenticated"},
    403: {"model": APIErrorResponse, "description": "Not permitted"},
}

#: Everything an export may carry. The ``context`` JSON is deliberately not a
#: column: it can hold structured detail whose shape varies by action, and
#: flattening it into a spreadsheet cell invites parsing it back out.
_EXPORT_COLUMNS = (
    "created_at",
    "action",
    "outcome",
    "actor_email",
    "entity_type",
    "entity_id",
    "description",
    "ip_address",
    "request_id",
)


class AuditListParams(PaginationParams):
    actor_id: uuid.UUID | None = None
    action: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None


@router.get(
    "",
    dependencies=[require("audit:view")],
    response_model=APIResponse[Page[AuditLogRead]],
    summary="Search the audit trail",
    description=(
        "Every audited event, most recent first, filterable by actor, action, entity and "
        "time window. The per-employee view under /employees/{id}/audit remains for the "
        "HR profile screen; this is the administrator's view of the whole trail."
    ),
    responses={**_ERRORS},
)
async def search_audit_trail(
    params: Annotated[AuditListParams, Query()],
    repository: AuditLogRepo,
    current_user: CurrentUser,
) -> APIResponse[Page[AuditLogRead]]:
    del current_user
    rows = await repository.search(
        actor_id=params.actor_id,
        action=params.action,
        entity_type=params.entity_type,
        entity_id=params.entity_id,
        since=params.since,
        until=params.until,
        offset=(params.page - 1) * params.page_size,
        limit=params.page_size,
    )
    total = await repository.count_matching(
        actor_id=params.actor_id,
        action=params.action,
        entity_type=params.entity_type,
        entity_id=params.entity_id,
        since=params.since,
        until=params.until,
    )
    return APIResponse.ok(
        Page.create(
            [AuditLogRead.model_validate(row) for row in rows],
            page=params.page,
            page_size=params.page_size,
            total_items=total,
        )
    )


@router.get(
    "/actions",
    dependencies=[require("audit:view")],
    response_model=APIResponse[list[str]],
    summary="Every action the trail can record",
    description="For the filter dropdown, so the screen never guesses at the vocabulary.",
    responses={**_ERRORS},
)
async def list_audit_actions(current_user: CurrentUser) -> APIResponse[list[str]]:
    del current_user
    return APIResponse.ok(sorted(action.value for action in AuditAction))


@router.get(
    "/export",
    dependencies=[require("audit:export")],
    summary="Export the audit trail as CSV",
    description=(
        "The same filters as the search, un-paginated up to a hard cap. Exporting the "
        "trail is itself an audited action -- the trail records who read it out."
    ),
    responses={**_ERRORS},
)
async def export_audit_trail(
    repository: AuditLogRepo,
    audit: AuditSvc,
    current_user: CurrentUser,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    entity_type: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
) -> Response:
    rows = await repository.search(
        actor_id=actor_id, action=action, entity_type=entity_type, since=since, until=until, limit=10_000
    )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(_EXPORT_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.created_at.isoformat(),
                row.action,
                row.outcome,
                row.actor_email or "",
                row.entity_type or "",
                row.entity_id or "",
                row.description or "",
                row.ip_address or "",
                row.request_id or "",
            ]
        )
    await audit.record_success(
        AuditAction.AUDIT_TRAIL_EXPORTED,
        actor_id=current_user.id,
        entity_type="audit_trail",
        entity_id=None,
        description=f"Exported {len(rows)} audit rows",
        context={"action": action, "entity_type": entity_type},
    )
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-trail.csv"'},
    )
