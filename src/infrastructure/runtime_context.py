from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import NAMESPACE_URL, uuid4, uuid5

_correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    return _correlation_id_var.get()


def ensure_correlation_id(seed: str | None = None) -> str:
    current = get_correlation_id()
    if current:
        return current

    current = uuid5(NAMESPACE_URL, seed).hex if seed else uuid4().hex
    _correlation_id_var.set(current)
    return current


def bind_correlation_id(correlation_id: str | None) -> Token[str | None] | None:
    if correlation_id is None:
        return None
    return _correlation_id_var.set(correlation_id)


def reset_correlation_id(token: Token[str | None] | None) -> None:
    if token is None:
        return
    _correlation_id_var.reset(token)
