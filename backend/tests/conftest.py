"""Shared pytest fixtures.

Two tiers of tests live side by side:

* **Unit tests** exercise pure logic (security primitives, schema validation,
  helpers) and need nothing external. They always run.
* **Integration tests** exercise the real HTTP stack against a real PostgreSQL
  database. The schema is built by running the *actual Alembic migrations*, so
  every test run also proves the migration chain applies cleanly.

If the test database is unreachable the integration fixtures skip rather than
fail, so ``pytest`` is still useful on a fresh clone with no database.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Configure the environment before any application module is imported.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-definitely-long-enough-for-validation")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("SMTP_HOST", "")
os.environ.setdefault("MAX_FAILED_LOGIN_ATTEMPTS", "3")
os.environ.setdefault("BCRYPT_ROUNDS", "4")

BACKEND_DIR = Path(__file__).resolve().parents[1]

from app.api.deps import get_db_session  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.business_unit import BusinessUnit  # noqa: E402
from app.models.designation import Designation  # noqa: E402
from app.models.employee import Employee  # noqa: E402
from app.models.employment_type import EmploymentType  # noqa: E402
from app.models.enums import EmploymentStatus, RecordStatus  # noqa: E402
from app.models.grade import Grade  # noqa: E402
from app.models.location import Location  # noqa: E402
from app.models.team import Team  # noqa: E402
from app.models.user import User  # noqa: E402
from app.utils.datetime import utc_now  # noqa: E402

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    f"{settings.sqlalchemy_database_uri}_test",
)

TEST_USER_EMAIL = "test.user@example.com"
TEST_USER_PASSWORD = "Test@Password123"


# ----------------------------------------------------------------------
# Database lifecycle
# ----------------------------------------------------------------------
def _alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


async def _probe_connection(url: str) -> None:
    """Open and close a single connection, raising if the server is unreachable."""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect():
            pass
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Verify the test database is reachable, then build its schema.

    Deliberately synchronous: a session-scoped *async* fixture would need its
    own session-scoped event loop, which conflicts with the per-test loop the
    request fixtures use. ``asyncio.run`` gives us the one-off probe without
    dragging a second loop scope into the suite.

    The schema is built with ``alembic upgrade head`` -- the same command used
    in production -- so a broken migration fails the test suite.
    """
    try:
        asyncio.run(_probe_connection(TEST_DATABASE_URL))
    except (SQLAlchemyError, OSError) as exc:
        pytest.skip(
            "Test database unavailable at "
            f"{TEST_DATABASE_URL.rsplit('@', 1)[-1]} ({type(exc).__name__}). "
            "Create it with: createdb jsan_people360_test",
            allow_module_level=True,
        )

    config = _alembic_config(TEST_DATABASE_URL)
    command.upgrade(config, "head")

    yield TEST_DATABASE_URL

    command.downgrade(config, "base")


@pytest.fixture
async def db_session(database_url: str) -> AsyncIterator[AsyncSession]:
    """A session bound to an outer transaction that is rolled back after each test.

    Nothing a test writes survives it, so tests stay independent and ordering
    never matters.
    """
    engine = create_async_engine(database_url, poolclass=NullPool)
    connection = await engine.connect()
    transaction = await connection.begin()

    factory = async_sessionmaker(bind=connection, expire_on_commit=False, autoflush=False)
    session = factory()

    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


# ----------------------------------------------------------------------
# HTTP client
# ----------------------------------------------------------------------
@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired to the app with the test session injected.

    Overriding ``get_db_session`` means requests join the test's transaction, so
    assertions can read what an endpoint wrote and everything rolls back after.
    """

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    fastapi_app.dependency_overrides[get_db_session] = _override_session

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client

    fastapi_app.dependency_overrides.clear()


# ----------------------------------------------------------------------
# Domain fixtures
# ----------------------------------------------------------------------
@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """An active account with a known password.

    A superuser since RBAC landed. This fixture exists so a module's tests can
    exercise *that module*, and the alternative -- granting it whichever roles
    each suite happens to need -- would make every test partly a permissions
    test and would quietly stop covering the endpoint whenever a grant drifted.
    Permissions have their own suite, in ``test_rbac.py``, where the accounts
    are deliberately narrow.
    """
    user = User(
        email=TEST_USER_EMAIL,
        username="test.user",
        first_name="Test",
        last_name="User",
        hashed_password=hash_password(TEST_USER_PASSWORD),
        is_active=True,
        is_superuser=True,
        password_changed_at=utc_now(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def inactive_user(db_session: AsyncSession) -> User:
    """A deactivated account, used to assert sign-in is refused."""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"inactive.{suffix}@example.com",
        username=f"inactive.{suffix}",
        first_name="Inactive",
        last_name="User",
        hashed_password=hash_password(TEST_USER_PASSWORD),
        is_active=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def business_unit(db_session: AsyncSession) -> BusinessUnit:
    """A live, active business unit -- the root of the master-data hierarchy."""
    record = BusinessUnit(name="Technology Services", code="TECH", status=RecordStatus.ACTIVE)
    db_session.add(record)
    await db_session.flush()
    return record


@pytest.fixture
async def team(db_session: AsyncSession, business_unit: BusinessUnit) -> Team:
    record = Team(
        name="Platform Engineering",
        business_unit_id=business_unit.id,
        status=RecordStatus.ACTIVE,
    )
    db_session.add(record)
    await db_session.flush()
    return record


@pytest.fixture
async def designation(db_session: AsyncSession, business_unit: BusinessUnit) -> Designation:
    record = Designation(
        name="Software Engineer",
        code="SE",
        business_unit_id=business_unit.id,
        level=2,
        status=RecordStatus.ACTIVE,
    )
    db_session.add(record)
    await db_session.flush()
    return record


@pytest.fixture
async def grade(db_session: AsyncSession) -> Grade:
    record = Grade(name="Grade 2", code="G2", level=2, status=RecordStatus.ACTIVE)
    db_session.add(record)
    await db_session.flush()
    return record


@pytest.fixture
async def location(db_session: AsyncSession) -> Location:
    record = Location(
        name="Hyderabad Office",
        code="HYD",
        country="India",
        state="Telangana",
        city="Hyderabad",
        address="Hitec City",
        timezone="Asia/Kolkata",
        status=RecordStatus.ACTIVE,
    )
    db_session.add(record)
    await db_session.flush()
    return record


@pytest.fixture
async def employment_type(db_session: AsyncSession) -> EmploymentType:
    record = EmploymentType(name="Full Time", code="FT", status=RecordStatus.ACTIVE)
    db_session.add(record)
    await db_session.flush()
    return record


@pytest.fixture
async def employee(db_session: AsyncSession, business_unit: BusinessUnit, team: Team) -> Employee:
    """A live employee on probation, placed in a team but nothing else set.

    Deliberately sparse: most tests are about what happens when something
    changes, and a fully populated fixture makes it harder to see which field
    the assertion is really about.
    """
    suffix = uuid.uuid4().hex[:8]
    record = Employee(
        first_name="Priya",
        last_name="Sharma",
        official_email=f"priya.{suffix}@jsan.example",
        joining_date=date(2026, 1, 15),
        business_unit_id=business_unit.id,
        team_id=team.id,
        employment_status=EmploymentStatus.PROBATION,
    )
    db_session.add(record)
    await db_session.flush()
    return record


@pytest.fixture
async def auth_headers(client: AsyncClient, test_user: User) -> dict[str, str]:
    """Authorization header for ``test_user``, obtained through a real sign-in."""
    response = await client.post(
        f"{settings.API_V1_PREFIX}/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
    )
    assert response.status_code == 200, response.text
    token = response.json()["data"]["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
