"""Payslips (Phase 7).

A payslip is a document rendered *over* a finalized payroll snapshot, and
three rules follow from that.

**Only finalized payroll becomes a payslip.** Generation refuses any run
that is not ``finalized`` and any employee without a snapshot; the numbers
on a payslip are the snapshot's numbers, copied once and never recomputed.

**The number is the identity.** ``PS-YYYY-MM-EMPCODE`` — traceable to the
period and the employee by reading it — unique by constraint and immutable
by construction: no code path updates it.

**Regeneration replaces the file, nothing else.** The PDF is rebuilt from
the same snapshot; the service re-checks that gross, deductions and net
still match before it will store a new file. A correction to a finalized
payroll is a separate controlled process of a later phase, never an edit
here.

The rendering reads from the same :class:`PayslipDetail` the screens show,
so what an employee sees in the browser and what they download cannot
disagree.
"""

from __future__ import annotations

import io
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.exceptions import ConflictError, NotFoundError
from app.models.audit_log import AuditAction
from app.models.employee import Employee
from app.models.enums import (
    PayFrequency,
    PayrollAdjustmentStatus,
    PayrollItemType,
    PayrollRecordStatus,
    PayrollRunStatus,
    PayslipStatus,
)
from app.models.organization import Organization
from app.models.payroll import PayrollFinalSnapshot, PayrollRun, Payslip
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.payroll_repository import (
    PayrollConfigurationRepository,
    PayrollEmployeeRecordRepository,
    PayrollFinalSnapshotRepository,
    PayrollRunRepository,
    PayslipRepository,
)
from app.schemas.payroll import (
    EmployeeSummary,
    PayrollPeriodRead,
    PayslipDetail,
    PayslipEmployee,
    PayslipEmployer,
    PayslipGenerationResult,
    PayslipLine,
    PayslipListParams,
    PayslipRead,
)
from app.services.audit_service import AuditService
from app.storage import StorageBackend
from app.utils.amount_words import amount_to_words
from app.utils.datetime import utc_now

_CENT = Decimal("0.01")


class PayslipService:
    """Generate, regenerate, list, view and download payslips."""

    def __init__(
        self,
        payslips: PayslipRepository,
        runs: PayrollRunRepository,
        snapshots: PayrollFinalSnapshotRepository,
        records: PayrollEmployeeRecordRepository,
        organizations: OrganizationRepository,
        config: PayrollConfigurationRepository,
        storage: StorageBackend,
        audit: AuditService,
    ) -> None:
        self.payslips = payslips
        self.runs = runs
        self.snapshots = snapshots
        self.records = records
        self.organizations = organizations
        self.config = config
        self.storage = storage
        self.audit = audit

    # ==================================================================
    # Generation
    # ==================================================================
    async def generate_for_run(self, run_id: uuid.UUID, *, actor_id: uuid.UUID) -> PayslipGenerationResult:
        run = await self.runs.get(run_id)
        if run is None:
            raise NotFoundError("Payroll run")
        if run.status != PayrollRunStatus.FINALIZED.value:
            raise ConflictError(
                "Official payslips come only from finalized payroll. This run is "
                f"{run.status.replace('_', ' ')}.",
                error_code="not_finalized",
            )
        snapshots = await self.snapshots.for_run(run.id)
        if not snapshots:
            raise ConflictError(
                "This run has no final snapshots to render payslips from.",
                error_code="no_snapshots",
            )
        records = {r.employee_id: r for r in await self.records.for_run(run.id)}
        organization = await self.organizations.get_primary()
        frequency = await self._pay_frequency()

        generated: list[PayslipRead] = []
        already = 0
        excluded = 0
        for snapshot in snapshots:
            if snapshot.status == PayrollRecordStatus.EXCLUDED.value:
                excluded += 1
                continue
            if await self.payslips.by_run_employee(run.id, snapshot.employee_id) is not None:
                already += 1
                continue
            record = records.get(snapshot.employee_id)
            if record is None:
                raise ConflictError(
                    f"No payroll record exists for {snapshot.employee_name} on this run.",
                    error_code="payslip_invalid",
                )
            self._validate(run, snapshot, record.id, record.employee_id)

            number = await self._next_number(run, snapshot)
            # The id is minted here rather than by the database: the detail is
            # rendered — and its number embedded in the PDF — before the row is
            # flushed, and the presenter needs the id to exist.
            payslip = Payslip(
                id=uuid.uuid4(),
                payslip_number=number,
                run_id=run.id,
                record_id=record.id,
                snapshot_id=snapshot.id,
                employee_id=snapshot.employee_id,
                period_id=run.payroll_period_id,
                status=PayslipStatus.GENERATED.value,
                currency=snapshot.currency,
                gross_earnings=snapshot.final_gross,
                total_deductions=snapshot.final_deductions,
                net_pay=snapshot.final_net,
                generated_at=utc_now(),
                generated_by_id=actor_id,
                pdf_key="",
            )
            # The file is rendered from the detail the screens show, so the
            # two can never disagree.
            payslip.employee = snapshot.employee
            payslip.period = run.period
            payslip.snapshot = snapshot
            payslip.run = run
            detail = self._detail(payslip, organization, frequency, generated_by=None)
            stored = await self.storage.save(
                content=self._render(detail, organization),
                key=f"payslips/{run.id}/{number}-{uuid.uuid4().hex[:8]}.pdf",
            )
            payslip.pdf_key = stored.key
            payslip.pdf_size = stored.size_bytes
            payslip.pdf_checksum = stored.checksum
            payslip = await self.payslips.add(payslip, actor_id=actor_id)
            await self.audit.record_success(
                AuditAction.PAYSLIP_GENERATED,
                actor_id=actor_id,
                entity_type="payslip",
                entity_id=payslip.id,
                description=f"Generated payslip {number} for {snapshot.employee_name}",
                context={"run_id": str(run.id), "employee_id": str(snapshot.employee_id)},
            )
            generated.append(self._present(payslip))

        return PayslipGenerationResult(
            run_id=run.id,
            generated=len(generated),
            already_existed=already,
            skipped_excluded=excluded,
            payslips=generated,
        )

    async def regenerate(self, payslip_id: uuid.UUID, *, actor_id: uuid.UUID) -> PayslipRead:
        """Rebuild the PDF from the same snapshot. Nothing else moves."""
        payslip = await self.payslips.get(payslip_id)
        if payslip is None:
            raise NotFoundError("Payslip")
        snapshot = payslip.snapshot
        if (
            snapshot.final_gross != payslip.gross_earnings
            or snapshot.final_deductions != payslip.total_deductions
            or snapshot.final_net != payslip.net_pay
        ):  # pragma: no cover - both sides are immutable; this is a tripwire
            raise ConflictError(
                "The payslip's figures no longer match its snapshot; regeneration refused.",
                error_code="payslip_mismatch",
            )
        organization = await self.organizations.get_primary()
        detail = self._detail(payslip, organization, await self._pay_frequency(), generated_by=None)
        stored = await self.storage.save(
            content=self._render(detail, organization),
            key=f"payslips/{payslip.run_id}/{payslip.payslip_number}-{uuid.uuid4().hex[:8]}.pdf",
        )
        await self.payslips.update(
            payslip,
            {
                "pdf_key": stored.key,
                "pdf_size": stored.size_bytes,
                "pdf_checksum": stored.checksum,
                "regenerated_at": utc_now(),
                "regenerated_by_id": actor_id,
            },
            actor_id=actor_id,
        )
        await self.audit.record_success(
            AuditAction.PAYSLIP_REGENERATED,
            actor_id=actor_id,
            entity_type="payslip",
            entity_id=payslip.id,
            description=f"Regenerated the PDF of payslip {payslip.payslip_number}",
            context={"employee_id": str(payslip.employee_id)},
        )
        return self._present(payslip)

    # ==================================================================
    # Administrator reads
    # ==================================================================
    async def list_admin(self, params: PayslipListParams) -> tuple[list[PayslipRead], int]:
        rows, total = await self.payslips.search(params)
        return [self._present(row) for row in rows], total

    async def get_admin(
        self, employee_id: uuid.UUID, payslip_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> PayslipDetail:
        payslip = await self._require_for_employee(employee_id, payslip_id)
        await self.audit.record_success(
            AuditAction.PAYSLIP_VIEWED,
            actor_id=actor_id,
            entity_type="payslip",
            entity_id=payslip.id,
            description=f"Viewed payslip {payslip.payslip_number}",
            context={"employee_id": str(payslip.employee_id)},
        )
        return await self._full_detail(payslip)

    async def download_admin(
        self, employee_id: uuid.UUID, payslip_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> tuple[bytes, str]:
        payslip = await self._require_for_employee(employee_id, payslip_id)
        return await self._download(payslip, actor_id=actor_id)

    # ==================================================================
    # Employee self-service
    # ==================================================================
    async def list_mine(self, employee: Employee, params: PayslipListParams) -> tuple[list[PayslipRead], int]:
        rows, total = await self.payslips.for_employee(employee.id, params)
        return [self._present(row) for row in rows], total

    async def get_mine(
        self, employee: Employee, payslip_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> PayslipDetail:
        payslip = await self._require_owned(employee, payslip_id, actor_id=actor_id)
        return await self._full_detail(payslip)

    async def download_mine(
        self, employee: Employee, payslip_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> tuple[bytes, str]:
        payslip = await self._require_owned(employee, payslip_id, actor_id=actor_id)
        return await self._download(payslip, actor_id=actor_id)

    # ==================================================================
    # Internals
    # ==================================================================
    async def _require_owned(
        self, employee: Employee, payslip_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> Payslip:
        """The caller's own payslip, or a 404 that leaves a trace.

        A forged or foreign id is answered as "no such payslip" — the
        existence of somebody else's payslip is itself not the caller's to
        learn — and the attempt is audited through the request's rollback.
        """
        payslip = await self.payslips.get(payslip_id)
        if payslip is None or payslip.employee_id != employee.id:
            await self.audit.record_failure(
                AuditAction.PAYSLIP_ACCESS_DENIED,
                actor_id=actor_id,
                entity_type="payslip",
                entity_id=payslip_id,
                description="Refused access to a payslip that is not the caller's own",
                context={"employee_id": str(employee.id)},
            )
            error = NotFoundError("Payslip")
            error.preserve_writes = True
            raise error
        return payslip

    async def _require_for_employee(self, employee_id: uuid.UUID, payslip_id: uuid.UUID) -> Payslip:
        payslip = await self.payslips.get(payslip_id)
        if payslip is None or payslip.employee_id != employee_id:
            raise NotFoundError("Payslip")
        return payslip

    async def _download(self, payslip: Payslip, *, actor_id: uuid.UUID) -> tuple[bytes, str]:
        content = await self.storage.read(payslip.pdf_key)
        await self.audit.record_success(
            AuditAction.PAYSLIP_DOWNLOADED,
            actor_id=actor_id,
            entity_type="payslip",
            entity_id=payslip.id,
            description=f"Downloaded payslip {payslip.payslip_number}",
            context={"employee_id": str(payslip.employee_id)},
        )
        return content, f"{payslip.payslip_number}.pdf"

    async def _pay_frequency(self) -> PayFrequency:
        config = await self.config.singleton()
        return PayFrequency(config.pay_frequency) if config is not None else PayFrequency.MONTHLY

    @staticmethod
    def _validate(
        run: PayrollRun,
        snapshot: PayrollFinalSnapshot,
        record_id: uuid.UUID,
        record_employee_id: uuid.UUID,
    ) -> None:
        """Every claim a payslip makes must already be true of its source."""
        problems: list[str] = []
        if record_employee_id != snapshot.employee_id:
            problems.append("the payroll record and the snapshot name different employees")
        if snapshot.run_id != run.id:
            problems.append("the snapshot belongs to a different run")
        if snapshot.final_gross < 0:
            problems.append("gross earnings are negative")
        if snapshot.final_deductions < 0:
            problems.append("deductions are negative")
        if snapshot.final_net != snapshot.final_gross - snapshot.final_deductions:
            problems.append("net pay is not gross minus deductions")
        if snapshot.status == PayrollRecordStatus.REQUIRES_REVIEW.value:
            problems.append("the record was never calculated")
        if problems:
            raise ConflictError(
                f"Payslip for {snapshot.employee_name} refused: " + "; ".join(problems) + ".",
                error_code="payslip_invalid",
            )
        del record_id

    async def _next_number(self, run: PayrollRun, snapshot: PayrollFinalSnapshot) -> str:
        """``PS-YYYY-MM-EMPCODE``; a second period ending in the same month
        (weekly payroll, a special run) gets a numeric suffix rather than a
        collision."""
        base = f"PS-{run.period.end_date:%Y-%m}-{snapshot.employee_code}"
        candidate = base
        suffix = 2
        while (existing := await self.payslips.by_number(candidate)) is not None:
            if existing.run_id == run.id:  # pragma: no cover - guarded by by_run_employee
                break
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    # ------------------------------------------------------------------
    # Presentation
    # ------------------------------------------------------------------
    @staticmethod
    def _present(payslip: Payslip) -> PayslipRead:
        return PayslipRead(
            id=payslip.id,
            payslip_number=payslip.payslip_number,
            run_id=payslip.run_id,
            employee=EmployeeSummary.model_validate(payslip.employee),
            period=PayrollPeriodRead.model_validate(payslip.period),
            payroll_month=payslip.period.end_date.strftime("%B %Y"),
            status=PayslipStatus(payslip.status),
            currency=payslip.currency,
            gross_earnings=payslip.gross_earnings,
            total_deductions=payslip.total_deductions,
            net_pay=payslip.net_pay,
            generated_at=payslip.generated_at,
            regenerated_at=payslip.regenerated_at,
        )

    async def _full_detail(self, payslip: Payslip) -> PayslipDetail:
        organization = await self.organizations.get_primary()
        generated_by = None
        if payslip.generated_by_id is not None:
            await self.payslips.session.refresh(payslip, ["snapshot"])
        return self._detail(payslip, organization, await self._pay_frequency(), generated_by=generated_by)

    def _detail(
        self,
        payslip: Payslip,
        organization: Organization | None,
        frequency: PayFrequency,
        *,
        generated_by: str | None,
    ) -> PayslipDetail:
        snapshot = payslip.snapshot
        employee = payslip.employee
        bank = employee.bank_detail
        earnings: list[PayslipLine] = []
        deductions: list[PayslipLine] = []
        for item in snapshot.line_items:
            line = PayslipLine(
                name=str(item.get("name", "")),
                code=item.get("code"),
                calculation_basis=item.get("calculation_basis"),
                amount=Decimal(str(item.get("amount", "0"))),
            )
            (earnings if item.get("item_type") == PayrollItemType.EARNING.value else deductions).append(line)
        for adjustment in snapshot.adjustments:
            if adjustment.get("status") != PayrollAdjustmentStatus.ACTIVE.value:
                continue
            line = PayslipLine(
                name=f"{adjustment.get('name', 'Adjustment')} (adjustment)",
                code=None,
                calculation_basis=adjustment.get("reason"),
                amount=Decimal(str(adjustment.get("amount", "0"))),
            )
            (earnings if adjustment.get("item_type") == PayrollItemType.EARNING.value else deductions).append(
                line
            )

        address = None
        if organization is not None:
            parts = [
                organization.address_line1,
                organization.address_line2,
                organization.city,
                organization.state,
                organization.postal_code,
                organization.country,
            ]
            address = ", ".join(part for part in parts if part)

        return PayslipDetail(
            **self._present(payslip).model_dump(),
            employer=PayslipEmployer(
                name=organization.name if organization is not None else None,
                address=address,
                logo_url=organization.logo_url if organization is not None else None,
            ),
            employee_details=PayslipEmployee(
                name=snapshot.employee_name,
                employee_code=snapshot.employee_code,
                department=employee.team.name if employee.team is not None else None,
                designation=employee.designation.name if employee.designation is not None else None,
                joining_date=employee.joining_date,
                bank_name=bank.bank_name if bank is not None else None,
                account_masked=(
                    f"••••{bank.account_number[-4:]}" if bank is not None and bank.account_number else None
                ),
            ),
            period_start=snapshot.period_start,
            period_end=snapshot.period_end,
            pay_date=snapshot.pay_date,
            pay_frequency=frequency,
            earnings=earnings,
            deductions=deductions,
            amount_in_words=amount_to_words(snapshot.final_net, snapshot.currency),
            generated_by_name=generated_by,
            structure_name=snapshot.structure_name,
        )

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------
    @staticmethod
    def _money(amount: Decimal, currency: str) -> str:
        return f"{currency} {amount.quantize(_CENT):,.2f}"

    def _render(self, detail: PayslipDetail, organization: Organization | None) -> bytes:
        """A printable A4 payslip. Uncompressed page streams on purpose:
        the document is small, and a plain-text stream can be verified."""
        out = io.BytesIO()
        doc = SimpleDocTemplate(
            out,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=f"Payslip {detail.payslip_number}",
            author=detail.employer.name or "JSAN People360",
            pageCompression=0,
        )
        styles = getSampleStyleSheet()
        small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8, textColor=colors.grey)
        right = ParagraphStyle("right", parent=styles["BodyText"], alignment=TA_RIGHT)
        heading = ParagraphStyle(
            "heading", parent=styles["Heading4"], textColor=colors.HexColor("#1F4E78"), spaceAfter=4
        )
        navy = colors.HexColor("#1F4E78")
        currency = detail.currency

        def grid(rows: list[list[Any]], widths: list[float], *, header: bool = True) -> Table:
            table = Table(rows, colWidths=widths, hAlign="LEFT")
            style = [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BFBFBF")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
            if header:
                style += [
                    ("BACKGROUND", (0, 0), (-1, 0), navy),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            table.setStyle(TableStyle(style))
            return table

        employer = detail.employer
        story: list[Any] = [
            Paragraph(employer.name or "JSAN People360", styles["Title"]),
        ]
        if employer.address:
            story.append(Paragraph(employer.address, small))
        story += [
            Spacer(1, 6),
            Paragraph(f"PAYSLIP &mdash; {detail.payroll_month}", styles["Heading2"]),
            Paragraph(
                f"Payslip No. <b>{detail.payslip_number}</b> &nbsp;&middot;&nbsp; "
                f"Generated {detail.generated_at:%d %b %Y}",
                small,
            ),
            Spacer(1, 8),
        ]

        emp = detail.employee_details
        identity_rows = [
            ["Employee", emp.name, "Employee ID", emp.employee_code],
            ["Department", emp.department or "—", "Designation", emp.designation or "—"],
            [
                "Joining date",
                emp.joining_date.strftime("%d %b %Y") if emp.joining_date else "—",
                "Pay frequency",
                detail.pay_frequency.value.title(),
            ],
            [
                "Pay period",
                f"{detail.period_start:%d %b %Y} - {detail.period_end:%d %b %Y}",
                "Pay date",
                detail.pay_date.strftime("%d %b %Y"),
            ],
        ]
        if emp.bank_name:
            identity_rows.append(["Bank", emp.bank_name, "Account", emp.account_masked or "—"])
        identity = grid(identity_rows, [28 * mm, 60 * mm, 30 * mm, 56 * mm], header=False)
        identity.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F2F2")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F2F2F2")),
                ]
            )
        )
        story += [identity, Spacer(1, 10)]

        def lines_table(title: str, lines: list[PayslipLine], total: Decimal) -> Table:
            rows: list[list[Any]] = [[title, "Amount"]]
            for line in lines:
                label = line.name
                if line.calculation_basis:
                    label = f"{line.name}<br/><font size=7 color=grey>{line.calculation_basis}</font>"
                rows.append([Paragraph(label, styles["BodyText"]), self._money(line.amount, currency)])
            if not lines:
                rows.append([Paragraph("None", small), self._money(Decimal("0"), currency)])
            rows.append(
                [Paragraph(f"<b>Total {title.lower()}</b>", styles["BodyText"]), self._money(total, currency)]
            )
            table = grid(rows, [58 * mm, 27 * mm])
            table.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F2F2F2")),
                        ("FONTNAME", (1, -1), (1, -1), "Helvetica-Bold"),
                    ]
                )
            )
            return table

        side_by_side = Table(
            [
                [
                    lines_table("Earnings", detail.earnings, detail.gross_earnings),
                    lines_table("Deductions", detail.deductions, detail.total_deductions),
                ]
            ],
            colWidths=[87 * mm, 87 * mm],
            hAlign="LEFT",
        )
        side_by_side.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [side_by_side, Spacer(1, 12)]

        summary = grid(
            [
                ["Gross earnings", self._money(detail.gross_earnings, currency)],
                ["Total deductions", self._money(detail.total_deductions, currency)],
                ["Net pay", self._money(detail.net_pay, currency)],
            ],
            [120 * mm, 54 * mm],
            header=False,
        )
        summary.setStyle(
            TableStyle(
                [
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8F0F8")),
                    ("FONTSIZE", (0, -1), (-1, -1), 11),
                ]
            )
        )
        story += [
            Paragraph("Summary", heading),
            summary,
            Spacer(1, 6),
            Paragraph(f"<b>Net pay in words:</b> {detail.amount_in_words}", styles["BodyText"]),
            Spacer(1, 18),
            Paragraph(
                "This is a computer-generated payslip and does not require a signature. "
                "Figures are drawn from the finalized payroll for the period shown.",
                small,
            ),
            Paragraph(f"Payslip {detail.payslip_number} · {detail.employee_details.employee_code}", right),
        ]
        doc.build(story)
        return out.getvalue()


def payroll_month(end: date) -> str:
    """ "August 2026" for a period ending in August."""
    return end.strftime("%B %Y")
