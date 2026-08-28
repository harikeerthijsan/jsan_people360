"""The permission catalogue.

Permissions are defined **in code, not in the database**, for the same reason
``ALLOWED_EXTENSIONS`` is a code constant: a permission that can be invented by
writing a row is a permission nothing checks. Every string an endpoint guards on
has to appear here, and the seeder reconciles the table to this list on every
migration -- so a typo in a guard fails loudly at import instead of silently
granting access to everyone.

Roles, by contrast, *are* data. The nine shipped roles are seeded and flagged
``is_system`` so they cannot be deleted out from under the application, but an
administrator may add as many custom roles as they like.

A permission says what a caller may do; it says nothing about *whose* record.
That second question is answered by one permission -- ``employees:view_all`` --
and by :mod:`app.services.scope_service`, which turns its absence into "yourself
and your direct reports". See :class:`PermissionAction.VIEW_ALL`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple


class PermissionAction(StrEnum):
    """What may be done, not what it is done to."""

    VIEW = "view"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    APPROVE = "approve"
    #: Distinct from ``create``: applying is asking, creating is deciding. An
    #: employee may apply for leave without being able to record it as taken.
    APPLY = "apply"
    #: Administrative action on anybody's record, outside any reporting line.
    #:
    #: Distinct from ``approve`` on purpose, and the distinction is the whole
    #: point of it. ``attendance:approve`` is a manager deciding a correction
    #: their own report asked for -- a step in a workflow somebody started.
    #: ``attendance:manage_all`` is an administrator amending a record directly,
    #: for somebody who does not report to them, with no request behind it. The
    #: second is a far bigger power than the first, and a seat that needs one
    #: routinely does not automatically need the other.
    MANAGE_ALL = "manage_all"
    #: Take a request through the step that belongs to HR.
    #:
    #: Distinct from ``approve`` because the two are different people's acts on
    #: the same record. A manager *approves* their report's resignation -- a
    #: decision about their team. HR then *processes* it: verifies the notice
    #: period, settles the last working day, and opens the offboarding case.
    #: Collapsing them would mean either a manager who can start an offboarding
    #: or an HR user who can decide a team's resignations, and neither is the
    #: separation this workflow is built around.
    PROCESS = "process"
    #: Administer a module's records end to end, as opposed to reading them.
    #:
    #: Used where the work is custodial rather than a decision -- running the
    #: offboarding checklist, managing exit interviews, issuing exit documents.
    #: Kept apart from ``update`` so that "may tick a checklist row assigned to
    #: me" and "may administer anybody's case" are separable grants.
    MANAGE = "manage"
    #: Custody operations on a physical thing. Four actions rather than one
    #: ``update``, because they are four different authorities over somebody
    #: else's possessions and an organization routinely splits them: the person
    #: who hands out laptops is rarely the person who writes one off.
    #:
    #: They are also the actions whose *absence* defines the HR seat here --
    #: HR sees what an employee holds and cannot give, take or move it.
    ASSIGN = "assign"
    RETURN = "return"
    TRANSFER = "transfer"
    MAINTAIN = "maintain"
    #: End of life, and separate from each other on purpose. Retiring takes a
    #: thing out of service and is reversible only by disposing of it; disposal
    #: is final and usually has a financial record behind it.
    RETIRE = "retire"
    DISPOSE = "dispose"
    #: Make something visible to everybody it is addressed to.
    #:
    #: Separate from ``create`` and ``update`` because drafting a notice and
    #: broadcasting it to the company are different acts with different
    #: consequences, and an organization routinely lets more people write than
    #: send. An unpublished announcement is nobody's business but its author's.
    PUBLISH = "publish"
    #: Configure the rules a module runs by, as opposed to acting under them.
    POLICY_MANAGE = "policy_manage"
    #: Correct an entitlement by hand. Always audited; see ``WorkforceService``.
    BALANCE_ADJUST = "balance_adjust"
    #: Decide a request that was addressed to somebody else. The escape hatch
    #: for a manager on holiday, not the normal path -- which is why it is a
    #: permission of its own rather than a consequence of ``approve``.
    OVERRIDE_APPROVAL = "override_approval"
    #: Read the append-only change history of a record, as distinct from
    #: reading its current state. Split from ``view`` where the past is more
    #: sensitive than the present: somebody's current salary answers "what do
    #: we pay them", while the history reveals every revision decision ever
    #: made about them.
    HISTORY_VIEW = "history_view"
    #: Configure the reusable templates a module assigns from — for payroll,
    #: the salary structures. Configuration rather than a decision about a
    #: person, which is why it is not implied by ``create`` or ``update``.
    STRUCTURE_MANAGE = "structure_manage"
    #: Configure the building blocks those templates are made of — for
    #: payroll, the earning and deduction components. Separate from
    #: ``structure_manage`` because an organization routinely lets more people
    #: arrange components into structures than invent new components.
    COMPONENT_MANAGE = "component_manage"
    #: See a direct report's records in a module where the reporting line
    #: grants nothing by default. Every other module narrows ``view`` to the
    #: caller's team; payroll inverts that — a manager sees *no* salary unless
    #: this is granted on purpose, because knowing what somebody is paid is
    #: not implied by approving their leave.
    TEAM_VIEW = "team_view"
    #: Read a module's global configuration, as distinct from its records.
    #: Split from ``view`` because the payroll register and the payroll
    #: rulebook are different sensitivities: an HR seat that reads salaries
    #: does not thereby get to read — or reason about — the pay rules.
    CONFIG_VIEW = "config_view"
    #: Change a module's global configuration. The heavyweight grant: every
    #: change is history-recorded with a reason and an effective date.
    CONFIG_MANAGE = "config_manage"
    #: Create and manage the module's processing periods.
    PERIOD_MANAGE = "period_manage"
    #: Configure the per-record rules a module applies — for payroll, how
    #: each leave type treats pay. Separate from ``config_manage`` so the
    #: rulebook and the schedule can be different people's jobs.
    RULE_MANAGE = "rule_manage"
    #: Read per-employee module settings (eligibility, overrides).
    EMPLOYEE_SETTINGS_VIEW = "employee_settings_view"
    #: Change per-employee module settings. Every change is audited with the
    #: previous and new values.
    EMPLOYEE_SETTINGS_UPDATE = "employee_settings_update"
    #: Read the prepared inputs a processing run will consume — for payroll,
    #: the per-employee attendance/leave/overtime summaries. Split from
    #: ``view`` because inputs reveal attendance patterns across the whole
    #: organization without revealing a single salary, and the two are
    #: different sensitivities in both directions.
    INPUTS_VIEW = "inputs_view"
    #: Build or refresh those inputs from the source modules. A snapshot act:
    #: every preparation is audited with what it covered.
    INPUTS_PREPARE = "inputs_prepare"
    #: Sign off an input that was flagged for review.
    INPUTS_REVIEW = "inputs_review"
    #: See processing runs and their organization-wide totals. The heaviest
    #: read in the module: a run's summary is every salary at once.
    RUNS_VIEW = "runs_view"
    #: Open a processing run for a period.
    RUN_CREATE = "run_create"
    #: Execute the calculation for a run that has none yet.
    CALCULATE = "calculate"
    #: Compute a run's numbers again, replacing what was there. A separate
    #: grant because re-running an already-produced payroll is a bigger act
    #: than producing it, and an organization may split the two.
    RECALCULATE = "recalculate"
    #: Read one employee's calculated payroll record with its line items.
    RECORD_VIEW = "record_view"
    #: See the review surfaces of a processing run — exceptions, adjustments,
    #: reconciliation, checklist and comments. Sight grants a voice in the
    #: comment thread and nothing else.
    REVIEW_VIEW = "review_view"
    #: Resolve or deliberately waive a flagged exception. The exception row
    #: survives with its resolution; nothing is deleted.
    EXCEPTION_RESOLVE = "exception_resolve"
    #: Add a controlled, additive adjustment to one employee's calculated
    #: result. The original calculation is never overwritten.
    ADJUSTMENT_CREATE = "adjustment_create"
    #: Cancel an adjustment. Cancelling marks, never deletes.
    ADJUSTMENT_UPDATE = "adjustment_update"
    #: Perform the review acts that move a run along: mark records reviewed,
    #: tick the checklist, and declare the review complete.
    REVIEW_COMPLETE = "review_complete"
    #: See the approval queue and one run's approval summary (Phase 6).
    #: Payroll reuses the platform's APPROVE and RETURN verbs for the
    #: decision itself — deliberately separate grants from every preparation
    #: and review permission, so an organization can keep the person who
    #: computed payroll and the person who approves it apart.
    APPROVAL_VIEW = "approval_view"
    #: Finalize an approved run: snapshot it, lock it, close its period.
    FINALIZE = "finalize"
    #: See finalized payroll history and the immutable final snapshots.
    FINALIZED_VIEW = "finalized_view"
    #: See payslips (Phase 7): the organization-wide list and any employee's
    #: payslip within scope. Employees always see their own through /me.
    PAYSLIP_VIEW = "payslip_view"
    #: Generate payslips from a finalized run, and regenerate a payslip's
    #: document file. Neither touches a payroll figure.
    PAYSLIP_GENERATE = "payslip_generate"
    #: Download another employee's payslip PDF.
    PAYSLIP_DOWNLOAD = "payslip_download"
    #: Payroll reports (Phase 8): see, and separately export.
    REPORT_VIEW = "report_view"
    REPORT_EXPORT = "report_export"
    #: Full & final settlement (Phase 8): each workflow act is its own grant.
    SETTLEMENT_VIEW = "settlement_view"
    SETTLEMENT_CREATE = "settlement_create"
    SETTLEMENT_UPDATE = "settlement_update"
    SETTLEMENT_APPROVE = "settlement_approve"
    SETTLEMENT_FINALIZE = "settlement_finalize"
    #: The one action that is about *scope* rather than about a verb.
    #:
    #: Every other permission answers "may you do this?". ``view_all`` answers
    #: "to whom?" -- and only the ``employees`` module carries it, because every
    #: record this system scopes (an attendance row, a leave request, a
    #: timesheet, a document) belongs to an employee. Holding
    #: ``employees:view_all`` means the reporting line stops narrowing what you
    #: can reach; not holding it means you see yourself and your direct reports.
    #:
    #: It grants nothing on its own. A manager still needs ``leave:approve`` to
    #: approve leave; this only decides whose leave is in front of them.
    VIEW_ALL = "view_all"


class PermissionGroup(StrEnum):
    """How permissions are grouped on the role screen."""

    HR = "hr"
    RECRUITMENT = "recruitment"
    ATTENDANCE = "attendance"
    PROJECTS = "projects"
    PERFORMANCE = "performance"
    PAYROLL = "payroll"
    ADMINISTRATION = "administration"


#: Actions whose label is not simply the verb title-cased. Without this,
#: ``view_all`` renders as "View_All employees" on the role screen.
ACTION_LABELS: dict[str, str] = {
    PermissionAction.VIEW_ALL.value: "View all",
    PermissionAction.MANAGE_ALL.value: "Administer all",
    PermissionAction.POLICY_MANAGE.value: "Manage policies for",
    PermissionAction.BALANCE_ADJUST.value: "Adjust balances for",
    PermissionAction.OVERRIDE_APPROVAL.value: "Override approvals for",
    PermissionAction.HISTORY_VIEW.value: "View history in",
    PermissionAction.STRUCTURE_MANAGE.value: "Manage structures in",
    PermissionAction.COMPONENT_MANAGE.value: "Manage components in",
    PermissionAction.TEAM_VIEW.value: "View their team's",
    PermissionAction.CONFIG_VIEW.value: "View configuration of",
    PermissionAction.CONFIG_MANAGE.value: "Manage configuration of",
    PermissionAction.PERIOD_MANAGE.value: "Manage periods in",
    PermissionAction.RULE_MANAGE.value: "Manage rules in",
    PermissionAction.EMPLOYEE_SETTINGS_VIEW.value: "View employee settings in",
    PermissionAction.EMPLOYEE_SETTINGS_UPDATE.value: "Update employee settings in",
    PermissionAction.INPUTS_VIEW.value: "View inputs in",
    PermissionAction.INPUTS_PREPARE.value: "Prepare inputs in",
    PermissionAction.INPUTS_REVIEW.value: "Review inputs in",
    PermissionAction.RUNS_VIEW.value: "View runs in",
    PermissionAction.RUN_CREATE.value: "Create runs in",
    PermissionAction.CALCULATE.value: "Calculate",
    PermissionAction.RECALCULATE.value: "Recalculate",
    PermissionAction.RECORD_VIEW.value: "View calculated records in",
    PermissionAction.REVIEW_VIEW.value: "View reviews in",
    PermissionAction.EXCEPTION_RESOLVE.value: "Resolve exceptions in",
    PermissionAction.ADJUSTMENT_CREATE.value: "Create adjustments in",
    PermissionAction.ADJUSTMENT_UPDATE.value: "Cancel adjustments in",
    PermissionAction.REVIEW_COMPLETE.value: "Complete reviews in",
    PermissionAction.APPROVAL_VIEW.value: "View approvals in",
    PermissionAction.FINALIZE.value: "Finalize",
    PermissionAction.FINALIZED_VIEW.value: "View finalized history in",
    PermissionAction.PAYSLIP_VIEW.value: "View payslips in",
    PermissionAction.PAYSLIP_GENERATE.value: "Generate payslips in",
    PermissionAction.PAYSLIP_DOWNLOAD.value: "Download payslips in",
    PermissionAction.REPORT_VIEW.value: "View reports in",
    PermissionAction.REPORT_EXPORT.value: "Export reports in",
    PermissionAction.SETTLEMENT_VIEW.value: "View settlements in",
    PermissionAction.SETTLEMENT_CREATE.value: "Create settlements in",
    PermissionAction.SETTLEMENT_UPDATE.value: "Update settlements in",
    PermissionAction.SETTLEMENT_APPROVE.value: "Approve settlements in",
    PermissionAction.SETTLEMENT_FINALIZE.value: "Finalize settlements in",
}


def action_label(action: PermissionAction | str, module_label: str) -> str:
    """The human label for one permission, as the role screen shows it."""
    verb = PermissionAction(action).value
    return f"{ACTION_LABELS.get(verb, verb.title())} {module_label.lower()}"


GROUP_LABELS: dict[PermissionGroup, str] = {
    PermissionGroup.HR: "HR",
    PermissionGroup.RECRUITMENT: "Recruitment",
    PermissionGroup.ATTENDANCE: "Attendance",
    PermissionGroup.PROJECTS: "Projects",
    PermissionGroup.PERFORMANCE: "Performance",
    PermissionGroup.PAYROLL: "Payroll",
    PermissionGroup.ADMINISTRATION: "Administration",
}


class Module(NamedTuple):
    """One protected area of the product."""

    key: str
    label: str
    group: PermissionGroup
    actions: tuple[PermissionAction, ...]
    description: str


A = PermissionAction

#: Every module the application protects. Adding one here and running the seeder
#: is the whole job of registering a new protected area.
MODULES: tuple[Module, ...] = (
    # -- HR ------------------------------------------------------------
    Module(
        "employees",
        "Employees",
        PermissionGroup.HR,
        (A.VIEW, A.VIEW_ALL, A.CREATE, A.UPDATE, A.DELETE, A.EXPORT),
        "Employee master records, lifecycle actions and the directory.",
    ),
    Module(
        "documents",
        "Documents",
        PermissionGroup.HR,
        (A.VIEW, A.CREATE, A.UPDATE, A.DELETE, A.EXPORT),
        "The document vault, its categories and its versions.",
    ),
    Module(
        "organization",
        "Organization",
        PermissionGroup.HR,
        (A.VIEW, A.CREATE, A.UPDATE, A.DELETE),
        "Business units, teams, designations, grades, locations, employment types.",
    ),
    Module(
        "onboarding",
        "Onboarding",
        PermissionGroup.HR,
        (A.VIEW, A.CREATE, A.UPDATE),
        "Preboarding profiles, onboarding cases and their tasks.",
    ),
    Module(
        "resignation",
        "Resignations",
        PermissionGroup.HR,
        # No create/update: an employee submits their own resignation through
        # /me, identity-guarded -- HR raising one on somebody's behalf is not
        # a thing this platform does.
        (A.VIEW, A.APPROVE, A.PROCESS),
        "Separation requests, their review chain and the notice period.",
    ),
    Module(
        "offboarding",
        "Offboarding",
        PermissionGroup.HR,
        # No create: a case is opened by processing a resignation, never
        # directly.
        (A.VIEW, A.UPDATE, A.MANAGE),
        "Offboarding cases, the clearance checklist, handover and settlement tracking.",
    ),
    Module(
        "exit_interview",
        "Exit interviews",
        PermissionGroup.HR,
        # View only: the employee submits their own through /me, and there is
        # nothing to administer about a submitted answer.
        (A.VIEW,),
        "Completed exit interviews and their responses.",
    ),
    Module(
        "exit_documents",
        "Exit documents",
        PermissionGroup.HR,
        # Manage only (generating letters): reading them rides on the case,
        # behind offboarding:view, and the employee's own are under /me.
        (A.MANAGE,),
        "Experience letters, relieving letters and service certificates.",
    ),
    # -- Recruitment ---------------------------------------------------
    Module(
        "requisitions",
        "Job requisitions",
        PermissionGroup.RECRUITMENT,
        (A.VIEW, A.CREATE, A.UPDATE, A.APPROVE),
        "Workforce planning requests and their approval chain.",
    ),
    Module(
        "recruitment",
        "Recruitment",
        PermissionGroup.RECRUITMENT,
        (A.VIEW, A.CREATE, A.UPDATE, A.APPROVE, A.EXPORT),
        "Job openings, candidates, the pipeline and talent pools.",
    ),
    Module(
        "interviews",
        "Interviews",
        PermissionGroup.RECRUITMENT,
        (A.VIEW, A.CREATE, A.UPDATE),
        "Scheduling, panels and structured feedback.",
    ),
    Module(
        "offers",
        "Offers",
        PermissionGroup.RECRUITMENT,
        (A.VIEW, A.CREATE, A.UPDATE, A.APPROVE),
        "Offer letters, their versions and the approval chain.",
    ),
    # -- Attendance ----------------------------------------------------
    Module(
        "attendance",
        "Attendance",
        PermissionGroup.ATTENDANCE,
        (A.VIEW, A.CREATE, A.APPROVE, A.MANAGE_ALL, A.EXPORT),
        "The daily register, check-in/out and correction requests.",
    ),
    Module(
        "leave",
        "Leave",
        PermissionGroup.ATTENDANCE,
        (A.VIEW, A.APPLY, A.APPROVE, A.OVERRIDE_APPROVAL, A.POLICY_MANAGE, A.BALANCE_ADJUST, A.EXPORT),
        "Leave balances, applications, decisions and the policies behind them.",
    ),
    Module(
        "timesheets",
        "Timesheets",
        PermissionGroup.ATTENDANCE,
        (A.VIEW, A.CREATE, A.APPROVE, A.MANAGE_ALL, A.EXPORT),
        "Weekly timesheets, submission and approval.",
    ),
    Module(
        "shifts",
        "Shifts & holidays",
        PermissionGroup.ATTENDANCE,
        (A.VIEW, A.CREATE, A.UPDATE),
        "Shift patterns, their assignment and holiday calendars.",
    ),
    # -- Projects ------------------------------------------------------
    Module(
        "projects",
        "Projects & clients",
        PermissionGroup.PROJECTS,
        (A.VIEW, A.CREATE, A.UPDATE, A.DELETE, A.EXPORT),
        "Clients, projects, membership, allocation and the bench.",
    ),
    # -- Performance ---------------------------------------------------
    Module(
        "performance",
        "Performance",
        PermissionGroup.PERFORMANCE,
        (A.VIEW, A.CREATE, A.UPDATE, A.APPROVE, A.EXPORT),
        "Cycles, goals, reviews, recognition and feedback.",
    ),
    # -- Payroll ---------------------------------------------------------
    Module(
        "payroll",
        "Payroll",
        PermissionGroup.PAYROLL,
        # Deliberately granted to NO seeded role below Administrator. Salary is
        # the record RBAC exists for: HR gets these ticked on purpose or not at
        # all, and a manager's reporting line grants nothing here — team_view
        # is the explicit, separate grant that opens their direct reports'
        # compensation and stops there.
        (
            A.VIEW,
            A.CREATE,
            A.UPDATE,
            A.HISTORY_VIEW,
            A.STRUCTURE_MANAGE,
            A.COMPONENT_MANAGE,
            A.TEAM_VIEW,
            A.CONFIG_VIEW,
            A.CONFIG_MANAGE,
            A.PERIOD_MANAGE,
            A.RULE_MANAGE,
            A.EMPLOYEE_SETTINGS_VIEW,
            A.EMPLOYEE_SETTINGS_UPDATE,
            A.INPUTS_VIEW,
            A.INPUTS_PREPARE,
            A.INPUTS_REVIEW,
            A.RUNS_VIEW,
            A.RUN_CREATE,
            A.CALCULATE,
            A.RECALCULATE,
            A.RECORD_VIEW,
            A.REVIEW_VIEW,
            A.EXCEPTION_RESOLVE,
            A.ADJUSTMENT_CREATE,
            A.ADJUSTMENT_UPDATE,
            A.REVIEW_COMPLETE,
            A.APPROVAL_VIEW,
            A.APPROVE,
            A.RETURN,
            A.FINALIZE,
            A.FINALIZED_VIEW,
            A.PAYSLIP_VIEW,
            A.PAYSLIP_GENERATE,
            A.PAYSLIP_DOWNLOAD,
            A.REPORT_VIEW,
            A.REPORT_EXPORT,
            A.SETTLEMENT_VIEW,
            A.SETTLEMENT_CREATE,
            A.SETTLEMENT_UPDATE,
            A.SETTLEMENT_APPROVE,
            A.SETTLEMENT_FINALIZE,
        ),
        "Salary structures, compensation components, employee compensation and payroll configuration.",
    ),
    # -- Administration ------------------------------------------------
    Module(
        "helpdesk",
        "Helpdesk",
        PermissionGroup.HR,
        (A.VIEW, A.CREATE, A.UPDATE, A.ASSIGN, A.MANAGE),
        "Employee requests, their queues, assignment and resolution.",
    ),
    Module(
        "announcements",
        "Announcements",
        PermissionGroup.HR,
        (A.VIEW, A.CREATE, A.UPDATE, A.PUBLISH, A.DELETE),
        "Company notices, their audience and their acknowledgements.",
    ),
    Module(
        "assets",
        "Assets",
        PermissionGroup.ADMINISTRATION,
        (
            A.VIEW,
            A.CREATE,
            A.UPDATE,
            A.ASSIGN,
            A.RETURN,
            A.TRANSFER,
            A.MAINTAIN,
            A.RETIRE,
            A.DISPOSE,
            A.MANAGE,
            A.EXPORT,
        ),
        "The asset register, its categories, custody and maintenance.",
    ),
    Module(
        "users",
        "Users",
        PermissionGroup.ADMINISTRATION,
        (A.VIEW, A.CREATE, A.UPDATE, A.DELETE),
        "Login accounts, their status and password resets.",
    ),
    Module(
        "roles",
        "Roles & permissions",
        PermissionGroup.ADMINISTRATION,
        (A.VIEW, A.CREATE, A.UPDATE, A.DELETE),
        "Roles, what they grant, and who holds them.",
    ),
    Module(
        "reports",
        "Reports",
        PermissionGroup.ADMINISTRATION,
        (A.VIEW, A.EXPORT),
        "Cross-module reporting and its exports.",
    ),
    Module(
        "settings",
        "System settings",
        PermissionGroup.ADMINISTRATION,
        (A.VIEW, A.UPDATE),
        "Organization profile, policies and application configuration.",
    ),
    Module(
        "audit",
        "Audit trail",
        PermissionGroup.ADMINISTRATION,
        (A.VIEW, A.EXPORT),
        "Who did what, when, and from where.",
    ),
)

MODULES_BY_KEY: dict[str, Module] = {module.key: module for module in MODULES}


def code(module: str, action: PermissionAction | str) -> str:
    """The wire format for a permission: ``employees:view``.

    One string rather than a pair because it is what a route guard, a JWT claim
    and a React prop all have to carry, and three different shapes for the same
    idea is three places to get it wrong.
    """
    return f"{module}:{PermissionAction(action).value}"


def all_permission_codes() -> tuple[str, ...]:
    """Every permission the application recognises, in registry order."""
    return tuple(code(module.key, action) for module in MODULES for action in module.actions)


ALL_PERMISSIONS: frozenset[str] = frozenset(all_permission_codes())


def is_known(permission: str) -> bool:
    return permission in ALL_PERMISSIONS


def assert_known(*permissions: str) -> None:
    """Fail at import time rather than at request time.

    A guard naming a permission that does not exist would otherwise be
    unsatisfiable, and an unsatisfiable guard reads exactly like a locked-down
    endpoint until somebody who should have access is refused.
    """
    unknown = sorted(set(permissions) - ALL_PERMISSIONS)
    if unknown:
        raise ValueError(f"Unknown permission(s): {', '.join(unknown)}")


# ----------------------------------------------------------------------
# The roles that ship with the product
# ----------------------------------------------------------------------
def _every_action(*modules: str) -> tuple[str, ...]:
    return tuple(code(key, action) for key in modules for action in MODULES_BY_KEY[key].actions)


def _view_only(*modules: str) -> tuple[str, ...]:
    return tuple(code(key, A.VIEW) for key in modules)


def _every_action_except(module: str, *withheld: PermissionAction) -> tuple[str, ...]:
    """Every action on a module apart from the named ones.

    Written as a subtraction rather than a list of what *is* granted, because
    the interesting fact about these seats is what was deliberately kept back.
    It also means a new ordinary action reaches the role automatically while a
    new administrative one has to be granted on purpose -- which is the right
    default in both directions, and the reason ``hr_admin`` below no longer
    uses :func:`_every_action` for the three workforce modules.
    """
    excluded = set(withheld)
    return tuple(code(module, action) for action in MODULES_BY_KEY[module].actions if action not in excluded)


class SystemRole(NamedTuple):
    key: str
    name: str
    description: str
    permissions: tuple[str, ...]


#: What a person in each seat actually needs. Deliberately not a ladder: a
#: Recruiter is not "a Manager with less", and giving them a prefix of the same
#: list would hand them attendance approval they have no business holding.
#:
#: Five seats sit above the reporting line and three sit inside it, and the
#: difference between HR and Administrator is worth stating plainly because they
#: are routinely confused: **HR is not an administrator with a different job
#: title.** HR Admin runs the people processes -- hiring, records, leave policy,
#: documents, reporting -- and holds nothing that configures the application.
#: Roles, permissions, settings and audit administration are the Administrator's,
#: and so are the three workforce actions that act on somebody's record with no
#: request behind them. Nothing anywhere checks for the *name* "HR"; every one of
#: those boundaries is a permission that is either granted or not.
#:
#: Administrator and Super Admin differ in kind rather than in degree. Both hold
#: the whole catalogue, but Super Admin also carries ``users.is_superuser``,
#: which bypasses the permission check itself -- so an Administrator can be
#: narrowed by editing their role, and a Super Admin cannot. That is what makes
#: Super Admin the account that fixes a lock-out and Administrator the account
#: that does the day-to-day.
#:
#: ``employees:view_all`` is the line between organization-wide and team-scoped.
#: HR and Super Admin hold it because running HR means seeing everybody.
#: Recruiter and Project Manager hold it because their work is cross-org by
#: nature -- a panel is drawn from the whole company, and so is a project team --
#: and scoping them to a reporting line they usually do not have would leave the
#: panel and allocation pickers empty. Manager and Team Lead deliberately do not
#: hold it: they approve for the people who report to them, and nobody else.
SYSTEM_ROLES: tuple[SystemRole, ...] = (
    SystemRole(
        "super_admin",
        "Super Admin",
        "Unrestricted access, including roles, settings and the audit trail.",
        all_permission_codes(),
    ),
    SystemRole(
        "admin",
        "Administrator",
        "Full application access: people, configuration, roles, settings and the audit trail.",
        all_permission_codes(),
    ),
    SystemRole(
        "hr_admin",
        "HR Admin",
        "Runs HR end to end: people, documents, attendance, leave and reporting.",
        _every_action(
            "employees",
            "documents",
            "organization",
            "onboarding",
            "shifts",
            "requisitions",
            "recruitment",
            "interviews",
            "offers",
            "performance",
            "reports",
        )
        # The three workforce modules are subtractions rather than "everything",
        # because each has grown an administrative action that HR is not
        # supposed to hold by default. Amending somebody's attendance directly,
        # deciding a request addressed to their manager, and rewriting a balance
        # by hand are administrator powers; running HR is not a reason to have
        # them, and an organization that wants HR to have one ticks it on the
        # roles screen. Managing the leave *policies* is the exception: deciding
        # how much casual leave the company gives is HR's job by definition.
        + _every_action_except("attendance", A.MANAGE_ALL)
        + _every_action_except("leave", A.OVERRIDE_APPROVAL, A.BALANCE_ADJUST)
        + _every_action_except("timesheets", A.MANAGE_ALL)
        # Separation, on the same subtraction principle. HR runs the process --
        # verifying notice, settling the last working day, driving the checklist,
        # issuing the letters -- and `approve` is withheld because approving a
        # resignation is the *manager's* decision about their own team. HR's step
        # is `process`, which is a different act on the same record and is why
        # the two actions exist separately.
        + _every_action_except("resignation", A.APPROVE)
        + _every_action("offboarding", "exit_interview", "exit_documents")
        # The helpdesk is HR's to run: they answer the requests employees raise
        # about leave, records and pay. `manage` is included because
        # administering the categories -- what queues exist, who they route to --
        # is part of running a desk rather than a separate administrative power.
        + _every_action("helpdesk")
        # Announcements likewise: HR writes and sends them. `delete` is withheld,
        # because a notice that went out to the company is a thing that was said,
        # and taking it out of the record is an administrator's call. Archiving
        # it -- which is `update` -- takes it off the screen.
        + _every_action_except("announcements", A.DELETE)
        # Assets are Admin's, not HR's. HR needs to *see* what a leaver holds to
        # run a clearance, and needs no power at all to give, take, move, repair
        # or write off company property. `assets:view` is the whole grant, and
        # the eight actions withheld here are the substance of "do not give HR
        # full asset administration".
        + (code("assets", A.VIEW),)
        # Read-only on purpose. HR reads the trail to answer "what happened to
        # this record"; administering it -- and exporting it -- is not theirs.
        + _view_only("projects", "users", "audit"),
    ),
    SystemRole(
        "hr_executive",
        "HR Executive",
        "Day-to-day HR work without the ability to delete records or change configuration.",
        (
            code("employees", A.VIEW),
            code("employees", A.VIEW_ALL),
            code("employees", A.CREATE),
            code("employees", A.UPDATE),
            code("employees", A.EXPORT),
            code("documents", A.VIEW),
            code("documents", A.CREATE),
            code("documents", A.UPDATE),
            code("onboarding", A.VIEW),
            code("onboarding", A.CREATE),
            code("onboarding", A.UPDATE),
            code("attendance", A.VIEW),
            code("attendance", A.CREATE),
            code("attendance", A.EXPORT),
            code("leave", A.VIEW),
            code("leave", A.APPLY),
            code("leave", A.EXPORT),
            code("timesheets", A.VIEW),
            code("shifts", A.VIEW),
            code("performance", A.VIEW),
            code("reports", A.VIEW),
            code("reports", A.EXPORT),
            # Separation: sees it, and works the checklist rows that fall to HR.
            # `resignation:process` is withheld -- settling somebody's last
            # working day is the HR Admin's call, not day-to-day HR work -- and
            # so is issuing the letters, which are what the person leaves with.
            code("resignation", A.VIEW),
            code("offboarding", A.VIEW),
            code("offboarding", A.UPDATE),
            code("exit_interview", A.VIEW),
            # No exit_documents grant: reading issued letters rides on the
            # case (offboarding:view), and generating them is withheld above.
            code("assets", A.VIEW),
            # Answers tickets; does not configure the desk.
            code("helpdesk", A.VIEW),
            code("helpdesk", A.UPDATE),
            code("helpdesk", A.ASSIGN),
            # Drafts announcements; publishing one is HR Admin's.
            code("announcements", A.VIEW),
            code("announcements", A.CREATE),
            *_view_only("organization", "recruitment", "interviews", "offers", "requisitions"),
        ),
    ),
    SystemRole(
        "recruiter",
        "Recruiter",
        "Owns the hiring pipeline; sees nothing of payroll, attendance or performance.",
        (
            *_every_action("recruitment", "interviews"),
            code("offers", A.VIEW),
            code("offers", A.CREATE),
            code("offers", A.UPDATE),
            code("requisitions", A.VIEW),
            code("onboarding", A.VIEW),
            code("onboarding", A.CREATE),
            code("documents", A.VIEW),
            code("documents", A.CREATE),
            code("reports", A.VIEW),
            code("reports", A.EXPORT),
            # Interview panels are drawn from the whole company.
            code("employees", A.VIEW_ALL),
            *_view_only("employees", "organization"),
        ),
    ),
    SystemRole(
        "project_manager",
        "Project Manager",
        "Runs delivery: projects, allocation, timesheet approval and their team's performance.",
        (
            *_every_action("projects"),
            code("timesheets", A.VIEW),
            code("timesheets", A.CREATE),
            code("timesheets", A.APPROVE),
            code("timesheets", A.EXPORT),
            code("attendance", A.VIEW),
            code("attendance", A.EXPORT),
            code("leave", A.VIEW),
            code("leave", A.APPLY),
            code("leave", A.APPROVE),
            code("performance", A.VIEW),
            code("performance", A.CREATE),
            code("performance", A.UPDATE),
            code("requisitions", A.VIEW),
            code("requisitions", A.CREATE),
            code("interviews", A.VIEW),
            code("interviews", A.UPDATE),
            code("reports", A.VIEW),
            code("reports", A.EXPORT),
            # A project team is not a reporting line: the people a PM allocates
            # and whose timesheets they approve rarely report to them.
            code("employees", A.VIEW_ALL),
            *_view_only("employees", "organization", "shifts"),
        ),
    ),
    SystemRole(
        "team_lead",
        "Team Lead",
        "Approves their team's day-to-day work without changing any master data.",
        (
            code("attendance", A.VIEW),
            code("attendance", A.CREATE),
            code("attendance", A.APPROVE),
            code("leave", A.VIEW),
            code("leave", A.APPLY),
            code("leave", A.APPROVE),
            code("timesheets", A.VIEW),
            code("timesheets", A.CREATE),
            code("timesheets", A.APPROVE),
            code("performance", A.VIEW),
            code("performance", A.CREATE),
            code("performance", A.UPDATE),
            code("interviews", A.VIEW),
            code("interviews", A.UPDATE),
            code("reports", A.VIEW),
            # Sees a departing team member and records the handover; does not
            # decide the resignation. A Team Lead approves the day-to-day --
            # attendance, leave, a timesheet -- and a separation is not that.
            code("resignation", A.VIEW),
            code("offboarding", A.VIEW),
            code("offboarding", A.UPDATE),
            code("assets", A.VIEW),
            code("helpdesk", A.VIEW),
            code("announcements", A.VIEW),
            *_view_only("employees", "projects", "shifts", "organization"),
        ),
    ),
    SystemRole(
        "manager",
        "Manager",
        "Approves for their reports and contributes to hiring and performance.",
        (
            code("attendance", A.VIEW),
            code("attendance", A.CREATE),
            code("attendance", A.APPROVE),
            code("attendance", A.EXPORT),
            code("leave", A.VIEW),
            code("leave", A.APPLY),
            code("leave", A.APPROVE),
            code("leave", A.EXPORT),
            code("timesheets", A.VIEW),
            code("timesheets", A.CREATE),
            code("timesheets", A.APPROVE),
            code("performance", A.VIEW),
            code("performance", A.CREATE),
            code("performance", A.UPDATE),
            code("performance", A.APPROVE),
            code("requisitions", A.VIEW),
            code("requisitions", A.CREATE),
            code("requisitions", A.APPROVE),
            code("interviews", A.VIEW),
            code("interviews", A.UPDATE),
            code("offers", A.VIEW),
            code("offers", A.APPROVE),
            code("reports", A.VIEW),
            code("reports", A.EXPORT),
            # A resignation from a direct report is the manager's to decide, and
            # the handover is theirs to record. Scope still applies: `approve`
            # reaches the people who report to them and stops there. They get no
            # `resignation:process` -- opening an offboarding case, settling a
            # last working day and issuing letters are HR's, on purpose.
            code("resignation", A.VIEW),
            code("resignation", A.APPROVE),
            code("offboarding", A.VIEW),
            code("offboarding", A.UPDATE),
            # Sees what their reports hold, and cannot move any of it. Scoped to
            # the reporting line like every other manager read.
            code("assets", A.VIEW),
            # Sees requests raised by their reports -- a manager whose team has
            # three open payroll tickets should know -- and answers none of them.
            code("helpdesk", A.VIEW),
            code("announcements", A.VIEW),
            *_view_only("employees", "projects", "shifts", "organization", "documents"),
        ),
    ),
    SystemRole(
        "employee",
        "Employee",
        "Their own attendance, leave, timesheets and goals. The floor every account stands on.",
        (
            code("attendance", A.VIEW),
            code("attendance", A.CREATE),
            code("leave", A.VIEW),
            code("leave", A.APPLY),
            code("timesheets", A.VIEW),
            code("timesheets", A.CREATE),
            code("performance", A.VIEW),
            code("performance", A.UPDATE),
            code("documents", A.VIEW),
            code("shifts", A.VIEW),
        ),
    ),
)

SYSTEM_ROLES_BY_KEY: dict[str, SystemRole] = {role.key: role for role in SYSTEM_ROLES}

#: Assigned to a new account when nothing else is specified. Not a superuser and
#: not nothing: an account with no role at all cannot use the product, and the
#: temptation to fix that quickly is what produces a second superuser.
DEFAULT_ROLE_KEY = "employee"

# Every seeded role must reference real permissions. Checked at import so a bad
# edit to this file cannot reach a migration.
for _role in SYSTEM_ROLES:
    assert_known(*_role.permissions)
