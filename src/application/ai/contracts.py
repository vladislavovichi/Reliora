from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

AIMessageRole = Literal["system", "user"]


@dataclass(slots=True, frozen=True)
class AIMessage:
    role: AIMessageRole
    content: str


class AIProviderError(RuntimeError):
    """Raised when the configured AI provider cannot complete a request."""

    def __init__(self, message: str, *, failure_category: str = "provider_unavailable") -> None:
        super().__init__(message)
        self.failure_category = failure_category


class AIProviderTimeoutError(AIProviderError):
    """Raised when the configured AI provider request times out."""

    def __init__(self, message: str) -> None:
        super().__init__(message, failure_category="timeout")


class AIProvider(Protocol):
    @property
    def is_enabled(self) -> bool: ...

    @property
    def model_id(self) -> str | None: ...

    async def complete(
        self,
        *,
        messages: Sequence[AIMessage],
        max_output_tokens: int,
        temperature: float,
    ) -> str: ...
