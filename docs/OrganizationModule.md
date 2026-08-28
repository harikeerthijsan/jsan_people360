# Organization Management module

The master-data system every other HR module builds on. Recruitment, employee
records, attendance, leave, performance and offboarding all *reference* these
records rather than storing their own copies of a team or a grade.

Status: **complete and production-ready** (Phase 2).

---

## 1. What it manages

Seven masters, in two groups.

**Hierarchy** — each level belongs to the one above it:

```
Business Unit          e.g. Technology Services (TECH)
   ├── Team            e.g. Platform Engineering
   └── Designation     e.g. Software Engineer (level 2)
```

**Reference** — flat lists with no parent:

| Master | Purpose |
| --- | --- |
| Organization | The legal entity: company and legal name, registration, GST/PAN, logo, website, time zone, currency, address |
| Location | Offices and work sites, each with an IANA time zone |
| Employment type | Full Time, Contract, Consultant, Internship, Freelancer |
| Grade | Compensation and seniority bands: G1–G3, M1, M2 |

---

## 2. Two independent lifecycles

A record has a **status** and, separately, may be **archived**. Conflating them
is the most common misreading of this module.

| | Meaning | Reversible | Effect |
| --- | --- | --- | --- |
| `status = active` | In normal use | — | Selectable everywhere |
| `status = inactive` | Retained but discouraged | Yes, edit | Hidden from *new* selections; existing references unaffected |
| archived (`deleted_at` set) | Soft deleted | Yes, restore | Excluded from every read by default; existing references unaffected |

There is no hard delete. HR data is subject to retention obligations, and a row
that other modules point at must not vanish.

### Rules the API enforces

- A record cannot be archived while **live children** reference it. Archiving a
  business unit with active teams returns `409 has_active_children` naming
  the count.
- A record cannot be **restored** while its parent is archived — that would
  produce an orphan. Returns `409 parent_archived`.
- A child cannot be **created or moved** under a parent that is archived or
  inactive. Returns `409 invalid_<parent>`.
- An archived record cannot be **edited**. Restore it first. Returns
  `409 record_archived`.
- An existing child whose parent was *later* deactivated stays editable — the
  parent check only runs when the parent reference actually changes. Otherwise
  deactivating a business unit would freeze everything beneath it.

---

## 3. Uniqueness and normalisation

Master data is referenced by name and code, so near-duplicates are a data-quality
bug rather than a nuance.

**Normalisation, applied server-side before anything is stored:**

| Field | Rule |
| --- | --- |
| `name` | Trimmed, internal whitespace runs collapsed to one space |
| `code` | Trimmed, upper-cased, internal spaces become `_`; must match `^[A-Z0-9][A-Z0-9_-]*$` |
| `description` and other optional text | Trimmed; blank becomes `NULL`, never `""` |
| `currency` | Upper-cased, must be a 3-letter ISO 4217 code |
| `timezone` | Must be a real IANA identifier, checked against `zoneinfo` |
| GST / PAN | Upper-cased, shape-checked (not verified with the issuer) |

**Uniqueness** is enforced *twice*: in the service, so the user gets a message
naming the field, and in the database, so a race cannot slip through.

| Master | Code | Name |
| --- | --- | --- |
| Business unit, Location, Employment type, Grade | Globally unique | Globally unique |
| Designation | Globally unique | Unique **within its business unit** |
| Team | (no code) | Unique **within its business unit** |
| Organization | (no code) | Unique; registration number also unique |

Database uniqueness is enforced on `lower(column)`. A plain `UNIQUE` would accept
both `GIS` and `gis`.

Archived records **keep** their name and code. Attempting to reuse one returns a
409 that says so explicitly — "restore that record instead of creating a
duplicate" — rather than a bare integrity error.

---

## 4. API

Base: `/api/v1`. Every endpoint requires `Authorization: Bearer <token>` and
returns the standard envelope.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/{master}` | Paged list with search, filter and sort |
| `GET` | `/{master}/{id}` | One record (archived records included) |
| `POST` | `/{master}` | Create → `201` |
| `PATCH` | `/{master}/{id}` | Partial update |
| `POST` | `/{master}/{id}/archive` | Soft delete |
| `POST` | `/{master}/{id}/restore` | Undo the archive |

`{master}` is one of: `organizations`, `business-units`,
`teams`, `designations`, `locations`, `employment-types`,
`grades`.

Plus one extra: `GET /organizations/primary` — the profile other modules default
to, so nothing has to hard-code an id.

**55 operations in total.** Full request/response detail is in
[`API.md`](API.md#5-organization-management).

### List parameters

| Parameter | Default | Notes |
| --- | --- | --- |
| `page`, `page_size` | 1, 20 | `page_size` capped at 100 |
| `search` | — | Case-insensitive across name, code, description and entity-specific text. LIKE wildcards are escaped and matched literally |
| `status` | — | `active` or `inactive`; omit for both |
| `archived` | `false` | `true` returns **only** archived records. Live and archived are never mixed in one page |
| `sort_by`, `sort_order` | `name`, `asc` | `sort_by` is checked against a per-entity allowlist; anything else returns `400 invalid_sort_field` rather than reaching SQL |
| `business_unit_id` | — | Parent filter, on the masters that have a parent |

---

## 5. Audit

Every create, update, archive and restore writes an `audit_logs` row capturing
the action, entity type, record id, timestamp, actor and request id.

Actions follow `organization.<entity>.<verb>`:

```
organization.business_unit.created     organization.team.archived
organization.designation.updated       organization.grade.restored
organization.profile.created           organization.team.updated
```

A rejected write is **not** audited as a change — the request rolls back, so the
trail records only what actually happened.

---

## 6. Architecture

The module follows the platform's Clean Architecture. What is worth knowing is
where the *shared* behaviour lives, because that is what stops nine entities
drifting apart.

### Backend

| Layer | Shared | Per entity |
| --- | --- | --- |
| Models | `app/models/mixins.py` — name/code/status columns, status CHECK, case-insensitive unique index helpers | One file per entity |
| Schemas | `app/schemas/masters.py` — `Annotated` field types carrying their own normalisation | One file per entity |
| Repositories | `app/repositories/master_repository.py` — paged search, scoping, uniqueness lookups | `organization_repository.py`, ~10 lines each |
| Services | `app/services/master_service.py` — CRUD, duplicate detection, archive/restore, audit | `organization_service.py` — only reference checks and archive guards |
| Routes | `app/api/master_router.py` — builds the six endpoints | `routes/organization.py` — nine declarations |

Normalisation is attached to the **types**, not to each model:

```python
MasterName = Annotated[str, Field(min_length=2, max_length=150), AfterValidator(normalise_name)]
```

A field then cannot be declared without its normalisation, which is exactly the
mistake that lets `" GIS "` and `"GIS"` both reach the database.

### Frontend

One registry drives every screen:

```
src/features/organization/
├── config/master-registry.tsx   ← columns, form fields, validation, labels
├── components/                  ← three generic screens
├── hooks/                       ← data hooks + URL-backed list state
├── schemas/                     ← Zod, mirroring the server rules
├── api/                         ← one client, bound to a slug
└── types/
```

Routes are dynamic, so nine masters need five page files rather than thirty-six:

```
/organization                      overview
/organization/[master]             list
/organization/[master]/new         create
/organization/[master]/[id]        detail
/organization/[master]/[id]/edit   edit
```

`generateStaticParams` keeps the real routes enumerable at build time; an
unrecognised slug 404s.

**List state lives in the URL** (`?q=`, `?view=`, `?sort=`, `?dir=`, `?page=`), so
a filtered view can be bookmarked, shared and restored by the back button.

---

## 7. Adding a tenth master

**Backend**

1. Model in `app/models/`, composing `AuditableBase` and `CodedMasterMixin`.
2. Export it from `app/models/__init__.py`.
3. `alembic revision --autogenerate -m "add widgets table"`, then read it.
4. Schemas in `app/schemas/widget.py` from the `masters.py` bases.
5. A repository class in `organization_repository.py` (~10 lines).
6. A service class in `organization_service.py` — only what is specific.
7. Providers in `app/api/deps.py`.
8. One `build_master_router(...)` call in `routes/organization.py`.

**Frontend**

1. Add the slug to `MasterSlug`.
2. Add a Zod schema.
3. Add one entry to `MASTER_REGISTRY`.
4. Add the nav link.

No new pages, no new table or form components, no changes to the API contract.

---

## 8. Deliberate limitations

- **No RBAC.** Per the current phase, every authenticated user can create,
  edit and archive every master. The authorisation choke point is a single
  dependency (`get_current_user`), so adding roles is additive.
- **Team manager references `users`.** The Employee module does not exist yet.
  The column is already a nullable UUID foreign key, so pointing it at
  `employees` later is a migration, not a redesign.
- **No bulk import.** Records are created one at a time. A CSV import is the
  obvious next addition and would sit on the existing service layer.
- **Reference pickers load 100 active records.** Fine for the expected data
  volumes; a searchable async picker is the upgrade path if a master grows past
  that.
- **Time zones offered in the UI are a curated list.** The server validates
  against the full IANA database, so extending the list is a frontend-only
  change.
