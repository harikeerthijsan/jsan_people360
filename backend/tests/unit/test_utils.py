"""Unit tests for the shared helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.utils.datetime import ensure_utc, is_past, seconds_until, utc_now
from app.utils.strings import collapse_whitespace, mask_email, normalise_email, slugify, truncate

pytestmark = pytest.mark.unit


class TestStrings:
    def test_normalise_email(self) -> None:
        assert normalise_email("  Jane.Doe@Example.COM ") == "jane.doe@example.com"

    def test_collapse_whitespace(self) -> None:
        assert collapse_whitespace("  a   b \n c ") == "a b c"

    def test_slugify(self) -> None:
        assert slugify("Sénior Engineer (India)") == "senior-engineer-india"

    @pytest.mark.parametrize(
        ("email", "expected"),
        [
            ("jane.doe@example.com", "j******e@example.com"),
            ("ab@example.com", "***@example.com"),
            ("not-an-email", "***"),
        ],
    )
    def test_mask_email(self, email: str, expected: str) -> None:
        assert mask_email(email) == expected

    def test_truncate_leaves_short_values_alone(self) -> None:
        assert truncate("short", 10) == "short"

    def test_truncate_shortens_long_values(self) -> None:
        assert len(truncate("x" * 50, 10) or "") == 10

    def test_truncate_passes_through_none(self) -> None:
        assert truncate(None, 10) is None


class TestDatetime:
    def test_utc_now_is_timezone_aware(self) -> None:
        assert utc_now().tzinfo is not None

    def test_ensure_utc_attaches_utc_to_naive_values(self) -> None:
        naive = datetime(2026, 1, 1, 12, 0, 0)
        assert ensure_utc(naive) == datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def test_ensure_utc_converts_other_offsets(self) -> None:
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        assert (ensure_utc(aware) or aware).hour == 6

    def test_ensure_utc_passes_through_none(self) -> None:
        assert ensure_utc(None) is None

    def test_is_past(self) -> None:
        assert is_past(utc_now() - timedelta(seconds=1))
        assert not is_past(utc_now() + timedelta(minutes=5))
        assert not is_past(None)

    def test_seconds_until_is_never_negative(self) -> None:
        assert seconds_until(utc_now() - timedelta(hours=1)) == 0

    def test_seconds_until_counts_forward(self) -> None:
        assert 3500 <= seconds_until(utc_now() + timedelta(hours=1)) <= 3600


# ----------------------------------------------------------------------
# Configuration drift
# ----------------------------------------------------------------------
class TestEnvExampleMatchesTheSettings:
    """``.env.example`` is the deployment contract; drift makes it a lie.

    A setting that exists in code but not in the example is a knob an
    operator cannot find. One in the example but not in code is an
    instruction to set something that does nothing. Both are found the
    same way, and neither is worth discovering during a deploy.
    """

    @staticmethod
    def _documented() -> set[str]:
        import re

        from app.core.config import BACKEND_DIR

        text = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8")
        return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", text, re.M))

    def test_every_setting_is_documented(self) -> None:
        from app.core.config import Settings

        missing = sorted(set(Settings.model_fields) - self._documented())
        assert not missing, f"settings absent from .env.example: {missing}"

    def test_the_example_names_nothing_that_does_not_exist(self) -> None:
        from app.core.config import Settings

        stale = sorted(self._documented() - set(Settings.model_fields))
        assert not stale, f".env.example names settings that no longer exist: {stale}"
