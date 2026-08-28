"""Runtime application settings.

The storage half of this module has existed since Phase 1 -- the table, the
repository, the seeded rows, even the ``settings:view``/``settings:update``
permissions -- with no route over any of it. The settings screen showed a
permanent "coming soon" whose stated blocker (RBAC) shipped five phases ago.

Two rules the route layer enforces rather than trusts the client with:

* ``is_editable=False`` rows refuse updates outright. They exist so a value
  the code enforces (the password minimum, for instance) can be *shown* on the
  settings screen without pretending an operator could change it there.
* The key, category, description and flags are not updatable at all -- the
  update schema physically cannot carry them. An operator changes values;
  the platform changes vocabulary.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AppSettingRepo, AuditSvc, CurrentUser, require
from app.core.exceptions import ConflictError, NotFoundError
from app.models.audit_log import AuditAction
from app.schemas.app_setting import AppSettingRead, AppSettingUpdate
from app.schemas.common import APIErrorResponse, APIResponse

router = APIRouter(prefix="/settings", tags=["Settings"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": APIErrorResponse, "description": "Not authenticated"},
    403: {"model": APIErrorResponse, "description": "Not permitted"},
}


@router.get(
    "",
    dependencies=[require("settings:view")],
    response_model=APIResponse[list[AppSettingRead]],
    summary="Runtime settings",
    description="Every setting, grouped by category on the client. Locked rows are shown too — "
    "an operator should see the values the platform enforces, labelled as not theirs to edit.",
    responses={**_ERRORS},
)
async def list_settings(
    repository: AppSettingRepo,
    current_user: CurrentUser,
    category: Annotated[str | None, Query(max_length=100)] = None,
) -> APIResponse[list[AppSettingRead]]:
    del current_user
    rows = (
        await repository.list_by_category(category)
        if category
        else await repository.list(order_by="key", descending=False, limit=500)
    )
    return APIResponse.ok([AppSettingRead.model_validate(row) for row in rows])


@router.patch(
    "/{key}",
    dependencies=[require("settings:update")],
    response_model=APIResponse[AppSettingRead],
    summary="Change a setting's value",
    description="Refused for system-managed settings. The change is audited with both values.",
    responses={
        **_ERRORS,
        404: {"model": APIErrorResponse, "description": "No such setting"},
        409: {"model": APIErrorResponse, "description": "Setting is system-managed"},
    },
)
async def update_setting(
    key: str,
    payload: AppSettingUpdate,
    repository: AppSettingRepo,
    audit: AuditSvc,
    current_user: CurrentUser,
) -> APIResponse[AppSettingRead]:
    setting = await repository.get_by_key(key)
    if setting is None:
        raise NotFoundError("Setting")
    if not setting.is_editable:
        raise ConflictError(
            "This setting is enforced by the platform and cannot be edited here.",
            error_code="setting_locked",
        )

    previous = setting.value
    await repository.update(setting, {"value": payload.value}, actor_id=current_user.id)
    await audit.record_success(
        AuditAction.SETTING_UPDATED,
        actor_id=current_user.id,
        entity_type="app_setting",
        entity_id=setting.id,
        description=f"Setting {setting.key} changed",
        context={"key": setting.key, "from": previous, "to": payload.value},
    )
    return APIResponse.ok(AppSettingRead.model_validate(setting), message="Setting updated")
