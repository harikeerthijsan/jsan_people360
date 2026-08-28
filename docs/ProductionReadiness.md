# Production Readiness Audit

Final hardening pass over the complete application: 23 modules, 359 API
operations, 92 tables, 18 migrations.

**Verdict: NOT PRODUCTION READY — one blocking issue, listed in §14.**

The application itself is in good shape. The blocker is not a defect in the
code; it is that the code is not under version control, which makes every other
guarantee in this report unverifiable and unrepeatable.

---

## 1. Security findings

Five genuine vulnerabilities were found, all of the same class: an endpoint that
asked "may you use this module?" and never asked "about whom?".

| # | Severity | Endpoint | Finding |
| --- | --- | --- | --- |
| 1 | **High** | `GET /performance/reviews/{cycle_id}/{employee_id}` | Any employee could read **any colleague's** full performance review — self-assessment, manager assessment, ratings. `performance:view` is held by the base Employee role, so the id in the URL was the only thing deciding whose review came back. **Confirmed exploitable: HTTP 200 with real data.** |
| 2 | **High** | `POST /performance/reviews/{cycle_id}/{employee_id}/self` | No scope check on a write. `performance:update` is held by the Employee role, so any employee could file a self-review **under a colleague's name**. Blocked in practice only by an unrelated business rule (409 when the victim has no goals) — an authorization gap, not an authorization control. |
| 3 | Medium | `POST /performance/reviews/{cycle_id}/{employee_id}/manager` | Manager review writable for any employee company-wide, not just direct reports. |
| 4 | Medium | `POST /performance/reviews/{cycle_id}/{employee_id}/finalise` | Final rating of record writable outside the reporting line. |
| 5 | Medium | `GET /projects/employees/{employee_id}/allocation-history` | Any holder of `projects:view` — Manager, Team Lead, Project Manager, HR — could read any employee's project and allocation history. **Confirmed exploitable: HTTP 200.** |

**Why they survived earlier reviews.** The runtime IDOR sweep initially reported
them clean. Filling `{cycle_id}` with a random UUID made the endpoint answer 404
*before* the authorization guard ran, and an empty body made the writes answer
422 for the same reason. A refusal that comes from the wrong layer looks
identical to a refusal that comes from the right one.

Three further items were checked and found **not** to be vulnerabilities:
`/hr/employees/{employee_id}`, `/hr/attendance/{employee_id}/correct` and
`/hr/leave/balances/{employee_id}/adjust` are organization-wide by design, each
guarded by a permission that is itself administrative. `/manager/team/{employee_id}`
carries no declared scope dependency but checks `ManagerScope` in the handler
before it reads anything — verified at runtime, not assumed.

## 2. Security fixes

- **The five endpoints are scoped.** Four now carry `require_team_scope()`
  alongside their existing permission guard; the self-review route carries
  `require_self_or("performance:approve")` instead, because a self review is
  *by* the employee — your own is always yours, and writing one for somebody
  else needs an escalating permission *and* the reporting line.
- **`TestScopeCoverage`** asserts statically that every `{employee_id}` route
  declares a scope guard or appears on an allowlist with a written reason. It
  reads the route table instead of calling it, so it cannot be fooled by a 404
  or a 422 the way the runtime sweep was. A second test fails if an allowlist
  entry goes stale.
- **Production configuration is now enforced, not documented.** A process with
  `APP_ENV=production` validates its own settings at import and **refuses to
  boot** on a placeholder `SECRET_KEY`, `JP360_DEBUG=true`, `COOKIE_SECURE=false`,
  `LOG_REQUEST_BODY=true`, an unset `TRUSTED_HOSTS`, wildcard or localhost CORS
  origins, or either bootstrap credential left at its documented default. Every
  problem is listed at once, so a bad deploy is fixed in one pass.
- **Credential endpoints are throttled.** Per client address, counting only
  *failed* attempts on login, forgot-password, reset-password and refresh.
- **Request bodies are bounded** (`MAX_REQUEST_BODY_MB`, default 12 MB).
  Uploads were already capped; JSON was not.
- **`TrustedHostMiddleware`** is applied when `TRUSTED_HOSTS` is set. The Host
  header is reflected into password-reset links, so a forged one would send a
  working reset token to an attacker's domain.

### A flaw in the first version of the rate limiter, and its fix

The limiter initially counted *all* requests to the credential endpoints, at 10
per minute per address. An office shares one public address behind NAT, so a
hundred people signing in at nine o'clock would have been throttled and the
event logged as an attack. It now counts only rejected attempts, and a
successful sign-in clears that client's slate — invisible to a legitimate
office, immediate against a client whose traffic is nothing but failures.

Known limitation, stated in the code rather than only here: the counter is
in-process. With N workers the effective limit is N× the configured one, and a
restart forgets. It is a speed bump sized for a single node, not a substitute
for throttling at the edge.

## 3. RBAC verification

23 modules, 93 permissions, 9 seeded roles. The catalogue is defined in code and
mirrored to the database; roles are data and editable.

Verified against the required hierarchy:

| Seat | Reach | Verified by |
| --- | --- | --- |
| Employee | Own records only | `TestSelfScoping`, `TestEmployeeCannotReachAnotherEmployee` |
| Manager | Own + direct reports | `TestManagerCannotReachAnotherTeam`, `test_team_scoping` (30 tests) |
| HR | Explicit HR permissions only | `TestHrIsNotAnAdministrator` (36 tests) |
| Admin | Full application access | `TestAdminAccess` |
| Super Admin | Unrestricted | `TestSuperAdminAccess` |

`TestGuardCoverage` fails the build if any endpoint is added without a permission
guard or an entry on the unguarded allowlist with a stated reason. Nothing
anywhere checks a role *name*; every boundary is a permission that is granted or
withheld, which is why the HR tests are paired with grants that make the same
refused call succeed.

**One client-side defect found and fixed.** Eight HR navigation items gated on
permissions that do not exist in the backend catalogue — `attendance:view_all`,
`leave:view_all`, `timesheets:view_all`, `projects:view_all`,
`documents:view_all`, `performance:view_all`. The platform deliberately defines
only `employees:view_all` as its scoping permission. The client's check is plain
set membership with no superuser bypass, so **eight working HR screens were
invisible to every user including Super Admin.** This failed closed, so it was
never a security hole — it was a feature that silently appeared not to exist.
Each item is now gated on exactly what its endpoint requires, and a
cross-boundary test reads the client's navigation source and fails if it ever
again names a permission the backend does not define.

## 4. IDOR test results

A new suite (`tests/integration/test_idor.py`, 14 tests) enumerates every route
taking an `{employee_id}` — currently 36 — from the live route table, so a
future endpoint is covered the day it is merged.

| Scenario | Result |
| --- | --- |
| Employee A → Employee B, all 36 employee-id routes | **All refused** |
| Employee A → B: profile, sensitive reveal (unmasked Aadhaar/bank) | 403 |
| Employee A → B: check-in, leave, timesheet, correction, **with valid bodies** | 403 on each |
| Manager A → Manager B's team, all 36 routes | **All refused** |
| Employee's own records still reachable | 200 (the refusals are not a blanket deny) |

The four write endpoints are tested with bodies the server would have accepted
for the caller's own record, so a 403 there is the authorization guard refusing
and not the validator.

## 5. Database and migration status

- **18 migrations, single head, single root, no branches, complete chain.**
- Fresh database verified: the test suite builds the schema from `alembic
  upgrade head` and tears it down to base on every run — exercised 20+ times
  during this audit.
- `0018` verified in both directions (upgrade and downgrade).
- `Base.metadata.create_all()` appears nowhere; a pre-commit hook rejects it.
- **Indexes: no critical gaps.** An initial automated scan reported 46
  unindexed foreign keys; on inspection that was a false-positive analysis. The
  columns actually used as query predicates are indexed, and the composite
  shapes match the query shapes — `documents(owner_type, owner_id)` serves the
  vault's scoped reads exactly. The remaining unindexed FKs are columns never
  used as predicates, where an index would cost write throughput for nothing.
- Leave accrual is idempotent on both halves: lazily created in code, and
  `UNIQUE (employee_id, leave_type_id, year)` in the database, so two workers
  racing cannot double-credit. Verified by running it twice.

## 6. API test results

**969 backend tests, 0 failures** (up from 931 at the start of this phase: 14
IDOR, 21 hardening, 3 configuration-drift and cross-boundary tests added).

## 7. Frontend test results

**363 tests across 35 suites, 0 failures.**

## 8. Build status

| Gate | Result |
| --- | --- |
| backend black / isort / ruff | pass |
| backend mypy (strict) | 0 errors, 167 files |
| backend pytest | 969 passed |
| frontend prettier / tsc / eslint | pass |
| frontend jest | 363 passed |
| **frontend production build** | **compiles clean**, 5 new offboarding routes emitted |
| alembic migration chain | valid, single head |

## 9. Performance

Query counts were measured per request on six of the heaviest list endpoints at
two page sizes; an N+1 shows up as a count that tracks the page size.

| Endpoint | 5 rows | 25 rows | Verdict |
| --- | --- | --- | --- |
| Employee directory | 7 | 7 | flat |
| Document vault | 4 | 4 | flat |
| Offboarding cases | 4 | 4 | flat |
| Resignations | 4 | 4 | flat |
| Projects | 4 | 4 | flat |
| HR employees | 7 | 7 | flat |

**No N+1 found.** Every list endpoint is paginated (`PaginationParams`, capped
at 100 per page). No optimisation was applied, because none was warranted —
adding indexes or caching here would have been change without evidence.

## 10-12. Error handling, logging and audit

**Error handling** was already sound and is now structurally safe. Stack traces
never reach a client; internal detail is included only when `settings.debug` is
on, which production now refuses to start with. Database errors return a generic
message with the exception logged server-side. Every response uses the same
envelope, including the new 429 and 413.

**Logging** is structured and request-correlated. The access log records request
id, forwarded address and user agent — never the `Authorization` header and
never a body. Authorization failures and rate-limit refusals are logged as
security events without the credential that was tried.

*Minor finding:* `LOG_REQUEST_BODY` is declared, validated and **read by
nothing**. Bodies are never logged, which is the safe direction, but the setting
implies a capability that does not exist. Left in place — it is now enforced to
`false` in production — but it should either be implemented or removed.

**Audit logging** covers employee changes, role and permission changes, leave
adjustments, attendance corrections, document approvals, policy changes,
resignation approvals, offboarding, employee deactivation and administrative
overrides. Overrides are audited *as* overrides, in addition to the ordinary
action: an admin rewriting a last working day and HR settling one through the
normal step are the same column change and a completely different fact.

## 13. Environment and configuration

`.env.example` covers all 60 settings; six were missing (the ones added this
phase) and have been added. A test now fails if code and example drift in either
direction — a setting an operator cannot find, or an instruction to set
something that does nothing.

New required production variables: `TRUSTED_HOSTS`, and optionally
`RATE_LIMIT_*` and `MAX_REQUEST_BODY_MB`. The production checklist in
`docs/EnvironmentVariables.md` is updated and now notes which items are enforced
at startup rather than trusted.

Health checks: `GET /health` (liveness, no dependency checks) and `GET
/health/ready` (probes dependencies, 503 when unavailable). Neither leaks a DSN
or an exception; a failed database probe returns "The database is unreachable."
with the detail logged server-side.

## 14. Remaining known issues

### Blocking

**The project is not under version control.** There is no git repository —
only a `.gitignore` and a pre-commit config that nothing runs. This blocks
production for reasons independent of code quality:

- No rollback. A bad deploy has no previous known-good revision to return to.
- No review, no CI, no way to run these gates on a change before it ships.
- No audit of who changed what — in an HRMS that stores Aadhaar numbers, bank
  details and salary data, that is a compliance problem, not only an
  engineering one.
- The pre-commit hooks that enforce the schema-ownership rule and the formatting
  gates cannot run at all.

This is one command to start (`git init`, commit, push to a private remote) and
is the single thing standing between this application and a defensible
deployment.

### Non-blocking

1. **Five ACL-locked directories** (`backend/.pytest-*`) that no process can
   read or delete. They are excluded from every tool and git-ignored, so they
   are inert, but they need an elevated `takeown /f backend\.pytest-* /r`
   followed by `rmdir /s` to clear.
2. **Rate limiting is per-process.** Adequate for a single node; a cluster needs
   it in Redis or at the edge.
3. **`LOG_REQUEST_BODY` is dead configuration** (§10-12).
4. **`resignation:create` has no endpoint.** The permission exists and is
   granted to Admin and HR Admin so the capability can be added without a
   migration; employees submit their own resignations.
5. **No automated dependency-vulnerability scan** was run in this phase. `pip
   audit` / `npm audit` should be part of CI once the repository exists.
6. **SMTP is unconfigured.** Password-reset emails are written to the log until
   `SMTP_HOST` is set — correct for development, and a silent failure in
   production if missed. It is on the checklist but is not startup-enforced,
   because a deployment that legitimately uses a log-based mail relay is a real
   configuration.

## 15. Deployment checklist

**Before the first deploy**

- [ ] **`git init`, commit, push to a private remote** — the blocker above
- [ ] `pre-commit install` and run `pre-commit run --all-files`
- [ ] Add CI running `scripts/verify.ps1` (or its gates) on every push
- [ ] Run `pip audit` and `npm audit`; triage anything high or critical

**Configuration** — most of this is now enforced at startup; the process will
refuse to boot if it is wrong.

- [ ] `SECRET_KEY` unique, ≥64 random characters, from a secrets manager
- [ ] `APP_ENV=production` (disables `/docs`, `/redoc`, `/openapi.json`)
- [ ] `TRUSTED_HOSTS` names the API's real hostnames
- [ ] `BACKEND_CORS_ORIGINS` lists only the real frontend origin
- [ ] `COOKIE_SECURE=true`; `COOKIE_SAMESITE` correct for the topology
- [ ] `DEFAULT_ADMIN_PASSWORD` changed, or the bootstrap account removed
- [ ] `DATABASE_URL` points at production; the app user is **not** a superuser
- [ ] `LOG_FORMAT=json`, `LOG_LEVEL=INFO`, `DB_ECHO=false`
- [ ] SMTP configured, and a reset email actually received end to end
- [ ] `UPLOAD_DIR` on durable storage, not the container filesystem

**Infrastructure**

- [ ] TLS terminated in front of the API; HSTS is emitted in production
- [ ] Reverse proxy **overwrites** `X-Forwarded-For` (the limiter trusts it)
- [ ] Database backups, with a restore actually rehearsed
- [ ] `alembic upgrade head` runs as a deploy step, before the new version serves
- [ ] Rate limiting at the edge if running more than one worker or node

**After deploy**

- [ ] `/health/ready` returns 200
- [ ] Sign in as each of the five seats and confirm the sidebar matches the
      access model — Employee sees no HR section, HR sees no Roles or Settings
- [ ] Confirm `/docs` returns 404

---

## Verdict

**NOT PRODUCTION READY.**

One blocker: **the application is not in version control.** Everything else in
this report — 969 passing tests, five IDOR fixes, enforced production
configuration, a clean production build — is real work that cannot be defended,
reproduced or rolled back until there is a repository to hold it.

The application code itself is production-quality. Initialise the repository,
commit, put the gates in CI, and the verdict changes.
