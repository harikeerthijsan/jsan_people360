from __future__ import annotations

import io
import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from fastapi.encoders import jsonable_encoder
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select, update

from app.core.exceptions import ConflictError, NotFoundError
from app.models.document import Document, DocumentVersion
from app.models.document_category import DocumentCategory, DocumentType
from app.models.enums import RecordStatus
from app.models.offer import (
    Offer,
    OfferApproval,
    OfferSalaryComponent,
    OfferStatusHistory,
    OfferTemplate,
    OfferVersion,
)
from app.models.recruitment import Candidate, RecruitmentStage
from app.models.requisition import Notification
from app.repositories.offer_repository import (
    ApprovalRepository,
    ComponentRepository,
    HistoryRepository,
    OfferRepository,
    TemplateRepository,
    VersionRepository,
)
from app.repositories.requisition_repository import NotificationRepository
from app.schemas.offer import (
    OfferCreate,
    OfferDashboard,
    OfferListParams,
    OfferUpdate,
    TemplateCreate,
)
from app.services.audit_service import AuditService
from app.storage import StorageBackend
from app.utils.datetime import utc_now


class OfferService:
    def __init__(
        self,
        offers: OfferRepository,
        versions: VersionRepository,
        approvals: ApprovalRepository,
        history: HistoryRepository,
        components: ComponentRepository,
        templates: TemplateRepository,
        notifications: NotificationRepository,
        audit: AuditService,
        storage: StorageBackend,
    ) -> None:
        self.offers: OfferRepository = offers
        self.versions: VersionRepository = versions
        self.approvals: ApprovalRepository = approvals
        self.history: HistoryRepository = history
        self.components: ComponentRepository = components
        self.templates: TemplateRepository = templates
        self.notifications: NotificationRepository = notifications
        self.audit: AuditService = audit
        self.storage: StorageBackend = storage

    async def get(self, oid: uuid.UUID) -> Offer:
        await self.expire()
        x = await self.offers.get_detailed(oid)
        if not x:
            raise NotFoundError("Offer")
        return x

    async def list(self, p: OfferListParams) -> tuple[Sequence[Offer], int]:
        await self.expire()
        return await self.offers.search(p)

    async def create(self, p: OfferCreate, actor: uuid.UUID) -> Offer:
        c = await self.offers.session.get(Candidate, p.candidate_id)
        if not c or c.deleted_at:
            raise NotFoundError("Candidate")
        stage = await self.offers.session.get(RecruitmentStage, c.stage_id)
        if not stage or stage.name != "Selected":
            raise ConflictError("Only selected candidates can receive an offer.")
        if await self.offers.find(
            Offer.candidate_id == c.id,
            Offer.status.in_(["draft", "pending_approval", "approved", "released", "accepted"]),
        ):
            raise ConflictError("Candidate already has an active offer.")
        values = p.model_dump(
            exclude={"salary_components", "hr_executive_id", "hr_manager_id", "business_unit_head_id"}
        )
        x = await self.offers.add(Offer(**values, job_opening_id=c.job_opening_id), actor_id=actor)
        for comp in p.salary_components:
            await self.components.add(
                OfferSalaryComponent(offer_id=x.id, **comp.model_dump()), actor_id=actor
            )
        for seq, (role, user) in enumerate(
            (
                ("HR Executive", p.hr_executive_id),
                ("HR Manager", p.hr_manager_id),
                ("Business Unit Head", p.business_unit_head_id),
            ),
            1,
        ):
            await self.approvals.add(
                OfferApproval(
                    offer_id=x.id, sequence=seq, role_name=role, approver_id=user, status="waiting"
                ),
                actor_id=actor,
            )
        await self._version(x, actor)
        await self._history(x, "created", None, "draft", actor)
        await self._audit("offer.created", x.id, actor)
        return await self.get(x.id)

    async def update(self, oid: uuid.UUID, p: OfferUpdate, actor: uuid.UUID) -> Offer:
        x = await self.get(oid)
        if x.status not in {"draft", "rejected"}:
            raise ConflictError("Only draft or rejected offers can be edited.")
        await self.offers.update(x, p.model_dump(exclude_unset=True), actor_id=actor)
        x.current_version += 1
        await self.offers.session.flush()
        await self._version(x, actor)
        await self._history(x, "updated", x.status, x.status, actor)
        await self._audit("offer.updated", x.id, actor)
        return x

    async def submit(self, oid: uuid.UUID, actor: uuid.UUID) -> Offer:
        x = await self.get(oid)
        if x.status not in {"draft", "rejected"}:
            raise ConflictError("Offer cannot be submitted.")
        await self.offers.update(x, {"status": "pending_approval"}, actor_id=actor)
        first = x.approvals[0]
        await self.approvals.update(first, {"status": "pending"}, actor_id=actor)
        await self._notify(first.approver_id, "Offer approval pending", x, actor)
        await self._history(x, "submitted", "draft", "pending_approval", actor)
        return x

    async def approval(self, oid: uuid.UUID, action: str, comments: str | None, actor: uuid.UUID) -> Offer:
        x = await self.get(oid)
        if x.status != "pending_approval":
            raise ConflictError("Offer is not awaiting approval.")
        current = next((a for a in x.approvals if a.status == "pending"), None)
        if not current or current.approver_id != actor:
            raise ConflictError("Approval is assigned to another user.")
        await self.approvals.update(
            current, {"status": action, "comments": comments, "acted_at": utc_now()}, actor_id=actor
        )
        if action == "approve":
            nxt = next((a for a in x.approvals if a.sequence == current.sequence + 1), None)
            if nxt:
                await self.approvals.update(nxt, {"status": "pending"}, actor_id=actor)
                await self._notify(nxt.approver_id, "Offer approval pending", x, actor)
            else:
                await self.offers.update(x, {"status": "approved"}, actor_id=actor)
                await self._history(x, "approved", "pending_approval", "approved", actor)
        else:
            target = "rejected" if action == "reject" else "draft"
            await self.offers.update(x, {"status": target}, actor_id=actor)
            await self._history(x, action, "pending_approval", target, actor, comments)
        await self._audit(f"offer.{action}", x.id, actor)
        return x

    async def generate_pdf(self, oid: uuid.UUID, actor: uuid.UUID) -> tuple[uuid.UUID, bytes]:
        x = await self.get(oid)
        pdf = self._pdf(x)
        category = await self.offers.session.scalar(
            select(DocumentCategory).where(DocumentCategory.code == "OFFER")
        )
        if not category:
            category = DocumentCategory(name="Offer Letters", code="OFFER", status=RecordStatus.ACTIVE)
            self.offers.session.add(category)
            await self.offers.session.flush()
        dtype = await self.offers.session.scalar(select(DocumentType).where(DocumentType.code == "OFFPDF"))
        if not dtype:
            dtype = DocumentType(
                name="Offer Letter PDF", code="OFFPDF", category_id=category.id, status=RecordStatus.ACTIVE
            )
            self.offers.session.add(dtype)
            await self.offers.session.flush()
        doc = Document(
            name=f"Offer Letter {x.offer_code}",
            category_id=category.id,
            document_type_id=dtype.id,
            owner_type="candidate",
            owner_id=x.candidate_id,
            version_count=1,
        )
        self.offers.session.add(doc)
        await self.offers.session.flush()
        key = f"offers/{x.id}/v{x.current_version}-{uuid.uuid4()}.pdf"
        stored = await self.storage.save(content=pdf, key=key)
        dv = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            original_filename=f"{x.offer_code}.pdf",
            content_type="application/pdf",
            size_bytes=stored.size_bytes,
            checksum=stored.checksum,
            storage_key=stored.key,
            created_by=actor,
            updated_by=actor,
        )
        self.offers.session.add(dv)
        await self.offers.session.flush()
        doc.current_version_id = dv.id
        version = await self._current_version(x)
        await self.versions.update(version, {"pdf_document_id": doc.id}, actor_id=actor)
        await self._audit("offer.pdf_generated", x.id, actor)
        return doc.id, pdf

    async def release(self, oid: uuid.UUID, actor: uuid.UUID) -> Offer:
        x = await self.get(oid)
        if x.status != "approved":
            raise ConflictError("Only approved offers can be released.")
        version = await self._current_version(x)
        if not version.pdf_document_id:
            await self.generate_pdf(x.id, actor)
        await self.offers.update(x, {"status": "released", "release_date": date.today()}, actor_id=actor)
        await self._history(x, "released", "approved", "released", actor)
        await self._notify(x.created_by, "Offer released", x, actor)
        return x

    async def candidate_action(
        self, oid: uuid.UUID, action: str, reason: str | None, actor: uuid.UUID
    ) -> Offer:
        x = await self.get(oid)
        if x.status != "released":
            raise ConflictError("Only released offers can be acted on.")
        vals: dict[str, Any]
        if action == "accept":
            vals = {"status": "accepted", "accepted_at": utc_now()}
        elif action == "decline":
            vals = {"status": "declined", "declined_at": utc_now(), "decline_reason": reason}
        else:
            vals = {"clarification_request": reason}
        await self.offers.update(x, vals, actor_id=actor)
        await self._history(x, action, "released", vals.get("status", "released"), actor, reason)
        await self._notify(x.created_by, f"Offer {action}", x, actor)
        return x

    async def withdraw(self, oid: uuid.UUID, reason: str | None, actor: uuid.UUID) -> Offer:
        x = await self.get(oid)
        if x.status in {"accepted", "declined", "expired", "withdrawn"}:
            raise ConflictError("Offer cannot be withdrawn.")
        old = x.status
        await self.offers.update(
            x, {"status": "withdrawn", "withdrawn_at": utc_now(), "withdrawal_reason": reason}, actor_id=actor
        )
        await self._history(x, "withdrawn", old, "withdrawn", actor, reason)
        return x

    async def expire(self) -> None:
        await self.offers.session.execute(
            update(Offer)
            .where(
                Offer.expiry_date < date.today(),
                Offer.status.in_(["approved", "released"]),
                Offer.deleted_at.is_(None),
            )
            .values(status="expired", updated_at=utc_now())
        )

    async def dashboard(self) -> OfferDashboard:
        await self.expire()
        s = self.offers.session

        async def c(status: str | None = None) -> int:
            return int(
                await s.scalar(
                    select(func.count())
                    .select_from(Offer)
                    .where(Offer.deleted_at.is_(None), *([Offer.status == status] if status else []))
                )
                or 0
            )

        total = await c()
        accepted = await c("accepted")
        released = await c("released") + accepted + await c("declined")
        return OfferDashboard(
            total=total,
            draft=await c("draft"),
            pending_approval=await c("pending_approval"),
            approved=await c("approved"),
            released=await c("released"),
            accepted=accepted,
            declined=await c("declined"),
            expired=await c("expired"),
            joining_pending=accepted,
            acceptance_rate=round(accepted / released * 100, 2) if released else 0,
            offer_to_join_ratio=0,
        )

    async def templates_list(self) -> Sequence[OfferTemplate]:
        return await self.templates.list(limit=500)

    async def template_create(self, p: TemplateCreate, actor: uuid.UUID) -> OfferTemplate:
        return await self.templates.add(OfferTemplate(**p.model_dump()), actor_id=actor)

    async def _current_version(self, x: Offer) -> OfferVersion:
        version = await self.versions.get_by(offer_id=x.id, version_number=x.current_version)
        if version is None:
            raise NotFoundError("Offer version")
        return version

    async def _version(self, x: Offer, actor: uuid.UUID) -> None:
        await self.versions.add(
            OfferVersion(
                offer_id=x.id,
                version_number=x.current_version,
                snapshot=jsonable_encoder({k: v for k, v in x.__dict__.items() if not k.startswith("_")}),
            ),
            actor_id=actor,
        )

    async def _history(
        self,
        x: Offer,
        action: str,
        old: str | None,
        new: str | None,
        actor: uuid.UUID,
        comments: str | None = None,
    ) -> None:
        await self.history.add(
            OfferStatusHistory(
                offer_id=x.id, action=action, from_status=old, to_status=new, comments=comments
            ),
            actor_id=actor,
        )

    async def _notify(self, user: uuid.UUID | None, title: str, x: Offer, actor: uuid.UUID) -> None:
        if user:
            await self.notifications.add(
                Notification(
                    user_id=user,
                    title=title,
                    message=x.offer_code,
                    link=f"/offers/{x.id}",
                    notification_type="offer",
                ),
                actor_id=actor,
            )

    async def _audit(self, action: str, eid: uuid.UUID, actor: uuid.UUID) -> None:
        await self.audit.record_success(action, actor_id=actor, entity_type="offer", entity_id=eid)

    def _pdf(self, x: Offer) -> bytes:
        out = io.BytesIO()
        doc = SimpleDocTemplate(out, pagesize=A4)
        styles = getSampleStyleSheet()
        story = [
            Paragraph("JSAN People360", styles["Title"]),
            Paragraph(f"Offer Letter - {x.offer_code}", styles["Heading1"]),
            Spacer(1, 12),
            Paragraph(f"Candidate: {x.candidate_id}", styles["BodyText"]),
            Paragraph(f"Joining Date: {x.joining_date}", styles["BodyText"]),
            Spacer(1, 12),
        ]
        data = (
            [["Compensation Component", "Annual Amount"]]
            + [[c.name, f"{c.annual_amount:,.2f}"] for c in x.salary_components]
            + [["Total CTC", f"{x.ctc:,.2f}"]]
        )
        table = Table(data, colWidths=[280, 140])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.extend(
            [
                table,
                Spacer(1, 16),
                Paragraph(x.benefits, styles["BodyText"]),
                Paragraph(x.confidentiality, styles["BodyText"]),
                Spacer(1, 30),
                Paragraph("Authorized Signature ____________________", styles["BodyText"]),
            ]
        )
        doc.build(story)
        return out.getvalue()
