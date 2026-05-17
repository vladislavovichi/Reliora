"""
E2E: full ticket lifecycle across a real gRPC backend and DB.

Scenario: client submits → operator sees in queue → operator replies → ticket closed.
"""

from __future__ import annotations

import pytest

from application.contracts.actors import OperatorIdentity, RequestActor
from application.contracts.tickets import (
    ClientTicketMessageCommand,
    OperatorTicketReplyCommand,
)
from backend.grpc.contracts import HelpdeskBackendClient
from domain.enums.tickets import TicketStatus


@pytest.mark.e2e
@pytest.mark.integration
async def test_client_submits_operator_replies_ticket_closes(
    grpc_client: HelpdeskBackendClient,
) -> None:
    super_admin = RequestActor(telegram_user_id=42)
    operator = OperatorIdentity(telegram_user_id=1001, display_name="Operator One")
    client_chat_id = 9001

    # --- promote operator ---
    await grpc_client.promote_operator(operator, actor=super_admin)

    # --- client submits a ticket ---
    ticket = await grpc_client.create_ticket_from_client_intake(
        ClientTicketMessageCommand(
            client_chat_id=client_chat_id,
            telegram_message_id=100,
            text="Я не могу войти в систему",
        )
    )
    assert ticket is not None
    assert ticket.status == TicketStatus.NEW

    # --- ticket appears in the operator queue ---
    queued = await grpc_client.list_queued_tickets(actor=RequestActor(telegram_user_id=1001))
    queue_ids = [t.public_id for t in queued]
    assert ticket.public_id in queue_ids, "New ticket must appear in the operator queue"

    # --- operator takes the ticket ---
    from application.contracts.tickets import AssignNextQueuedTicketCommand

    assigned = await grpc_client.assign_next_ticket_to_operator(
        AssignNextQueuedTicketCommand(operator=operator, prioritize_priority=False),
        actor=RequestActor(telegram_user_id=operator.telegram_user_id),
    )
    assert assigned is not None
    assert assigned.public_id == ticket.public_id
    assert assigned.status == TicketStatus.ASSIGNED

    # --- operator replies ---
    reply_result = await grpc_client.reply_to_ticket_as_operator(
        OperatorTicketReplyCommand(
            ticket_public_id=ticket.public_id,
            operator=operator,
            text="Здравствуйте! Помогу разобраться.",
            attachment=None,
        ),
        actor=RequestActor(telegram_user_id=operator.telegram_user_id),
    )
    assert reply_result is not None

    # --- operator closes the ticket ---
    closed = await grpc_client.close_ticket_as_operator(
        ticket_public_id=ticket.public_id,
        actor=RequestActor(telegram_user_id=operator.telegram_user_id),
    )
    assert closed is not None
    assert closed.status == TicketStatus.CLOSED

    # --- ticket no longer in active queue ---
    queued_after = await grpc_client.list_queued_tickets(
        actor=RequestActor(telegram_user_id=operator.telegram_user_id)
    )
    remaining_ids = [t.public_id for t in queued_after]
    assert ticket.public_id not in remaining_ids, "Closed ticket must leave the queue"

    # --- cleanup: revoke operator to avoid polluting other tests ---
    await grpc_client.revoke_operator(
        telegram_user_id=operator.telegram_user_id, actor=super_admin
    )
