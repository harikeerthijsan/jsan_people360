# Architecture

How JSAN People360 is put together, and why. This document explains the
reasoning behind the structure so that future modules extend the foundation
rather than working around it.

---

## 1. Principles

1. **Dependencies point inward.** HTTP knows about services; services know about
   repositories; repositories know about models. Nothing points back out. A
   service can be tested with a fake repository and no HTTP stack at all.
2. **One responsibility per layer.** If a route contains an `if` that encodes a
   business rule, it belongs in a service. If a service builds a `SELECT`, it
   belongs in a repository.
3. **The database schema is a versioned artefact.** Alembic owns it exclusively.
4. **Validation happens at the boundary.** Untrusted input becomes a typed model
   before any business code sees it.
5. **Modules are independent.** A feature module adds files; it should not need
   to modify existing ones beyond one router registration and one nav entry.

---

## 2. System shape

```
┌────────────────────────────┐         ┌──────────────────────────────┐
│  Next.js 15 (App Router)   │         │  FastAPI                     │
│  localhost:3000            │  HTTPS  │  localhost:8000              │
│                            │ ──────► │                              │
│  • Feature-based modules   │  JSON   │  • /api/v1                   │
│  • TanStack Query cache    │ ◄────── │  • Clean Architecture        │
│  • Access token in memory  │         │  • Async SQLAlchemy 2        │
└────────────────────────────┘         └───────────────┬──────────────┘
                                                       │ asyncpg
                                                       ▼
                                            ┌──────────────────────┐
                                            │  PostgreSQL          │
                                            │  schema via Alembic  │
                                            └──────────────────────┘
```

---

## 3. Backend layers

```
   HTTP request
        │
        ▼
┌───────────────────┐
│  Middleware       │  request id, access log, security headers, CORS, gzip
├───────────────────┤
│  Routes           │  app/api/v1/routes/    ← HTTP only
├───────────────────┤
│  Dependencies     │  app/api/deps.py       ← composition root, auth, session
├───────────────────┤
│  Schemas          │  app/schemas/          ← Pydantic validation boundary
├───────────────────┤
│  Services         │  app/services/         ← ALL business rules
├───────────────────┤
│  Repositories     │  app/repositories/     ← the only code that issues SQL
├───────────────────┤
│  Models           │  app/models/           ← SQLAlchemy ORM
└───────────────────┘
        │
        ▼
    PostgreSQL
```

### What belongs where

| Layer | Responsibility | Never does |
| --- | --- | --- |
| **Routes** | Parse and validate input, call one service, wrap the result in the envelope, manage cookies | Business rules, SQL, error formatting |
| **Dependencies** | Construct services and repositories, resolve the current user, own the transaction boundary | Business rules |
| **Schemas** | Shape and validate requests and responses | Persistence, I/O |
| **Services** | Enforce business rules, orchestrate repositories, emit audit entries | Build SQL, touch `Request`/`Response` |
| **Repositories** | Query and persist entities | Business decisions, commits |
| **Models** | Define tables, columns and relationships | Business rules, queries |

### Worked example: sign-in

```
POST /api/v1/auth/login
  │
  ├─ RequestContextMiddleware   assigns a request id, starts the access log timer
  ├─ CORSMiddleware             validates the browser origin
  │
  ├─ routes/auth.py             LoginRequest validates and normalises the payload
  │                             (via get_db_session, which opens the transaction)
  │
  ├─ AuthService.login()        • look up the account
  │                             • equalise timing for unknown emails
  │                             • check the lockout window
  │                             • verify the password
  │                             • reset counters, record sign-in telemetry
  │                             • ask TokenService for a session
  │                             • write an audit entry
  │
  ├─ TokenService.issue_session()   mints the JWT, persists the hashed refresh token
  ├─ UserRepository / RefreshTokenRepository   the SQL
  │
  ├─ routes/auth.py             sets the HttpOnly refresh cookie, builds APIResponse
  └─ get_db_session             commits on success, rolls back on any exception
```

Note what the route does *not* do: no password checks, no lockout logic, no
token minting, no commits.

---

## 4. Transactions

The request-scoped session in `app/api/deps.py` is the unit of work:

```python
async def get_db_session() -> AsyncIterator[AsyncSession]:
    session = SessionFactory()
    try:
        yield session
        await session.commit()      # endpoint returned normally
    except Exception:
        await session.rollback()    # any failure, anywhere
        raise
    finally:
        await session.close()
```

Consequences worth understanding:

- Services and repositories **never commit**. They `flush()` when they need a
  generated id, and that is all.
- A request either persists everything or nothing. If auditing succeeds but the
  business write fails, both are rolled back.
- Tests bind the session to an outer transaction and roll it back afterwards, so
  no test can pollute another.

---

## 5. Authentication

### Token strategy

| | Access token | Refresh token |
| --- | --- | --- |
| Format | Signed JWT (HS256) | Opaque random string (64 bytes) |
| Lifetime | 15 minutes | 7 days (28 with "keep me signed in") |
| Storage (client) | JavaScript memory | HttpOnly, SameSite cookie |
| Storage (server) | Not stored | SHA-256 digest in `refresh_tokens` |
| Sent as | `Authorization: Bearer …` | Automatically by the browser |

**Why the access token is not in `localStorage`.** Anything JavaScript can read,
an XSS payload can read. Holding it in a module-scoped variable means it dies
with the tab. The session survives a page reload because the app calls
`/auth/refresh` once on mount and the browser supplies the HttpOnly cookie —
which script cannot read.

**Why only the digest of the refresh token is stored.** A database dump then
contains nothing replayable.

### Rotation and theft detection

Every refresh rotates the token: the presented row is revoked and linked to its
replacement via `replaced_by_id`.

If an *already revoked* token is presented, that means two parties hold the same
token — the legitimate client and an attacker. The service cannot tell which is
which, so it revokes the entire family for that user and audits
`auth.token.reuse_detected`. Both parties must sign in again; the attacker gains
nothing.

The client cooperates with this: `lib/api/client.ts` funnels concurrent 401s
into a single in-flight refresh. Without that, three parallel requests failing at
once would fire three refreshes, two of which would look exactly like token
theft and would log the user out.

### Where authorisation lives

`get_current_user` in `app/api/deps.py` is the single choke point. Today it
answers only "is this a valid, active user?".

When RBAC arrives it will be a *separate* dependency layered on top —
`require_permission("employee.read")` — so existing routes need only add the new
dependency. No route changes shape.

### User enumeration

Sign-in and password reset are written so that a caller cannot learn whether an
account exists:

- An unknown email still costs a bcrypt verification (`dummy_password_verify`),
  so response times match.
- Unknown email and wrong password return the identical 401 body.
- `/auth/forgot-password` returns 200 with the same message either way.

---

## 6. Error handling

Every failure — domain error, validation error, database error, unhandled crash,
404, 500 — is converted into the standard envelope by handlers registered in
`app/core/error_handlers.py`.

```
AppException          → its own status, code and message
RequestValidationError→ 422 with field-level detail
ResponseValidationError→ 500 (our bug; details logged only)
StarletteHTTPException→ mapped status, friendly copy (covers 404, 405)
IntegrityError        → 409 "conflicts with existing data"
SQLAlchemyError       → 500, detail logged only
Exception             → 500, detail logged only
```

Two rules hold throughout:

1. **The `message` is written for a user.** Services raise
   `InvalidCredentialsError("Incorrect email or password.")`, not
   `ValueError("pwd mismatch uid=...")`.
2. **Internal detail never crosses the boundary.** Stack traces, SQL and driver
   messages are logged with the request id and replaced with neutral copy.

The frontend mirrors this: `lib/errors.ts` normalises every thrown value into an
`AppError`, so components render errors one way instead of branching on
provenance.

---

## 7. Logging

Structured logging, `console` format locally and single-line JSON in deployed
environments. A `RequestContextFilter` attaches the request id and actor id to
every record, so one request can be traced across the access log, service logs
and any exception.

Logged: authentication events, one line per request (method, path, status,
duration, client IP), warnings and every exception.

Never logged: passwords, tokens, or full email addresses in security contexts —
`mask_email()` exists for that.

> **A trap worth knowing.** Python's `LogRecord` reserves attribute names such as
> `created`, `message`, `module` and `args`. Passing one via `extra=` raises
> `KeyError` at the call site. Namespace your keys (`settings_created`, not
> `created`).

### Logs versus the audit trail

They answer different questions and have different lifetimes:

| | Logs | `audit_logs` |
| --- | --- | --- |
| Question | "What did the system do?" | "Who did what, to what, when?" |
| Audience | Engineers | Compliance, security, support |
| Store | stdout → log shipper | PostgreSQL |
| Retention | Days to weeks | Years |

---

## 8. Database conventions

Every table carries the same contract:

| Column | Purpose |
| --- | --- |
| `id` | UUID primary key, `gen_random_uuid()` |
| `created_at` / `updated_at` | `timestamptz`, database-generated |
| `created_by` / `updated_by` | FK to `users.id`, `ON DELETE SET NULL` |
| `deleted_at` / `deleted_by` | Soft delete; `NULL` means active |

Composed once in `app/db/mixins.py` as `AuditableBase`. New models inherit it and
get the whole contract.

**Soft delete.** `BaseRepository` filters `deleted_at IS NULL` on every read
unless `include_deleted=True`. HR data is subject to retention rules that a
`DELETE` would violate.

**Constraint naming.** `app/db/base_class.py` sets a naming convention on the
metadata. Without it, Alembic generates anonymous constraint names that cannot be
reliably dropped in a downgrade, which quietly makes migrations irreversible.

**`eager_defaults`.** `Base` sets `__mapper_args__ = {"eager_defaults": True}` so
server-generated values come back via `RETURNING` on the same statement.
Otherwise those columns are left expired and reload lazily on first access —
which under asyncio means blocking I/O outside a greenlet and a `MissingGreenlet`
error the moment a response model touches `updated_at`.

---

## 9. Frontend architecture

Feature-based, not type-based. Everything one feature needs lives together:

```
src/
├── app/            Next.js routes — thin; they compose features
│   ├── (auth)/     Unauthenticated route group
│   └── (app)/      Authenticated route group (wrapped in AppShell)
├── components/
│   ├── ui/         Shadcn primitives (Button, Input, Dialog, …)
│   ├── common/     Composed, product-level reusables (DataTable, EmptyState, …)
│   ├── layout/     The application shell
│   └── providers/  React context providers
├── features/       ← where product code goes
│   └── auth/
│       ├── api/        transport
│       ├── components/ feature UI
│       ├── hooks/      TanStack Query hooks
│       ├── schemas/    Zod validation
│       └── types/      domain types
├── config/         navigation, site metadata
├── hooks/          cross-feature hooks
└── lib/            api client, errors, query client, utils
```

**Why.** Adding "Employees" means creating `features/employees/` and two files
outside it (a route and a nav entry). Deleting it means deleting one directory.
With a type-based layout the same work is scattered across `components/`,
`hooks/`, `api/` and `types/`.

**The dependency rule:** `app/` → `features/` → `components/` + `lib/`. Features
never import from each other; shared code moves down into `components/common/` or
`lib/`.

### Route protection

`AppShell` guards the authenticated route group. This is a **usability** guard,
not a security boundary — it decides what to render, while the API independently
authorises every request.

Next.js middleware cannot do this job here: the refresh cookie is scoped to the
backend's `/api/v1/auth` path, so the browser never sends it to the Next.js
server, which therefore has no way to know whether a visitor is signed in.

### Data fetching

TanStack Query owns server state. Query keys are centralised in
`lib/query-client.ts` so invalidation cannot drift. Mutations never retry
automatically — they are not idempotent. Queries do not retry 4xx responses,
since the server already gave a definitive answer.

---

## 10. Adding a module

The foundation is designed so this list stays short. To add "Employees":

**Backend**

1. `app/models/employee.py` — inherit `Base` and `AuditableBase`.
2. Export it from `app/models/__init__.py` (so Alembic sees it).
3. `alembic revision --autogenerate -m "add employees table"`, then **read the
   generated file** before applying it.
4. `app/schemas/employee.py` — request and response models.
5. `app/repositories/employee_repository.py` — extend `BaseRepository[Employee]`.
6. `app/services/employee_service.py` — the business rules.
7. `app/api/v1/routes/employees.py` — thin routes.
8. Register the router in `app/api/v1/router.py`.
9. Add providers to `app/api/deps.py`.
10. Tests in `backend/tests/`.

**Frontend**

1. `src/features/employees/` — `api/`, `components/`, `hooks/`, `schemas/`,
   `types/`.
2. `src/app/(app)/employees/page.tsx` — compose the feature.
3. Add the endpoints to `src/lib/api/endpoints.ts`.
4. Add query keys to `src/lib/query-client.ts`.
5. Flip `disabled` off the nav entry in `src/config/navigation.ts`.
6. Tests alongside the code.

Note what is *not* on this list: no changes to the auth flow, error handling,
logging, the response envelope, the design system or the app shell.

---

## 11. Decisions and trade-offs

| Decision | Why | Cost |
| --- | --- | --- |
| Async SQLAlchemy | FastAPI is async; sync sessions would block the event loop | Async has sharper edges (see `eager_defaults` above) |
| Opaque refresh tokens, not JWTs | Revocable; a stateless JWT cannot be withdrawn before it expires | A database read per refresh |
| Refresh cookie scoped to `/api/v1/auth` | Not attached to every API call, shrinking the exposure surface | Next.js middleware cannot read it, so route guarding is client-side |
| Access token in memory | XSS cannot read it | One extra request on page load to restore the session |
| Repository pattern | Services stay testable without a database; SQL stays in one place | More files than calling the ORM directly from services |
| No `Base.metadata.create_all()` | Guarantees development, CI and production share one schema history | Migrations must be written even for local experiments |
| Envelope on every response | Clients parse success and failure identically | Slightly more verbose payloads |
| Tests run real migrations | Every test run proves the migration chain applies | Integration tests need a live PostgreSQL |
| RBAC deferred | Explicit Phase 1 scope | The settings editor is held back until roles exist |

---

## 12. Known gaps

Deliberate omissions, listed so they are not mistaken for oversights:

- **No rate limiting.** Account lockout blunts credential stuffing against a
  single account, but there is no global limiter. Put one at the gateway, or add
  `slowapi`, before public exposure.
- **No refresh-token cleanup job.** `RefreshTokenRepository.purge_expired()`
  exists but nothing schedules it.
- **Mail is minimal SMTP with a console fallback.** Fine for development;
  replace `MailService._deliver` with a transactional provider for production.
- **No CI pipeline.** `scripts/verify.ps1` runs the same gates locally; wiring
  it into a workflow is a small step.
- **Single-tenant.** Every table has the audit contract but no `tenant_id`.
  Retrofitting multi-tenancy would be a significant change.
