from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import cast
from uuid import UUID

from application.services.authorization import Permission
from application.services.helpdesk.components import HelpdeskComponents
from application.services.helpdesk.ticket_operations import HelpdeskSLASync
from application.use_cases.tickets.summaries import (
    MacroApplicationResult,
    MacroSummary,
    TagSummary,
    TicketCategorySummary,
    TicketTagMutationResult,
    TicketTagsSummary,
)


class HelpdeskCatalogOperations:
    _components: HelpdeskComponents
    _require_permission_if_actor: Callable[..., Awaitable[None]]

    async def list_ticket_categories(
        self,
        *,
        actor_telegram_user_id: int | None = None,
    ) -> Sequence[TicketCategorySummary]:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.list_ticket_categories(include_inactive=True)

    async def get_ticket_category(
        self,
        *,
        category_id: int,
        actor_telegram_user_id: int | None = None,
    ) -> TicketCategorySummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.get_ticket_category(category_id=category_id)

    async def create_ticket_category(
        self,
        *,
        title: str,
        actor_telegram_user_id: int | None = None,
    ) -> TicketCategorySummary:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.create_ticket_category(title=title)

    async def update_ticket_category_title(
        self,
        *,
        category_id: int,
        title: str,
        actor_telegram_user_id: int | None = None,
    ) -> TicketCategorySummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.update_ticket_category_title(
            category_id=category_id,
            title=title,
        )

    async def set_ticket_category_active(
        self,
        *,
        category_id: int,
        is_active: bool,
        actor_telegram_user_id: int | None = None,
    ) -> TicketCategorySummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.set_ticket_category_active(
            category_id=category_id,
            is_active=is_active,
        )

    async def list_macros(
        self,
        *,
        actor_telegram_user_id: int | None = None,
    ) -> Sequence[MacroSummary]:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.list_macros()

    async def get_macro(
        self,
        *,
        macro_id: int,
        actor_telegram_user_id: int | None = None,
    ) -> MacroSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.get_macro(macro_id=macro_id)

    async def create_macro(
        self,
        *,
        title: str,
        body: str,
        actor_telegram_user_id: int | None = None,
    ) -> MacroSummary:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.create_macro(title=title, body=body)

    async def update_macro_title(
        self,
        *,
        macro_id: int,
        title: str,
        actor_telegram_user_id: int | None = None,
    ) -> MacroSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.update_macro_title(
            macro_id=macro_id,
            title=title,
        )

    async def update_macro_body(
        self,
        *,
        macro_id: int,
        body: str,
        actor_telegram_user_id: int | None = None,
    ) -> MacroSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.update_macro_body(
            macro_id=macro_id,
            body=body,
        )

    async def delete_macro(
        self,
        *,
        macro_id: int,
        actor_telegram_user_id: int | None = None,
    ) -> MacroSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.delete_macro(macro_id=macro_id)

    async def apply_macro_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        macro_id: int,
        telegram_user_id: int,
        display_name: str,
        username: str | None,
        actor_telegram_user_id: int | None = None,
    ) -> MacroApplicationResult | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        result = await self._components.catalog.apply_macro(
            ticket_public_id=ticket_public_id,
            macro_id=macro_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )
        if result is not None:
            await cast(HelpdeskSLASync, self)._sync_sla_deadline(
                ticket_public_id=result.ticket.public_id
            )
        return result

    async def list_ticket_tags(
        self,
        *,
        ticket_public_id: UUID,
        actor_telegram_user_id: int | None = None,
    ) -> TicketTagsSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.list_ticket_tags(ticket_public_id=ticket_public_id)

    async def list_available_tags(
        self,
        *,
        actor_telegram_user_id: int | None = None,
    ) -> Sequence[TagSummary]:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.catalog.list_available_tags()

    async def add_tag_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
        actor_telegram_user_id: int | None = None,
    ) -> TicketTagMutationResult | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        result = await self._components.catalog.add_tag(
            ticket_public_id=ticket_public_id,
            tag_name=tag_name,
        )
        if result is not None:
            await cast(HelpdeskSLASync, self)._sync_sla_deadline(
                ticket_public_id=result.ticket.public_id
            )
        return result

    async def remove_tag_from_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
        actor_telegram_user_id: int | None = None,
    ) -> TicketTagMutationResult | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        result = await self._components.catalog.remove_tag(
            ticket_public_id=ticket_public_id,
            tag_name=tag_name,
        )
        if result is not None:
            await cast(HelpdeskSLASync, self)._sync_sla_deadline(
                ticket_public_id=result.ticket.public_id
            )
        return result
