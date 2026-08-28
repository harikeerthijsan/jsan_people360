"""Audit trail service.

Any layer that performs a security- or data-relevant action records it here.
Recording never raises: a failure to write the trail must not fail the business
operation it describes, but it is always logged at ERROR level.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.core.context import get_client_ip, get_request_id, get_user_agent
from app.core.logging import get_logger
from app.models.audit_log import AuditLog, AuditOutcome
from app.repositories.audit_log_repository import AuditLogRepository
from app.utils.strings import truncate

logger = get_logger("services.audit")


class AuditService:
    """Writes and queries the append-only audit trail."""

    def __init__(self, repository: AuditLogRepository) -> None:
        self._repository = repository

    async def for_entity(
        self, entity_type: str, entity_id: str | uuid.UUID, *, limit: int = 100
    ) -> Sequence[AuditLog]:
        """Return the newest audit entries for one domain record."""
        return await self._repository.search(
            entity_type=entity_type,
            entity_id=str(entity_id),
            limit=limit,
        )

    async def record(
        self,
        action: str,
        *,
        actor_id: uuid.UUID | None = None,
        actor_email: str | None = None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        entity_type: str | None = None,
        entity_id: str | uuid.UUID | None = None,
        description: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AuditLog | None:
        """Append one entry, enriched with the ambient request context."""
        entry = AuditLog(
            actor_id=actor_id,
            actor_email=actor_email,
            action=action,
            outcome=outcome.value,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            description=description,
            context=context,
            request_id=get_request_id(),
            ip_address=get_client_ip(),
            user_agent=truncate(get_user_agent(), 512),
            created_by=actor_id,
            updated_by=actor_id,
        )

        try:
            return await self._repository.add(entry)
        except SQLAlchemyError:
            # Never let auditing break the operation being audited.
            logger.error("Failed to write audit entry", extra={"audit_action": action}, exc_info=True)
            return None

    async def record_success(self, action: str, **kwargs: Any) -> AuditLog | None:
        return await self.record(action, outcome=AuditOutcome.SUCCESS, **kwargs)

    async def record_failure(self, action: str, **kwargs: Any) -> AuditLog | None:
        return await self.record(action, outcome=AuditOutcome.FAILURE, **kwargs)
