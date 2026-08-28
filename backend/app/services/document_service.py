"""Document vault business logic.

The rule this module exists to enforce is that **an uploaded file is never
overwritten**. Uploading again appends a version; nothing updates or deletes
one. That makes the vault's history complete by construction rather than by
anyone remembering to keep it.

Everything else is the boundary around untrusted input: bytes are validated
against their own signature before they are stored, filenames never reach the
filesystem, and no response ever carries a storage key.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.audit_log import AuditAction
from app.models.document import Document, DocumentVersion
from app.models.enums import VERIFIABLE_OWNER_TYPES, DocumentOwnerType, DocumentStatus
from app.models.requisition import Notification
from app.repositories.document_repository import (
    DocumentRepository,
    DocumentVersionRepository,
)
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.recruitment_repository import CandidateRepository
from app.repositories.requisition_repository import NotificationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.document import (
    DocumentListParams,
    DocumentOwnerRef,
    DocumentReviewRequest,
    DocumentUpdate,
    DocumentUploadMetadata,
    DocumentVersionUploadMetadata,
)
from app.services.audit_service import AuditService
from app.services.scope_service import EmployeeScope, visible_employee_ids, visible_user_ids
from app.storage import StorageBackend, StoredObjectNotFound
from app.utils.datetime import utc_now
from app.utils.files import FileValidationError, build_storage_key, inspect_upload

logger = get_logger("services.document")

#: Statuses a document can be moved out of by an ordinary edit. Once archived it
#: is restored first, and once expired the expiry date is what changes.
_EDITABLE_STATUSES: frozenset[str] = frozenset(
    {
        DocumentStatus.UPLOADED.value,
        DocumentStatus.UNDER_REVIEW.value,
        DocumentStatus.APPROVED.value,
        DocumentStatus.REJECTED.value,
        DocumentStatus.EXPIRED.value,
    }
)


@dataclass(frozen=True)
class UploadedFile:
    """One file as it arrived, before anything has been validated."""

    content: bytes
    filename: str
    declared_content_type: str | None = None


@dataclass(frozen=True)
class FilePayload:
    """A file on its way back out, ready to be streamed."""

    content: bytes
    filename: str
    content_type: str


class DocumentService:
    """Store and manage documents for any owner."""

    def __init__(
        self,
        repository: DocumentRepository,
        version_repository: DocumentVersionRepository,
        audit_service: AuditService,
        storage: StorageBackend,
        *,
        employee_repository: EmployeeRepository | None = None,
        user_repository: UserRepository | None = None,
        organization_repository: OrganizationRepository | None = None,
        candidate_repository: CandidateRepository | None = None,
        notification_repository: NotificationRepository | None = None,
    ) -> None:
        self._documents = repository
        self._versions = version_repository
        self._audit = audit_service
        self._storage = storage
        # Used only to confirm an owner exists and to resolve a display name.
        # Repositories rather than services: this module has no business asking
        # another module to apply *its* rules.
        self._employees = employee_repository
        self._users = user_repository
        self._organizations = organization_repository
        self._candidates = candidate_repository
        # The platform's one in-app inbox, shared with requisitions, recruitment
        # and workforce. Optional because unit tests build this service from
        # plain fakes, and a missing inbox must never fail a review.
        self._notifications = notification_repository

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def list(
        self, params: DocumentListParams, *, scope: EmployeeScope | None = None
    ) -> tuple[Sequence[Document], int]:
        self._assert_sortable(params.sort_by)
        self._assert_date_range(params.uploaded_from, params.uploaded_to)
        return await self._documents.list_page(
            params,
            today=self._today(),
            visible_employee_ids=visible_employee_ids(scope),
            visible_user_ids=visible_user_ids(scope),
        )

    async def get_by_id(
        self,
        document_id: uuid.UUID,
        *,
        include_archived: bool = True,
        scope: EmployeeScope | None = None,
    ) -> Document:
        """Fetch one document, or raise :class:`NotFoundError`.

        The single choke point for team scoping in this module: ``versions``,
        ``read_file``, ``update``, ``review``, ``archive`` and ``restore`` all
        load their document through here, so one check covers the file, its
        history and its metadata rather than six that have to stay in step.
        """
        document = await self._documents.get(document_id, include_deleted=include_archived)
        if document is None:
            raise NotFoundError("Document")
        self._assert_owner_in_scope(scope, document.owner_type, document.owner_id)
        return document

    async def status_counts_for_employees(
        self,
        employee_ids: Collection[uuid.UUID],
        *,
        scope: EmployeeScope | None = None,
    ) -> dict[uuid.UUID, dict[str, int]]:
        """How many documents each of these employees has, by review status.

        Counts and nothing else. A manager is entitled to know whether their
        team's paperwork is complete; that is a different question from being
        entitled to read a passport scan, and this answers only the first --
        there is no name, no classification and no file in the return value, so
        the endpoint on top of it cannot leak one by forgetting to strip it.

        The scope is still applied, because "how many documents does this person
        have" is itself a fact about them. Asking about somebody outside it is a
        403, not a zero.
        """
        if scope is not None:
            for employee_id in employee_ids:
                scope.assert_allows(employee_id)

        counts: dict[uuid.UUID, dict[str, int]] = {employee_id: {} for employee_id in employee_ids}
        for owner_id, status, count in await self._documents.status_counts_for_owners(
            DocumentOwnerType.EMPLOYEE, employee_ids
        ):
            counts.setdefault(owner_id, {})[status] = count
        return counts

    async def versions(
        self, document_id: uuid.UUID, *, scope: EmployeeScope | None = None
    ) -> Sequence[DocumentVersion]:
        await self.get_by_id(document_id, scope=scope)
        return await self._documents.list_versions(document_id)

    async def resolve_owner(self, document: Document) -> DocumentOwnerRef:
        """Turn the polymorphic owner reference into something readable.

        A bare type and UUID is unusable in a list. When the owner cannot be
        resolved -- an unknown type, or a record since removed -- the name comes
        back null rather than the method failing: a document must remain
        readable even if what it belonged to has gone.
        """
        owner_type = DocumentOwnerType(document.owner_type)
        display_name: str | None = None
        reference_code: str | None = None

        if owner_type is DocumentOwnerType.EMPLOYEE and self._employees is not None:
            employee = await self._employees.get(document.owner_id, include_deleted=True)
            if employee is not None:
                display_name, reference_code = employee.full_name, employee.employee_code

        elif owner_type is DocumentOwnerType.USER and self._users is not None:
            user = await self._users.get(document.owner_id, include_deleted=True)
            if user is not None:
                display_name, reference_code = user.full_name, user.user_code

        elif owner_type is DocumentOwnerType.CANDIDATE and self._candidates is not None:
            candidate = await self._candidates.get(document.owner_id, include_deleted=True)
            if candidate is not None:
                # Candidates carry no ``full_name`` column, so it is composed
                # here rather than adding one to another module's model.
                display_name = f"{candidate.first_name} {candidate.last_name}".strip()
                reference_code = candidate.candidate_code

        elif owner_type is DocumentOwnerType.ORGANIZATION and self._organizations is not None:
            organization = await self._organizations.get(document.owner_id, include_deleted=True)
            if organization is not None:
                display_name = organization.name

        return DocumentOwnerRef(
            owner_type=owner_type,
            owner_id=document.owner_id,
            display_name=display_name,
            reference_code=reference_code,
        )

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------
    async def create(
        self,
        payload: DocumentUploadMetadata,
        upload: UploadedFile,
        *,
        actor_id: uuid.UUID | None = None,
        scope: EmployeeScope | None = None,
    ) -> Document:
        """Record a new document and store its first version."""
        # Checked before the file is inspected or stored: filing a document
        # against a stranger is refused, not stored and then hidden.
        self._assert_owner_in_scope(scope, payload.owner_type.value, payload.owner_id)
        await self._assert_owner_exists(payload.owner_type, payload.owner_id)
        document_type = await self._load_document_type(payload.document_type_id, payload.category_id)
        self._assert_expiry_supplied(document_type, payload.expiry_date)

        inspected = self._inspect(upload, document_type=document_type)

        document = Document(
            name=payload.name,
            description=payload.description,
            category_id=payload.category_id,
            document_type_id=payload.document_type_id,
            owner_type=payload.owner_type.value,
            owner_id=payload.owner_id,
            expiry_date=payload.expiry_date,
            status=DocumentStatus.UPLOADED,
        )
        await self._documents.add(document, actor_id=actor_id)

        await self._append_version(
            document,
            inspected=inspected,
            content=upload.content,
            notes=None,
            actor_id=actor_id,
        )

        created = await self._reload(document.id)
        await self._audit.record_success(
            AuditAction.DOCUMENT_UPLOADED,
            actor_id=actor_id,
            entity_type="document",
            entity_id=created.id,
            description=f"Uploaded {created.document_code} ({created.name})",
            # The filename and size are recorded; the content never is.
            context={
                "document_code": created.document_code,
                "owner_type": created.owner_type,
                "filename": inspected.filename,
                "size_bytes": inspected.size_bytes,
                "version": 1,
            },
        )
        logger.info(
            "Document uploaded",
            extra={"document_id": str(created.id), "document_code": created.document_code},
        )
        return created

    async def add_version(
        self,
        document_id: uuid.UUID,
        payload: DocumentVersionUploadMetadata,
        upload: UploadedFile,
        *,
        actor_id: uuid.UUID | None = None,
        scope: EmployeeScope | None = None,
    ) -> Document:
        """Store a new version of an existing document.

        Never replaces the previous file. The old version stays on disk and in
        the database, and remains downloadable.
        """
        document = await self.get_by_id(document_id, scope=scope)
        self._assert_not_archived(document)

        # The classification is not being chosen here, only read for its
        # extension narrowing, so an inactive type must not block a new version.
        document_type = await self._get_document_type(document.document_type_id)
        inspected = self._inspect(upload, document_type=document_type)

        await self._append_version(
            document,
            inspected=inspected,
            content=upload.content,
            notes=payload.notes,
            actor_id=actor_id,
        )

        updated = await self._reload(document.id)
        await self._audit.record_success(
            AuditAction.DOCUMENT_VERSION_UPLOADED,
            actor_id=actor_id,
            entity_type="document",
            entity_id=updated.id,
            description=(
                f"Uploaded version {updated.version_count} of {updated.document_code} ({updated.name})"
            ),
            context={
                "version": updated.version_count,
                "filename": inspected.filename,
                "size_bytes": inspected.size_bytes,
            },
        )
        return updated

    async def _append_version(
        self,
        document: Document,
        *,
        inspected: Any,
        content: bytes,
        notes: str | None,
        actor_id: uuid.UUID | None,
    ) -> DocumentVersion:
        """Write the file, then record it. Order matters.

        Storage first: if the write fails the transaction rolls back and no row
        claims a file that is not there. The reverse order can leave a row
        pointing at nothing, which is the harder failure to detect later.
        """
        checksum_match = await self._documents.find_by_checksum(document.id, self._checksum(content))
        if checksum_match is not None:
            raise ConflictError(
                f"That exact file is already stored as version {checksum_match.version_number}. "
                "Upload a different file, or leave the current version in place.",
                error_code="duplicate_version",
            )

        version_number = await self._documents.next_version_number(document.id)
        key = build_storage_key(
            owner_type=document.owner_type,
            document_id=document.id,
            extension=inspected.extension,
            on=self._today(),
        )

        stored = await self._storage.save(content=content, key=key)

        version = DocumentVersion(
            document_id=document.id,
            version_number=version_number,
            original_filename=inspected.filename,
            content_type=inspected.content_type,
            size_bytes=stored.size_bytes,
            checksum=stored.checksum,
            storage_key=stored.key,
            notes=notes,
            created_by=actor_id,
            updated_by=actor_id,
        )
        await self._versions.add(version, actor_id=actor_id)

        # The pointer is what stops a list page needing a subquery per row.
        await self._documents.update(
            document,
            {"current_version_id": version.id, "version_count": version_number},
            actor_id=actor_id,
        )
        return version

    # ------------------------------------------------------------------
    # Download and preview
    # ------------------------------------------------------------------
    async def read_file(
        self,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        for_preview: bool = False,
        scope: EmployeeScope | None = None,
    ) -> FilePayload:
        """Fetch a version's content for download or preview.

        Both are audited, and separately: previewing is browsing, downloading
        takes a copy out of the vault, and an access review cares about the
        difference.
        """
        document = await self.get_by_id(document_id, scope=scope)

        if version_id is None:
            version = document.current_version
            if version is None:
                raise NotFoundError("Document version")
        else:
            found = await self._documents.get_version(document.id, version_id)
            if found is None:
                # Scoped to the document, so a valid id from *another* document
                # is a 404 here rather than a way to read someone else's file.
                raise NotFoundError("Document version")
            version = found

        try:
            content = await self._storage.read(version.storage_key)
        except StoredObjectNotFound as error:
            # The row exists but the file does not: an operational fault, and
            # not something the caller can act on.
            logger.error(
                "Stored file missing for a document version",
                extra={"document_id": str(document.id), "version": version.version_number},
            )
            raise NotFoundError(
                message="The stored file for this document could not be found. "
                "Contact your platform team, quoting the document ID."
            ) from error

        await self._audit.record_success(
            AuditAction.DOCUMENT_PREVIEWED if for_preview else AuditAction.DOCUMENT_DOWNLOADED,
            actor_id=actor_id,
            entity_type="document",
            entity_id=document.id,
            description=(
                f"{'Previewed' if for_preview else 'Downloaded'} version "
                f"{version.version_number} of {document.document_code}"
            ),
            context={"version": version.version_number, "filename": version.original_filename},
        )

        return FilePayload(
            content=content,
            filename=version.original_filename,
            content_type=version.content_type,
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    async def update(
        self,
        document_id: uuid.UUID,
        payload: DocumentUpdate,
        *,
        actor_id: uuid.UUID | None = None,
        scope: EmployeeScope | None = None,
    ) -> Document:
        """Change a document's metadata. The file is changed by uploading a version."""
        document = await self.get_by_id(document_id, scope=scope)
        self._assert_not_archived(document)

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return document

        type_id = changes.get("document_type_id", document.document_type_id)
        category_id = changes.get("category_id", document.category_id)

        # An edit form resubmits the whole classification, so "unchanged" has to
        # be decided by comparison rather than by what was sent. Only a genuine
        # re-filing is held to the stricter rule.
        reclassifying = type_id != document.document_type_id or category_id != document.category_id
        document_type = (
            await self._load_document_type(type_id, category_id)
            if reclassifying
            else await self._get_document_type(type_id)
        )

        expiry = changes.get("expiry_date", document.expiry_date)
        self._assert_expiry_supplied(document_type, expiry)

        await self._documents.update(document, changes, actor_id=actor_id)
        updated = await self._reload(document.id)

        await self._audit.record_success(
            AuditAction.DOCUMENT_UPDATED,
            actor_id=actor_id,
            entity_type="document",
            entity_id=updated.id,
            description=f"Updated {updated.document_code} ({updated.name})",
            context={"fields": sorted(changes)},
        )
        return updated

    async def review(
        self,
        document_id: uuid.UUID,
        payload: DocumentReviewRequest,
        *,
        actor_id: uuid.UUID | None = None,
        scope: EmployeeScope | None = None,
    ) -> Document:
        """Record a review decision."""
        document = await self.get_by_id(document_id, scope=scope)
        self._assert_not_archived(document)

        if document.status == payload.status.value:
            raise ConflictError(
                f"This document is already {payload.status.value.replace('_', ' ')}.",
                error_code="already_in_status",
            )

        await self._documents.update(
            document,
            {
                "status": payload.status.value,
                "review_notes": payload.review_notes,
                "reviewed_at": utc_now(),
                "reviewed_by": actor_id,
            },
            actor_id=actor_id,
        )
        updated = await self._reload(document.id)

        await self._audit.record_success(
            AuditAction.DOCUMENT_REVIEWED,
            actor_id=actor_id,
            entity_type="document",
            entity_id=updated.id,
            description=f"Marked {updated.document_code} as {payload.status.value.replace('_', ' ')}",
            context={"status": payload.status.value},
        )
        await self._notify_owner(updated, payload.status)
        return updated

    async def _notify_owner(self, document: Document, status: DocumentStatus) -> None:
        """Tell the owner what was decided about their document.

        Only a decision is worth an inbox entry: ``under_review`` is a step in
        somebody else's process and notifying on it would train people to ignore
        the ones that matter. Best-effort throughout -- an inbox failure must not
        roll back a review that has already been recorded and audited.
        """
        if self._notifications is None or status not in {
            DocumentStatus.APPROVED,
            DocumentStatus.REJECTED,
        }:
            return

        user_id = await self._owner_user_id(document)
        if user_id is None:
            return

        rejected = status is DocumentStatus.REJECTED
        message = (
            f"{document.name} was not accepted. {document.review_notes}"
            if rejected and document.review_notes
            else f"{document.name} was {status.value}."
        )
        await self._notifications.add(
            Notification(
                user_id=user_id,
                title=f"Document {status.value}",
                message=message,
                link=f"/employee/documents/{document.id}",
                notification_type=f"document_{status.value}",
            )
        )

    async def _owner_user_id(self, document: Document) -> uuid.UUID | None:
        """The login account behind a document's owner, when there is one.

        A candidate has no account and an organization is not a person; both
        return ``None`` rather than being special-cased at the call site.
        """
        owner_type = DocumentOwnerType(document.owner_type)
        if owner_type is DocumentOwnerType.USER:
            return document.owner_id
        if owner_type is DocumentOwnerType.EMPLOYEE and self._employees is not None:
            employee = await self._employees.get(document.owner_id, include_deleted=True)
            return employee.user_id if employee else None
        return None

    # ------------------------------------------------------------------
    # Archive and restore
    # ------------------------------------------------------------------
    async def archive(
        self,
        document_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        scope: EmployeeScope | None = None,
    ) -> Document:
        """Hide a document. The file stays on disk and every version is kept."""
        document = await self.get_by_id(document_id, scope=scope)

        if document.deleted_at is not None:
            raise ConflictError("This document is already archived.", error_code="already_archived")

        await self._documents.soft_delete(document, actor_id=actor_id)
        await self._audit.record_success(
            AuditAction.DOCUMENT_ARCHIVED,
            actor_id=actor_id,
            entity_type="document",
            entity_id=document.id,
            description=f"Archived {document.document_code} ({document.name})",
        )
        return await self._reload(document.id)

    async def restore(
        self,
        document_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        scope: EmployeeScope | None = None,
    ) -> Document:
        document = await self.get_by_id(document_id, scope=scope)

        if document.deleted_at is None:
            raise ConflictError("This document is not archived.", error_code="not_archived")

        await self._documents.restore(document, actor_id=actor_id)
        await self._audit.record_success(
            AuditAction.DOCUMENT_RESTORED,
            actor_id=actor_id,
            entity_type="document",
            entity_id=document.id,
            description=f"Restored {document.document_code} ({document.name})",
        )
        return await self._reload(document.id)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _inspect(self, upload: UploadedFile, *, document_type: Any) -> Any:
        """Validate the bytes, then apply the document type's own narrowing.

        The platform allowlist is checked first and always. A type may narrow it
        -- a signed contract as PDF only -- but nothing here can widen it.
        """
        try:
            inspected = inspect_upload(
                content=upload.content,
                filename=upload.filename,
                max_size_bytes=settings.max_upload_size_bytes,
                declared_content_type=upload.declared_content_type,
            )
        except FileValidationError as error:
            # A 422 rather than a 400: the file is the field that failed.
            raise ValidationError(str(error), error_code="invalid_file") from error

        narrowing = document_type.extension_allowlist
        if narrowing is not None and inspected.extension not in narrowing:
            allowed = ", ".join(sorted(narrowing))
            raise ValidationError(
                f"{document_type.name} accepts only {allowed} files.",
                error_code="invalid_file",
            )

        return inspected

    @staticmethod
    def _assert_owner_in_scope(scope: EmployeeScope | None, owner_type: str, owner_id: uuid.UUID) -> None:
        """Refuse a document belonging to somebody outside the caller's team.

        Only the two person-shaped owner types are scoped. A candidate belongs
        to the recruitment pipeline and a policy belongs to the company; neither
        has a reporting line, and narrowing them here would hide the handbook
        from everybody who is not their own manager.

        Employee-owned and user-owned are both checked because the vault files
        against either, and a scope that covered one of them would leave the
        same person's documents readable through the other.
        """
        if scope is None or scope.unrestricted:
            return

        if owner_type == DocumentOwnerType.EMPLOYEE.value:
            scope.assert_allows(owner_id, field="owner_id")
        elif owner_type == DocumentOwnerType.USER.value:
            scope.assert_allows_user(owner_id)

    async def _assert_owner_exists(self, owner_type: DocumentOwnerType, owner_id: uuid.UUID) -> None:
        """Confirm the owner is real.

        Every owner type now has a table behind it. A repository is still
        allowed to be absent -- the service is constructed with plain fakes in
        unit tests -- and an absent one simply skips the check rather than
        failing the upload.
        """
        if owner_type not in VERIFIABLE_OWNER_TYPES:
            return

        repositories = {
            DocumentOwnerType.EMPLOYEE: self._employees,
            DocumentOwnerType.USER: self._users,
            DocumentOwnerType.ORGANIZATION: self._organizations,
            DocumentOwnerType.CANDIDATE: self._candidates,
        }
        repository = repositories.get(owner_type)
        if repository is None:
            return

        if await repository.get(owner_id, include_deleted=True) is None:
            raise ConflictError(
                f"No {owner_type.value} exists with that identifier.",
                error_code="invalid_owner",
            )

    async def _get_document_type(self, type_id: uuid.UUID) -> Any:
        """Fetch a type a document *already* refers to.

        Only archival is fatal here. Deactivating a type is how an administrator
        stops it being chosen next time; it is not a statement that the records
        already filed under it have become invalid. Treating the two as the same
        thing freezes every existing document of that type -- it could not be
        renamed, re-filed, or given a new version -- which is the opposite of
        what deactivating is for.

        The same reasoning already governs a type under a deactivated category;
        see :meth:`DocumentTypeService._validate_references`.
        """
        from app.models.document_category import DocumentType

        record = await self._documents.session.get(DocumentType, type_id)
        if record is None or record.deleted_at is not None:
            raise ConflictError(
                "The selected document type does not exist or is archived.",
                error_code="invalid_document_type",
            )
        return record

    async def _load_document_type(self, type_id: uuid.UUID, category_id: uuid.UUID) -> Any:
        """Resolve a type that is being *chosen*, and confirm the pair is coherent.

        Stricter than :meth:`_get_document_type` precisely because this is a new
        selection: an inactive type must not be picked, and filing a passport
        under "Contracts" is not a validation error the database would catch --
        both ids are valid -- so the category is checked here.
        """
        record = await self._get_document_type(type_id)

        if record.status != "active":
            raise ConflictError(
                f"The document type {record.name!r} is inactive and cannot be used.",
                error_code="invalid_document_type",
            )
        if record.category_id != category_id:
            raise ConflictError(
                f"{record.name!r} belongs to a different category. Choose the category it sits in.",
                error_code="category_mismatch",
            )
        return record

    @staticmethod
    def _assert_expiry_supplied(document_type: Any, expiry_date: date | None) -> None:
        if document_type.requires_expiry and expiry_date is None:
            raise ValidationError(
                f"{document_type.name} needs an expiry date.",
                error_code="expiry_required",
            )

    def _assert_sortable(self, sort_by: str) -> None:
        if sort_by not in self._documents.sortable_fields:
            allowed = ", ".join(sorted(self._documents.sortable_fields))
            raise BadRequestError(
                f"Cannot sort by {sort_by!r}. Sortable columns are: {allowed}.",
                error_code="invalid_sort_field",
            )

    @staticmethod
    def _assert_date_range(start: date | None, end: date | None) -> None:
        if start is not None and end is not None and start > end:
            raise BadRequestError(
                "The start of the upload-date range is after its end.",
                error_code="invalid_date_range",
            )

    @staticmethod
    def _assert_not_archived(document: Document) -> None:
        if document.deleted_at is not None:
            raise ConflictError(
                "This document is archived. Restore it before making changes.",
                error_code="record_archived",
            )
        if document.status not in _EDITABLE_STATUSES:
            raise ConflictError(
                "This document cannot be changed in its current state.",
                error_code="not_editable",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _checksum(content: bytes) -> str:
        import hashlib

        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _today() -> date:
        return datetime.now(UTC).date()

    async def _reload(self, document_id: uuid.UUID) -> Document:
        refreshed = await self._documents.get_with_relationships(document_id)
        if refreshed is None:  # pragma: no cover - the row was just written
            raise NotFoundError("Document")
        return refreshed
