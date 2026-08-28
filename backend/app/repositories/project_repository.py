import uuid
from collections.abc import Collection, Sequence
from datetime import date

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.models.project import AllocationHistory, Client, EmployeeAllocation, Project, ProjectMember
from app.repositories.base import BaseRepository
from app.schemas.project import ListParams


class ClientRepository(BaseRepository[Client]):
    model = Client

    async def search(self, params: ListParams) -> tuple[Sequence[Client], int]:
        stmt = self._base_select()
        if params.status:
            stmt = stmt.where(Client.status == params.status)
        if params.search:
            term = f"%{params.search}%"
            stmt = stmt.where(
                or_(
                    Client.client_name.ilike(term),
                    Client.company_name.ilike(term),
                    Client.client_code.ilike(term),
                )
            )
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(Client.created_at.desc()).offset(params.offset).limit(params.page_size)
                )
            )
            .scalars()
            .all()
        )
        return rows, total


class ProjectRepository(BaseRepository[Project]):
    model = Project

    def detailed_query(self) -> Select[tuple[Project]]:
        return self._base_select().options(selectinload(Project.members), selectinload(Project.allocations))

    async def detailed(self, project_id: uuid.UUID) -> Project | None:
        result = await self.session.execute(
            self.detailed_query().where(Project.id == project_id).execution_options(populate_existing=True)
        )
        return result.scalars().unique().one_or_none()

    async def search(self, params: ListParams) -> tuple[Sequence[Project], int]:
        stmt = self.detailed_query()
        if params.status:
            stmt = stmt.where(Project.status == params.status)
        if params.search:
            term = f"%{params.search}%"
            stmt = stmt.where(or_(Project.project_name.ilike(term), Project.project_code.ilike(term)))
        total = int(await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(Project.created_at.desc()).offset(params.offset).limit(params.page_size)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return rows, total


class MemberRepository(BaseRepository[ProjectMember]):
    model = ProjectMember


class AllocationRepository(BaseRepository[EmployeeAllocation]):
    model = EmployeeAllocation

    async def for_employee(self, employee_id: uuid.UUID) -> list[tuple[EmployeeAllocation, ProjectMember]]:
        """One employee's allocations, each paired with the membership that names their role.

        Joined rather than fetched per row: an allocation without its project,
        client and role is not something any screen can display, so the three
        queries a lazy version would issue are three queries every caller pays.
        ``Project`` and ``Client`` arrive eagerly through the model's own
        relationships; only the membership needs saying here.
        """
        stmt = (
            select(EmployeeAllocation, ProjectMember)
            .join(ProjectMember, ProjectMember.id == EmployeeAllocation.member_id)
            .where(
                EmployeeAllocation.employee_id == employee_id,
                EmployeeAllocation.deleted_at.is_(None),
            )
            .order_by(EmployeeAllocation.start_date.desc())
        )
        return [tuple(row) for row in (await self.session.execute(stmt)).unique().all()]

    async def current_for_employees(
        self, employee_ids: Collection[uuid.UUID], on: date
    ) -> list[EmployeeAllocation]:
        """Everyone's allocations that are live on one date, in one query.

        One query rather than one per person: a team screen renders a project
        and a percentage against every row, and doing that per employee is the
        difference between one round trip and twenty.

        "Current" is the allocation *window*, not the ``status`` column. An
        allocation that ended last month is still ``active`` until somebody
        removes it, and showing it as today's project would misreport where the
        team actually is.
        """
        if not employee_ids:
            return []
        stmt = (
            select(EmployeeAllocation)
            .where(
                EmployeeAllocation.employee_id.in_(employee_ids),
                EmployeeAllocation.deleted_at.is_(None),
                EmployeeAllocation.start_date <= on,
                or_(EmployeeAllocation.end_date.is_(None), EmployeeAllocation.end_date >= on),
            )
            .order_by(EmployeeAllocation.allocation_percentage.desc())
        )
        return list((await self.session.execute(stmt)).scalars().unique().all())

    async def employee_ids_on_project(self, project_id: uuid.UUID, on: date) -> set[uuid.UUID]:
        """Who is allocated to a project on a date.

        Used to turn "filter the team by project" into an employee-id narrowing
        *before* the directory query runs, so the filter composes with the team
        scope instead of being applied to rows that were already fetched.
        """
        stmt = select(EmployeeAllocation.employee_id).where(
            EmployeeAllocation.project_id == project_id,
            EmployeeAllocation.deleted_at.is_(None),
            EmployeeAllocation.start_date <= on,
            or_(EmployeeAllocation.end_date.is_(None), EmployeeAllocation.end_date >= on),
        )
        return set((await self.session.execute(stmt)).scalars().all())


class AllocationHistoryRepository(BaseRepository[AllocationHistory]):
    model = AllocationHistory
