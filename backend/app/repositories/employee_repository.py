"""Persistence operations for the Employee Management module.

Two repositories: one for the employee record and its satellite tables, one for
the append-only employment history. They are separate because the history has a
different access pattern -- always scoped to one employee, always ordered, never
updated -- and mixing it into the employee repository would invite a query that
loads an unbounded history alongside a list page.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from datetime import date
from typing import Any

from sqlalchemy import Select, and_, false, func, or_, select, text
from sqlalchemy.sql.elements import ColumnElement

from app.db.base_class import Base
from app.models.business_unit import BusinessUnit
from app.models.designation import Designation
from app.models.employee import Employee
from app.models.employee_address import EmployeeAddress
from app.models.employee_bank_detail import EmployeeBankDetail
from app.models.employee_identification import EmployeeIdentification
from app.models.employment_history import EmployeeEmploymentHistory
from app.models.employment_type import EmploymentType
from app.models.enums import EMPLOYED_STATUSES, EmploymentStatus, RecordStatus
from app.models.grade import Grade
from app.models.location import Location
from app.models.team import Team
from app.repositories.base import BaseRepository
from app.repositories.master_repository import LIKE_ESCAPE, escape_like
from app.schemas.employee import EmployeeListParams
from app.utils.strings import normalise_email

#: The organizational references an employee carries, and the label used when one
#: is rejected. Declared once so the checks and the messages cannot drift.
EMPLOYEE_REFERENCE_MODELS: dict[str, tuple[type[Base], str]] = {
    "employment_type_id": (EmploymentType, "employment type"),
    "business_unit_id": (BusinessUnit, "business unit"),
    "team_id": (Team, "team"),
    "designation_id": (Designation, "designation"),
    "grade_id": (Grade, "grade"),
    "salary_grade_id": (Grade, "salary grade"),
    "work_location_id": (Location, "work location"),
}

#: Identifier columns that must be unique across employees, and how to name them
#: in a duplicate message.
IDENTIFIER_LABELS: dict[str, str] = {
    "aadhaar_number": "Aadhaar number",
    "pan_number": "PAN",
    "passport_number": "passport number",
    "uan_number": "UAN",
    "pf_number": "PF number",
    "esi_number": "ESI number",
}

#: Hard ceiling on an export. Large enough for any realistic headcount, small
#: enough that a mistaken unfiltered export cannot exhaust memory.
EXPORT_LIMIT = 10_000

#: How far up a reporting chain to walk when checking for a cycle. A chain deeper
#: than this is already broken data, and an unbounded recursive query against it
#: would not terminate.
MAX_REPORTING_DEPTH = 50


class EmployeeRepository(BaseRepository[Employee]):
    """Queries scoped to employee records."""

    model = Employee

    #: Columns a free-text search covers. Deliberately includes the identifiers
    #: someone is most likely to be handed by a colleague -- a staff code from a
    #: ticket, an email from a forwarded message.
    searchable_fields: tuple[str, ...] = (
        "employee_code",
        "first_name",
        "last_name",
        "official_email",
        "personal_email",
        "mobile_number",
        "official_mobile",
    )

    #: Columns a client may sort by. Anything else is rejected by the service
    #: rather than passed through to SQL.
    sortable_fields: frozenset[str] = frozenset(
        {
            "employee_code",
            "first_name",
            "last_name",
            "official_email",
            "joining_date",
            "confirmation_date",
            "employment_status",
            "created_at",
            "updated_at",
        }
    )

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    async def get_with_relationships(self, employee_id: uuid.UUID) -> Employee | None:
        """Re-read an employee with every eager relationship repopulated.

        ``populate_existing`` matters after a write that changed a reference: the
        identity-mapped instance would otherwise still hold the record that was
        just replaced.
        """
        stmt = select(Employee).where(Employee.id == employee_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def get_by_code(self, employee_code: str) -> Employee | None:
        stmt = select(Employee).where(func.upper(Employee.employee_code) == employee_code.upper())
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def find_official_email_owner(
        self, email: str, *, exclude_id: uuid.UUID | None = None
    ) -> Employee | None:
        """Find any employee holding this work address, archived rows included.

        Archived employees keep their address -- the unique index covers every
        row -- so the service can say "restore that record" rather than leaving
        the database to raise an opaque integrity error.
        """
        stmt = select(Employee).where(func.lower(Employee.official_email) == normalise_email(email))
        if exclude_id is not None:
            stmt = stmt.where(Employee.id != exclude_id)
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def find_by_user_id(
        self, user_id: uuid.UUID, *, exclude_id: uuid.UUID | None = None
    ) -> Employee | None:
        """Find the employee already linked to a login account, if any."""
        stmt = select(Employee).where(Employee.user_id == user_id)
        if exclude_id is not None:
            stmt = stmt.where(Employee.id != exclude_id)
        return (await self.session.execute(stmt)).scalars().unique().first()

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------
    def _scoped_select(self, *, archived: bool) -> Select[tuple[Employee]]:
        """Select either the live employees or the archived ones, never both."""
        stmt = select(Employee)
        return stmt.where(Employee.deleted_at.is_not(None) if archived else Employee.deleted_at.is_(None))

    def _search_criteria(self, term: str) -> ColumnElement[bool]:
        """Case-insensitive OR across the searchable columns.

        Also matches the composed full name, so searching "Priya Sharma" finds a
        row whose parts are stored separately -- the most obvious thing to type,
        and the one a naive per-column search misses.
        """
        pattern = f"%{escape_like(term)}%"
        clauses: list[ColumnElement[bool]] = [
            getattr(Employee, field).ilike(pattern, escape=LIKE_ESCAPE)
            for field in self.searchable_fields
            if hasattr(Employee, field)
        ]
        clauses.append((Employee.first_name + " " + Employee.last_name).ilike(pattern, escape=LIKE_ESCAPE))
        return or_(*clauses)

    def _filters(self, params: EmployeeListParams) -> list[ColumnElement[bool]]:
        criteria: list[ColumnElement[bool]] = []

        if params.search:
            criteria.append(self._search_criteria(params.search))

        if params.employment_status is not None:
            criteria.append(Employee.employment_status == params.employment_status.value)

        if params.work_mode is not None:
            criteria.append(Employee.work_mode == params.work_mode.value)

        for field in (
            "business_unit_id",
            "team_id",
            "designation_id",
            "grade_id",
            "work_location_id",
            "employment_type_id",
            "reporting_manager_id",
        ):
            value = getattr(params, field)
            if value is not None:
                criteria.append(getattr(Employee, field) == value)

        if params.joined_from is not None:
            criteria.append(Employee.joining_date >= params.joined_from)
        if params.joined_to is not None:
            criteria.append(Employee.joining_date <= params.joined_to)

        return criteria

    def _ordered(self, stmt: Select[tuple[Employee]], params: EmployeeListParams) -> Select[tuple[Employee]]:
        column = getattr(Employee, params.sort_by)
        # A second, stable key keeps paging deterministic when the primary sort
        # has duplicates -- many employees share a status or a joining date.
        return stmt.order_by(column.desc() if params.descending else column.asc()).order_by(Employee.id)

    @staticmethod
    def _visibility(visible_ids: Collection[uuid.UUID] | None) -> list[ColumnElement[bool]]:
        """Narrow a directory query to a caller's team scope.

        ``None`` means no restriction. An *empty* collection is not the same
        thing and must not be treated as one: it means the caller is entitled to
        nobody, and the query has to return nothing rather than everything. That
        distinction is the whole reason this takes a nullable collection rather
        than an optional set the caller might leave empty by accident.
        """
        if visible_ids is None:
            return []
        return [Employee.id.in_(visible_ids)] if visible_ids else [false()]

    async def list_page(
        self, params: EmployeeListParams, *, visible_ids: Collection[uuid.UUID] | None = None
    ) -> tuple[Sequence[Employee], int]:
        """Return one page of employees and the total number of matches."""
        base = (
            self._scoped_select(archived=params.archived)
            .where(*self._filters(params))
            .where(*self._visibility(visible_ids))
        )

        count_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        page_stmt = self._ordered(base, params).offset(params.offset).limit(params.page_size)
        rows = (await self.session.execute(page_stmt)).scalars().unique().all()
        return rows, total

    async def list_for_export(
        self, params: EmployeeListParams, *, visible_ids: Collection[uuid.UUID] | None = None
    ) -> Sequence[Employee]:
        """Every employee matching the filters, up to :data:`EXPORT_LIMIT`.

        An export honours the filters on screen but ignores the page: exporting
        page 1 of 12 is never what the user meant.
        """
        base = (
            self._scoped_select(archived=params.archived)
            .where(*self._filters(params))
            .where(*self._visibility(visible_ids))
        )
        stmt = self._ordered(base, params).limit(EXPORT_LIMIT)
        return (await self.session.execute(stmt)).scalars().unique().all()

    # ------------------------------------------------------------------
    # Referential checks
    # ------------------------------------------------------------------
    async def find_unusable_org_references(self, data: dict[str, uuid.UUID | None]) -> list[str]:
        """Names of organizational references that cannot be assigned.

        A reference is usable only when the master record exists, is live and is
        active -- the same rule the master module applies to its own parents.
        Every field is checked so the service can report them all at once rather
        than one per round trip.
        """
        invalid: list[str] = []

        for field, (model, label) in EMPLOYEE_REFERENCE_MODELS.items():
            value = data.get(field)
            if value is None:
                continue

            related: Any = model
            stmt = (
                select(func.count())
                .select_from(related)
                .where(
                    related.id == value,
                    related.deleted_at.is_(None),
                    related.status == RecordStatus.ACTIVE.value,
                )
            )
            if int((await self.session.execute(stmt)).scalar_one()) == 0:
                invalid.append(label)

        return invalid

    async def manager_would_cycle(self, employee_id: uuid.UUID, manager_id: uuid.UUID) -> bool:
        """Whether making ``manager_id`` the manager of ``employee_id`` closes a loop.

        Walks up the proposed manager's reporting chain. If the employee appears
        in it, the assignment would create a cycle -- A reports to B reports to A
        -- which makes every org-chart and approval-routing query non-terminating.

        The CHECK constraint on the table catches only the one-step case.
        """
        chain = text("""
            WITH RECURSIVE chain(id, reporting_manager_id, depth) AS (
                SELECT e.id, e.reporting_manager_id, 1
                FROM employees e
                WHERE e.id = :manager_id
                UNION ALL
                SELECT e.id, e.reporting_manager_id, c.depth + 1
                FROM employees e
                JOIN chain c ON e.id = c.reporting_manager_id
                WHERE c.depth < :max_depth
            )
            SELECT count(*) FROM chain WHERE id = :employee_id
            """)
        result = await self.session.execute(
            chain,
            {"manager_id": manager_id, "employee_id": employee_id, "max_depth": MAX_REPORTING_DEPTH},
        )
        return int(result.scalar_one()) > 0

    async def direct_report_ids(self, manager_id: uuid.UUID) -> set[uuid.UUID]:
        """The employees who report to this one, for team scoping.

        Direct reports only -- one hop, not the whole subtree. That is what a
        manager is accountable for, and it is what the approval routing already
        assumes: a leave request is addressed to ``reporting_manager_id``, not to
        everyone above it. Widening this to the full chain is a change to this
        one query and nothing else.

        Archived employees are excluded. Their records are still readable to HR
        through the archive, but a manager approving a week of timesheets has no
        business seeing somebody who has left.
        """
        stmt = select(Employee.id).where(
            Employee.reporting_manager_id == manager_id,
            Employee.deleted_at.is_(None),
        )
        return set((await self.session.execute(stmt)).scalars().all())

    async def user_ids_for(self, employee_ids: set[uuid.UUID]) -> set[uuid.UUID]:
        """The login accounts belonging to these employees.

        Needed because the document vault files things against either an
        employee or the user account that employee signs in with, and a scope
        that covered only one of the two would leave the other readable.
        """
        if not employee_ids:
            return set()
        stmt = select(Employee.user_id).where(Employee.id.in_(employee_ids), Employee.user_id.is_not(None))
        return {row for row in (await self.session.execute(stmt)).scalars().all() if row is not None}

    async def count_direct_reports(self, employee_id: uuid.UUID) -> int:
        """Live employees reporting to this one. Blocks an archive."""
        stmt = (
            select(func.count())
            .select_from(Employee)
            .where(Employee.reporting_manager_id == employee_id, Employee.deleted_at.is_(None))
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def find_identifier_owner(
        self, field: str, value: str, *, exclude_employee_id: uuid.UUID | None = None
    ) -> Employee | None:
        """Find the employee already holding a statutory identifier.

        Compared upper-cased, matching the functional unique indexes on the
        table, so ``abcde1234f`` and ``ABCDE1234F`` are recognised as the same
        PAN rather than reaching the database as two rows.
        """
        if field not in IDENTIFIER_LABELS:
            raise ValueError(f"{field!r} is not a unique employee identifier")

        column = getattr(EmployeeIdentification, field)
        stmt = (
            select(Employee)
            .join(EmployeeIdentification, EmployeeIdentification.employee_id == Employee.id)
            .where(
                func.upper(column) == value.upper(),
                EmployeeIdentification.deleted_at.is_(None),
            )
        )
        if exclude_employee_id is not None:
            stmt = stmt.where(Employee.id != exclude_employee_id)
        return (await self.session.execute(stmt)).scalars().unique().first()

    # ------------------------------------------------------------------
    # Satellite records
    # ------------------------------------------------------------------
    async def get_address(self, employee_id: uuid.UUID, address_type: str) -> EmployeeAddress | None:
        stmt = select(EmployeeAddress).where(
            EmployeeAddress.employee_id == employee_id,
            EmployeeAddress.address_type == address_type,
            EmployeeAddress.deleted_at.is_(None),
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def get_bank_detail(self, employee_id: uuid.UUID) -> EmployeeBankDetail | None:
        stmt = select(EmployeeBankDetail).where(
            EmployeeBankDetail.employee_id == employee_id,
            EmployeeBankDetail.deleted_at.is_(None),
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def get_identification(self, employee_id: uuid.UUID) -> EmployeeIdentification | None:
        stmt = select(EmployeeIdentification).where(
            EmployeeIdentification.employee_id == employee_id,
            EmployeeIdentification.deleted_at.is_(None),
        )
        return (await self.session.execute(stmt)).scalars().first()

    # ------------------------------------------------------------------
    # Dashboard aggregates
    # ------------------------------------------------------------------
    async def count_live(self, *criteria: ColumnElement[bool]) -> int:
        stmt = select(func.count()).select_from(Employee).where(Employee.deleted_at.is_(None), *criteria)
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_archived(self) -> int:
        stmt = select(func.count()).select_from(Employee).where(Employee.deleted_at.is_not(None))
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_by_status(self) -> list[tuple[str, int]]:
        stmt = (
            select(Employee.employment_status, func.count())
            .where(Employee.deleted_at.is_(None))
            .group_by(Employee.employment_status)
        )
        return [(row[0], int(row[1])) for row in (await self.session.execute(stmt)).all()]

    async def count_by_work_mode(self) -> list[tuple[str, int]]:
        stmt = (
            select(Employee.work_mode, func.count())
            .where(Employee.deleted_at.is_(None), Employee.work_mode.is_not(None))
            .group_by(Employee.work_mode)
        )
        return [(row[0], int(row[1])) for row in (await self.session.execute(stmt)).all()]

    async def count_by_business_unit(self, *, limit: int = 10) -> list[tuple[str, int]]:
        """Headcount per business unit, largest first.

        An inner join, so employees with no business unit are excluded rather
        than collapsed into a nameless bar.
        """
        stmt = (
            select(BusinessUnit.name, func.count(Employee.id))
            .join(BusinessUnit, BusinessUnit.id == Employee.business_unit_id)
            .where(Employee.deleted_at.is_(None))
            .group_by(BusinessUnit.name)
            .order_by(func.count(Employee.id).desc(), BusinessUnit.name)
            .limit(limit)
        )
        return [(row[0], int(row[1])) for row in (await self.session.execute(stmt)).all()]

    async def count_joining_between(self, start: date, end: date) -> int:
        return await self.count_live(
            and_(Employee.joining_date >= start, Employee.joining_date <= end),
        )

    async def count_joined_by(self, on: date) -> int:
        """Live employees who had joined by a date -- the headcount trend.

        Counted from ``joining_date`` because it is the only leaving-or-arriving
        fact the schema records. It therefore over-counts historic months by
        anyone who has since left, which is stated on the analytics response
        rather than quietly smoothed over: the platform has no leaving date, and
        inventing one from ``employment_status`` would attribute every departure
        ever to the month the report happened to run.
        """
        return await self.count_live(Employee.joining_date <= on)

    async def count_employed(self) -> int:
        """Everyone currently on the books, whatever stage of the lifecycle."""
        return await self.count_live(
            Employee.employment_status.in_([status.value for status in EMPLOYED_STATUSES]),
        )

    async def count_with_status(self, status: EmploymentStatus) -> int:
        return await self.count_live(Employee.employment_status == status.value)


class EmploymentHistoryRepository(BaseRepository[EmployeeEmploymentHistory]):
    """Reads and appends to the employment history.

    There is deliberately no update or delete: the history is the record of what
    happened, and a correction is a new row rather than an edit to an old one.
    """

    model = EmployeeEmploymentHistory

    async def list_for_employee(self, employee_id: uuid.UUID) -> Sequence[EmployeeEmploymentHistory]:
        """One employee's history, most recent change first.

        Ordered by effective date and then by insertion time, so two changes
        effective on the same day still read in the order they were made.
        """
        stmt = (
            select(EmployeeEmploymentHistory)
            .where(
                EmployeeEmploymentHistory.employee_id == employee_id,
                EmployeeEmploymentHistory.deleted_at.is_(None),
            )
            .order_by(
                EmployeeEmploymentHistory.effective_date.desc(),
                EmployeeEmploymentHistory.created_at.desc(),
            )
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    async def count_for_employee(self, employee_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(EmployeeEmploymentHistory)
            .where(
                EmployeeEmploymentHistory.employee_id == employee_id,
                EmployeeEmploymentHistory.deleted_at.is_(None),
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())
