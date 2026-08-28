"""Read models for the audit trail.

Read-only on purpose: the trail is append-only and the appends happen where
the audited actions happen, so there is no create or update schema for a
client to hold.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    action: str
    outcome: str
    actor_id: uuid.UUID | None
    actor_email: str | None
    entity_type: str | None
    entity_id: str | None
    description: str | None
    context: dict[str, Any] | None
    request_id: str | None
    ip_address: str | None
