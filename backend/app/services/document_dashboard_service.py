"""Headline figures for the document dashboard.

Separate from :class:`~app.services.document_service.DocumentService` for the
same reason the employee dashboard is separate from its service: this only
counts. It holds no guards and enforces no rules, and it will grow as later
modules add their own tiles.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.models.enums import DocumentStatus, ExpiryState
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import CountByLabel, DocumentDashboardStats

#: How many categories the breakdown shows before the tail is dropped.
CATEGORY_LIMIT = 8


def _humanise(value: str) -> str:
    """``under_review`` -> ``Under review``."""
    return value.replace("_", " ").capitalize()


class DocumentDashboardService:
    """Aggregate counts across the vault."""

    def __init__(self, repository: DocumentRepository) -> None:
        self._documents = repository

    async def stats(self, *, today: date | None = None) -> DocumentDashboardStats:
        """Every figure the dashboard shows.

        ``today`` is injectable so the expiry boundary can be tested without
        waiting for a date to pass.
        """
        reference = today or datetime.now(UTC).date()

        by_status = await self._documents.count_by_status()
        by_category = await self._documents.count_by_category(limit=CATEGORY_LIMIT)

        return DocumentDashboardStats(
            total_documents=await self._documents.count_live(),
            pending_review=await self._documents.count_pending_review(),
            expiring_soon=await self._documents.count_by_expiry(ExpiryState.EXPIRING_SOON, today=reference),
            expired=await self._documents.count_by_expiry(ExpiryState.EXPIRED, today=reference),
            approved=await self._count_status(DocumentStatus.APPROVED, by_status),
            rejected=await self._count_status(DocumentStatus.REJECTED, by_status),
            archived=await self._documents.count_archived(),
            total_storage_bytes=await self._documents.total_storage_bytes(),
            by_category=[CountByLabel(label=name, count=count) for name, count in by_category],
            by_status=[CountByLabel(label=_humanise(name), count=count) for name, count in by_status],
        )

    @staticmethod
    async def _count_status(status: DocumentStatus, tallies: list[tuple[str, int]]) -> int:
        """Read a status out of the grouped tally rather than re-querying."""
        return next((count for name, count in tallies if name == status.value), 0)
