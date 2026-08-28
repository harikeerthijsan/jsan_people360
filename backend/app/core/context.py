"""Request-scoped context.

Contextvars let cross-cutting concerns (logging, auditing) read the current
request id / actor without threading them through every function signature.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
_actor_id_ctx: ContextVar[uuid.UUID | None] = ContextVar("actor_id", default=None)
_client_ip_ctx: ContextVar[str | None] = ContextVar("client_ip", default=None)
_user_agent_ctx: ContextVar[str | None] = ContextVar("user_agent", default=None)


def set_request_id(request_id: str) -> Token[str | None]:
    return _request_id_ctx.set(request_id)


def get_request_id() -> str | None:
    return _request_id_ctx.get()


def set_actor_id(actor_id: uuid.UUID | None) -> Token[uuid.UUID | None]:
    return _actor_id_ctx.set(actor_id)


def get_actor_id() -> uuid.UUID | None:
    return _actor_id_ctx.get()


def set_client_ip(value: str | None) -> Token[str | None]:
    return _client_ip_ctx.set(value)


def get_client_ip() -> str | None:
    return _client_ip_ctx.get()


def set_user_agent(value: str | None) -> Token[str | None]:
    return _user_agent_ctx.set(value)


def get_user_agent() -> str | None:
    return _user_agent_ctx.get()


def reset_request_context(
    request_id_token: Token[str | None],
    client_ip_token: Token[str | None],
    user_agent_token: Token[str | None],
) -> None:
    _request_id_ctx.reset(request_id_token)
    _client_ip_ctx.reset(client_ip_token)
    _user_agent_ctx.reset(user_agent_token)
