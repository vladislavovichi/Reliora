from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from ai_service.sentiment import analyze_ticket_sentiment
from ai_service.service_completion import (
    AICompletionFailureReason,
    complete_json_with_metadata,
)
from ai_service.service_prompts import (
    CATEGORY_INSTRUCTIONS,
    MACRO_INSTRUCTIONS,
    REPLY_DRAFT_INSTRUCTIONS,
    SUMMARY_INSTRUCTIONS,
    build_category_prediction_prompt,
    build_macro_suggestion_prompt,
    build_reply_draft_prompt,
    build_ticket_summary_prompt,
)
from ai_service.service_results import (
    build_category_prediction,
    build_generated_ticket_summary,
    build_reply_draft,
    build_suggested_macros,
    has_macro_suggestion_signal,
    has_prediction_signal,
    unavailable_category_result,
    unavailable_macros_result,
    unavailable_reply_draft_result,
    unavailable_summary_result,
)
from application.ai.contracts import AIProvider
from application.ai.summaries import AIPredictionConfidence
from application.contracts.ai import (
    AIPredictedCategoryResult,
    AIPredictTicketCategoryCommand,
    AnalyzedTicketSentimentResult,
    AnalyzeTicketSentimentCommand,
    GeneratedTicketReplyDraftResult,
    GeneratedTicketSummaryResult,
    GenerateTicketReplyDraftCommand,
    GenerateTicketSummaryCommand,
    SuggestedMacrosResult,
    SuggestMacrosCommand,
)
from infrastructure.config.settings import AIConfig

logger = logging.getLogger(__name__)

_AIOperationName = Literal["summary", "macro_suggestion", "category_prediction", "reply_draft"]


class TicketSummaryPayload(BaseModel):
    short_summary: str = Field(min_length=8, max_length=280)
    user_goal: str = Field(min_length=4, max_length=280)
    actions_taken: str = Field(min_length=4, max_length=280)
    current_status: str = Field(min_length=4, max_length=280)


class ReplyDraftPayload(BaseModel):
    reply_text: str = Field(min_length=8, max_length=1400)
    tone: str = Field(min_length=3, max_length=80)
    confidence: float | None = Field(default=None, ge=0, le=1)
    safety_note: str | None = Field(default=None, max_length=220)
    missing_information: list[str] | None = Field(default=None, max_length=6)


class MacroSuggestionItemPayload(BaseModel):
    macro_id: int
    reason: str = Field(min_length=4, max_length=220)
    confidence: AIPredictionConfidence = AIPredictionConfidence.MEDIUM


class MacroSuggestionPayload(BaseModel):
    macro_ids: list[MacroSuggestionItemPayload] = Field(default_factory=list, max_length=3)


class CategoryPredictionPayload(BaseModel):
    category_id: int | None = None
    confidence: AIPredictionConfidence = AIPredictionConfidence.NONE
    reason: str | None = Field(default=None, max_length=220)


@dataclass(slots=True)
class AIApplicationService:
    provider: AIProvider
    config: AIConfig

    async def generate_ticket_summary(
        self,
        command: GenerateTicketSummaryCommand,
    ) -> GeneratedTicketSummaryResult:
        operation = _AIOperationLogger(
            operation="summary",
            model_id=self.provider.model_id,
            ticket_public_id=command.ticket_public_id,
        )
        if not self.provider.is_enabled:
            operation.finish(success=False, failure_reason="disabled_by_settings")
            return unavailable_summary_result(self.provider.model_id)

        completion = await complete_json_with_metadata(
            provider=self.provider,
            instructions=SUMMARY_INSTRUCTIONS,
            prompt=build_ticket_summary_prompt(command),
            schema=TicketSummaryPayload,
            max_output_tokens=self.config.summary_max_output_tokens,
            temperature=self.config.summary_temperature,
        )
        payload = completion.payload
        if payload is None:
            operation.finish(
                success=False,
                failure_reason=completion.failure_reason,
                retry_count=completion.retry_count,
            )
            return GeneratedTicketSummaryResult(
                available=False,
                unavailable_reason="Не удалось подготовить сводку.",
                model_id=self.provider.model_id,
            )
        summary = build_generated_ticket_summary(
            short_summary=payload.short_summary,
            user_goal=payload.user_goal,
            actions_taken=payload.actions_taken,
            current_status=payload.current_status,
        )
        if summary is None:
            operation.finish(
                success=False,
                failure_reason="validation_failed",
                retry_count=completion.retry_count,
            )
            return GeneratedTicketSummaryResult(
                available=False,
                unavailable_reason="Не удалось подготовить достаточно надёжную сводку.",
                model_id=self.provider.model_id,
            )
        operation.finish(success=True, retry_count=completion.retry_count)
        return GeneratedTicketSummaryResult(
            available=True,
            summary=summary,
            model_id=self.provider.model_id,
        )

    async def suggest_macros(
        self,
        command: SuggestMacrosCommand,
    ) -> SuggestedMacrosResult:
        operation = _AIOperationLogger(
            operation="macro_suggestion",
            model_id=self.provider.model_id,
            ticket_public_id=command.ticket_public_id,
        )
        if not command.macros:
            operation.finish(success=False, failure_reason="missing_context")
            return SuggestedMacrosResult(available=True, model_id=self.provider.model_id)
        if not has_macro_suggestion_signal(command):
            operation.finish(success=False, failure_reason="missing_context")
            return SuggestedMacrosResult(available=True, model_id=self.provider.model_id)
        if not self.provider.is_enabled:
            operation.finish(success=False, failure_reason="disabled_by_settings")
            return unavailable_macros_result(self.provider.model_id)

        completion = await complete_json_with_metadata(
            provider=self.provider,
            instructions=MACRO_INSTRUCTIONS,
            prompt=build_macro_suggestion_prompt(command),
            schema=MacroSuggestionPayload,
            max_output_tokens=self.config.macros_max_output_tokens,
            temperature=self.config.macros_temperature,
        )
        payload = completion.payload
        if payload is None:
            operation.finish(
                success=False,
                failure_reason=completion.failure_reason,
                retry_count=completion.retry_count,
            )
            return SuggestedMacrosResult(
                available=False,
                unavailable_reason="Не удалось подобрать макросы.",
                model_id=self.provider.model_id,
            )
        suggestions = build_suggested_macros(
            [(item.macro_id, item.reason, item.confidence) for item in payload.macro_ids]
        )
        operation.finish(success=True, retry_count=completion.retry_count)
        return SuggestedMacrosResult(
            available=True,
            suggestions=suggestions,
            model_id=self.provider.model_id,
        )

    async def generate_ticket_reply_draft(
        self,
        command: GenerateTicketReplyDraftCommand,
    ) -> GeneratedTicketReplyDraftResult:
        operation = _AIOperationLogger(
            operation="reply_draft",
            model_id=self.provider.model_id,
            ticket_public_id=command.ticket_public_id,
        )
        if not self.provider.is_enabled:
            operation.finish(success=False, failure_reason="disabled_by_settings")
            return unavailable_reply_draft_result(self.provider.model_id)

        completion = await complete_json_with_metadata(
            provider=self.provider,
            instructions=REPLY_DRAFT_INSTRUCTIONS,
            prompt=build_reply_draft_prompt(command),
            schema=ReplyDraftPayload,
            max_output_tokens=self.config.summary_max_output_tokens,
            temperature=self.config.summary_temperature,
        )
        payload = completion.payload
        if payload is None:
            operation.finish(
                success=False,
                failure_reason=completion.failure_reason,
                retry_count=completion.retry_count,
            )
            return GeneratedTicketReplyDraftResult(
                available=False,
                unavailable_reason="Не удалось подготовить черновик ответа.",
                model_id=self.provider.model_id,
            )
        draft = build_reply_draft(
            reply_text=payload.reply_text,
            tone=payload.tone,
            confidence=payload.confidence,
            safety_note=payload.safety_note,
            missing_information=payload.missing_information,
            model_id=self.provider.model_id,
        )
        if draft is None:
            operation.finish(
                success=False,
                failure_reason="validation_failed",
                retry_count=completion.retry_count,
            )
            return GeneratedTicketReplyDraftResult(
                available=False,
                unavailable_reason="Не удалось подготовить достаточно надёжный черновик.",
                model_id=self.provider.model_id,
            )
        operation.finish(success=True, retry_count=completion.retry_count)
        return draft

    async def predict_ticket_category(
        self,
        command: AIPredictTicketCategoryCommand,
    ) -> AIPredictedCategoryResult:
        operation = _AIOperationLogger(
            operation="category_prediction",
            model_id=self.provider.model_id,
        )
        if not command.categories or not has_prediction_signal(command):
            operation.finish(success=False, failure_reason="missing_context")
            return AIPredictedCategoryResult(available=False, model_id=self.provider.model_id)
        if not self.provider.is_enabled:
            operation.finish(success=False, failure_reason="disabled_by_settings")
            return unavailable_category_result(self.provider.model_id)

        completion = await complete_json_with_metadata(
            provider=self.provider,
            instructions=CATEGORY_INSTRUCTIONS,
            prompt=build_category_prediction_prompt(command),
            schema=CategoryPredictionPayload,
            max_output_tokens=self.config.category_max_output_tokens,
            temperature=self.config.category_temperature,
        )
        payload = completion.payload
        prediction = build_category_prediction(
            category_id=payload.category_id if payload is not None else None,
            confidence=payload.confidence if payload is not None else AIPredictionConfidence.NONE,
            reason=payload.reason if payload is not None else None,
            command=command,
            model_id=self.provider.model_id,
        )
        if prediction is None:
            operation.finish(
                success=False,
                failure_reason=completion.failure_reason or "validation_failed",
                retry_count=completion.retry_count,
            )
            return AIPredictedCategoryResult(
                available=False,
                confidence=AIPredictionConfidence.NONE,
                model_id=self.provider.model_id,
            )
        operation.finish(success=True, retry_count=completion.retry_count)
        return prediction

    async def analyze_ticket_sentiment(
        self,
        command: AnalyzeTicketSentimentCommand,
    ) -> AnalyzedTicketSentimentResult:
        return analyze_ticket_sentiment(command)


@dataclass(slots=True)
class _AIOperationLogger:
    operation: _AIOperationName
    model_id: str | None
    ticket_public_id: UUID | None = None
    started_at: float = 0.0

    def __post_init__(self) -> None:
        self.started_at = perf_counter()

    def finish(
        self,
        *,
        success: bool,
        failure_reason: AICompletionFailureReason | str | None = None,
        retry_count: int = 0,
    ) -> None:
        normalized_reason = _normalize_failure_reason(failure_reason)
        logger.info(
            "AI operation finished",
            extra={
                "operation": self.operation,
                "ticket_public_id": str(self.ticket_public_id)
                if self.ticket_public_id is not None
                else None,
                "model_id": self.model_id,
                "latency_ms": round((perf_counter() - self.started_at) * 1000, 2),
                "success": success,
                "failure_reason": None if success else normalized_reason,
                "retry_count": retry_count,
            },
        )


def _normalize_failure_reason(reason: AICompletionFailureReason | str | None) -> str:
    if isinstance(reason, AICompletionFailureReason):
        return reason.value
    if isinstance(reason, str) and reason:
        return reason
    return "unknown"
