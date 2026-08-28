"""Unit tests for the cryptographic primitives."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.core.exceptions import InvalidTokenError
from app.core.security import (
    MAX_PASSWORD_BYTES,
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    get_subject_id,
    hash_opaque_token,
    hash_password,
    tokens_match,
    verify_password,
)

pytestmark = pytest.mark.unit


class TestPasswordHashing:
    def test_hash_is_not_the_plaintext(self) -> None:
        hashed = hash_password("Correct@Horse1")
        assert hashed != "Correct@Horse1"
        assert hashed.startswith("$2b$")

    def test_hashes_are_salted(self) -> None:
        """The same password must never produce the same hash twice."""
        assert hash_password("Correct@Horse1") != hash_password("Correct@Horse1")

    def test_verify_accepts_the_right_password(self) -> None:
        assert verify_password("Correct@Horse1", hash_password("Correct@Horse1"))

    def test_verify_rejects_the_wrong_password(self) -> None:
        assert not verify_password("Wrong@Horse1", hash_password("Correct@Horse1"))

    def test_verify_rejects_a_malformed_hash_without_raising(self) -> None:
        assert not verify_password("Correct@Horse1", "not-a-bcrypt-hash")

    def test_rejects_passwords_beyond_the_bcrypt_limit(self) -> None:
        with pytest.raises(ValueError, match="exceed"):
            hash_password("a" * (MAX_PASSWORD_BYTES + 1))


class TestOpaqueTokens:
    def test_tokens_are_unique(self) -> None:
        assert generate_opaque_token() != generate_opaque_token()

    def test_hash_is_stable(self) -> None:
        token = generate_opaque_token()
        assert hash_opaque_token(token) == hash_opaque_token(token)

    def test_hash_is_a_sha256_digest(self) -> None:
        assert len(hash_opaque_token(generate_opaque_token())) == 64

    def test_tokens_match_compares_against_the_digest(self) -> None:
        token = generate_opaque_token()
        assert tokens_match(token, hash_opaque_token(token))
        assert not tokens_match(generate_opaque_token(), hash_opaque_token(token))


class TestAccessTokens:
    def test_round_trip_preserves_the_subject(self) -> None:
        user_id = uuid.uuid4()
        token, _ = create_access_token(user_id)
        assert get_subject_id(decode_access_token(token)) == user_id

    def test_expiry_is_returned_alongside_the_token(self) -> None:
        token, expires_at = create_access_token(uuid.uuid4())
        assert decode_access_token(token)["exp"] == int(expires_at.timestamp())

    def test_extra_claims_are_carried(self) -> None:
        token, _ = create_access_token(uuid.uuid4(), extra_claims={"email": "a@b.com"})
        assert decode_access_token(token)["email"] == "a@b.com"

    def test_expired_token_is_rejected(self) -> None:
        token, _ = create_access_token(uuid.uuid4(), expires_delta=timedelta(seconds=-10))
        with pytest.raises(InvalidTokenError):
            decode_access_token(token)

    def test_tampered_token_is_rejected(self) -> None:
        token, _ = create_access_token(uuid.uuid4())
        header, payload, signature = token.split(".")
        tampered = f"{header}.{payload}.{signature[:-2]}xy"
        with pytest.raises(InvalidTokenError):
            decode_access_token(tampered)

    def test_garbage_is_rejected(self) -> None:
        with pytest.raises(InvalidTokenError):
            decode_access_token("not.a.jwt")

    def test_malformed_subject_is_rejected(self) -> None:
        with pytest.raises(InvalidTokenError):
            get_subject_id({"sub": "not-a-uuid"})


# ----------------------------------------------------------------------
# Cross-boundary: the client may only gate on permissions that exist
# ----------------------------------------------------------------------
class TestFrontendGatesOnRealPermissions:
    """Every permission the sidebar names must exist in the catalogue.

    The client's permission check is plain set membership with no superuser
    bypass, so a menu item gated on a permission nobody can hold is a screen
    nobody can reach -- including Super Admin. That is not a security hole; it
    is worse in one specific way, because it fails *closed* and silently, and a
    working feature simply appears not to exist.

    This audit found eight HR items in exactly that state, asking for
    `attendance:view_all`, `leave:view_all` and four others that the backend
    deliberately does not define -- ``employees:view_all`` is the platform's
    only scoping permission, for the reasons ``require_org_wide`` gives.

    The test lives on the backend because the backend owns the catalogue, and
    it reads the client's source rather than mirroring it, so the two cannot
    drift apart quietly.
    """

    @staticmethod
    def _navigation_permissions() -> set[str]:
        import re

        from app.core.config import PROJECT_ROOT

        navigation = PROJECT_ROOT / "frontend" / "src" / "config" / "navigation.ts"
        if not navigation.exists():  # pragma: no cover - frontend absent
            pytest.skip("frontend source not present")
        text = navigation.read_text(encoding="utf-8")
        # Only inside `permission:`, `anyOf:` and `allOf:` -- a bare colon-string
        # elsewhere in the file is a CSS class, not a permission.
        gates = re.findall(r"(?:permission|anyOf|allOf):\s*(\[[^\]]*\]|'[^']*')", text)
        return set(re.findall(r"'([^']+)'", " ".join(gates)))

    def test_the_sidebar_names_no_permission_that_does_not_exist(self) -> None:
        from app.core.permissions import ALL_PERMISSIONS

        referenced = self._navigation_permissions()
        assert referenced, "no permission strings found; the parser has drifted from the file"

        unknown = sorted(referenced - ALL_PERMISSIONS)
        assert not unknown, (
            "the sidebar gates on permissions the backend does not define, so those items "
            f"can never be shown to anybody: {unknown}"
        )
