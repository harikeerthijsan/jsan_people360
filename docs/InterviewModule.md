# Interview Management & Scheduling

Interview Management schedules ATS candidates with one or more employee interviewers, prevents overlapping bookings, gathers structured scorecards, and records decisions back into the ATS pipeline.

## Workflow

1. Schedule a future, timezone-aware interview for an ATS candidate.
2. Assign exactly one lead interviewer and optional panel members or observers.
3. Candidate and interviewer schedules are checked for overlap before scheduling, rescheduling, or panel replacement.
4. Assigned non-observer interviewers submit all six score categories from 1–10 and a recommendation.
5. The service calculates the overall score and panel recommendation.
6. Recruiters record next-round, reject, hold, shortlist, or final-selection decisions. Decisions update ATS stage history without implementing offer logic.

Every schedule, reschedule, cancellation, panel change, feedback submission, and decision is captured in interview history and the platform audit log. Interview materials link to versioned Document Vault records.

## Screens

- `/interviews/dashboard` — scheduling and outcome metrics
- `/interviews` — searchable interview directory
- `/interviews/calendar` — day, week and month views with drag rescheduling
- `/interviews/new` — validated scheduling and panel form
- `/interviews/{id}` — details, panel scorecard, feedback, decisions and timeline
- `/interviews/{id}/edit` — editable interview metadata

## API

The authenticated `/api/v1/interviews` API provides list/detail/schedule/update, reschedule, cancel, panel replacement, feedback, decisions, attachments, dashboard, and CSV/XLSX export operations.
