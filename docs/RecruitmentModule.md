# Recruitment & Applicant Tracking System

The ATS converts an approved job requisition into a publishable opening and tracks each applicant from Applied through Joined, Rejected, or Withdrawn.

## Workflow

1. Create a job opening from a requisition whose status is `approved`.
2. Publish the opening. Candidates cannot be added to draft or closed openings.
3. Create a candidate with a source, at least one skill, and a resume document from Document Vault.
4. Move the candidate through configured stages on the Kanban board. Every move creates immutable stage history, audit activity, and a recruiter notification.
5. Add internal notes, link additional document versions, and optionally add the candidate to multiple talent pools.
6. Close, cancel, or mark the opening filled.

Duplicate detection compares normalized email and mobile number before insertion. The API also exposes a preflight duplicate endpoint so the UI can warn before submission.

## Screens

- `/recruitment` — metrics, stage funnel and recruiter workload
- `/recruitment/openings` — opening creation and publication lifecycle
- `/recruitment/candidates` — search and advanced skill filters
- `/recruitment/candidates/new` — validated candidate intake
- `/recruitment/candidates/{id}` — overview, resume/documents, skills, notes and timeline
- `/recruitment/pipeline` — drag-and-drop stage board
- `/recruitment/talent-pools` — reusable talent communities

## Boundaries

Interview scheduling and offer-document generation are deliberately outside this module. ATS records the corresponding pipeline stages without owning those future workflows.
