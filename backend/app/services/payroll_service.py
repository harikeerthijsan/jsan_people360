"""Payroll foundation business logic.

Three rules shape this module.

**Salary history is append-only.** A revision never edits the current record:
it closes the period (``effective_to``, status ``ended``) and opens a new one,
and ``salary_history`` records the change itself. There is no method here that
rewrites a past amount, so "never overwrite salary history" is a property of
the design rather than a discipline.

**One active period at a time.** Every write path calls
:meth:`EmployeeCompensationRepository.overlapping` before inserting, and the
partial unique index on ``employee_compensation`` backs the open-ended case up
at the database, where two concurrent requests cannot talk their way past it.

**Nothing is calculated.** The amounts stored are the amounts supplied,
validated for coherence (non-negative, percentage within range, required
components present) and never derived. Deriving net pay from these inputs is a
later phase's job, and pretending otherwise here would produce numbers payroll
would then have to distrust.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.audit_log import AuditAction
from app.models.employee import Employee
from app.models.enums import (
    CompensationStatus,
    RecordStatus,
    SalaryCalculationType,
    SalaryStructureStatus,
)
from app.models.payroll import (
    EmployeeCompensation,
    EmployeeCompensationComponent,
    SalaryComponent,
    SalaryHistory,
    SalaryStructure,
    SalaryStructureComponent,
)
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.payroll_repository import (
    EmployeeCompensationComponentRepository,
    EmployeeCompensationRepository,
    SalaryComponentRepository,
    SalaryHistoryRepository,
    SalaryStructureComponentRepository,
    SalaryStructureRepository,
)
from app.schemas.payroll import (
    CompensationAssign,
    CompensationComponentInput,
    CompensationComponentRead,
    CompensationListParams,
    CompensationListRow,
    CompensationRead,
    EmployeeCompensationData,
    EmployeeSummary,
    SalaryComponentCreate,
    SalaryComponentUpdate,
    SalaryHistoryRead,
    SalaryRevision,
    SalaryStructureCreate,
    SalaryStructureDetail,
    SalaryStructureRead,
    SalaryStructureUpdate,
    StructureComponentInput,
    StructureComponentRead,
    StructureListParams,
)
from app.services.audit_service import AuditService

logger = get_logger("services.payroll")

#: Where a structure may move next. Draft activates; active and inactive
#: toggle. Nothing returns to draft — a structure that has been live is no
#: longer an unpublished idea.
STRUCTURE_TRANSITIONS: dict[str, frozenset[str]] = {
    SalaryStructureStatus.DRAFT.value: frozenset({SalaryStructureStatus.ACTIVE.value}),
    SalaryStructureStatus.ACTIVE.value: frozenset({SalaryStructureStatus.INACTIVE.value}),
    SalaryStructureStatus.INACTIVE.value: frozenset({SalaryStructureStatus.ACTIVE.value}),
}


class PayrollService:
    """Salary structures, components, and employee compensation."""

    def __init__(
        self,
        structures: SalaryStructureRepository,
        components: SalaryComponentRepository,
        structure_components: SalaryStructureComponentRepository,
        compensation: EmployeeCompensationRepository,
        compensation_components: EmployeeCompensationComponentRepository,
        history: SalaryHistoryRepository,
        employees: EmployeeRepository,
        audit: AuditService,
    ) -> None:
        self.structures = structures
        self.components = components
        self.structure_components = structure_components
        self.compensation = compensation
        self.compensation_components = compensation_components
        self.history = history
        self.employees = employees
        self.audit = audit

    # ==================================================================
    # Components
    # ==================================================================
    async def list_components(self, *, include_inactive: bool = False) -> Sequence[SalaryComponent]:
        return await self.components.all_components(include_inactive=include_inactive)

    async def create_component(
        self, payload: SalaryComponentCreate, *, actor_id: uuid.UUID
    ) -> SalaryComponent:
        code = payload.code.strip().upper()
        if await self.components.by_code(code) is not None:
            raise ConflictError(
                f'A component with the code "{code}" already exists.', error_code="duplicate_code"
            )
        component = await self.components.add(
            SalaryComponent(
                name=payload.name.strip(),
                code=code,
                component_type=payload.component_type.value,
                calculation_type=payload.calculation_type.value,
                value=payload.value,
                percentage_basis=payload.percentage_basis.value if payload.percentage_basis else None,
                description=payload.description,
                status=RecordStatus.ACTIVE.value,
            ),
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.SALARY_COMPONENT_CREATED,
            actor_id=actor_id,
            entity_type="salary_component",
            entity_id=component.id,
            description=f"Created salary component {component.name} ({component.code})",
        )
        return component

    async def update_component(
        self, component_id: uuid.UUID, payload: SalaryComponentUpdate, *, actor_id: uuid.UUID
    ) -> SalaryComponent:
        component = await self.components.get(component_id)
        if component is None:
            raise NotFoundError("Salary component")

        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes and changes["name"] is not None:
            changes["name"] = str(changes["name"]).strip()
        for enum_field in ("calculation_type", "percentage_basis"):
            if changes.get(enum_field) is not None:
                changes[enum_field] = changes[enum_field].value

        # Coherence is a property of the final row, not of the fields sent:
        # switching a fixed component to percentage without sending a basis
        # must fail even though neither field is individually wrong.
        final_type = changes.get("calculation_type", component.calculation_type)
        final_value = changes.get("value", component.value)
        final_basis = changes.get("percentage_basis", component.percentage_basis)
        if final_type == SalaryCalculationType.PERCENTAGE.value:
            if final_basis is None:
                raise ValidationError("A percentage component must name the base it applies to")
            if final_value is not None and Decimal(final_value) > 100:
                raise ValidationError("A percentage cannot exceed 100")
        if final_type == SalaryCalculationType.FIXED.value and final_basis is not None:
            # Sending only the type is a request to re-express the component;
            # drop the stale basis rather than refuse the obvious intent.
            changes["percentage_basis"] = None

        await self.components.update(component, changes, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.SALARY_COMPONENT_UPDATED,
            actor_id=actor_id,
            entity_type="salary_component",
            entity_id=component.id,
            description=f"Updated salary component {component.name}",
            context={"fields": sorted(changes)},
        )
        return component

    async def set_component_status(
        self, component_id: uuid.UUID, new_status: RecordStatus, *, actor_id: uuid.UUID
    ) -> SalaryComponent:
        component = await self.components.get(component_id)
        if component is None:
            raise NotFoundError("Salary component")
        previous = component.status
        if previous == new_status.value:
            return component
        await self.components.update(component, {"status": new_status.value}, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.SALARY_COMPONENT_STATUS_CHANGED,
            actor_id=actor_id,
            entity_type="salary_component",
            entity_id=component.id,
            description=f"Salary component {component.name}: {previous} -> {new_status.value}",
            context={"previous": previous, "new": new_status.value},
        )
        return component

    # ==================================================================
    # Structures
    # ==================================================================
    async def list_structures(self, params: StructureListParams) -> tuple[Sequence[SalaryStructure], int]:
        return await self.structures.search(params)

    async def get_structure(self, structure_id: uuid.UUID) -> SalaryStructure:
        structure = await self.structures.get(structure_id)
        if structure is None:
            raise NotFoundError("Salary structure")
        return structure

    async def create_structure(
        self, payload: SalaryStructureCreate, *, actor_id: uuid.UUID
    ) -> SalaryStructure:
        name = payload.name.strip()
        if await self.structures.by_name(name) is not None:
            raise ConflictError(
                f'A salary structure named "{name}" already exists.', error_code="duplicate_name"
            )
        await self._assert_components_usable([item.component_id for item in payload.components])

        structure = await self.structures.add(
            SalaryStructure(
                name=name,
                description=payload.description,
                pay_frequency=payload.pay_frequency.value,
                currency=payload.currency,
                status=SalaryStructureStatus.DRAFT.value,
                effective_from=payload.effective_from,
                effective_to=payload.effective_to,
            ),
            actor_id=actor_id,
        )
        for item in payload.components:
            await self.structure_components.add(
                SalaryStructureComponent(
                    structure_id=structure.id,
                    component_id=item.component_id,
                    default_value=item.default_value,
                ),
                actor_id=actor_id,
            )

        await self.audit.record_success(
            AuditAction.SALARY_STRUCTURE_CREATED,
            actor_id=actor_id,
            entity_type="salary_structure",
            entity_id=structure.id,
            description=f"Created salary structure {structure.name}",
            context={"components": len(payload.components)},
        )
        return await self._reload_structure(structure.id)

    async def update_structure(
        self, structure_id: uuid.UUID, payload: SalaryStructureUpdate, *, actor_id: uuid.UUID
    ) -> SalaryStructure:
        structure = await self.get_structure(structure_id)

        changes = payload.model_dump(exclude_unset=True, exclude={"components"})
        if changes.get("name") is not None:
            name = str(changes["name"]).strip()
            existing = await self.structures.by_name(name)
            if existing is not None and existing.id != structure.id:
                raise ConflictError(
                    f'A salary structure named "{name}" already exists.', error_code="duplicate_name"
                )
            changes["name"] = name
        if changes.get("pay_frequency") is not None:
            changes["pay_frequency"] = changes["pay_frequency"].value
        if changes:
            await self.structures.update(structure, changes, actor_id=actor_id)

        if payload.components is not None:
            await self._replace_structure_components(structure, payload.components, actor_id=actor_id)

        await self.audit.record_success(
            AuditAction.SALARY_STRUCTURE_UPDATED,
            actor_id=actor_id,
            entity_type="salary_structure",
            entity_id=structure.id,
            description=f"Updated salary structure {structure.name}",
            context={"fields": sorted(changes) + (["components"] if payload.components else [])},
        )
        return await self._reload_structure(structure.id)

    async def set_structure_status(
        self, structure_id: uuid.UUID, new_status: SalaryStructureStatus, *, actor_id: uuid.UUID
    ) -> SalaryStructure:
        structure = await self.get_structure(structure_id)
        previous = structure.status
        if previous == new_status.value:
            return structure
        if new_status.value not in STRUCTURE_TRANSITIONS.get(previous, frozenset()):
            raise ConflictError(
                f"A {previous} structure cannot become {new_status.value}.",
                error_code="invalid_status_transition",
            )
        await self.structures.update(structure, {"status": new_status.value}, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.SALARY_STRUCTURE_STATUS_CHANGED,
            actor_id=actor_id,
            entity_type="salary_structure",
            entity_id=structure.id,
            description=f"Salary structure {structure.name}: {previous} -> {new_status.value}",
            context={"previous": previous, "new": new_status.value},
        )
        return await self._reload_structure(structure.id)

    async def _replace_structure_components(
        self,
        structure: SalaryStructure,
        desired: Sequence[StructureComponentInput],
        *,
        actor_id: uuid.UUID,
    ) -> None:
        await self._assert_components_usable([item.component_id for item in desired])
        wanted = {item.component_id: item for item in desired}

        existing = await self.structure_components.list(
            SalaryStructureComponent.structure_id == structure.id,
            include_deleted=True,
            limit=1000,
        )
        seen: set[uuid.UUID] = set()
        for row in existing:
            item = wanted.get(row.component_id)
            if item is None:
                if row.deleted_at is None:
                    await self.structure_components.soft_delete(row, actor_id=actor_id)
                continue
            seen.add(row.component_id)
            if row.deleted_at is not None:
                # Re-adding a pair that once existed: restore rather than
                # insert, because the unique constraint spans deleted rows.
                await self.structure_components.restore(row, actor_id=actor_id)
            await self.structure_components.update(
                row, {"default_value": item.default_value}, actor_id=actor_id
            )
        for component_id, item in wanted.items():
            if component_id in seen:
                continue
            await self.structure_components.add(
                SalaryStructureComponent(
                    structure_id=structure.id,
                    component_id=component_id,
                    default_value=item.default_value,
                ),
                actor_id=actor_id,
            )

    async def _reload_structure(self, structure_id: uuid.UUID) -> SalaryStructure:
        """Re-read with fresh membership, so the response reflects the write."""
        await self.structures.session.flush()
        structure = await self.structures.get(structure_id)
        if structure is None:  # pragma: no cover - just written
            raise NotFoundError("Salary structure")
        await self.structures.session.refresh(structure, ["components"])
        return structure

    # ==================================================================
    # Employee compensation
    # ==================================================================
    async def list_current_compensation(
        self, params: CompensationListParams
    ) -> tuple[list[CompensationListRow], int]:
        rows, total = await self.compensation.search_current(params)
        return [
            CompensationListRow(
                id=row.id,
                employee=EmployeeSummary.model_validate(row.employee),
                structure_name=row.structure.name,
                currency=row.currency,
                annual_ctc=row.annual_ctc,
                monthly_gross=row.monthly_gross,
                status=CompensationStatus(row.status),
                effective_from=row.effective_from,
                effective_to=row.effective_to,
            )
            for row in rows
        ], total

    async def employee_compensation(self, employee_id: uuid.UUID) -> EmployeeCompensationData:
        employee = await self.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("Employee")
        return await self._compensation_data(employee)

    async def my_compensation(self, employee: Employee) -> EmployeeCompensationData:
        return await self._compensation_data(employee)

    async def _compensation_data(self, employee: Employee) -> EmployeeCompensationData:
        records = await self.compensation.for_employee(employee.id)
        presented = [self._present_compensation(record) for record in records]
        current = next((item for item in presented if item.status == CompensationStatus.ACTIVE), None)
        return EmployeeCompensationData(
            employee=EmployeeSummary.model_validate(employee),
            current=current,
            records=presented,
        )

    async def assign_compensation(
        self, employee_id: uuid.UUID, payload: CompensationAssign, *, actor_id: uuid.UUID
    ) -> CompensationRead:
        employee = await self.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("Employee")

        structure = await self._assert_structure_assignable(payload.salary_structure_id)
        await self._assert_compensation_components(structure, payload.components)

        clash = await self.compensation.overlapping(employee.id, payload.effective_from, payload.effective_to)
        if clash is not None:
            raise ConflictError(
                "This employee already has active compensation covering that period. "
                "Revise it instead of assigning a second one.",
                error_code="overlapping_compensation",
            )

        previous_records = await self.compensation.for_employee(employee.id)
        previous = previous_records[0] if previous_records else None

        record = await self._insert_compensation(employee.id, payload, actor_id=actor_id)
        await self._record_history(
            employee_id=employee.id,
            record=record,
            previous=previous,
            reason=payload.reason or "Initial compensation",
            actor_id=actor_id,
        )

        await self.audit.record_success(
            AuditAction.COMPENSATION_ASSIGNED,
            actor_id=actor_id,
            entity_type="employee_compensation",
            entity_id=record.id,
            description=f"Assigned compensation to {employee.full_name}",
            context={
                "employee_id": str(employee.id),
                "annual_ctc": str(record.annual_ctc),
                "currency": record.currency,
                "effective_from": record.effective_from.isoformat(),
            },
        )
        return self._present_compensation(await self._reload_compensation(record.id))

    async def revise_salary(
        self, employee_id: uuid.UUID, payload: SalaryRevision, *, actor_id: uuid.UUID
    ) -> CompensationRead:
        employee = await self.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("Employee")

        current = await self.compensation.current_for_employee(employee.id)
        if current is None:
            raise ConflictError(
                "This employee has no active compensation to revise. Assign one first.",
                error_code="nothing_to_revise",
            )
        if payload.effective_from <= current.effective_from:
            raise ValidationError(
                "The revision must take effect after the current record started "
                f"({current.effective_from.isoformat()})."
            )
        clash = await self.compensation.overlapping(
            employee.id, payload.effective_from, None, exclude_id=current.id
        )
        if clash is not None:
            raise ConflictError(
                "Another active compensation record overlaps that period.",
                error_code="overlapping_compensation",
            )

        structure = await self._assert_structure_assignable(payload.salary_structure_id)
        await self._assert_compensation_components(structure, payload.components)

        # End the current period the day before the new one starts. The row
        # survives untouched otherwise — this is the whole of "end previous",
        # and nothing here rewrites its amounts.
        await self.compensation.update(
            current,
            {
                "effective_to": payload.effective_from - timedelta(days=1),
                "status": CompensationStatus.ENDED.value,
            },
            actor_id=actor_id,
        )

        record = await self._insert_compensation(
            employee.id,
            CompensationAssign(
                salary_structure_id=payload.salary_structure_id,
                currency=payload.currency,
                annual_ctc=payload.annual_ctc,
                annual_gross=payload.annual_gross,
                monthly_gross=payload.monthly_gross,
                basic_salary=payload.basic_salary,
                effective_from=payload.effective_from,
                effective_to=None,
                components=payload.components,
            ),
            actor_id=actor_id,
        )
        await self._record_history(
            employee_id=employee.id,
            record=record,
            previous=current,
            reason=payload.reason,
            actor_id=actor_id,
        )

        await self.audit.record_success(
            AuditAction.SALARY_REVISED,
            actor_id=actor_id,
            entity_type="employee_compensation",
            entity_id=record.id,
            description=f"Revised compensation for {employee.full_name}",
            context={
                "employee_id": str(employee.id),
                "previous_annual_ctc": str(current.annual_ctc),
                "new_annual_ctc": str(record.annual_ctc),
                "effective_from": record.effective_from.isoformat(),
            },
        )
        return self._present_compensation(await self._reload_compensation(record.id))

    async def salary_history(self, employee_id: uuid.UUID) -> list[SalaryHistoryRead]:
        employee = await self.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("Employee")
        return await self._history_for(employee_id)

    async def my_salary_history(self, employee: Employee) -> list[SalaryHistoryRead]:
        return await self._history_for(employee.id)

    async def _history_for(self, employee_id: uuid.UUID) -> list[SalaryHistoryRead]:
        rows = await self.history.for_employee(employee_id)
        return [
            SalaryHistoryRead(
                id=row.id,
                employee_id=row.employee_id,
                previous_annual_ctc=row.previous_annual_ctc,
                new_annual_ctc=row.new_annual_ctc,
                currency=row.currency,
                effective_from=row.effective_from,
                reason=row.reason,
                changed_by_name=(
                    f"{row.changed_by.first_name} {row.changed_by.last_name}".strip()
                    if row.changed_by is not None
                    else None
                ),
                created_at=row.created_at,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Shared checks and presenters
    # ------------------------------------------------------------------
    async def _assert_structure_assignable(self, structure_id: uuid.UUID) -> SalaryStructure:
        structure = await self.structures.get(structure_id)
        if structure is None:
            raise NotFoundError("Salary structure")
        if structure.status != SalaryStructureStatus.ACTIVE.value:
            raise ConflictError(
                "Only an active salary structure can be assigned.",
                error_code="structure_not_active",
            )
        return structure

    async def _assert_components_usable(self, component_ids: Sequence[uuid.UUID]) -> None:
        found = {row.id: row for row in await self.components.by_ids(component_ids)}
        missing = [str(cid) for cid in component_ids if cid not in found]
        if missing:
            raise ValidationError("One or more components do not exist")
        inactive = sorted(row.code for row in found.values() if row.status != RecordStatus.ACTIVE.value)
        if inactive:
            raise ValidationError(f"Inactive component(s) cannot be used: {', '.join(inactive)}")

    async def _assert_compensation_components(
        self,
        structure: SalaryStructure,
        inputs: Sequence[CompensationComponentInput],
    ) -> dict[uuid.UUID, SalaryComponent]:
        """Every structure component present, every input component usable.

        Returns the component masters keyed by id so the caller can snapshot
        calculation type and basis without a second read.
        """
        input_ids = [item.component_id for item in inputs]
        await self._assert_components_usable(input_ids)

        required = await self.structure_components.for_structure(structure.id)
        missing = sorted(row.component.code for row in required if row.component_id not in set(input_ids))
        if missing:
            raise ValidationError(
                f"The structure requires component(s) this assignment does not carry: "
                f"{', '.join(missing)}"
            )

        masters = {row.id: row for row in await self.components.by_ids(input_ids)}
        for item in inputs:
            master = masters[item.component_id]
            if master.calculation_type == SalaryCalculationType.PERCENTAGE.value and item.value > 100:
                raise ValidationError(f"{master.code} is a percentage component; its value cannot exceed 100")
        return masters

    async def _insert_compensation(
        self, employee_id: uuid.UUID, payload: CompensationAssign, *, actor_id: uuid.UUID
    ) -> EmployeeCompensation:
        record = await self.compensation.add(
            EmployeeCompensation(
                employee_id=employee_id,
                salary_structure_id=payload.salary_structure_id,
                currency=payload.currency,
                annual_ctc=payload.annual_ctc,
                annual_gross=payload.annual_gross,
                monthly_gross=payload.monthly_gross,
                basic_salary=payload.basic_salary,
                status=CompensationStatus.ACTIVE.value,
                effective_from=payload.effective_from,
                effective_to=payload.effective_to,
            ),
            actor_id=actor_id,
        )
        wanted_ids = [item.component_id for item in payload.components]
        masters = {row.id: row for row in await self.components.by_ids(wanted_ids)}
        for item in payload.components:
            master = masters[item.component_id]
            await self.compensation_components.add(
                EmployeeCompensationComponent(
                    compensation_id=record.id,
                    component_id=item.component_id,
                    calculation_type=master.calculation_type,
                    value=item.value,
                    percentage_basis=master.percentage_basis,
                ),
                actor_id=actor_id,
            )
        return record

    async def _record_history(
        self,
        *,
        employee_id: uuid.UUID,
        record: EmployeeCompensation,
        previous: EmployeeCompensation | None,
        reason: str | None,
        actor_id: uuid.UUID,
    ) -> None:
        await self.history.add(
            SalaryHistory(
                employee_id=employee_id,
                compensation_id=record.id,
                previous_compensation_id=previous.id if previous is not None else None,
                previous_annual_ctc=previous.annual_ctc if previous is not None else None,
                new_annual_ctc=record.annual_ctc,
                currency=record.currency,
                effective_from=record.effective_from,
                reason=reason,
                changed_by_id=actor_id,
            ),
            actor_id=actor_id,
        )

    async def _reload_compensation(self, compensation_id: uuid.UUID) -> EmployeeCompensation:
        record = await self.compensation.get(compensation_id)
        if record is None:  # pragma: no cover - just written
            raise NotFoundError("Compensation")
        await self.compensation.session.refresh(record, ["components"])
        return record

    def _present_compensation(self, record: EmployeeCompensation) -> CompensationRead:
        return CompensationRead(
            id=record.id,
            employee_id=record.employee_id,
            structure=SalaryStructureRead.model_validate(record.structure),
            currency=record.currency,
            annual_ctc=record.annual_ctc,
            annual_gross=record.annual_gross,
            monthly_gross=record.monthly_gross,
            basic_salary=record.basic_salary,
            status=CompensationStatus(record.status),
            effective_from=record.effective_from,
            effective_to=record.effective_to,
            components=[
                CompensationComponentRead(
                    id=row.id,
                    component_id=row.component_id,
                    name=row.component.name,
                    code=row.component.code,
                    component_type=row.component.component_type,
                    calculation_type=row.calculation_type,
                    value=row.value,
                    percentage_basis=row.percentage_basis,
                )
                for row in record.components
            ],
            created_at=record.created_at,
        )

    def present_structure(self, structure: SalaryStructure) -> SalaryStructureDetail:
        return SalaryStructureDetail(
            **SalaryStructureRead.model_validate(structure).model_dump(),
            components=[
                StructureComponentRead.model_validate(row)
                for row in structure.components
                if row.deleted_at is None
            ],
        )
