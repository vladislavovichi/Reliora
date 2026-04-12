from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from application.ai.contracts import AIMessage, AIProvider, AIProviderError
from application.ai.summaries import (
    AIPredictionConfidence,
    TicketAssistSnapshot,
    TicketCategoryPrediction,
    TicketMacroSuggestion,
    TicketSummaryStatus,
)
from application.contracts.ai import PredictTicketCategoryCommand
from application.use_cases.tickets.summaries import MacroSummary, TicketCategorySummary
from domain.contracts.repositories import (
    MacroRepository,
    TicketAISummaryRepository,
    TicketCategoryRepository,
    TicketRepository,
)
from domain.entities.ai import TicketAISummaryDetails
from domain.entities.ticket import TicketDetails
from domain.enums.tickets import TicketAttachmentKind

_SUMMARY_INSTRUCTIONS = (
    "Ты помогаешь оператору русскоязычного helpdesk. "
    "Верни только JSON без пояснений и markdown. "
    "Тон деловой, спокойный, короткий. "
    "Пиши как внутреннюю support-сводку. Не выдумывай факты."
)
_MACRO_INSTRUCTIONS = (
    "Ты подбираешь операторские макросы для helpdesk. "
    "Верни только JSON без пояснений и markdown. "
    "Выбирай только из переданного списка макросов. Не придумывай новые. "
    "Если уверенность слабая, не предлагай макрос."
)
_CATEGORY_INSTRUCTIONS = (
    "Ты помогаешь предсказать тему нового обращения в helpdesk. "
    "Верни только JSON без пояснений и markdown. "
    "Выбирай только из переданного списка тем. "
    "Если уверенность низкая, верни отсутствие предсказания."
)


class _TicketSummaryPayload(BaseModel):
    short_summary: str = Field(min_length=8, max_length=280)
    user_goal: str = Field(min_length=4, max_length=280)
    actions_taken: str = Field(min_length=4, max_length=280)
    current_status: str = Field(min_length=4, max_length=280)


class _MacroSuggestionItemPayload(BaseModel):
    macro_id: int
    reason: str = Field(min_length=4, max_length=220)
    confidence: AIPredictionConfidence = AIPredictionConfidence.MEDIUM


class _MacroSuggestionPayload(BaseModel):
    macro_ids: list[_MacroSuggestionItemPayload] = Field(default_factory=list, max_length=3)


class _CategoryPredictionPayload(BaseModel):
    category_id: int | None = None
    confidence: AIPredictionConfidence = AIPredictionConfidence.NONE
    reason: str | None = Field(default=None, max_length=220)


@dataclass(slots=True, frozen=True)
class AIGenerationProfile:
    summary_temperature: float = 0.15
    summary_max_output_tokens: int = 320
    macros_temperature: float = 0.2
    macros_max_output_tokens: int = 280
    category_temperature: float = 0.1
    category_max_output_tokens: int = 160


class BuildTicketAssistSnapshotUseCase:
    def __init__(
        self,
        *,
        ticket_repository: TicketRepository,
        ticket_ai_summary_repository: TicketAISummaryRepository,
        macro_repository: MacroRepository,
        ai_provider: AIProvider,
        profile: AIGenerationProfile,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_ai_summary_repository = ticket_ai_summary_repository
        self.macro_repository = macro_repository
        self.ai_provider = ai_provider
        self.profile = profile

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        refresh_summary: bool = False,
    ) -> TicketAssistSnapshot | None:
        ticket = await self.ticket_repository.get_details_by_public_id(ticket_public_id)
        if ticket is None:
            return None
        stored_summary = await self.ticket_ai_summary_repository.get_by_ticket_id(
            ticket_id=ticket.id
        )

        status_note: str | None = None
        if refresh_summary:
            if not self.ai_provider.is_enabled:
                status_note = (
                    "Обновление AI сейчас недоступно. Показываю последнюю сохранённую версию."
                    if stored_summary is not None
                    else "AI сейчас недоступен. Сводку можно сформировать позже."
                )
            else:
                refreshed_summary = await _build_ticket_summary(
                    provider=self.ai_provider,
                    profile=self.profile,
                    ticket=ticket,
                )
                if refreshed_summary is None:
                    status_note = (
                        "Не удалось обновить сводку. Оставил последнюю сохранённую версию."
                        if stored_summary is not None
                        else "Не удалось подготовить сводку сейчас."
                    )
                else:
                    stored_summary = await self.ticket_ai_summary_repository.upsert(
                        ticket_id=ticket.id,
                        short_summary=refreshed_summary.short_summary,
                        user_goal=refreshed_summary.user_goal,
                        actions_taken=refreshed_summary.actions_taken,
                        current_status=refreshed_summary.current_status,
                        generated_at=datetime.now(UTC),
                        source_ticket_updated_at=ticket.updated_at,
                        source_message_count=len(ticket.message_history),
                        source_internal_note_count=len(ticket.internal_notes),
                        model_id=self.ai_provider.model_id,
                    )
                    status_note = "Сводка обновлена."

        macro_suggestions: tuple[TicketMacroSuggestion, ...] = ()
        if self.ai_provider.is_enabled:
            macro_suggestions = await _build_macro_suggestions(
                provider=self.ai_provider,
                profile=self.profile,
                ticket=ticket,
                macros=await self._list_macros(),
            )

        if not self.ai_provider.is_enabled and stored_summary is None:
            return TicketAssistSnapshot(
                available=False,
                unavailable_reason="AI-провайдер не настроен.",
                model_id=self.ai_provider.model_id,
            )

        summary_status = _resolve_summary_status(ticket=ticket, stored_summary=stored_summary)
        if (
            stored_summary is not None
            and summary_status is TicketSummaryStatus.STALE
            and status_note is None
        ):
            status_note = "В переписке появились изменения. Сводку лучше обновить."
        if stored_summary is None and self.ai_provider.is_enabled and status_note is None:
            status_note = (
                "Сводка ещё не подготовлена. При необходимости её можно сформировать вручную."
            )
        if not macro_suggestions and self.ai_provider.is_enabled and status_note is None:
            status_note = (
                "Точных AI-подсказок по макросам сейчас нет. "
                "Обычная библиотека макросов остаётся доступной."
            )

        return TicketAssistSnapshot(
            available=True,
            summary_status=summary_status,
            summary_generated_at=(
                stored_summary.generated_at if stored_summary is not None else None
            ),
            short_summary=stored_summary.short_summary if stored_summary is not None else None,
            user_goal=stored_summary.user_goal if stored_summary is not None else None,
            actions_taken=stored_summary.actions_taken if stored_summary is not None else None,
            current_status=stored_summary.current_status if stored_summary is not None else None,
            macro_suggestions=tuple(macro_suggestions),
            status_note=status_note,
            unavailable_reason=(
                "Новые AI-подсказки временно недоступны."
                if not self.ai_provider.is_enabled and stored_summary is not None
                else None
            ),
            model_id=(
                stored_summary.model_id if stored_summary is not None else self.ai_provider.model_id
            ),
        )

    async def _list_macros(self) -> tuple[MacroSummary, ...]:
        return tuple(
            MacroSummary(id=item.id, title=item.title, body=item.body)
            for item in await self.macro_repository.list_all()
        )


class PredictTicketCategoryUseCase:
    def __init__(
        self,
        *,
        ticket_category_repository: TicketCategoryRepository,
        ai_provider: AIProvider,
        profile: AIGenerationProfile,
    ) -> None:
        self.ticket_category_repository = ticket_category_repository
        self.ai_provider = ai_provider
        self.profile = profile

    async def __call__(
        self,
        command: PredictTicketCategoryCommand,
    ) -> TicketCategoryPrediction:
        categories = await self._list_categories()
        if not categories or not self.ai_provider.is_enabled:
            return TicketCategoryPrediction(
                available=False,
                model_id=self.ai_provider.model_id,
            )
        if not _has_signal(command):
            return TicketCategoryPrediction(
                available=False,
                model_id=self.ai_provider.model_id,
            )

        prompt = _build_category_prediction_prompt(command=command, categories=categories)
        payload = await _complete_json(
            provider=self.ai_provider,
            instructions=_CATEGORY_INSTRUCTIONS,
            prompt=prompt,
            schema=_CategoryPredictionPayload,
            max_output_tokens=self.profile.category_max_output_tokens,
            temperature=self.profile.category_temperature,
        )
        if payload is None or payload.category_id is None:
            return TicketCategoryPrediction(
                available=False,
                model_id=self.ai_provider.model_id,
            )
        if payload.confidence not in {
            AIPredictionConfidence.MEDIUM,
            AIPredictionConfidence.HIGH,
        }:
            return TicketCategoryPrediction(
                available=False,
                model_id=self.ai_provider.model_id,
            )

        category = next((item for item in categories if item.id == payload.category_id), None)
        if category is None:
            return TicketCategoryPrediction(
                available=False,
                model_id=self.ai_provider.model_id,
            )

        return TicketCategoryPrediction(
            available=True,
            category_id=category.id,
            category_code=category.code,
            category_title=category.title,
            confidence=payload.confidence,
            reason=payload.reason,
            model_id=self.ai_provider.model_id,
        )

    async def _list_categories(self) -> tuple[TicketCategorySummary, ...]:
        return tuple(
            TicketCategorySummary(
                id=item.id,
                code=item.code,
                title=item.title,
                is_active=item.is_active,
                sort_order=item.sort_order,
            )
            for item in await self.ticket_category_repository.list_all(include_inactive=False)
        )


async def _build_ticket_summary(
    *,
    provider: AIProvider,
    profile: AIGenerationProfile,
    ticket: TicketDetails,
) -> _TicketSummaryPayload | None:
    prompt = _build_ticket_summary_prompt(ticket)
    return await _complete_json(
        provider=provider,
        instructions=_SUMMARY_INSTRUCTIONS,
        prompt=prompt,
        schema=_TicketSummaryPayload,
        max_output_tokens=profile.summary_max_output_tokens,
        temperature=profile.summary_temperature,
    )


async def _build_macro_suggestions(
    *,
    provider: AIProvider,
    profile: AIGenerationProfile,
    ticket: TicketDetails,
    macros: Sequence[MacroSummary],
) -> tuple[TicketMacroSuggestion, ...]:
    if not macros:
        return ()

    prompt = _build_macro_suggestion_prompt(ticket=ticket, macros=macros)
    payload = await _complete_json(
        provider=provider,
        instructions=_MACRO_INSTRUCTIONS,
        prompt=prompt,
        schema=_MacroSuggestionPayload,
        max_output_tokens=profile.macros_max_output_tokens,
        temperature=profile.macros_temperature,
    )
    if payload is None or not payload.macro_ids:
        return ()

    macro_by_id = {macro.id: macro for macro in macros}
    suggestions: list[TicketMacroSuggestion] = []
    seen_macro_ids: set[int] = set()
    for item in payload.macro_ids:
        if item.confidence not in {
            AIPredictionConfidence.MEDIUM,
            AIPredictionConfidence.HIGH,
        }:
            continue
        macro = macro_by_id.get(item.macro_id)
        if macro is None or macro.id in seen_macro_ids:
            continue
        seen_macro_ids.add(macro.id)
        suggestions.append(
            TicketMacroSuggestion(
                macro_id=macro.id,
                title=macro.title,
                body=macro.body,
                reason=item.reason,
                confidence=item.confidence,
            )
        )
    return tuple(suggestions)


def _resolve_summary_status(
    *,
    ticket: TicketDetails,
    stored_summary: TicketAISummaryDetails | None,
) -> TicketSummaryStatus:
    if stored_summary is None:
        return TicketSummaryStatus.MISSING
    if (
        ticket.updated_at > stored_summary.source_ticket_updated_at
        or len(ticket.message_history) != stored_summary.source_message_count
        or len(ticket.internal_notes) != stored_summary.source_internal_note_count
    ):
        return TicketSummaryStatus.STALE
    return TicketSummaryStatus.FRESH


async def _complete_json[SchemaT: BaseModel](
    *,
    provider: AIProvider,
    instructions: str,
    prompt: str,
    schema: type[SchemaT],
    max_output_tokens: int,
    temperature: float,
) -> SchemaT | None:
    try:
        raw = await provider.complete(
            messages=(
                AIMessage(role="system", content=instructions),
                AIMessage(role="user", content=prompt),
            ),
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
    except AIProviderError:
        return None

    payload = _extract_json_object(raw)
    if payload is None:
        return None
    try:
        return schema.model_validate(payload)
    except ValidationError:
        return None


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _build_ticket_summary_prompt(ticket: TicketDetails) -> str:
    return "\n".join(
        [
            "Сформируй краткую сводку по заявке helpdesk.",
            "Нужен JSON вида:",
            (
                '{"short_summary":"...","user_goal":"...",'
                '"actions_taken":"...","current_status":"..."}'
            ),
            "",
            f"Заявка: {ticket.public_id}",
            f"Тема: {ticket.subject}",
            f"Статус: {ticket.status.value}",
            f"Категория: {ticket.category_title or 'не указана'}",
            f"Теги: {', '.join(ticket.tags) if ticket.tags else 'нет'}",
            "",
            "Полная история сообщений:",
            _format_ticket_history(ticket),
            "",
            "Внутренние заметки:",
            _format_internal_notes(ticket),
        ]
    )


def _build_macro_suggestion_prompt(
    *,
    ticket: TicketDetails,
    macros: Sequence[MacroSummary],
) -> str:
    macro_lines = [
        f"- id={macro.id}; title={macro.title}; body={_normalize_inline(macro.body, 180)}"
        for macro in macros
    ]
    return "\n".join(
        [
            "Подбери до трёх макросов для оператора.",
            "Нужен JSON вида:",
            (
                '{"macro_ids":[{"macro_id":1,"reason":"...","confidence":"high"},'
                '{"macro_id":2,"reason":"...","confidence":"medium"}]}'
            ),
            "Если ничего не подходит, верни пустой массив.",
            "",
            f"Тема: {ticket.subject}",
            f"Статус: {ticket.status.value}",
            f"Категория: {ticket.category_title or 'не указана'}",
            "",
            "Контекст переписки:",
            _format_ticket_history(ticket),
            "",
            "Доступные макросы:",
            "\n".join(macro_lines),
        ]
    )


def _build_category_prediction_prompt(
    *,
    command: PredictTicketCategoryCommand,
    categories: Sequence[TicketCategorySummary],
) -> str:
    category_lines = [
        f"- id={category.id}; code={category.code}; title={category.title}"
        for category in categories
    ]
    return "\n".join(
        [
            "Определи наиболее вероятную тему нового обращения.",
            "Нужен JSON вида:",
            '{"category_id":2,"confidence":"medium","reason":"..."}',
            'Если тема неочевидна, верни {"category_id":null,"confidence":"none","reason":"..."}',
            "",
            f"Текст: {command.text or 'нет текста'}",
            "Вложение: "
            + _format_attachment_hint(
                command.attachment_kind,
                command.attachment_filename,
                command.attachment_mime_type,
            ),
            "",
            "Темы:",
            "\n".join(category_lines),
        ]
    )


def _format_ticket_history(ticket: TicketDetails) -> str:
    if not ticket.message_history:
        return "История сообщений пуста."

    lines: list[str] = []
    for index, message in enumerate(ticket.message_history, start=1):
        sender = message.sender_operator_name or message.sender_type.value
        attachment_hint = ""
        if message.attachment is not None:
            attachment_hint = (
                f" [вложение: {message.attachment.kind.value}"
                f"{f', {message.attachment.filename}' if message.attachment.filename else ''}]"
            )
        body = message.text or "без текста"
        lines.append(f"{index}. {sender}: {_normalize_inline(body, 400)}{attachment_hint}")
    return "\n".join(lines)


def _format_internal_notes(ticket: TicketDetails) -> str:
    if not ticket.internal_notes:
        return "Заметок нет."
    return "\n".join(
        f"- {note.author_operator_name or f'оператор #{note.author_operator_id}'}: "
        f"{_normalize_inline(note.text, 240)}"
        for note in ticket.internal_notes
    )


def _normalize_inline(value: str, limit: int) -> str:
    normalized = " ".join(escape(value).split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def _format_attachment_hint(
    kind: TicketAttachmentKind | None,
    filename: str | None,
    mime_type: str | None,
) -> str:
    parts = [kind.value if kind is not None else None, filename, mime_type]
    resolved = [part for part in parts if part]
    if not resolved:
        return "нет"
    return ", ".join(resolved)


def _has_signal(command: PredictTicketCategoryCommand) -> bool:
    return bool(
        (command.text and command.text.strip())
        or command.attachment_kind is not None
        or (command.attachment_filename and command.attachment_filename.strip())
    )
