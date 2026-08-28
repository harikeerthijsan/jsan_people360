"""Business logic for the nine organization master-data entities.

Each service declares only what is genuinely specific to its entity: which
foreign keys must point at usable records, how far name uniqueness is scoped,
and what must not still depend on a record before it can be archived. Everything
else -- paging, search, duplicate detection, audit, archive/restore -- comes from
:class:`app.services.master_service.MasterService`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import ConflictError, NotFoundError
from app.models.business_unit import BusinessUnit
from app.models.designation import Designation
from app.models.employment_type import EmploymentType
from app.models.grade import Grade
from app.models.location import Location
from app.models.organization import Organization
from app.models.team import Team
from app.repositories.organization_repository import (
    BusinessUnitRepository,
    DesignationRepository,
    EmploymentTypeRepository,
    GradeRepository,
    LocationRepository,
    OrganizationRepository,
    TeamRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas.business_unit import BusinessUnitCreate, BusinessUnitUpdate
from app.schemas.designation import DesignationCreate, DesignationListParams, DesignationUpdate
from app.schemas.employment_type import EmploymentTypeCreate, EmploymentTypeUpdate
from app.schemas.grade import GradeCreate, GradeUpdate
from app.schemas.location import LocationCreate, LocationUpdate
from app.schemas.masters import MasterListParams
from app.schemas.organization import OrganizationCreate, OrganizationUpdate
from app.schemas.team import TeamCreate, TeamListParams, TeamUpdate
from app.services.audit_service import AuditService
from app.services.master_service import MasterService


# ======================================================================
# Organization
# ======================================================================
class OrganizationService(
    MasterService[Organization, OrganizationCreate, OrganizationUpdate, MasterListParams]
):
    entity_label = "Organization"
    entity_label_plural = "organizations"
    entity_type = "organization"
    audit_entity = "organization.profile"

    repository: OrganizationRepository

    def __init__(self, repository: OrganizationRepository, audit_service: AuditService) -> None:
        super().__init__(repository, audit_service)

    async def get_primary(self) -> Organization:
        """The organization other modules default to."""
        organization = await self.repository.get_primary()
        if organization is None:
            raise NotFoundError(
                message="No organization profile has been configured yet.",
            )
        return organization

    async def _assert_unique(self, data: dict[str, Any], *, entity: Organization | None) -> None:
        await super()._assert_unique(data, entity=entity)

        # Registration numbers identify the legal entity, so they are as
        # unique as the name is.
        registration_number = data.get("registration_number")
        if registration_number is None:
            return

        exclude_id = entity.id if entity is not None else None
        clash = await self.repository.find(
            Organization.registration_number == registration_number,
            include_deleted=True,
        )
        if clash is not None and clash.id != exclude_id:
            raise ConflictError(
                f'Registration number "{registration_number}" is already recorded '
                "against another organization.",
                error_code="duplicate_registration_number",
            )


# ======================================================================
# Business unit
# ======================================================================
class BusinessUnitService(
    MasterService[BusinessUnit, BusinessUnitCreate, BusinessUnitUpdate, MasterListParams]
):
    entity_label = "Business unit"
    entity_label_plural = "business units"
    entity_type = "business_unit"
    audit_entity = "organization.business_unit"

    repository: BusinessUnitRepository

    def __init__(self, repository: BusinessUnitRepository, audit_service: AuditService) -> None:
        super().__init__(repository, audit_service)

    async def _assert_can_archive(self, entity: BusinessUnit) -> None:
        live_teams = await self.repository.count_children(Team.business_unit_id == entity.id, Team)
        if live_teams:
            raise self._blocked_by_children(live_teams, "team")

        live_designations = await self.repository.count_children(
            Designation.business_unit_id == entity.id, Designation
        )
        if live_designations:
            raise self._blocked_by_children(live_designations, "designation")


# ======================================================================
# Team
# ======================================================================
class TeamService(MasterService[Team, TeamCreate, TeamUpdate, TeamListParams]):
    entity_label = "Team"
    entity_label_plural = "teams"
    entity_type = "team"
    audit_entity = "organization.team"

    repository: TeamRepository

    def __init__(
        self,
        repository: TeamRepository,
        business_unit_repository: BusinessUnitRepository,
        user_repository: UserRepository,
        audit_service: AuditService,
    ) -> None:
        super().__init__(repository, audit_service)
        self._business_units = business_unit_repository
        self._users = user_repository

    def _name_scope(self, data: dict[str, Any]) -> Sequence[ColumnElement[bool]]:
        business_unit_id = data.get("business_unit_id")
        return () if business_unit_id is None else (Team.business_unit_id == business_unit_id,)

    def _list_criteria(self, params: TeamListParams) -> Sequence[ColumnElement[bool]]:
        criteria: list[ColumnElement[bool]] = []
        if params.business_unit_id is not None:
            criteria.append(Team.business_unit_id == params.business_unit_id)
        if params.manager_id is not None:
            criteria.append(Team.manager_id == params.manager_id)
        return criteria

    async def _validate_references(self, data: dict[str, Any], *, entity: Team | None = None) -> None:
        business_unit_id = data.get("business_unit_id")
        if business_unit_id is not None and not (
            entity is not None and entity.business_unit_id == business_unit_id
        ):
            business_unit = await self._business_units.get(business_unit_id, include_deleted=True)
            if not self._is_usable(business_unit):
                raise ConflictError(
                    "The selected business unit does not exist, is archived, or is inactive.",
                    error_code="invalid_business_unit",
                )

        manager_id = data.get("manager_id")
        if manager_id is not None:
            manager = await self._users.get(manager_id)
            if manager is None or not manager.is_active:
                raise ConflictError(
                    "The selected manager does not exist or is not an active user.",
                    error_code="invalid_manager",
                )

    async def _assert_can_restore(self, entity: Team) -> None:
        parent = await self._business_units.get(entity.business_unit_id, include_deleted=True)
        if parent is None or parent.deleted_at is not None:
            raise ConflictError(
                "The business unit this team belongs to is archived. Restore it first.",
                error_code="parent_archived",
            )


# ======================================================================
# Designation
# ======================================================================
class DesignationService(
    MasterService[Designation, DesignationCreate, DesignationUpdate, DesignationListParams]
):
    entity_label = "Designation"
    entity_label_plural = "designations"
    entity_type = "designation"
    audit_entity = "organization.designation"

    repository: DesignationRepository

    def __init__(
        self,
        repository: DesignationRepository,
        business_unit_repository: BusinessUnitRepository,
        audit_service: AuditService,
    ) -> None:
        super().__init__(repository, audit_service)
        self._business_units = business_unit_repository

    def _name_scope(self, data: dict[str, Any]) -> Sequence[ColumnElement[bool]]:
        business_unit_id = data.get("business_unit_id")
        return () if business_unit_id is None else (Designation.business_unit_id == business_unit_id,)

    def _list_criteria(self, params: DesignationListParams) -> Sequence[ColumnElement[bool]]:
        criteria: list[ColumnElement[bool]] = []
        if params.business_unit_id is not None:
            criteria.append(Designation.business_unit_id == params.business_unit_id)
        if params.level is not None:
            criteria.append(Designation.level == params.level)
        return criteria

    async def _validate_references(self, data: dict[str, Any], *, entity: Designation | None = None) -> None:
        business_unit_id = data.get("business_unit_id")
        if business_unit_id is None:
            return
        if entity is not None and entity.business_unit_id == business_unit_id:
            return

        business_unit = await self._business_units.get(business_unit_id, include_deleted=True)
        if not self._is_usable(business_unit):
            raise ConflictError(
                "The selected business unit does not exist, is archived, or is inactive.",
                error_code="invalid_business_unit",
            )

    async def _assert_can_restore(self, entity: Designation) -> None:
        parent = await self._business_units.get(entity.business_unit_id, include_deleted=True)
        if parent is None or parent.deleted_at is not None:
            raise ConflictError(
                "The business unit this designation belongs to is archived. Restore it first.",
                error_code="parent_archived",
            )


# ======================================================================
# Reference masters -- no parents, no children
# ======================================================================
class LocationService(MasterService[Location, LocationCreate, LocationUpdate, MasterListParams]):
    entity_label = "Location"
    entity_label_plural = "locations"
    entity_type = "location"
    audit_entity = "organization.location"

    def __init__(self, repository: LocationRepository, audit_service: AuditService) -> None:
        super().__init__(repository, audit_service)


class EmploymentTypeService(
    MasterService[EmploymentType, EmploymentTypeCreate, EmploymentTypeUpdate, MasterListParams]
):
    entity_label = "Employment type"
    entity_label_plural = "employment types"
    entity_type = "employment_type"
    audit_entity = "organization.employment_type"

    def __init__(self, repository: EmploymentTypeRepository, audit_service: AuditService) -> None:
        super().__init__(repository, audit_service)


class GradeService(MasterService[Grade, GradeCreate, GradeUpdate, MasterListParams]):
    entity_label = "Grade"
    entity_label_plural = "grades"
    entity_type = "grade"
    audit_entity = "organization.grade"

    def __init__(self, repository: GradeRepository, audit_service: AuditService) -> None:
        super().__init__(repository, audit_service)


__all__ = [
    "BusinessUnitService",
    "DesignationService",
    "EmploymentTypeService",
    "GradeService",
    "LocationService",
    "OrganizationService",
    "TeamService",
]
