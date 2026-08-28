"""Employee business logic.

The rule this module exists to enforce is that **placement history is never
overwritten**. Every path that can change an employee's team, designation,
grade, reporting manager, work location or employment status funnels through
:meth:`EmployeeService._apply_placement_change`, which appends a history row
before the change is visible anywhere. The lifecycle endpoints and the general
update both go through it, so there is no way to move someone quietly.

Everything else here is guards: identifiers that must stay unique, references
that must point at usable master records, reporting lines that must not close a
loop, and archives that must not orphan a team.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.audit_log import AuditAction, AuditLog
from app.models.employee import Employee
from app.models.employee_address import EmployeeAddress
from app.models.employee_bank_detail import EmployeeBankDetail
from app.models.employee_identification import EmployeeIdentification
from app.models.employment_history import EmployeeEmploymentHistory
from app.models.enums import EmploymentChangeType, EmploymentStatus
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_repository import (
    IDENTIFIER_LABELS,
    EmployeeRepository,
    EmploymentHistoryRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas.employee import (
    ChangeDesignationRequest,
    ChangeLocationRequest,
    ChangeManagerRequest,
    ChangeStatusRequest,
    ConfirmEmployeeRequest,
    EmployeeAddressInput,
    EmployeeBankInput,
    EmployeeCreate,
    EmployeeIdentificationInput,
    EmployeeListParams,
    EmployeeUpdate,
    PromoteEmployeeRequest,
    TransferTeamRequest,
)
from app.services.audit_service import AuditService
from app.services.scope_service import EmployeeScope, visible_employee_ids

logger = get_logger("services.employee")

#: The columns whose change must produce a history row. Order matters only for
#: the readability of the composed summary.
TRACKED_PLACEMENT_FIELDS: tuple[tuple[str, str], ...] = (
    ("team_id", "Team"),
    ("designation_id", "Designation"),
    ("grade_id", "Grade"),
    ("reporting_manager_id", "Reporting manager"),
    ("work_location_id", "Work location"),
    ("employment_status", "Status"),
)

#: Which relationship carries the display name for each tracked column, so the
#: summary reads "Engineering to Platform Engineering" rather than two UUIDs.
_LABEL_SOURCE: dict[str, str] = {
    "team_id": "team",
    "designation_id": "designation",
    "grade_id": "grade",
    "reporting_manager_id": "reporting_manager",
    "work_location_id": "work_location",
}

#: Statuses an employee cannot be moved out of by an ordinary status change.
#: Reaching either means the employment ended; returning from one is a rehire,
#: which is a new employment record rather than an edit to the old one.
_TERMINAL_STATUSES: frozenset[EmploymentStatus] = frozenset(
    {EmploymentStatus.RESIGNED, EmploymentStatus.INACTIVE}
)


@dataclass(frozen=True)
class PlacementChange:
    """A requested change to an employee's placement.

    Carries the fields to apply plus the provenance the history row needs. The
    lifecycle methods each build one of these and hand it to a single applier,
    which is what keeps their behaviour identical.
    """

    change_type: EmploymentChangeType
    values: dict[str, Any]
    effective_date: date
    reason: str | None = None
    notes: str | None = None


class EmployeeService:
    """Create and maintain employee records."""

    def __init__(
        self,
        repository: EmployeeRepository,
        history_repository: EmploymentHistoryRepository,
        audit_service: AuditService,
        audit_log_repository: AuditLogRepository,
        user_repository: UserRepository | None = None,
    ) -> None:
        self._employees = repository
        self._history = history_repository
        self._audit = audit_service
        # Reading the trail back is a different job from writing it, and only
        # the profile page needs it -- hence a repository rather than another
        # method on the write-only audit service.
        self._audit_logs = audit_log_repository
        self._users = user_repository

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def list(
        self, params: EmployeeListParams, *, scope: EmployeeScope | None = None
    ) -> tuple[Sequence[Employee], int]:
        """One page of the directory, narrowed to what the caller may see.

        ``scope=None`` means organization-wide, which is the right default for
        the callers that have no reporting line to speak of -- the dashboard
        aggregates, the seeder, a background job.
        """
        self._assert_sortable(params.sort_by)
        self._assert_date_range(params.joined_from, params.joined_to)
        return await self._employees.list_page(params, visible_ids=visible_employee_ids(scope))

    async def list_for_export(
        self, params: EmployeeListParams, *, scope: EmployeeScope | None = None
    ) -> Sequence[Employee]:
        """The export honours the same scope as the screen it was launched from.

        Otherwise the export would be the way around the restriction, which is
        worse than not having applied it: it produces a file.
        """
        self._assert_sortable(params.sort_by)
        self._assert_date_range(params.joined_from, params.joined_to)
        return await self._employees.list_for_export(params, visible_ids=visible_employee_ids(scope))

    async def get_by_id(self, employee_id: uuid.UUID, *, include_archived: bool = True) -> Employee:
        """Fetch one employee, or raise :class:`NotFoundError`.

        Archived employees are readable so a link from the archive list, or a
        stale bookmark, resolves rather than returning a confusing 404.
        """
        employee = await self._employees.get(employee_id, include_deleted=include_archived)
        if employee is None:
            raise NotFoundError("Employee")
        return employee

    async def history(self, employee_id: uuid.UUID) -> Sequence[EmployeeEmploymentHistory]:
        await self.get_by_id(employee_id)
        return await self._history.list_for_employee(employee_id)

    async def audit_trail(self, employee_id: uuid.UUID, *, limit: int = 100) -> Sequence[AuditLog]:
        """Every audited action taken on this employee, most recent first.

        Distinct from the employment history: that records what the employment
        *is*, this records what was *done* to the record and by whom -- including
        the actions that leave no placement trace, such as revealing the bank
        details.
        """
        await self.get_by_id(employee_id)
        return await self._audit_logs.search(entity_type="employee", entity_id=str(employee_id), limit=limit)

    async def reveal_sensitive(
        self, employee_id: uuid.UUID, *, actor_id: uuid.UUID | None = None
    ) -> Employee:
        """Return an employee for the purpose of reading their unmasked details.

        The caller serialises the sensitive schemas from the result. Recording
        the access here rather than in the route is deliberate: the audit entry
        is part of what makes revealing the data acceptable, so it belongs with
        the operation rather than with its transport.
        """
        employee = await self.get_by_id(employee_id)
        await self._audit.record_success(
            AuditAction.EMPLOYEE_SENSITIVE_VIEWED,
            actor_id=actor_id,
            entity_type="employee",
            entity_id=employee.id,
            description=f"Viewed unmasked bank and identity details for {employee.employee_code}",
        )
        logger.info(
            "Sensitive employee details revealed",
            extra={"employee_id": str(employee.id), "employee_code": employee.employee_code},
        )
        return employee

    async def record_export(
        self, action: str, *, actor_id: uuid.UUID | None, row_count: int, export_format: str
    ) -> None:
        """Record that the directory was exported.

        An export takes personal data out of the system, where none of the
        platform's controls apply to it any more. That is worth a trail entry
        even though the file itself contains nothing sensitive.
        """
        await self._audit.record_success(
            action,
            actor_id=actor_id,
            entity_type="employee",
            description=f"Exported {row_count} employee records as {export_format.upper()}",
            context={"row_count": row_count, "format": export_format},
        )
        logger.info("Employee directory exported", extra={"row_count": row_count, "fmt": export_format})

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    async def create(self, payload: EmployeeCreate, *, actor_id: uuid.UUID | None = None) -> Employee:
        """Record a new employee, their satellite rows and their opening history.

        ``employee_code`` is not set here: the database generates it from a
        sequence, which is the only way two concurrent creates cannot be handed
        the same number.
        """
        data = payload.model_dump()
        addresses = data.pop("addresses") or []
        bank = data.pop("bank_detail")
        identification = data.pop("identification")

        await self._assert_official_email_available(data["official_email"], exclude_id=None)
        await self._assert_user_link_available(data.get("user_id"), exclude_id=None)
        await self._assert_org_references_usable(data)
        await self._assert_manager_usable(None, data.get("reporting_manager_id"))
        if identification:
            await self._assert_identifiers_available(identification, exclude_employee_id=None)

        employee = Employee(**data)
        await self._employees.add(employee, actor_id=actor_id)

        for address in addresses:
            self._employees.session.add(
                EmployeeAddress(employee_id=employee.id, created_by=actor_id, updated_by=actor_id, **address)
            )
        if bank:
            self._employees.session.add(
                EmployeeBankDetail(employee_id=employee.id, created_by=actor_id, updated_by=actor_id, **bank)
            )
        if identification:
            self._employees.session.add(
                EmployeeIdentification(
                    employee_id=employee.id, created_by=actor_id, updated_by=actor_id, **identification
                )
            )

        # The session runs with `autoflush=False`, so the satellite rows above
        # are still pending. Flushing here is what puts them in front of the
        # reload's SELECT; without it the response would come back with no
        # addresses, bank details or identifiers.
        await self._employees.session.flush()

        # Reload before composing the opening summary. A freshly constructed
        # entity has `team_id` set but no `team` object, and reading
        # the relationship off it would issue a lazy SELECT -- which under
        # asyncio raises MissingGreenlet rather than loading anything.
        created = await self._reload(employee.id)

        # The opening history row, so the series covers the whole employment
        # rather than starting at the first amendment.
        await self._append_history(
            created,
            change_type=EmploymentChangeType.CREATED,
            effective_date=created.joining_date,
            summary=f"Joined as {self._describe_placement(created)}",
            reason=None,
            notes=None,
            actor_id=actor_id,
        )

        await self._audit.record_success(
            AuditAction.EMPLOYEE_CREATED,
            actor_id=actor_id,
            entity_type="employee",
            entity_id=created.id,
            description=f"Created employee {created.employee_code} ({created.full_name})",
            context={
                "employee_code": created.employee_code,
                "has_bank_detail": bank is not None,
                "has_identification": identification is not None,
                "address_count": len(addresses),
            },
        )
        logger.info(
            "Employee created",
            extra={"employee_id": str(created.id), "employee_code": created.employee_code},
        )
        return created

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    async def update(
        self, employee_id: uuid.UUID, payload: EmployeeUpdate, *, actor_id: uuid.UUID | None = None
    ) -> Employee:
        """Apply a partial update, writing history for any placement change."""
        employee = await self.get_by_id(employee_id)
        self._assert_not_archived(employee)

        changes = payload.model_dump(exclude_unset=True)
        reason = changes.pop("change_reason", None)
        if not changes:
            return employee

        if "official_email" in changes:
            await self._assert_official_email_available(changes["official_email"], exclude_id=employee.id)
        if "user_id" in changes:
            await self._assert_user_link_available(changes["user_id"], exclude_id=employee.id)
        await self._assert_org_references_usable(changes)
        if "reporting_manager_id" in changes:
            await self._assert_manager_usable(employee.id, changes["reporting_manager_id"])

        # Only a tracked field whose value actually *differs* counts as a
        # placement change. Submitting the current team back is a no-op,
        # and recording it would put a row in the history that says nothing
        # happened -- worse than no row, because it reads as though something
        # did.
        placement = {
            field: changes[field]
            for field, _ in TRACKED_PLACEMENT_FIELDS
            if field in changes and changes[field] != getattr(employee, field)
        }

        # Checked against the *filtered* set, not the submitted one. An edit form
        # posts the whole record, so the current status comes back with every
        # save; refusing that as "already confirmed" would make the form
        # unusable. The dedicated status endpoint still rejects a no-op, where
        # asking for a change that is not a change really is a mistake.
        if "employment_status" in placement:
            self._assert_status_transition(employee, EmploymentStatus(placement["employment_status"]))
        tracked = {field for field, _ in TRACKED_PLACEMENT_FIELDS}
        plain = {field: value for field, value in changes.items() if field not in tracked}

        if plain:
            await self._employees.update(employee, plain, actor_id=actor_id)

        if placement:
            await self._apply_placement_change(
                employee,
                PlacementChange(
                    change_type=self._infer_change_type(placement),
                    values=placement,
                    effective_date=date.today(),
                    reason=reason,
                ),
                actor_id=actor_id,
            )

        updated = await self._reload(employee.id)
        await self._audit.record_success(
            AuditAction.EMPLOYEE_UPDATED,
            actor_id=actor_id,
            entity_type="employee",
            entity_id=updated.id,
            description=f"Updated employee {updated.employee_code}",
            context={"fields": sorted(changes)},
        )
        return updated

    # ------------------------------------------------------------------
    # Satellite records
    # ------------------------------------------------------------------
    async def set_address(
        self,
        employee_id: uuid.UUID,
        payload: EmployeeAddressInput,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Employee:
        """Create or replace one of an employee's two addresses."""
        employee = await self.get_by_id(employee_id)
        self._assert_not_archived(employee)

        values = payload.model_dump()
        address_type = values.pop("address_type")
        existing = await self._employees.get_address(employee.id, address_type)

        if existing is None:
            self._employees.session.add(
                EmployeeAddress(
                    employee_id=employee.id,
                    address_type=address_type,
                    created_by=actor_id,
                    updated_by=actor_id,
                    **values,
                )
            )
            await self._employees.session.flush()
        else:
            for field, value in values.items():
                setattr(existing, field, value)
            existing.updated_by = actor_id
            await self._employees.session.flush()

        await self._audit.record_success(
            AuditAction.EMPLOYEE_UPDATED,
            actor_id=actor_id,
            entity_type="employee",
            entity_id=employee.id,
            description=f"Updated the {address_type} address of {employee.employee_code}",
            context={"address_type": address_type},
        )
        return await self._reload(employee.id)

    async def set_bank_detail(
        self, employee_id: uuid.UUID, payload: EmployeeBankInput, *, actor_id: uuid.UUID | None = None
    ) -> Employee:
        """Create or replace an employee's bank details.

        The audit entry records that the details changed and never what they
        changed to -- an audit trail that quotes an account number is a second
        copy of the thing being protected.
        """
        employee = await self.get_by_id(employee_id)
        self._assert_not_archived(employee)

        values = payload.model_dump()
        existing = await self._employees.get_bank_detail(employee.id)

        if existing is None:
            self._employees.session.add(
                EmployeeBankDetail(
                    employee_id=employee.id, created_by=actor_id, updated_by=actor_id, **values
                )
            )
        else:
            for field, value in values.items():
                setattr(existing, field, value)
            existing.updated_by = actor_id
        await self._employees.session.flush()

        await self._audit.record_success(
            AuditAction.EMPLOYEE_BANK_UPDATED,
            actor_id=actor_id,
            entity_type="employee",
            entity_id=employee.id,
            description=f"Updated the bank details of {employee.employee_code}",
            context={"fields": sorted(values)},
        )
        return await self._reload(employee.id)

    async def set_identification(
        self,
        employee_id: uuid.UUID,
        payload: EmployeeIdentificationInput,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Employee:
        """Create or replace an employee's statutory identifiers."""
        employee = await self.get_by_id(employee_id)
        self._assert_not_archived(employee)

        values = payload.model_dump()
        await self._assert_identifiers_available(values, exclude_employee_id=employee.id)

        existing = await self._employees.get_identification(employee.id)
        if existing is None:
            self._employees.session.add(
                EmployeeIdentification(
                    employee_id=employee.id, created_by=actor_id, updated_by=actor_id, **values
                )
            )
        else:
            for field, value in values.items():
                setattr(existing, field, value)
            existing.updated_by = actor_id
        await self._employees.session.flush()

        await self._audit.record_success(
            AuditAction.EMPLOYEE_IDENTIFICATION_UPDATED,
            actor_id=actor_id,
            entity_type="employee",
            entity_id=employee.id,
            # Names the fields that were set, never their values.
            description=f"Updated the government identifiers of {employee.employee_code}",
            context={"fields": sorted(field for field, value in values.items() if value is not None)},
        )
        return await self._reload(employee.id)

    # ------------------------------------------------------------------
    # Lifecycle actions
    # ------------------------------------------------------------------
    async def confirm(
        self, employee_id: uuid.UUID, payload: ConfirmEmployeeRequest, *, actor_id: uuid.UUID | None = None
    ) -> Employee:
        """Confirm an employee at the end of probation."""
        employee = await self.get_by_id(employee_id)
        self._assert_not_archived(employee)

        if employee.employment_status != EmploymentStatus.PROBATION:
            raise ConflictError(
                "Only an employee on probation can be confirmed. "
                f"{employee.full_name} is currently {self._status_label(employee.employment_status)}.",
                error_code="not_on_probation",
            )

        return await self._apply_placement_change(
            employee,
            PlacementChange(
                change_type=EmploymentChangeType.CONFIRMATION,
                values={
                    "employment_status": EmploymentStatus.CONFIRMED.value,
                    "confirmation_date": payload.effective_date,
                },
                effective_date=payload.effective_date,
                reason=payload.reason,
                notes=payload.notes,
            ),
            actor_id=actor_id,
            audit_action=AuditAction.EMPLOYEE_CONFIRMED,
        )

    async def transfer_team(
        self,
        employee_id: uuid.UUID,
        payload: TransferTeamRequest,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Employee:
        """Move an employee to another team.

        The business unit follows when one is supplied: a team belongs to a
        business unit, so a move across units has to carry both.
        """
        employee = await self.get_by_id(employee_id)
        self._assert_not_archived(employee)

        values: dict[str, Any] = {"team_id": payload.team_id}
        if payload.business_unit_id is not None:
            values["business_unit_id"] = payload.business_unit_id

        await self._assert_org_references_usable(values)
        if employee.team_id == payload.team_id:
            raise ConflictError(
                f"{employee.full_name} is already in that team.",
                error_code="already_in_team",
            )

        return await self._apply_placement_change(
            employee,
            PlacementChange(
                change_type=EmploymentChangeType.TEAM_TRANSFER,
                values=values,
                effective_date=payload.effective_date,
                reason=payload.reason,
                notes=payload.notes,
            ),
            actor_id=actor_id,
            audit_action=AuditAction.EMPLOYEE_TRANSFERRED,
        )

    async def change_designation(
        self,
        employee_id: uuid.UUID,
        payload: ChangeDesignationRequest,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Employee:
        employee = await self.get_by_id(employee_id)
        self._assert_not_archived(employee)

        values: dict[str, Any] = {"designation_id": payload.designation_id}
        if payload.grade_id is not None:
            values["grade_id"] = payload.grade_id
        await self._assert_org_references_usable(values)

        if employee.designation_id == payload.designation_id and payload.grade_id is None:
            raise ConflictError(
                f"{employee.full_name} already holds that designation.",
                error_code="already_has_designation",
            )

        return await self._apply_placement_change(
            employee,
            PlacementChange(
                change_type=EmploymentChangeType.DESIGNATION_CHANGE,
                values=values,
                effective_date=payload.effective_date,
                reason=payload.reason,
                notes=payload.notes,
            ),
            actor_id=actor_id,
            audit_action=AuditAction.EMPLOYEE_DESIGNATION_CHANGED,
        )

    async def change_manager(
        self, employee_id: uuid.UUID, payload: ChangeManagerRequest, *, actor_id: uuid.UUID | None = None
    ) -> Employee:
        employee = await self.get_by_id(employee_id)
        self._assert_not_archived(employee)

        await self._assert_manager_usable(employee.id, payload.reporting_manager_id)
        if employee.reporting_manager_id == payload.reporting_manager_id:
            raise ConflictError(
                f"{employee.full_name} already reports to that manager.",
                error_code="already_reports_to",
            )

        return await self._apply_placement_change(
            employee,
            PlacementChange(
                change_type=EmploymentChangeType.MANAGER_CHANGE,
                values={"reporting_manager_id": payload.reporting_manager_id},
                effective_date=payload.effective_date,
                reason=payload.reason,
                notes=payload.notes,
            ),
            actor_id=actor_id,
            audit_action=AuditAction.EMPLOYEE_MANAGER_CHANGED,
        )

    async def change_location(
        self, employee_id: uuid.UUID, payload: ChangeLocationRequest, *, actor_id: uuid.UUID | None = None
    ) -> Employee:
        employee = await self.get_by_id(employee_id)
        self._assert_not_archived(employee)

        values: dict[str, Any] = {"work_location_id": payload.work_location_id}
        if payload.work_mode is not None:
            values["work_mode"] = payload.work_mode.value
        await self._assert_org_references_usable(values)

        return await self._apply_placement_change(
            employee,
            PlacementChange(
                change_type=EmploymentChangeType.LOCATION_CHANGE,
                values=values,
                effective_date=payload.effective_date,
                reason=payload.reason,
                notes=payload.notes,
            ),
            actor_id=actor_id,
            audit_action=AuditAction.EMPLOYEE_LOCATION_CHANGED,
        )

    async def promote(
        self, employee_id: uuid.UUID, payload: PromoteEmployeeRequest, *, actor_id: uuid.UUID | None = None
    ) -> Employee:
        """Promote an employee: designation, grade, pay band, salary, or several.

        Recorded as a promotion rather than as the individual changes, because
        "promoted on this date" is the fact anyone reading the history later
        wants, and it cannot be reconstructed from a designation change alone.
        """
        employee = await self.get_by_id(employee_id)
        self._assert_not_archived(employee)

        values: dict[str, Any] = {}
        for field in ("designation_id", "grade_id", "salary_grade_id"):
            value = getattr(payload, field)
            if value is not None:
                values[field] = value
        if payload.ctc is not None:
            values["ctc"] = payload.ctc

        await self._assert_org_references_usable(values)

        return await self._apply_placement_change(
            employee,
            PlacementChange(
                change_type=EmploymentChangeType.PROMOTION,
                values=values,
                effective_date=payload.effective_date,
                reason=payload.reason,
                notes=payload.notes,
            ),
            actor_id=actor_id,
            audit_action=AuditAction.EMPLOYEE_PROMOTED,
        )

    async def change_status(
        self, employee_id: uuid.UUID, payload: ChangeStatusRequest, *, actor_id: uuid.UUID | None = None
    ) -> Employee:
        employee = await self.get_by_id(employee_id)
        self._assert_not_archived(employee)
        self._assert_status_transition(employee, payload.employment_status)

        return await self._apply_placement_change(
            employee,
            PlacementChange(
                change_type=EmploymentChangeType.STATUS_CHANGE,
                values={"employment_status": payload.employment_status.value},
                effective_date=payload.effective_date,
                reason=payload.reason,
                notes=payload.notes,
            ),
            actor_id=actor_id,
            audit_action=AuditAction.EMPLOYEE_STATUS_CHANGED,
        )

    async def set_active(
        self, employee_id: uuid.UUID, *, active: bool, actor_id: uuid.UUID | None = None
    ) -> Employee:
        """The Activate and Deactivate shortcuts.

        Thin wrappers over a status change so they cannot behave differently from
        it -- they write the same history row and honour the same guards.
        """
        target = EmploymentStatus.ACTIVE if active else EmploymentStatus.INACTIVE
        return await self.change_status(
            employee_id,
            ChangeStatusRequest(employment_status=target),
            actor_id=actor_id,
        )

    # ------------------------------------------------------------------
    # Archive and restore
    # ------------------------------------------------------------------
    async def archive(self, employee_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> Employee:
        """Soft delete an employee, after checking nothing still depends on them."""
        employee = await self.get_by_id(employee_id)

        if employee.deleted_at is not None:
            raise ConflictError("This employee is already archived.", error_code="already_archived")

        reports = await self._employees.count_direct_reports(employee.id)
        if reports:
            subject = "1 employee still reports" if reports == 1 else f"{reports} employees still report"
            raise ConflictError(
                f"{subject} to {employee.full_name}. "
                f"Reassign {'that person' if reports == 1 else 'them'} before archiving this record.",
                error_code="has_direct_reports",
            )

        await self._employees.soft_delete(employee, actor_id=actor_id)
        await self._audit.record_success(
            AuditAction.EMPLOYEE_ARCHIVED,
            actor_id=actor_id,
            entity_type="employee",
            entity_id=employee.id,
            description=f"Archived employee {employee.employee_code} ({employee.full_name})",
        )
        logger.info("Employee archived", extra={"employee_id": str(employee.id)})
        return await self._reload(employee.id)

    async def restore(self, employee_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> Employee:
        """Bring an archived employee back into use."""
        employee = await self.get_by_id(employee_id)

        if employee.deleted_at is None:
            raise ConflictError("This employee is not archived.", error_code="not_archived")

        # The work address and any statutory identifiers stayed reserved while
        # archived, but another record could have taken them in the meantime.
        await self._assert_official_email_available(employee.official_email, exclude_id=employee.id)

        await self._employees.restore(employee, actor_id=actor_id)
        await self._audit.record_success(
            AuditAction.EMPLOYEE_RESTORED,
            actor_id=actor_id,
            entity_type="employee",
            entity_id=employee.id,
            description=f"Restored employee {employee.employee_code} ({employee.full_name})",
        )
        return await self._reload(employee.id)

    # ------------------------------------------------------------------
    # The single path through which placement changes
    # ------------------------------------------------------------------
    async def _apply_placement_change(
        self,
        employee: Employee,
        change: PlacementChange,
        *,
        actor_id: uuid.UUID | None,
        audit_action: str | None = None,
    ) -> Employee:
        """Apply the change and append the history row describing it.

        The labels are read twice -- once before the write and once after the
        reload -- because a summary has to name both sides of the change, and the
        incoming payload carries ids rather than names. Reading the "after" side
        off the reloaded employee is what turns
        ``team_id=7b2e...`` into ``Platform to Delivery``.

        Both writes are in the request's single transaction, so either the change
        and its history both land or neither does.
        """
        before = self._snapshot_labels(employee)

        await self._employees.update(employee, change.values, actor_id=actor_id)
        refreshed = await self._reload(employee.id)

        after = self._snapshot_labels(refreshed)
        summary = self._compose_summary(before, after, change.values)

        await self._append_history(
            refreshed,
            change_type=change.change_type,
            effective_date=change.effective_date,
            summary=summary,
            reason=change.reason,
            notes=change.notes,
            actor_id=actor_id,
        )

        if audit_action is not None:
            await self._audit.record_success(
                audit_action,
                actor_id=actor_id,
                entity_type="employee",
                entity_id=refreshed.id,
                description=f"{summary} for {refreshed.employee_code}",
                context={
                    "change_type": change.change_type.value,
                    "effective_date": change.effective_date.isoformat(),
                    "fields": sorted(change.values),
                },
            )

        return refreshed

    async def _append_history(
        self,
        employee: Employee,
        *,
        change_type: EmploymentChangeType,
        effective_date: date,
        summary: str,
        reason: str | None,
        notes: str | None,
        actor_id: uuid.UUID | None,
    ) -> None:
        """Write one history row capturing the employee's state right now."""
        row = EmployeeEmploymentHistory(
            employee_id=employee.id,
            change_type=change_type.value,
            effective_date=effective_date,
            team_id=employee.team_id,
            designation_id=employee.designation_id,
            grade_id=employee.grade_id,
            work_location_id=employee.work_location_id,
            reporting_manager_id=employee.reporting_manager_id,
            employment_status=employee.employment_status,
            summary=summary,
            reason=reason,
            notes=notes,
            created_by=actor_id,
            updated_by=actor_id,
        )
        await self._history.add(row, actor_id=actor_id)

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------
    def _snapshot_labels(self, employee: Employee) -> dict[str, str]:
        """The human-readable value of every field a summary can mention."""
        labels: dict[str, str] = {
            "employment_status": self._status_label(employee.employment_status),
            # Not a tracked field -- changing it alone writes no history row --
            # but it rides along on a location change and the summary should
            # say so rather than fall back to the generic wording.
            "work_mode": employee.work_mode or "not set",
        }

        for field, source in _LABEL_SOURCE.items():
            related = getattr(employee, source, None)
            if related is None:
                labels[field] = "not set"
            else:
                name = getattr(related, "full_name", None) or getattr(related, "name", None)
                labels[field] = str(name) if name else "not set"

        return labels

    @staticmethod
    def _compose_summary(before: dict[str, str], after: dict[str, str], values: dict[str, Any]) -> str:
        """Describe a change in terms of the names involved, not the ids.

        Frozen into the history row at write time, so the timeline still reads
        correctly after one of the master records is renamed.
        """
        parts: list[str] = []

        for field, label in TRACKED_PLACEMENT_FIELDS:
            if field not in values:
                continue
            was, now = before.get(field, "not set"), after.get(field, "not set")
            if was == now:
                continue
            parts.append(f"{label}: {was} to {now}")

        if "work_mode" in values and before.get("work_mode") != after.get("work_mode"):
            parts.append(f"Work mode: {before.get('work_mode')} to {after.get('work_mode')}")

        # Amounts are named but never quoted: the history is read by more people
        # than are entitled to see someone's salary.
        if "ctc" in values:
            parts.append("CTC revised")
        if "salary_grade_id" in values:
            parts.append("Salary grade revised")
        if "confirmation_date" in values and "employment_status" not in values:
            parts.append("Confirmed")

        return "; ".join(parts) if parts else "Employment details updated"

    @staticmethod
    def _status_label(status: str) -> str:
        return status.replace("_", " ")

    @staticmethod
    def _describe_placement(employee: Employee) -> str:
        """A one-line description of where someone sits, for the opening history row."""
        designation = employee.designation.name if employee.designation else None
        team = employee.team.name if employee.team else None

        if designation and team:
            return f"{designation} in {team}"
        return designation or team or "an employee"

    @staticmethod
    def _infer_change_type(placement: dict[str, Any]) -> EmploymentChangeType:
        """Pick the most specific change type a general update corresponds to.

        A single tracked field maps to its own type; several at once are recorded
        as a details update, because claiming one of them was "the" change would
        be a guess.
        """
        if len(placement) != 1:
            return EmploymentChangeType.DETAILS_UPDATED

        field = next(iter(placement))
        return {
            "team_id": EmploymentChangeType.TEAM_TRANSFER,
            "designation_id": EmploymentChangeType.DESIGNATION_CHANGE,
            "grade_id": EmploymentChangeType.GRADE_CHANGE,
            "reporting_manager_id": EmploymentChangeType.MANAGER_CHANGE,
            "work_location_id": EmploymentChangeType.LOCATION_CHANGE,
            "employment_status": EmploymentChangeType.STATUS_CHANGE,
        }[field]

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------
    def _assert_sortable(self, sort_by: str) -> None:
        if sort_by not in self._employees.sortable_fields:
            allowed = ", ".join(sorted(self._employees.sortable_fields))
            raise BadRequestError(
                f"Cannot sort by {sort_by!r}. Sortable columns are: {allowed}.",
                error_code="invalid_sort_field",
            )

    @staticmethod
    def _assert_date_range(start: date | None, end: date | None) -> None:
        if start is not None and end is not None and start > end:
            raise BadRequestError(
                "The start of the joining-date range is after its end.",
                error_code="invalid_date_range",
            )

    @staticmethod
    def _assert_not_archived(employee: Employee) -> None:
        if employee.deleted_at is not None:
            raise ConflictError(
                "This employee is archived. Restore the record before making changes.",
                error_code="record_archived",
            )

    async def _assert_official_email_available(self, email: str, *, exclude_id: uuid.UUID | None) -> None:
        clash = await self._employees.find_official_email_owner(email, exclude_id=exclude_id)
        if clash is None:
            return

        if clash.deleted_at is not None:
            raise ConflictError(
                f'The official email "{email}" belongs to an archived employee '
                f"({clash.employee_code}). Restore that record instead of creating a "
                "duplicate, or use a different address.",
                error_code="duplicate_official_email",
            )
        raise ConflictError(
            f'The official email "{email}" is already in use by {clash.employee_code}.',
            error_code="duplicate_official_email",
        )

    async def _assert_user_link_available(
        self, user_id: uuid.UUID | None, *, exclude_id: uuid.UUID | None
    ) -> None:
        """One login account belongs to at most one employee."""
        if user_id is None:
            return

        if self._users is not None and await self._users.get(user_id, include_deleted=True) is None:
            raise ConflictError(
                "The selected user account does not exist.",
                error_code="invalid_user_reference",
            )

        clash = await self._employees.find_by_user_id(user_id, exclude_id=exclude_id)
        if clash is not None:
            raise ConflictError(
                f"That user account is already linked to {clash.employee_code} ({clash.full_name}).",
                error_code="user_already_linked",
            )

    async def _assert_org_references_usable(self, data: dict[str, Any]) -> None:
        invalid = await self._employees.find_unusable_org_references(data)
        if not invalid:
            return

        names = ", ".join(invalid)
        raise ConflictError(
            (
                f"The selected {names} does not exist, is archived, or is inactive."
                if len(invalid) == 1
                else f"These selections do not exist, are archived, or are inactive: {names}."
            ),
            error_code="invalid_organization_reference",
        )

    async def _assert_manager_usable(
        self, employee_id: uuid.UUID | None, manager_id: uuid.UUID | None
    ) -> None:
        """A manager must exist, be employed, and not be below the employee."""
        if manager_id is None:
            return

        if employee_id is not None and manager_id == employee_id:
            raise ConflictError(
                "An employee cannot report to themselves.",
                error_code="manager_is_self",
            )

        manager = await self._employees.get(manager_id, include_deleted=True)
        if manager is None:
            raise ConflictError(
                "The selected reporting manager does not exist.",
                error_code="invalid_manager",
            )
        if manager.deleted_at is not None:
            raise ConflictError(
                f"{manager.full_name} is archived and cannot be a reporting manager.",
                error_code="invalid_manager",
            )
        if not manager.is_employed:
            raise ConflictError(
                f"{manager.full_name} is {self._status_label(manager.employment_status)} and cannot be a "
                "reporting manager.",
                error_code="invalid_manager",
            )

        if employee_id is not None and await self._employees.manager_would_cycle(employee_id, manager_id):
            raise ConflictError(
                f"{manager.full_name} reports to this employee, directly or indirectly. "
                "Assigning them would create a reporting loop.",
                error_code="reporting_cycle",
            )

    async def _assert_identifiers_available(
        self, values: dict[str, Any], *, exclude_employee_id: uuid.UUID | None
    ) -> None:
        """Statutory identifiers belong to one person, so they cannot be shared.

        A duplicate here almost always means the same person has been entered
        twice, which is far cheaper to catch now than to reconcile in payroll.
        """
        for field, label in IDENTIFIER_LABELS.items():
            value = values.get(field)
            if not value:
                continue

            clash = await self._employees.find_identifier_owner(
                field, str(value), exclude_employee_id=exclude_employee_id
            )
            if clash is not None:
                # The message names the other employee but never repeats the
                # identifier itself.
                raise ConflictError(
                    f"That {label} is already recorded against {clash.employee_code} ({clash.full_name}).",
                    error_code="duplicate_identifier",
                )

    def _assert_status_transition(self, employee: Employee, target: EmploymentStatus) -> None:
        """Reject a status change that says nothing or undoes an ending."""
        current = EmploymentStatus(employee.employment_status)

        if current == target:
            raise ConflictError(
                f"{employee.full_name} is already {self._status_label(target.value)}.",
                error_code="already_in_status",
            )

        if current in _TERMINAL_STATUSES and target not in {EmploymentStatus.ACTIVE, *_TERMINAL_STATUSES}:
            raise ConflictError(
                f"{employee.full_name} is {self._status_label(current.value)}. A former employee can only "
                "be reactivated, not moved back through the joining lifecycle.",
                error_code="invalid_status_transition",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _reload(self, employee_id: uuid.UUID) -> Employee:
        """Re-read after a write so the organizational references are current."""
        refreshed = await self._employees.get_with_relationships(employee_id)
        if refreshed is None:  # pragma: no cover - the row was just written
            raise NotFoundError("Employee")
        return refreshed
