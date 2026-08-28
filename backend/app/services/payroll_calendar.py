"""Period day-set arithmetic shared by payroll input preparation and the
calculation engine.

One implementation on purpose: "which dates in this period are working days"
is a single question, and two modules answering it independently is how a
payroll input and the payroll calculated from it come to disagree about a
denominator. Everything derives from the Phase 2 configuration — the weekly
off list and the referenced workforce holiday calendar — and nothing here
touches the database beyond what the loaded configuration row already
carries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.models.enums import PayrollDayBasis, WorkingDaysRule
from app.models.payroll import PayrollConfiguration


def dates_between(start: date, end: date) -> list[date]:
    """Every date from start to end, inclusive."""
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


@dataclass(frozen=True)
class PeriodCalendar:
    """The day sets one payroll period resolves to under one configuration."""

    start: date
    end: date
    all_dates: list[date]
    off_dates: frozenset[date]
    holiday_dates: frozenset[date]
    working_dates: frozenset[date]
    #: What the configured working-days rule reports as the period's working
    #: day count — the calendar count when the rule says calendar days.
    working_days: int

    @property
    def calendar_days(self) -> int:
        return len(self.all_dates)

    def basis_days(self, basis: str | PayrollDayBasis) -> int:
        """The denominator a per-day rate divides by, for a given basis."""
        value = PayrollDayBasis(basis).value
        return self.calendar_days if value == PayrollDayBasis.CALENDAR_DAYS.value else len(self.working_dates)

    def basis_days_in(self, basis: str | PayrollDayBasis, window: set[date]) -> int:
        """How many of ``window``'s dates count under a given basis."""
        value = PayrollDayBasis(basis).value
        if value == PayrollDayBasis.CALENDAR_DAYS.value:
            return len(window)
        return len(self.working_dates & window)


def period_calendar(config: PayrollConfiguration, start: date, end: date) -> PeriodCalendar:
    """Resolve one period's day sets under the given configuration.

    Weekly offs come from the configuration's weekday list; holidays come from
    the referenced workforce calendar (payroll owns no holiday list of its
    own); a holiday falling on a weekly off counts once, as an off.
    """
    all_dates = dates_between(start, end)
    off_weekdays = {int(day) for day in config.weekly_off_days}
    off_dates = frozenset(d for d in all_dates if d.weekday() in off_weekdays)

    holiday_dates: frozenset[date] = frozenset()
    if config.holiday_calendar is not None:
        holiday_dates = (
            frozenset(
                holiday.holiday_date
                for holiday in config.holiday_calendar.holidays
                if holiday.deleted_at is None and start <= holiday.holiday_date <= end
            )
            - off_dates
        )

    working_dates = frozenset(set(all_dates) - off_dates - holiday_dates)
    working_days = (
        len(all_dates)
        if config.working_days_rule == WorkingDaysRule.CALENDAR_DAYS.value
        else len(working_dates)
    )
    return PeriodCalendar(
        start=start,
        end=end,
        all_dates=all_dates,
        off_dates=off_dates,
        holiday_dates=holiday_dates,
        working_dates=working_dates,
        working_days=working_days,
    )
