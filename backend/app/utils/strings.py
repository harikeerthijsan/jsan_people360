"""Small, dependency-free string helpers."""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def normalise_email(email: str) -> str:
    """Lower-case and trim an email address.

    Email local parts are technically case sensitive, but no mainstream
    provider treats them that way and case-preserving storage is a reliable
    source of duplicate-account bugs.
    """
    return email.strip().lower()


def collapse_whitespace(value: str) -> str:
    """Trim and collapse internal runs of whitespace to a single space."""
    return _WHITESPACE.sub(" ", value).strip()


def slugify(value: str) -> str:
    """ASCII, lower-case, hyphen-separated slug."""
    normalised = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return _NON_SLUG.sub("-", normalised.lower()).strip("-")


def mask_email(email: str) -> str:
    """Partially obscure an email for safe inclusion in logs.

    ``jane.doe@example.com`` -> ``j******e@example.com``
    """
    local, separator, domain = email.partition("@")
    if not separator or len(local) <= 2:
        return "***" + separator + domain
    return f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}@{domain}"


def truncate(value: str | None, max_length: int) -> str | None:
    """Truncate a value to fit a database column without raising."""
    if value is None:
        return None
    return value if len(value) <= max_length else value[: max_length - 1] + "…"
