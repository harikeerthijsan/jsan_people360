# Workforce Operations — Attendance, Leave and Timesheets

Attendance, leave and timesheets are one module because they are one day. A leave
day suppresses an absence, a holiday is not charged as leave, and a timesheet is
read against the attendance for the same date. Splitting them into three modules
would mean three services reaching into each other.

**Who sees what** is not this module's decision. The register, the leave list,
the timesheet list and every approval are narrowed by reporting line: a Manager
or Team Lead reaches their direct reports, HR and Super Admin reach everybody.
The rule and its enforcement points live in
[`RBACModule.md`](RBACModule.md#team-scoping--whose-records-not-just-which-endpoint).

## The four rules

Everything else in this module follows from these. Each is enforced in the
service layer, covered by an integration test, and stated on the screen that
depends on it.

**A day belongs to one attendance record.** Checking in twice does not create a
second row; it is refused. Every monthly figure — attendance percentage, late
arrivals, overtime — depends on that being true.

**Leave is counted in working days.** Weekends and holidays inside a range are
excluded when a request is measured, so a Friday-to-Monday absence costs two
days, not four. Getting this wrong quietly overcharges people for their own
weekends.

**Balance is held, then spent.** Applying moves days into `pending`; approving
moves them from `pending` into `used`; rejecting or cancelling releases them. The
held amount is what stops two overlapping requests both being approved against
the same entitlement.

**A submitted timesheet is not edited.** It is approved or rejected. Only a
rejected week can be saved again, and saving is what returns it to draft — so an
approval always refers to a state somebody actually looked at.

## Tables

Migration `0014_workforce_operations` creates eleven tables. All use UUID primary
keys, audit columns and soft deletion.

| Table | Holds |
| --- | --- |
| `shifts` | Working patterns: window, grace, break, weekly off |
| `employee_shifts` | Which shift an employee was on, and when |
| `attendance_records` | One row per employee per day |
| `attendance_regularizations` | Requests to correct a day, and their decisions |
| `leave_types` | What can be applied for, and how much of it |
| `leave_balances` | Entitlement, taken and held, per employee per year |
| `leave_requests` | Applications and their decisions |
| `holiday_calendars` | A named set of holidays for a year, optionally per location |
| `holidays` | The dates inside a calendar |
| `timesheets` | One week per employee, with a `TS-` code from a sequence |
| `timesheet_entries` | Individual lines: project, day, task, hours |

Three shape decisions are worth stating.

`employee_shifts` is closed and replaced, never edited — exactly like a project
allocation. An attendance record from March has to be read against the shift that
was in force in March, not the one assigned since.

`leave_balances.remaining` is a derived property, not a stored column. A stored
total is one write away from lying, and a leave balance is the number an employee
will dispute.

`shifts.weekly_off` is a JSONB list of weekday integers with Monday as 0, matching
Python's `date.weekday()` and the frontend's `WEEKDAYS` array. A shift must have
at least one working day.

### Seeded on migration

A shift and a leave type are not sample data: attendance cannot be marked without
a shift, and leave cannot be applied for without a type. Migration `0014` seeds
four shifts (General, Morning, Evening, Night) and the eight statutory Indian
leave types (CL, SL, EL, ML, PL, BL, Comp Off, LOP), so the first employee added
to the system can already check in and apply for casual leave.

## How a day is measured

`check_in` opens the day's record against the shift in force on that date.
Arrival later than the shift start plus its grace counts as late. `check_out`
closes it and computes worked minutes (less the shift's break), early-exit
minutes and overtime. A day may be back-dated for a forgotten entry; a future
date is refused, because that is a prediction rather than a record.

Where no shift is assigned, the day is still recorded — worked minutes are
measured, and lateness and overtime are simply not claimed, since there is no
window to measure them against.

## How leave is measured

`_working_days` walks the requested range and skips two kinds of day: those in
the employee's shift `weekly_off` (falling back to Saturday and Sunday when no
shift is assigned), and those on any holiday calendar. A half day is worth 0.5
and is only allowed on a single date — rounding a multi-day half-day request
would produce a balance nobody could explain.

Balance rows are created the first time they are read rather than by a nightly
job, so an employee who joins mid-year sees their entitlement immediately.

## API

Twenty-seven endpoints under `/api/v1/workforce`. Static segments are registered
before the `/{id}` forms, or `/dashboard` would be read as an identifier.

| Method | Path | Does |
| --- | --- | --- |
| GET | `/dashboard` | The day at a glance, plus month-to-date attendance |
| GET | `/timesheets/dashboard` | Draft, submitted, approved, rejected, missing |
| GET | `/calendar/{employee_id}` | One month, with leave and holidays in place |
| GET | `/reports/export` | Six reports in CSV, XLSX or PDF |
| GET, POST | `/shifts` | List and create |
| PATCH | `/shifts/{id}` | Edit |
| POST | `/shifts/assign` | Close the current assignment, open a new one |
| GET | `/shifts/history/{employee_id}` | Every assignment, newest first |
| GET | `/attendance` | The register, filtered and paged |
| POST | `/attendance/{employee_id}/check-in` | Open the day |
| POST | `/attendance/{employee_id}/check-out` | Close it and compute the figures |
| GET, POST | `/regularizations`, `/regularizations/{employee_id}` | Corrections |
| POST | `/regularizations/{id}/decide` | Approving is what amends the record |
| GET, POST | `/leave/types` | List and create |
| PATCH | `/leave/types/{id}` | Edit |
| GET | `/leave/balances/{employee_id}` | Creates the year's rows on first read |
| GET | `/leave` | Requests, filtered and paged |
| POST | `/leave/{employee_id}` | Apply; holds the balance |
| POST | `/leave/{id}/decide` | Approve (spend) or reject (release) |
| POST | `/leave/{id}/cancel` | Release; leave already taken cannot be cancelled |
| GET, POST | `/holidays` | Calendars, with their dates |
| GET, POST | `/timesheets`, `/timesheets/{employee_id}` | List and save a week |
| GET | `/timesheets/{id}` | One week with its entries |
| POST | `/timesheets/{id}/submit` | Lock it for review |
| POST | `/timesheets/{id}/decide` | Approve, or send it back |

## Screens

Thirteen screens under three sections of the sidebar.

| Route | Screen |
| --- | --- |
| `/attendance` | Workforce dashboard: present, absent, on leave, remote, pending queues |
| `/attendance/register` | The register, with check-in and check-out on the same page |
| `/attendance/calendar` | One employee's month, colour-coded, with a legend |
| `/attendance/regularizations` | Corrections: request and decide |
| `/attendance/reports` | Six reports, one shared period, three formats |
| `/shifts` | Shift master |
| `/shifts/assignments` | Who is on which shift, and the full history |
| `/leave` | Balances above, requests below, apply from either |
| `/leave/approvals` | The approval queue, defaulting to pending |
| `/leave/types` | Leave type master |
| `/leave/holidays` | Holiday calendars by year |
| `/timesheets` | The weekly grid, with per-day totals |
| `/timesheets/approvals` | The review queue, with the week's entries in the dialog |

Check-in and check-out live on the register rather than on a separate "mark
attendance" page: the person marking a day almost always wants to see whether it
is already marked, and splitting them produces the duplicate-entry attempt the
API then has to refuse.

The balances sit above the leave form because the number that decides whether an
application is worth making is "days remaining", and putting it behind a tab
would mean applying first and finding out afterwards.

## What this module does not do

Roles are not implemented anywhere in the product yet, so every authenticated
user can see and decide everything here — including other people's leave reasons.
That is a product-wide gap, not a workforce one, but it is worth knowing before
this module is used with real data.

Payroll is out of scope. Leave types carry an `is_paid` flag and attendance
carries the minutes, but nothing here calculates pay.

## Testing

`backend/tests/integration/test_workforce.py` — 41 tests, one per rule that a
later refactor could break without any signature changing: double check-in
refused, weekends not charged, balance held then spent, overlapping leave
refused, submitted timesheets locked, holidays free.

`frontend/src/features/workforce/schema.test.ts` — 21 tests over the client-side
mirrors: zero-length shifts, carry-forward coherence, multi-day half days,
duplicate holiday dates, over-24-hour days, entries outside the week.
