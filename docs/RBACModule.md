# Role-Based Access Control

Until this module landed, every authenticated account could read everything —
salary, CTC, bank details, Aadhaar and PAN included. RBAC closes that, and does
it in a way that a new endpoint cannot quietly reopen.

## The shape of it

**Permissions are code, roles are data.** The catalogue lives in
`app/core/permissions.py` and the `permissions` table mirrors it. A permission
that can be invented by writing a database row is a permission nothing checks —
the same reason `ALLOWED_EXTENSIONS` is a constant rather than a setting. Roles,
by contrast, are genuinely a company's decision, so they are rows: eight ship
with the product, and an administrator may add as many more as they like.

**A user holds roles, not permissions.** There is no user-permission table. A
one-off grant is invisible on the roles screen, survives an audit unnoticed, and
is how an access model rots. If somebody needs a different set, that set is a
role.

**Effective permissions are the union of every active role.** No deny lists, no
precedence. Denies that override grants read well in a design document and are
impossible to reason about when somebody cannot approve leave and nobody can say
why. Deactivating a role revokes it immediately, for everyone holding it — that
is the fastest lever an administrator has and it would be worthless if it only
applied to new grants.

**`is_superuser` short-circuits everything.** It predates RBAC and it is how the
first account bootstraps. Removing it would mean a bad grant could lock every
administrator out of the screen that fixes grants.

## The catalogue

19 modules, 73 permissions, grouped six ways for the role editor: HR,
Recruitment, Attendance, Projects, Performance, Administration.

Actions are per module rather than universal, because they are not the same
question. `leave` has `apply` as well as `approve` — applying is asking,
approving is deciding, and an employee does one without the other. `attendance`
has no `delete`, because a day that happened cannot be made not to have
happened.

A permission is written `module:action` — one string, because a route guard, a
session payload and a React prop all have to carry it, and three shapes for one
idea is three places to get it wrong.

## The eight shipped roles

| Role | Holds | Shape of it |
| --- | --- | --- |
| Super Admin | 73 | Everything, including roles and the audit trail |
| HR Admin | 59 | HR end to end; read-only on projects, users and audit |
| HR Executive | 27 | Day-to-day HR without deletion or configuration |
| Manager | 29 | Approves for **their direct reports**; contributes to hiring |
| Project Manager | 27 | Delivery, allocation and timesheet approval |
| Recruiter | 21 | The hiring pipeline; nothing of payroll or performance |
| Team Lead | 19 | Approves **their team's** work, changes no master data |
| Employee | 10 | Their own attendance, leave, timesheets and goals |

The reach of each of these is narrowed by reporting line unless the role holds
`employees:view_all` — see [Team scoping](#team-scoping--whose-records-not-just-which-endpoint).

Deliberately **not** a ladder. A Recruiter is not "a Manager with less" — giving
them a prefix of the same list would hand them attendance approval they have no
business holding.

System roles are marked `is_system`. Their permissions can be edited freely —
what "HR Executive" means is a policy decision — but they cannot be renamed,
deactivated or deleted, because the seeder reconciles them on every deployment
and a renamed one would reappear beside its replacement.

## Enforcement

A route declares what it needs:

```python
@router.get("/employees", dependencies=[require("employees:view")])
```

`require()` validates the permission string **at import time**. A guard naming a
permission that does not exist is unsatisfiable, and an unsatisfiable guard is
indistinguishable from a correctly locked endpoint until somebody who should
have access is refused.

**246 of 260 endpoints are guarded.** The other 14 are listed in
`tests/integration/test_rbac.py` with a reason each: health probes, the auth
endpoints, `/users/me`, your own notification inbox, and `/organizations/primary`
(the shell renders the company name for everyone).

The master-router factory takes `permission_module` as a *required* argument, so
a new master built without naming one fails at import rather than shipping
unguarded.

### The test that outlives the retrofit

Sweeping 246 endpoints once was the easy part. The risk that lasts is a *new*
endpoint merged without a guard, which looks exactly like a working endpoint
until someone reads what they should not.

So `require()` tags its guard, and `TestGuardCoverage` walks the whole route tree
asserting every endpoint is either guarded or on the exceptions list. Adding an
unguarded endpoint now fails the suite.

## Team scoping — whose records, not just which endpoint

A permission answers "may you do this?". It says nothing about *whose* row, which
is how a Manager holding `leave:approve` could approve for the entire company by
changing an id in the URL. Team scoping is the second half of the question.

**The rule, in one sentence:** a caller reaches themselves and their direct
reports, unless they hold **`employees:view_all`**, in which case they reach
everybody.

`employees:view_all` is the 73rd permission and the only one that describes
scope rather than a verb. It lives on the `employees` module because every
record this system narrows — an attendance row, a leave request, a timesheet, a
document — belongs to an employee, so there is one question to answer, not five.
It grants nothing by itself: a Manager still needs `leave:approve` to reach the
decision endpoint, and this only decides whose leave is in front of them.

| Role | Reach |
| --- | --- |
| Super Admin, HR Admin, HR Executive | Organization-wide |
| Recruiter, Project Manager | Organization-wide — their work crosses the org chart, and an interview panel or a project team is not a reporting line |
| Manager, Team Lead | Themselves and their direct reports |
| Employee | Themselves |

Roles are data, so any of this is editable: revoking `employees:view_all` from
Recruiter narrows them, and granting it to a custom role widens it.

### Where it applies

Employee profile and directory, attendance, leave, timesheets, and employee
documents. Company policies and candidate paperwork are **not** narrowed — they
have no reporting line, and hiding the handbook from everybody who is not their
own manager would be a bug rather than a control.

Three enforcement points, each where the information actually exists:

- **`require_team_scope()` / `require_self_or(...)`** — route guards for
  `/{employee_id}` paths, where the subject is in the URL. `require_self_or`
  keeps its escalating-permission gate: without it, an employee who happens to
  have reports but holds only the base Employee role would *gain* access.
- **The service layer** — for records keyed by their own id. Whose leave request
  `/leave/{request_id}/decide` refers to is only knowable once the row is read,
  so the check happens after the load and *before* the workflow guards: telling
  a manager that a stranger's request "has already been approved" answers a
  question they were not entitled to ask.
- **The repository layer** — list queries take a nullable id collection. `None`
  means unrestricted; an *empty* collection means the caller may see nobody and
  must return nothing. Collapsing those two into one branch is the bug this
  shape exists to prevent.

Scope is resolved once per request by `TeamScopeService` and injected as
`CurrentScope`. It is never re-derived inside a repository — a repository that
quietly filters by the current user is one whose results depend on invisible
state, and the exports, dashboards and notification fan-out all legitimately
need the unfiltered query.

Exports honour the scope of the screen they were launched from. An export that
did not would be worse than no restriction at all: it produces a file.

A refusal is **403 `outside_your_team`**, not a 404. Hiding a colleague's
existence buys nothing in a system whose directory is readable anyway, and costs
the person on the support call any chance of understanding what happened.

**Direct reports, one hop.** A skip-level report belongs to the manager in
between, which is also how approval routing already works — a leave request is
addressed to `reporting_manager_id`. Widening to the full chain is a change to
one query in `EmployeeRepository.direct_report_ids`.

## The client

`/auth/me` answers with the session — profile, roles and permissions together —
rather than the bare profile it used to return. **This is a breaking change** to
that endpoint's contract: it is now `{user, roles, permissions, is_superuser}`.

The permissions travel with the profile because the first render already needs
them: the shell decides which navigation items exist, and fetching them
separately would show a flash of menu entries the user cannot open. The provider
loads them *before* marking the session authenticated, for the same reason.

```tsx
<Can permission="employees:export">
  <ExportButton />
</Can>

const mayEdit = usePermitted({ permission: 'roles:update' });

<RequirePermission permission="roles:view" title="roles and permissions">
  <RoleManagementPage />
</RequirePermission>
```

These hide and disable; they do not secure. Every one has a matching guard on the
endpoint behind it, because anything enforced only in the browser is enforced by
whoever has not opened the network tab. What they buy is that a user is never
shown a control that will refuse them.

Navigation items declare a `permission`; the sidebar drops what the session
cannot open, and drops a section heading when everything under it is hidden — a
lone "Recruitment" label above nothing reads as a broken page.

`RequirePermission` shows a plain refusal rather than redirecting. A redirect to
the dashboard looks like a broken link and sends people to support.

## Protections against locking yourself out

Role editing is itself behind `roles:update`, which makes three mistakes
unrecoverable without database access. Each is refused:

- **A system role cannot be deleted or renamed** — the seeder would resurrect it.
- **A role still held by somebody cannot be deleted** — it would strip access
  from people the confirmation dialog cannot show you. Revoke or deactivate it.
- **Super Admin cannot lose `roles:view` or `roles:update`, and the last account
  holding it cannot be demoted** — that is locking the door with the key still
  inside.

## Tables

Migration `0015_rbac` adds four tables, all with UUID keys, audit columns and
soft deletion.

| Table | Holds |
| --- | --- |
| `permissions` | The catalogue, mirrored from the code registry |
| `roles` | System and custom roles |
| `role_permissions` | What a role grants; replaced wholesale on edit |
| `user_roles` | Who holds what, optionally scoped to a business unit |

`user_roles.scope_business_unit_id` is stored but **not yet enforced**. It is the
seam for the department-scoped access on the roadmap — "approve leave, but only
for this business unit" — and carrying it now means switching that on later is a
change to the resolver rather than a migration against live grants.

The migration also backfills: existing superusers are granted Super Admin so the
first deploy cannot lock out the only administrator, and every other account gets
the Employee floor, because an account with no role cannot use the product and
fixing that in a hurry is how a second superuser gets created.

Note the partial unique index `uq_user_roles_unscoped`. PostgreSQL treats NULLs
as distinct in a unique constraint, so `uq_user_roles_grant` alone does **not**
stop the same unscoped role being granted to the same user twice.

## API

| Method | Path | Does |
| --- | --- | --- |
| GET | `/roles/permissions` | The catalogue, grouped as the editor renders it |
| POST | `/roles/permissions/reconcile` | Add permissions the code defines but the database lacks |
| GET, POST | `/roles` | List and create |
| GET, PATCH, DELETE | `/roles/{id}` | Read, edit, remove |
| GET, PUT | `/users/{id}/roles` | Read and replace the roles a user holds |

Both `PATCH /roles/{id}` and `PUT /users/{id}/roles` replace their collection
wholesale rather than adding and removing one at a time. Each screen is a list of
checkboxes, and two endpoints that each move one row make "what does this person
hold?" a question with two answers.

`reconcile` is additive only. A permission that has disappeared from the registry
is reported, never deleted — deleting it would silently strip it from every role
that grants it.

## Testing

`tests/integration/test_rbac.py` — 29 tests, weighted toward the negative cases.
A permissions system that grants correctly but never actually refuses is
indistinguishable from having none, and it fails silently.

The ones worth knowing about: an Employee cannot browse the employee master, read
sensitive fields or export the directory; an HR Executive can read but not
archive; a Recruiter cannot create employees; deactivating a role revokes it
immediately; and the guard-coverage tests above.

`tests/integration/test_team_scoping.py` — 30 tests covering the reporting-line
half. Every one has the same shape: a manager, somebody who reports to them, and
a stranger who does not, with the same request made twice. It covers the scope
rule itself (skip-level reports are out, archived reports drop out, an account
with no employee record reaches nobody) and its application to the profile,
directory, attendance, leave, timesheets and the vault — including that a
refused decision really did leave the record undecided.

Note that the shared `test_user` fixture is a superuser. Guarding one router broke
72 of 74 employee tests, and a module's suite should exercise that module rather
than becoming partly a permissions test. RBAC has its own suite where the
accounts are deliberately narrow.

## Known gaps

Business-unit scoping is stored on `user_roles.scope_business_unit_id` but not
enforced; team scoping (below) narrows by reporting line instead.

Project-based scoping is not implemented. A Project Manager approves timesheets
for people who do not report to them, so they hold `employees:view_all` and are
organization-wide rather than narrowed to their project members. Narrowing them
to project membership is the next meaningful step if the product needs it.
