"""Optional sample data for the Organization Management module.

Run with ``python -m app.cli.seed --sample-data``.

This is *demonstration* data, not defaults the product depends on: the module
works perfectly well against an empty database, and nothing in the code assumes
any of these records exist. It gives a fresh install a realistic hierarchy to
click through, and gives the later HR modules something to reference while they
are being built.

Idempotent -- every insert is skipped when a record with the same code (or, for
teams, the same name within a business unit) already exists.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.base_class import Base
from app.models.business_unit import BusinessUnit
from app.models.designation import Designation
from app.models.employment_type import EmploymentType
from app.models.enums import RecordStatus
from app.models.grade import Grade
from app.models.location import Location
from app.models.organization import Organization
from app.models.team import Team

logger = get_logger("cli.seed.organization")

# ----------------------------------------------------------------------
# Definitions
# ----------------------------------------------------------------------
ORGANIZATION: dict[str, Any] = {
    "name": "JSAN Technologies",
    "legal_name": "JSAN Technologies Private Limited",
    "registration_number": "U72900TG2015PTC000001",
    "timezone": "Asia/Kolkata",
    "currency": "INR",
    "address_line1": "Plot 12, HITEC City",
    "address_line2": "Madhapur",
    "city": "Hyderabad",
    "state": "Telangana",
    "country": "India",
    "postal_code": "500081",
    "description": "Sample organization profile created by the seed command.",
}

BUSINESS_UNITS: tuple[dict[str, str], ...] = (
    {"code": "TECH", "name": "Technology Services", "description": "Client-facing engineering delivery."},
    {"code": "CORP", "name": "Corporate Services", "description": "Internal functions supporting delivery."},
)

# (name, business unit code, description)
TEAMS: tuple[tuple[str, str, str], ...] = (
    ("Platform Engineering", "TECH", "Shared services the product teams build on."),
    ("Product Engineering", "TECH", "Customer-facing feature delivery."),
    ("Quality Engineering", "TECH", "Test automation and release quality."),
    ("Talent Acquisition", "CORP", "Sourcing, interviewing and offers."),
    ("Finance", "CORP", "Accounting, payroll and financial planning."),
)

# (code, name, business unit code, level, description)
DESIGNATIONS: tuple[tuple[str, str, str, int, str], ...] = (
    ("SE", "Software Engineer", "TECH", 2, "Delivers features with guidance."),
    ("SSE", "Senior Software Engineer", "TECH", 3, "Delivers complex features and mentors engineers."),
    ("TL", "Team Lead", "TECH", 4, "Leads a team's technical delivery."),
    ("PM", "Project Manager", "TECH", 4, "Owns scope, schedule and delivery risk."),
    ("HRE", "HR Executive", "CORP", 2, "Runs day-to-day people operations."),
)

# (code, name, level, description)
GRADES: tuple[tuple[str, str, int, str], ...] = (
    ("G1", "Grade 1", 1, "Entry-level individual contributor."),
    ("G2", "Grade 2", 2, "Established individual contributor."),
    ("G3", "Grade 3", 3, "Senior individual contributor."),
    ("M1", "Manager 1", 4, "First-line manager."),
    ("M2", "Manager 2", 5, "Manager of managers."),
)

EMPLOYMENT_TYPES: tuple[tuple[str, str, str], ...] = (
    ("FULL_TIME", "Full Time", "Permanent employee on the company payroll."),
    ("CONTRACT", "Contract", "Fixed-term engagement with an end date."),
    ("CONSULTANT", "Consultant", "Engaged through a consulting agreement."),
    ("INTERNSHIP", "Internship", "Time-boxed placement, usually for a student."),
    ("FREELANCER", "Freelancer", "Independent contractor engaged per assignment."),
)

# (code, name, country, state, city, address, timezone)
LOCATIONS: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    (
        "HYD",
        "Hyderabad HQ",
        "India",
        "Telangana",
        "Hyderabad",
        "Plot 12, HITEC City, Madhapur, Hyderabad 500081",
        "Asia/Kolkata",
    ),
    (
        "BLR",
        "Bengaluru Office",
        "India",
        "Karnataka",
        "Bengaluru",
        "Level 4, Outer Ring Road, Bellandur, Bengaluru 560103",
        "Asia/Kolkata",
    ),
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
async def _existing_codes(session: AsyncSession, model: type[Base]) -> set[str]:
    """Codes already present, compared case-insensitively like the DB index."""
    rows = (await session.execute(select(func.lower(model.code)))).scalars().all()  # type: ignore[attr-defined]
    return set(rows)


async def _seed_codeless_teams(
    session: AsyncSession,
    business_unit_ids: dict[str, uuid.UUID],
    actor_id: uuid.UUID | None,
) -> int:
    """Teams are keyed by name within a business unit rather than by code."""
    created = 0
    for name, unit_code, description in TEAMS:
        business_unit_id = business_unit_ids.get(unit_code)
        if business_unit_id is None:
            continue

        exists = (
            (
                await session.execute(
                    select(Team.id).where(
                        Team.business_unit_id == business_unit_id,
                        func.lower(Team.name) == name.lower(),
                    )
                )
            )
            .scalars()
            .first()
        )
        if exists is not None:
            continue

        session.add(
            Team(
                name=name,
                business_unit_id=business_unit_id,
                description=description,
                status=RecordStatus.ACTIVE,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        created += 1

    await session.flush()
    return created


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
async def seed_organization_sample_data(
    session: AsyncSession, *, actor_id: uuid.UUID | None = None
) -> dict[str, int]:
    """Insert the sample hierarchy. Returns a count of rows created per entity."""
    audit = {"created_by": actor_id, "updated_by": actor_id}
    created: dict[str, int] = {}

    # -- Organization profile -----------------------------------------
    existing_org = (
        (
            await session.execute(
                select(Organization.id).where(
                    func.lower(Organization.registration_number)
                    == ORGANIZATION["registration_number"].lower()
                )
            )
        )
        .scalars()
        .first()
    )
    if existing_org is None:
        session.add(Organization(**ORGANIZATION, status=RecordStatus.ACTIVE, **audit))
        created["organizations"] = 1
    else:
        created["organizations"] = 0

    # -- Business units -------------------------------------------------
    known = await _existing_codes(session, BusinessUnit)
    created["business_units"] = 0
    for definition in BUSINESS_UNITS:
        if definition["code"].lower() in known:
            continue
        session.add(BusinessUnit(**definition, status=RecordStatus.ACTIVE, **audit))
        created["business_units"] += 1
    await session.flush()

    business_unit_ids: dict[str, uuid.UUID] = dict(
        row.tuple() for row in (await session.execute(select(BusinessUnit.code, BusinessUnit.id))).all()
    )

    # -- Teams -------------------------------------------------------------
    created["teams"] = await _seed_codeless_teams(session, business_unit_ids, actor_id)

    # -- Designations ------------------------------------------------------
    known = await _existing_codes(session, Designation)
    created["designations"] = 0
    for code, name, unit_code, level, description in DESIGNATIONS:
        if code.lower() in known or unit_code not in business_unit_ids:
            continue
        session.add(
            Designation(
                code=code,
                name=name,
                business_unit_id=business_unit_ids[unit_code],
                level=level,
                description=description,
                status=RecordStatus.ACTIVE,
                **audit,
            )
        )
        created["designations"] += 1

    # -- Grades -------------------------------------------------------------
    known = await _existing_codes(session, Grade)
    created["grades"] = 0
    for code, name, level, description in GRADES:
        if code.lower() in known:
            continue
        session.add(
            Grade(
                code=code,
                name=name,
                level=level,
                description=description,
                status=RecordStatus.ACTIVE,
                **audit,
            )
        )
        created["grades"] += 1

    # -- Employment types ----------------------------------------------------
    known = await _existing_codes(session, EmploymentType)
    created["employment_types"] = 0
    for code, name, description in EMPLOYMENT_TYPES:
        if code.lower() in known:
            continue
        session.add(
            EmploymentType(code=code, name=name, description=description, status=RecordStatus.ACTIVE, **audit)
        )
        created["employment_types"] += 1

    # -- Locations ------------------------------------------------------------
    known = await _existing_codes(session, Location)
    created["locations"] = 0
    for code, name, country, state, city, address, timezone in LOCATIONS:
        if code.lower() in known:
            continue
        session.add(
            Location(
                code=code,
                name=name,
                country=country,
                state=state,
                city=city,
                address=address,
                timezone=timezone,
                status=RecordStatus.ACTIVE,
                **audit,
            )
        )
        created["locations"] += 1

    await session.flush()

    logger.info("Organization sample data seeded", extra={"rows_created": created})
    return created
