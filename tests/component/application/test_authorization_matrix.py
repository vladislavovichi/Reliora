from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from application.contracts.actors import OperatorIdentity, RequestActor
from application.contracts.tickets import (
    AssignNextQueuedTicketCommand,
    OperatorTicketReplyCommand,
    TicketAssignmentCommand,
)
from application.services.authorization import AuthorizationError
from application.services.helpdesk.service import HelpdeskService
from application.use_cases.tickets.exports import TicketReportFormat
from domain.enums.tickets import TicketStatus
from tests.component.application.test_helpdesk_service import (
    StubOperatorManagementRepository,
    StubTicketRepository,
    build_service,
    build_ticket,
)

USER_ACTOR = RequestActor(telegram_user_id=2002)
OPERATOR_ACTOR = RequestActor(telegram_user_id=1001)
OPERATOR = OperatorIdentity(telegram_user_id=1001, display_name="Operator")
ServiceFixture = tuple[HelpdeskService, Any]


@pytest.fixture
def queued_ticket_service() -> ServiceFixture:
    ticket = build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.QUEUED)
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=2, public_id=uuid4(), status=TicketStatus.NEW),
            queued_tickets=[ticket],
        ),
        operator_repository=StubOperatorManagementRepository(active_operator_ids={1001}),
        super_admin_telegram_user_ids=frozenset({42}),
    )
    return service, ticket


async def test_user_cannot_view_operator_queue(queued_ticket_service: ServiceFixture) -> None:
    service, _ticket = queued_ticket_service

    with pytest.raises(AuthorizationError):
        await service.list_queued_tickets(actor=USER_ACTOR)


async def test_user_cannot_reply_as_operator(queued_ticket_service: ServiceFixture) -> None:
    service, ticket = queued_ticket_service

    with pytest.raises(AuthorizationError):
        await service.reply_to_ticket_as_operator(
            OperatorTicketReplyCommand(
                ticket_public_id=ticket.public_id,
                telegram_message_id=3001,
                operator=OPERATOR,
                text="Ответ",
            ),
            actor=USER_ACTOR,
        )


async def test_user_cannot_close_as_operator(queued_ticket_service: ServiceFixture) -> None:
    service, ticket = queued_ticket_service

    with pytest.raises(AuthorizationError):
        await service.close_ticket_as_operator(ticket_public_id=ticket.public_id, actor=USER_ACTOR)


async def test_user_cannot_assign_or_reassign_tickets(
    queued_ticket_service: ServiceFixture,
) -> None:
    service, ticket = queued_ticket_service

    with pytest.raises(AuthorizationError):
        await service.assign_next_ticket_to_operator(
            AssignNextQueuedTicketCommand(operator=OPERATOR),
            actor=USER_ACTOR,
        )

    with pytest.raises(AuthorizationError):
        await service.assign_ticket_to_operator(
            TicketAssignmentCommand(ticket_public_id=ticket.public_id, operator=OPERATOR),
            actor=USER_ACTOR,
        )


async def test_user_cannot_export_ticket_reports(
    queued_ticket_service: ServiceFixture,
) -> None:
    service, ticket = queued_ticket_service

    with pytest.raises(AuthorizationError):
        await service.export_ticket_report(
            ticket_public_id=ticket.public_id,
            format=TicketReportFormat.CSV,
            actor=USER_ACTOR,
        )


async def test_user_cannot_use_ai_assist(queued_ticket_service: ServiceFixture) -> None:
    service, ticket = queued_ticket_service

    with pytest.raises(AuthorizationError):
        await service.get_ticket_ai_assist_snapshot(
            ticket_public_id=ticket.public_id,
            actor=USER_ACTOR,
        )

    with pytest.raises(AuthorizationError):
        await service.generate_ticket_reply_draft(
            ticket_public_id=ticket.public_id,
            actor=USER_ACTOR,
        )


async def test_operator_cannot_manage_operators_or_invites(
    queued_ticket_service: ServiceFixture,
) -> None:
    service, _ticket = queued_ticket_service

    with pytest.raises(AuthorizationError):
        await service.list_operators(actor=OPERATOR_ACTOR)

    with pytest.raises(AuthorizationError):
        await service.create_operator_invite(actor=OPERATOR_ACTOR)


async def test_operator_cannot_perform_super_admin_category_actions(
    queued_ticket_service: ServiceFixture,
) -> None:
    service, _ticket = queued_ticket_service

    with pytest.raises(AuthorizationError):
        await service.create_ticket_category(title="Billing", actor=OPERATOR_ACTOR)

    with pytest.raises(AuthorizationError):
        await service.set_ticket_category_active(
            category_id=1,
            is_active=False,
            actor=OPERATOR_ACTOR,
        )


async def test_internal_service_actor_remains_allowed_where_intended(
    queued_ticket_service: ServiceFixture,
) -> None:
    service, _ticket = queued_ticket_service

    queued = await service.list_queued_tickets(actor=None)
    operators = await service.list_operators(actor=None)

    assert len(queued) == 1
    assert [operator.telegram_user_id for operator in operators] == [1001]
