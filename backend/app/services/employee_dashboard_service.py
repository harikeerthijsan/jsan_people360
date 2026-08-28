"""Headline figures for the employee dashboard.

Separate from :class:`~app.services.employee_service.EmployeeService` because it
answers a different kind of question. The employee service enforces rules about
one record; this one only counts, holds no guards, and will grow as later modules
add their own tiles.
"""

from __future__ import annotations

import calendar
from datetime import date

from app.models.enums import EmploymentStatus
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.employee import CountByLabel, EmployeeDashboardStats

#: How many business units the breakdown shows before the tail is dropped. A bar
#: chart with forty bars communicates less than one with eight.
BUSINESS_UNIT_LIMIT = 8


def _humanise(value: str) -> str:
    """``notice_period`` -> ``Notice period``."""
    return value.replace("_", " ").capitalize()


class EmployeeDashboardService:
    """Aggregate counts across the employee directory."""

    def __init__(self, repository: EmployeeRepository) -> None:
        self._employees = repository

    async def stats(self, *, today: date | None = None) -> EmployeeDashboardStats:
        """Every figure the dashboard shows, in one round of queries.

        ``today`` is injectable so the month boundary can be tested without
        waiting for one.
        """
        reference = today or date.today()
        month_start = reference.replace(day=1)
        month_end = reference.replace(day=calendar.monthrange(reference.year, reference.month)[1])

        by_status = await self._employees.count_by_status()
        by_business_unit = await self._employees.count_by_business_unit(limit=BUSINESS_UNIT_LIMIT)
        by_work_mode = await self._employees.count_by_work_mode()

        return EmployeeDashboardStats(
            total_employees=await self._employees.count_live(),
            employed=await self._employees.count_employed(),
            by_status=[CountByLabel(label=_humanise(name), count=count) for name, count in by_status],
            by_business_unit=[CountByLabel(label=name, count=count) for name, count in by_business_unit],
            by_work_mode=[CountByLabel(label=_humanise(name), count=count) for name, count in by_work_mode],
            joining_this_month=await self._employees.count_joining_between(month_start, month_end),
            on_probation=await self._employees.count_with_status(EmploymentStatus.PROBATION),
            on_notice=await self._employees.count_with_status(EmploymentStatus.NOTICE_PERIOD),
            archived=await self._employees.count_archived(),
        )
