"""The DATABASE_URL a hosting platform hands out is usable as pasted."""

from app.core.config import normalise_database_url


def test_plain_postgresql_scheme_gets_async_driver() -> None:
    assert normalise_database_url("postgresql://u:p@host:5432/db") == "postgresql+asyncpg://u:p@host:5432/db"


def test_legacy_postgres_scheme_gets_async_driver() -> None:
    assert normalise_database_url("postgres://u:p@host/db") == "postgresql+asyncpg://u:p@host/db"


def test_already_async_url_is_untouched() -> None:
    url = "postgresql+asyncpg://u:p@host/db"
    assert normalise_database_url(url) == url


def test_sslmode_is_translated_for_asyncpg() -> None:
    assert (
        normalise_database_url("postgresql://u:p@host/db?sslmode=require")
        == "postgresql+asyncpg://u:p@host/db?ssl=require"
    )


def test_sslmode_disable_is_dropped() -> None:
    assert normalise_database_url("postgresql://u:p@host/db?sslmode=disable&application_name=x") == (
        "postgresql+asyncpg://u:p@host/db?application_name=x"
    )
