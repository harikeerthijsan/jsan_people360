"""Repositories for the nine organization master-data entities.

Each is a thin declaration on top of :class:`MasterRepository`: the model it
binds to, the columns a free-text search covers, and the columns a client may
sort by. Anything more interesting than that belongs in the service layer.

They live in one module because they form a single feature -- Organization
Management -- and splitting nine ten-line classes across nine files would make
them harder to compare, not easier to find.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.models.business_unit import BusinessUnit
from app.models.designation import Designation
from app.models.employment_type import EmploymentType
from app.models.grade import Grade
from app.models.location import Location
from app.models.organization import Organization
from app.models.team import Team
from app.repositories.master_repository import MasterRepository

#: Sort keys every master supports.
_BASE_SORTABLE = frozenset({"name", "status", "created_at", "updated_at"})
#: Plus the code column, for the masters that have one.
_CODED_SORTABLE = _BASE_SORTABLE | {"code"}


class OrganizationRepository(MasterRepository[Organization]):
    """Legal entities."""

    model = Organization
    searchable_fields = ("name", "legal_name", "registration_number", "city", "description")
    sortable_fields = _BASE_SORTABLE | {"legal_name", "city", "country"}

    async def get_primary(self) -> Organization | None:
        """The organization other modules should default to.

        Most deployments have exactly one. Returning the oldest active record
        gives a deterministic answer for the ones that do not.
        """
        stmt = (
            self._scoped_select(archived=False)
            .where(Organization.status == "active")
            .order_by(Organization.created_at.asc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()


class BusinessUnitRepository(MasterRepository[BusinessUnit]):
    """Top level of the hierarchy."""

    model = BusinessUnit
    searchable_fields = ("name", "code", "description")
    sortable_fields = _CODED_SORTABLE
    has_code = True


class TeamRepository(MasterRepository[Team]):
    """Teams within a business unit. No code column -- see the model."""

    model = Team
    searchable_fields = ("name", "description")
    sortable_fields = _BASE_SORTABLE

    async def count_managed_by(self, user_id: uuid.UUID) -> int:
        """How many live teams a user manages. Used before deactivating them."""
        stmt = (
            select(func.count())
            .select_from(Team)
            .where(Team.manager_id == user_id, Team.deleted_at.is_(None))
        )
        return int((await self.session.execute(stmt)).scalar_one())


class LocationRepository(MasterRepository[Location]):
    """Offices and work sites."""

    model = Location
    searchable_fields = ("name", "code", "city", "state", "country", "address")
    sortable_fields = _CODED_SORTABLE | {"city", "country"}
    has_code = True


class EmploymentTypeRepository(MasterRepository[EmploymentType]):
    """Contractual basis of an engagement."""

    model = EmploymentType
    searchable_fields = ("name", "code", "description")
    sortable_fields = _CODED_SORTABLE
    has_code = True


class DesignationRepository(MasterRepository[Designation]):
    """Job titles within a business unit."""

    model = Designation
    searchable_fields = ("name", "code", "description")
    sortable_fields = _CODED_SORTABLE | {"level"}
    has_code = True

    async def list_for_business_unit(self, business_unit_id: uuid.UUID) -> Sequence[Designation]:
        stmt = (
            self._scoped_select(archived=False)
            .where(Designation.business_unit_id == business_unit_id)
            .order_by(Designation.level.asc(), Designation.name.asc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()


class GradeRepository(MasterRepository[Grade]):
    """Compensation and seniority bands."""

    model = Grade
    searchable_fields = ("name", "code", "description")
    sortable_fields = _CODED_SORTABLE | {"level"}
    has_code = True
