# Performance Management

Phase 13 adds appraisal cycles, weighted goals, two-sided reviews, recognition
and continuous feedback, with an append-only performance history behind them.

## Three rules

**A submitted review is never rewritten.** Self, manager and final reviews are
written once. Re-submitting is refused rather than silently overwriting, because
a rating somebody disputes six months later has to still say what it said. A
review is a `draft` until it is submitted, and there is no transition back.

**Weightage is a budget.** An employee's live goals may total at most 100% of
their cycle. The check runs against everything *else* they hold, so editing a
goal's weight never trips over its own current value.

**Progress is appended, never edited.** The goal carries a denormalised
percentage so list screens do not aggregate on every render; the trail of who
reported what, and when, is the record.

## The cycle

`Draft → Active → Closed → Archived`. A cycle is configured while it is a draft;
only an **active** cycle accepts goals and reviews. `Closed` means every final
rating is in, and `archived` takes a cycle out of normal view without destroying
a year of performance data.

Within an active cycle one employee's appraisal runs
`goals assigned → progress recorded → self review → manager review → finalised`.
Self and manager ratings have the same shape — a score against one goal, with
comments — so they share `goal_ratings` and are told apart by a stage column.
Finalising requires a manager review and writes the row that
`performance_history` and every later cycle read from.

## Tables

`performance_cycles`, `goals`, `goal_progress`, `goal_ratings`, `self_reviews`,
`manager_reviews`, `final_reviews`, `recognitions`, `continuous_feedback` and
`performance_history`.

## API

Twenty-two operations under `/api/v1/performance`:

| Area | Operations |
| --- | --- |
| Cycles | list, create, get, update, move through the lifecycle |
| Goals | list, assign, get, amend, record progress |
| Reviews | read one employee in one cycle; submit self, manager, finalise |
| Culture | list/leave continuous feedback, list/give recognition |
| Reporting | dashboard, analytics, an employee's history, CSV/XLSX/PDF export |

## Scope

Access narrows by reporting line exactly as elsewhere: a Manager or Team Lead
sees and rates **their direct reports**, while a holder of `employees:view_all`
stays organization-wide. Nothing in the module checks a role name — see
[`RBACModule.md`](RBACModule.md).

## Screens

`/performance` and its cycle, goal and review views for the appraisal itself;
`/employee/*` for an employee's own goals and reviews; `/manager/performance`
for a team's; `/hr/performance` for the organization-wide read described in
[`HRModule.md`](HRModule.md).
