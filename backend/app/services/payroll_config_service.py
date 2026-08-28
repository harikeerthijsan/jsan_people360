"""Payroll configuration and pay rules business logic (Phase 2).

Three rules shape this module.

**Configuration is never silently overwritten.** Every update to the
singleton requires a reason and an effective date, and writes one
``payroll_configuration_history`` row per field that actually changed —
previous value, new value, who, why — before the column moves. There is no
method that edits or deletes a history row.

**Nothing is calculated.** Periods are created and moved along their status
map; rules and flags are stored and validated for coherence. The engine that
reads them is a later phase, which is why a period can be approved here while
carrying no numbers at all.

**Existing modules are referenced, never duplicated.** Holidays come from the
workforce module's calendars, leave rules point at its leave types, and the
per-employee row carries no money — the salary is the Phase 1 compensation
record.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.audit_log import AuditAction
from app.models.enums import (
    PAYROLL_PERIOD_TRANSITIONS,
    LeaveTreatment,
    PayrollPeriodStatus,
    RecordStatus,
    RoundingRule,
)
from app.models.payroll import (
    PayrollConfiguration,
    PayrollConfigurationHistory,
    PayrollEmployeeSetting,
    PayrollLeaveRule,
    PayrollPeriod,
)
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.payroll_repository import (
    EmployeeCompensationRepository,
    PayrollConfigurationHistoryRepository,
    PayrollConfigurationRepository,
    PayrollEmployeeSettingRepository,
    PayrollLeaveRuleRepository,
    PayrollPeriodRepository,
)
from app.repositories.workforce_repository import HolidayRepository, LeaveTypeRepository
from app.schemas.payroll import (
    EmployeeSettingsData,
    EmployeeSettingsListParams,
    EmployeeSettingsRead,
    EmployeeSettingsUpsert,
    EmployeeSummary,
    LeaveRuleCreate,
    LeaveRuleRead,
    LeaveRuleUpdate,
    PayrollConfigHistoryRead,
    PayrollConfigRead,
    PayrollConfigUpdate,
    PayrollPeriodCreate,
    PayrollPeriodRead,
    PayrollPeriodUpdate,
    PeriodListParams,
)
from app.services.audit_service import AuditService

logger = get_logger("services.payroll_config")

#: Fields on the update payload that are instructions rather than columns.
_NON_COLUMN_FIELDS = {"reason", "effective_from", "clear_holiday_calendar", "clear_overtime_max_hours"}


class PayrollConfigService:
    """The payroll rulebook: configuration, periods, rules and settings."""

    def __init__(
        self,
        config: PayrollConfigurationRepository,
        config_history: PayrollConfigurationHistoryRepository,
        periods: PayrollPeriodRepository,
        leave_rules: PayrollLeaveRuleRepository,
        employee_settings: PayrollEmployeeSettingRepository,
        compensation: EmployeeCompensationRepository,
        leave_types: LeaveTypeRepository,
        holidays: HolidayRepository,
        employees: EmployeeRepository,
        audit: AuditService,
    ) -> None:
        self.config = config
        self.config_history = config_history
        self.periods = periods
        self.leave_rules = leave_rules
        self.employee_settings = employee_settings
        self.compensation = compensation
        self.leave_types = leave_types
        self.holidays = holidays
        self.employees = employees
        self.audit = audit

    # ==================================================================
    # Configuration
    # ==================================================================
    async def get_config(self) -> PayrollConfigRead:
        row = await self._require_config()
        return self._present_config(row)

    async def update_config(self, payload: PayrollConfigUpdate, *, actor_id: uuid.UUID) -> PayrollConfigRead:
        row = await self._require_config()

        changes = payload.model_dump(exclude_unset=True, exclude=_NON_COLUMN_FIELDS)
        for field, value in list(changes.items()):
            if hasattr(value, "value"):
                changes[field] = value.value
        if payload.clear_holiday_calendar:
            changes["holiday_calendar_id"] = None
        if payload.clear_overtime_max_hours:
            changes["overtime_max_hours"] = None

        if changes.get("holiday_calendar_id") is not None:
            calendar = await self.holidays.get(changes["holiday_calendar_id"])
            if calendar is None:
                raise NotFoundError("Holiday calendar")

        # Coherence of the final state, which a partial payload cannot see.
        final_rule = changes.get("rounding_rule", row.rounding_rule)
        final_precision = changes.get("rounding_precision", row.rounding_precision)
        if final_rule == RoundingRule.CUSTOM.value and final_precision is None:
            raise ValidationError("Custom rounding needs a precision — 0.01, 1, 10 and so on")
        if final_rule != RoundingRule.CUSTOM.value and row.rounding_precision is not None:
            # Leaving a stale precision behind would make the next switch to
            # custom silently revive a number nobody chose on purpose.
            changes.setdefault("rounding_precision", None)
        final_min = changes.get("overtime_min_hours", row.overtime_min_hours)
        final_max = changes.get("overtime_max_hours", row.overtime_max_hours)
        if final_max is not None and final_min is not None and final_max < final_min:
            raise ValidationError("Maximum overtime hours cannot be below the minimum")

        # Only what actually differs is a change; only changes reach history.
        real_changes = {field: value for field, value in changes.items() if getattr(row, field) != value}
        if not real_changes:
            return self._present_config(row)

        for field, new_value in sorted(real_changes.items()):
            await self.config_history.add(
                PayrollConfigurationHistory(
                    configuration_id=row.id,
                    field=field,
                    previous_value=self._stringify(getattr(row, field)),
                    new_value=self._stringify(new_value),
                    effective_from=payload.effective_from,
                    reason=payload.reason,
                    changed_by_id=actor_id,
                ),
                actor_id=actor_id,
            )

        await self.config.update(row, real_changes, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.PAYROLL_CONFIG_UPDATED,
            actor_id=actor_id,
            entity_type="payroll_configuration",
            entity_id=row.id,
            description="Updated payroll configuration",
            context={
                "fields": sorted(real_changes),
                "effective_from": payload.effective_from.isoformat(),
                "reason": payload.reason,
            },
        )
        return self._present_config(row)

    async def config_history_entries(self) -> list[PayrollConfigHistoryRead]:
        rows = await self.config_history.newest_first()
        return [
            PayrollConfigHistoryRead(
                id=entry.id,
                field=entry.field,
                previous_value=entry.previous_value,
                new_value=entry.new_value,
                effective_from=entry.effective_from,
                reason=entry.reason,
                changed_by_name=(
                    f"{entry.changed_by.first_name} {entry.changed_by.last_name}".strip()
                    if entry.changed_by is not None
                    else None
                ),
                created_at=entry.created_at,
            )
            for entry in rows
        ]

    async def _require_config(self) -> PayrollConfiguration:
        row = await self.config.singleton()
        if row is None:  # pragma: no cover - seeded by the migration
            raise NotFoundError("Payroll configuration")
        return row

    @staticmethod
    def _stringify(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return str(value)

    def _present_config(self, row: PayrollConfiguration) -> PayrollConfigRead:
        return PayrollConfigRead(
            id=row.id,
            pay_frequency=row.pay_frequency,
            period_start_day=row.period_start_day,
            period_end_day=row.period_end_day,
            pay_day=row.pay_day,
            cutoff_day=row.cutoff_day,
            currency=row.currency,
            working_days_rule=row.working_days_rule,
            weekly_off_days=[int(day) for day in row.weekly_off_days],
            holiday_calendar_id=row.holiday_calendar_id,
            holiday_calendar_name=(row.holiday_calendar.name if row.holiday_calendar is not None else None),
            proration_basis=row.proration_basis,
            unpaid_leave_treatment=row.unpaid_leave_treatment,
            unpaid_leave_basis=row.unpaid_leave_basis,
            overtime_enabled=row.overtime_enabled,
            overtime_basis=row.overtime_basis,
            overtime_multiplier=row.overtime_multiplier,
            overtime_min_hours=row.overtime_min_hours,
            overtime_max_hours=row.overtime_max_hours,
            overtime_approval_required=row.overtime_approval_required,
            standard_daily_hours=row.standard_daily_hours,
            deduct_absence=row.deduct_absence,
            deduct_late_arrival=row.deduct_late_arrival,
            deduct_early_exit=row.deduct_early_exit,
            require_approved_attendance=row.require_approved_attendance,
            rounding_rule=row.rounding_rule,
            rounding_precision=row.rounding_precision,
            updated_at=row.updated_at,
        )

    # ==================================================================
    # Periods
    # ==================================================================
    async def list_periods(self, params: PeriodListParams) -> tuple[list[PayrollPeriodRead], int]:
        rows, total = await self.periods.search(params)
        return [PayrollPeriodRead.model_validate(row) for row in rows], total

    async def get_period(self, period_id: uuid.UUID) -> PayrollPeriod:
        period = await self.periods.get(period_id)
        if period is None:
            raise NotFoundError("Payroll period")
        return period

    async def create_period(self, payload: PayrollPeriodCreate, *, actor_id: uuid.UUID) -> PayrollPeriod:
        name = payload.name.strip()
        if await self.periods.by_name(name) is not None:
            raise ConflictError(
                f'A payroll period named "{name}" already exists.', error_code="duplicate_name"
            )
        clash = await self.periods.overlapping(payload.start_date, payload.end_date)
        if clash is not None:
            raise ConflictError(
                f"The dates overlap the existing period {clash.name}.",
                error_code="overlapping_period",
            )
        period = await self.periods.add(
            PayrollPeriod(
                name=name,
                start_date=payload.start_date,
                end_date=payload.end_date,
                pay_date=payload.pay_date,
                status=PayrollPeriodStatus.OPEN.value,
                notes=payload.notes,
            ),
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.PAYROLL_PERIOD_CREATED,
            actor_id=actor_id,
            entity_type="payroll_period",
            entity_id=period.id,
            description=f"Created payroll period {period.name}",
            context={
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat(),
                "pay_date": period.pay_date.isoformat(),
            },
        )
        return period

    async def update_period(
        self, period_id: uuid.UUID, payload: PayrollPeriodUpdate, *, actor_id: uuid.UUID
    ) -> PayrollPeriod:
        period = await self.get_period(period_id)
        if period.status != PayrollPeriodStatus.OPEN.value:
            raise ConflictError(
                "Only an open period can be edited. Move it back to open first, or cancel it.",
                error_code="period_not_open",
            )

        changes = payload.model_dump(exclude_unset=True)
        if changes.get("name") is not None:
            name = str(changes["name"]).strip()
            existing = await self.periods.by_name(name)
            if existing is not None and existing.id != period.id:
                raise ConflictError(
                    f'A payroll period named "{name}" already exists.', error_code="duplicate_name"
                )
            changes["name"] = name

        final_start = changes.get("start_date", period.start_date)
        final_end = changes.get("end_date", period.end_date)
        final_pay = changes.get("pay_date", period.pay_date)
        if final_end < final_start:
            raise ValidationError("The period cannot end before it starts")
        if final_pay < final_start:
            raise ValidationError("The pay date cannot be before the period starts")
        clash = await self.periods.overlapping(final_start, final_end, exclude_id=period.id)
        if clash is not None:
            raise ConflictError(
                f"The dates overlap the existing period {clash.name}.",
                error_code="overlapping_period",
            )

        await self.periods.update(period, changes, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.PAYROLL_PERIOD_UPDATED,
            actor_id=actor_id,
            entity_type="payroll_period",
            entity_id=period.id,
            description=f"Updated payroll period {period.name}",
            context={"fields": sorted(changes)},
        )
        return period

    async def set_period_status(
        self, period_id: uuid.UUID, new_status: PayrollPeriodStatus, *, actor_id: uuid.UUID
    ) -> PayrollPeriod:
        period = await self.get_period(period_id)
        previous = period.status
        if previous == new_status.value:
            return period
        if new_status.value not in PAYROLL_PERIOD_TRANSITIONS.get(previous, frozenset()):
            raise ConflictError(
                f"A {previous.replace('_', ' ')} period cannot become {new_status.value.replace('_', ' ')}.",
                error_code="invalid_status_transition",
            )
        await self.periods.update(period, {"status": new_status.value}, actor_id=actor_id)
        await self.audit.record_success(
            AuditAction.PAYROLL_PERIOD_STATUS_CHANGED,
            actor_id=actor_id,
            entity_type="payroll_period",
            entity_id=period.id,
            description=f"Payroll period {period.name}: {previous} -> {new_status.value}",
            context={"previous": previous, "new": new_status.value},
        )
        return period

    # ==================================================================
    # Leave rules
    # ==================================================================
    async def list_leave_rules(self, *, include_inactive: bool = False) -> list[LeaveRuleRead]:
        rows = await self.leave_rules.all_rules(include_inactive=include_inactive)
        return [self._present_leave_rule(row) for row in rows]

    async def create_leave_rule(self, payload: LeaveRuleCreate, *, actor_id: uuid.UUID) -> LeaveRuleRead:
        leave_type = await self.leave_types.get(payload.leave_type_id)
        if leave_type is None:
            raise NotFoundError("Leave type")

        existing = await self.leave_rules.by_leave_type(payload.leave_type_id, include_deleted=True)
        if existing is not None and existing.deleted_at is None:
            raise ConflictError(
                f"A payroll rule for {leave_type.name} already exists. Edit it instead.",
                error_code="duplicate_rule",
            )

        basis = payload.deduction_basis.value if payload.deduction_basis else None
        if payload.treatment == LeaveTreatment.PAID:
            basis = None

        if existing is not None:
            # Re-creating a rule that once existed: restore rather than
            # insert, because the unique constraint spans soft-deleted rows.
            await self.leave_rules.restore(existing, actor_id=actor_id)
            rule = await self.leave_rules.update(
                existing,
                {
                    "treatment": payload.treatment.value,
                    "deduction_basis": basis,
                    "description": payload.description,
                    "status": RecordStatus.ACTIVE.value,
                },
                actor_id=actor_id,
            )
        else:
            rule = await self.leave_rules.add(
                PayrollLeaveRule(
                    leave_type_id=payload.leave_type_id,
                    treatment=payload.treatment.value,
                    deduction_basis=basis,
                    description=payload.description,
                    status=RecordStatus.ACTIVE.value,
                ),
                actor_id=actor_id,
            )

        await self._audit_leave_rule(rule, actor_id, f"Created payroll rule for {leave_type.name}")
        return self._present_leave_rule(await self._reload_leave_rule(rule.id))

    async def update_leave_rule(
        self, rule_id: uuid.UUID, payload: LeaveRuleUpdate, *, actor_id: uuid.UUID
    ) -> LeaveRuleRead:
        rule = await self.leave_rules.get(rule_id)
        if rule is None:
            raise NotFoundError("Payroll leave rule")

        changes = payload.model_dump(exclude_unset=True)
        for enum_field in ("treatment", "deduction_basis"):
            if changes.get(enum_field) is not None:
                changes[enum_field] = changes[enum_field].value

        final_treatment = changes.get("treatment", rule.treatment)
        final_basis = changes.get("deduction_basis", rule.deduction_basis)
        if final_treatment == LeaveTreatment.UNPAID.value and final_basis is None:
            raise ValidationError("An unpaid rule must say which day basis the deduction uses")
        if final_treatment == LeaveTreatment.PAID.value:
            changes["deduction_basis"] = None

        await self.leave_rules.update(rule, changes, actor_id=actor_id)
        await self._audit_leave_rule(rule, actor_id, f"Updated payroll rule for {rule.leave_type.name}")
        return self._present_leave_rule(rule)

    async def set_leave_rule_status(
        self, rule_id: uuid.UUID, new_status: RecordStatus, *, actor_id: uuid.UUID
    ) -> LeaveRuleRead:
        rule = await self.leave_rules.get(rule_id)
        if rule is None:
            raise NotFoundError("Payroll leave rule")
        if rule.status != new_status.value:
            await self.leave_rules.update(rule, {"status": new_status.value}, actor_id=actor_id)
            await self._audit_leave_rule(
                rule, actor_id, f"Payroll rule for {rule.leave_type.name}: {new_status.value}"
            )
        return self._present_leave_rule(rule)

    async def _reload_leave_rule(self, rule_id: uuid.UUID) -> PayrollLeaveRule:
        rule = await self.leave_rules.get(rule_id)
        if rule is None:  # pragma: no cover - just written
            raise NotFoundError("Payroll leave rule")
        return rule

    async def _audit_leave_rule(self, rule: PayrollLeaveRule, actor_id: uuid.UUID, text: str) -> None:
        await self.audit.record_success(
            AuditAction.PAYROLL_LEAVE_RULE_CHANGED,
            actor_id=actor_id,
            entity_type="payroll_leave_rule",
            entity_id=rule.id,
            description=text,
            context={"treatment": rule.treatment, "deduction_basis": rule.deduction_basis},
        )

    def _present_leave_rule(self, rule: PayrollLeaveRule) -> LeaveRuleRead:
        return LeaveRuleRead(
            id=rule.id,
            leave_type_id=rule.leave_type_id,
            leave_type_name=rule.leave_type.name,
            leave_type_code=rule.leave_type.code,
            leave_type_is_paid=rule.leave_type.is_paid,
            treatment=rule.treatment,
            deduction_basis=rule.deduction_basis,
            description=rule.description,
            status=rule.status,
            updated_at=rule.updated_at,
        )

    # ==================================================================
    # Employee payroll settings
    # ==================================================================
    async def list_employee_settings(
        self, params: EmployeeSettingsListParams
    ) -> tuple[list[EmployeeSettingsRead], int]:
        rows, total = await self.employee_settings.search(params)
        return [self._present_settings(row) for row in rows], total

    async def employee_settings_data(self, employee_id: uuid.UUID) -> EmployeeSettingsData:
        employee = await self.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("Employee")
        row = await self.employee_settings.by_employee(employee_id)
        current = await self.compensation.current_for_employee(employee_id)
        return EmployeeSettingsData(
            employee=EmployeeSummary.model_validate(employee),
            has_active_compensation=current is not None,
            settings=self._present_settings(row) if row is not None else None,
        )

    async def upsert_employee_settings(
        self, employee_id: uuid.UUID, payload: EmployeeSettingsUpsert, *, actor_id: uuid.UUID
    ) -> EmployeeSettingsData:
        employee = await self.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("Employee")

        values = {
            "eligibility": payload.eligibility.value,
            "eligibility_reason": (payload.eligibility_reason.value if payload.eligibility_reason else None),
            "frequency_override": (payload.frequency_override.value if payload.frequency_override else None),
            "proration_override": (payload.proration_override.value if payload.proration_override else None),
            "overtime_eligible": payload.overtime_eligible,
            "unpaid_leave_deduction": payload.unpaid_leave_deduction,
            "payroll_effective_date": payload.payroll_effective_date,
            "notes": payload.notes,
        }

        row = await self.employee_settings.by_employee(employee_id, include_deleted=True)
        if row is None:
            row = await self.employee_settings.add(
                PayrollEmployeeSetting(employee_id=employee_id, **values), actor_id=actor_id
            )
            previous: dict[str, Any] = {}
        else:
            previous = {
                field: self._stringify(getattr(row, field))
                for field in values
                if getattr(row, field) != values[field]
            }
            if row.deleted_at is not None:
                await self.employee_settings.restore(row, actor_id=actor_id)
            await self.employee_settings.update(row, values, actor_id=actor_id)

        await self.audit.record_success(
            AuditAction.EMPLOYEE_PAYROLL_SETTINGS_CHANGED,
            actor_id=actor_id,
            entity_type="payroll_employee_setting",
            entity_id=row.id,
            description=f"Updated payroll settings for {employee.full_name}",
            context={
                "employee_id": str(employee_id),
                "eligibility": row.eligibility,
                "changed": {
                    field: {"previous": value, "new": self._stringify(values[field])}
                    for field, value in previous.items()
                },
            },
        )
        return await self.employee_settings_data(employee_id)

    def _present_settings(self, row: PayrollEmployeeSetting) -> EmployeeSettingsRead:
        return EmployeeSettingsRead(
            id=row.id,
            employee=EmployeeSummary.model_validate(row.employee),
            eligibility=row.eligibility,
            eligibility_reason=row.eligibility_reason,
            frequency_override=row.frequency_override,
            proration_override=row.proration_override,
            overtime_eligible=row.overtime_eligible,
            unpaid_leave_deduction=row.unpaid_leave_deduction,
            payroll_effective_date=row.payroll_effective_date,
            notes=row.notes,
            updated_at=row.updated_at,
        )
