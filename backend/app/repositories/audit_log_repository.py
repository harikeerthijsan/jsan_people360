"""Persistence operations for :class:`app.models.audit_log.AuditLog`."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.sql.elements import ColumnElement

from app.models.audit_log import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    """Read/append access to the audit trail."""

    model = AuditLog

    def _filters(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str | None,
        entity_type: str | None,
        entity_id: str | None,
        since: datetime | None,
        until: datetime | None,
    ) -> list[ColumnElement[bool]]:
        criteria: list[ColumnElement[bool]] = []
        if actor_id is not None:
            criteria.append(AuditLog.actor_id == actor_id)
        if action:
            criteria.append(AuditLog.action == action)
        if entity_type:
            criteria.append(AuditLog.entity_type == entity_type)
        if entity_id:
            criteria.append(AuditLog.entity_id == entity_id)
        if since is not None:
            criteria.append(AuditLog.created_at >= since)
        if until is not None:
            criteria.append(AuditLog.created_at <= until)
        return criteria

    async def search(
        self,
        *,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[AuditLog]:
        criteria = self._filters(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            since=since,
            until=until,
        )
        return await self.list(*criteria, offset=offset, limit=limit, order_by="created_at", descending=True)

    async def count_matching(
        self,
        *,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        criteria = self._filters(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            since=since,
            until=until,
        )
        return await self.count(*criteria)
