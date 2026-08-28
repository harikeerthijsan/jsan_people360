"""Default document categories and types.

The vault is unusable until at least one category and type exist, so these are
seeded with the platform rather than left as setup homework. They are ordinary
master records: an administrator can rename them, deactivate them, or add their
own.

Idempotent, like the rest of the seed -- matched on code, and never overwriting
an operator's edits.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.document_category import DocumentCategory, DocumentType
from app.models.enums import RecordStatus

logger = get_logger("cli.seed.documents")

#: Categories, in the order they are offered. Ordered by how often HR reaches
#: for them rather than alphabetically.
DEFAULT_CATEGORIES: tuple[dict[str, Any], ...] = (
    {
        "code": "IDENTITY",
        "name": "Identity Documents",
        "display_order": 10,
        "description": "Government-issued proof of identity.",
    },
    {
        "code": "ADDRESS",
        "name": "Address Proof",
        "display_order": 20,
        "description": "Documents evidencing a residential address.",
    },
    {
        "code": "EDUCATION",
        "name": "Educational Certificates",
        "display_order": 30,
        "description": "Degrees, diplomas and transcripts.",
    },
    {
        "code": "EMPLOYMENT",
        "name": "Employment Documents",
        "display_order": 40,
        "description": "Letters and records from current or previous employment.",
    },
    {
        "code": "GOVERNMENT",
        "name": "Government Documents",
        "display_order": 50,
        "description": "Statutory registrations and filings.",
    },
    {
        "code": "FINANCIAL",
        "name": "Financial Documents",
        "display_order": 60,
        "description": "Bank and salary records.",
    },
    {
        "code": "HR_LETTERS",
        "name": "HR Letters",
        "display_order": 70,
        "description": "Letters issued by HR to an employee.",
    },
    {"code": "CONTRACTS", "name": "Contracts", "display_order": 80, "description": "Signed agreements."},
    {
        "code": "PROJECT",
        "name": "Project Documents",
        "display_order": 90,
        "description": "Documents relating to a client or internal project.",
    },
    {
        "code": "OTHER",
        "name": "Other Documents",
        "display_order": 999,
        "description": "Anything that does not belong elsewhere.",
    },
)

#: Types, keyed by the code of the category they belong to.
#:
#: ``requires_expiry`` is set only where the document genuinely stops being
#: valid -- a passport does, a résumé does not -- because a required field that
#: is not really required trains people to enter nonsense.
DEFAULT_TYPES: tuple[dict[str, Any], ...] = (
    {"category": "IDENTITY", "code": "AADHAAR", "name": "Aadhaar", "is_sensitive": True},
    {"category": "IDENTITY", "code": "PAN", "name": "PAN Card", "is_sensitive": True},
    {
        "category": "IDENTITY",
        "code": "PASSPORT",
        "name": "Passport",
        "requires_expiry": True,
        "is_sensitive": True,
    },
    {
        "category": "IDENTITY",
        "code": "DL",
        "name": "Driving License",
        "requires_expiry": True,
        "is_sensitive": True,
    },
    {"category": "ADDRESS", "code": "UTILITY_BILL", "name": "Utility Bill"},
    {"category": "ADDRESS", "code": "RENT_AGREEMENT", "name": "Rental Agreement"},
    {"category": "EDUCATION", "code": "DEGREE", "name": "Degree Certificate"},
    {"category": "EDUCATION", "code": "MARKSHEET", "name": "Marksheet"},
    {"category": "EMPLOYMENT", "code": "RESUME", "name": "Resume"},
    {"category": "EMPLOYMENT", "code": "RELIEVING", "name": "Relieving Letter"},
    {"category": "EMPLOYMENT", "code": "EXPERIENCE", "name": "Experience Letter"},
    {"category": "GOVERNMENT", "code": "UAN_PROOF", "name": "UAN Proof", "is_sensitive": True},
    {"category": "FINANCIAL", "code": "SALARY_SLIP", "name": "Salary Slip", "is_sensitive": True},
    {"category": "FINANCIAL", "code": "BANK_PASSBOOK", "name": "Bank Passbook", "is_sensitive": True},
    {"category": "HR_LETTERS", "code": "OFFER_LETTER", "name": "Offer Letter"},
    {"category": "HR_LETTERS", "code": "APPOINTMENT", "name": "Appointment Letter"},
    # Signed agreements are PDF only: a photograph of a contract is not one.
    {
        "category": "CONTRACTS",
        "code": "NDA",
        "name": "Non-Disclosure Agreement",
        "allowed_extensions": ".pdf",
    },
    {
        "category": "CONTRACTS",
        "code": "EMP_CONTRACT",
        "name": "Employment Contract",
        "allowed_extensions": ".pdf",
    },
    {"category": "PROJECT", "code": "PROJECT_DOC", "name": "Project Document"},
    {"category": "OTHER", "code": "MISC", "name": "Miscellaneous"},
)


async def seed_document_masters(session: AsyncSession) -> None:
    """Insert the default categories and types if they are absent."""
    categories: dict[str, DocumentCategory] = {}

    for entry in DEFAULT_CATEGORIES:
        existing = (
            (await session.execute(select(DocumentCategory).where(DocumentCategory.code == entry["code"])))
            .scalars()
            .first()
        )

        if existing is None:
            existing = DocumentCategory(status=RecordStatus.ACTIVE, **entry)
            session.add(existing)
            await session.flush()

        categories[entry["code"]] = existing

    for entry in DEFAULT_TYPES:
        payload = dict(entry)
        category = categories[payload.pop("category")]

        exists = (
            (await session.execute(select(DocumentType).where(DocumentType.code == payload["code"])))
            .scalars()
            .first()
        )
        if exists is not None:
            continue

        session.add(DocumentType(category_id=category.id, status=RecordStatus.ACTIVE, **payload))

    await session.flush()
    logger.info(
        "Document masters seeded",
        extra={"categories": len(DEFAULT_CATEGORIES), "types": len(DEFAULT_TYPES)},
    )
