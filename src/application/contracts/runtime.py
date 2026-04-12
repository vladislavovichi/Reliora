from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol

CorrelationIdProvider = Callable[[], str | None]


class SLADeadlineScheduler(Protocol):
    async def schedule(self, *, ticket_id: str, deadline_at: datetime) -> None:
        """Schedule an SLA deadline."""

    async def cancel(self, *, ticket_id: str) -> None:
        """Cancel an SLA deadline."""

    async def get_due(self, *, until: datetime, limit: int = 100) -> Sequence[str]:
        """Return due ticket identifiers."""
