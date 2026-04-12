from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from application.ai.summaries import AIPredictionConfidence, TicketSummaryStatus
from application.contracts.ai import (
    AIGeneratedTicketSummary,
    AIPredictedCategoryResult,
    AIServiceClient,
    AIServiceClientFactory,
    AISuggestedMacro,
    GeneratedTicketSummaryResult,
    PredictTicketCategoryCommand,
    SuggestedMacrosResult,
)
from application.use_cases.ai.assist import (
    BuildTicketAssistSnapshotUseCase,
    PredictTicketCategoryUseCase,
)
from domain.contracts.repositories import (
    MacroRepository,
    TicketAISummaryRepository,
    TicketCategoryRepository,
    TicketRepository,
)
from domain.entities.ai import TicketAISummaryDetails
from domain.entities.ticket import (
    TicketDetails,
    TicketInternalNoteDetails,
    TicketMessageDetails,
)
from domain.enums.tickets import TicketMessageSenderType, TicketPriority, TicketStatus


class StubAIClient(AIServiceClient):
    def __init__(
        self,
        *,
        summary_result: GeneratedTicketSummaryResult | None = None,
        macros_result: SuggestedMacrosResult | None = None,
        category_result: AIPredictedCategoryResult | None = None,
    ) -> None:
        self.summary_result = summary_result or GeneratedTicketSummaryResult(
            available=False,
            model_id="Qwen/Qwen3.5-4B",
        )
        self.macros_result = macros_result or SuggestedMacrosResult(
            available=False,
            model_id="Qwen/Qwen3.5-4B",
        )
        self.category_result = category_result or AIPredictedCategoryResult(
            available=False,
            model_id="Qwen/Qwen3.5-4B",
        )

    async def get_service_status(self) -> tuple[str, str]:
        return "helpdesk-ai-service", "ready"

    async def generate_ticket_summary(self, command: object) -> GeneratedTicketSummaryResult:
        del command
        return self.summary_result

    async def suggest_macros(self, command: object) -> SuggestedMacrosResult:
        del command
        return self.macros_result

    async def predict_ticket_category(self, command: object) -> AIPredictedCategoryResult:
        del command
        return self.category_result


def build_ai_client_factory(client: StubAIClient) -> AIServiceClientFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[AIServiceClient]:
        yield client

    return provide


class StubTicketRepository:
    def __init__(self, ticket: TicketDetails | None) -> None:
        self.ticket = ticket

    async def get_details_by_public_id(self, public_id: object) -> TicketDetails | None:
        del public_id
        return self.ticket


class StubMacroRepository:
    async def list_all(self) -> tuple[SimpleNamespace, ...]:
        return (
            SimpleNamespace(
                id=1,
                title="Сброс доступа",
                body="Сбросили пароль и обновили ссылку.",
            ),
            SimpleNamespace(
                id=2,
                title="Проверка платежа",
                body="Проверяем платёж и возвращаемся.",
            ),
        )


class StubCategoryRepository:
    async def list_all(self, *, include_inactive: bool = True) -> tuple[SimpleNamespace, ...]:
        assert include_inactive is False
        return (
            SimpleNamespace(
                id=1,
                code="access",
                title="Доступ и вход",
                is_active=True,
                sort_order=10,
            ),
            SimpleNamespace(
                id=2,
                code="billing",
                title="Оплата и баланс",
                is_active=True,
                sort_order=20,
            ),
        )


class StubTicketAISummaryRepository:
    def __init__(self) -> None:
        self.summary: TicketAISummaryDetails | None = None

    async def get_by_ticket_id(self, *, ticket_id: int) -> TicketAISummaryDetails | None:
        if self.summary is None or self.summary.ticket_id != ticket_id:
            return None
        return self.summary

    async def upsert(
        self,
        *,
        ticket_id: int,
        short_summary: str,
        user_goal: str,
        actions_taken: str,
        current_status: str,
        generated_at: datetime,
        source_ticket_updated_at: datetime,
        source_message_count: int,
        source_internal_note_count: int,
        model_id: str | None,
    ) -> TicketAISummaryDetails:
        self.summary = TicketAISummaryDetails(
            ticket_id=ticket_id,
            short_summary=short_summary,
            user_goal=user_goal,
            actions_taken=actions_taken,
            current_status=current_status,
            generated_at=generated_at,
            source_ticket_updated_at=source_ticket_updated_at,
            source_message_count=source_message_count,
            source_internal_note_count=source_internal_note_count,
            model_id=model_id,
        )
        return self.summary


def _build_ticket() -> TicketDetails:
    return TicketDetails(
        id=1,
        public_id=uuid4(),
        client_chat_id=2002,
        status=TicketStatus.ASSIGNED,
        priority=TicketPriority.NORMAL,
        subject="Не могу войти в кабинет после смены пароля",
        assigned_operator_id=7,
        assigned_operator_name="Иван Петров",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 12, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 12, 10, 15, tzinfo=UTC),
        first_response_at=datetime(2026, 4, 12, 10, 5, tzinfo=UTC),
        closed_at=None,
        category_id=1,
        category_code="access",
        category_title="Доступ и вход",
        tags=("vip",),
        message_history=(
            TicketMessageDetails(
                telegram_message_id=1,
                sender_type=TicketMessageSenderType.CLIENT,
                sender_operator_id=None,
                sender_operator_name=None,
                text="После смены пароля кабинет пишет, что логин недействителен.",
                created_at=datetime(2026, 4, 12, 10, 1, tzinfo=UTC),
            ),
            TicketMessageDetails(
                telegram_message_id=2,
                sender_type=TicketMessageSenderType.OPERATOR,
                sender_operator_id=7,
                sender_operator_name="Иван Петров",
                text="Проверяем профиль и готовим сброс доступа.",
                created_at=datetime(2026, 4, 12, 10, 5, tzinfo=UTC),
            ),
        ),
        internal_notes=(
            TicketInternalNoteDetails(
                id=1,
                author_operator_id=7,
                author_operator_name="Иван Петров",
                text="Похоже на рассинхрон после смены пароля в legacy-форме.",
                created_at=datetime(2026, 4, 12, 10, 8, tzinfo=UTC),
            ),
        ),
    )


async def test_build_ticket_assist_snapshot_returns_summary_and_macro_suggestions() -> None:
    summary_repository = StubTicketAISummaryRepository()
    use_case = BuildTicketAssistSnapshotUseCase(
        ticket_repository=cast(TicketRepository, StubTicketRepository(_build_ticket())),
        ticket_ai_summary_repository=cast(TicketAISummaryRepository, summary_repository),
        macro_repository=cast(MacroRepository, StubMacroRepository()),
        ai_client_factory=build_ai_client_factory(
            StubAIClient(
                summary_result=GeneratedTicketSummaryResult(
                    available=True,
                    summary=AIGeneratedTicketSummary(
                        short_summary="Клиент потерял доступ после смены пароля.",
                        user_goal="Восстановить вход без повторной регистрации.",
                        actions_taken="Оператор проверил профиль и готовит сброс.",
                        current_status="Ожидается финальное подтверждение после сброса.",
                    ),
                    model_id="Qwen/Qwen3.5-4B",
                ),
                macros_result=SuggestedMacrosResult(
                    available=True,
                    suggestions=(
                        AISuggestedMacro(
                            macro_id=1,
                            reason="Нужен готовый ответ про сброс доступа.",
                            confidence=AIPredictionConfidence.HIGH,
                        ),
                    ),
                    model_id="Qwen/Qwen3.5-4B",
                ),
            )
        ),
    )

    snapshot = await use_case(ticket_public_id=uuid4(), refresh_summary=True)

    assert snapshot is not None
    assert snapshot.available is True
    assert snapshot.short_summary == "Клиент потерял доступ после смены пароля."
    assert snapshot.macro_suggestions[0].macro_id == 1
    assert snapshot.summary_status is TicketSummaryStatus.FRESH
    assert snapshot.model_id == "Qwen/Qwen3.5-4B"


async def test_predict_ticket_category_returns_valid_prediction() -> None:
    use_case = PredictTicketCategoryUseCase(
        ticket_category_repository=cast(TicketCategoryRepository, StubCategoryRepository()),
        ai_client_factory=build_ai_client_factory(
            StubAIClient(
                category_result=AIPredictedCategoryResult(
                    available=True,
                    category_id=1,
                    confidence=AIPredictionConfidence.HIGH,
                    reason="Есть явные признаки проблемы со входом.",
                    model_id="Qwen/Qwen3.5-4B",
                )
            )
        ),
    )

    prediction = await use_case(
        PredictTicketCategoryCommand(
            text="Не могу войти после смены пароля",
        )
    )

    assert prediction.available is True
    assert prediction.category_id == 1
    assert prediction.category_title == "Доступ и вход"
    assert prediction.confidence == AIPredictionConfidence.HIGH


async def test_saved_ticket_summary_becomes_stale_after_history_changes() -> None:
    ticket = _build_ticket()
    summary_repository = StubTicketAISummaryRepository()
    await summary_repository.upsert(
        ticket_id=ticket.id,
        short_summary="Старая сводка",
        user_goal="Старый запрос",
        actions_taken="Старые действия",
        current_status="Старое состояние",
        generated_at=datetime(2026, 4, 12, 10, 7, tzinfo=UTC),
        source_ticket_updated_at=datetime(2026, 4, 12, 10, 7, tzinfo=UTC),
        source_message_count=1,
        source_internal_note_count=0,
        model_id="Qwen/Qwen3.5-4B",
    )
    use_case = BuildTicketAssistSnapshotUseCase(
        ticket_repository=cast(TicketRepository, StubTicketRepository(ticket)),
        ticket_ai_summary_repository=cast(TicketAISummaryRepository, summary_repository),
        macro_repository=cast(MacroRepository, StubMacroRepository()),
        ai_client_factory=build_ai_client_factory(
            StubAIClient(
                macros_result=SuggestedMacrosResult(
                    available=True,
                    suggestions=(),
                    model_id="Qwen/Qwen3.5-4B",
                )
            )
        ),
    )

    snapshot = await use_case(ticket_public_id=ticket.public_id)

    assert snapshot is not None
    assert snapshot.summary_status is TicketSummaryStatus.STALE
    assert snapshot.short_summary == "Старая сводка"
