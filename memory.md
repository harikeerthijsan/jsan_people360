# Claude's project memory — JSAN People360

Working notes kept by Claude (the AI pair on this codebase) so that any new session
starts with the same picture of the project, its conventions, and what has changed
recently. Update this file whenever a session ends with something worth remembering.
Last updated: 2026-08-27.

---

## 1. What this project is

**JSAN People360** — an enterprise HRMS by JSAN Technologies covering the whole employee
lifecycle: organisation setup, users/RBAC, employee master, document vault,
requisitions → ATS → interviews → offers → preboarding/onboarding, project & client
allocation, performance, attendance/leave/timesheets, HR administration, resignation &
offboarding, asset management, helpdesk/announcements, and end-to-end payroll.

Delivered phases: **1–22** (Payroll is phase 22, itself built in 8 sub-phases; all done).
Module docs live in `docs/*.md`; the professional end-user manual is `docs/UserGuide.md`.

## 2. Stack and layout

| Area | Details |
|---|---|
| Backend | `backend/` — FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, PostgreSQL. Strict gates: `mypy --strict`, `ruff`, `black`, `isort`, `pytest`. |
| Frontend | `frontend/` — Next.js 15 App Router, React 19, TanStack Query, Tailwind v4 (oklch tokens in `src/app/globals.css`), Shadcn UI, Jest. Gates: `tsc`, `eslint`, `jest`. |
| Run backend | `cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload` — health check at `/api/v1/health` (not `/health`). |
| Run frontend | `cd frontend; npm run dev` |
| Migrations | `backend/alembic/versions/` — dev DB currently at head **0031**. |

### Sample sign-ins (dev seed)
- `admin@example.com` — password from `backend/.env` `DEFAULT_ADMIN_PASSWORD` (README default `Admin@12345`).
- Employees/managers/recruiters (`Employee@12345`): `emp.078989@jsan.example` (JSAN71),
  `mgr.078989@jsan.example` (JSAN70), `emp.032017@…`, `recruiter.022842@…`, `recruiter.472073@…`.
- "Unable to login" has so far always meant the backend was not running.

## 3. House conventions (follow these, they bite otherwise)

**Backend**
- Migrations use the house helpers: `_audit_columns`, `_actor_constraints`, `_add_permissions`
  (ON CONFLICT) and `_grant_permissions` from `SYSTEM_ROLES`. Status check constraints are
  dropped by name-suffix in a `DO $$` block because early ones (0027) were double-wrapped and
  Postgres rewrites `IN` → `= ANY`.
- Permissions are code-defined in `app/core/permissions.py` (`PermissionAction`). Scoping
  helpers: `require`, `require_org_wide`, `require_self_or`, `require_team_scope`.
  **Payroll inverts scoping** — the reporting line grants nothing; only explicit payroll
  permissions (41 actions) do.
- Set `preserve_writes = True` on `ConflictError`/`NotFoundError` when a failure audit row must
  survive the rollback.
- Money is `Decimal` quantised to 2 dp (`_ZERO = Decimal("0.00")`); serialisation must give
  `"0.00"`, not `"0"`.
- Relationships that would join too many columns (e.g. `Payslip.snapshot/run`) use
  `lazy="selectin"` — otherwise Postgres throws `TooManyColumnsError` (>1664 columns).
- Mint UUIDs client-side (`id=uuid.uuid4()`) when a read schema is built before flush.
- **Payroll only reads employees whose `employment_status` is `active`** (plus notice_period/
  resigned/inactive for exits) -- `confirmed` and `probation` people are silently absent from
  inputs and runs (`PayrollSourceReader.employees_joined_by`). Seed/test data meant for payroll
  must be `active`.
- Sick leave (`SL`) requires a supporting document id; the offer schema needs Basic/HRA/Special
  Allowance components summing exactly to CTC; onboarding conversion needs seven approved
  candidate documents with fixed names; a job opening can only be created while the requisition
  is `approved` (not yet `open`); allocations must end inside the project window.
- FastAPI treats a Pydantic query model as a body when another `Query` param is present —
  fold extra params into the model (see `ReportExportParams`).

**Frontend**
- `Page<T>` is `{ items, meta.total_items }`; `DataTable` takes `getRowId(row)`.
- Narrow errors with `instanceof AppError`; `restrict-template-expressions` is on — wrap
  numbers with `String()`.
- Blob downloads go through `apiClient` with `responseType: 'blob'`.
- Routes live in `config/site.ts`, sidebar entries in `config/navigation.ts` (with per-page
  permission gating).

**Editing files**
- Many files are **CRLF**. Naive `\n`-based patch scripts silently do nothing — use
  CRLF-aware replacements and re-read a file before overwriting it.

**Testing**
- Full backend pytest is **~30–47 min** and needs an exclusive test DB. Before re-running,
  find and kill stale `pytest` processes (Get-CimInstance Win32_Process filtered on the
  command line, then taskkill). Background runs get orphaned when the session restarts.
  Do not use `-p no:cacheprovider` (conflicts with project config).
- Last confirmed full-suite result: **1191 passed** (after Payroll Phase 6) + Phase 7's 24 new
  tests. Phase 8's own 12 tests pass and all static gates pass, but its full-suite regression
  run was orphaned and never confirmed — **re-run when a 45-minute window is free.**
- Jest: 384 tests, one known timing flake; rerun clean.

## 4. Payroll — the shape of what Claude built (phases 5–8)

Run status machine: `draft → calculating → requires_review/calculated → in_review →
review_complete → pending_approval → (returned) → approved → finalized`. Locked statuses
reject edits and audit the attempt. Finalisation writes denormalised
`PayrollFinalSnapshot` rows that later reports and payslips read from.

| Phase | Backend | Frontend |
|---|---|---|
| 5 Review & adjustments | `payroll_review_service.py`, migration 0028, 21 tests | review screens under `features/payroll/components` |
| 6 Approval & finalisation | `payroll_approval_service.py`, migration 0029, 11 tests | approval + history components |
| 7 Payslips & self-service | `payslip_service.py` (reportlab PDF, numbers `PS-YYYY-MM-EMPCODE`, amount-to-words in Indian lakh/crore), migration 0030, 14 + 10 unit tests | `payslip-document`, `my-payslips-page`, `payroll-payslips-page` |
| 8 Reports & Full & Final | `payroll_report_service.py` (CSV/XLSX via openpyxl), `payroll_settlement_service.py` (draft → under_review → approved → settled; syncs offboarding `FinalSettlementTracking`), routes in `payroll_reports.py`, migration 0031, 12 tests | `payroll-reports-page`, `payroll-settlements-page`, `payroll-settlement-detail-page`, `my-settlement-page` |

Constraints the owner set: no module redesigns, no Docker, no bank/tax/statutory features.
The Phase 8 12-item close-out report was requested but not yet delivered — write it if asked.

## 5. UI work done in the latest sessions

- **Dashboard** (`features/dashboard/components/home-dashboard.tsx`): rebuilt, then
  simplified after feedback ("clumsy"). Now: 4 stat cards, headcount area chart, attendance
  donut, hires/leave bar charts, month-by-month table, "waiting on somebody" list. Removed on
  request: tabs, quick-access shortcuts (file deleted), platform status card
  (`platform-status-card.tsx` is now **unused but still on disk** — safe to delete).
- **Theme** (`src/app/globals.css`): soft-light identity from the owner's reference
  screenshot — pale grey page, white rounded cards, near-black text, one accent hue,
  `--chart-1..6`, `--radius: 1rem`, matching dark mode. Accent history: coral → **blue**
  (2026-08-27, `oklch(0.55 0.2 262)` light / `oklch(0.7 0.16 258)` dark; greys got a cool
  bias, hue 250). A heavier "more blue" pass (blue-tinted page, navy text, deep-blue
  sidebar) was **rejected** by the owner on 2026-08-27 and rolled back the same day. Current
  state: neutral cool-grey page, white cards and a white navigation rail; blue only in
  `--primary` (`oklch(0.52 0.22 262)`), the active nav pill (`--primary-subtle`), links,
  focus rings and an all-blue chart ramp. `--sidebar*` tokens exist (aliased to card/
  foreground tokens) and are what `sidebar.tsx`, `mobile-nav.tsx`, `sidebar-nav.tsx` use;
  `Brand` keeps an `inverted` prop (unused now). Do not tint page surfaces or text with
  the accent hue again. Later on 2026-08-27 the owner asked for white + blue as primary **plus** red / green / orange: status tokens were made vivid (red 27, green 150, orange 55, with dark-mode overrides), charts are blue/green/orange/red/purple/teal, `StatCard` gained a `tone` prop (blue|green|orange|red|purple), `ChartPoint.color` lets a donut slice carry a semantic colour, and the dashboard uses all of this (present=green, absent=red, on leave=orange). Do not tint page surfaces or text with — the owner wants blue as an accent, not a wash.
- **Motion**: keyframes `rise`, `grow-up`, `draw`, `appear`; `.animate-rise`, `.stagger`
  child delays, chart classes; `prefers-reduced-motion` override.
  `components/common/page-transition.tsx` (keyed on pathname) is wired into `app-shell.tsx`.
- **Components restyled**: pill buttons with press scale, borderless soft-shadow cards,
  filled inputs/textarea/select (`bg-muted/60`, `h-11`, focus → background), `FormSection`
  with accent-dot header, sticky frosted `FormActions`, hover-lift `StatCard`.
- **Growth panel** (2026-08-27): `features/dashboard/components/growth-glance.tsx` rebuilds the
  owner's "JSAN growth at a glance" infographic as a native card. First version (coloured tiles,
  stepped columns, pill ribbon) was called unprofessional; v2 is restrained: eyebrow + sentence-case
  title, a 4-figure stat strip with hairline dividers, an area line chart (countries) and a bar
  chart (workforce) in the single primary blue, facts as muted text. Charts gained `formatValue`. Shown to every role at the top of the home
  dashboard. Figures are marketing constants at the top of the file -- edit there to update.
- **Tables** (2026-08-27): `ui/table.tsx` primitives restyled (tinted uppercase header band,
  hairline rows, roomier cells); `DataTable` renders on a white rounded card surface with a
  `flush` prop for tables already inside a Card (dashboard uses it); interactive rows get a
  blue-tinted hover; right-aligned columns are tabular-nums; pagination lost its top rule.
- **Charts**: dependency-free SVG `BarChart`, `LineChart` (area), `DonutChart`, `Gauge` in
  `components/common/charts.tsx`; every chart also renders its figures as text.
- **User guide**: `docs/UserGuide.md` (17 sections) and a published HTML artifact
  ("People360 User Guide").
- **Demo data**: `backend/app/cli/seed_demo.py` (2026-08-27) walks every module through the
  real services -- 12 demo people (`*@demo.jsan.example`, password `Demo@12345`), documents,
  workforce history, projects/timesheets, performance, a full hiring story (requisition →
  offer → onboarding), assets, helpdesk/announcements, payroll (last month finalized with
  payslips, this month in review) and one offboarding with a settled F&F. Additive and
  re-runnable (ancok tables ahor checks per section); each step runs in a savepoint and failures are
  listed at the end. Runs ~10-15 min because of the audited attendance backfill. Employees
  without compensation get a `not_eligible` payroll setting so the run can finalize.

## 6. How the owner likes to work

- Builds in numbered phases with explicit specs; wants a report at the end of a phase and
  then "STOP" — do not continue into unrequested scope.
- Prefers uncluttered UI: reacted against tabs, jump-link pills, quick-access grids and
  status widgets. Fewer, clearer things win.
- Likes premium visuals (currently a blue accent, previously coral) and tasteful animation; asked for forms to be
  "more stylish".
- Asks short operational questions often ("command to run backend", "credentials") —
  answer directly.

## 6b. Deployment (Railway) -- added 2026-08-27
- `backend/Dockerfile` (python:3.12-slim, build context = repo root because requirements.txt lives
  there) + `backend/docker-entrypoint.sh` (alembic upgrade → `seed --sample-data` if SEED_ON_START →
  optional `seed_demo` if SEED_DEMO_DATA → uvicorn on $PORT, 2 workers, proxy headers).
- `frontend/Dockerfile` (node:22-alpine, NEXT_PUBLIC_* as build ARGs, `output: 'standalone'` added to
  next.config.ts, `frontend/public/` created). `.dockerignore`, `.gitattributes` (LF for *.sh).
- `railway.api.json` / `railway.web.json` at the repo root: each service sets its config-as-code
  path to one of these; health checks `/api/v1/health` and `/login`; watchPatterns per service.
- `config.normalise_database_url()` rewrites `postgres(ql)://` → `postgresql+asyncpg://` and
  `sslmode=` → `ssl=require`, so Railway's `${{Postgres.DATABASE_URL}}` works as pasted.
- Production guards in Settings require: strong SECRET_KEY, non-default admin password,
  COOKIE_SECURE=true, TRUSTED_HOSTS (include healthcheck.railway.app), real CORS origin. Cross-domain
  refresh cookie needs COOKIE_SAMESITE=none. Uploads need a volume at /data/uploads (UPLOAD_DIR).
- Guide: `docs/RailwayDeployment.md`; README has a pointer.

## 7. Open items

1. Confirm the full backend regression after Phase 8 (needs a free ~45-min window).
2. Deliver the Phase 8 12-item close-out report if requested.
3. Delete `frontend/src/components/common/platform-status-card.tsx` (unused).
4. Keep `docs/UserGuide.md` in step with any new screens.
