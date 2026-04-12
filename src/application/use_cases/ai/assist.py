from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from application.ai.summaries import (
    AIPredictionConfidence,
    TicketAssistSnapshot,
    TicketCategoryPrediction,
    TicketMacroSuggestion,
    TicketSummaryStatus,
)
from application.contracts.ai import (
    AICategoryOption,
    AIContextAttachment,
    AIContextInternalNote,
    AIContextMessage,
    AIPredictTicketCategoryCommand,
    AIServiceClientFactory,
    GenerateTicketSummaryCommand,
    MacroCandidate,
    PredictTicketCategoryCommand,
    SuggestMacrosCommand,
)
from application.use_cases.tickets.summaries import MacroSummary, TicketCategorySummary
from domain.contracts.repositories import (
    MacroRepository,
    TicketAISummaryRepository,
    TicketCategoryRepository,
    TicketRepository,
)
from domain.entities.ai import TicketAISummaryDetails
from domain.entities.ticket import TicketAttachmentDetails, TicketDetails, TicketMessageDetails


class BuildTicketAssistSnapshotUseCase:
    def __init__(
        self,
        *,
        ticket_repository: TicketRepository,
        ticket_ai_summary_repository: TicketAISummaryRepository,
        macro_repository: MacroRepository,
        ai_client_factory: AIServiceClientFactory,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_ai_summary_repository = ticket_ai_summary_repository
        self.macro_repository = macro_repository
        self.ai_client_factory = ai_client_factory

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

        macros = await self._list_macros()
        summary_result = None
        macros_result = None
        status_note: str | None = None

        async with self.ai_client_factory() as ai_client:
            if refresh_summary:
                summary_result = await ai_client.generate_ticket_summary(
                    _build_generate_ticket_summary_command(ticket)
                )
                if not summary_result.available or summary_result.summary is None:
                    status_note = (
                        "Не удалось обновить сводку. Оставил последнюю сохранённую версию."
                        if stored_summary is not None
                        else "Не удалось подготовить сводку сейчас."
                    )
                else:
                    generated_summary = summary_result.summary
                    stored_summary = await self.ticket_ai_summary_repository.upsert(
                        ticket_id=ticket.id,
                        short_summary=generated_summary.short_summary,
                        user_goal=generated_summary.user_goal,
                        actions_taken=generated_summary.actions_taken,
                        current_status=generated_summary.current_status,
                        generated_at=datetime.now(UTC),
                        source_ticket_updated_at=ticket.updated_at,
                        source_message_count=len(ticket.message_history),
                        source_internal_note_count=len(ticket.internal_notes),
                        model_id=summary_result.model_id,
                    )
                    status_note = "Сводка обновлена."

            macros_result = await ai_client.suggest_macros(
                _build_suggest_macros_command(ticket=ticket, macros=macros)
            )

        macro_suggestions = _resolve_macro_suggestions(
            macros=macros,
            suggestions=(() if macros_result is None else macros_result.suggestions),
        )

        if stored_summary is None and _ai_unavailable(summary_result, macros_result):
            return TicketAssistSnapshot(
                available=False,
                unavailable_reason=_resolve_unavailable_reason(summary_result, macros_result),
                model_id=_resolve_model_id(summary_result, macros_result, stored_summary),
            )

        summary_status = _resolve_summary_status(ticket=ticket, stored_summary=stored_summary)
        if (
            stored_summary is not None
            and summary_status is TicketSummaryStatus.STALE
            and status_note is None
        ):
            status_note = "В переписке появились изменения. Сводку лучше обновить."
        if (
            stored_summary is None
            and macros_result is not None
            and macros_result.available
            and status_note is None
        ):
            status_note = (
                "Сводка ещё не подготовлена. При необходимости её можно сформировать вручную."
            )
        if (
            macros_result is not None
            and macros_result.available
            and not macro_suggestions
            and status_note is None
        ):
            status_note = (
                "Точных AI-подсказок по макросам сейчас нет. "
                "Обычная библиотека макросов остаётся доступной."
            )
        if (
            stored_summary is not None
            and macros_result is not None
            and not macros_result.available
            and status_note is None
        ):
            status_note = "Новые AI-подсказки временно недоступны."

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
            macro_suggestions=macro_suggestions,
            status_note=status_note,
            unavailable_reason=(
                "Новые AI-подсказки временно недоступны."
                if stored_summary is not None
                and macros_result is not None
                and not macros_result.available
                else None
            ),
            model_id=_resolve_model_id(summary_result, macros_result, stored_summary),
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
        ai_client_factory: AIServiceClientFactory,
    ) -> None:
        self.ticket_category_repository = ticket_category_repository
        self.ai_client_factory = ai_client_factory

    async def __call__(
        self,
        command: PredictTicketCategoryCommand,
    ) -> TicketCategoryPrediction:
        categories = await self._list_categories()
        if not categories or not _has_signal(command):
            return TicketCategoryPrediction(available=False)

        async with self.ai_client_factory() as ai_client:
            result = await ai_client.predict_ticket_category(
                AIPredictTicketCategoryCommand(
                    text=command.text,
                    attachment=_build_attachment_context_from_prediction(command),
                    categories=tuple(
                        AICategoryOption(
                            id=category.id,
                            code=category.code,
                            title=category.title,
                        )
                        for category in categories
                    ),
                )
            )

        if result.category_id is None or result.confidence not in {
            AIPredictionConfidence.MEDIUM,
            AIPredictionConfidence.HIGH,
        }:
            return TicketCategoryPrediction(
                available=False,
                model_id=result.model_id,
            )

        category = next((item for item in categories if item.id == result.category_id), None)
        if category is None:
            return TicketCategoryPrediction(
                available=False,
                model_id=result.model_id,
            )

        return TicketCategoryPrediction(
            available=result.available,
            category_id=category.id,
            category_code=category.code,
            category_title=category.title,
            confidence=result.confidence,
            reason=result.reason,
            model_id=result.model_id,
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


def _build_generate_ticket_summary_command(
    ticket: TicketDetails,
) -> GenerateTicketSummaryCommand:
    return GenerateTicketSummaryCommand(
        ticket_public_id=ticket.public_id,
        subject=ticket.subject,
        status=ticket.status,
        category_title=ticket.category_title,
        tags=ticket.tags,
        message_history=tuple(
            _build_message_context(message) for message in ticket.message_history
        ),
        internal_notes=tuple(
            AIContextInternalNote(
                author_name=note.author_operator_name,
                text=note.text,
                created_at=note.created_at,
            )
            for note in ticket.internal_notes
        ),
    )


def _build_suggest_macros_command(
    *,
    ticket: TicketDetails,
    macros: tuple[MacroSummary, ...],
) -> SuggestMacrosCommand:
    return SuggestMacrosCommand(
        ticket_public_id=ticket.public_id,
        subject=ticket.subject,
        status=ticket.status,
        category_title=ticket.category_title,
        tags=ticket.tags,
        message_history=tuple(
            _build_message_context(message) for message in ticket.message_history
        ),
        macros=tuple(
            MacroCandidate(id=macro.id, title=macro.title, body=macro.body) for macro in macros
        ),
    )


def _build_message_context(message: TicketMessageDetails) -> AIContextMessage:
    return AIContextMessage(
        sender_type=message.sender_type,
        sender_label=message.sender_operator_name,
        text=message.text,
        created_at=message.created_at,
        attachment=_build_attachment_context(message.attachment),
    )


def _build_attachment_context(
    attachment: TicketAttachmentDetails | None,
) -> AIContextAttachment | None:
    if attachment is None:
        return None
    return AIContextAttachment(
        kind=attachment.kind,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
    )


def _build_attachment_context_from_prediction(
    command: PredictTicketCategoryCommand,
) -> AIContextAttachment | None:
    if command.attachment_kind is None:
        return None
    return AIContextAttachment(
        kind=command.attachment_kind,
        filename=command.attachment_filename,
        mime_type=command.attachment_mime_type,
    )


def _resolve_macro_suggestions(
    *,
    macros: tuple[MacroSummary, ...],
    suggestions: tuple[object, ...],
) -> tuple[TicketMacroSuggestion, ...]:
    macro_by_id = {macro.id: macro for macro in macros}
    result: list[TicketMacroSuggestion] = []
    seen_macro_ids: set[int] = set()
    for suggestion in suggestions:
        macro_id = getattr(suggestion, "macro_id", None)
        if not isinstance(macro_id, int) or macro_id in seen_macro_ids:
            continue
        macro = macro_by_id.get(macro_id)
        if macro is None:
            continue
        confidence = getattr(suggestion, "confidence", AIPredictionConfidence.NONE)
        if confidence not in {AIPredictionConfidence.MEDIUM, AIPredictionConfidence.HIGH}:
            continue
        seen_macro_ids.add(macro_id)
        result.append(
            TicketMacroSuggestion(
                macro_id=macro.id,
                title=macro.title,
                body=macro.body,
                reason=str(getattr(suggestion, "reason", "")),
                confidence=confidence,
            )
        )
    return tuple(result)


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


def _ai_unavailable(summary_result: object | None, macros_result: object | None) -> bool:
    checks = [item for item in (summary_result, macros_result) if item is not None]
    return bool(checks) and not any(bool(getattr(item, "available", False)) for item in checks)


def _resolve_unavailable_reason(*results: object | None) -> str:
    for result in results:
        reason = getattr(result, "unavailable_reason", None) if result is not None else None
        if isinstance(reason, str) and reason.strip():
            return reason
    return "AI-сервис сейчас недоступен."


def _resolve_model_id(
    summary_result: object | None,
    macros_result: object | None,
    stored_summary: TicketAISummaryDetails | None,
) -> str | None:
    if stored_summary is not None and stored_summary.model_id is not None:
        return stored_summary.model_id
    for result in (summary_result, macros_result):
        model_id = getattr(result, "model_id", None) if result is not None else None
        if isinstance(model_id, str) and model_id.strip():
            return model_id
    return None


def _has_signal(command: PredictTicketCategoryCommand) -> bool:
    return bool(
        (command.text and command.text.strip())
        or command.attachment_kind is not None
        or (command.attachment_filename and command.attachment_filename.strip())
    )
