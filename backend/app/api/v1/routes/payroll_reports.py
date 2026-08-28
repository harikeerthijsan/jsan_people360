"""Payroll reports and full & final settlement endpoints (Phase 8).

Reports are organization-wide by nature — every row is somebody's pay — so
every report read pairs its permission with ``employees:view_all``; there is
no team-scoped report. Settlement acts are each their own permission, and the
employee's own settlement lives under ``/me`` with no id to forge.

NOTE: no ``from __future__ import annotations`` — FastAPI reads parameter
types from evaluated annotations.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    CurrentEmployee,
    CurrentUser,
    PayrollReportSvc,
    PayrollSettlementSvc,
    require_org_wide,
)
from app.schemas.common import APIErrorResponse, APIResponse, Page
from app.schemas.payroll_reports import (
    PayrollReport,
    PayrollReportFilters,
    PayrollReportKind,
    ReportExportParams,
)
from app.schemas.payroll_settlement import (
    EligibleExitRow,
    MySettlement,
    SettlementAdjustmentCreate,
    SettlementAdjustmentDecision,
    SettlementApproval,
    SettlementDetail,
    SettlementFinalize,
    SettlementListParams,
    SettlementRead,
    SettlementReopen,
    SettlementUpdate,
)

router = APIRouter(prefix="/payroll", tags=["Payroll Reports & Settlement"])
me_router = APIRouter(prefix="/me", tags=["Employee Self-Service"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Not signed in."},
    status.HTTP_403_FORBIDDEN: {"model": APIErrorResponse, "description": "Missing the permission."},
    status.HTTP_404_NOT_FOUND: {"model": APIErrorResponse, "description": "No such record."},
    status.HTTP_409_CONFLICT: {"model": APIErrorResponse, "description": "A workflow rule was violated."},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": APIErrorResponse, "description": "Validation failed."},
}

ReportFilters = Annotated[PayrollReportFilters, Query()]
ExportParams = Annotated[ReportExportParams, Query()]
SettlementParams = Annotated[SettlementListParams, Query()]


# ======================================================================
# Reports
# ======================================================================
@router.get(
    "/reports/{kind}",
    dependencies=[require_org_wide("payroll:report_view")],
    response_model=APIResponse[PayrollReport],
    summary="A payroll report",
    description="summary, monthly, earnings, deductions, overtime or unpaid_leave — read from "
    "finalized payroll by default. Every row is classified from what the engine recorded.",
    responses={**_ERRORS},
)
async def payroll_report(
    kind: PayrollReportKind, filters: ReportFilters, current_user: CurrentUser, service: PayrollReportSvc
) -> APIResponse[PayrollReport]:
    return APIResponse.ok(await service.report(kind, filters, actor_id=current_user.id))


@router.get(
    "/reports/{kind}/export",
    dependencies=[require_org_wide("payroll:report_export")],
    summary="Export a payroll report",
    responses={**_ERRORS, 200: {"content": {"text/csv": {}}, "description": "The file."}},
)
async def export_payroll_report(
    kind: PayrollReportKind,
    params: ExportParams,
    current_user: CurrentUser,
    service: PayrollReportSvc,
) -> Response:
    content, media_type, filename = await service.export(
        kind, params.filters(), params.format, actor_id=current_user.id
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# ======================================================================
# Full & final settlement
# ======================================================================
@me_router.get(
    "/payroll/settlement",
    response_model=APIResponse[MySettlement],
    summary="My final settlement",
    description="The caller's own settlement, once it has been settled and released. Internal "
    "comments, issues and approvals are not part of it.",
    responses={**_ERRORS},
)
async def my_settlement(
    employee: CurrentEmployee, service: PayrollSettlementSvc
) -> APIResponse[MySettlement]:
    return APIResponse.ok(await service.mine(employee))


@router.get(
    "/final-settlement",
    dependencies=[require_org_wide("payroll:settlement_view")],
    response_model=APIResponse[list[EligibleExitRow]],
    summary="Exiting employees and their settlement status",
    responses={**_ERRORS},
)
async def exiting_employees(
    current_user: CurrentUser, service: PayrollSettlementSvc
) -> APIResponse[list[EligibleExitRow]]:
    del current_user
    return APIResponse.ok(await service.exits())


@router.get(
    "/final-settlement/settlements",
    dependencies=[require_org_wide("payroll:settlement_view")],
    response_model=APIResponse[Page[SettlementRead]],
    summary="Settlements",
    responses={**_ERRORS},
)
async def list_settlements(
    params: SettlementParams, current_user: CurrentUser, service: PayrollSettlementSvc
) -> APIResponse[Page[SettlementRead]]:
    del current_user
    rows, total = await service.list_settlements(params)
    return APIResponse.ok(Page.create(rows, page=params.page, page_size=params.page_size, total_items=total))


@router.post(
    "/final-settlement/cases/{case_id}",
    dependencies=[require_org_wide("payroll:settlement_create")],
    response_model=APIResponse[SettlementDetail],
    status_code=status.HTTP_201_CREATED,
    summary="Open a settlement for an offboarding case",
    description="Refused unless the employee is eligible: the offboarding case is in progress or "
    "completed and a compensation record exists. The settlement is calculated on creation.",
    responses={**_ERRORS},
)
async def create_settlement(
    case_id: uuid.UUID, current_user: CurrentUser, service: PayrollSettlementSvc
) -> APIResponse[SettlementDetail]:
    return APIResponse.ok(
        await service.create(case_id, actor_id=current_user.id), message="Settlement opened"
    )


@router.get(
    "/final-settlement/{settlement_id}",
    dependencies=[require_org_wide("payroll:settlement_view")],
    response_model=APIResponse[SettlementDetail],
    summary="One settlement, in full",
    responses={**_ERRORS},
)
async def get_settlement(
    settlement_id: uuid.UUID, current_user: CurrentUser, service: PayrollSettlementSvc
) -> APIResponse[SettlementDetail]:
    del current_user
    return APIResponse.ok(await service.get(settlement_id))


@router.patch(
    "/final-settlement/{settlement_id}",
    dependencies=[require_org_wide("payroll:settlement_update")],
    response_model=APIResponse[SettlementDetail],
    summary="Update a settlement's notes and exit details",
    responses={**_ERRORS},
)
async def update_settlement(
    settlement_id: uuid.UUID,
    payload: SettlementUpdate,
    current_user: CurrentUser,
    service: PayrollSettlementSvc,
) -> APIResponse[SettlementDetail]:
    return APIResponse.ok(
        await service.update(settlement_id, payload, actor_id=current_user.id), message="Settlement updated"
    )


@router.post(
    "/final-settlement/{settlement_id}/calculate",
    dependencies=[require_org_wide("payroll:settlement_update")],
    response_model=APIResponse[SettlementDetail],
    summary="Recalculate a settlement from current data",
    responses={**_ERRORS},
)
async def calculate_settlement(
    settlement_id: uuid.UUID, current_user: CurrentUser, service: PayrollSettlementSvc
) -> APIResponse[SettlementDetail]:
    return APIResponse.ok(
        await service.calculate(settlement_id, actor_id=current_user.id), message="Settlement recalculated"
    )


@router.post(
    "/final-settlement/{settlement_id}/adjustments",
    dependencies=[require_org_wide("payroll:settlement_update")],
    response_model=APIResponse[SettlementDetail],
    status_code=status.HTTP_201_CREATED,
    summary="Propose a settlement adjustment",
    description="A bonus, incentive, leave encashment, recovery or asset recovery — with a reason. "
    "It counts only once an approver approves it.",
    responses={**_ERRORS},
)
async def add_settlement_adjustment(
    settlement_id: uuid.UUID,
    payload: SettlementAdjustmentCreate,
    current_user: CurrentUser,
    service: PayrollSettlementSvc,
) -> APIResponse[SettlementDetail]:
    return APIResponse.ok(
        await service.add_adjustment(settlement_id, payload, actor_id=current_user.id),
        message="Adjustment proposed",
    )


@router.post(
    "/final-settlement/{settlement_id}/adjustments/{adjustment_id}/decide",
    dependencies=[require_org_wide("payroll:settlement_approve")],
    response_model=APIResponse[SettlementDetail],
    summary="Approve or reject a proposed adjustment",
    responses={**_ERRORS},
)
async def decide_settlement_adjustment(
    settlement_id: uuid.UUID,
    adjustment_id: uuid.UUID,
    payload: SettlementAdjustmentDecision,
    current_user: CurrentUser,
    service: PayrollSettlementSvc,
) -> APIResponse[SettlementDetail]:
    return APIResponse.ok(
        await service.decide_adjustment(settlement_id, adjustment_id, payload, actor_id=current_user.id),
        message="Adjustment decided",
    )


@router.post(
    "/final-settlement/{settlement_id}/submit",
    dependencies=[require_org_wide("payroll:settlement_update")],
    response_model=APIResponse[SettlementDetail],
    summary="Submit a settlement for review",
    responses={**_ERRORS},
)
async def submit_settlement(
    settlement_id: uuid.UUID, current_user: CurrentUser, service: PayrollSettlementSvc
) -> APIResponse[SettlementDetail]:
    return APIResponse.ok(
        await service.submit(settlement_id, actor_id=current_user.id), message="Submitted for review"
    )


@router.post(
    "/final-settlement/{settlement_id}/complete-review",
    dependencies=[require_org_wide("payroll:settlement_update")],
    response_model=APIResponse[SettlementDetail],
    summary="Mark the settlement review complete",
    responses={**_ERRORS},
)
async def complete_settlement_review(
    settlement_id: uuid.UUID, current_user: CurrentUser, service: PayrollSettlementSvc
) -> APIResponse[SettlementDetail]:
    return APIResponse.ok(
        await service.complete_review(settlement_id, actor_id=current_user.id), message="Review completed"
    )


@router.post(
    "/final-settlement/{settlement_id}/approve",
    dependencies=[require_org_wide("payroll:settlement_approve")],
    response_model=APIResponse[SettlementDetail],
    summary="Approve a settlement",
    description="Requires a completed review and no critical issue; both are re-derived at the "
    "moment of the decision.",
    responses={**_ERRORS},
)
async def approve_settlement(
    settlement_id: uuid.UUID,
    payload: SettlementApproval,
    current_user: CurrentUser,
    service: PayrollSettlementSvc,
) -> APIResponse[SettlementDetail]:
    return APIResponse.ok(
        await service.approve(settlement_id, payload, actor_id=current_user.id), message="Settlement approved"
    )


@router.post(
    "/final-settlement/{settlement_id}/reopen",
    dependencies=[require_org_wide("payroll:settlement_approve")],
    response_model=APIResponse[SettlementDetail],
    summary="Reopen an approved settlement for correction",
    responses={**_ERRORS},
)
async def reopen_settlement(
    settlement_id: uuid.UUID,
    payload: SettlementReopen,
    current_user: CurrentUser,
    service: PayrollSettlementSvc,
) -> APIResponse[SettlementDetail]:
    return APIResponse.ok(
        await service.reopen(settlement_id, payload, actor_id=current_user.id), message="Settlement reopened"
    )


@router.post(
    "/final-settlement/{settlement_id}/finalize",
    dependencies=[require_org_wide("payroll:settlement_finalize")],
    response_model=APIResponse[SettlementDetail],
    summary="Settle an approved settlement",
    description="Freezes the settlement, stores its snapshot, releases it to the employee and "
    "marks the offboarding settlement tracker completed.",
    responses={**_ERRORS},
)
async def finalize_settlement(
    settlement_id: uuid.UUID,
    payload: SettlementFinalize,
    current_user: CurrentUser,
    service: PayrollSettlementSvc,
) -> APIResponse[SettlementDetail]:
    return APIResponse.ok(
        await service.finalize(settlement_id, payload, actor_id=current_user.id), message="Settlement settled"
    )


__all__ = ["me_router", "router"]
