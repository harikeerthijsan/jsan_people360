"""Application configuration.

All runtime configuration is sourced from environment variables (optionally
loaded from a local ``.env`` file) and validated by Pydantic v2. Nothing in the
codebase should read ``os.environ`` directly -- always go through
:func:`get_settings`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import EmailStr, Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent

Environment = Literal["local", "development", "staging", "production", "test"]
LogFormat = Literal["json", "console"]
SameSite = Literal["lax", "strict", "none"]


def normalise_database_url(url: str) -> str:
    """Rewrite a platform-issued PostgreSQL URL into the async SQLAlchemy form."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix) :]
            break
    if "sslmode=" in url:
        head, _, query = url.partition("?")
        params = [part for part in query.split("&") if part and not part.startswith("sslmode=")]
        mode = next((part.split("=", 1)[1] for part in query.split("&") if part.startswith("sslmode=")), "")
        if mode and mode != "disable":
            params.append("ssl=require")
        url = head + ("?" + "&".join(params) if params else "")
    return url


class Settings(BaseSettings):
    """Strongly typed application settings."""

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_NAME: str = "JSAN People360"
    APP_ENV: Environment = "local"
    APP_VERSION: str = "0.1.0"
    # Use a product-specific name. Generic DEBUG is commonly injected by IDEs,
    # package managers and hosting platforms with non-boolean values such as
    # "release", which must not prevent the API from starting.
    JP360_DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ------------------------------------------------------------------
    # Security / JWT
    # ------------------------------------------------------------------
    SECRET_KEY: str = Field(
        min_length=32,
        description="Signs access tokens. Must be unique per environment.",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "jsan-people360"
    JWT_AUDIENCE: str = "jsan-people360-api"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, ge=1, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=90)
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=5, le=1440)

    MAX_FAILED_LOGIN_ATTEMPTS: int = Field(default=5, ge=1, le=100)
    ACCOUNT_LOCKOUT_MINUTES: int = Field(default=15, ge=1, le=1440)
    BCRYPT_ROUNDS: int = Field(default=12, ge=4, le=16)

    # ------------------------------------------------------------------
    # Refresh token cookie
    # ------------------------------------------------------------------
    REFRESH_COOKIE_NAME: str = "jp360_refresh_token"
    REFRESH_COOKIE_PATH: str = "/api/v1/auth"
    COOKIE_DOMAIN: str | None = None
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: SameSite = "lax"

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    # S105 suppressed: a placeholder default for a fresh local install, not a
    # credential. Every deployed environment supplies its own value.
    POSTGRES_PASSWORD: str = "postgres"  # noqa: S105
    POSTGRES_DB: str = "jsan_people360"
    DATABASE_URL: str | None = Field(
        default=None,
        description="Full SQLAlchemy async DSN. When omitted it is assembled from the POSTGRES_* values.",
    )
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
    DB_POOL_TIMEOUT: int = Field(default=30, ge=1, le=300)
    DB_POOL_RECYCLE: int = Field(default=1800, ge=60)

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ------------------------------------------------------------------
    # Trusted hosts
    #
    # Empty means "answer to any Host header", which is right on a laptop and
    # wrong on the internet: the Host is reflected into password-reset links, so
    # a forged one sends a working reset token to an attacker's domain.
    # Production refuses to start without this set.
    # ------------------------------------------------------------------
    TRUSTED_HOSTS: str = ""

    # ------------------------------------------------------------------
    # Request limits
    #
    # The rate limit applies only to the credential endpoints; see
    # app/middleware/rate_limit.py for why, and for what it does not protect
    # against in a multi-worker deployment.
    # ------------------------------------------------------------------
    RATE_LIMIT_ENABLED: bool = True
    #: Counted per client address, and only *failed* attempts -- a successful
    #: sign-in clears the slate. Sized so a shared office address running on one
    #: NAT gateway is never affected while a guessing client trips quickly.
    RATE_LIMIT_ATTEMPTS: int = Field(default=20, ge=1, le=1000)
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=300, ge=1, le=3600)
    RATE_LIMIT_MAX_TRACKED_CLIENTS: int = Field(default=10_000, ge=100)
    MAX_REQUEST_BODY_MB: int = Field(default=12, ge=1, le=1024)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: LogFormat = "console"
    LOG_REQUEST_BODY: bool = False

    # ------------------------------------------------------------------
    # Uploads
    # ------------------------------------------------------------------
    UPLOAD_DIR: str = str(PROJECT_ROOT / "uploads")
    MAX_UPLOAD_SIZE_MB: int = Field(default=10, ge=1, le=1024)

    # ------------------------------------------------------------------
    # Outbound mail (password reset). When SMTP_HOST is unset, mail is logged.
    # ------------------------------------------------------------------
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_TLS: bool = True
    EMAIL_FROM: EmailStr = "no-reply@example.com"
    EMAIL_FROM_NAME: str = "JSAN People360"

    # ------------------------------------------------------------------
    # Frontend
    # ------------------------------------------------------------------
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # ------------------------------------------------------------------
    # Bootstrap administrator (development convenience only)
    #
    # Typed as EmailStr so a misconfigured address fails at start-up rather
    # than producing an account nobody can sign in to. Note that reserved
    # domains such as `.local`, `.test` and bare `localhost` are *not* valid
    # email domains and will be rejected here.
    # ------------------------------------------------------------------
    DEFAULT_ADMIN_EMAIL: EmailStr = "admin@example.com"
    # S105 suppressed: a documented development bootstrap credential, intended
    # to be replaced. The seed command warns when it runs against production.
    DEFAULT_ADMIN_PASSWORD: str = "Admin@12345"  # noqa: S105
    DEFAULT_ADMIN_NAME: str = "System Administrator"

    # ------------------------------------------------------------------
    # Validators / derived values
    # ------------------------------------------------------------------
    @field_validator("LOG_LEVEL")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        normalised = value.upper()
        if normalised not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return normalised

    @field_validator("API_V1_PREFIX", "REFRESH_COOKIE_PATH")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("Path values must start with '/'")
        return value.rstrip("/") or "/"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins(self) -> list[str]:
        """CORS origins parsed from the comma separated environment value."""
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_uri(self) -> str:
        """Async DSN used by the application engine.

        Hosting platforms (Railway, Heroku, Render, Supabase) hand out plain
        ``postgresql://`` or ``postgres://`` URLs, sometimes with a libpq
        ``sslmode`` parameter. SQLAlchemy needs the ``+asyncpg`` driver marker
        and asyncpg needs ``ssl=`` instead, so a pasted platform URL is
        translated here rather than at every deployment.
        """
        if self.DATABASE_URL:
            return normalise_database_url(self.DATABASE_URL)
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are disabled in production."""
        return not self.is_production

    @computed_field  # type: ignore[prop-decorator]
    @property
    def debug(self) -> bool:
        """Whether exception details may be included in local error responses."""
        return self.JP360_DEBUG

    @computed_field  # type: ignore[prop-decorator]
    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @computed_field  # type: ignore[prop-decorator]
    @property
    def max_request_body_bytes(self) -> int:
        """Outer bound on any request body.

        Deliberately larger than ``max_upload_size_bytes``: a multipart upload
        carries the file plus its form fields and boundaries, so a limit equal
        to the file limit would reject a file of exactly the permitted size.
        """
        return self.MAX_REQUEST_BODY_MB * 1024 * 1024

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trusted_hosts(self) -> list[str]:
        """Host headers the application will answer to.

        Empty means "any", which is correct behind a load balancer that has
        already validated it and wrong anywhere else -- so production requires
        it to be set, in :meth:`_reject_unsafe_production_configuration`.
        """
        return [host.strip() for host in self.TRUSTED_HOSTS.split(",") if host.strip()]

    # ------------------------------------------------------------------
    # Production safety
    # ------------------------------------------------------------------
    @model_validator(mode="after")
    def _reject_unsafe_production_configuration(self) -> Settings:
        """Refuse to start a production process that is configured unsafely.

        Every item below is a setting whose *default* is right for a laptop and
        wrong for the internet. Documenting them in a checklist has one failure
        mode -- somebody deploys without reading it -- and the consequence is
        silent: a service that starts, serves traffic, and sends its session
        cookie over plain HTTP.

        Failing at start-up is deliberately noisy. A container that will not
        boot is a deployment that gets fixed; a container that boots insecurely
        is an incident three months later.

        This runs only when ``APP_ENV=production``. Local, test, development and
        staging environments are untouched, so nothing here can make the test
        suite or a developer's machine harder to work with.
        """
        if self.APP_ENV != "production":
            return self

        problems: list[str] = []

        if self.SECRET_KEY in _WEAK_SECRETS or len(set(self.SECRET_KEY)) < 8:
            problems.append(
                "SECRET_KEY is a placeholder or has too little entropy. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(64))"'
            )
        if self.JP360_DEBUG:
            problems.append("JP360_DEBUG must be false in production; it puts exception detail in responses.")
        if not self.COOKIE_SECURE:
            problems.append(
                "COOKIE_SECURE must be true in production, or the refresh cookie travels in clear."
            )
        if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
            problems.append("COOKIE_SAMESITE=none requires COOKIE_SECURE=true.")
        if self.LOG_REQUEST_BODY:
            problems.append("LOG_REQUEST_BODY must be false in production; bodies carry credentials.")
        if self.DEFAULT_ADMIN_PASSWORD == _DOCUMENTED_ADMIN_PASSWORD:
            problems.append(
                "DEFAULT_ADMIN_PASSWORD is still the documented development credential. "
                "Change it, or unset it if the bootstrap account already exists."
            )
        if self.POSTGRES_PASSWORD == _LOCAL_DB_PASSWORD and not self.DATABASE_URL:
            problems.append("POSTGRES_PASSWORD is still the local default.")
        if not self.trusted_hosts:
            problems.append(
                "TRUSTED_HOSTS must name the hostnames this API answers to, or a forged Host "
                "header can be reflected into password-reset links."
            )

        bad_origins = [
            origin
            for origin in self.cors_origins
            if origin == "*" or "localhost" in origin or "127.0.0.1" in origin
        ]
        if bad_origins:
            problems.append(
                f"BACKEND_CORS_ORIGINS contains development or wildcard origins: {bad_origins}. "
                "Credentials are sent with CORS requests, so this is an account-takeover path."
            )
        if not self.cors_origins:
            problems.append("BACKEND_CORS_ORIGINS must name the real frontend origin.")

        if problems:
            listed = "\n  - ".join(problems)
            raise ValueError(
                "Refusing to start: this process has APP_ENV=production but is configured "
                f"for development.\n  - {listed}\n"
                "See docs/EnvironmentVariables.md#production-checklist."
            )
        return self


#: Values that must never sign a production token. Not an exhaustive list of bad
#: keys -- entropy is checked separately -- but these are the ones a copied
#: ``.env.example`` actually contains.
_WEAK_SECRETS: frozenset[str] = frozenset(
    {
        "change-me",
        "changeme",
        "secret",
        "development-secret-key-change-me-in-production",
        "replace-this-with-a-64-character-random-string-generated-by-secrets",
    }
)

#: The credential printed in the README. Kept as a constant so the check and the
#: documentation cannot drift apart.
_DOCUMENTED_ADMIN_PASSWORD = "Admin@12345"  # noqa: S105

#: The local default, compared against rather than used. Same reasoning as above.
_LOCAL_DB_PASSWORD = "postgres"  # noqa: S105


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


settings = get_settings()
