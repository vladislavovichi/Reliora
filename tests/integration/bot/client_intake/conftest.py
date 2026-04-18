from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from application.use_cases.tickets.summaries import TicketDetailsSummary, TicketSummary
from backend.grpc.contracts import HelpdeskBackendClient, HelpdeskBackendClientFactory
from domain.enums.tickets import TicketStatus


@dataclass(slots=True)
class MessageHarness:
    message: Message
    answer: AsyncMock
    edit_text: AsyncMock


def build_helpdesk_backend_client_factory(
    service: HelpdeskBackendClient,
) -> HelpdeskBackendClientFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskBackendClient]:
        yield service

    return provide


def build_message_harness(
    *,
    text: str,
    chat_id: int = 2002,
    message_id: int = 15,
) -> MessageHarness:
    message = Message.model_construct(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat.model_construct(id=chat_id, type="private"),
        from_user=User.model_construct(id=chat_id, is_bot=False, first_name="Client"),
        text=text,
    )
    answer_mock = AsyncMock()
    edit_text_mock = AsyncMock()
    object.__setattr__(message, "answer", answer_mock)
    object.__setattr__(message, "edit_text", edit_text_mock)
    return MessageHarness(
        message=message,
        answer=answer_mock,
        edit_text=edit_text_mock,
    )


def build_callback(
    *,
    message: Message,
    data: str,
    user_id: int = 2002,
) -> tuple[CallbackQuery, AsyncMock]:
    callback = CallbackQuery.model_construct(
        id="callback-id",
        from_user=User.model_construct(id=user_id, is_bot=False, first_name="Client"),
        chat_instance="chat-instance",
        message=message,
        data=data,
    )
    answer_mock = AsyncMock()
    object.__setattr__(callback, "answer", answer_mock)
    return callback, answer_mock


def build_ticket_summary(public_id: UUID) -> TicketSummary:
    return TicketSummary(
        public_id=public_id,
        public_number="HD-AAAA1111",
        status=TicketStatus.QUEUED,
        created=True,
    )


def build_ticket_details(
    *,
    public_id: UUID,
    subject: str,
    category_id: int,
    category_title: str,
) -> TicketDetailsSummary:
    return TicketDetailsSummary(
        public_id=public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        status=TicketStatus.QUEUED,
        priority="normal",
        subject=subject,
        assigned_operator_id=None,
        assigned_operator_name=None,
        assigned_operator_telegram_user_id=None,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        category_id=category_id,
        category_title=category_title,
    )


@pytest.fixture
def backend_client_factory_builder():
    return build_helpdesk_backend_client_factory


@pytest.fixture
def message_harness_builder():
    return build_message_harness


@pytest.fixture
def callback_builder():
    return build_callback


@pytest.fixture
def ticket_summary_builder():
    return build_ticket_summary


@pytest.fixture
def ticket_details_builder():
    return build_ticket_details


@pytest.fixture
def publisher() -> SimpleNamespace:
    return SimpleNamespace(publish_new_ticket=AsyncMock())
