# API reference

Base URL: `http://localhost:8000/api/v1`

Interactive documentation from the running server (disabled in production):

- Swagger UI — <http://localhost:8000/docs>
- ReDoc — <http://localhost:8000/redoc>
- OpenAPI schema — <http://localhost:8000/openapi.json>

---

## 1. Response envelope

Every endpoint, success or failure, returns the same four keys.

**Success**

```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": { "...": "endpoint-specific payload" },
  "errors": null
}
```

**Failure**

```json
{
  "success": false,
  "message": "One or more fields failed validation.",
  "data": null,
  "errors": [
    {
      "code": "value_error",
      "message": "value is not a valid email address",
      "field": "email"
    }
  ]
}
```

| Key | Type | Notes |
| --- | --- | --- |
| `success` | boolean | Mirrors the HTTP status class |
| `message` | string | **Written for a user.** Safe to display directly |
| `data` | object \| null | Payload on success; `null` on failure |
| `errors` | array \| null | `null` on success; at least one entry on failure |

`errors[].field` is a dotted path into the request body when the error is
field-scoped, and `null` otherwise — which is what lets a client map server
errors onto form inputs.

### Response headers

| Header | Meaning |
| --- | --- |
| `X-Request-ID` | Correlation id. Echoes an inbound value, otherwise generated. Quote it in bug reports |
| `X-Response-Time-Ms` | Server processing time |

---

## 2. Status codes

| Code | When |
| --- | --- |
| `200` | Request succeeded |
| `201` | Resource created |
| `204` | Succeeded, no body |
| `400` | Malformed request |
| `401` | Missing, invalid or expired credentials |
| `403` | Authenticated but not permitted, or account deactivated |
| `404` | No such resource |
| `409` | Conflicts with existing data (e.g. duplicate email) |
| `422` | Validation failed — see `errors[]` |
| `423` | Account locked after repeated failed sign-ins |
| `429` | Rate limited |
| `500` | Server fault — detail is logged, never returned |
| `503` | A dependency is unavailable |

### Error codes

| `code` | Status | Meaning |
| --- | --- | --- |
| `invalid_credentials` | 401 | Email or password incorrect |
| `invalid_token` | 401 | Token unknown, expired or already used |
| `authentication_failed` | 401 | No credentials supplied |
| `account_inactive` | 403 | Account deactivated |
| `account_locked` | 423 | Too many failed attempts |
| `permission_denied` | 403 | Not permitted |
| `not_found` | 404 | No such resource |
| `conflict` / `integrity_error` | 409 | Conflicts with existing data |
| `validation_error` | 422 | Payload failed validation |
| `rate_limited` | 429 | Too many requests |
| `database_error` | 500 | Persistence failure |
| `internal_error` | 500 | Unhandled fault |
| `service_unavailable` | 503 | Dependency down |

---

## 3. Authentication

### How it works

1. `POST /auth/login` returns a short-lived **access token** in the body and
   sets a long-lived **refresh token** as an `HttpOnly` cookie.
2. Send the access token on every request:
   `Authorization: Bearer <access_token>`.
3. When it expires (15 minutes), call `POST /auth/refresh`. The browser supplies
   the cookie automatically; a new token pair comes back.
4. `POST /auth/logout` revokes the refresh token and clears the cookie.

### Rules that will affect your client

- **Refresh tokens rotate.** Each refresh revokes the token you presented.
- **Reuse is treated as theft.** Presenting an already-revoked refresh token
  revokes *every* session for that user. Never issue two concurrent refreshes —
  funnel them into one in-flight request.
- **Cookies require `withCredentials`.** Browser clients must send credentials
  and the origin must appear in `BACKEND_CORS_ORIGINS`.
- **Cookie path.** The cookie is scoped to `/api/v1/auth`, so it is not attached
  to unrelated API calls.

### No RBAC yet

Every authenticated user has full access, including the administrative user
routes. `is_superuser` is returned but not enforced anywhere.

The write schemas already draw the line RBAC will later enforce: `ProfileUpdate`
simply has no administrative fields on it, so a self-service request cannot
carry one whether or not a role check exists.

---

## 4. Endpoints

### Job Requisitions

`/requisitions` provides dashboard, filtered lists, create/update/detail, submit, approve, reject, send-back, cancel, close, attachment links and CSV/XLSX export. `/notifications` lists and marks read the authenticated user's in-app notifications. See `RequisitionModule.md`.

### Document Vault

The authenticated `/documents` API provides listing, multipart upload, detail,
metadata update, immutable version upload/history, preview, download, review,
archive, restore, dashboard figures and `/{id}/audit`. Listing accepts category,
type, owner, workflow status, expiry state and upload-date filters.

`/document-categories` and `/document-types` expose the shared master-data
contract for configurable classification, including archive and restore.

File responses never expose a storage path. Preview and download are separate
audited actions.

An owner is a type plus an id. All four types — employee, candidate,
organization and user — are checked against their table on upload, so a document
cannot be filed against a record that does not exist; the response resolves the
owner to a display name and reference code. Note that a candidate's application
résumé is filed against the *user*, because it exists before the candidate does.

### Health

#### `GET /health`

Liveness. No authentication, no dependency checks.

```json
{
  "success": true,
  "message": "Service is healthy",
  "data": {
    "status": "healthy",
    "service": "JSAN People360",
    "version": "0.1.0",
    "environment": "local",
    "timestamp": "2026-07-31T08:17:24.161649Z"
  },
  "errors": null
}
```

#### `GET /health/ready`

Readiness. Probes every dependency. Returns **503** when any is down.

```json
{
  "success": true,
  "message": "Service is ready",
  "data": {
    "status": "ready",
    "service": "JSAN People360",
    "version": "0.1.0",
    "environment": "local",
    "timestamp": "2026-07-31T08:17:24.161649Z",
    "checks": [
      { "name": "postgresql", "status": "up", "latency_ms": 12.4, "detail": null }
    ]
  },
  "errors": null
}
```

---

### Authentication

#### `POST /auth/login`

Anonymous.

```json
{
  "email": "admin@example.com",
  "password": "Admin@12345",
  "remember_me": false
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `email` | string | Required. Trimmed and lower-cased |
| `password` | string | Required, 1–128 characters |
| `remember_me` | boolean | Optional. Extends the refresh token from 7 to 28 days |

**200**

```json
{
  "success": true,
  "message": "Signed in successfully",
  "data": {
    "tokens": {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "token_type": "bearer",
      "expires_in": 899
    },
    "user": { "...": "the user object described in §6" }
  },
  "errors": null
}
```

Also sets:

```
Set-Cookie: jp360_refresh_token=<opaque>; HttpOnly; Path=/api/v1/auth; SameSite=lax; Max-Age=604800
```

The refresh token is **never** in the response body.

**Errors** — `401 invalid_credentials`, `403 account_inactive`,
`423 account_locked` (after 5 failures, for 15 minutes), `422` validation.

> Unknown email and wrong password return identical responses, by design, so the
> endpoint cannot be used to discover which addresses are registered.

---

#### `POST /auth/refresh`

Anonymous — the cookie is the credential.

Body is optional. Browser clients should send `{}` and rely on the cookie;
non-browser clients may send `{"refresh_token": "<token>"}`.

**200** — same shape as `/auth/login`, with a rotated cookie.

**401** — `invalid_token`. The presented token was unknown, expired, or already
used. In the last case every session for that user has now been revoked.

---

#### `POST /auth/logout`

Requires `Authorization`.

```json
{ "all_sessions": false }
```

Set `all_sessions` to `true` to revoke every active session.

**200**

```json
{
  "success": true,
  "message": "Signed out successfully.",
  "data": { "detail": "Signed out successfully." },
  "errors": null
}
```

---

#### `GET /auth/me`

Requires `Authorization`. Returns the caller's profile (same `user` object as
`/auth/login`).

---

#### `POST /auth/forgot-password`

Anonymous.

```json
{ "email": "admin@example.com" }
```

**Always returns 200**, whether or not the address is registered.

```json
{
  "success": true,
  "message": "If an account exists for that address, a password reset link has been sent.",
  "data": {
    "detail": "If an account exists for that address, a password reset link has been sent.",
    "reset_token": "kJ8n2mQx..."
  },
  "errors": null
}
```

> `reset_token` is populated **only outside production**, so the flow can be
> completed without a mail server. In production it is always `null`.

---

#### `POST /auth/reset-password`

Anonymous.

```json
{
  "token": "kJ8n2mQx...",
  "new_password": "N3w@Password!",
  "confirm_password": "N3w@Password!"
}
```

Password policy: at least 8 characters (max 72 bytes), with an uppercase letter,
a lowercase letter, a digit and a special character. One definition, in
`app.schemas.user.PasswordStr`, is shared by every endpoint that accepts a
password.

**200** — password changed; **every** existing session is revoked.

**Errors** — `401 invalid_token` (unknown, expired or already used — tokens are
single-use), `422` (weak password or mismatch).

---

#### `POST /auth/change-password`

Requires `Authorization`.

```json
{
  "current_password": "Admin@12345",
  "new_password": "N3w@Password!",
  "confirm_password": "N3w@Password!"
}
```

**200** — password changed; every session including the caller's is revoked, so
the client must sign in again.

**Errors** — `401 invalid_credentials` (current password wrong), `422`.

---

---

## 5. Organization Management

Master data referenced by every other module. Conceptual detail — the two
lifecycles, the uniqueness rules, the referential guards — is in
[`OrganizationModule.md`](OrganizationModule.md); this section is the contract.

All nine masters expose the **same six endpoints** at
`/api/v1/{master}`, where `{master}` is one of:

`organizations` · `business-units` · `teams` ·
`designations` · `locations` · `employment-types` · `grades`

| Method | Path | Success | Purpose |
| --- | --- | --- | --- |
| `GET` | `/{master}` | 200 | Paged list |
| `GET` | `/{master}/{id}` | 200 | One record, archived included |
| `POST` | `/{master}` | **201** | Create |
| `PATCH` | `/{master}/{id}` | 200 | Partial update |
| `POST` | `/{master}/{id}/archive` | 200 | Soft delete |
| `POST` | `/{master}/{id}/restore` | 200 | Undo the archive |

All require `Authorization: Bearer <token>`.

### List parameters

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `page` | int ≥ 1 | 1 | |
| `page_size` | int 1–100 | 20 | |
| `search` | string | — | Case-insensitive; LIKE wildcards matched literally |
| `status` | `active` \| `inactive` | — | Omit for both |
| `archived` | bool | `false` | `true` returns **only** archived records |
| `sort_by` | string | `name` | Per-entity allowlist; unknown → `400 invalid_sort_field` |
| `sort_order` | `asc` \| `desc` | `asc` | |
| `business_unit_id` | uuid | — | Teams and designations |

### Fields by master

Every master has `id`, `name`, `description`, `status`, `created_at`,
`updated_at`, `created_by`, `updated_by` and `deleted_at`. On top of that:

| Master | Additional fields |
| --- | --- |
| `organizations` | `legal_name`*, `registration_number`*, `gst_number`, `pan_number`, `logo_url`, `website`, `timezone`*, `currency`*, `address_line1`*, `address_line2`, `city`*, `state`*, `country`*, `postal_code` |
| `business-units` | `code`* |
| `teams` | `business_unit_id`*, `business_unit` (embedded), `manager_id`, `manager` (embedded) |
| `designations` | `code`*, `business_unit_id`*, `business_unit` (embedded), `level`* |
| `locations` | `code`*, `country`*, `state`*, `city`*, `address`*, `timezone`* |
| `employment-types` | `code`* |
| `grades` | `code`*, `level`* |

`*` required on create. Parent objects are embedded in responses so list screens
need no extra request per row.

### `GET /api/v1/designations?page=1&page_size=2`

```json
{
  "success": true,
  "message": "Designations retrieved successfully",
  "data": {
    "items": [
      {
        "id": "8c2f...",
        "name": "Software Engineer",
        "code": "SE",
        "level": 2,
        "description": "Delivers features with guidance.",
        "status": "active",
        "business_unit_id": "1a4d...",
        "business_unit": { "id": "1a4d...", "name": "Technology Services", "code": "TECH", "status": "active" },
        "created_at": "2026-07-31T11:47:06Z",
        "updated_at": "2026-07-31T11:47:06Z",
        "created_by": "37c8...",
        "updated_by": "37c8...",
        "deleted_at": null
      }
    ],
    "meta": {
      "page": 1, "page_size": 2, "total_items": 6,
      "total_pages": 3, "has_next": true, "has_previous": false
    }
  },
  "errors": null
}
```

### `POST /api/v1/designations`

```json
{
  "name": "Team Lead",
  "code": "tl",
  "business_unit_id": "1a4d...",
  "level": 4,
  "description": "Leads a team's technical delivery.",
  "status": "active"
}
```

The code is stored as `TL`, and the name is trimmed and whitespace-collapsed,
before any uniqueness check runs.

### `GET /api/v1/organizations/primary`

Returns the organization other modules should default to — the oldest live,
active profile — so nothing has to hard-code an id. `404` when none is
configured.

### Module-specific error codes

| `code` | Status | Meaning |
| --- | --- | --- |
| `duplicate_name` | 409 | Name already in use within its scope |
| `duplicate_code` | 409 | Code already in use |
| `duplicate_registration_number` | 409 | Another organization has this registration |
| `has_active_children` | 409 | Cannot archive; live children still reference it |
| `parent_archived` | 409 | Cannot restore; the parent is archived |
| `record_archived` | 409 | Cannot edit an archived record |
| `already_archived` / `not_archived` | 409 | Archive/restore called in the wrong state |
| `invalid_business_unit` / `invalid_manager` | 409 | Referenced record is missing, archived or inactive |
| `invalid_sort_field` | 400 | `sort_by` is not an allowed column |

A duplicate against an **archived** record says so in `message`, so the user
knows to restore rather than rename.

---

## 6. User Management

Everyone who can sign in. Conceptual detail — the two lifecycles, the guards, the
password rules — is in [`UserModule.md`](UserModule.md); this section is the
contract.

| Method | Path | Success | Purpose |
| --- | --- | --- | --- |
| `GET` | `/users` | 200 | Paged directory |
| `POST` | `/users` | **201** | Create an account |
| `GET` | `/users/{id}` | 200 | One account, archived included |
| `PATCH` | `/users/{id}` | 200 | Partial update |
| `POST` | `/users/{id}/activate` | 200 | Restore sign-in |
| `POST` | `/users/{id}/deactivate` | 200 | Block sign-in, end sessions |
| `POST` | `/users/{id}/archive` | 200 | Soft delete |
| `POST` | `/users/{id}/restore` | 200 | Undo the archive |
| `POST` | `/users/{id}/reset-password` | 200 | Set a password on someone's behalf |
| `GET` | `/users/me` | 200 | The caller's own profile |
| `PATCH` | `/users/me` | 200 | Self-service profile update |

All require `Authorization: Bearer <token>`.

> `/users/me` is registered **before** `/users/{id}`. Starlette matches in
> registration order, and the reverse would let `{id}` capture `me` and fail to
> parse it as a UUID.

### The user object

```json
{
  "id": "e39f390d-2440-4207-93d0-4f24ff1e64c6",
  "user_code": "USR-000004",
  "username": "jane.doe",
  "first_name": "Jane",
  "last_name": "Doe",
  "full_name": "Jane Doe",

  "email": "jane.doe@jsan.example",
  "personal_email": "jane@personal.example",
  "phone_number": "+91 98765 43210",
  "avatar_url": null,
  "gender": "female",
  "date_of_birth": "1994-06-15",

  "business_unit_id": "1a4d...",
  "team_id": "7b2e...",
  "team_id": null,
  "designation_id": null,
  "grade_id": null,
  "location_id": null,
  "employment_type_id": null,
  "joining_date": "2026-08-01",

  "organization": {
    "business_unit": { "id": "1a4d...", "name": "Technology Services", "code": "TECH", "status": "active" },
    "team": { "id": "7b2e...", "name": "Platform Engineering", "status": "active" },
    "team": null,
    "designation": null,
    "grade": null,
    "location": null,
    "employment_type": null
  },

  "is_active": true,
  "status": "active",
  "is_superuser": false,
  "force_password_change": false,
  "is_locked": false,

  "last_login_at": null,
  "password_changed_at": "2026-07-31T14:53:11Z",
  "created_at": "2026-07-31T14:53:11Z",
  "updated_at": "2026-07-31T14:53:11Z",
  "created_by": "37c8...",
  "updated_by": "37c8...",
  "deleted_at": null
}
```

`hashed_password` and the reset-token columns are **not** in this model, which is
what keeps credentials out of every response that returns a user.

Four fields are derived rather than stored, so they cannot fall out of step with
the columns they summarise:

| Field | Derived from |
| --- | --- |
| `full_name` | `first_name` + `last_name` |
| `status` | `is_active` — `active` or `inactive` |
| `organization` | the eight `*_id` columns, resolved to names |
| `is_locked` | `locked_until` compared to now |

This is the object returned by `/auth/login`, `/auth/me` and every endpoint in
this section.

### List parameters

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `page` | int ≥ 1 | 1 | |
| `page_size` | int 1–100 | 20 | |
| `search` | string | — | Staff code, username, both name parts, the two emails and the mobile number |
| `status` | `active` \| `inactive` | — | Omit for both |
| `archived` | bool | `false` | `true` returns **only** archived accounts |
| `sort_by` | string | `first_name` | Also `last_name`, `user_code`, `username`, `email`, `joining_date`, `last_login_at`, `created_at`, `updated_at`. Unknown → `400 invalid_sort_field` |
| `sort_order` | `asc` \| `desc` | `asc` | |
| `business_unit_id` | uuid | — | |
| `team_id` | uuid | — | |
| `designation_id` | uuid | — | |
| `location_id` | uuid | — | |

Search is case-insensitive and LIKE wildcards are matched literally. `full_name`
is not a column, so searching it compares `first_name || ' ' || last_name`.

### `POST /api/v1/users`

```json
{
  "first_name": "Jane",
  "last_name": "Doe",
  "username": "jane.doe",
  "email": "jane.doe@jsan.example",
  "password": "Str0ng@1",
  "personal_email": "jane@personal.example",
  "phone_number": "+91 98765 43210",
  "gender": "female",
  "date_of_birth": "1994-06-15",
  "team_id": "7b2e...",
  "joining_date": "2026-08-01",
  "force_password_change": false,
  "status": "active"
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `first_name`, `last_name` | ✓ | Trimmed, whitespace-collapsed, 1–100 chars |
| `username` | ✓ | 3–50 chars. Lower-cased, spaces become dots. Must start with a letter or digit; then letters, digits, `.`, `-`, `_` |
| `email` | ✓ | Official address. Trimmed, lower-cased. Also a sign-in identifier |
| `password` | ✓ | See the policy in §4 |
| `personal_email` | | |
| `phone_number` | | `+91 98765 43210`, `020 7946 0958`, `+1 (555) 123-4567` all accepted; free text is not |
| `gender` | | `male`, `female`, `other`, `prefer_not_to_say` |
| `date_of_birth` | | Not in the future; implied age 14–100 |
| `avatar_url` | | |
| The eight `*_id` references, `joining_date` | | Each must exist, be live and be active |
| `force_password_change` | | Default `false` |
| `status` | | Default `active` |

`user_code` is **not accepted**. It comes from a PostgreSQL sequence, which is
the only way two concurrent creates cannot be handed the same number.

Write schemas are `extra="forbid"`: an unknown or misspelled field is a `422`
rather than a silently ignored one.

**201** — the user object.

### `PATCH /api/v1/users/{id}`

Same fields, all optional, minus `password` — setting someone else's password is
a separate, separately audited action. Omitted fields are unchanged.

Uniqueness is evaluated against the *resulting* record, so a partial update
cannot sidestep it.

### `POST /api/v1/users/{id}/reset-password`

```json
{
  "new_password": "R3set@11",
  "force_password_change": true,
  "revoke_sessions": true
}
```

Both flags default to `true`, so a reset performed because of a suspected
compromise actually ends it. `force_password_change` is part of the user object,
so it comes back on the user's next sign-in and the client can route straight to
a change-password screen.

### `PATCH /api/v1/users/me`

```json
{
  "personal_email": "jane@personal.example",
  "phone_number": "+91 98765 43210",
  "avatar_url": "https://cdn.example/avatars/jane.png"
}
```

Those three fields are the whole model. Names, username, official email,
organizational placement and status are administrative and produce a `422`
here — not a silent discard.

Send `null` to clear a field. Omit it to leave it unchanged.

### Module-specific error codes

| `code` | Status | Meaning |
| --- | --- | --- |
| `duplicate_email` | 409 | Another account already uses this official email |
| `duplicate_username` | 409 | Another account already uses this username |
| `invalid_organization_reference` | 409 | A selected master record is missing, archived or inactive |
| `cannot_modify_self` | 409 | You cannot deactivate or archive your own account |
| `last_active_user` | 409 | The only active account cannot be deactivated or archived |
| `has_linked_records` | 409 | Other records still reference this user — today, a team they manage |
| `record_archived` | 409 | Cannot edit or reset the password of an archived account |
| `already_active` / `already_inactive` | 409 | Activate/deactivate called in the wrong state |
| `already_archived` / `not_archived` | 409 | Archive/restore called in the wrong state |
| `invalid_sort_field` | 400 | `sort_by` is not an allowed column |

Duplicate messages name the conflicting account by staff code, and say when it is
archived, so the user knows to restore rather than rename:

> The username "jane.doe" is already in use by an archived account (USR-000002).
> Restore that account instead of creating a duplicate, or choose a different
> value.

---

## 7. Employee Management

The central entity of the HRMS. Conceptual detail — the history rule, the guards,
what "masked" means — is in [`EmployeeModule.md`](EmployeeModule.md); this
section is the contract.

| Method | Path | Success | Purpose |
| --- | --- | --- | --- |
| `GET` | `/employees` | 200 | Paged directory |
| `POST` | `/employees` | **201** | Create, with satellite records |
| `GET` | `/employees/dashboard` | 200 | Headline figures |
| `GET` | `/employees/export` | 200 | CSV or XLSX file |
| `GET` | `/employees/{id}` | 200 | One employee, archived included |
| `PATCH` | `/employees/{id}` | 200 | Partial update |
| `GET` | `/employees/{id}/history` | 200 | Employment history |
| `GET` | `/employees/{id}/audit` | 200 | Audit trail for this record |
| `GET` | `/employees/{id}/sensitive` | 200 | **Unmasked** bank and identity details |
| `PUT` | `/employees/{id}/bank` | 200 | Set bank details |
| `PUT` | `/employees/{id}/identification` | 200 | Set government identifiers |
| `PUT` | `/employees/{id}/address` | 200 | Set one address |
| `POST` | `/employees/{id}/confirm` | 200 | End probation |
| `POST` | `/employees/{id}/transfer` | 200 | Move to another team |
| `POST` | `/employees/{id}/designation` | 200 | Change designation |
| `POST` | `/employees/{id}/manager` | 200 | Change reporting manager |
| `POST` | `/employees/{id}/location` | 200 | Change work location |
| `POST` | `/employees/{id}/promote` | 200 | Record a promotion |
| `POST` | `/employees/{id}/status` | 200 | Change employment status |
| `POST` | `/employees/{id}/activate` | 200 | Status → active |
| `POST` | `/employees/{id}/deactivate` | 200 | Status → inactive |
| `POST` | `/employees/{id}/archive` | 200 | Soft delete |
| `POST` | `/employees/{id}/restore` | 200 | Undo the archive |

All require `Authorization: Bearer <token>`.

> `/dashboard` and `/export` are registered **before** `/{employee_id}`, for the
> same reason `/users/me` is: Starlette matches in registration order.

### The employee object

```json
{
  "id": "e6782e8d-c87a-488c-a465-422d02c6b1ec",
  "employee_code": "EMP-000006",
  "first_name": "Kavya",
  "last_name": "Menon",
  "full_name": "Kavya Menon",

  "gender": "female",
  "date_of_birth": "1995-04-12",
  "blood_group": "O+",
  "marital_status": "single",
  "nationality": "Indian",

  "personal_email": "kavya@personal.example",
  "mobile_number": "+91 98765 43210",
  "alternate_number": null,
  "emergency_contact_name": "Lakshmi Menon",
  "emergency_contact_number": "+91 98765 11111",
  "emergency_contact_relationship": "Mother",
  "photo_url": null,

  "official_email": "kavya.menon@jsan.example",
  "official_mobile": "+91 40 1234 5678",
  "extension_number": "4021",
  "work_mode": "hybrid",

  "joining_date": "2026-04-01",
  "confirmation_date": null,
  "employment_status": "probation",

  "business_unit_id": "1a4d...", "team_id": "7b2e...",
  "designation_id": null,        "grade_id": null,
  "work_location_id": null,      "employment_type_id": null,
  "salary_grade_id": null,       "reporting_manager_id": null,

  "organization": {
    "business_unit": { "id": "1a4d...", "name": "Technology Services", "code": "TECH", "status": "active" },
    "team": { "...": "..." },
    "designation": null, "grade": null, "salary_grade": null,
    "work_location": null, "employment_type": null
  },
  "reporting_manager": null,
  "user": null,

  "ctc": "1450000.50",
  "notes": null,

  "addresses": [
    {
      "id": "…", "address_type": "current",
      "address_line1": "12 Jubilee Hills", "address_line2": null, "landmark": null,
      "city": "Hyderabad", "state": "Telangana", "country": "India", "postal_code": "500033"
    }
  ],
  "bank_detail": {
    "id": "…", "bank_name": "HDFC Bank",
    "account_number": "XXXXXXXXXX6789",
    "account_holder_name": null,
    "ifsc_code": "HDFC0001234",
    "branch_name": "Hitec City"
  },
  "identification": {
    "id": "…",
    "aadhaar_number": "XXXXXXXX0123",
    "pan_number": "XXXXXX234F",
    "passport_number": null, "passport_expiry": null,
    "driving_license_number": null,
    "uan_number": "100200300400",
    "pf_number": null, "esi_number": null
  },

  "created_at": "2026-04-01T09:00:00Z",
  "updated_at": "2026-04-01T09:00:00Z",
  "created_by": "37c8...", "updated_by": "37c8...",
  "deleted_at": null
}
```

**`bank_detail.account_number` and the identity fields are masked.** Masking
happens in the read model, so there is no endpoint that returns an employee with
a full Aadhaar. IFSC, UAN, PF and ESI are returned in full — see
[`EmployeeModule.md` §8](EmployeeModule.md#8-sensitive-data) for why.

`full_name` and `organization` are derived from the columns they summarise, and
`employee_code` cannot be supplied or edited: it comes from a PostgreSQL
sequence.

### List parameters

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `page` | int ≥ 1 | 1 | |
| `page_size` | int 1–100 | 20 | |
| `search` | string | — | Employee ID, both name parts, the composed full name, both emails, both mobiles |
| `archived` | bool | `false` | `true` returns **only** archived records |
| `sort_by` | string | `employee_code` | Also `first_name`, `last_name`, `official_email`, `joining_date`, `confirmation_date`, `employment_status`, `created_at`, `updated_at`. Unknown → `400 invalid_sort_field` |
| `sort_order` | `asc` \| `desc` | `asc` | |
| `employment_status` | enum | — | `probation`, `confirmed`, `active`, `notice_period`, `resigned`, `inactive` |
| `work_mode` | enum | — | `office`, `remote`, `hybrid` |
| `business_unit_id`, `team_id`, `designation_id`, `grade_id`, `work_location_id`, `employment_type_id`, `reporting_manager_id` | uuid | — | |
| `joined_from`, `joined_to` | date | — | Inclusive range. Inverted → `400 invalid_date_range` |

There is no `status` parameter: employees have a lifecycle status of their own,
and accepting the master-data one would let a client pass a filter that is
silently ignored. Sending it is a `422`.

### `POST /api/v1/employees`

```json
{
  "first_name": "Kavya",
  "last_name": "Menon",
  "official_email": "kavya.menon@jsan.example",
  "joining_date": "2026-04-01",
  "employment_status": "probation",
  "team_id": "7b2e...",
  "ctc": "1450000.50",
  "addresses": [
    { "address_type": "current", "address_line1": "12 Jubilee Hills",
      "city": "Hyderabad", "state": "Telangana", "country": "India", "postal_code": "500033" }
  ],
  "bank_detail": {
    "bank_name": "HDFC Bank", "account_number": "50100123456789",
    "ifsc_code": "HDFC0001234", "branch_name": "Hitec City"
  },
  "identification": { "aadhaar_number": "234567890123", "pan_number": "ABCDE1234F" }
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `first_name`, `last_name` | ✓ | Trimmed, whitespace-collapsed |
| `official_email` | ✓ | Unique across employees, compared case-insensitively |
| `joining_date` | ✓ | Not before 1950; at most a year in the future |
| `user_id` | | Must exist and not already belong to another employee |
| `employment_status` | | Default `probation` |
| `addresses` | | At most one of each type |
| `bank_detail`, `identification` | | Optional nested objects |
| Everything else | | Optional |

Creating an employee also writes the **opening row of the employment history**,
so the series covers the whole employment rather than starting at the first
amendment.

**Statutory identifier formats**, normalised before validation — separators are
stripped and letters upper-cased, so `2345 6789 0123` and `abcde1234f` are
accepted:

| Field | Shape |
| --- | --- |
| `aadhaar_number` | 12 digits, not starting 0 or 1 |
| `pan_number` | `ABCDE1234F` |
| `ifsc_code` | 4 letters, a zero, 6 alphanumerics |
| `uan_number` | 12 digits |
| `esi_number` | 17 digits |
| `pf_number` | letters, digits, slashes and hyphens |
| `passport_number` | 6–20 alphanumerics |

None is verified against the issuing authority — a shape check still catches the
transposed digit and the pasted-wrong-field mistakes that make up almost all real
errors.

### Lifecycle payloads

Every lifecycle endpoint accepts:

```json
{ "effective_date": "2026-06-01", "reason": "Probation completed", "notes": null }
```

`effective_date` defaults to today and may be back-dated — a transfer is
routinely recorded in arrears. Plus, per action:

| Endpoint | Additional fields |
| --- | --- |
| `/transfer` | `team_id`* , `business_unit_id` |
| `/designation` | `designation_id`* , `grade_id` |
| `/manager` | `reporting_manager_id` (null clears the line) |
| `/location` | `work_location_id`, `work_mode` |
| `/promote` | `designation_id`, `grade_id`, `salary_grade_id`, `ctc` — **at least one** |
| `/status` | `employment_status`* |

`*` required.

### `GET /api/v1/employees/{id}/history`

```json
[
  {
    "id": "…",
    "change_type": "promotion",
    "effective_date": "2026-08-03",
    "employment_status": "confirmed",
    "team": { "id": "…", "name": "Platform Engineering", "status": "active" },
    "designation": { "...": "..." }, "grade": { "...": "..." },
    "work_location": null, "reporting_manager": null,
    "summary": "Designation: HR Executive to Project Manager; Grade: Grade 1 to Grade 2; CTC revised",
    "reason": "Annual cycle",
    "notes": null,
    "created_at": "2026-08-03T12:57:00Z",
    "created_by": "37c8..."
  }
]
```

Newest first. Each row is the state **after** the change; `summary` is composed
when the row is written and frozen, so the timeline still reads correctly after a
master record is renamed. It names amounts but never quotes them.

**Append-only.** `PATCH`, `PUT` and `DELETE` on this path return `405`.

### `GET /api/v1/employees/{id}/sensitive`

Returns the unmasked bank account and government identifiers, for an edit form.

```json
{
  "employee_id": "…",
  "bank_detail": { "id": "…", "bank_name": "HDFC Bank", "account_number": "50100123456789", "ifsc_code": "HDFC0001234", "branch_name": "Hitec City" },
  "identification": { "id": "…", "aadhaar_number": "234567890123", "pan_number": "ABCDE1234F" }
}
```

**Every call is written to the audit trail** as `employee.sensitive.viewed`.

### `GET /api/v1/employees/export`

Returns a file rather than the envelope. Accepts every list parameter plus
`format=csv|xlsx`; the page parameters are ignored, and the result is capped at
10,000 rows.

```
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="employees-2026-08-03.csv"
```

No sensitive value is included — not even masked.

### `GET /api/v1/employees/dashboard`

```json
{
  "total_employees": 5, "employed": 5,
  "by_status": [{ "label": "Confirmed", "count": 3 }, { "label": "Probation", "count": 2 }],
  "by_business_unit": [{ "label": "Technology Services", "count": 4 }],
  "by_work_mode": [{ "label": "Hybrid", "count": 1 }],
  "joining_this_month": 0, "on_probation": 2, "on_notice": 0, "archived": 0
}
```

### Module-specific error codes

| `code` | Status | Meaning |
| --- | --- | --- |
| `duplicate_official_email` | 409 | Another employee holds this work address |
| `duplicate_identifier` | 409 | Another employee holds this Aadhaar, PAN, passport, UAN, PF or ESI |
| `user_already_linked` | 409 | That account already belongs to another employee |
| `invalid_user_reference` | 409 | No such account |
| `invalid_organization_reference` | 409 | A selected master is missing, archived or inactive |
| `invalid_manager` | 409 | The manager is missing, archived, or no longer employed |
| `manager_is_self` | 409 | An employee cannot report to themselves |
| `reporting_cycle` | 409 | The proposed manager reports to this employee |
| `has_direct_reports` | 409 | Other employees still report to this one |
| `not_on_probation` | 409 | Only an employee on probation can be confirmed |
| `already_in_team` / `already_has_designation` / `already_reports_to` | 409 | The lifecycle action would change nothing |
| `already_in_status` | 409 | On `/status` only; `PATCH` accepts the current status |
| `invalid_status_transition` | 409 | A former employee cannot re-enter the joining lifecycle |
| `record_archived` | 409 | Restore before editing |
| `already_archived` / `not_archived` | 409 | Archive/restore in the wrong state |
| `invalid_sort_field` | 400 | `sort_by` is not an allowed column |
| `invalid_date_range` | 400 | `joined_from` is after `joined_to` |

Duplicate-identifier messages name the other employee but **never repeat the
identifier**.

---

## 8. Worked example

```bash
BASE=http://localhost:8000/api/v1

# 1. Sign in, keeping cookies in a jar
curl -sS -c cookies.txt -X POST "$BASE/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"Admin@12345"}'

TOKEN="<access_token from the response>"

# 2. Call an authenticated endpoint
curl -sS "$BASE/auth/me" -H "Authorization: Bearer $TOKEN"

# 3. Rotate the session (uses the cookie; writes the new one back)
curl -sS -b cookies.txt -c cookies.txt -X POST "$BASE/auth/refresh"

# 4. Sign out
curl -sS -b cookies.txt -X POST "$BASE/auth/logout" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"all_sessions":false}'
```

---

## 9. Conventions for new endpoints

1. Version under `/api/v1`. Breaking changes go to `/api/v2`.
2. Return `APIResponse[T]`; never build a response dict by hand.
3. Never raise `HTTPException` in a route — raise a domain exception from
   `app/core/exceptions.py` and let the global handlers format it.
4. Validate with a Pydantic model. Never read `request.json()` directly.
5. Paginated collections return `Page[T]`: `{ "items": [...], "meta": {...} }`.
6. Write `message` for a human. It is displayed verbatim.
# Recruitment ATS

Authenticated ATS endpoints use the `/api/v1/recruitment` prefix. They cover dashboard metrics, reference stages/sources, opening creation and publication, candidate CRUD/search/duplicate detection, stage movement, document links, internal notes, talent pools, and CSV/XLSX export.

Important invariants: `POST /openings` accepts approved requisitions only; `POST /candidates` accepts published openings only and requires a valid Document Vault resume; duplicate email or mobile returns HTTP 409.
# Interview Management

Authenticated endpoints under `/api/v1/interviews` cover dashboard metrics, calendar/list queries, scheduling, editing, conflict-safe rescheduling, cancellation, panel replacement, structured feedback, candidate decisions, Document Vault attachments, timelines, and CSV/XLSX export.
# Preboarding and onboarding

The `/api/v1/onboarding` API covers candidate portals, HR document review, policy acknowledgement, employee conversion, onboarding cases/tasks, completion, welcome data, dashboards and CSV/XLSX reports. See [the module guide](PreboardingOnboardingModule.md).

# Projects and clients

The `/api/v1/projects` API provides client CRUD, project management, assignment/change/removal, allocation history, bench discovery, dashboards and CSV/XLSX exports. See [the project allocation guide](ProjectClientAllocationModule.md).

# Workforce operations

The `/api/v1/workforce` API covers shifts and their assignment history,
attendance check-in/check-out and corrections, leave types, balances, requests
and decisions, holiday calendars, weekly timesheets with submission and
approval, two dashboards, a monthly calendar, and six reports in CSV/XLSX/PDF.
See [the module guide](WorkforceModule.md).

Important invariants: a second check-in on a day returns HTTP 409; leave is
measured in working days with weekends and holidays excluded; applying holds the
balance and approving spends it; only a submitted timesheet can be decided, and
only a rejected one can be saved again.

# Roles and permissions

The `/api/v1/roles` API covers the permission catalogue, role CRUD, and role
assignment (`/api/v1/users/{id}/roles`). See [the module guide](RBACModule.md).

**Breaking change:** `GET /auth/me` now answers with the session --
`{user, roles, permissions, is_superuser}` -- rather than a bare profile. The
permissions travel with it because the first render needs them to decide which
navigation exists.

Every other endpoint is guarded by a `module:action` permission. A 403 names the
missing permission in `errors[]`, because this is an internal system and a
refusal that says only "denied" turns every access question into a support
ticket. The 14 deliberately unguarded endpoints -- health, auth, self-service --
are enumerated in `tests/integration/test_rbac.py`.
