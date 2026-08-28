"""Organization Management routes.

Eight of the nine masters expose exactly the six standard endpoints, so they are
declared here through :func:`build_master_router`. The organization profile adds
one endpoint of its own -- ``GET /organizations/primary`` -- which other modules
use to resolve "the" company without knowing its id.

NOTE: no ``from __future__ import annotations`` here either -- see the note in
``app.api.master_router``.
"""

from fastapi import APIRouter, status

from app.api.deps import (
    CurrentUser,
    OrganizationSvc,
    get_business_unit_service,
    get_designation_service,
    get_employment_type_service,
    get_grade_service,
    get_location_service,
    get_organization_service,
    get_team_service,
)
from app.api.master_router import build_master_router
from app.schemas.business_unit import BusinessUnitCreate, BusinessUnitRead, BusinessUnitUpdate
from app.schemas.common import APIErrorResponse, APIResponse
from app.schemas.designation import (
    DesignationCreate,
    DesignationListParams,
    DesignationRead,
    DesignationUpdate,
)
from app.schemas.employment_type import (
    EmploymentTypeCreate,
    EmploymentTypeRead,
    EmploymentTypeUpdate,
)
from app.schemas.grade import GradeCreate, GradeRead, GradeUpdate
from app.schemas.location import LocationCreate, LocationRead, LocationUpdate
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate
from app.schemas.team import TeamCreate, TeamListParams, TeamRead, TeamUpdate

ORGANIZATION_TAG = "Organization"

# ----------------------------------------------------------------------
# Organization profile -- the standard six, plus one convenience read
# ----------------------------------------------------------------------
organizations_router = build_master_router(
    permission_module="organization",
    prefix="/organizations",
    tag=ORGANIZATION_TAG,
    entity_label="Organization",
    entity_label_plural="Organizations",
    read_schema=OrganizationRead,
    create_schema=OrganizationCreate,
    update_schema=OrganizationUpdate,
    service_dependency=get_organization_service,
)

# A separate router, included *before* the generated one. Starlette matches
# routes in registration order, so if `/organizations/{record_id}` were
# registered first it would capture "primary" and fail to parse it as a UUID.
organization_extras_router = APIRouter(prefix="/organizations", tags=[ORGANIZATION_TAG])


@organization_extras_router.get(
    "/primary",
    response_model=APIResponse[OrganizationRead],
    summary="Get the primary organization",
    description=(
        "Returns the organization other modules should default to: the oldest live, "
        "active profile. Lets a caller resolve the company without hard-coding an id."
    ),
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": APIErrorResponse,
            "description": "No organization profile has been configured.",
        }
    },
)
async def get_primary_organization(
    service: OrganizationSvc,
    current_user: CurrentUser,
) -> APIResponse[OrganizationRead]:
    del current_user
    organization = await service.get_primary()
    return APIResponse.ok(
        OrganizationRead.model_validate(organization),
        message="Organization retrieved successfully",
    )


# ----------------------------------------------------------------------
# Hierarchy masters
# ----------------------------------------------------------------------
business_units_router = build_master_router(
    permission_module="organization",
    prefix="/business-units",
    tag=ORGANIZATION_TAG,
    entity_label="Business unit",
    entity_label_plural="Business units",
    read_schema=BusinessUnitRead,
    create_schema=BusinessUnitCreate,
    update_schema=BusinessUnitUpdate,
    service_dependency=get_business_unit_service,
)

teams_router = build_master_router(
    permission_module="organization",
    prefix="/teams",
    tag=ORGANIZATION_TAG,
    entity_label="Team",
    entity_label_plural="Teams",
    read_schema=TeamRead,
    create_schema=TeamCreate,
    update_schema=TeamUpdate,
    service_dependency=get_team_service,
    params_schema=TeamListParams,
)

designations_router = build_master_router(
    permission_module="organization",
    prefix="/designations",
    tag=ORGANIZATION_TAG,
    entity_label="Designation",
    entity_label_plural="Designations",
    read_schema=DesignationRead,
    create_schema=DesignationCreate,
    update_schema=DesignationUpdate,
    service_dependency=get_designation_service,
    params_schema=DesignationListParams,
)

# ----------------------------------------------------------------------
# Reference masters
# ----------------------------------------------------------------------
locations_router = build_master_router(
    permission_module="organization",
    prefix="/locations",
    tag=ORGANIZATION_TAG,
    entity_label="Location",
    entity_label_plural="Locations",
    read_schema=LocationRead,
    create_schema=LocationCreate,
    update_schema=LocationUpdate,
    service_dependency=get_location_service,
)

employment_types_router = build_master_router(
    permission_module="organization",
    prefix="/employment-types",
    tag=ORGANIZATION_TAG,
    entity_label="Employment type",
    entity_label_plural="Employment types",
    read_schema=EmploymentTypeRead,
    create_schema=EmploymentTypeCreate,
    update_schema=EmploymentTypeUpdate,
    service_dependency=get_employment_type_service,
)

grades_router = build_master_router(
    permission_module="organization",
    prefix="/grades",
    tag=ORGANIZATION_TAG,
    entity_label="Grade",
    entity_label_plural="Grades",
    read_schema=GradeRead,
    create_schema=GradeCreate,
    update_schema=GradeUpdate,
    service_dependency=get_grade_service,
)


# ----------------------------------------------------------------------
# Aggregate
# ----------------------------------------------------------------------
router = APIRouter()

for _master_router in (
    organization_extras_router,
    organizations_router,
    business_units_router,
    teams_router,
    designations_router,
    locations_router,
    employment_types_router,
    grades_router,
):
    router.include_router(_master_router)
