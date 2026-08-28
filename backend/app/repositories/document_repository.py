"""Persistence for the Document Management module.

Four repositories. The two masters extend :class:`MasterRepository` and gain
paging, search and uniqueness lookups unchanged; the document and version
repositories are their own, because a document's access patterns -- filter by a
polymorphic owner, aggregate by expiry -- have nothing in common with master
data.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from datetime import date, datetime, timedelta

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.models.document import Document, DocumentVersion
from app.models.document_category import DocumentCategory, DocumentType
from app.models.enums import EXPIRY_WARNING_DAYS, DocumentOwnerType, DocumentStatus, ExpiryState
from app.repositories.base import BaseRepository
from app.repositories.master_repository import LIKE_ESCAPE, MasterRepository, escape_like
from app.schemas.document import DocumentListParams

#: Statuses that mean nobody has decided about the document yet.
PENDING_STATUSES: tuple[str, ...] = (DocumentStatus.UPLOADED.value, DocumentStatus.UNDER_REVIEW.value)


class DocumentCategoryRepository(MasterRepository[DocumentCategory]):
    model = DocumentCategory
    has_code = True
    searchable_fields = ("name", "code", "description")
    sortable_fields = frozenset({"name", "code", "status", "display_order", "created_at", "updated_at"})


class DocumentTypeRepository(MasterRepository[DocumentType]):
    model = DocumentType
    has_code = True
    searchable_fields = ("name", "code", "description")
    sortable_fields = frozenset({"name", "code", "status", "created_at", "updated_at"})


class DocumentRepository(BaseRepository[Document]):
    """Queries scoped to documents."""

    model = Document

    searchable_fields: tuple[str, ...] = ("document_code", "name", "description")

    sortable_fields: frozenset[str] = frozenset(
        {"document_code", "name", "status", "expiry_date", "created_at", "updated_at"}
    )

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    async def get_with_relationships(self, document_id: uuid.UUID) -> Document | None:
        """Re-read a document with its eager relationships repopulated.

        ``populate_existing`` matters after adding a version: the identity-mapped
        instance would otherwise still hold the previous current version.
        """
        stmt = select(Document).where(Document.id == document_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalars().unique().first()

    async def find_by_checksum(self, document_id: uuid.UUID, checksum: str) -> DocumentVersion | None:
        """Whether this exact content already exists on this document.

        Uploading a byte-identical file is a mistake -- a double-click, or the
        wrong file picked twice -- not a new version, and a version that changes
        nothing makes the history harder to read.
        """
        stmt = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.checksum == checksum,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def next_version_number(self, document_id: uuid.UUID) -> int:
        """One past the highest version this document has ever had.

        Deliberately counts *every* version rather than the live ones, so a
        number is never reissued.
        """
        stmt = select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
            DocumentVersion.document_id == document_id
        )
        return int((await self.session.execute(stmt)).scalar_one()) + 1

    async def get_version(self, document_id: uuid.UUID, version_id: uuid.UUID) -> DocumentVersion | None:
        """Fetch one version, scoped to its document.

        Scoping matters: without it, a caller who knows any version id could
        read a file belonging to a document they were not looking at.
        """
        stmt = select(DocumentVersion).where(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document_id,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_versions(self, document_id: uuid.UUID) -> Sequence[DocumentVersion]:
        """Every version of a document, newest first."""
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
        )
        return (await self.session.execute(stmt)).scalars().unique().all()

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------
    def _scoped_select(self, *, archived: bool) -> Select[tuple[Document]]:
        stmt = select(Document)
        return stmt.where(Document.deleted_at.is_not(None) if archived else Document.deleted_at.is_(None))

    def _search_criteria(self, term: str) -> ColumnElement[bool]:
        pattern = f"%{escape_like(term)}%"
        return or_(
            *[getattr(Document, field).ilike(pattern, escape=LIKE_ESCAPE) for field in self.searchable_fields]
        )

    @staticmethod
    def _expiry_criteria(state: ExpiryState, today: date) -> ColumnElement[bool]:
        """Translate a derived expiry state into something SQL can filter on.

        The state is computed in Python on read, but filtering a page by it has
        to happen in the database or paging would be wrong.
        """
        horizon = today + timedelta(days=EXPIRY_WARNING_DAYS)

        if state is ExpiryState.NONE:
            return Document.expiry_date.is_(None)
        if state is ExpiryState.EXPIRED:
            return Document.expiry_date < today
        if state is ExpiryState.EXPIRING_SOON:
            return Document.expiry_date.between(today, horizon)
        return Document.expiry_date > horizon

    def _filters(self, params: DocumentListParams, *, today: date) -> list[ColumnElement[bool]]:
        criteria: list[ColumnElement[bool]] = []

        if params.search:
            criteria.append(self._search_criteria(params.search))
        if params.status is not None:
            criteria.append(Document.status == params.status.value)
        if params.category_id is not None:
            criteria.append(Document.category_id == params.category_id)
        if params.document_type_id is not None:
            criteria.append(Document.document_type_id == params.document_type_id)
        if params.owner_type is not None:
            criteria.append(Document.owner_type == params.owner_type.value)
        if params.owner_id is not None:
            criteria.append(Document.owner_id == params.owner_id)
        if params.expiry_state is not None:
            criteria.append(self._expiry_criteria(params.expiry_state, today))
        if params.uploaded_from is not None:
            criteria.append(func.date(Document.created_at) >= params.uploaded_from)
        if params.uploaded_to is not None:
            criteria.append(func.date(Document.created_at) <= params.uploaded_to)

        return criteria

    @staticmethod
    def _visibility(
        visible_employee_ids: Collection[uuid.UUID] | None,
        visible_user_ids: Collection[uuid.UUID] | None,
    ) -> list[ColumnElement[bool]]:
        """Narrow the vault to the people a caller may see.

        Only the two person-shaped owner types are narrowed. Organization
        policies and candidate paperwork stay visible to anybody holding
        ``documents:view``: they have no reporting line to be outside of, and
        filtering them out would hide the employee handbook from most of the
        company.

        ``None`` means unrestricted. An empty collection means the caller may
        see nobody, which still leaves the unscoped owner types readable -- so
        this is deliberately not a blanket ``false()``.
        """
        if visible_employee_ids is None and visible_user_ids is None:
            return []

        mine: list[ColumnElement[bool]] = [
            Document.owner_type.not_in([DocumentOwnerType.EMPLOYEE.value, DocumentOwnerType.USER.value])
        ]
        if visible_employee_ids:
            mine.append(
                and_(
                    Document.owner_type == DocumentOwnerType.EMPLOYEE.value,
                    Document.owner_id.in_(visible_employee_ids),
                )
            )
        if visible_user_ids:
            mine.append(
                and_(
                    Document.owner_type == DocumentOwnerType.USER.value,
                    Document.owner_id.in_(visible_user_ids),
                )
            )
        return [or_(*mine)]

    async def list_page(
        self,
        params: DocumentListParams,
        *,
        today: date,
        visible_employee_ids: Collection[uuid.UUID] | None = None,
        visible_user_ids: Collection[uuid.UUID] | None = None,
    ) -> tuple[Sequence[Document], int]:
        """Return one page of documents and the total number of matches."""
        base = (
            self._scoped_select(archived=params.archived)
            .where(*self._filters(params, today=today))
            .where(*self._visibility(visible_employee_ids, visible_user_ids))
        )

        count_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        column = getattr(Document, params.sort_by)
        ordered = base.order_by(column.desc() if params.descending else column.asc()).order_by(Document.id)

        page_stmt = ordered.offset(params.offset).limit(params.page_size)
        rows = (await self.session.execute(page_stmt)).scalars().unique().all()
        return rows, total

    # ------------------------------------------------------------------
    # Dashboard aggregates
    # ------------------------------------------------------------------
    async def count_live(self, *criteria: ColumnElement[bool]) -> int:
        stmt = select(func.count()).select_from(Document).where(Document.deleted_at.is_(None), *criteria)
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_archived(self) -> int:
        stmt = select(func.count()).select_from(Document).where(Document.deleted_at.is_not(None))
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_pending_review(self) -> int:
        return await self.count_live(Document.status.in_(PENDING_STATUSES))

    async def oldest_pending_at(self) -> datetime | None:
        """When the longest-waiting document arrived, for the HR queue's age."""
        stmt = select(func.min(Document.created_at)).where(
            Document.deleted_at.is_(None), Document.status.in_(PENDING_STATUSES)
        )
        oldest: datetime | None = await self.session.scalar(stmt)
        return oldest

    async def count_by_expiry(self, state: ExpiryState, *, today: date) -> int:
        return await self.count_live(self._expiry_criteria(state, today))

    async def count_by_status(self) -> list[tuple[str, int]]:
        stmt = (
            select(Document.status, func.count())
            .where(Document.deleted_at.is_(None))
            .group_by(Document.status)
        )
        return [(row[0], int(row[1])) for row in (await self.session.execute(stmt)).all()]

    async def count_by_category(self, *, limit: int = 10) -> list[tuple[str, int]]:
        stmt = (
            select(DocumentCategory.name, func.count(Document.id))
            .join(DocumentCategory, DocumentCategory.id == Document.category_id)
            .where(Document.deleted_at.is_(None))
            .group_by(DocumentCategory.name)
            .order_by(func.count(Document.id).desc(), DocumentCategory.name)
            .limit(limit)
        )
        return [(row[0], int(row[1])) for row in (await self.session.execute(stmt)).all()]

    async def total_storage_bytes(self) -> int:
        """Across every version, including superseded ones.

        Superseded versions are the point: they are what the vault is still
        holding, and an operator sizing a disk needs the real figure.
        """
        stmt = select(func.coalesce(func.sum(DocumentVersion.size_bytes), 0))
        return int((await self.session.execute(stmt)).scalar_one())

    async def status_counts_for_owners(
        self, owner_type: DocumentOwnerType, owner_ids: Collection[uuid.UUID]
    ) -> list[tuple[uuid.UUID, str, int]]:
        """``(owner, status, count)`` for a set of owners, in one query.

        For the completion figures a manager sees -- eight required, seven
        approved, one outstanding. Aggregated in the database rather than by
        paging the vault and counting in Python: a page has a ceiling, and a
        count assembled from a truncated page is a number that quietly stops
        being true once a team files enough paperwork.

        No file, no name and no classification comes back -- only how many are
        in each state. That is what makes this answerable for a manager who is
        not entitled to read the documents themselves.
        """
        if not owner_ids:
            return []
        stmt = (
            select(Document.owner_id, Document.status, func.count())
            .where(
                Document.deleted_at.is_(None),
                Document.owner_type == owner_type.value,
                Document.owner_id.in_(owner_ids),
            )
            .group_by(Document.owner_id, Document.status)
        )
        return [(row[0], row[1], int(row[2])) for row in (await self.session.execute(stmt)).all()]

    async def count_for_type(self, document_type_id: uuid.UUID) -> int:
        """Live documents of a type. Blocks archiving the type."""
        return await self.count_live(Document.document_type_id == document_type_id)

    async def count_for_category(self, category_id: uuid.UUID) -> int:
        """Live documents in a category. Blocks archiving the category."""
        return await self.count_live(Document.category_id == category_id)


class DocumentVersionRepository(BaseRepository[DocumentVersion]):
    """Appends versions. There is deliberately no update or delete.

    A version records what was held at a point in time; correcting it means
    uploading a new one.
    """

    model = DocumentVersion
