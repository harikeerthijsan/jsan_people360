# Folder structure

The Phase 5 Document Vault follows the same feature boundaries: backend models,
schemas, repositories, services, storage adapters and versioned routes live
under `backend/app`; frontend screens, API bindings, hooks, schemas and types
live under `frontend/src/features/documents`; reusable upload, preview, card,
status and timeline components live under `frontend/src/components/common`.

An annotated map of the repository, and where new code belongs.

---

## Repository root

```
jsan-people360/
├── backend/                    FastAPI application
├── frontend/                   Next.js application
├── docs/                       Documentation
├── scripts/                    PowerShell developer scripts
├── uploads/                    Runtime file storage (contents git-ignored)
├── .vscode/                    Shared editor settings and recommendations
├── .gitignore
├── .pre-commit-config.yaml     Format, lint and guard-rail hooks
├── README.md
└── requirements.txt            Backend Python dependencies (single source)
```

---

## Backend

```
backend/
├── alembic/                          Database migrations — the only way the schema changes
│   ├── versions/
│   │   ├── 2026_07_31_0900-0001_initial_platform_schema.py
│   │   ├── 2026_07_31_1106-0002_org_masters_add_organization_master_data.py
│   │   ├── 2026_07_31_1358-0003_user_management_extend_users.py
│   │   └── 2026_08_03_0834-0004_employee_master_employee_master.py
│   ├── env.py                        Async migration environment; reads the URL from settings
│   ├── script.py.mako                Template for new revisions
│   └── README.md                     Migration workflow and conventions
│
├── app/
│   ├── api/                          ── HTTP LAYER ──
│   │   ├── deps.py                   Dependency injection: the composition root.
│   │   │                             Session (unit of work), repositories, services,
│   │   │                             current user, request origin.
│   │   ├── master_router.py          Factory building the six endpoints per master
│   │   └── v1/
│   │       ├── router.py             Aggregates every v1 router (register new modules here)
│   │       └── routes/
│   │           ├── auth.py           Sign in, refresh, sign out, password recovery
│   │           ├── health.py         Liveness and readiness probes
│   │           ├── employees.py      Employee master (23 operations)
│   │           ├── organization.py   All nine masters (55 operations)
│   │           └── users.py          User directory, lifecycle, self-service profile
│   │
│   ├── core/                         ── CROSS-CUTTING ──
│   │   ├── config.py                 Pydantic Settings; the only reader of the environment
│   │   ├── context.py                Request-scoped contextvars (request id, actor, IP)
│   │   ├── error_handlers.py         Global handlers producing the standard envelope
│   │   ├── exceptions.py             Domain exception hierarchy
│   │   ├── logging.py                JSON and console formatters, request correlation
│   │   └── security.py               Password hashing, JWTs, opaque tokens
│   │
│   ├── db/                           ── PERSISTENCE INFRASTRUCTURE ──
│   │   ├── base.py                   Imports every model so Alembic sees the full schema
│   │   ├── base_class.py             Declarative Base, naming convention, eager_defaults
│   │   ├── mixins.py                 UUID PK, timestamps, audit and soft-delete columns
│   │   └── session.py                Async engine and session factory
│   │
│   ├── middleware/                   ── ASGI MIDDLEWARE ──
│   │   ├── request_context.py        Request id, access logging, timing
│   │   └── security_headers.py       CSP, HSTS, frame and sniffing protections
│   │
│   ├── models/                       ── ORM MODELS ──
│   │   ├── app_setting.py            Operator-editable runtime configuration
│   │   ├── audit_log.py              Append-only trail; AuditAction enum
│   │   ├── refresh_token.py          Rotating session tokens
│   │   ├── user.py                   Accounts, credentials, lockout, directory record
│   │   ├── enums.py                  RecordStatus, Gender, EmploymentStatus, WorkMode, …
│   │   ├── mixins.py                 Master-data columns; CI unique index helpers
│   │   │                             ── Employee master ──
│   │   ├── employee.py               The central HRMS entity
│   │   ├── employee_address.py       Current and permanent
│   │   ├── employee_bank_detail.py   Sensitive; its own table by design
│   │   ├── employee_identification.py  Sensitive; statutory identifiers
│   │   ├── employment_history.py     Append-only placement history
│   │   │                             ── Organization master data ──
│   │   ├── organization.py           Legal entity / company profile
│   │   ├── business_unit.py          Top of the hierarchy
│   │   ├── team.py                   Belongs to a business unit
│   │   ├── designation.py            Job title within a business unit
│   │   ├── location.py               Office or work site
│   │   ├── employment_type.py        Full time, contract, …
│   │   └── grade.py                  Compensation / seniority band
│   │
│   ├── repositories/                 ── DATA ACCESS — the only place SQL is written ──
│   │   ├── base.py                   Generic CRUD with soft-delete filtering
│   │   ├── employee_repository.py    Employee queries, cycle detection, aggregates
│   │   ├── master_repository.py      Paged search, scoping, CI uniqueness lookups
│   │   ├── organization_repository.py  The nine master repositories
│   │   ├── app_setting_repository.py
│   │   ├── audit_log_repository.py
│   │   ├── refresh_token_repository.py
│   │   └── user_repository.py
│   │
│   ├── schemas/                      ── VALIDATION BOUNDARY (Pydantic v2) ──
│   │   ├── auth.py                   Login, refresh, password recovery payloads
│   │   ├── common.py                 APIResponse envelope, pagination, error detail
│   │   ├── health.py                 Probe payloads
│   │   ├── employee.py               Employee writes, reads, masking, lifecycle payloads
│   │   ├── masters.py                Shared master field types and list parameters
│   │   ├── organization.py …         One file per master (nine in total)
│   │   └── user.py                   Admin vs self-service writes, password policy
│   │
│   ├── services/                     ── BUSINESS LOGIC — all rules live here ──
│   │   ├── audit_service.py          Writes the audit trail; never raises
│   │   ├── auth_service.py           Sign-in, refresh, sign-out, password recovery
│   │   ├── employee_service.py       Employee rules; the one path history flows through
│   │   ├── employee_dashboard_service.py  Headcount aggregates
│   │   ├── employee_export_service.py     CSV and XLSX
│   │   ├── health_service.py         Dependency probes
│   │   ├── mail_service.py           Transactional email (console fallback)
│   │   ├── master_service.py         Shared master CRUD, duplicates, archive/restore
│   │   ├── organization_service.py   The nine master services
│   │   ├── token_service.py          Token issue, rotation, revocation, reuse detection
│   │   └── user_service.py           Account lifecycle, guards, password reset, profile
│   │
│   ├── utils/                        Stateless helpers
│   │   ├── datetime.py               Timezone-aware UTC helpers
│   │   ├── masking.py                Masks for sensitive identifiers
│   │   └── strings.py                Email normalisation, masking, slugs
│   │
│   ├── cli/
│   │   ├── seed.py                   Bootstrap administrator and default settings
│   │   └── seed_organization.py      Sample master data for development
│   │
│   └── main.py                       Application factory, middleware, lifespan
│
├── tests/
│   ├── conftest.py                   Fixtures: migrated test DB, rollback session, HTTP client
│   ├── unit/                         Pure logic — no I/O, always runs
│   │   ├── test_employee_schemas.py
│   │   ├── test_master_schemas.py
│   │   ├── test_schemas.py
│   │   ├── test_security.py
│   │   ├── test_user_schemas.py
│   │   └── test_utils.py
│   └── integration/                  Real HTTP stack against real PostgreSQL
│       ├── test_auth.py
│       ├── test_employees.py
│       ├── test_health.py
│       ├── test_organization_masters.py
│       ├── test_password_recovery.py
│       └── test_users.py
│
├── .env.example                      Template; copy to .env (git-ignored)
├── alembic.ini
├── pyproject.toml                    Black, isort, Ruff, mypy, pytest, coverage
└── requirements.txt                  Defers to ../requirements.txt
```

### Where backend code goes

| You are adding | Put it in |
| --- | --- |
| An endpoint | `app/api/v1/routes/<module>.py` + register in `router.py` |
| A business rule | `app/services/<module>_service.py` |
| A query | `app/repositories/<module>_repository.py` |
| A table | `app/models/<module>.py` + export + Alembic revision |
| A request/response shape | `app/schemas/<module>.py` |
| A dependency provider | `app/api/deps.py` |
| A reusable helper | `app/utils/` |
| A configuration value | `app/core/config.py` + `.env.example` |

---

## Frontend

```
frontend/
├── src/
│   ├── app/                          ── ROUTES (thin; they compose features) ──
│   │   ├── layout.tsx                Root layout: fonts, providers, skip link
│   │   ├── page.tsx                  Redirects to the dashboard
│   │   ├── globals.css               Tailwind v4 config and all design tokens
│   │   ├── loading.tsx               Route streaming fallback
│   │   ├── error.tsx                 Route error boundary (500)
│   │   ├── global-error.tsx          Root layout error boundary
│   │   ├── not-found.tsx             404
│   │   │
│   │   ├── (auth)/                   Unauthenticated route group
│   │   │   ├── login/page.tsx
│   │   │   ├── forgot-password/page.tsx
│   │   │   └── reset-password/page.tsx
│   │   │
│   │   └── (app)/                    Authenticated route group
│   │       ├── layout.tsx            Wraps everything in AppShell
│   │       ├── dashboard/
│   │       │   ├── page.tsx
│   │       │   └── loading.tsx       Layout-matching skeleton
│   │       ├── organization/         Nine masters, five page files
│   │       │   ├── page.tsx              Overview of the masters
│   │       │   └── [master]/
│   │       │       ├── page.tsx          List
│   │       │       ├── new/page.tsx      Create
│   │       │       └── [id]/
│   │       │           ├── page.tsx          Detail
│   │       │           └── edit/page.tsx     Edit
│   │       ├── employees/                Employee master
│   │       │   ├── page.tsx                  Directory
│   │       │   ├── dashboard/page.tsx        Headcount and composition
│   │       │   ├── new/page.tsx              Create
│   │       │   └── [id]/
│   │       │       ├── page.tsx              Profile (8 tabs)
│   │       │       └── edit/page.tsx         Edit
│   │       ├── users/                    User directory
│   │       │   ├── page.tsx                  List
│   │       │   ├── new/page.tsx              Create
│   │       │   └── [id]/
│   │       │       ├── page.tsx              Detail
│   │       │       └── edit/page.tsx         Edit
│   │       ├── profile/page.tsx      Self-service: own details and password
│   │       └── settings/page.tsx
│   │
│   ├── components/
│   │   ├── ui/                       Shadcn/Radix primitives — generic, no product knowledge
│   │   │   ├── alert.tsx        avatar.tsx     badge.tsx      button.tsx
│   │   │   ├── card.tsx         checkbox.tsx   dialog.tsx     dropdown-menu.tsx
│   │   │   ├── form.tsx         input.tsx      label.tsx      select.tsx
│   │   │   ├── separator.tsx    sheet.tsx      skeleton.tsx   sonner.tsx
│   │   │   ├── table.tsx        textarea.tsx   tooltip.tsx
│   │   │
│   │   ├── common/                   Composed, product-level reusables
│   │   │   ├── action-menu.tsx       Data-driven row actions dropdown
│   │   │   ├── data-table.tsx        Loading/error/empty/populated states + sorting
│   │   │   ├── employee-card.tsx     A person as a compact card
│   │   │   ├── employment-status-badge.tsx  The six lifecycle states
│   │   │   ├── detail-view.tsx       DetailSection — labelled read-only fields
│   │   │   ├── empty-state.tsx
│   │   │   ├── error-state.tsx
│   │   │   ├── form-layout.tsx       FormLayout, FormSection, FormActions
│   │   │   ├── loading-state.tsx     Spinner plus shape-matched skeletons
│   │   │   ├── modal.tsx             Modal and ConfirmDialog
│   │   │   ├── number-field.tsx      RHF-bound numeric input
│   │   │   ├── masked-value.tsx      A sensitive value with an audited reveal
│   │   │   ├── page-header.tsx
│   │   │   ├── pagination.tsx        Page controls plus range summary
│   │   │   ├── profile-card.tsx      Identity banner for a person's page
│   │   │   ├── search-bar.tsx        Debounced search input
│   │   │   ├── select-field.tsx      RHF-bound select with loading/empty states
│   │   │   ├── stat-card.tsx
│   │   │   ├── status-badge.tsx      active / inactive / archived
│   │   │   ├── text-field.tsx        RHF-bound input with label, error and ARIA wiring
│   │   │   ├── tabs.tsx              URL-backed tabs, WAI-ARIA keyboard pattern
│   │   │   ├── textarea-field.tsx    RHF-bound multi-line input
│   │   │   ├── timeline.tsx          Vertical timeline of dated events
│   │   │   └── user-avatar.tsx       UserAvatar and UserIdentity
│   │   │
│   │   ├── layout/                   The application shell
│   │   │   ├── app-shell.tsx         Frame plus session guard
│   │   │   ├── auth-shell.tsx        Split layout for unauthenticated pages
│   │   │   ├── brand.tsx    breadcrumbs.tsx   header.tsx
│   │   │   ├── mobile-nav.tsx        Drawer navigation below `lg`
│   │   │   ├── sidebar.tsx           Permanent desktop sidebar
│   │   │   ├── sidebar-nav.tsx       Grouped nav, shared by both
│   │   │   └── user-menu.tsx         Account menu and sign-out
│   │   │
│   │   └── providers/
│   │       ├── app-providers.tsx     Single composition point
│   │       ├── auth-provider.tsx     Session state, bootstrap, login/logout
│   │       └── query-provider.tsx    TanStack Query client
│   │
│   ├── features/                     ── PRODUCT CODE LIVES HERE ──
│   │   ├── auth/
│   │   │   ├── api/auth.api.ts       Transport only
│   │   │   ├── components/           login, forgot, reset, change-password, profile forms
│   │   │   ├── hooks/                TanStack Query mutations
│   │   │   ├── schemas/              Zod schemas and inferred types
│   │   │   └── types/                Domain types mirroring the API
│   │   ├── organization/             ── ORGANIZATION MASTER DATA ──
│   │   │   ├── config/
│   │   │   │   └── master-registry.tsx   The one declaration driving every screen
│   │   │   ├── components/
│   │   │   │   ├── master-list-page.tsx      Search, filter, sort, page, archive
│   │   │   │   ├── master-form-page.tsx      Create and edit
│   │   │   │   ├── master-detail-page.tsx    Read-only view
│   │   │   │   └── master-form-field.tsx     Field type -> component
│   │   │   ├── hooks/
│   │   │   │   ├── use-masters.ts            Queries and mutations
│   │   │   │   └── use-master-list-state.ts  List state, stored in the URL
│   │   │   ├── api/organization.api.ts   One client, bound to a slug
│   │   │   ├── schemas/              Zod, mirroring the server rules
│   │   │   └── types/
│   │   ├── employees/                ── EMPLOYEE MASTER ──
│   │   │   ├── components/
│   │   │   │   ├── employee-list-page.tsx     Directory, filters, export
│   │   │   │   ├── employee-form.tsx          Six sections, create and edit
│   │   │   │   ├── employee-form-page.tsx     Create and edit wrappers
│   │   │   │   ├── employee-profile-page.tsx  The tabbed profile
│   │   │   │   ├── employee-dashboard-page.tsx
│   │   │   │   └── lifecycle-dialogs.tsx      One dialog per action
│   │   │   ├── hooks/use-employees.ts
│   │   │   ├── api/employees.api.ts
│   │   │   ├── schemas/
│   │   │   └── types/
│   │   ├── users/                    ── USER MANAGEMENT ──
│   │   │   ├── components/
│   │   │   │   ├── user-list-page.tsx        Directory: search, filter, lifecycle
│   │   │   │   ├── user-form.tsx             Four sections, shared by create and edit
│   │   │   │   ├── user-form-page.tsx        UserCreatePage and UserEditPage
│   │   │   │   ├── user-detail-page.tsx      Read-only view plus actions
│   │   │   │   ├── reset-password-dialog.tsx
│   │   │   │   └── profile-form.tsx          Self-service
│   │   │   ├── hooks/use-users.ts    Queries plus one lifecycle mutation factory
│   │   │   ├── api/users.api.ts
│   │   │   ├── schemas/              Zod, mirroring the server rules
│   │   │   └── types/                Re-exports the shared record type
│   │   └── dashboard/
│   │       └── components/           Platform status card, module roadmap
│   │
│   ├── config/
│   │   ├── navigation.ts             Sidebar structure (add modules here)
│   │   └── site.ts                   Product metadata and route constants
│   │
│   ├── hooks/                        Cross-feature hooks
│   │   ├── use-breadcrumbs.ts
│   │   ├── use-disclosure.ts
│   │   └── use-media-query.ts
│   │
│   ├── types/                        Types more than one feature needs
│   │   └── user.ts                   UserRecord — used by both `auth` and `users`
│   │
│   └── lib/
│       ├── api/
│       │   ├── client.ts             Axios instance, single-flight refresh, typed helpers
│       │   ├── endpoints.ts          Every API path
│       │   └── types.ts              ApiResponse envelope, pagination
│       ├── auth/token-store.ts       In-memory access token
│       ├── env.ts                    Zod-validated public environment
│       ├── errors.ts                 AppError and normalisation
│       ├── query-client.ts           Cache policy and query keys
│       └── utils.ts                  cn(), formatting, initials
│
├── .env.example                      Template; copy to .env.local (git-ignored)
├── components.json                   Shadcn CLI configuration
├── eslint.config.mjs                 Flat config with type-aware rules
├── jest.config.mjs
├── jest.setup.ts
├── next.config.ts
├── package.json
├── postcss.config.mjs
├── .prettierrc.json
└── tsconfig.json                     Strict mode, `@/*` path alias
```

### Where frontend code goes

| You are adding | Put it in |
| --- | --- |
| A page | `src/app/(app)/<module>/page.tsx` |
| Feature UI | `src/features/<module>/components/` |
| An API call | `src/features/<module>/api/<module>.api.ts` |
| A data hook | `src/features/<module>/hooks/` |
| Validation | `src/features/<module>/schemas/` |
| A generic primitive | `src/components/ui/` |
| A reusable product component | `src/components/common/` |
| A cross-feature hook | `src/hooks/` |
| A type two features share | `src/types/` |
| A nav entry | `src/config/navigation.ts` |
| A design token | `src/app/globals.css` |

**Tests are colocated** in `__tests__/` next to the code they cover.

**Features must not import each other.** When two need the same type, it moves to
`src/types/` — which is why `UserRecord` lives there rather than inside
`features/users/`, with `auth` and `users` both re-exporting it.

---

## Access control

Permissions are defined in code and mirrored into the database; roles are data.

```
backend/app/
├── core/permissions.py                 The catalogue: 19 modules, 73 permissions,
│                                       8 system roles. The single source of truth.
├── models/rbac.py                      roles, permissions, role_permissions, user_roles
├── schemas/rbac.py                     Role CRUD + the /auth/me session payload
├── repositories/rbac_repository.py     Four repositories
├── services/
│   ├── authorization_service.py        Resolves what a user may do
│   ├── scope_service.py                Resolves *whose* records they may reach
│   └── role_service.py                 Role CRUD + the lock-out protections
├── api/deps.py                         require(), require_self_or(),
│                                       require_team_scope() -- the route guards
└── api/v1/routes/rbac.py               Role administration endpoints

frontend/src/
├── components/common/can.tsx           <Can>, usePermitted, <RequirePermission>
├── components/providers/auth-provider.tsx   Loads permissions with the session
├── config/navigation.ts                Each item declares its permission
└── features/roles/                     Role management screen
    ├── types.ts / api.ts / hooks.ts
    └── components/role-management-page.tsx
```

Adding a protected area is: a `Module` entry in `core/permissions.py`, a
`require(...)` on each route, a `permission` on the nav item.

---

## Workforce Operations

Attendance, leave and timesheets are one module because they are one day, so
they share a service and a router rather than being split three ways.

```
backend/app/
├── models/workforce.py                     Eleven tables
├── schemas/workforce.py                    Write, read and list-param schemas
├── repositories/workforce_repository.py    Ten repositories + analytics
├── services/workforce_service.py           The four rules live here
└── api/v1/routes/workforce.py              27 endpoints

frontend/src/
├── features/workforce/
│   ├── types.ts                            Domain types and label maps
│   ├── schema.ts                           Zod mirrors of the server rules
│   ├── schema.test.ts                      21 tests over those mirrors
│   ├── api.ts                              Transport only
│   ├── hooks.ts                            Queries and mutations
│   └── components/                         Thirteen screens
│       ├── employee-picker.tsx                 Shared "whose record" control
│       ├── workforce-dashboard.tsx
│       ├── attendance-register.tsx             Register + check in/out
│       ├── attendance-calendar-page.tsx
│       ├── regularizations-page.tsx
│       ├── shifts-page.tsx
│       ├── shift-assignments-page.tsx
│       ├── leave-page.tsx                      Balances above, requests below
│       ├── leave-approvals-page.tsx
│       ├── leave-types-page.tsx
│       ├── holidays-page.tsx
│       ├── timesheet-page.tsx                  The weekly grid
│       ├── timesheet-approvals-page.tsx
│       └── workforce-reports-page.tsx
├── components/common/workforce-widgets.tsx  Badges, balance card, calendar
└── app/(app)/                               Thirteen four-line route files
    ├── attendance/{,register,calendar,regularizations,reports}/page.tsx
    ├── shifts/{,assignments}/page.tsx
    ├── leave/{,approvals,types,holidays}/page.tsx
    └── timesheets/{,approvals}/page.tsx
```

---

## Naming conventions

| Kind | Convention | Example |
| --- | --- | --- |
| Python modules | `snake_case` | `auth_service.py` |
| Python classes | `PascalCase` | `AuthService` |
| Python functions | `snake_case` | `request_password_reset` |
| Database tables | `snake_case`, plural | `refresh_tokens` |
| TypeScript files | `kebab-case` | `login-form.tsx` |
| React components | `PascalCase` | `LoginForm` |
| Hooks | `use-` prefix | `use-breadcrumbs.ts` |
| Types / interfaces | `PascalCase` | `LoginResult` |
| API fields | `snake_case` (matches the backend) | `full_name` |

API payload fields stay `snake_case` on both sides. Translating between casings
at the boundary adds a mapping layer that must be maintained forever and buys
nothing.
