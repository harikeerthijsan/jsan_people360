# Announcements

Phase 20 adds company announcements: durable notices addressed to everybody, a
business unit, a team or a location — with optional acknowledgement tracking.

## Not a second message system

The platform already had a notification inbox, and the earlier phases
deliberately refused to invent an announcements table beside it. What changed is
the relationship: **publishing an announcement still delivers through the
inbox** — each person in the audience gets a notification pointing at the
notice. A notification is "something happened that concerns you" and is
disposable; an announcement is the company's position on something, the same
text for everybody it reaches, and it persists. The employee dashboard's
`recent_announcements` field now carries the real thing, beside
`recent_notifications`.

## Writing and sending are two permissions

`announcements:create` drafts; `announcements:publish` sends. An HR executive
can write the redundancy notice, and only somebody holding publish decides it
goes out. Publishing stamps `published_at`, fans notifications out to the
resolved audience, and records who did it. A published notice can be amended,
pinned and archived — never unpublished, because people have already read it.

`publish_at` in the future schedules instead of sending; `expires_at` takes a
notice off the board without deleting anything. A CHECK constraint refuses an
expiry at or before publication.

## Audience is matched in SQL, per reader

`audience` + `target_ids` (JSONB) name who a notice reaches. What an employee
sees (`GET /me/announcements`) is computed in the database against *their own*
business unit, team and location — published, in-window, pinned first. The
employee read model (`MyAnnouncement`) carries no author, no audience
configuration and no acknowledgement roll: who else was told and who has not
read it are the sender's business.

## Acknowledgements

A notice can require acknowledgement. `POST /me/announcements/{id}/acknowledge`
is idempotent (unique on announcement + employee — acknowledging twice is not
twice as acknowledged), and the sender's detail view shows the roll:
`acknowledged_count` against `audience_size`, with names and timestamps.

## Access model

| Seat | Reach |
| --- | --- |
| **Employee** | Own board via `/me/announcements` — read and acknowledge. Identity only |
| **Manager / Team Lead** | `announcements:view` — can read the register |
| **HR Executive** | view, create — drafts, cannot send |
| **HR Admin** | everything except delete |
| **Admin / Super Admin** | everything, including delete (archive is the ordinary way to retire one) |

## Endpoints

Employee: `GET /me/announcements`, `POST /me/announcements/{id}/acknowledge`.

Administration: `GET/POST /announcements`, `GET/PATCH /announcements/{id}`,
`POST …/publish`, `POST …/archive`, `DELETE /announcements/{id}`.

## Frontend

- `/employee/announcements` — the notice board: pinned first, acknowledgement
  prompts, priority badges (My Workspace)
- `/hr/announcements` — register with a composer, the publish/pin/archive
  controls gated on their separate permissions, and the acknowledgement roll

Tests: covered in `backend/tests/integration/test_helpdesk.py` alongside the
helpdesk (33 tests total for the phase), plus the platform-wide guard/scope
coverage suites.
