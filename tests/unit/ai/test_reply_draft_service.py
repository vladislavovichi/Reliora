from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from ai_service.service import AIApplicationService
from ai_service.service_prompts import build_reply_draft_prompt
from application.ai.contracts import AIMessage, AIProvider
from application.contracts.ai import (
    AIContextInternalNote,
    AIContextMessage,
    GenerateTicketReplyDraftCommand,
)
from domain.enums.tickets import TicketMessageSenderType, TicketStatus
from infrastructure.config.settings import AIConfig


class SequencedProvider(AIProvider):
    def __init__(self, responses: Sequence[str], *, enabled: bool = True) -> None:
        self.responses = list(responses)
        self._enabled = enabled
        self.calls: list[Sequence[AIMessage]] = []

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def model_id(self) -> str | None:
        return "reply-model"

    async def complete(
        self,
        *,
        messages: Sequence[AIMessage],
        max_output_tokens: int,
        temperature: float,
    ) -> str:
        del max_output_tokens, temperature
        self.calls.append(messages)
        return self.responses.pop(0)


async def test_generate_ticket_reply_draft_returns_validated_payload() -> None:
    provider = SequencedProvider(
        (
            (
                '{"reply_text":"Здравствуйте! Проверим вашу заявку и вернёмся с ответом.",'
                '"tone":"polite","confidence":0.82,"safety_note":"Не обещает сроки.",'
                '"missing_information":["номер заказа"]}'
            ),
        )
    )
    service = AIApplicationService(provider=provider, config=AIConfig())

    result = await service.generate_ticket_reply_draft(_build_command())

    assert result.available is True
    assert result.reply_text == "Здравствуйте! Проверим вашу заявку и вернёмся с ответом."
    assert result.tone == "polite"
    assert result.confidence == 0.82
    assert result.safety_note == "Не обещает сроки."
    assert result.missing_information == ("номер заказа",)


async def test_generate_ticket_reply_draft_rejects_invalid_payload() -> None:
    service = AIApplicationService(
        provider=SequencedProvider(('{"reply_text":"","tone":"ok"}', '{"still":"bad"}')),
        config=AIConfig(),
    )

    result = await service.generate_ticket_reply_draft(_build_command())

    assert result.available is False
    assert result.unavailable_reason == "Не удалось подготовить черновик ответа."


async def test_generate_ticket_reply_draft_retries_invalid_json_once() -> None:
    provider = SequencedProvider(
        (
            "not json",
            (
                '{"reply_text":"Здравствуйте! Уточните номер заказа, '
                'чтобы мы проверили обращение.","tone":"polite","confidence":0.7,'
                '"safety_note":null,"missing_information":["номер заказа"]}'
            ),
        )
    )
    service = AIApplicationService(provider=provider, config=AIConfig())

    result = await service.generate_ticket_reply_draft(_build_command())

    assert result.available is True
    assert result.reply_text is not None
    assert "Уточните номер заказа" in result.reply_text
    assert len(provider.calls) == 2


def test_reply_draft_prompt_marks_internal_notes_as_internal() -> None:
    prompt = build_reply_draft_prompt(_build_command())

    assert "Внутренние заметки (используй только для понимания; не раскрывай клиенту)" in prompt
    assert "role=customer" in prompt
    assert "role=operator" in prompt
    assert "Всего сообщений: 2. Показано последних: 2." in prompt


async def test_generate_ticket_reply_draft_degrades_when_provider_disabled() -> None:
    service = AIApplicationService(
        provider=SequencedProvider((), enabled=False),
        config=AIConfig(),
    )

    result = await service.generate_ticket_reply_draft(_build_command())

    assert result.available is False
    assert result.unavailable_reason == "AI-провайдер не настроен."


def _build_command() -> GenerateTicketReplyDraftCommand:
    return GenerateTicketReplyDraftCommand(
        ticket_public_id=uuid4(),
        subject="Не могу войти",
        status=TicketStatus.ASSIGNED,
        category_title="Доступ",
        tags=("vip",),
        message_history=(
            AIContextMessage(
                sender_type=TicketMessageSenderType.CLIENT,
                sender_label=None,
                text="Здравствуйте, не могу войти в кабинет.",
                created_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
            ),
            AIContextMessage(
                sender_type=TicketMessageSenderType.OPERATOR,
                sender_label="Анна",
                text="Проверяем доступ.",
                created_at=datetime(2026, 4, 20, 10, 5, tzinfo=UTC),
            ),
        ),
        internal_notes=(
            AIContextInternalNote(
                author_name="Анна",
                text="Не раскрывать клиенту внутренний идентификатор проверки.",
                created_at=datetime(2026, 4, 20, 10, 6, tzinfo=UTC),
            ),
        ),
    )
