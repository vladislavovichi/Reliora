from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from application.ai.summaries import (
    AIPredictionConfidence,
    TicketAssistSnapshot,
    TicketMacroSuggestion,
    TicketReplyDraft,
    TicketSummaryStatus,
)
from application.contracts.actors import RequestActor
from backend.grpc.contracts import HelpdeskBackendClient, HelpdeskBackendClientFactory
from mini_app.api import MiniAppGateway
from mini_app.auth import TelegramMiniAppUser
from mini_app.serializers import serialize_ticket_ai_snapshot, serialize_ticket_reply_draft


class StubBackendClient:
    def __init__(
        self,
        snapshot: TicketAssistSnapshot,
        draft: TicketReplyDraft | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.draft = draft or _build_reply_draft()
        self.calls: list[tuple[UUID, bool, RequestActor | None]] = []
        self.draft_calls: list[tuple[UUID, RequestActor | None]] = []

    async def get_ticket_ai_assist_snapshot(
        self,
        *,
        ticket_public_id: UUID,
        refresh_summary: bool = False,
        actor: RequestActor | None = None,
    ) -> TicketAssistSnapshot | None:
        self.calls.append((ticket_public_id, refresh_summary, actor))
        return self.snapshot

    async def generate_ticket_reply_draft(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketReplyDraft | None:
        self.draft_calls.append((ticket_public_id, actor))
        return self.draft


def build_backend_factory(client: StubBackendClient) -> HelpdeskBackendClientFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskBackendClient]:
        yield cast(HelpdeskBackendClient, client)

    return provide


async def test_gateway_refresh_ticket_ai_summary_requests_forced_summary_refresh() -> None:
    ticket_public_id = uuid4()
    client = StubBackendClient(_build_snapshot())
    gateway = MiniAppGateway(backend_client_factory=build_backend_factory(client))

    result = await gateway.refresh_ticket_ai_summary(
        user=TelegramMiniAppUser(
            telegram_user_id=1001,
            first_name="Anna",
            last_name=None,
            username="anna",
            language_code="ru",
        ),
        ticket_public_id=ticket_public_id,
    )

    assert result["short_summary"] == "Клиент ждёт восстановления доступа."
    assert client.calls == [(ticket_public_id, True, RequestActor(telegram_user_id=1001))]


def test_serialize_ticket_ai_snapshot_contains_mini_app_fields() -> None:
    payload = serialize_ticket_ai_snapshot(_build_snapshot())

    assert payload == {
        "available": True,
        "unavailable_reason": None,
        "model_id": "test-model",
        "short_summary": "Клиент ждёт восстановления доступа.",
        "user_goal": "Войти в личный кабинет.",
        "actions_taken": "Оператор проверил профиль.",
        "current_status": "Нужен сброс доступа.",
        "summary_status": "fresh",
        "summary_generated_at": "2026-04-20T10:30:00+00:00",
        "status_note": "Сводка актуальна.",
        "macro_suggestions": [
            {
                "macro_id": 7,
                "title": "Сброс доступа",
                "body": "Сбросили доступ и отправили ссылку.",
                "reason": "Подходит для ответа про восстановление входа.",
                "confidence": "high",
            }
        ],
    }


def test_serialize_unavailable_ticket_ai_snapshot_contains_degraded_state() -> None:
    payload = serialize_ticket_ai_snapshot(
        TicketAssistSnapshot(
            available=False,
            unavailable_reason="AI-провайдер не настроен.",
            model_id=None,
        )
    )

    assert payload is not None
    assert payload["available"] is False
    assert payload["unavailable_reason"] == "AI-провайдер не настроен."
    assert payload["summary_status"] == "missing"
    assert payload["macro_suggestions"] == []


async def test_gateway_generate_ticket_reply_draft_calls_backend_with_actor() -> None:
    ticket_public_id = uuid4()
    client = StubBackendClient(_build_snapshot())
    gateway = MiniAppGateway(backend_client_factory=build_backend_factory(client))

    result = await gateway.generate_ticket_reply_draft(
        user=TelegramMiniAppUser(
            telegram_user_id=1001,
            first_name="Anna",
            last_name=None,
            username="anna",
            language_code="ru",
        ),
        ticket_public_id=ticket_public_id,
    )

    assert result["available"] is True
    assert result["reply_text"] == "Здравствуйте! Проверим заявку и вернёмся с ответом."
    assert client.draft_calls == [(ticket_public_id, RequestActor(telegram_user_id=1001))]


def test_serialize_ticket_reply_draft_contains_expected_fields() -> None:
    payload = serialize_ticket_reply_draft(_build_reply_draft())

    assert payload == {
        "available": True,
        "reply_text": "Здравствуйте! Проверим заявку и вернёмся с ответом.",
        "tone": "polite",
        "confidence": 0.8,
        "safety_note": "Без обещаний сроков.",
        "missing_information": ["номер заказа"],
        "unavailable_reason": None,
        "model_id": "reply-model",
    }


def test_serialize_unavailable_ticket_reply_draft_contains_degraded_state() -> None:
    payload = serialize_ticket_reply_draft(
        TicketReplyDraft(
            available=False,
            unavailable_reason="AI-провайдер не настроен.",
        )
    )

    assert payload is not None
    assert payload["available"] is False
    assert payload["reply_text"] is None
    assert payload["unavailable_reason"] == "AI-провайдер не настроен."


def _build_snapshot() -> TicketAssistSnapshot:
    return TicketAssistSnapshot(
        available=True,
        summary_status=TicketSummaryStatus.FRESH,
        summary_generated_at=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
        short_summary="Клиент ждёт восстановления доступа.",
        user_goal="Войти в личный кабинет.",
        actions_taken="Оператор проверил профиль.",
        current_status="Нужен сброс доступа.",
        macro_suggestions=(
            TicketMacroSuggestion(
                macro_id=7,
                title="Сброс доступа",
                body="Сбросили доступ и отправили ссылку.",
                reason="Подходит для ответа про восстановление входа.",
                confidence=AIPredictionConfidence.HIGH,
            ),
        ),
        status_note="Сводка актуальна.",
        model_id="test-model",
    )


def _build_reply_draft() -> TicketReplyDraft:
    return TicketReplyDraft(
        available=True,
        reply_text="Здравствуйте! Проверим заявку и вернёмся с ответом.",
        tone="polite",
        confidence=0.8,
        safety_note="Без обещаний сроков.",
        missing_information=("номер заказа",),
        model_id="reply-model",
    )
