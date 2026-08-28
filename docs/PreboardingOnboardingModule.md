# Preboarding & Onboarding

This module completes the recruitment lifecycle after an offer is accepted. Background verification is intentionally outside the MVP.

## Workflow

1. HR starts preboarding for an accepted offer and links the candidate's existing user account.
2. The candidate confirms the joining date, supplies personal, emergency, address, bank and statutory information, uploads documents through the Document Vault, and acknowledges all policies.
3. HR reviews documents and approves the complete profile. Mandatory information, seven approved document types and four acknowledgements are enforced by the backend.
4. Conversion creates the employee and its address, bank and identification records without re-entry, links the existing user, copies offer/job placement data, assigns the database-generated employee code, and changes the ATS stage to `Joined`.
5. HR creates a configurable onboarding case with HR, IT, Administration and Manager tasks. Completion is recalculated from actual tasks. The case can close only after every task is complete.

Sensitive values are excluded from reports. Candidate documents continue to use the existing immutable Document Vault. Policy acknowledgements record UTC time, IP address and user agent.

## UI

- `/onboarding` — operational dashboard and reports
- `/onboarding/start` — accepted-offer intake
- `/onboarding/portal/{profileId}` — candidate portal
- `/onboarding/review/{profileId}` — HR review and conversion
- `/onboarding/tasks/{caseId}` — task checklist
- `/onboarding/welcome/{caseId}` — employee welcome screen

## API

All routes use `/api/v1/onboarding`. The module provides dashboard and CSV/XLSX export routes, profile start/read/update, policy acknowledgement, document review, HR approval, employee conversion, case creation, task updates, completion and welcome data.
