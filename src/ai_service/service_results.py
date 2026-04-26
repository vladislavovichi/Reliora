from __future__ import annotations

from application.ai.summaries import AIPredictionConfidence
from application.contracts.ai import (
    AIGeneratedTicketSummary,
    AIPredictedCategoryResult,
    AIPredictTicketCategoryCommand,
    AISuggestedMacro,
    GeneratedTicketReplyDraftResult,
    GeneratedTicketSummaryResult,
    SuggestedMacrosResult,
)

GENERIC_AI_REASON_TEXTS = {
    "...",
    "не знаю",
    "не уверен",
    "подходит",
    "релевантно",
    "по контексту",
    "по теме",
}


def build_generated_ticket_summary(
    *,
    short_summary: str,
    user_goal: str,
    actions_taken: str,
    current_status: str,
) -> AIGeneratedTicketSummary | None:
    normalized_short_summary = normalize_ai_text(short_summary, limit=280)
    normalized_user_goal = normalize_ai_text(user_goal, limit=280)
    normalized_actions_taken = normalize_ai_text(actions_taken, limit=280)
    normalized_current_status = normalize_ai_text(current_status, limit=280)
    if (
        normalized_short_summary is None
        or normalized_user_goal is None
        or normalized_actions_taken is None
        or normalized_current_status is None
    ):
        return None

    unique_sections = {
        normalized_short_summary,
        normalized_user_goal,
        normalized_actions_taken,
        normalized_current_status,
    }
    if len(unique_sections) < 3:
        return None

    return AIGeneratedTicketSummary(
        short_summary=normalized_short_summary,
        user_goal=normalized_user_goal,
        actions_taken=normalized_actions_taken,
        current_status=normalized_current_status,
    )


def build_suggested_macros(
    items: list[tuple[int, str, AIPredictionConfidence]],
) -> tuple[AISuggestedMacro, ...]:
    suggestions: list[AISuggestedMacro] = []
    seen_macro_ids: set[int] = set()
    for macro_id, reason_text, confidence in items:
        if macro_id in seen_macro_ids:
            continue
        if confidence not in {AIPredictionConfidence.MEDIUM, AIPredictionConfidence.HIGH}:
            continue
        reason = normalize_ai_reason(reason_text)
        if reason is None:
            continue
        seen_macro_ids.add(macro_id)
        suggestions.append(
            AISuggestedMacro(
                macro_id=macro_id,
                reason=reason,
                confidence=confidence,
            )
        )
    return tuple(suggestions)


def build_reply_draft(
    *,
    reply_text: str,
    tone: str,
    confidence: float | None,
    safety_note: str | None,
    missing_information: list[str] | None,
    model_id: str | None,
) -> GeneratedTicketReplyDraftResult | None:
    normalized_reply_text = normalize_ai_text(reply_text, limit=1400)
    normalized_tone = normalize_ai_text(tone, limit=80)
    if normalized_reply_text is None or normalized_tone is None:
        return None
    normalized_safety_note = normalize_ai_reason(safety_note)
    normalized_missing_information = _normalize_missing_information(missing_information)
    return GeneratedTicketReplyDraftResult(
        available=True,
        reply_text=normalized_reply_text,
        tone=normalized_tone,
        confidence=confidence,
        safety_note=normalized_safety_note,
        missing_information=normalized_missing_information,
        model_id=model_id,
    )


def build_category_prediction(
    *,
    category_id: int | None,
    confidence: AIPredictionConfidence,
    reason: str | None,
    command: AIPredictTicketCategoryCommand,
    model_id: str | None,
) -> AIPredictedCategoryResult | None:
    if category_id is None:
        return None
    if confidence not in {AIPredictionConfidence.MEDIUM, AIPredictionConfidence.HIGH}:
        return None
    valid_category_ids = {category.id for category in command.categories}
    if category_id not in valid_category_ids:
        return None
    return AIPredictedCategoryResult(
        available=True,
        category_id=category_id,
        confidence=confidence,
        reason=normalize_ai_reason(reason),
        model_id=model_id,
    )


def normalize_ai_text(value: str, *, limit: int) -> str | None:
    normalized = " ".join(value.split())
    if len(normalized) < 4:
        return None
    if normalized.lower() in GENERIC_AI_REASON_TEXTS:
        return None
    clipped = normalized[:limit].rstrip(" ,;:-")
    if len(clipped) < 4:
        return None
    return clipped


def normalize_ai_reason(value: str | None) -> str | None:
    if value is None:
        return None
    return normalize_ai_text(value, limit=120)


def has_prediction_signal(command: AIPredictTicketCategoryCommand) -> bool:
    return bool((command.text and command.text.strip()) or command.attachment is not None)


def unavailable_reply_draft_result(model_id: str | None) -> GeneratedTicketReplyDraftResult:
    return GeneratedTicketReplyDraftResult(
        available=False,
        unavailable_reason="AI-провайдер не настроен.",
        model_id=model_id,
    )


def unavailable_summary_result(model_id: str | None) -> GeneratedTicketSummaryResult:
    return GeneratedTicketSummaryResult(
        available=False,
        unavailable_reason="AI-провайдер не настроен.",
        model_id=model_id,
    )


def unavailable_macros_result(model_id: str | None) -> SuggestedMacrosResult:
    return SuggestedMacrosResult(
        available=False,
        unavailable_reason="AI-провайдер не настроен.",
        model_id=model_id,
    )


def unavailable_category_result(model_id: str | None) -> AIPredictedCategoryResult:
    return AIPredictedCategoryResult(
        available=False,
        unavailable_reason="AI-провайдер не настроен.",
        model_id=model_id,
    )


def _normalize_missing_information(values: list[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = normalize_ai_text(value, limit=120)
        if item is None:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return tuple(normalized) if normalized else None
