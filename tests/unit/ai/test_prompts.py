from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from ai_service.service_prompts import (
    build_category_prediction_prompt,
    build_reply_draft_prompt,
    build_ticket_summary_prompt,
)
from application.contracts.ai import (
    AICategoryOption,
    AIContextMessage,
    AIPredictTicketCategoryCommand,
    GenerateTicketReplyDraftCommand,
    GenerateTicketSummaryCommand,
)
from domain.enums.tickets import TicketMessageSenderType, TicketStatus


def test_summary_prompt_contains_required_context_and_escapes_user_text() -> None:
    prompt = build_ticket_summary_prompt(
        GenerateTicketSummaryCommand(
            ticket_public_id=UUID("11111111-1111-1111-1111-111111111111"),
            subject="<script>alert(1)</script>",
            status=TicketStatus.ASSIGNED,
            category_title="Доступ",
            message_history=(
                AIContextMessage(
                    sender_type=TicketMessageSenderType.CLIENT,
                    sender_label="Client",
                    text="<b>Не могу войти</b>",
                    created_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
                ),
            ),
        )
    )

    assert "Сформируй краткую сводку" in prompt
    assert "public_id: 11111111-1111-1111-1111-111111111111" in prompt
    assert "&lt;b&gt;Не могу войти&lt;/b&gt;" in prompt


def test_reply_draft_prompt_preserves_operator_review_and_internal_note_boundary() -> None:
    prompt = build_reply_draft_prompt(
        GenerateTicketReplyDraftCommand(
            ticket_public_id=UUID("22222222-2222-2222-2222-222222222222"),
            subject="Ошибка оплаты",
            status=TicketStatus.QUEUED,
            category_title="Оплата",
        )
    )

    assert "не будет отправлен автоматически" in prompt
    assert "не раскрывай клиенту" in prompt
    assert '"reply_text"' in prompt


def test_category_prompt_lists_only_provided_categories() -> None:
    prompt = build_category_prediction_prompt(
        AIPredictTicketCategoryCommand(
            text="Не могу оплатить",
            categories=(
                AICategoryOption(id=1, code="access", title="Доступ"),
                AICategoryOption(id=2, code="billing", title="Оплата"),
            ),
        )
    )

    assert "id=1; code=access; title=Доступ" in prompt
    assert "id=2; code=billing; title=Оплата" in prompt
    assert "Выбирай только из переданного списка тем" not in prompt
