from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from application.use_cases.tickets.common import build_ticket_summary
from application.use_cases.tickets.identifiers import format_public_ticket_number
from application.use_cases.tickets.summaries import (
    TagSummary,
    TicketTagMutationResult,
    TicketTagsSummary,
)
from domain.contracts.repositories import (
    TagRepository,
    TicketEventRepository,
    TicketRepository,
    TicketTagRepository,
)
from domain.enums.tickets import TicketEventType


class ListTicketTagsUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_tag_repository: TicketTagRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_tag_repository = ticket_tag_repository

    async def __call__(self, *, ticket_public_id: UUID) -> TicketTagsSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        tags = await self.ticket_tag_repository.list_for_ticket(ticket_id=ticket.id)
        return TicketTagsSummary(
            public_id=ticket.public_id,
            public_number=format_public_ticket_number(ticket.public_id),
            tags=tuple(tag.name for tag in tags),
        )


class ListAvailableTagsUseCase:
    def __init__(self, tag_repository: TagRepository) -> None:
        self.tag_repository = tag_repository

    async def __call__(self) -> Sequence[TagSummary]:
        tags = await self.tag_repository.list_all()
        return [TagSummary(id=tag.id, name=tag.name) for tag in tags]


class AddTagToTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        tag_repository: TagRepository,
        ticket_tag_repository: TicketTagRepository,
        ticket_event_repository: TicketEventRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.tag_repository = tag_repository
        self.ticket_tag_repository = ticket_tag_repository
        self.ticket_event_repository = ticket_event_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
    ) -> TicketTagMutationResult | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        tag_id = await self.tag_repository.get_or_create(name=tag_name)
        added = await self.ticket_tag_repository.add(ticket_id=ticket.id, tag_id=tag_id)
        tags = await self.ticket_tag_repository.list_for_ticket(ticket_id=ticket.id)
        normalized_tag = next(
            (tag.name for tag in tags if tag.id == tag_id), tag_name.strip().lower()
        )

        if added:
            await self.ticket_event_repository.add(
                ticket_id=ticket.id,
                event_type=TicketEventType.TAG_ADDED,
                payload_json={"tag": normalized_tag},
            )

        return TicketTagMutationResult(
            ticket=build_ticket_summary(
                ticket, event_type=TicketEventType.TAG_ADDED if added else None
            ),
            tag=normalized_tag,
            changed=added,
            tags=tuple(tag.name for tag in tags),
        )


class RemoveTagFromTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        tag_repository: TagRepository,
        ticket_tag_repository: TicketTagRepository,
        ticket_event_repository: TicketEventRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.tag_repository = tag_repository
        self.ticket_tag_repository = ticket_tag_repository
        self.ticket_event_repository = ticket_event_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
    ) -> TicketTagMutationResult | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        tag = await self.tag_repository.get_by_name(name=tag_name)
        removed = False
        normalized_tag = tag_name.strip().lower()
        if tag is not None:
            normalized_tag = tag.name
            removed = await self.ticket_tag_repository.remove(ticket_id=ticket.id, tag_id=tag.id)
            if removed:
                await self.ticket_event_repository.add(
                    ticket_id=ticket.id,
                    event_type=TicketEventType.TAG_REMOVED,
                    payload_json={"tag": normalized_tag},
                )

        tags = await self.ticket_tag_repository.list_for_ticket(ticket_id=ticket.id)
        return TicketTagMutationResult(
            ticket=build_ticket_summary(
                ticket,
                event_type=TicketEventType.TAG_REMOVED if removed else None,
            ),
            tag=normalized_tag,
            changed=removed,
            tags=tuple(tag_item.name for tag_item in tags),
        )
