# JSAN People360

The MVP supports the complete recruitment lifecycle: requisition, ATS, interviews, offers, candidate acceptance, preboarding, employee conversion and onboarding. See [Preboarding & Onboarding](docs/PreboardingOnboardingModule.md) for the Phase 3 workflow.

Workforce Operations covers [Project & Client Allocation Management](docs/ProjectClientAllocationModule.md) and [Attendance, Leave & Timesheets](docs/WorkforceModule.md) — shifts, the daily register, corrections, leave balances and approvals, holiday calendars, and weekly timesheets.

An enterprise HR management platform built to carry the complete employee
lifecycle — recruitment, employee management, attendance, leave, performance and
offboarding.

**Delivered so far: phases 1 to 22** — the platform foundation, Organization
Management, User Management, Employee Master Management, the Document Vault, Job
Requisitions, Recruitment/ATS, Interviews, Offers, Preboarding & Onboarding,
Project & Client Allocation, Performance Management, Workforce Operations,
Role-Based Access Control, manager team scoping, HR Administration,
Resignation & Offboarding, Asset Management, and the Helpdesk with
Announcements, plus end-to-end Payroll. Everything here is application code,
not a prototype; production deployment still requires the checklist under
[Production build](#production-build).

---

## Phase 22 — Payroll

Payroll covers the full controlled path from compensation setup to an immutable
payroll result:

```text
Salary components and structures
  → employee compensation and payroll eligibility
  → payroll period
  → attendance, leave and overtime input snapshot
  → calculation
  → exception review and adjustments
  → reconciliation
  → approval
  → finalization
  → payslips, reports and final settlement
```

Administrators define earning and deduction components, compose them into
version-safe salary structures, assign compensation, revise it without rewriting
history, configure payroll and leave rules, and explicitly mark employees as
eligible. A payroll period snapshots approved workforce data before calculation;
source-change detection identifies attendance or leave that changed after the
snapshot.

One run is allowed per period. Calculation produces explainable line items per
employee, while review exceptions, comments and manual adjustments remain
append-only. Critical exceptions and incomplete checklist items block review.
Submission, approval and finalization are separate permissions, and every gate
is rechecked by the server at the moment of the decision. Finalization closes the
period and writes immutable, denormalized employee snapshots.

Official PDF payslips are generated only from finalized snapshots. Employees can
view their current compensation, salary history, payslips and released final
settlement through self-service screens. Administrators have finalized-payroll
history, period comparison and payroll reports, plus a Full & Final Settlement
workflow connected to offboarding.

Current boundary: the module records approved payroll and settlements but does
not transmit money to a bank. Employer statutory contributions are not modelled
as a separate employer-cost layer; applicable tax and statutory rules must be
configured and validated for the deployment jurisdiction.

## Phase 21 — Completion sweep

A whole-project audit hunted for half-built features, and this phase closed
what it found. The security fix first: **completing an offboarding now
disables the login** — the exit set the employee inactive but never touched
the account, and authentication checks only the account.

Shipped from the audit's list: the **org-wide Performance screen** (its
backend and an unused 1,100-line frontend data layer had existed for phases,
one file short of a module), an editable **Settings screen** over the
`app_settings` store that had waited since Phase 1, a searchable **Audit
Trail** screen with CSV export, real UIs for the three HR screens that
rendered raw JSON, a live landing dashboard in place of the Phase-1
placeholder tiles, **leave carry-forward and joining-year proration** (the
policy fields existed and were applied nowhere), the **preboarding invitation
email** (the one message that cannot land in-app — the recipient has no
account yet), and employee pickers where seven screens asked for pasted UUIDs.

Also pruned: eight permission codes no endpoint ever checked (a permission no
route requires is a lie on the roles screen), a dead `employees.shift_id`
column, and every stale "Phase 1 has no roles" comment — five of them sat on
security-critical code describing the opposite of its behaviour.

## Phase 20 — Helpdesk & Announcements

The internal helpdesk — an employee asks HR, IT, Admin, Finance or Facilities
for something and the request is tracked from raised to closed — and company
announcements with audience targeting and acknowledgement tracking.

Two decisions shape the helpdesk. **The requester never appears in a request
body** — `POST /me/helpdesk` has no employee field, so the IDOR class of bug is
unrepresentable rather than checked for. And **an agent's internal note cannot
leak**: the employee read model has no `internal` field, so even a filtering bug
would leave the note nowhere to land.

Announcements split **writing from sending**: `announcements:create` drafts,
`announcements:publish` sends. Publishing fans out through the existing
notification inbox — the announcement is the durable thing the notification
points at, which is why this is not a second message system. The employee
dashboard's `recent_announcements` field, a notification-inbox stand-in since
phase 6, now carries the real thing.

Full detail: [`docs/HelpdeskModule.md`](docs/HelpdeskModule.md) and
[`docs/AnnouncementsModule.md`](docs/AnnouncementsModule.md).

## Phase 19 — Asset Management

The asset register: what the company owns, who is holding it, what condition it
is in, and everywhere it has been.

One decision shapes it — **the asset row holds current state and the transaction
tables hold what happened**. An assignment, a return and a transfer are each a
record of an event rather than a column being overwritten, because
`assigned_to = somebody_else` answers "who has it now" and destroys "who had it
in March".

Status moves only along a transition table: nothing comes back from disposed,
and a damaged thing cannot become available without passing through maintenance.

**Assets belong to Admin.** HR holds `assets:view` and none of the six custody
actions — they see what a leaver is holding in order to run a clearance, and
issuing or writing off company property is a different job.

Integrated with offboarding by adding **one column** to the clearance table
phase 18 already had, which was written anticipating exactly this.

Full detail: [`docs/AssetModule.md`](docs/AssetModule.md).

## Phase 18 — Resignation & Offboarding

The complete separation lifecycle: an employee resigns, their manager decides,
HR processes, five departments clear, the employee completes an exit interview
and collects their letters, and the record goes inactive without anything being
deleted.

Two acts are deliberately separate permissions, and the distinction is the whole
access model: a **manager approves** their own direct report's resignation, and
**HR processes** it — verifying the notice period, settling the last working day
and opening the case. HR Admin holds every resignation action except `approve`.

The notice period is configuration rather than a constant: it comes from the
employment type, is resolved once when the resignation is submitted, and an
authorized adjustment is refused without a reason and recorded as an override.

An exit ends live allocations and stops new attendance, leave and timesheets. It
deletes nothing — the history outlives the employment.

Full detail: [`docs/OffboardingModule.md`](docs/OffboardingModule.md).

## Phase 17 — HR Administration

An HR dashboard composed from seven modules, an organization-wide read across
the workforce, leave-policy configuration, and three administrative actions the
seeded HR roles deliberately do not hold.

**HR is not an administrator**, and the module is where that is enforced —
by which permission guards which endpoint, never by a role name. An HR user
without `employees:view_all` sees their own reporting line here and nothing
else. No endpoint touches users, roles, settings or the audit trail.

Full detail: [`docs/HRModule.md`](docs/HRModule.md).

## Phase 15–16 — Role-Based Access Control

19 modules, 73 permissions and eight seeded roles, with 246 of 260 endpoints
guarded and a coverage test that fails the build if a new endpoint is added
without one. Permissions are defined in code and mirrored to the database; roles
are data and editable. The client hides what a session cannot open, and the
server refuses it regardless.

Access is scoped by reporting line as well as by permission: a Manager or Team
Lead sees and approves for **their direct reports**, while Super Admin, HR,
Recruiter and Project Manager hold `employees:view_all` and stay
organization-wide. The narrowing applies to the employee profile and directory,
attendance, leave, timesheets and employee documents — including their exports.

`GET /auth/me` returns the session rather than a bare profile — a breaking
change to that endpoint. See [`docs/RBACModule.md`](docs/RBACModule.md).

## Phase 14 — Workforce Operations

Configurable shifts with grace and weekly off, an attendance register with
check-in/check-out and correction requests, leave types and balances that hold
days on application and spend them on approval, holiday calendars whose dates
are not charged as leave, weekly timesheets validated against project
allocations, a monthly calendar, two dashboards, and six reports in
CSV/XLSX/PDF.

Four rules shape it: a day belongs to one attendance record; leave is counted in
working days; balance is held, then spent; a submitted timesheet is not edited.
See [`docs/WorkforceModule.md`](docs/WorkforceModule.md).

## Phase 13 — Performance Management

Appraisal cycles, weighted goals, two-sided reviews, recognition and continuous
feedback, over an append-only performance history. A submitted review is never
rewritten, weightage is a budget capped at 100%, and progress is appended rather
than edited.

Full detail: [`docs/PerformanceModule.md`](docs/PerformanceModule.md).

## Phase 11–12 — Project & Client Allocation

Clients, projects, memberships and percentage allocations, with capacity checks
that refuse to take anyone past 100%, a bench view, and allocation history.

Full detail: [`docs/ProjectClientAllocationModule.md`](docs/ProjectClientAllocationModule.md).

## Phase 10 — Preboarding & Onboarding

Candidate preboarding portals, document review, policy acknowledgements,
conversion to an employee record, and onboarding cases with tasks and progress.

Full detail: [`docs/PreboardingOnboardingModule.md`](docs/PreboardingOnboardingModule.md).

## Phase 9 — Offer Management

Offer letters with salary components, sequential approval, generated PDFs stored
in the Document Vault, release, candidate acceptance or decline, withdrawal and
expiry.

Full detail: [`docs/OfferManagementModule.md`](docs/OfferManagementModule.md).

## Phase 8 — Interview Management & Scheduling

Conflict-safe scheduling, employee panels, calendar views, structured
scorecards, calculated recommendations, ATS decisions, Document Vault materials,
notifications, reports and complete interview history.

Full detail: [`docs/InterviewModule.md`](docs/InterviewModule.md).

## Phase 7 — Recruitment & Applicant Tracking

Approved-requisition job openings, candidate profiles and Document Vault
resumes, duplicate detection, configurable recruitment stages, a drag-and-drop
pipeline, recruiter notes, talent pools, notifications, audit history, dashboard
metrics and CSV/XLSX reporting.

Full detail: [`docs/RecruitmentModule.md`](docs/RecruitmentModule.md).

---

## Phase 5 — Document Management & Digital Document Vault

A reusable vault for employee, user, organization and future candidate files.
It provides configurable categories and types, signature-validated PDF/image
uploads, append-only versions, authenticated preview/download, review status,
expiry tracking, archive/restore, dashboards and a document-scoped audit trail.
Files are accessed through an interchangeable storage interface and physical
storage keys never leave the API.

Full detail: [`docs/DocumentModule.md`](docs/DocumentModule.md).

## Phase 6 — Job Requisition & Workforce Planning

Manpower requests with generated requisition IDs, organization and position details, sequential Hiring Manager → Second approver → HR approval, complete history, in-app notifications, Document Vault attachments, workforce dashboards, filters and CSV/XLSX exports.

Full detail: [`docs/RequisitionModule.md`](docs/RequisitionModule.md).

---

## Phase 4 — Employee Master Management

The central entity of the HRMS. Attendance, leave, projects, performance,
documents and payroll will all reference an employee rather than storing their
own copy of a person.

Highlights:

- **History is never overwritten.** Every change to a team, designation,
  grade, reporting manager, work location or status appends to an append-only
  employment history in the same transaction. There is no endpoint that edits or
  deletes an entry — a correction is a new row. A change that changes nothing
  writes nothing.
- **Twenty-three API operations** — the directory, the record, eleven lifecycle
  actions, the sensitive-data reveal, the audit trail, a dashboard and an export.
- **Auto-generated employee IDs.** `JSAN1`, `JSAN2`, ... from a PostgreSQL
  sequence, so two concurrent creates can never be handed the same number.
- **Sensitive data is masked by the read model**, not by the caller: there is no
  code path that returns a full Aadhaar or account number. The unmasked values
  come from one endpoint, and **every call to it is audited**.
- **Guards that keep the org chart sound.** A reporting line cannot close a loop
  (checked with a recursive walk up the chain), a manager with direct reports
  cannot be archived, and statutory identifiers are unique across employees —
  a duplicate Aadhaar is a duplicate person, not a coincidence.
- **Export to CSV and Excel** honouring the filters on screen, with no sensitive
  value included — not even masked.
- **A profile with eight tabs**, and the active tab lives in the URL, so a
  colleague can be sent a link straight to the one that matters.

Full detail: [`docs/EmployeeModule.md`](docs/EmployeeModule.md).

---

## Phase 3 — User Management

Everyone who can sign in. Accounts are created and maintained here, and every
later module will reference a user rather than storing its own copy of a person.

Highlights:

- **Eleven API operations** — list, create, read, update, activate, deactivate,
  archive, restore, reset password, plus two self-service profile routes.
- **Auto-generated staff codes.** `USR-000001` onwards, from a PostgreSQL
  sequence, so two concurrent creates can never be handed the same number.
- **Guards that prevent lock-out.** You cannot deactivate or archive your own
  account, or the last active one. An account still referenced by other records —
  today, a team they manage — cannot be archived.
- **Two audiences, two schemas.** What an administrator may change and what a
  user may change about themselves are separate models, so a self-service request
  cannot carry an organizational assignment even before RBAC exists.
- **Placed in the organization.** Eight optional references into the Phase 2
  masters — business unit, team, designation, grade,
  location, employment type — resolved to names in every response.
- **Password policy in one place.** 8+ characters with upper, lower, digit and
  symbol; bcrypt; shared by create, admin reset, self-service change and the
  forgot-password flow, so it cannot drift between them.

Full detail: [`docs/UserModule.md`](docs/UserModule.md).

---

## Phase 2 — Organization Management

The master-data system every other module builds on. Seven masters, each with
full CRUD plus archive and restore:

**Hierarchy** — Business Unit → Team / Designation
**Reference** — Organization profile, Location, Employment Type, Grade

Highlights:

- **55 API operations** — six standard endpoints per master, generated from one
  router factory so the HTTP contract cannot drift between entities.
- **Archive, never delete.** Records that other modules reference are soft
  deleted and restorable. A parent cannot be archived while live children point
  at it; a child cannot be restored under an archived parent.
- **Duplicate-proof.** Names and codes are trimmed, normalised and compared
  case-insensitively, enforced in the service *and* by functional unique indexes
  in PostgreSQL.
- **Fully audited.** Every create, update, archive and restore records the
  action, entity, record id, timestamp and user.
- **One set of screens.** A declarative registry drives the list, form and
  detail pages for all nine masters; adding a tenth is a config entry, not four
  new pages.

Full detail: [`docs/OrganizationModule.md`](docs/OrganizationModule.md).

```bash
# Optional: a realistic sample hierarchy to click through
cd backend && python -m app.cli.seed --sample-data
```

---

## What Phase 1 delivers

| Area | Status |
| --- | --- |
| FastAPI application, versioned at `/api/v1` | Done |
| Clean Architecture: routes → services → repositories → models | Done |
| PostgreSQL schema, owned entirely by Alembic | Done |
| JWT authentication with rotating refresh tokens | Done |
| Password reset and password change flows | Done |
| Standard response envelope on every endpoint | Done |
| Global exception handling with user-friendly messages | Done |
| Structured, request-correlated logging | Done |
| Append-only audit trail | Done |
| Next.js 15 / React 19 app shell: sidebar, header, breadcrumbs | Done |
| Reusable component library (tables, forms, modals, cards, states) | Done |
| Validation: Zod on the client, Pydantic v2 on the server | Done |
| Test suites: pytest, Jest + React Testing Library | Done |
| Tooling: Black, isort, Ruff, mypy, ESLint, Prettier, pre-commit | Done |
| Role-based access control | Deferred in Phase 1 — delivered in Phase 15 |
| Organization Management (master data) | Done — Phase 2 |
| User Management | Done — Phase 3 |
| Employee Master Management | Done — Phase 4 |
| Recruitment, interviews, offers, onboarding | Done — Phases 7–10 |
| Projects, performance, attendance, leave, timesheets | Done — Phases 11–14 |
| Resignation & offboarding | Done — Phase 18 |
| Asset management | Done — Phase 19 |
| Helpdesk & announcements | Done — Phase 20 |
| Performance screens, settings, audit trail, leave accrual | Done — Phase 21 |
| Payroll: compensation, inputs, calculation, review, approval, payslips, reports and settlements | Done — Phase 22 |

### RBAC arrived in Phase 15

Phase 1 deliberately shipped without it: per the brief, every authenticated user
had full access, and the building blocks were left in place — `users.is_superuser`
and a single authorisation dependency (`app/api/deps.py`) — so that adding roles
later would be additive rather than a rewrite. It was.

The line RBAC now enforces was already drawn in the schemas: the self-service
profile model has no administrative fields on it, so a request cannot carry one
whether or not a role check runs.

See [`docs/RBACModule.md`](docs/RBACModule.md) for the permission catalogue, the
eight seeded roles, and the reporting-line scoping that narrows *whose* records a
permission reaches.

---

## Tech stack

**Backend** — Python 3.12+, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2,
PostgreSQL, asyncpg, PyJWT, bcrypt, openpyxl and ReportLab.

**Frontend** — Next.js 15 (App Router), React 19, TypeScript (strict, no `any`),
Tailwind CSS v4, Shadcn UI / Radix, TanStack Query, React Hook Form, Zod, Axios,
Lucide React.

---

## Repository layout

```
jsan-people360/
├── backend/          FastAPI application (Clean Architecture)
├── frontend/         Next.js application (feature-based architecture)
├── docs/             Architecture, API, environment and setup documentation
├── scripts/          PowerShell developer scripts
├── uploads/          Runtime file storage (git-ignored)
├── .gitignore
├── .pre-commit-config.yaml
├── README.md
└── requirements.txt  Backend Python dependencies
```

A full annotated tree is in [`docs/FolderStructure.md`](docs/FolderStructure.md).

---

## Quick start

### Prerequisites

- Python 3.12 or newer
- Node.js LTS (20+) and npm
- PostgreSQL 14 or newer, running locally
- Git

### Windows (scripted)

```powershell
git clone <repository-url> jsan-people360
cd jsan-people360

# Creates the venv, installs everything, writes .env files,
# creates the databases, migrates and seeds. Prompts for the
# PostgreSQL password.
.\scripts\setup.ps1

# Start the API and web client in separate windows
.\scripts\dev.ps1
```

### Any platform (manual)

```bash
# 1. Backend
python -m venv backend/.venv
source backend/.venv/bin/activate          # Windows: backend\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

cp backend/.env.example backend/.env
# Edit backend/.env: set SECRET_KEY and your POSTGRES_* values.
# Generate a key with:
#   python -c "import secrets; print(secrets.token_urlsafe(64))"

createdb jsan_people360
createdb jsan_people360_test

cd backend
alembic upgrade head        # create the schema
python -m app.cli.seed      # create the bootstrap admin + default settings
uvicorn app.main:app --reload

# 2. Frontend (in a second terminal)
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Then open **<http://localhost:3000>**.

Full step-by-step instructions, including troubleshooting, are in
[`docs/Installation.md`](docs/Installation.md).

### Deploying to Railway

The repository ships ready for Railway: `backend/Dockerfile` and
`frontend/Dockerfile` (selected by `railway.api.json` / `railway.web.json`), an
entrypoint that applies migrations and creates the administrator on every
start, health checks, and a volume mount for uploads. The fifteen-minute
walkthrough -- project, Postgres, the two services and every variable -- is in
[`docs/RailwayDeployment.md`](docs/RailwayDeployment.md).

### Default administrator

A single development account is created by the seed script:

| Email | Password |
| --- | --- |
| `admin@example.com` | `Admin@12345` |

Both are configurable via `DEFAULT_ADMIN_EMAIL` and `DEFAULT_ADMIN_PASSWORD` in
`backend/.env`.

> **These are development credentials.** Change them before the application is
> reachable by anyone but you. The seed script warns when it runs against a
> production environment.

The seed creates no employee login. Create an active user in User Management,
assign the Employee role, and link that user from the employee record. The
`--sample-data` option adds only a demonstration organization hierarchy; it does
not add people or reusable employee passwords.

### Demo data (every module, end to end)

To see the whole product working -- not just an empty shell -- run the demo
seed after the steps above:

```bash
cd backend
python -m app.cli.seed --sample-data   # organization hierarchy (if not done yet)
python -m app.cli.seed_demo            # people and one full story per module
```

It drives the real service layer, so everything it writes went through the same
rules, audit trail and notifications the application applies. It creates:

| Area | What you get |
| --- | --- |
| People | 12 employees with logins across HR, recruiting, finance, engineering management and a product team, with reporting lines, addresses, bank and ID details |
| Documents | Offer letters and ID proofs in the vault, some reviewed and approved |
| Workforce | Shifts, the year's holiday calendar, leave balances, ~40 working days of attendance per person, leave requests in every state, regularizations, timesheets (approved, submitted and draft) |
| Projects | Two clients, three projects, allocations for the engineering team |
| Performance | An active annual cycle, goals with progress, one complete self → manager → HR review chain, a recognition and a feedback note |
| Hiring | A requisition approved by all three approvers and opened; three candidates (one rejected, one in a talent pool); a scheduled technical interview with two scorecards and a hire decision; an approved, released and accepted offer; preboarding with documents, policy acknowledgements and conversion to an employee with an onboarding checklist |
| Assets | Laptops, a monitor and a phone -- issued, one under repair |
| Helpdesk | Tickets open, in progress and resolved; announcements published (one pinned, one requiring acknowledgement) and one draft |
| Payroll | Salary components and an active structure, compensation for everybody in the cast, last month's run calculated → reviewed → approved → **finalized with payslips**, and this month's run sitting in review |
| Offboarding | One resignation approved by the manager, processed by HR, cleared, exit interview taken, relieving and experience letters issued, **full & final settlement approved and settled**, case completed |

Demo sign-ins all use the password **`Demo@12345`**:

| Email | Role | Who |
| --- | --- | --- |
| `ananya.rao@demo.jsan.example` | HR Admin | Head of People |
| `rahul.verma@demo.jsan.example` | HR Executive | HR operations |
| `meera.iyer@demo.jsan.example` | Recruiter | Talent acquisition |
| `fatima.khan@demo.jsan.example` | HR Admin (payroll) | Finance operations |
| `vikram.singh@demo.jsan.example` | Manager | Engineering manager |
| `suresh.kumar@demo.jsan.example` | Project Manager | Delivery |
| `sneha.patel@demo.jsan.example` | Team Lead | Product Engineering lead |
| `arjun.nair@demo.jsan.example`, `divya.menon@…`, `karthik.reddy@…`, `pooja.gupta@…` | Employee | Engineers |
| `rohan.das@demo.jsan.example` | Employee | Left the company (offboarded) -- login disabled |
| `aisha.sheikh@demo.jsan.example` | Employee | Joiner in preboarding |

The demo seed is additive and safe to re-run: each section skips itself when its
data already exists. The one thing it changes outside its own records is that
employees **without** a salary are marked *not eligible* for payroll, so the
demo run can be finalized.

---

## Development commands

### Backend (run from `backend/`, virtual environment active)

```bash
uvicorn app.main:app --reload        # start the API with hot reload
pytest                               # all tests
pytest tests/unit -q                 # unit tests only (no database needed)
pytest --cov=app --cov-report=term   # tests with coverage

alembic upgrade head                 # apply migrations
alembic revision --autogenerate -m "add employees table"
alembic downgrade -1                 # roll back one revision
alembic check                        # fail if models and schema have drifted

black . && isort . && ruff check --fix .
mypy app
python -m app.cli.seed               # re-seed development data
python -m app.cli.seed --sample-data # also insert the sample org hierarchy
python -m app.cli.seed_demo          # demo people and one full story per module
```

### Frontend (run from `frontend/`)

```bash
npm run dev            # development server with hot reload
npm run build          # production build
npm start              # serve the production build
npm test               # Jest + React Testing Library
npm run test:coverage  # tests with coverage
npm run typecheck      # tsc --noEmit
npm run lint           # ESLint
npm run format         # Prettier (write)
npm run verify         # typecheck + lint + test
```

### Everything at once

```powershell
.\scripts\verify.ps1                     # every quality gate
.\scripts\verify.ps1 -SkipIntegration    # skip tests needing a database
```

---

## Production build

```bash
# Backend — no build step; run migrations then serve with workers
cd backend
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --no-access-log

# Frontend
cd frontend
npm ci
npm run build
npm start
```

Before deploying, review the production checklist in
[`docs/EnvironmentVariables.md`](docs/EnvironmentVariables.md#production-checklist).
The essentials: a unique `SECRET_KEY`, `APP_ENV=production`, `JP360_DEBUG=false`,
`COOKIE_SECURE=true`, `LOG_FORMAT=json`, an explicit `TRUSTED_HOSTS`, and
`BACKEND_CORS_ORIGINS` restricted to your real frontend origin. Also replace or
remove the bootstrap administrator credential, configure SMTP if password-reset
mail must be delivered, apply every migration, and run the full verification
suite against the release revision before deployment.

---

## API

Interactive documentation is served by the running backend (disabled in
production):

- Swagger UI — <http://localhost:8000/docs>
- ReDoc — <http://localhost:8000/redoc>
- OpenAPI schema — <http://localhost:8000/openapi.json>

Every endpoint returns the same envelope:

```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": {},
  "errors": null
}
```

The complete reference, including error codes and the authentication flow, is in
[`docs/API.md`](docs/API.md).

---

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/Architecture.md`](docs/Architecture.md) | Layering, request lifecycle, auth design, key decisions and their rationale |
| [`docs/OrganizationModule.md`](docs/OrganizationModule.md) | The Organization Management module: masters, lifecycles, rules, extension guide |
| [`docs/UserModule.md`](docs/UserModule.md) | The User Management module: accounts, guards, passwords, the two audiences |
| [`docs/EmployeeModule.md`](docs/EmployeeModule.md) | The Employee Master module: the history rule, lifecycle actions, sensitive data, export |
| [`docs/DocumentModule.md`](docs/DocumentModule.md) | The Document Vault: categories, versions, review, expiry |
| [`docs/RequisitionModule.md`](docs/RequisitionModule.md) | Job requisitions: the approval chain, attachments, exports |
| [`docs/RecruitmentModule.md`](docs/RecruitmentModule.md) | Recruitment/ATS: openings, candidates, the pipeline, talent pools |
| [`docs/InterviewModule.md`](docs/InterviewModule.md) | Interviews: conflict-safe scheduling, panels, scorecards, decisions |
| [`docs/OfferManagementModule.md`](docs/OfferManagementModule.md) | Offers: versions, approval, PDFs, release and candidate response |
| [`docs/PreboardingOnboardingModule.md`](docs/PreboardingOnboardingModule.md) | Preboarding and onboarding: the portal, conversion, cases and tasks |
| [`docs/ProjectClientAllocationModule.md`](docs/ProjectClientAllocationModule.md) | Clients, projects, allocations, capacity and the bench |
| [`docs/PerformanceModule.md`](docs/PerformanceModule.md) | Performance: cycles, weighted goals, two-sided reviews, the three rules |
| [`docs/HRModule.md`](docs/HRModule.md) | HR Administration: the dashboard, leave policy, and why HR is not an administrator |
| [`docs/AssetModule.md`](docs/AssetModule.md) | Asset management: the register, custody as transactions, the status table and the offboarding link |
| [`docs/HelpdeskModule.md`](docs/HelpdeskModule.md) | Helpdesk: employee requests, agent queues, internal notes, SLAs and audit history |
| [`docs/AnnouncementsModule.md`](docs/AnnouncementsModule.md) | Announcements: drafting, targeted publication, notification delivery and acknowledgement tracking |
| [`docs/OffboardingModule.md`](docs/OffboardingModule.md) | Resignation & offboarding: the workflow, notice period, clearance and what an exit preserves |
| [`docs/ProductionReadiness.md`](docs/ProductionReadiness.md) | The final hardening audit: security findings and fixes, IDOR results, and the deployment checklist |
| [`docs/FolderStructure.md`](docs/FolderStructure.md) | Annotated directory tree and where new code belongs |
| [`docs/API.md`](docs/API.md) | Endpoint reference, response envelope, error codes |
| [`docs/EnvironmentVariables.md`](docs/EnvironmentVariables.md) | Every variable, its default, and the production checklist |
| [`docs/RBACModule.md`](docs/RBACModule.md) | Roles, permissions, enforcement and the lock-out protections |
| [`docs/WorkforceModule.md`](docs/WorkforceModule.md) | Attendance, leave and timesheets: the four rules, the tables, the screens |
| [`docs/DatabaseSchema.md`](docs/DatabaseSchema.md) | Table definitions, relationships, conventions |
| [`docs/Components.md`](docs/Components.md) | The reusable component library |
| [`docs/Installation.md`](docs/Installation.md) | Detailed setup and troubleshooting |
| [`backend/alembic/README.md`](backend/alembic/README.md) | Migration workflow |

---

## Non-negotiables

These rules keep the foundation sound as it grows:

1. **The schema belongs to Alembic.** `Base.metadata.create_all()` is never
   called; a pre-commit hook rejects it. Every schema change ships as a
   migration.
2. **No business logic in routes.** Routes translate HTTP to service calls.
   Services hold the rules. Repositories are the only code that issues SQL.
3. **Validate every request.** Pydantic v2 on the server, Zod on the client.
4. **Both languages are type-checked, and both checks are gates.** `mypy --strict`
   over `backend/app` and `tsc --noEmit` over `frontend/src`, wired into
   `scripts/verify.ps1` *and* pre-commit. A strict setting nothing runs is a
   preference, not a rule.
5. **No `any` in TypeScript.** Enforced by ESLint with type-aware rules.
6. **One response shape.** Success and failure both use the envelope above.
7. **Errors are user-facing.** Internal detail is logged, never returned.
8. **History is append-only.** Employment history is never updated or deleted;
   a correction is a new row.
9. **Sensitive values are masked in the read model**, never at the call site, so
   a new endpoint is masked by default rather than by remembering to.

---

## Licence

Proprietary — © JSAN Technologies. All rights reserved.
