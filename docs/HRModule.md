# HR Administration

Phase 17 gives HR its own dashboard, an organization-wide read across the
workforce modules, the leave-policy configuration §6 of the brief asks for, and
three administrative actions that are deliberately **not** granted to the seeded
HR roles.

## HR is not an administrator

That sentence is the whole module, and it is enforced by which permission guards
which endpoint. Three kinds appear:

| Guard | Meaning | Held by seeded HR |
| --- | --- | --- |
| `require_org_wide("attendance:view")` | An HR **read** across the organization: the module permission *and* `employees:view_all` | Yes |
| `require("leave:policy_manage")` | An HR **administrative** action — deciding how much casual leave the company gives is HR's job by definition | HR Admin only |
| `require("attendance:manage_all")`, `require("timesheets:manage_all")`, `require("leave:balance_adjust")`, `require("leave:override_approval")` | Amending somebody's record with no request behind it, or deciding a request addressed to their manager | **No** |

The last four are administrative powers, not consequences of `approve`: a
manager approving their own report's correction and an administrator overwriting
a stranger's day are different things, and collapsing them is how HR quietly
becomes an administrator. An organization that wants HR to hold one ticks it on
the roles screen; nothing in the module grants it.

An HR user *without* `employees:view_all` sees their own reporting line here and
nothing else — the org-wide guard is a conjunction, not a role check. **There is
no `if role == "HR"` anywhere in the codebase.**

What is absent matters as much: no endpoint touches users, roles, permissions,
settings or integrations, and none administers the audit trail. Those are the
Administrator's, on their own modules, behind their own permissions.

## No business rules live here

A leave policy change is `WorkforceService.update_leave_type`. A document review
is `DocumentService.review`. A balance adjustment is
`WorkforceService.adjust_balance`, audited there because that is where balances
live. If a rule appears to be missing from an HR screen, it is missing from the
module that owns it.

What the module *does* own is two things a shared service cannot:

- **Composition.** The dashboard is seven modules' figures on one screen and the
  employee profile is nine tabs about one person. Assembling either in the
  browser would be sixteen requests to render two screens.
- **Graduated disclosure.** Every dashboard section sits behind the permission
  for the module it summarises, and the service asks `AuthorizationService`
  which of them the caller holds. `sections` names the ones that came back — a
  block of zeroes and "you may not ask" are different answers.

## Leave policy

Migration `0017` extends `leave_types` with credit frequency, credit amount,
proration and an `effective_from` / `effective_to` window. These extend the
table the leave engine already reads rather than adding a second one, and the
window is honoured by `WorkforceService` — configuration with an effect, not
configuration with a screen.

## API

Twenty operations under `/api/v1/hr`:

| Area | Operations |
| --- | --- |
| Overview | dashboard, analytics, report catalogue, report export |
| People | employee directory, employee profile |
| Workforce reads | attendance, leave, timesheets, projects, performance |
| Documents | review queue, review a document |
| Leave policy | list, create, update |
| Administrative | correct attendance, adjust a balance, override a leave decision, decide a timesheet |
| Requests | the queue of employee requests waiting on HR |

## Screens

`/hr/dashboard`, `/hr/employees` and `/hr/employees/{employeeId}`,
`/hr/attendance`, `/hr/leave` and `/hr/leave/policies`, `/hr/timesheets`,
`/hr/documents`, `/hr/projects`, `/hr/performance`, `/hr/recruitment`,
`/hr/reports` and `/hr/helpdesk`. The client hides what a session cannot open;
the server refuses it regardless.

The asymmetry between the five permissions — HR Admin is granted exactly one of
them — is asserted by `backend/tests/integration/test_hr.py`.
