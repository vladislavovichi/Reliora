from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID

from application.contracts.actors import RequestActor, actor_telegram_user_id
from application.contracts.tickets import ApplyMacroToTicketCommand
from application.services.audit import AuditTrail
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


class HelpdeskCatalogOperations(HelpdeskSLASync):
    _components: HelpdeskComponents
    _audit: AuditTrail
    _require_permission_if_actor: Callable[..., Awaitable[None]]

    async def list_ticket_categories(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[TicketCategorySummary]:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.catalog.list_ticket_categories(include_inactive=True)

    async def get_ticket_category(
        self,
        *,
        category_id: int,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.catalog.get_ticket_category(category_id=category_id)

    async def create_ticket_category(
        self,
        *,
        title: str,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.catalog.create_ticket_category(title=title)
        await self._audit.write(
            action="category.create",
            entity_type="ticket_category",
            outcome="applied",
            actor_telegram_user_id=actor_telegram_user_id(actor),
            entity_id=result.id,
            metadata={"code": result.code, "title": result.title},
        )
        return result

    async def update_ticket_category_title(
        self,
        *,
        category_id: int,
        title: str,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.catalog.update_ticket_category_title(
            category_id=category_id,
            title=title,
        )
        if result is not None:
            await self._audit.write(
                action="category.update_title",
                entity_type="ticket_category",
                outcome="applied",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_id=result.id,
                metadata={"code": result.code, "title": result.title},
            )
        return result

    async def set_ticket_category_active(
        self,
        *,
        category_id: int,
        is_active: bool,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.catalog.set_ticket_category_active(
            category_id=category_id,
            is_active=is_active,
        )
        if result is not None:
            await self._audit.write(
                action="category.set_active",
                entity_type="ticket_category",
                outcome="applied",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_id=result.id,
                metadata={"code": result.code, "is_active": result.is_active},
            )
        return result

    async def list_macros(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[MacroSummary]:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.catalog.list_macros()

    async def get_macro(
        self,
        *,
        macro_id: int,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.catalog.get_macro(macro_id=macro_id)

    async def create_macro(
        self,
        *,
        title: str,
        body: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.catalog.create_macro(title=title, body=body)
        await self._audit.write(
            action="macro.create",
            entity_type="macro",
            outcome="applied",
            actor_telegram_user_id=actor_telegram_user_id(actor),
            entity_id=result.id,
            metadata={"title": result.title},
        )
        return result

    async def update_macro_title(
        self,
        *,
        macro_id: int,
        title: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.catalog.update_macro_title(
            macro_id=macro_id,
            title=title,
        )
        if result is not None:
            await self._audit.write(
                action="macro.update_title",
                entity_type="macro",
                outcome="applied",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_id=result.id,
                metadata={"title": result.title},
            )
        return result

    async def update_macro_body(
        self,
        *,
        macro_id: int,
        body: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.catalog.update_macro_body(
            macro_id=macro_id,
            body=body,
        )
        if result is not None:
            await self._audit.write(
                action="macro.update_body",
                entity_type="macro",
                outcome="applied",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_id=result.id,
                metadata={"title": result.title},
            )
        return result

    async def delete_macro(
        self,
        *,
        macro_id: int,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.catalog.delete_macro(macro_id=macro_id)
        if result is not None:
            await self._audit.write(
                action="macro.delete",
                entity_type="macro",
                outcome="applied",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_id=result.id,
                metadata={"title": result.title},
            )
        return result

    async def apply_macro_to_ticket(
        self,
        command: ApplyMacroToTicketCommand,
        actor: RequestActor | None = None,
    ) -> MacroApplicationResult | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.catalog.apply_macro(command)
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.ticket.public_id)
            await self._audit.write(
                action="ticket.macro.apply",
                entity_type="ticket",
                outcome="applied" if result.ticket.event_type is not None else "noop",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_public_id=result.ticket.public_id,
                metadata={
                    "ticket_public_number": result.ticket.public_number,
                    "macro_id": result.macro.id,
                    "macro_title": result.macro.title,
                },
            )
        return result

    async def list_ticket_tags(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketTagsSummary | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.catalog.list_ticket_tags(ticket_public_id=ticket_public_id)

    async def list_available_tags(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[TagSummary]:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.catalog.list_available_tags()

    async def add_tag_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
        actor: RequestActor | None = None,
    ) -> TicketTagMutationResult | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.catalog.add_tag(
            ticket_public_id=ticket_public_id,
            tag_name=tag_name,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.ticket.public_id)
            await self._audit.write(
                action="ticket.tag.add",
                entity_type="ticket",
                outcome="applied" if result.changed else "noop",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_public_id=result.ticket.public_id,
                metadata={"tag": result.tag, "tags": result.tags},
            )
        return result

    async def remove_tag_from_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
        actor: RequestActor | None = None,
    ) -> TicketTagMutationResult | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.catalog.remove_tag(
            ticket_public_id=ticket_public_id,
            tag_name=tag_name,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.ticket.public_id)
            await self._audit.write(
                action="ticket.tag.remove",
                entity_type="ticket",
                outcome="applied" if result.changed else "noop",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                entity_public_id=result.ticket.public_id,
                metadata={"tag": result.tag, "tags": result.tags},
            )
        return result
