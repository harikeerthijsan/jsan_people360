from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from sqlalchemy import func, or_, select

from app.core.exceptions import ConflictError, NotFoundError
from app.models.employee import Employee
from app.models.project import AllocationHistory, Client, EmployeeAllocation, Project, ProjectMember
from app.models.requisition import Notification
from app.repositories.project_repository import (
    AllocationHistoryRepository,
    AllocationRepository,
    ClientRepository,
    MemberRepository,
    ProjectRepository,
)
from app.schemas.project import (
    AllocationChange,
    AllocationCreate,
    AllocationRemove,
    ClientCreate,
    ClientUpdate,
    ListParams,
    ProjectCreate,
    ProjectUpdate,
)
from app.services.audit_service import AuditService


class ProjectService:
    def __init__(
        self,
        clients: ClientRepository,
        projects: ProjectRepository,
        members: MemberRepository,
        allocations: AllocationRepository,
        history: AllocationHistoryRepository,
        audit: AuditService,
    ) -> None:
        self.clients, self.projects, self.members = clients, projects, members
        self.allocations, self.history, self.audit = allocations, history, audit
        self.session = clients.session

    async def list_clients(self, params: ListParams) -> tuple[Sequence[Client], int]:
        return await self.clients.search(params)

    async def get_client(self, client_id: uuid.UUID) -> Client:
        client = await self.clients.get(client_id)
        if not client:
            raise NotFoundError("Client")
        return client

    async def create_client(self, payload: ClientCreate, actor: uuid.UUID) -> Client:
        if await self.clients.find(func.lower(Client.client_name) == payload.client_name.lower()):
            raise ConflictError("Client name already exists.")
        client = await self.clients.add(Client(**payload.model_dump(mode="json")), actor_id=actor)
        await self._audit("client.created", "client", client.id, actor)
        return client

    async def update_client(self, client_id: uuid.UUID, payload: ClientUpdate, actor: uuid.UUID) -> Client:
        client = await self.get_client(client_id)
        values = payload.model_dump(exclude_unset=True, mode="json")
        if "client_name" in values and await self.clients.find(
            func.lower(Client.client_name) == values["client_name"].lower(), Client.id != client.id
        ):
            raise ConflictError("Client name already exists.")
        await self.clients.update(client, values, actor_id=actor)
        await self._audit("client.updated", "client", client.id, actor)
        return client

    async def archive_client(self, client_id: uuid.UUID, actor: uuid.UUID) -> None:
        client = await self.get_client(client_id)
        if any(project.status in {"planned", "active", "on_hold"} for project in client.projects):
            raise ConflictError("A client with open projects cannot be archived.")
        await self.clients.soft_delete(client, actor_id=actor)
        await self._audit("client.archived", "client", client.id, actor)

    async def list_projects(self, params: ListParams) -> tuple[Sequence[Project], int]:
        return await self.projects.search(params)

    async def get_project(self, project_id: uuid.UUID) -> Project:
        project = await self.projects.detailed(project_id)
        if not project:
            raise NotFoundError("Project")
        return project

    async def create_project(self, payload: ProjectCreate, actor: uuid.UUID) -> Project:
        await self._validate_project_refs(
            payload.client_id, payload.project_manager_id, payload.delivery_manager_id
        )
        project = await self.projects.add(Project(**payload.model_dump()), actor_id=actor)
        await self._notify_employee(project.project_manager_id, "Project created", project, actor)
        if project.end_date and project.end_date <= date.today() + timedelta(days=14):
            await self._notify_employee(project.project_manager_id, "Project ending soon", project, actor)
        await self._audit("project.created", "project", project.id, actor)
        return await self.get_project(project.id)

    async def update_project(
        self, project_id: uuid.UUID, payload: ProjectUpdate, actor: uuid.UUID
    ) -> Project:
        project = await self.get_project(project_id)
        values = payload.model_dump(exclude_unset=True)
        start, end = values.get("start_date", project.start_date), values.get("end_date", project.end_date)
        if end and end < start:
            raise ConflictError("Project end date must be on or after start date.")
        old_status = project.status
        await self.projects.update(project, values, actor_id=actor)
        if values.get("status") == "completed" and old_status != "completed":
            for member in project.members:
                await self._notify_employee(member.employee_id, "Project completed", project, actor)
            await self._audit("project.closed", "project", project.id, actor)
        else:
            await self._audit("project.updated", "project", project.id, actor)
        return await self.get_project(project.id)

    async def assign(
        self, project_id: uuid.UUID, payload: AllocationCreate, actor: uuid.UUID
    ) -> EmployeeAllocation:
        project = await self.get_project(project_id)
        await self._validate_employee(payload.employee_id)
        self._within_project(project, payload.start_date, payload.end_date)
        existing_member = await self.members.get_by(project_id=project.id, employee_id=payload.employee_id)
        if existing_member and existing_member.left_at is None:
            raise ConflictError("Employee is already a member of this project.")
        if await self._overlapping_project_allocation(
            payload.employee_id, project.id, payload.start_date, payload.end_date
        ):
            raise ConflictError("Duplicate overlapping allocation for this project.")
        await self._validate_capacity(
            payload.employee_id, payload.start_date, payload.end_date, payload.allocation_percentage
        )
        member = existing_member or await self.members.add(
            ProjectMember(
                project_id=project.id,
                employee_id=payload.employee_id,
                role=payload.role,
                reporting_manager_id=payload.reporting_manager_id,
                joined_at=payload.start_date,
            ),
            actor_id=actor,
        )
        if existing_member:
            await self.members.update(
                member,
                {
                    "role": payload.role,
                    "reporting_manager_id": payload.reporting_manager_id,
                    "joined_at": payload.start_date,
                    "left_at": None,
                },
                actor_id=actor,
            )
        allocation = await self.allocations.add(
            EmployeeAllocation(
                employee_id=payload.employee_id,
                project_id=project.id,
                member_id=member.id,
                allocation_percentage=payload.allocation_percentage,
                start_date=payload.start_date,
                end_date=payload.end_date,
                billable=payload.billable,
                reason=payload.reason,
            ),
            actor_id=actor,
        )
        await self._history(
            payload.employee_id,
            None,
            project.id,
            None,
            payload.allocation_percentage,
            payload.start_date,
            payload.reason,
            "assigned",
            actor,
        )
        await self._notify_employee(payload.employee_id, "Employee assigned", project, actor)
        current_total = await self._current_total(payload.employee_id, payload.start_date)
        if current_total >= 90:
            await self._notify_employee(
                payload.employee_id,
                f"Allocation capacity warning ({current_total}%)",
                project,
                actor,
            )
        await self._audit("allocation.assigned", "allocation", allocation.id, actor)
        return allocation

    async def change(
        self, allocation_id: uuid.UUID, payload: AllocationChange, actor: uuid.UUID
    ) -> EmployeeAllocation:
        old = await self.allocations.get(allocation_id)
        if not old or old.status != "active":
            raise NotFoundError("Active allocation")
        project = await self.get_project(old.project_id)
        self._within_project(project, payload.effective_date, payload.end_date)
        await self._validate_capacity(
            old.employee_id,
            payload.effective_date,
            payload.end_date,
            payload.allocation_percentage,
            exclude_id=old.id,
        )
        close_date = payload.effective_date - timedelta(days=1)
        if close_date < old.start_date:
            raise ConflictError("Change date must be after allocation start date.")
        await self.allocations.update(old, {"end_date": close_date, "status": "superseded"}, actor_id=actor)
        member = await self.members.get(old.member_id)
        if member is None:
            raise NotFoundError("Project member")
        if payload.role or payload.reporting_manager_id is not None:
            await self.members.update(
                member,
                {
                    "role": payload.role or member.role,
                    "reporting_manager_id": (
                        payload.reporting_manager_id
                        if payload.reporting_manager_id is not None
                        else member.reporting_manager_id
                    ),
                },
                actor_id=actor,
            )
        new = await self.allocations.add(
            EmployeeAllocation(
                employee_id=old.employee_id,
                project_id=old.project_id,
                member_id=old.member_id,
                allocation_percentage=payload.allocation_percentage,
                start_date=payload.effective_date,
                end_date=payload.end_date,
                billable=old.billable if payload.billable is None else payload.billable,
                reason=payload.reason,
            ),
            actor_id=actor,
        )
        await self._history(
            old.employee_id,
            old.project_id,
            old.project_id,
            old.allocation_percentage,
            payload.allocation_percentage,
            payload.effective_date,
            payload.reason,
            "changed",
            actor,
        )
        await self._notify_employee(old.employee_id, "Allocation changed", project, actor)
        await self._audit("allocation.changed", "allocation", new.id, actor)
        return new

    async def remove(
        self, allocation_id: uuid.UUID, payload: AllocationRemove, actor: uuid.UUID
    ) -> EmployeeAllocation:
        allocation = await self.allocations.get(allocation_id)
        if not allocation or allocation.status != "active":
            raise NotFoundError("Active allocation")
        if payload.effective_date < allocation.start_date:
            raise ConflictError("Removal date cannot precede allocation start date.")
        await self.allocations.update(
            allocation,
            {"end_date": payload.effective_date, "status": "ended", "reason": payload.reason},
            actor_id=actor,
        )
        member = await self.members.get(allocation.member_id)
        if member is None:
            raise NotFoundError("Project member")
        await self.members.update(member, {"left_at": payload.effective_date}, actor_id=actor)
        await self._history(
            allocation.employee_id,
            allocation.project_id,
            None,
            allocation.allocation_percentage,
            None,
            payload.effective_date,
            payload.reason,
            "removed",
            actor,
        )
        await self._audit("allocation.removed", "allocation", allocation.id, actor)
        return allocation

    async def allocation_history(self, employee_id: uuid.UUID) -> Sequence[AllocationHistory]:
        return await self.history.list(AllocationHistory.employee_id == employee_id, limit=1000)

    async def bench(self) -> list[dict[str, Any]]:
        today = date.today()
        employees = (
            (
                await self.session.execute(
                    select(Employee).where(
                        Employee.deleted_at.is_(None),
                        Employee.employment_status.notin_(["inactive", "resigned"]),
                    )
                )
            )
            .scalars()
            .unique()
            .all()
        )
        result: list[dict[str, Any]] = []
        for employee in employees:
            total = await self._current_total(employee.id, today)
            if total == 0:
                last_end = await self.session.scalar(
                    select(func.max(EmployeeAllocation.end_date)).where(
                        EmployeeAllocation.employee_id == employee.id, EmployeeAllocation.deleted_at.is_(None)
                    )
                )
                result.append(
                    {
                        "employee_id": employee.id,
                        "employee_code": employee.employee_code,
                        "name": employee.full_name,
                        "bench_since": last_end or employee.joining_date,
                        "bench_duration_days": max(0, (today - (last_end or employee.joining_date)).days),
                        "skills": await self._employee_skills(employee.id),
                        "team": employee.team.name if employee.team else None,
                        "manager": (
                            employee.reporting_manager.full_name if employee.reporting_manager else None
                        ),
                    }
                )
        return result

    async def dashboard(self) -> dict[str, Any]:
        today, soon = date.today(), date.today() + timedelta(days=30)
        active_employees = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Employee)
                .where(
                    Employee.deleted_at.is_(None), Employee.employment_status.notin_(["inactive", "resigned"])
                )
            )
            or 0
        )
        allocated = int(
            await self.session.scalar(
                select(func.count(func.distinct(EmployeeAllocation.employee_id))).where(
                    EmployeeAllocation.deleted_at.is_(None),
                    EmployeeAllocation.status == "active",
                    EmployeeAllocation.start_date <= today,
                    or_(EmployeeAllocation.end_date.is_(None), EmployeeAllocation.end_date >= today),
                )
            )
            or 0
        )
        total_pct = Decimal(
            await self.session.scalar(
                select(func.coalesce(func.sum(EmployeeAllocation.allocation_percentage), 0)).where(
                    EmployeeAllocation.deleted_at.is_(None),
                    EmployeeAllocation.status == "active",
                    EmployeeAllocation.start_date <= today,
                    or_(EmployeeAllocation.end_date.is_(None), EmployeeAllocation.end_date >= today),
                )
            )
            or 0
        )
        projects = await self.projects.list(Project.status.in_(["active", "planned"]), limit=10000)
        headcount: list[dict[str, Any]] = []
        for project in projects:
            count = int(
                await self.session.scalar(
                    select(func.count(func.distinct(EmployeeAllocation.employee_id))).where(
                        EmployeeAllocation.project_id == project.id,
                        EmployeeAllocation.status == "active",
                        EmployeeAllocation.start_date <= today,
                        or_(EmployeeAllocation.end_date.is_(None), EmployeeAllocation.end_date >= today),
                    )
                )
                or 0
            )
            headcount.append(
                {"project_id": str(project.id), "project": project.project_name, "headcount": count}
            )
        conflicts = await self.session.scalar(
            select(func.count()).select_from(
                select(EmployeeAllocation.employee_id)
                .where(
                    EmployeeAllocation.status == "active",
                    EmployeeAllocation.start_date <= today,
                    or_(EmployeeAllocation.end_date.is_(None), EmployeeAllocation.end_date >= today),
                )
                .group_by(EmployeeAllocation.employee_id)
                .having(func.sum(EmployeeAllocation.allocation_percentage) > 100)
                .subquery()
            )
        )
        return {
            "total_clients": await self.clients.count(),
            "active_projects": await self.projects.count(Project.status == "active"),
            "completed_projects": await self.projects.count(Project.status == "completed"),
            "employees_allocated": allocated,
            "bench_employees": max(0, active_employees - allocated),
            "allocation_utilization_percent": round(float(total_pct) / (active_employees or 1), 2),
            "projects_ending_soon": await self.projects.count(
                Project.status == "active", Project.end_date.between(today, soon)
            ),
            "allocation_conflicts": int(conflicts or 0),
            "project_headcount": headcount,
        }

    async def project_dashboard(self, project_id: uuid.UUID) -> dict[str, Any]:
        project = await self.get_project(project_id)
        today = date.today()
        current = [
            x
            for x in project.allocations
            if x.status == "active" and x.start_date <= today and (x.end_date is None or x.end_date >= today)
        ]
        total = sum((x.allocation_percentage for x in current), Decimal(0))
        billable = sum((x.allocation_percentage for x in current if x.billable), Decimal(0))
        return {
            "project": project,
            "team_members": current,
            "headcount": len({x.employee_id for x in current}),
            "utilization_percent": round(float(total) / (len({x.employee_id for x in current}) or 1), 2),
            "billable_percent": round(float(billable / total * 100), 2) if total else 0,
            "upcoming_end_dates": [
                x for x in current if x.end_date and x.end_date <= today + timedelta(days=30)
            ],
        }

    async def client_dashboard(self, client_id: uuid.UUID) -> dict[str, Any]:
        client = await self.get_client(client_id)
        active = [p for p in client.projects if p.status == "active"]
        ids = [p.id for p in active]
        employees = (
            int(
                await self.session.scalar(
                    select(func.count(func.distinct(EmployeeAllocation.employee_id))).where(
                        EmployeeAllocation.project_id.in_(ids), EmployeeAllocation.status == "active"
                    )
                )
                or 0
            )
            if ids
            else 0
        )
        billable = (
            int(
                await self.session.scalar(
                    select(func.count(func.distinct(EmployeeAllocation.employee_id))).where(
                        EmployeeAllocation.project_id.in_(ids),
                        EmployeeAllocation.status == "active",
                        EmployeeAllocation.billable.is_(True),
                    )
                )
                or 0
            )
            if ids
            else 0
        )
        return {
            "client": client,
            "active_projects": len(active),
            "total_employees": employees,
            "billable_employees": billable,
            "revenue_available": False,
        }

    async def export(self, report: str, fmt: str) -> tuple[bytes, str]:
        rows: list[list[Any]]
        if report == "clients":
            rows = [["Client ID", "Client", "Company", "Industry", "Status"]] + [
                [x.client_code, x.client_name, x.company_name, x.industry, x.status]
                for x in await self.clients.list(limit=10000)
            ]
        elif report == "projects":
            rows = [["Project ID", "Project", "Client", "Status", "Start", "End"]] + [
                [x.project_code, x.project_name, x.client.client_name, x.status, x.start_date, x.end_date]
                for x in await self.projects.list(limit=10000)
            ]
        elif report == "bench":
            rows = [["Employee ID", "Name", "Bench since", "Days", "Team", "Manager"]] + [
                [
                    x["employee_code"],
                    x["name"],
                    x["bench_since"],
                    x["bench_duration_days"],
                    x["team"],
                    x["manager"],
                ]
                for x in await self.bench()
            ]
        elif report == "utilization":
            today = date.today()
            employees = (
                (
                    await self.session.execute(
                        select(Employee).where(
                            Employee.deleted_at.is_(None),
                            Employee.employment_status.notin_(["inactive", "resigned"]),
                        )
                    )
                )
                .scalars()
                .unique()
                .all()
            )
            rows = [["Employee ID", "Employee", "Current utilization %", "Bench"]]
            for employee in employees:
                utilization = await self._current_total(employee.id, today)
                rows.append([employee.employee_code, employee.full_name, utilization, utilization == 0])
        else:
            allocations = await self.allocations.list(limit=10000)
            rows = [["Employee ID", "Project", "Allocation %", "Start", "End", "Billable", "Status"]] + [
                [
                    x.employee_id,
                    x.project.project_code,
                    x.allocation_percentage,
                    x.start_date,
                    x.end_date,
                    x.billable,
                    x.status,
                ]
                for x in allocations
            ]
        if fmt == "csv":
            text = io.StringIO()
            csv.writer(text).writerows(rows)
            return text.getvalue().encode("utf-8-sig"), "text/csv"
        book = Workbook()
        sheet = book.active
        for row in rows:
            sheet.append(list(row))
        buffer = io.BytesIO()
        book.save(buffer)
        return buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    async def _validate_project_refs(
        self, client_id: uuid.UUID, manager_id: uuid.UUID, delivery_id: uuid.UUID | None
    ) -> None:
        client = await self.clients.get(client_id)
        if not client or client.status != "active":
            raise ConflictError("Project requires an active client.")
        await self._validate_employee(manager_id)
        if delivery_id:
            await self._validate_employee(delivery_id)

    async def _validate_employee(self, employee_id: uuid.UUID) -> None:
        employee = await self.session.get(Employee, employee_id)
        if not employee or employee.deleted_at or employee.employment_status in {"inactive", "resigned"}:
            raise ConflictError("Employee is not available for allocation.")

    def _within_project(self, project: Project, start: date, end: date | None) -> None:
        if start < project.start_date or (project.end_date and (end is None or end > project.end_date)):
            raise ConflictError("Allocation dates must fall within project dates.")
        if end and end < start:
            raise ConflictError("Allocation end date must be on or after start date.")

    async def _validate_capacity(
        self,
        employee_id: uuid.UUID,
        start: date,
        end: date | None,
        percentage: Decimal,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        finish = end or date.max
        criteria = [
            EmployeeAllocation.employee_id == employee_id,
            EmployeeAllocation.status == "active",
            EmployeeAllocation.deleted_at.is_(None),
            EmployeeAllocation.start_date <= finish,
            or_(EmployeeAllocation.end_date.is_(None), EmployeeAllocation.end_date >= start),
        ]
        if exclude_id:
            criteria.append(EmployeeAllocation.id != exclude_id)
        used = Decimal(
            await self.session.scalar(
                select(func.coalesce(func.sum(EmployeeAllocation.allocation_percentage), 0)).where(*criteria)
            )
            or 0
        )
        if used + percentage > 100:
            raise ConflictError(f"Allocation exceeds 100%; {used}% is already allocated in this period.")

    async def _overlapping_project_allocation(
        self, employee_id: uuid.UUID, project_id: uuid.UUID, start: date, end: date | None
    ) -> bool:
        finish = end or date.max
        return bool(
            await self.allocations.find(
                EmployeeAllocation.employee_id == employee_id,
                EmployeeAllocation.project_id == project_id,
                EmployeeAllocation.status == "active",
                EmployeeAllocation.start_date <= finish,
                or_(EmployeeAllocation.end_date.is_(None), EmployeeAllocation.end_date >= start),
            )
        )

    async def _current_total(self, employee_id: uuid.UUID, day: date) -> Decimal:
        return Decimal(
            await self.session.scalar(
                select(func.coalesce(func.sum(EmployeeAllocation.allocation_percentage), 0)).where(
                    EmployeeAllocation.employee_id == employee_id,
                    EmployeeAllocation.status == "active",
                    EmployeeAllocation.start_date <= day,
                    or_(EmployeeAllocation.end_date.is_(None), EmployeeAllocation.end_date >= day),
                )
            )
            or 0
        )

    async def _employee_skills(self, employee_id: uuid.UUID) -> list[str]:
        from app.models.onboarding import PreboardingProfile
        from app.models.recruitment import CandidateSkill

        result = await self.session.execute(
            select(CandidateSkill.name)
            .join(PreboardingProfile, PreboardingProfile.candidate_id == CandidateSkill.candidate_id)
            .where(PreboardingProfile.employee_id == employee_id, CandidateSkill.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def _history(
        self,
        employee: uuid.UUID,
        previous_project: uuid.UUID | None,
        new_project: uuid.UUID | None,
        previous_pct: Decimal | None,
        new_pct: Decimal | None,
        effective: date,
        reason: str | None,
        action: str,
        actor: uuid.UUID,
    ) -> None:
        await self.history.add(
            AllocationHistory(
                employee_id=employee,
                previous_project_id=previous_project,
                new_project_id=new_project,
                previous_allocation_percentage=previous_pct,
                new_allocation_percentage=new_pct,
                effective_date=effective,
                reason=reason,
                action=action,
            ),
            actor_id=actor,
        )

    async def _notify_employee(
        self, employee_id: uuid.UUID | None, title: str, project: Project, actor: uuid.UUID
    ) -> None:
        employee = await self.session.get(Employee, employee_id)
        if employee and employee.user_id:
            self.session.add(
                Notification(
                    user_id=employee.user_id,
                    title=title,
                    message=f"{project.project_code} — {project.project_name}",
                    link=f"/projects/{project.id}",
                    notification_type="project",
                    created_by=actor,
                    updated_by=actor,
                )
            )
            await self.session.flush()

    async def _audit(self, action: str, entity_type: str, entity_id: uuid.UUID, actor: uuid.UUID) -> None:
        await self.audit.record_success(action, actor_id=actor, entity_type=entity_type, entity_id=entity_id)
