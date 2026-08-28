"""Development data seeding.

Creates the bootstrap administrator and the baseline application settings.
Idempotent: running it repeatedly is safe and never overwrites operator edits.

Usage (from ``backend/``)::

    python -m app.cli.seed

This is *seeding*, not *migrating* — it inserts rows into a schema that Alembic
has already created. Run ``alembic upgrade head`` first.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli.seed_documents import seed_document_masters
from app.cli.seed_organization import seed_organization_sample_data
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.db.session import session_scope
from app.models.app_setting import AppSetting
from app.models.user import User
from app.schemas.user import PASSWORD_MIN_LENGTH
from app.utils.datetime import utc_now
from app.utils.strings import normalise_email

logger = get_logger("cli.seed")

# Baseline runtime settings. ``is_editable=False`` marks values the platform
# itself depends on, which operators must not remove.
DEFAULT_SETTINGS: tuple[dict[str, Any], ...] = (
    {
        "key": "company.name",
        "value": "JSAN Technologies",
        "category": "company",
        "description": "Legal name shown in the application header and on documents.",
        "is_public": True,
    },
    {
        "key": "company.timezone",
        "value": "Asia/Kolkata",
        "category": "company",
        "description": "Default timezone for date display and scheduling.",
        "is_public": True,
    },
    {
        "key": "company.date_format",
        "value": "dd MMM yyyy",
        "category": "localisation",
        "description": "Default date presentation format.",
        "is_public": True,
    },
    {
        "key": "company.currency",
        "value": "INR",
        "category": "localisation",
        "description": "Default currency code (ISO 4217).",
        "is_public": True,
    },
    {
        "key": "security.password_min_length",
        # Bound to the constant the schemas actually enforce, so an operator
        # reading this setting is never told a different number to the one the
        # API applies.
        "value": PASSWORD_MIN_LENGTH,
        "category": "security",
        "description": "Minimum password length enforced at registration and reset.",
        "is_public": False,
        "is_editable": False,
    },
    {
        "key": "security.session_idle_minutes",
        "value": 30,
        "category": "security",
        "description": "Minutes of inactivity before the web client signs the user out.",
        "is_public": False,
    },
    {
        "key": "platform.onboarding_complete",
        "value": False,
        "category": "platform",
        "description": "Set once the initial platform configuration wizard has been completed.",
        "is_public": False,
    },
)


async def seed_admin_user(session: AsyncSession, *, force_password_reset: bool = False) -> User:
    """Create the bootstrap administrator if it does not already exist."""
    email = normalise_email(settings.DEFAULT_ADMIN_EMAIL)
    existing = (await session.execute(select(User).where(User.email == email))).scalars().first()

    if existing is not None:
        if force_password_reset:
            existing.hashed_password = hash_password(settings.DEFAULT_ADMIN_PASSWORD)
            existing.password_changed_at = utc_now()
            existing.failed_login_attempts = 0
            existing.locked_until = None
            logger.warning("Reset the bootstrap administrator password", extra={"user_id": str(existing.id)})
        else:
            logger.info(
                "Bootstrap administrator already exists; skipping", extra={"user_id": str(existing.id)}
            )
        return existing

    # The configured name is a single string, so it is split the same way the
    # user-management migration splits legacy names: first token, then the rest.
    first_name, _, remainder = settings.DEFAULT_ADMIN_NAME.strip().partition(" ")
    last_name = remainder.strip() or first_name

    admin = User(
        email=email,
        username=email.split("@", 1)[0],
        first_name=first_name,
        last_name=last_name,
        hashed_password=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
        is_active=True,
        is_superuser=True,
        email_verified_at=utc_now(),
        password_changed_at=utc_now(),
    )
    session.add(admin)
    await session.flush()

    # Self-attribution: the bootstrap account is its own creator.
    admin.created_by = admin.id
    admin.updated_by = admin.id
    await session.flush()

    logger.info("Bootstrap administrator created", extra={"user_id": str(admin.id), "email": email})
    return admin


async def seed_app_settings(session: AsyncSession, *, actor_id: Any = None) -> int:
    """Insert any missing baseline settings. Existing rows are left untouched."""
    existing_keys = set((await session.execute(select(AppSetting.key))).scalars().all())

    created = 0
    for definition in DEFAULT_SETTINGS:
        if definition["key"] in existing_keys:
            continue
        session.add(
            AppSetting(
                key=definition["key"],
                value=definition["value"],
                category=definition["category"],
                description=definition["description"],
                is_public=definition.get("is_public", False),
                is_editable=definition.get("is_editable", True),
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        created += 1

    await session.flush()
    # NOTE: `created` / `message` / `module` etc. are reserved LogRecord attribute
    # names -- passing them via `extra` raises KeyError. Always namespace the keys.
    logger.info(
        "Application settings seeded",
        extra={"settings_created": created, "settings_skipped": len(DEFAULT_SETTINGS) - created},
    )
    return created


async def run(*, force_password_reset: bool = False, sample_data: bool = False) -> None:
    """Seed everything inside a single transaction."""
    async with session_scope() as session:
        admin = await seed_admin_user(session, force_password_reset=force_password_reset)
        await seed_app_settings(session, actor_id=admin.id)

        # Not behind --sample-data: the document vault cannot accept anything
        # until a category and a type exist, so these are part of a working
        # installation rather than demonstration data.
        await seed_document_masters(session)

        if sample_data:
            await seed_organization_sample_data(session, actor_id=admin.id)

    if settings.is_production:
        logger.warning(
            "Seeding ran in a production environment. Change the administrator password immediately."
        )
    else:
        logger.info(
            "Seeding complete. Sign in with the bootstrap administrator.",
            extra={"email": settings.DEFAULT_ADMIN_EMAIL},
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed JSAN People360 development data.")
    parser.add_argument(
        "--reset-admin-password",
        action="store_true",
        help="Reset the bootstrap administrator password to DEFAULT_ADMIN_PASSWORD.",
    )
    parser.add_argument(
        "--sample-data",
        action="store_true",
        help=(
            "Also insert a sample organization hierarchy (business units, teams, "
            "designations, grades, employment types, locations). "
            "Demonstration data only -- nothing in the product depends on it."
        ),
    )
    args = parser.parse_args()

    configure_logging()

    try:
        asyncio.run(run(force_password_reset=args.reset_admin_password, sample_data=args.sample_data))
    except SQLAlchemyError:
        logger.error(
            "Seeding failed. Is the database running and has 'alembic upgrade head' been applied?",
            exc_info=True,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
