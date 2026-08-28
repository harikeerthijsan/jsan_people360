"""Alembic environment.

The migration target metadata comes from ``app.db.base``, which imports every
model — so ``alembic revision --autogenerate`` always sees the complete schema.

The database URL comes from application settings rather than ``alembic.ini`` so
there is exactly one source of truth.
"""

from __future__ import annotations

import asyncio
import re
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Make the ``app`` package importable when Alembic is invoked from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Fall back to application settings, but never override a URL the caller has
# already supplied. The test suite sets it explicitly to point at the test
# database -- clobbering it here would migrate the *development* database
# instead, and the teardown would then drop it.
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_uri)

DATABASE_URL = config.get_main_option("sqlalchemy.url") or settings.sqlalchemy_database_uri

target_metadata = Base.metadata


# Tables owned by extensions rather than by this application. Autogenerate must
# not offer to drop them.
UNMANAGED_TABLES = frozenset({"spatial_ref_sys"})


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Ignore objects that are not managed by this application."""
    return not (type_ == "table" and name in UNMANAGED_TABLES)


_DEFAULT_CAST = re.compile(r"::[a-z_ ]+", re.IGNORECASE)
_DEFAULT_NOISE = re.compile(r"[\s()]+")


def _normalise_default(value: str | None) -> str | None:
    """Reduce a server default to a form that survives PostgreSQL's rewriting.

    PostgreSQL does not store a default as written. It reparses it and reports
    it back with explicit casts and extra parentheses, so
    ``'USR-' || lpad(nextval('users_user_code_seq')::text, 6, '0')`` comes back
    as ``('USR-'::text || lpad((nextval('users_user_code_seq'::regclass))::text,
    6, '0'::text))``. Comparing those as strings reports a difference on every
    run, which would make ``alembic check`` cry wolf and train people to ignore
    it.
    """
    if value is None:
        return None
    return _DEFAULT_NOISE.sub("", _DEFAULT_CAST.sub("", value)).lower()


def compare_server_default(
    context,
    inspected_column,
    metadata_column,
    inspected_default,
    metadata_default,
    rendered_metadata_default,
) -> bool | None:
    """Report a server-default difference only when there is a real one.

    Returning ``None`` defers to Alembic's own comparison, which is correct for
    ordinary literal defaults.
    """
    del context, inspected_column, metadata_column, metadata_default

    normalised_inspected = _normalise_default(inspected_default)
    normalised_metadata = _normalise_default(rendered_metadata_default)

    if normalised_inspected is not None and normalised_inspected == normalised_metadata:
        return False
    return None


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        # Detect column type changes and server-default changes in autogenerate.
        compare_type=True,
        compare_server_default=compare_server_default,
        include_object=include_object,
        # Render every constraint with its explicit name so downgrades work.
        render_as_batch=False,
        dialect_opts={"paramstyle": "named"},
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (``alembic upgrade head --sql``)."""
    _configure(url=DATABASE_URL)

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations against a live async connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
