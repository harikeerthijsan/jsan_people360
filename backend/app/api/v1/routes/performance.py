"""Performance management endpoints.

Route order matters as elsewhere: every static segment is registered before the
``/{id}`` forms, or ``/dashboard`` would be read as a cycle identifier.

NOTE: no ``from __future__ import annotations`` -- FastAPI reads parameter types
from evaluated annotations, and postponed evaluation breaks ``Annotated[...,
Query()]``.
"""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    CurrentUser,
    PerformanceSvc,
    require,
    require_self_or,
    require_team_scope,
)
from app.models.enums import PerformanceCycleStatus
from app.schemas.common import APIErrorResponse, APIResponse, Page
from app.schemas.performance import (
    AnalyticsRead,
    CycleListParams,
    DashboardRead,
    EmployeePerformanceRead,
    ExportFormat,
    FeedbackCreate,
    FeedbackListParams,
    FeedbackRead,
    FinalReviewRead,
    FinalReviewSubmit,
    GoalCreate,
    GoalListParams,
    GoalProgressCreate,
    GoalRead,
    GoalUpdate,
    ManagerReviewRead,
    ManagerReviewSubmit,
    PerformanceCycleCreate,
    PerformanceCycleRead,
    PerformanceCycleUpdate,
    PerformanceHistoryRead,
    RecognitionCreate,
    RecognitionListParams,
    RecognitionRead,
    ReportName,
    SelfReviewRead,
    SelfReviewSubmit,
)

router = APIRouter(prefix="/performance", tags=["Performance Management"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such record."},
    status.HTTP_409_CONFLICT: {"model": APIErrorResponse, "description": "A workflow rule was violated."},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": APIErrorResponse,
        "description": "Validation failed.",
    },
}


def _labelled(rows: Sequence[tuple[str, int]]) -> list[dict[str, object]]:
    """Turn ``(label, count)`` tuples into the shape the schemas expect."""
    return [{"label": label, "count": count} for label, count in rows]


# ----------------------------------------------------------------------
# Static segments -- must precede /{id}
# ----------------------------------------------------------------------
@router.get(
    "/dashboard",
    dependencies=[require("performance:view")],
    response_model=APIResponse[DashboardRead],
    summary="Performance dashboard",
)
async def dashboard(
    service: PerformanceSvc,
    current_user: CurrentUser,
    cycle_id: Annotated[uuid.UUID | None, Query(description="Defaults to the active cycle.")] = None,
) -> APIResponse[DashboardRead]:
    del current_user
    data = await service.dashboard(cycle_id)
    data["by_goal_status"] = _labelled(data["by_goal_status"])
    data["by_priority"] = _labelled(data["by_priority"])
    return APIResponse.ok(DashboardRead.model_validate(data))


@router.get(
    "/analytics",
    dependencies=[require("performance:view")],
    response_model=APIResponse[AnalyticsRead],
    summary="Performance analytics",
)
async def analytics(
    service: PerformanceSvc,
    current_user: CurrentUser,
    cycle_id: Annotated[uuid.UUID | None, Query()] = None,
) -> APIResponse[AnalyticsRead]:
    del current_user
    data = await service.analytics_overview(cycle_id)
    return APIResponse.ok(AnalyticsRead(**{key: _labelled(rows) for key, rows in data.items()}))


@router.get(
    "/reports/export", dependencies=[require("performance:export")], summary="Export a performance report"
)
async def export_report(
    report: ReportName,
    fmt: ExportFormat,
    service: PerformanceSvc,
    current_user: CurrentUser,
    cycle_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Response:
    del current_user
    content, media_type = await service.export(report, fmt, cycle_id)
    extension = "xlsx" if fmt == "xlsx" else fmt
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{report}.{extension}"'},
    )


# ----------------------------------------------------------------------
# Cycles
# ----------------------------------------------------------------------
@router.get(
    "/cycles",
    dependencies=[require("performance:view")],
    response_model=APIResponse[Page[PerformanceCycleRead]],
    summary="List cycles",
)
async def list_cycles(
    service: PerformanceSvc,
    current_user: CurrentUser,
    params: Annotated[CycleListParams, Query()],
) -> APIResponse[Page[PerformanceCycleRead]]:
    del current_user
    rows, total = await service.list_cycles(params)
    page = Page.create(
        [PerformanceCycleRead.model_validate(row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total_items=total,
    )
    return APIResponse.ok(page, message="Performance cycles retrieved successfully")


@router.post(
    "/cycles",
    dependencies=[require("performance:create")],
    response_model=APIResponse[PerformanceCycleRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a performance cycle",
    responses=_ERRORS,
)
async def create_cycle(
    payload: PerformanceCycleCreate, service: PerformanceSvc, current_user: CurrentUser
) -> APIResponse[PerformanceCycleRead]:
    cycle = await service.create_cycle(payload, actor_id=current_user.id)
    return APIResponse.ok(
        PerformanceCycleRead.model_validate(cycle), message="Performance cycle created successfully"
    )


@router.get(
    "/cycles/{cycle_id}",
    dependencies=[require("performance:view")],
    response_model=APIResponse[PerformanceCycleRead],
    summary="Get a cycle",
    responses=_ERRORS,
)
async def get_cycle(
    cycle_id: uuid.UUID, service: PerformanceSvc, current_user: CurrentUser
) -> APIResponse[PerformanceCycleRead]:
    del current_user
    return APIResponse.ok(PerformanceCycleRead.model_validate(await service.get_cycle(cycle_id)))


@router.patch(
    "/cycles/{cycle_id}",
    dependencies=[require("performance:update")],
    response_model=APIResponse[PerformanceCycleRead],
    summary="Update a cycle",
    responses=_ERRORS,
)
async def update_cycle(
    cycle_id: uuid.UUID,
    payload: PerformanceCycleUpdate,
    service: PerformanceSvc,
    current_user: CurrentUser,
) -> APIResponse[PerformanceCycleRead]:
    cycle = await service.update_cycle(cycle_id, payload, actor_id=current_user.id)
    return APIResponse.ok(
        PerformanceCycleRead.model_validate(cycle), message="Performance cycle updated successfully"
    )


@router.post(
    "/cycles/{cycle_id}/status/{new_status}",
    dependencies=[require("performance:approve")],
    response_model=APIResponse[PerformanceCycleRead],
    summary="Move a cycle through its lifecycle",
    description=(
        "Draft to active opens the cycle for goals and reviews; closing requires every "
        "employee with goals to have a manager review and a final rating."
    ),
    responses=_ERRORS,
)
async def set_cycle_status(
    cycle_id: uuid.UUID,
    new_status: PerformanceCycleStatus,
    service: PerformanceSvc,
    current_user: CurrentUser,
) -> APIResponse[PerformanceCycleRead]:
    cycle = await service.set_cycle_status(cycle_id, new_status, actor_id=current_user.id)
    return APIResponse.ok(
        PerformanceCycleRead.model_validate(cycle), message=f"Cycle moved to {new_status.value}"
    )


# ----------------------------------------------------------------------
# Goals
# ----------------------------------------------------------------------
@router.get(
    "/goals",
    dependencies=[require("performance:view")],
    response_model=APIResponse[Page[GoalRead]],
    summary="List goals",
)
async def list_goals(
    service: PerformanceSvc,
    current_user: CurrentUser,
    params: Annotated[GoalListParams, Query()],
) -> APIResponse[Page[GoalRead]]:
    del current_user
    rows, total = await service.list_goals(params)
    page = Page.create(
        [GoalRead.model_validate(row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total_items=total,
    )
    return APIResponse.ok(page, message="Goals retrieved successfully")


@router.post(
    "/goals",
    dependencies=[require("performance:create")],
    response_model=APIResponse[GoalRead],
    status_code=status.HTTP_201_CREATED,
    summary="Assign a goal",
    description=(
        "Refused when the employee's live goals would pass 100% weightage for the cycle, "
        "when the title repeats one they already hold, or when the dates fall outside the cycle."
    ),
    responses=_ERRORS,
)
async def assign_goal(
    payload: GoalCreate, service: PerformanceSvc, current_user: CurrentUser
) -> APIResponse[GoalRead]:
    goal = await service.assign_goal(payload, actor_id=current_user.id)
    return APIResponse.ok(GoalRead.model_validate(goal), message="Goal assigned successfully")


@router.get(
    "/goals/{goal_id}",
    dependencies=[require("performance:view")],
    response_model=APIResponse[GoalRead],
    summary="Get a goal",
    responses=_ERRORS,
)
async def get_goal(
    goal_id: uuid.UUID, service: PerformanceSvc, current_user: CurrentUser
) -> APIResponse[GoalRead]:
    del current_user
    return APIResponse.ok(GoalRead.model_validate(await service.get_goal(goal_id)))


@router.patch(
    "/goals/{goal_id}",
    dependencies=[require("performance:update")],
    response_model=APIResponse[GoalRead],
    summary="Amend a goal",
    description="Refused once the manager has rated it -- the rating was given against this scope.",
    responses=_ERRORS,
)
async def update_goal(
    goal_id: uuid.UUID, payload: GoalUpdate, service: PerformanceSvc, current_user: CurrentUser
) -> APIResponse[GoalRead]:
    goal = await service.update_goal(goal_id, payload, actor_id=current_user.id)
    return APIResponse.ok(GoalRead.model_validate(goal), message="Goal updated successfully")


@router.post(
    "/goals/{goal_id}/progress",
    dependencies=[require("performance:update")],
    response_model=APIResponse[GoalRead],
    status_code=status.HTTP_201_CREATED,
    summary="Record progress",
    description="Appends a progress report. Earlier reports are never edited or removed.",
    responses=_ERRORS,
)
async def record_progress(
    goal_id: uuid.UUID,
    payload: GoalProgressCreate,
    service: PerformanceSvc,
    current_user: CurrentUser,
) -> APIResponse[GoalRead]:
    goal = await service.record_progress(goal_id, payload, actor_id=current_user.id)
    return APIResponse.ok(GoalRead.model_validate(goal), message="Progress recorded successfully")


# ----------------------------------------------------------------------
# Reviews
# ----------------------------------------------------------------------
@router.get(
    "/reviews/{cycle_id}/{employee_id}",
    # `performance:view` is held by the base Employee role -- it has to be, or
    # nobody could see their own review -- so on its own it guarded nothing
    # here: the id in the URL was the only thing deciding whose review came
    # back. The scope guard is what makes it your own, your team's, or (with
    # `employees:view_all`) anybody's.
    dependencies=[require("performance:view"), require_team_scope()],
    response_model=APIResponse[EmployeePerformanceRead],
    summary="One employee's performance in one cycle",
    responses=_ERRORS,
)
async def employee_performance(
    cycle_id: uuid.UUID, employee_id: uuid.UUID, service: PerformanceSvc, current_user: CurrentUser
) -> APIResponse[EmployeePerformanceRead]:
    del current_user
    data = await service.employee_performance(cycle_id, employee_id)
    return APIResponse.ok(EmployeePerformanceRead.model_validate(data))


@router.post(
    "/reviews/{cycle_id}/{employee_id}/self",
    # A self review is by the employee, so `require_self_or` rather than a plain
    # team scope: your own is always yours, and writing one for somebody else
    # needs an escalating permission *and* the reporting line. Without this,
    # `performance:update` -- which the Employee role holds -- let any employee
    # file a self review under a colleague's name.
    dependencies=[require("performance:update"), require_self_or("performance:approve")],
    response_model=APIResponse[SelfReviewRead],
    status_code=status.HTTP_201_CREATED,
    summary="Submit a self review",
    description="Every live goal must be rated. Submitting is final.",
    responses=_ERRORS,
)
async def submit_self_review(
    cycle_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: SelfReviewSubmit,
    service: PerformanceSvc,
    current_user: CurrentUser,
) -> APIResponse[SelfReviewRead]:
    review = await service.submit_self_review(cycle_id, employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(SelfReviewRead.model_validate(review), message="Self review submitted successfully")


@router.post(
    "/reviews/{cycle_id}/{employee_id}/manager",
    dependencies=[require("performance:create"), require_team_scope()],
    response_model=APIResponse[ManagerReviewRead],
    status_code=status.HTTP_201_CREATED,
    summary="Submit a manager review",
    description="Requires the self review to be in first, so the manager is assessing a stated position.",
    responses=_ERRORS,
)
async def submit_manager_review(
    cycle_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: ManagerReviewSubmit,
    service: PerformanceSvc,
    current_user: CurrentUser,
) -> APIResponse[ManagerReviewRead]:
    review = await service.submit_manager_review(cycle_id, employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(
        ManagerReviewRead.model_validate(review), message="Manager review submitted successfully"
    )


@router.post(
    "/reviews/{cycle_id}/{employee_id}/finalise",
    dependencies=[require("performance:approve"), require_team_scope()],
    response_model=APIResponse[FinalReviewRead],
    status_code=status.HTTP_201_CREATED,
    summary="Finalise performance",
    description="HR's rating of record. Written once; there is no endpoint that edits it.",
    responses=_ERRORS,
)
async def finalise(
    cycle_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: FinalReviewSubmit,
    service: PerformanceSvc,
    current_user: CurrentUser,
) -> APIResponse[FinalReviewRead]:
    review = await service.finalise(cycle_id, employee_id, payload, actor_id=current_user.id)
    return APIResponse.ok(
        FinalReviewRead.model_validate(review), message="Performance finalised successfully"
    )


# ----------------------------------------------------------------------
# Recognition, feedback and history
# ----------------------------------------------------------------------
@router.get(
    "/recognitions",
    dependencies=[require("performance:view")],
    response_model=APIResponse[Page[RecognitionRead]],
    summary="List recognitions",
)
async def list_recognitions(
    service: PerformanceSvc,
    current_user: CurrentUser,
    params: Annotated[RecognitionListParams, Query()],
) -> APIResponse[Page[RecognitionRead]]:
    del current_user
    rows, total = await service.list_recognitions(params)
    page = Page.create(
        [RecognitionRead.model_validate(row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total_items=total,
    )
    return APIResponse.ok(page, message="Recognitions retrieved successfully")


@router.post(
    "/recognitions",
    dependencies=[require("performance:create")],
    response_model=APIResponse[RecognitionRead],
    status_code=status.HTTP_201_CREATED,
    summary="Recognise an employee",
    responses=_ERRORS,
)
async def add_recognition(
    payload: RecognitionCreate, service: PerformanceSvc, current_user: CurrentUser
) -> APIResponse[RecognitionRead]:
    recognition = await service.add_recognition(payload, actor_id=current_user.id)
    return APIResponse.ok(
        RecognitionRead.model_validate(recognition), message="Recognition recorded successfully"
    )


@router.get(
    "/feedback",
    dependencies=[require("performance:view")],
    response_model=APIResponse[Page[FeedbackRead]],
    summary="List feedback",
)
async def list_feedback(
    service: PerformanceSvc,
    current_user: CurrentUser,
    params: Annotated[FeedbackListParams, Query()],
) -> APIResponse[Page[FeedbackRead]]:
    del current_user
    rows, total = await service.list_feedback(params)
    page = Page.create(
        [FeedbackRead.model_validate(row) for row in rows],
        page=params.page,
        page_size=params.page_size,
        total_items=total,
    )
    return APIResponse.ok(page, message="Feedback retrieved successfully")


@router.post(
    "/feedback",
    dependencies=[require("performance:create")],
    response_model=APIResponse[FeedbackRead],
    status_code=status.HTTP_201_CREATED,
    summary="Leave feedback",
    responses=_ERRORS,
)
async def add_feedback(
    payload: FeedbackCreate, service: PerformanceSvc, current_user: CurrentUser
) -> APIResponse[FeedbackRead]:
    feedback = await service.add_feedback(payload, actor_id=current_user.id)
    return APIResponse.ok(FeedbackRead.model_validate(feedback), message="Feedback recorded successfully")


@router.get(
    "/history/{employee_id}",
    dependencies=[require("performance:view"), require_self_or("performance:approve", "performance:export")],
    response_model=APIResponse[list[PerformanceHistoryRead]],
    summary="An employee's performance history",
    description="Append-only. Nothing here is ever edited or removed.",
    responses=_ERRORS,
)
async def performance_history(
    employee_id: uuid.UUID, service: PerformanceSvc, current_user: CurrentUser
) -> APIResponse[list[PerformanceHistoryRead]]:
    del current_user
    rows = await service.history_for(employee_id)
    return APIResponse.ok(
        [PerformanceHistoryRead.model_validate(row) for row in rows],
        message="Performance history retrieved successfully",
    )
