# Project & Client Allocation Management

This module is the first part of Workforce Operations and is the source of project and allocation data for future attendance, timesheet, performance and resource-planning modules. It does not implement timesheets, payroll or revenue calculations.

## Domain model

- `clients` stores customer organizations and generates `CLT-000001` identifiers.
- `projects` stores delivery engagements and generates `PRJ-000001` identifiers.
- `project_members` records team membership, role and reporting relationship.
- `employee_allocations` stores time-bounded allocation records. Allocation changes close the existing record and append a replacement.
- `allocation_history` is an append-only business timeline for assignment, change and removal events.

Every table uses UUID primary keys, audit fields and soft deletion. The service rejects duplicate overlapping project assignments and any overlapping allocation total above 100%. Utilization at 90% or above is visibly warned in the UI and generates an in-app capacity notification.

## Screens

- `/projects` — workforce allocation dashboard
- `/projects/list` and `/projects/{id}` — portfolio and project dashboard
- `/projects/new` — project creation
- `/projects/{id}/allocate` — employee allocation
- `/projects/bench` — automatically calculated bench resources
- `/clients`, `/clients/new`, `/clients/{id}` — client management and dashboard

## Reports

Client, project, allocation, bench and utilization reports are available as CSV and XLSX through `/api/v1/projects/reports/export`.

## Lifecycle

Project creation and updates are audited. Assignment, allocation changes and removal append allocation history. Project managers and allocated employees receive in-app notifications for project creation, assignment, capacity warnings, allocation changes, completion and near-term project end dates.
