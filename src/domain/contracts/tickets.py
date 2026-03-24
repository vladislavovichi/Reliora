from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from domain.entities.ticket import Ticket


class TicketQueryService(Protocol):
    async def get_by_id(self, ticket_id: UUID) -> Ticket | None:
        """Return a single ticket or ``None`` when it does not exist."""

    async def list_open(self) -> Sequence[Ticket]:
        """Return currently open tickets."""


class TicketCommandService(Protocol):
    async def save(self, ticket: Ticket) -> None:
        """Persist a ticket aggregate."""

    # TODO: add assignment, escalation, and closure commands once workflows are introduced.
