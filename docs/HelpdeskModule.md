# Helpdesk

Phase 20 adds the internal helpdesk: an employee asks HR, IT, Admin, Finance or
Facilities for something, and the request is tracked from raised to closed with
a conversation, a response-time clock and a complete history.

## The one decision the schema turns on

**The requester never appears in a request body.** `POST /me/helpdesk` has no
employee field at all — the requester is whoever the access token says, which
makes the IDOR class of bug unrepresentable rather than merely checked for.
Raising a ticket *for* somebody (a request taken over the phone) is a different
endpoint (`POST /helpdesk`), a different schema (`TicketRaiseFor`), a different
permission (`helpdesk:create`), and the record keeps both names: `raised_by`
and `raised_for`.

## Internal notes cannot leak

An agent's comment can be marked `internal` — a working note the requester must
never see. Three layers keep it that way, of which only the last is load
bearing:

1. The employee screens have no way to render one.
2. The employee endpoints filter internal comments out in SQL
   (`public_for_ticket()`).
3. **`MyTicketComment` has no `internal` field.** The read model the employee
   endpoints answer with cannot carry the flag, so a future bug in layer 2
   still has nowhere to put the note.

## Status is a table, not a chain of conditionals

`TICKET_STATUS_TRANSITIONS` in `app/models/enums.py`:

```
open                → in_progress, waiting_on_employee, resolved, cancelled
in_progress         → waiting_on_employee, resolved, cancelled
waiting_on_employee → in_progress, resolved, cancelled
resolved            → closed, reopened
reopened            → in_progress, waiting_on_employee, resolved, cancelled
closed              → (nothing)
cancelled           → (nothing)
```

What is absent matters: nothing leaves `closed` or `cancelled`, and `reopened`
is reachable only from `resolved` — an employee can say "this is not actually
fixed", and nobody can reopen a request that was never answered. The ticket
detail response carries `allowed_transitions`, so the frontend's status control
offers exactly what the server will accept and holds no copy of the table.

## Queues, categories and the SLA clock

Categories are rows, not code (`GET /helpdesk/categories`, seeded with eight).
Each category names a queue (`hr`/`it`/`admin`/`finance`/`facilities`) and an
optional `sla_hours`; `DEFAULT_SLA_HOURS` supplies one from priority when the
category doesn't. The queue and the due time are **copied onto the ticket at
raise time** — recategorising later moves future work, and escalating a late
ticket does not reset its clock.

## Scoping

`GET /helpdesk` is narrowed by the platform's one scoping mechanism,
`EmployeeScope`, on `raised_by_id OR raised_for_id`: a manager holding
`helpdesk:view` sees their team's requests; an HR agent with
`employees:view_all` sees the whole desk. Supplying `employee_id` as a filter
never widens anything — the id is checked against the caller's scope first.

## Access model

| Seat | Reach |
| --- | --- |
| **Employee** | Own requests via `/me/helpdesk` — raise, read, reply, reopen. Identity only, no permission |
| **Manager / Team Lead** | `helpdesk:view` — their team's requests, read only |
| **HR Executive** | view, update, assign — works the desk |
| **HR Admin / Admin** | everything, including raising on behalf and category administration |

## Endpoints

Employee: `GET/POST /me/helpdesk`, `GET /me/helpdesk/{id}`, `POST …/reply`,
`POST …/reopen`.

Desk: `GET/POST /helpdesk`, `GET /helpdesk/dashboard`,
`GET/POST/PATCH /helpdesk/categories`, `GET /helpdesk/{id}`, `POST …/comments`,
`POST …/status`, `POST …/assign`, `POST …/reclassify`.

## Frontend

- `/employee/helpdesk` — raise, follow, reply, reopen (My Workspace)
- `/hr/helpdesk` — the queue with dashboard tiles and server-side filters;
  replaces the Phase-16 placeholder screen
- `/hr/helpdesk/{id}` — the ticket: conversation with internal notes marked and
  locked, status control built from `allowed_transitions`, assignment,
  reclassification, full history

Tests: `backend/tests/integration/test_helpdesk.py` (33 tests), plus the
platform-wide guard/scope coverage suites which enumerate these routes like any
others.
