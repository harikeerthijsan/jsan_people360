"""Async SQLAlchemy engine and session management.

IMPORTANT: the schema is owned exclusively by Alembic. ``Base.metadata.create_all``
is never called anywhere in this codebase -- every schema change ships as a
migration.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("db.session")


def create_engine() -> AsyncEngine:
    """Build the application-wide async engine."""
    return create_async_engine(
        settings.sqlalchemy_database_uri,
        echo=settings.DB_ECHO,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        future=True,
    )


engine: AsyncEngine = create_engine()

SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional scope for code outside the request lifecycle (CLI, jobs).

    Commits on success, rolls back on failure, always closes.
    """
    session = SessionFactory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def detached_session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional scope on its own dedicated connection.

    For writes that must survive the failure of the request around them — an
    audit entry describing a refusal — where the request session is about to
    roll back. It deliberately avoids the shared engine: pooled connections are
    bound to the event loop that created them, which the caller's loop need not
    be (the test suite runs one loop per test). The price is a connection
    handshake per call, acceptable for rare failure-path bookkeeping.
    """
    detached_engine = create_async_engine(settings.sqlalchemy_database_uri, poolclass=NullPool)
    try:
        session = AsyncSession(detached_engine, expire_on_commit=False, autoflush=False)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    finally:
        await detached_engine.dispose()


async def dispose_engine() -> None:
    """Release all pooled connections during application shutdown."""
    await engine.dispose()
    logger.info("Database connection pool disposed")
