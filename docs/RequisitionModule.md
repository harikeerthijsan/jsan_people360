# Job Requisition & Workforce Planning

Phase 6 introduces the manpower-request entry point for Recruitment. Requisitions receive database-generated `REQ-000001` identifiers, organizational placement, position and compensation details, hiring targets, structured job-description content and required business justification.

## Workflow

`Draft → Pending approval → Approved` is the happy path. Submission creates an immutable three-step approval chain: Hiring Manager, Second approver, then HR. The current assigned approver may approve, reject, or send back. Live requests may be cancelled; approved/open requests may be closed. Every transition appends `requisition_history` and a platform audit event. Approval requests and terminal outcomes create in-app notifications.

## Attachments

Attachments are existing Document Vault documents linked through `requisition_attachments`; file bytes and versions are never duplicated. Types are job description, budget approval, and supporting document.

## APIs and screens

Authenticated APIs under `/api/v1/requisitions` provide dashboard, list/filter/sort, create, detail, update, submit, approval actions, attachment linking, and CSV/XLSX export. `/api/v1/notifications` exposes the current user's notifications. Frontend routes are `/requisitions/dashboard`, `/requisitions`, `/requisitions/new`, `/requisitions/{id}`, and edit.

RBAC and Candidate Management remain deliberately out of scope. Recruitment can later create postings directly from approved requisitions.
