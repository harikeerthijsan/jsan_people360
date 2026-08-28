"""Unit tests for the request session's failure-path transaction decision.

The request session rolls back on failure — except for security bookkeeping:
an authentication refusal must keep the failed-attempt counter, lockout and
token revocations it wrote before refusing, or the refusal enforces nothing.
"""

from __future__ import annotations

import pytest

from app.api import deps
from app.core.exceptions import (
    AccountInactiveError,
    AccountLockedError,
    AuthenticationError,
    InvalidCredentialsError,
    InvalidTokenError,
    NotFoundError,
    PermissionDeniedError,
)

pytestmark = pytest.mark.unit


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_session(monkeypatch: pytest.MonkeyPatch) -> _FakeSession:
    session = _FakeSession()
    monkeypatch.setattr(deps, "SessionFactory", lambda: session)
    return session


async def _fail_request(exc: Exception) -> None:
    """Open the dependency, then throw ``exc`` into it as a failing route would."""
    generator = deps.get_db_session()
    await anext(generator)
    with pytest.raises(type(exc)):
        await generator.athrow(exc)


async def test_commits_on_normal_completion(fake_session: _FakeSession) -> None:
    generator = deps.get_db_session()
    await anext(generator)
    with pytest.raises(StopAsyncIteration):
        await anext(generator)
    assert fake_session.committed
    assert not fake_session.rolled_back
    assert fake_session.closed


async def test_rolls_back_on_ordinary_failure(fake_session: _FakeSession) -> None:
    await _fail_request(NotFoundError("Employee"))
    assert fake_session.rolled_back
    assert not fake_session.committed
    assert fake_session.closed


async def test_permission_denied_still_rolls_back(fake_session: _FakeSession) -> None:
    """A 403 can interrupt a service mid-write; those writes must not survive."""
    await _fail_request(PermissionDeniedError())
    assert fake_session.rolled_back
    assert not fake_session.committed


async def test_authentication_failures_keep_their_bookkeeping(fake_session: _FakeSession) -> None:
    await _fail_request(InvalidCredentialsError())
    assert fake_session.committed
    assert not fake_session.rolled_back
    assert fake_session.closed


def test_every_authentication_error_preserves_writes() -> None:
    """The flag rides the base class so a new auth failure cannot forget it."""
    for exc_type in (
        AuthenticationError,
        InvalidCredentialsError,
        InvalidTokenError,
        AccountLockedError,
        AccountInactiveError,
    ):
        assert exc_type.preserve_writes
    assert not PermissionDeniedError.preserve_writes
