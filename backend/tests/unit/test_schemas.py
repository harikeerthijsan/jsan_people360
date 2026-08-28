"""Unit tests for the validation boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, ResetPasswordRequest
from app.schemas.common import APIResponse, Page
from app.schemas.user import UserCreate

pytestmark = pytest.mark.unit


class TestLoginRequest:
    def test_email_is_normalised(self) -> None:
        assert LoginRequest(email="  Admin@Example.COM ", password="x").email == "admin@example.com"

    def test_invalid_email_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(email="not-an-email", password="x")

    def test_empty_password_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(email="a@b.com", password="")

    def test_remember_me_defaults_to_false(self) -> None:
        assert LoginRequest(email="a@b.com", password="x").remember_me is False


def _user_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "first_name": "Test",
        "last_name": "User",
        "username": "test.user",
        "email": "a@b.com",
        "password": "Str0ng@1",
    }
    payload.update(overrides)
    return payload


class TestPasswordPolicy:
    @pytest.mark.parametrize(
        ("password", "reason"),
        [
            ("Sh0rt@a", "shorter than the minimum of 8"),
            ("alllowercase@1", "no uppercase letter"),
            ("ALLUPPERCASE@1", "no lowercase letter"),
            ("NoDigitsHere@", "no digit"),
            ("NoSpecialChar1", "no special character"),
        ],
    )
    def test_weak_passwords_are_rejected(self, password: str, reason: str) -> None:
        with pytest.raises(ValidationError):
            UserCreate(**_user_payload(password=password))

    def test_an_eight_character_password_meeting_every_rule_is_accepted(self) -> None:
        assert UserCreate(**_user_payload(password="Str0ng@1")).password == "Str0ng@1"

    def test_name_whitespace_is_collapsed(self) -> None:
        user = UserCreate(**_user_payload(first_name="  Jane  ", last_name="Van   Doe "))
        assert user.first_name == "Jane"
        assert user.last_name == "Van Doe"

    def test_a_blank_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreate(**_user_payload(first_name="   "))


class TestResetPasswordRequest:
    def test_mismatched_confirmation_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="do not match"):
            ResetPasswordRequest(
                token="a" * 32,
                new_password="Str0ng@Password",
                confirm_password="Different@Password1",
            )

    def test_matching_confirmation_is_accepted(self) -> None:
        payload = ResetPasswordRequest(
            token="a" * 32,
            new_password="Str0ng@Password",
            confirm_password="Str0ng@Password",
        )
        assert payload.new_password == payload.confirm_password


class TestResponseEnvelope:
    def test_ok_produces_the_standard_shape(self) -> None:
        payload = APIResponse.ok({"id": 1}, message="Created").model_dump()
        assert payload == {
            "success": True,
            "message": "Created",
            "data": {"id": 1},
            "errors": None,
        }

    def test_default_message(self) -> None:
        assert APIResponse.ok().message == "Operation completed successfully"

    def test_every_envelope_has_all_four_keys(self) -> None:
        assert set(APIResponse.ok().model_dump()) == {"success", "message", "data", "errors"}


class TestPagination:
    def test_metadata_is_derived_correctly(self) -> None:
        page = Page.create([1, 2, 3], page=2, page_size=3, total_items=10)
        assert page.meta.total_pages == 4
        assert page.meta.has_next is True
        assert page.meta.has_previous is True

    def test_single_page_has_no_neighbours(self) -> None:
        page = Page.create([1], page=1, page_size=20, total_items=1)
        assert page.meta.total_pages == 1
        assert page.meta.has_next is False
        assert page.meta.has_previous is False

    def test_empty_result_set(self) -> None:
        page = Page.create([], page=1, page_size=20, total_items=0)
        assert page.meta.total_pages == 0
        assert page.meta.has_next is False
