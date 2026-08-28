# Employee Master Management module

The central entity of the HRMS. Attendance, leave, projects, performance,
documents and payroll will all reference an employee rather than storing their
own copy of a person.

Status: **complete and production-ready** (Phase 4).

The directory, the profile and its export are narrowed by reporting line: a
Manager or Team Lead sees themselves and their direct reports, while HR, Super
Admin, Recruiter and Project Manager hold `employees:view_all` and see the whole
company. See
[`RBACModule.md`](RBACModule.md#team-scoping--whose-records-not-just-which-endpoint).

---

## 1. The rule this module exists to enforce

**Placement history is never overwritten.**

Every path that can change an employee's team, designation, grade,
reporting manager, work location or employment status funnels through a single
method, `EmployeeService._apply_placement_change`, which appends a row to
`employee_employment_history` in the same transaction as the change itself. The
dedicated lifecycle endpoints and the general update both go through it, so
there is no way to move someone quietly.

Two consequences worth knowing:

* There is **no endpoint that edits or deletes a history entry.** A correction is
  a new row, not an edit to an old one. `PATCH`, `PUT` and `DELETE` on
  `/employees/{id}/history` all return `405`.
* A change that **changes nothing writes nothing.** Resubmitting the current
  team is a no-op; recording it would put a row in the history saying
  nothing happened, which is worse than no row because it reads as though
  something did.

---

## 2. Employee and user

An employee is a person the organization employs. A user is a login identity.
They are separate records with an optional one-to-one link.

| | `users` | `employees` |
| --- | --- | --- |
| Answers | "who is signing in?" | "who do we employ?" |
| Created by | User Management | this module |
| Can exist alone | yes — an administrator with no employment | yes — an employee with no system access |
| Identifier | `USR-000001` | `EMP-000001` |

`employees.user_id` is nullable and unique: nullable because an employee can be
recorded before an account is provisioned, unique because one account cannot
belong to two employees.

**The employee record is the source of truth for HR data**, even where a field
also exists on the linked user. The two overlap on name, gender, date of birth,
personal email and mobile. The create form pre-fills nothing automatically today;
the employee record is authoritative once saved, and the user record continues to
serve authentication.

---

## 3. What it stores

Five tables. The satellite tables are separate rather than columns on
`employees` for a specific reason each time.

### `employees` — the record

**Personal** — name parts, gender, date of birth, blood group, marital status,
nationality, photo.

**Contact** — personal email, mobile, alternate number, emergency contact name,
number and relationship.

**Official** — official email (unique), official mobile, extension, work mode
(office / remote / hybrid).

**Employment** — joining date (required), confirmation date, employment status,
and seven references: employment type, business unit, team,
designation, grade, work location and reporting manager.

**Compensation** — CTC and salary grade. Basic only; payroll components,
deductions and revisions belong to the payroll module and will hang off these
rather than replace them.

### `employee_addresses` — current and permanent

A separate table because the shape of an address is identical whichever kind it
is, and duplicating eight columns to distinguish "current" from "permanent"
would double every future change to the address format. A partial unique index
on `(employee_id, address_type)` allows one of each.

### `employee_bank_details` and `employee_identification` — sensitive

Held apart so that **reading an employee does not read them**. A query that lists
employees does not touch these tables unless it asks to, which is what keeps
account numbers and Aadhaar out of exports, list responses and log lines by
default.

### `employee_employment_history` — append-only

Each row is the **state after a change**, not a description of the change. That
is the difference between a log and a history: given a date, a snapshot table can
answer "which team were they in?", which is exactly what attendance,
payroll and performance will need to ask about periods that have already closed.

---

## 4. The employee ID

`EMP-000001`, `EMP-000002`, … from a PostgreSQL sequence:

```sql
'EMP-' || lpad(nextval('employees_employee_code_seq')::text, 6, '0')
```

As a column default, not application code. Two concurrent creates running
`SELECT max(...) + 1` read the same maximum and produce the same code, and the
unique index then rejects one of them for a reason the user cannot act on.

It is absent from `EmployeeCreate` entirely, so a client can neither supply nor
edit one.

---

## 5. Employment status

Six states, distinct from soft deletion. An employee on notice is still employed
and still appears everywhere; an archived employee is hidden regardless of this
value.

| Status | Meaning |
| --- | --- |
| `probation` | Newly joined, not yet confirmed. The default on create |
| `confirmed` | Probation completed |
| `active` | In normal employment |
| `notice_period` | Serving notice; still employed |
| `resigned` | Employment ended |
| `inactive` | Not currently employed |

`resigned` and `inactive` are terminal: from either, the only move is back to
`active`. Returning someone to `probation` would rewrite the start of an
employment that already ended — a rehire is a new record, not an edit to the old
one. `409 invalid_status_transition`.

The **no-op rule differs by endpoint**, deliberately:

* `POST /employees/{id}/status` refuses a change to the current status
  (`409 already_in_status`) — asking for a change that is not a change is a
  mistake worth reporting.
* `PATCH /employees/{id}` accepts it silently. An edit form posts the whole
  record, so the current status comes back with every save; refusing that would
  make the form impossible to submit.

---

## 6. Lifecycle actions

One endpoint per action rather than a general "change" with a mode flag: each has
its own payload, its own guards and its own audit action, and collapsing them
would make every field optional and every rule conditional.

| Action | Endpoint | Records |
| --- | --- | --- |
| Confirm | `POST /{id}/confirm` | Status → confirmed, sets the confirmation date. Refused unless currently on probation |
| Transfer team | `POST /{id}/transfer` | New team; supply a business unit as well when the move crosses units |
| Change designation | `POST /{id}/designation` | New designation, optionally a new grade |
| Change reporting manager | `POST /{id}/manager` | New manager, or null to clear the line |
| Change work location | `POST /{id}/location` | New location, optionally a new work mode |
| Promote | `POST /{id}/promote` | Designation, grade, salary grade or CTC — at least one |
| Change status | `POST /{id}/status` | Any lifecycle move |
| Activate / Deactivate | `POST /{id}/activate`, `/deactivate` | Thin wrappers over a status change, so they cannot behave differently from it |
| Archive / Restore | `POST /{id}/archive`, `/restore` | Soft delete and its undo |

Every one takes an `effective_date` (defaulting to today, back-dating allowed), a
`reason` and `notes`. The effective date is not the date it was entered — a
transfer is routinely recorded in arrears.

A **transfer may carry a business unit**, because a team belongs to one; supply
it when the move crosses units so the placement stays coherent.

A **promotion must change something.** A promotion that changes nothing is a
history row with no content, which is worse than an error because it looks like a
record of something.

---

## 7. Guards

| Rule | Code | Why |
| --- | --- | --- |
| An employee cannot report to themselves | `manager_is_self` | Also a CHECK constraint on the table |
| A reporting line cannot close a loop | `reporting_cycle` | A ↦ B ↦ A makes every org-chart and approval-routing query non-terminating. Detected with a recursive CTE walking the proposed manager's chain, depth-capped at 50 |
| A manager with direct reports cannot be archived | `has_direct_reports` | Archiving them would leave their reports pointing at a hidden record |
| Statutory identifiers are unique across employees | `duplicate_identifier` | A duplicate Aadhaar almost always means the same person entered twice, which is far cheaper to catch now than to reconcile in payroll |
| The official email is unique | `duplicate_official_email` | Names the conflicting employee, and says when it is archived so the user restores rather than renames |
| One login account belongs to one employee | `user_already_linked` | |
| A reference must be live and active | `invalid_organization_reference` | The same rule the master module applies to its own parents |
| An archived employee cannot be edited | `record_archived` | Restore first |

Every message names the blocking record. "This user manages 2 active teams" is
actionable; "operation failed" is not.

---

## 8. Sensitive data

### What is masked

Masking happens **in the read model**, not at the call site. There is no code
path that returns an employee with a full Aadhaar or account number:
`EmployeeBankRead` and `EmployeeIdentificationRead` mask on construction, so a
new endpoint that returns an employee is masked by default rather than by
remembering to.

| Field | Masked as | Why |
| --- | --- | --- |
| Aadhaar | `XXXXXXXX9012` | Identifies the person; enough on its own to open an account somewhere |
| PAN | `XXXXXX234F` | As above |
| Account number | `XXXXXXXX3210` | As above |
| Passport, driving licence | last 3 characters | Identity documents of the same class |
| IFSC | **not masked** | A branch code identifies a bank, not a person |
| UAN, PF, ESI | **not masked** | Employer-side references that already appear on every payslip. Masking them would make the payroll reconciliation these screens exist for impossible |

Masks keep the *last* few characters: that is the half a person uses to confirm
"yes, that's my account", and the half that is useless alone to someone who has
only seen the response. The masked value preserves the original length, so the
reader can sanity-check what they entered.

### Revealing

`GET /employees/{id}/sensitive` returns the unmasked values, and **every call is
written to the audit trail** as `employee.sensitive.viewed`. An unaudited reveal
would make the masking everywhere else decorative.

In the UI, revealing is a button rather than a hover — a hover is something a
mouse does, not something a person decides. The client cache for this query uses
`staleTime: 0, gcTime: 0`, so the request happens only when someone has actually
asked and is never served from a cache that outlives that decision.

Audit entries name the fields that changed and never their values: a trail that
quotes an account number is a second copy of the thing being protected.

### What "stored securely" does and does not mean here

Bank and identifier columns are stored **as plain text**. What protects them is:

* a separate table, so ordinary reads do not touch it;
* masking in every read model;
* a single audited endpoint for the unmasked values;
* exclusion from exports and from `__repr__`, which ends up in tracebacks.

**Column-level encryption is not implemented.** Doing it properly needs a managed
`ENCRYPTION_KEY` with its own rotation story — deriving it from `SECRET_KEY`
would mean rotating that key destroys the data, which is a trap rather than a
safeguard. The recommended next step is pgcrypto or an application-level
envelope with a dedicated key, and it is a schema change to two columns rather
than a redesign.

---

## 9. Export

`GET /employees/export?format=csv|xlsx` returns the employees matching the
current filters. The page parameters are ignored: exporting page 1 of 12 is never
what was meant. Capped at 10,000 rows.

**No sensitive value is exported** — not even masked. A masked value in a
spreadsheet is noise: it cannot be used for anything, and its presence invites
someone to ask for the unmasked version "just for this file".

One column definition drives both formats, so a CSV and a spreadsheet of the same
filter always contain the same data.

* **CSV** is UTF-8 **with a BOM**: without it, Excel on Windows opens the file in
  the system codepage and mangles every non-ASCII name. Every field is quoted,
  because an address containing a comma is the norm rather than an edge case.
* **XLSX** writes real dates rather than strings, so sorting and filtering in
  Excel behave, and freezes the header row with an autofilter — a 3,000-row
  export is unusable without both.

The export itself is audited: it takes personal data out of the system, where
none of the platform's controls apply to it any more.

---

## 10. API

Twenty-three endpoints under `/api/v1/employees`, all requiring
`Authorization: Bearer <token>`. Full request and response detail is in
[`API.md`](API.md#7-employee-management).

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/employees` | Paged directory: search, status, org filters, joining-date range, sorting |
| `POST` | `/employees` | Create, with addresses, bank details and identifiers → `201` |
| `GET` | `/employees/{id}` | One employee, sensitive values masked |
| `PATCH` | `/employees/{id}` | Partial update; writes history for a placement change |
| `GET` | `/employees/{id}/history` | Employment history, newest first |
| `GET` | `/employees/{id}/audit` | Audit trail for this record |
| `GET` | `/employees/{id}/sensitive` | Unmasked bank and identity details. **Audited** |
| `PUT` | `/employees/{id}/bank` | Set bank details |
| `PUT` | `/employees/{id}/identification` | Set government identifiers |
| `PUT` | `/employees/{id}/address` | Set the current or permanent address |
| `POST` | `/employees/{id}/…` | The eleven lifecycle actions in §6 |
| `GET` | `/employees/dashboard` | Headline figures |
| `GET` | `/employees/export` | CSV or XLSX |

`/dashboard` and `/export` are registered **before** `/{employee_id}`. Starlette
matches in registration order, and the reverse would let `{employee_id}` capture
"dashboard" and fail to parse it as a UUID.

---

## 11. Audit

Every action writes an `audit_logs` row capturing the action, entity type, record
id, timestamp, actor and request id.

```
employee.created                 employee.promoted
employee.updated                 employee.team.transferred
employee.confirmed               employee.designation.changed
employee.archived                employee.manager.changed
employee.restored                employee.location.changed
employee.bank.updated            employee.status.changed
employee.identification.updated  employee.sensitive.viewed
employee.exported
```

A rejected write is **not** audited as a change: the request rolls back, so the
trail records only what actually happened.

The profile's **Audit history** tab reads this back. It is distinct from the
Employment history tab: that records what the employment *is*, this records what
was *done* to the record and by whom — including the actions that leave no
placement trace, such as revealing the bank details.

---

## 12. Architecture

Clean Architecture throughout — routes → services → repositories → models — with
the request-scoped session as the unit of work.

### Backend

| Layer | File |
| --- | --- |
| Models | `app/models/employee.py`, `employee_address.py`, `employee_bank_detail.py`, `employee_identification.py`, `employment_history.py` |
| Migration | `alembic/versions/..._0004_employee_master.py` |
| Schemas | `app/schemas/employee.py` |
| Repositories | `app/repositories/employee_repository.py` |
| Services | `app/services/employee_service.py`, `employee_export_service.py`, `employee_dashboard_service.py` |
| Routes | `app/api/v1/routes/employees.py` |
| Masking | `app/utils/masking.py` |

The dashboard and export services are separate from `EmployeeService` because
they answer different kinds of question. The employee service enforces rules
about one record; the other two only count and render, hold no guards, and will
grow as later modules add their own tiles and columns.

### Frontend

```
src/features/employees/
├── api/employees.api.ts        one client, including the file download
├── hooks/use-employees.ts      queries + one shared mutation factory
├── schemas/employee.schemas.ts Zod, mirroring the server rules
├── types/employee.types.ts
└── components/
    ├── employee-list-page.tsx      directory, filters, export
    ├── employee-form.tsx           six sections, shared by create and edit
    ├── employee-form-page.tsx      create and edit wrappers
    ├── employee-profile-page.tsx   the tabbed profile
    ├── employee-dashboard-page.tsx
    └── lifecycle-dialogs.tsx       one dialog per action
```

```
/employees            directory
/employees/dashboard  headline figures
/employees/new        create
/employees/[id]       profile (8 tabs)
/employees/[id]/edit  edit
```

**The active tab lives in the URL** (`?tab=bank`), so a colleague can be sent
"look at the bank tab of this employee" as a link, the back button steps between
tabs, and a refresh stays where you were. An unknown tab falls back to Overview
rather than rendering nothing.

Bank details and government identifiers are **absent from the main form**. They
are edited from their own tabs, where the unmasked values come through the
audited reveal endpoint rather than sitting in a form that is open for every
other reason too.

### Reusable components

Added to `src/components/common/` because later modules need them:

| Component | Purpose |
| --- | --- |
| `Timeline` | A vertical timeline of dated events. Generic — the employment history and the audit trail both render through it |
| `Tabs` | URL-backed tabs with the WAI-ARIA keyboard pattern |
| `EmploymentStatusBadge` | The six lifecycle states as one badge |
| `MaskedValue` | A sensitive value with an explicit, audited reveal |
| `EmployeeCard` | A person as a compact card, for where a table row would be too dense |

---

## 13. Tests

| Suite | Covers |
| --- | --- |
| Backend integration (80) | Every endpoint, every guard, masking, the audit trail, uniqueness, export contents, the dashboard |
| Backend unit (46) | Statutory identifier formats, masking, joining-date bounds, the promotion rule |
| Frontend (65 across the module) | Zod schemas, the list page, the status badge, the masked value |

Verified in a real browser as well: create with validation, all eight tabs, tab
deep-linking and fallback, the confirm dialog and the history row it produces,
the audit tab, edit, and the reveal round trip with its two audit entries.

Two regression tests were written against bugs found in live testing rather than
by the suite, and each was **verified to fail against the old code** before being
kept:

* creating an employee with any organizational reference (`MissingGreenlet` — the
  fixtures left records in the session's identity map, so the lazy load the
  server hits was never attempted);
* resubmitting the current employment status from the edit form.

---

## 14. Deliberate limitations

- **No column-level encryption.** See §8.
- **No RBAC.** Every authenticated user can reach every route, including the
  reveal. The choke point is a single dependency (`get_current_user`), so adding
  roles is additive — and the reveal endpoint is already separate and audited,
  which is exactly the shape a permission check will attach to.
- **Placement is not validated as a tree.** Nothing checks that the chosen team
  sits under the chosen business unit. That belongs in a later module where the
  assignment is authoritative; enforcing it here would block the legitimate case
  of an employee attached to a business unit and a location and nothing else.
- **`shift_id` is reserved, not usable.** The column exists for the Shift master
  that does not, carries no foreign key, and is absent from every write schema so
  nothing can populate it until there is a table to validate it against. The
  Shift module adds the constraint; it does not add the column.
- **No document storage.** `photo_url` is a URL, not an upload — there is no file
  storage in the platform yet.
- **No offboarding.** `resigned` and `notice_period` exist as statuses, but exit
  interviews, clearances and final settlements are the Offboarding module.
- **Reference pickers load 100 active records.** Fine for the expected volumes; a
  searchable async picker is the upgrade path.
- **Compensation is a number, not a structure.** CTC and a salary grade only;
  breakdown, revisions and payslips belong to payroll.
