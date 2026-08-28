"""Whose records a signed-in user may reach.

:mod:`app.services.authorization_service` answers "may this user do that?".
This answers the other half of the question -- "to whom?" -- and the two are
deliberately separate objects, because they fail differently: a missing
permission is a role problem an administrator fixes on the roles screen, and a
scope violation is a reporting-line problem that fixes itself when the org chart
changes.

The rule is one sentence: **a caller sees themselves and their direct reports,
unless they hold ``employees:view_all``, in which case they see everybody.**

Two consequences are worth stating plainly, because both have been the source of
real holes in this codebase:

* **Scope is not a permission check and does not replace one.** A manager still
  needs ``leave:approve`` to reach the decision endpoint at all. Scope only
  narrows the rows once they are through the door. A route that applies scope
  without a permission guard is unguarded.
* **Scope is resolved once per request and passed down.** It is not re-derived
  inside repositories, because a repository that quietly filters by the current
  user is a repository whose results depend on invisible state -- and the export,
  the dashboard and the notification fan-out all legitimately need the unfiltered
  query.

Employees are matched by their *employee* id; documents are also matched by the
*user* id behind that employee, since the vault files things against both.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDeniedError
from app.core.permissions import PermissionAction, code
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository
from app.services.authorization_service import AuthorizationService

#: The permission that lifts the reporting-line restriction entirely.
ORG_WIDE_PERMISSION: str = code("employees", PermissionAction.VIEW_ALL)


@dataclass(frozen=True)
class EmployeeScope:
    """Which employees' records one caller may reach, for one request.

    Frozen, and carrying its answers rather than a session: once resolved it is
    a plain value that a service can consult without another round trip, and a
    unit test can construct without a database.
    """

    #: True for a superuser or a holder of ``employees:view_all``. When set, the
    #: id collections below are empty and must not be consulted.
    unrestricted: bool

    #: The caller's own employee id, when they have an employee record at all.
    #: A user account with no employee record -- an IT administrator, an
    #: integration account -- is legitimate, and scopes to nothing.
    self_employee_id: uuid.UUID | None = None

    #: Employees who report directly to the caller.
    direct_report_ids: frozenset[uuid.UUID] = frozenset()

    #: Login accounts belonging to the employees in scope, for document owners
    #: filed under ``user`` rather than ``employee``.
    user_ids: frozenset[uuid.UUID] = frozenset()

    @property
    def employee_ids(self) -> frozenset[uuid.UUID]:
        """Every employee id in scope: the caller plus their direct reports."""
        own = frozenset({self.self_employee_id} if self.self_employee_id else ())
        return own | self.direct_report_ids

    @property
    def visible_employee_ids(self) -> frozenset[uuid.UUID] | None:
        """The filter to apply to a list query, or ``None`` for no filter.

        ``None`` rather than "every id in the company": materialising the whole
        directory to build an ``IN`` clause would turn every HR list page into a
        second full-table read, and would silently start truncating at whatever
        the driver's parameter limit is.
        """
        return None if self.unrestricted else self.employee_ids

    @property
    def visible_user_ids(self) -> frozenset[uuid.UUID] | None:
        return None if self.unrestricted else self.user_ids

    @property
    def manages_anyone(self) -> bool:
        return bool(self.direct_report_ids)

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------
    def allows(self, employee_id: uuid.UUID) -> bool:
        return self.unrestricted or employee_id in self.employee_ids

    def is_self(self, employee_id: uuid.UUID) -> bool:
        return self.self_employee_id is not None and self.self_employee_id == employee_id

    def allows_user(self, user_id: uuid.UUID) -> bool:
        return self.unrestricted or user_id in self.user_ids

    def assert_allows(self, employee_id: uuid.UUID, *, field: str = "employee_id") -> None:
        """Refuse a record outside the reporting line.

        Deliberately a 403 and not a 404. Hiding the existence of a colleague's
        leave request buys nothing in an internal HR system where the directory
        is readable anyway, and it costs the person on the other end of the
        support call any chance of understanding what happened.
        """
        if self.allows(employee_id):
            return
        raise PermissionDeniedError(
            "You can only see records for yourself and the people who report to you.",
            details=[{"code": "outside_your_team", "message": field}],
        )

    def assert_allows_user(self, user_id: uuid.UUID, *, field: str = "owner_id") -> None:
        if self.allows_user(user_id):
            return
        raise PermissionDeniedError(
            "You can only see records for yourself and the people who report to you.",
            details=[{"code": "outside_your_team", "message": field}],
        )

    @classmethod
    def organization_wide(cls) -> EmployeeScope:
        """The scope a superuser and every HR role gets.

        Also the default for a service called outside a request -- the seeder,
        an export job, the notification fan-out -- none of which act on behalf of
        a person whose reporting line means anything.
        """
        return cls(unrestricted=True)

    @classmethod
    def just_self(cls, employee_id: uuid.UUID, user_id: uuid.UUID | None = None) -> EmployeeScope:
        """One person and nobody else -- the scope employee self-service runs in.

        Deliberately narrower than :meth:`TeamScopeService.for_user`, which also
        admits direct reports. A ``/me`` endpoint is answering "what is *mine*",
        and a manager calling one should get their own week, not a set that
        happens to include their team's. Their team is reached through the
        approval screens, which are permission-guarded for that purpose.

        It is also what makes a superuser's ``/me`` behave like everybody
        else's: unrestricted scope would otherwise let the shared services hand
        back the whole company through a personal endpoint.
        """
        return cls(
            unrestricted=False,
            self_employee_id=employee_id,
            direct_report_ids=frozenset(),
            user_ids=frozenset({user_id} if user_id else ()),
        )

    @classmethod
    def of_direct_reports(
        cls,
        report_ids: Collection[uuid.UUID],
        user_ids: Collection[uuid.UUID] = (),
    ) -> EmployeeScope:
        """The reporting line and nothing else -- the scope a manager screen runs in.

        Two things distinguish it from :meth:`TeamScopeService.for_user`, and
        both are deliberate.

        **The caller is not in it.** ``self_employee_id`` is left unset, so
        ``allows(manager.id)`` is false. A manager screen is about the team, and
        the same property is what stops a manager approving their own leave
        through it: the request is outside the scope the decision runs in, so it
        is refused by the check that was already there rather than by a rule
        somebody has to remember to write.

        **It ignores ``employees:view_all``.** An HR administrator's ordinary
        scope is unrestricted, and passing that to a team screen would put the
        whole company on it. This narrows to the reporting line for everybody,
        including a superuser -- their organization-wide access is unchanged on
        the HR screens, which is where it belongs.

        An empty set is not the same as no filter: a manager with no reports
        sees nothing, which is what ``visible_employee_ids`` returning an empty
        frozenset means downstream.
        """
        return cls(
            unrestricted=False,
            self_employee_id=None,
            direct_report_ids=frozenset(report_ids),
            user_ids=frozenset(user_ids),
        )


def visible_employee_ids(scope: EmployeeScope | None) -> frozenset[uuid.UUID] | None:
    """The employee-id filter for a list query, or ``None`` for no filter.

    Exists so every service spells "no scope supplied means organization-wide"
    the same way. Services take ``scope`` as an optional keyword precisely so
    that the callers with no reporting line -- the seeder, the dashboards, a
    background job -- keep working unchanged; that default has to be written
    once, not once per call site.
    """
    return None if scope is None else scope.visible_employee_ids


def visible_user_ids(scope: EmployeeScope | None) -> frozenset[uuid.UUID] | None:
    """The user-id filter for a list query, or ``None`` for no filter."""
    return None if scope is None else scope.visible_user_ids


class TeamScopeService:
    """Resolves the :class:`EmployeeScope` for a user."""

    def __init__(self, session: AsyncSession, authorization: AuthorizationService) -> None:
        self._employees = EmployeeRepository(session)
        self._authorization = authorization

    async def for_user(self, user: User) -> EmployeeScope:
        if user.is_superuser:
            return EmployeeScope.organization_wide()

        held = await self._authorization.permissions_for(user)
        if ORG_WIDE_PERMISSION in held:
            return EmployeeScope.organization_wide()

        own = await self._employees.get_by(user_id=user.id)
        if own is None:
            # No employee record, no reporting line, and no org-wide permission:
            # this account can reach nobody's records. It can still use every
            # endpoint that is not employee-scoped -- the org masters, the
            # recruitment pipeline -- which is what such an account is for.
            return EmployeeScope(unrestricted=False)

        reports = await self._employees.direct_report_ids(own.id)
        employee_ids = reports | {own.id}
        return EmployeeScope(
            unrestricted=False,
            self_employee_id=own.id,
            direct_report_ids=frozenset(reports),
            user_ids=frozenset(await self._employees.user_ids_for(employee_ids)),
        )

    async def direct_reports_of(self, user: User) -> EmployeeScope:
        """The manager screens' scope: whoever reports to this user, and nobody else.

        Reuses the one team-scoping query the platform has --
        :meth:`EmployeeRepository.direct_report_ids` -- so "who reports to me"
        has a single definition. What differs from :meth:`for_user` is only
        which people the resulting scope admits; see
        :meth:`EmployeeScope.of_direct_reports` for why the caller and
        ``employees:view_all`` are both left out of it.

        An account with no employee record has no reporting line and therefore
        no team, which is a legitimate answer rather than an error: an
        integration account can hold ``employees:view`` and still manage nobody.
        """
        own = await self._employees.get_by(user_id=user.id)
        if own is None:
            return EmployeeScope.of_direct_reports(frozenset())

        reports = await self._employees.direct_report_ids(own.id)
        return EmployeeScope.of_direct_reports(reports, await self._employees.user_ids_for(reports))
