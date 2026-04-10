from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Chat, Message, User

from application.contracts.actors import RequestActor
from application.services.stats import (
    AnalyticsCategorySnapshot,
    AnalyticsOperatorSnapshot,
    AnalyticsRatingBucket,
    AnalyticsWindow,
    HelpdeskAnalyticsSnapshot,
    OperatorTicketLoad,
)
from backend.grpc.contracts import HelpdeskBackendClient, HelpdeskBackendClientFactory
from bot.handlers.operator.stats import handle_stats, handle_stats_navigation
from bot.texts.operator import build_analytics_opened_text


def _build_helpdesk_backend_client_factory(service: object) -> HelpdeskBackendClientFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskBackendClient]:
        yield cast(HelpdeskBackendClient, service)

    return provide


def _build_message() -> Message:
    message = Message.model_construct(
        message_id=10,
        date=datetime.now(UTC),
        chat=Chat.model_construct(id=3001, type="private"),
        from_user=User.model_construct(id=1001, is_bot=False, first_name="Operator"),
        text="Статистика",
    )
    object.__setattr__(message, "answer", AsyncMock())
    return message


def _build_callback() -> CallbackQuery:
    message = _build_message()
    object.__setattr__(message, "edit_text", AsyncMock())
    callback = CallbackQuery.model_construct(
        id="callback-id",
        from_user=User.model_construct(id=1001, is_bot=False, first_name="Operator"),
        chat_instance="chat-instance",
        data="operator_stats:operators:7d",
        message=message,
    )
    object.__setattr__(callback, "answer", AsyncMock())
    return callback


async def test_handle_stats_sends_overview_surface() -> None:
    message = _build_message()
    state = cast(FSMContext, SimpleNamespace(clear=AsyncMock()))
    snapshot = _build_snapshot()
    service = SimpleNamespace(get_analytics_snapshot=AsyncMock(return_value=snapshot))
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_presence = SimpleNamespace(touch=AsyncMock())

    await handle_stats(
        message=message,
        state=state,
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
    )

    cast(AsyncMock, message.answer).assert_awaited_once_with(ANY, reply_markup=ANY)
    service.get_analytics_snapshot.assert_awaited_once_with(
        window=AnalyticsWindow.DAYS_7,
        actor=RequestActor(telegram_user_id=1001),
    )


async def test_handle_stats_navigation_updates_surface() -> None:
    callback = _build_callback()
    snapshot = _build_snapshot()
    service = SimpleNamespace(get_analytics_snapshot=AsyncMock(return_value=snapshot))
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_presence = SimpleNamespace(touch=AsyncMock())

    await handle_stats_navigation(
        callback=callback,
        callback_data=SimpleNamespace(section="operators", window="7d"),
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
    )

    cast(AsyncMock, callback.answer).assert_awaited_once_with(
        build_analytics_opened_text(section="operators", window=AnalyticsWindow.DAYS_7)
    )
    assert isinstance(callback.message, Message)
    cast(AsyncMock, callback.message.edit_text).assert_awaited_once_with(ANY, reply_markup=ANY)


def _build_snapshot() -> HelpdeskAnalyticsSnapshot:
    operators = (
        AnalyticsOperatorSnapshot(
            operator_id=7,
            display_name="Operator One",
            active_ticket_count=3,
            closed_ticket_count=4,
            average_first_response_time_seconds=120,
            average_resolution_time_seconds=5400,
            average_satisfaction=4.8,
            feedback_count=3,
        ),
    )
    categories = (
        AnalyticsCategorySnapshot(
            category_id=1,
            category_title="Доступ и вход",
            created_ticket_count=5,
            open_ticket_count=2,
            closed_ticket_count=3,
            average_satisfaction=4.5,
            feedback_count=2,
            sla_breach_count=2,
        ),
    )
    return HelpdeskAnalyticsSnapshot(
        window=AnalyticsWindow.DAYS_7,
        total_open_tickets=6,
        queued_tickets_count=2,
        assigned_tickets_count=3,
        escalated_tickets_count=1,
        closed_tickets_count=4,
        tickets_per_operator=(
            OperatorTicketLoad(operator_id=7, display_name="Operator One", ticket_count=3),
        ),
        period_created_tickets_count=9,
        period_closed_tickets_count=5,
        average_first_response_time_seconds=126,
        average_resolution_time_seconds=7260,
        satisfaction_average=4.7,
        feedback_count=4,
        feedback_coverage_percent=80,
        rating_distribution=(AnalyticsRatingBucket(rating=5, count=3),),
        operator_snapshots=operators,
        category_snapshots=categories,
        best_operators_by_closures=operators,
        best_operators_by_satisfaction=operators,
        top_categories=categories,
        first_response_breach_count=2,
        resolution_breach_count=1,
        sla_categories=categories,
    )
