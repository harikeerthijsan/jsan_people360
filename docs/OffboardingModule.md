# Resignation & Offboarding

Phase 18 carries the complete separation lifecycle: an employee resigns, their
manager decides, HR processes, five departments clear, the employee completes an
exit interview and collects their letters, and the record goes inactive without
anything being deleted.

## The one decision the schema turns on

**The resignation is the request; the offboarding case is the work.** They are
separate tables with separate lifecycles because they answer to different
people — a manager decides a resignation, five departments work a case over a
notice period. One status column cannot honestly say both "the manager has not
looked at this yet" and "IT still has the laptop".

Everything downstream hangs off the *case*, so a future termination or
retirement can open one without inventing a resignation to hang it on.

## Approving and processing are different acts

This is the access model in one sentence, and the reason two new permission
actions exist:

| Act | Permission | Who | What it does |
| --- | --- | --- | --- |
| Approve | `resignation:approve` | **Manager** | Decides their own direct report's resignation. Team-scoped. |
| Process | `resignation:process` | **HR** | Verifies notice, settles the last working day, opens the case. |

HR Admin holds every resignation action **except** `approve` — the same
subtraction [`HRModule.md`](HRModule.md) describes for the workforce modules,
and for the same reason. Collapsing the two into `update` would mean either a
manager who can start an offboarding or an HR user who can decide a team's
resignations.

Fifteen permissions across four modules: `resignation`, `offboarding`,
`exit_interview`, `exit_documents`. `offboarding:update` is "tick a row assigned
to me"; `offboarding:manage` is "administer anybody's case" — reassign a task,
force a completion, override a settled date.

## The workflow

```
Draft → Submitted → Manager review → HR review → Approved
      → Notice period → Clearance → Exit interview → Completed
```

`Rejected`, `Withdrawn` and `Cancelled` are the terminal exits. **Withdrawn and
cancelled are deliberately distinct**: an employee withdraws their own
resignation before it is approved; HR or an administrator cancels one that has
already been approved, which also cancels the case and returns the employee to
active.

An employee with no reporting manager goes straight to HR review rather than
sitting in a queue nobody owns.

## The notice period is configuration

§6 of the brief says not to hardcode one, and nothing in the schema held it.
`employment_types.notice_period_days` is where it belongs — a consultant's
notice and a full-time employee's differ, and that is a property of the
contract. `NULL` means "not configured" and falls back to a named default; `0`
means "no notice required", which is a different statement and is honoured.

It is **resolved once, when the resignation is submitted, and copied onto the
row**. A policy change six weeks into somebody's notice must not silently move
their last working day. An authorized adjustment is a deliberate write, refused
without a reason, and recorded in history as an override.

## What an exit does and does not do

**Does:** ends live project allocations, sets the employee `inactive`, closes
the case, and stops new attendance, leave and timesheets.

**Does not:** delete anything. Attendance, leave, timesheets, projects,
performance, documents, the resignation and the case itself all remain exactly
where they were.

The post-exit block has two triggers, because they become true at different
moments: an employee whose offboarding is *complete* is inactive and may record
nothing; an employee past their last working day but not yet closed out may
record nothing dated after it. The fortnight between the two is when this would
otherwise be missed.

## Clearance

A case opens with 21 checklist tasks across HR, Manager, IT, Admin and Finance,
six asset rows and five access rows — a starting configuration, not a limit. HR
adds, reassigns and waives rows on a live case.

**`Waived` is a completion, not a skip.** A task nobody has to do — an asset the
employee never held, a system they never had — still has to be answered, or the
checklist stalls on rows that will never be ticked.

Access clearance is **tracked, not performed**. Nothing here reaches out to a
mail server or an identity provider; `revoked` records that somebody in IT did
it and said so.

## Full & final settlement

Status, reference and date. **No figure is calculated.** No salary, tax, PF, ESI
or gratuity computation appears anywhere in this module, and none should until
there is a payroll module entitled to compute it.

## Tables

`resignations`, `resignation_history`, `offboarding_cases`, `offboarding_tasks`,
`handover_records`, `asset_clearance`, `access_clearance`, `exit_interviews`,
`exit_documents`, `final_settlement_tracking`.

Cases are `OFF-000001` onwards and resignations `RES-000001`, both from
PostgreSQL sequences. A partial unique index enforces at most one live
resignation per employee.

`asset_clearance` is deliberately **not** an asset register: there is no asset
module, so the rows are created per case and describe what the employee is being
asked to hand back. If an asset module arrives, it supplies the rows.

## API — 32 operations

| Audience | Prefix | Guarded by |
| --- | --- | --- |
| Employee | `/me` | Identity only — no permission, and no route takes an employee id |
| Manager | `/manager` | `resignation:approve` / `offboarding:update` **and** manager scope |
| HR & Admin | `/offboarding` | The module permissions; administrative acts need `offboarding:manage` |

The employee routes carry no `require(...)` guard for the same reason nothing
under `/me` does: guarding one would let an administrator take away an
employee's ability to resign or to read their own relieving letter.

## Security

**No self-service write schema carries an employee id.** Not
`ResignationSubmit`, not `ExitInterviewSubmit` — so submitting somebody else's
resignation is a thing that cannot be expressed rather than a thing a guard has
to catch. The test suite asserts this on the schema, not just over HTTP.

The manager scope excludes the caller, which is also what stops a manager
approving their own resignation through the team screen — refused by the check
that was already there rather than by a special case.

Every override is audited **as** an override: an admin rewriting a last working
day and HR settling one through the normal step are the same column change and a
completely different fact.

## Screens

`/employee/resignation`, `/employee/exit-interview`, `/employee/offboarding`,
`/manager/offboarding`, `/hr/offboarding`.

## Deliberately not built

Payroll and statutory settlement calculations, automated external account
deactivation, and a full asset-management module. Each is named in the brief as
out of scope, and each is a place where a plausible-looking half-implementation
would be worse than nothing.
