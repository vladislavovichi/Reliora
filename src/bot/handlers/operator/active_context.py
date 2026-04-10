from __future__ import annotations

from uuid import UUID

from application.use_cases.tickets.summaries import TicketDetailsSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_request_actor_from_id
from domain.enums.tickets import TicketStatus
from infrastructure.redis.contracts import OperatorActiveTicketStore, TicketLiveSessionStore

ACTIVE_OPERATOR_TICKET_STATUSES = frozenset({TicketStatus.ASSIGNED, TicketStatus.ESCALATED})


def is_operator_ticket_available(
    *,
    ticket_details: TicketDetailsSummary,
    operator_telegram_user_id: int,
) -> bool:
    return (
        ticket_details.status in ACTIVE_OPERATOR_TICKET_STATUSES
        and ticket_details.assigned_operator_telegram_user_id == operator_telegram_user_id
    )


async def activate_ticket_for_operator(
    *,
    active_ticket_store: OperatorActiveTicketStore,
    operator_telegram_user_id: int,
    ticket_details: TicketDetailsSummary,
    ticket_live_session_store: TicketLiveSessionStore | None = None,
) -> bool:
    if not is_operator_ticket_available(
        ticket_details=ticket_details,
        operator_telegram_user_id=operator_telegram_user_id,
    ):
        await active_ticket_store.clear_if_matches(
            operator_id=operator_telegram_user_id,
            ticket_public_id=str(ticket_details.public_id),
        )
        return False

    if ticket_live_session_store is not None:
        await refresh_live_session_for_ticket(
            ticket_live_session_store=ticket_live_session_store,
            ticket_details=ticket_details,
        )
    await active_ticket_store.set_active_ticket(
        operator_id=operator_telegram_user_id,
        ticket_public_id=str(ticket_details.public_id),
    )
    return True


async def clear_active_ticket_for_operator(
    *,
    active_ticket_store: OperatorActiveTicketStore,
    operator_telegram_user_id: int,
    ticket_public_id: str | None = None,
) -> None:
    if ticket_public_id is None:
        await active_ticket_store.clear(operator_id=operator_telegram_user_id)
        return

    await active_ticket_store.clear_if_matches(
        operator_id=operator_telegram_user_id,
        ticket_public_id=ticket_public_id,
    )


async def resolve_active_ticket_for_operator(
    *,
    active_ticket_store: OperatorActiveTicketStore,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    operator_telegram_user_id: int,
) -> TicketDetailsSummary | None:
    ticket_public_id = await active_ticket_store.get_active_ticket(
        operator_id=operator_telegram_user_id
    )
    if ticket_public_id is None:
        return None

    parsed_ticket_public_id = _parse_active_ticket_id(ticket_public_id)
    if parsed_ticket_public_id is None:
        await active_ticket_store.clear_if_matches(
            operator_id=operator_telegram_user_id,
            ticket_public_id=ticket_public_id,
        )
        return None

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        ticket_details = await helpdesk_backend.get_ticket_details(
            ticket_public_id=parsed_ticket_public_id,
            actor=build_request_actor_from_id(operator_telegram_user_id),
        )

    if ticket_details is None or not is_operator_ticket_available(
        ticket_details=ticket_details,
        operator_telegram_user_id=operator_telegram_user_id,
    ):
        await active_ticket_store.clear_if_matches(
            operator_id=operator_telegram_user_id,
            ticket_public_id=ticket_public_id,
        )
        return None

    return ticket_details


def _parse_active_ticket_id(ticket_public_id: str) -> UUID | None:
    from bot.handlers.operator.parsers import parse_ticket_public_id

    return parse_ticket_public_id(ticket_public_id)


async def refresh_live_session_for_ticket(
    *,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_details: TicketDetailsSummary,
) -> None:
    await ticket_live_session_store.refresh_session(
        ticket_public_id=str(ticket_details.public_id),
        client_chat_id=ticket_details.client_chat_id,
        operator_telegram_user_id=ticket_details.assigned_operator_telegram_user_id,
    )


async def delete_live_session_for_ticket(
    *,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_public_id: str,
) -> None:
    await ticket_live_session_store.delete_session(ticket_public_id=ticket_public_id)
