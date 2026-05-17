"""
Integration: bot handler → real gRPC transport → stub HelpdeskService.

These tests verify that bot handler functions correctly issue gRPC calls and
produce the expected Telegram Bot API responses.  The gRPC server and client
are real; only the HelpdeskService implementation is stubbed.
"""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from application.contracts.actors import RequestActor
from application.contracts.tickets import ClientTicketMessageCommand, OperatorTicketReplyCommand
from application.use_cases.tickets.summaries import (
    OperatorReplyResult,
    TicketDetailsSummary,
    TicketSummary,
)
from backend.grpc.client import build_helpdesk_backend_client_factory
from backend.grpc.contracts import HelpdeskBackendClientFactory
from backend.grpc.server import build_helpdesk_backend_server
from bot.handlers.operator.workflow_reply import _handle_operator_message
from bot.handlers.user.intake_context import TicketRuntimeContext
from bot.handlers.user.workflow import process_client_ticket_command
from bot.handlers.common.ticket_attachments import IncomingTicketContent
from domain.enums.tickets import TicketStatus
from infrastructure.config.settings import BackendAuthConfig, BackendServiceConfig, ResilienceConfig
from tests.support.aiogram import MessageHarness, build_message_harness


_AUTH_TOKEN = "integration-bot-test-token"


# ---------------------------------------------------------------------------
# Networking helpers
# ---------------------------------------------------------------------------


def _free_tcp_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return cast(int, s.getsockname()[1])
    except PermissionError as exc:
        pytest.skip(f"Sandbox blocks local TCP sockets: {exc}")


# ---------------------------------------------------------------------------
# gRPC server/client lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _grpc_server_and_client(
    service_stub: object,
) -> AsyncIterator[HelpdeskBackendClientFactory]:
    port = _free_tcp_port()
    server = build_helpdesk_backend_server(
        helpdesk_service_factory=cast(Any, lambda: _wrap_service(service_stub)),
        bind_target=f"127.0.0.1:{port}",
        auth_config=BackendAuthConfig(token=_AUTH_TOKEN, caller="integration-test"),
    )
    await server.start()
    try:
        factory = build_helpdesk_backend_client_factory(
            BackendServiceConfig(host="127.0.0.1", port=port),
            auth_config=BackendAuthConfig(token=_AUTH_TOKEN, caller="integration-test"),
            resilience_config=ResilienceConfig(),
        )
        yield factory
    finally:
        await server.stop(grace=0)


@asynccontextmanager
async def _wrap_service(service: object) -> AsyncIterator[Any]:
    yield service


# ---------------------------------------------------------------------------
# Shared stub builders
# ---------------------------------------------------------------------------


def _ticket_summary(public_id: UUID, *, created: bool = True) -> TicketSummary:
    return TicketSummary(
        public_id=public_id,
        public_number="HD-AAAA0001",
        status=TicketStatus.QUEUED,
        created=created,
    )


def _ticket_details(public_id: UUID) -> TicketDetailsSummary:
    return TicketDetailsSummary(
        public_id=public_id,
        public_number="HD-AAAA0001",
        client_chat_id=9001,
        status=TicketStatus.QUEUED,
        priority="normal",
        subject="Не могу войти",
        assigned_operator_id=None,
        assigned_operator_name=None,
        assigned_operator_telegram_user_id=None,
        created_at=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 10, 1, tzinfo=UTC),
    )


def _assigned_ticket_details(public_id: UUID, *, operator_user_id: int) -> TicketDetailsSummary:
    return TicketDetailsSummary(
        public_id=public_id,
        public_number="HD-AAAA0001",
        client_chat_id=9001,
        status=TicketStatus.ASSIGNED,
        priority="normal",
        subject="Не могу войти",
        assigned_operator_id=7,
        assigned_operator_name="Operator One",
        assigned_operator_telegram_user_id=operator_user_id,
        created_at=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 10, 5, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Test 1 — client intake submission travels through real gRPC
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_client_intake_submission_roundtrips_over_grpc() -> None:
    """
    `process_client_ticket_command` calls `create_ticket_from_client_intake`
    and `get_ticket_details` via the real gRPC transport.  The bot must send
    a "ticket created" confirmation back to the client chat.
    """
    ticket_public_id = uuid4()
    captured: list[ClientTicketMessageCommand] = []

    async def fake_create_intake(command: ClientTicketMessageCommand) -> TicketSummary:
        captured.append(command)
        return _ticket_summary(ticket_public_id, created=True)

    async def fake_get_ticket_details(
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        return _ticket_details(ticket_public_id)

    service = SimpleNamespace(
        create_ticket_from_client_intake=fake_create_intake,
        get_ticket_details=fake_get_ticket_details,
    )

    message_harness = build_message_harness(
        text="Не могу войти в систему",
        user_id=9001,
        message_id=100,
        with_edit_text=False,
    )

    async with _grpc_server_and_client(service) as factory:
        context = _build_ticket_runtime_context(factory)
        await process_client_ticket_command(
            response_message=message_harness.message,
            bot=Mock(),
            context=context,
            command=ClientTicketMessageCommand(
                client_chat_id=9001,
                telegram_message_id=100,
                text="Не могу войти в систему",
                category_id=1,
            ),
            content=IncomingTicketContent(text="Не могу войти в систему", attachment=None),
            category_id=1,
        )

    assert len(captured) == 1
    assert captured[0].text == "Не могу войти в систему"
    assert captured[0].category_id == 1
    assert message_harness.answer.await_count == 1


# ---------------------------------------------------------------------------
# Test 2 — operator reply travels through real gRPC
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_operator_reply_roundtrips_over_grpc() -> None:
    """
    `_handle_operator_message` fetches ticket details and then submits the
    reply via the real gRPC transport.  The bot must send the "reply sent"
    confirmation back to the operator.
    """
    ticket_public_id = uuid4()
    operator_user_id = 1001
    replied: list[OperatorTicketReplyCommand] = []

    async def fake_get_ticket_details(
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        return _assigned_ticket_details(ticket_public_id, operator_user_id=operator_user_id)

    async def fake_reply(
        command: OperatorTicketReplyCommand,
        *,
        actor: RequestActor | None = None,
    ) -> OperatorReplyResult | None:
        replied.append(command)
        return OperatorReplyResult(
            ticket=TicketSummary(
                public_id=ticket_public_id,
                public_number="HD-AAAA0001",
                status=TicketStatus.ASSIGNED,
            ),
            client_chat_id=9001,
        )

    service = SimpleNamespace(
        get_ticket_details=fake_get_ticket_details,
        reply_to_ticket_as_operator=fake_reply,
    )

    message_harness = build_message_harness(
        text="Здравствуйте! Разберёмся.",
        user_id=operator_user_id,
        message_id=200,
    )
    bot = Mock()
    bot.send_message = AsyncMock()

    async with _grpc_server_and_client(service) as factory:
        await _handle_operator_message(
            message=message_harness.message,
            bot=bot,
            helpdesk_backend_client_factory=factory,
            global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
            operator_presence=SimpleNamespace(touch=AsyncMock()),
            operator_active_ticket_store=_build_active_ticket_store(ticket_public_id),
            ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
            ticket_lock_manager=_build_lock_manager(),
            explicit_ticket_public_id=ticket_public_id,
        )

    assert len(replied) == 1
    assert replied[0].text == "Здравствуйте! Разберёмся."
    assert replied[0].operator.telegram_user_id == operator_user_id
    assert message_harness.answer.await_count == 1


# ---------------------------------------------------------------------------
# Test 3 — gRPC auth token is enforced (bot receives ForbiddenError)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_client_intake_fails_with_wrong_grpc_auth_token() -> None:
    """
    When the bot uses an incorrect gRPC auth token the backend rejects the call
    and the handler surfaces a service-unavailable reply.
    """
    from application.errors import ForbiddenError

    service = SimpleNamespace(
        create_ticket_from_client_intake=AsyncMock(),
        get_ticket_details=AsyncMock(),
    )
    port = _free_tcp_port()
    server = build_helpdesk_backend_server(
        helpdesk_service_factory=cast(Any, lambda: _wrap_service(service)),
        bind_target=f"127.0.0.1:{port}",
        auth_config=BackendAuthConfig(token="correct-token", caller="server"),
    )
    await server.start()
    try:
        wrong_factory = build_helpdesk_backend_client_factory(
            BackendServiceConfig(host="127.0.0.1", port=port),
            auth_config=BackendAuthConfig(token="wrong-token", caller="bot"),
            resilience_config=ResilienceConfig(),
        )
        async with wrong_factory() as client:
            try:
                await client.create_ticket_from_client_intake(
                    ClientTicketMessageCommand(
                        client_chat_id=9001,
                        telegram_message_id=1,
                        text="test",
                        category_id=1,
                    )
                )
            except ForbiddenError:
                pass
            else:
                raise AssertionError("expected ForbiddenError for wrong token")
    finally:
        await server.stop(grace=0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_ticket_runtime_context(factory: HelpdeskBackendClientFactory) -> TicketRuntimeContext:
    return TicketRuntimeContext(
        helpdesk_backend_client_factory=factory,
        operator_active_ticket_store=SimpleNamespace(
            get_active_ticket=AsyncMock(return_value=None)
        ),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_stream_publisher=SimpleNamespace(publish_new_ticket=AsyncMock()),
        logger=Mock(),
    )


def _build_active_ticket_store(ticket_public_id: UUID) -> Any:
    return SimpleNamespace(
        get_active_ticket=AsyncMock(return_value=str(ticket_public_id)),
        set_active_ticket=AsyncMock(),
        clear_active_ticket=AsyncMock(),
    )


def _build_lock_manager() -> Any:
    lock = SimpleNamespace(acquire=AsyncMock(return_value=True), release=AsyncMock())
    return SimpleNamespace(for_ticket=Mock(return_value=lock))
