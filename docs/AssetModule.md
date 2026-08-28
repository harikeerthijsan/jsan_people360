# Asset Management

Phase 19 adds the asset register: what the company owns, who is holding it, what
condition it is in, and everywhere it has been.

## The one decision the schema turns on

**The asset row holds current state; the transaction tables hold what
happened.** An assignment, a return and a transfer are each a *record of an
event*, never a column being overwritten.

That is the difference between an inventory and a register. Setting
`assigned_to = somebody_else` answers "who has it now" and destroys "who had it
in March" — which is the question an asset system actually gets asked, usually
months later, about a thing that has since been disposed of.

`Asset.current_assignment_id` is a denormalised pointer *into* the assignment
table, kept honest in one place. It exists so the list screen is one join rather
than a subquery per row. The truth is the assignment record, and `asset_history`
is the complete account.

## Status is a table, not a chain of conditionals

Every status change goes through one gate, which consults
`ASSET_STATUS_TRANSITIONS`:

```
available  → assigned, reserved, under_maintenance, damaged, lost, retired
assigned   → available, under_maintenance, damaged, lost
reserved   → available, assigned
maintenance→ available, damaged, retired
damaged    → under_maintenance, retired
lost       → under_maintenance, retired
retired    → disposed
disposed   → (nothing)
```

The interesting property is what is **absent**. There is no route out of
`disposed`. `damaged` cannot become `available` in one step — something has to
have been done to it first. A recovered item goes through maintenance for
inspection before it is offered to anybody again.

Assignment is not reachable from the status endpoint at all: an asset becomes
assigned by being given to somebody, and that needs an assignment record behind
it. The permitted next moves are published at `GET /assets/{id}/transitions`, so
the client never holds a copy of the table.

## Editing cannot rewrite history

`AssetUpdate` has no `status`, no `condition` and no holder. §8 of the brief
says an edit must not destroy audit history, and the way to guarantee that is to
leave the fields out of the model — not to check for them at the call site.

## Access model

| Seat | Reach |
| --- | --- |
| **Employee** | Their own assigned assets, via `/me/assets`. No id, no permission — identity only |
| **Manager** | Direct reports' assets, read only. `assets:view` + `ManagerScope` |
| **HR** | What one employee holds, for a clearance. `assets:view` + `employees:view_all` |
| **Admin** | Everything: 11 permissions including all six custody actions |
| **Super Admin** | Unrestricted |

**HR holds `assets:view` and nothing else.** The eight custody and lifecycle
actions belong to Administrator. HR needs to *see* what a leaver is holding in
order to run a clearance; issuing, recalling, repairing or writing off company
property is a different job. There is no HR endpoint that does any of it — the
absence is the control.

**Scoping an asset is indirect**, and it is the one subtlety in the module. An
asset has no employee; its *open assignment* does. So a scoped query joins
through `asset_assignments` and narrows on the holder — which also means an
unassigned laptop in a cupboard belongs to nobody and is invisible to anyone
whose reach is a reporting line. That is correct: only an org-wide caller has
business seeing the whole cupboard.

## Permissions

Six new actions were needed. They are separate because they are separate
authorities, and organizations routinely split them — the person who hands out
laptops is rarely the person who writes one off.

`assets:view` · `create` · `update` · **`assign`** · **`return`** ·
**`transfer`** · **`maintain`** · **`retire`** · **`dispose`** · `manage`
(categories) · `export`

| Role | Asset grants |
| --- | --- |
| Admin, Super Admin | all 11 |
| HR Admin, HR Executive | `view` |
| Manager, Team Lead | `view` |
| Employee | none — self-service is identity-based |

## Offboarding integration

§16 says not to build a second asset-clearance system, and nothing new was
built. The `asset_clearance` table from phase 18 grew **one column**, `asset_id`.

When phase 18 wrote that table, its docstring said: *"There is no asset module
in this platform… If an asset module arrives, it supplies the rows and this
table keeps recording their return."* That is exactly what now happens.

**Opening a case** seeds the clearance list from what the employee actually
holds, instead of the six generic lines it used to guess at. Categories marked
non-returnable (a headset the company does not want back) are seeded already
waived, so they appear on the list without holding an exit open. The generic
list survives as a fallback for an organization that has not populated the
register yet.

**Resolving a row works in both directions.** Ticking a laptop "returned" on the
offboarding screen frees it in the register; processing the return in the asset
module marks the clearance row settled. Without the second direction the two
would disagree the moment somebody tried to issue the laptop to the next joiner.

**A waiver is audited** as `asset.clearance.waived`, and recorded as an event on
the asset itself — "written off during somebody's exit" is a fact about the
laptop that outlives the case.

Completion still blocks on outstanding clearance, using the mechanism phase 18
already had.

## Tables

`assets`, `asset_categories`, `asset_assignments`, `asset_returns`,
`asset_transfers`, `asset_maintenance`, `asset_history` — plus `asset_id` on the
existing `asset_clearance`.

Asset codes are `AST-000001` onwards from a PostgreSQL sequence. Two **partial
unique indexes** carry rules a plain constraint cannot express:

- one *open* assignment per asset (`WHERE returned_at IS NULL`)
- a serial number unique *where present* — most accessories have none, and
  several NULLs are not duplicates of each other

## Categories are configuration

Fourteen are seeded (§2), and every one is editable. `returnable` is the only
judgement in the seed data: it decides whether a category blocks an exit
clearance by default. Any row can still be waived by an authorized user, and the
waiver is audited.

## API — 22 operations

| Prefix | Audience |
| --- | --- |
| `/me/assets` | Employee — identity only |
| `/manager/assets` | Manager — `assets:view` + team scope |
| `/hr/assets/{employee_id}` | HR — org-wide read for a clearance |
| `/assets/**` | Admin — the register, custody, maintenance, dashboard, reports |

Eight reports export to CSV or XLSX through the existing reporting approach.

## Deliberately not built

Procurement, purchase orders, depreciation and asset accounting. The register
records what a thing cost, not what it is worth now — depreciation is a finance
concern and belongs with payroll and the rest of the financial modules, none of
which exist yet.
