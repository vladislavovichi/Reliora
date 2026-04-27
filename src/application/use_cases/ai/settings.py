from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

DEFAULT_AI_MAX_HISTORY_MESSAGES = 20
MIN_AI_MAX_HISTORY_MESSAGES = 1
MAX_AI_MAX_HISTORY_MESSAGES = 100
DEFAULT_REPLY_DRAFT_TONE = "polite"
ALLOWED_REPLY_DRAFT_TONES = frozenset({"polite", "friendly", "formal"})


@dataclass(slots=True, frozen=True)
class RuntimeAISettings:
    ai_summaries_enabled: bool = True
    ai_macro_suggestions_enabled: bool = True
    ai_reply_drafts_enabled: bool = True
    ai_category_prediction_enabled: bool = True
    default_model_id: str | None = None
    max_history_messages: int = DEFAULT_AI_MAX_HISTORY_MESSAGES
    reply_draft_tone: str = DEFAULT_REPLY_DRAFT_TONE
    operator_must_review_ai: bool = True


class AISettingsProvider(Protocol):
    def get(self) -> RuntimeAISettings: ...


class AISettingsRepository(AISettingsProvider, Protocol):
    def save(self, settings: RuntimeAISettings) -> RuntimeAISettings: ...


@dataclass(slots=True)
class InMemoryAISettingsRepository(AISettingsRepository):
    settings: RuntimeAISettings = RuntimeAISettings()

    def get(self) -> RuntimeAISettings:
        return self.settings

    def save(self, settings: RuntimeAISettings) -> RuntimeAISettings:
        self.settings = normalize_ai_settings(settings)
        return self.settings


def normalize_ai_settings(settings: RuntimeAISettings) -> RuntimeAISettings:
    model_id = normalize_optional_string(settings.default_model_id)
    tone = normalize_reply_draft_tone(settings.reply_draft_tone)
    max_history_messages = max(
        MIN_AI_MAX_HISTORY_MESSAGES,
        min(settings.max_history_messages, MAX_AI_MAX_HISTORY_MESSAGES),
    )
    return replace(
        settings,
        default_model_id=model_id,
        max_history_messages=max_history_messages,
        reply_draft_tone=tone,
        operator_must_review_ai=True,
    )


def build_ai_settings_from_update(
    current: RuntimeAISettings,
    payload: dict[str, object],
) -> RuntimeAISettings:
    allowed_keys = {
        "ai_summaries_enabled",
        "ai_macro_suggestions_enabled",
        "ai_reply_drafts_enabled",
        "ai_category_prediction_enabled",
        "default_model_id",
        "max_history_messages",
        "reply_draft_tone",
        "operator_must_review_ai",
    }
    unknown_keys = sorted(set(payload) - allowed_keys)
    if unknown_keys:
        raise ValueError(f"Unsupported AI settings fields: {', '.join(unknown_keys)}")

    return normalize_ai_settings(
        RuntimeAISettings(
            ai_summaries_enabled=_optional_bool(
                payload,
                "ai_summaries_enabled",
                current.ai_summaries_enabled,
            ),
            ai_macro_suggestions_enabled=_optional_bool(
                payload,
                "ai_macro_suggestions_enabled",
                current.ai_macro_suggestions_enabled,
            ),
            ai_reply_drafts_enabled=_optional_bool(
                payload,
                "ai_reply_drafts_enabled",
                current.ai_reply_drafts_enabled,
            ),
            ai_category_prediction_enabled=_optional_bool(
                payload,
                "ai_category_prediction_enabled",
                current.ai_category_prediction_enabled,
            ),
            default_model_id=_optional_nullable_string(
                payload,
                "default_model_id",
                current.default_model_id,
            ),
            max_history_messages=_optional_int(
                payload,
                "max_history_messages",
                current.max_history_messages,
            ),
            reply_draft_tone=_optional_string(
                payload,
                "reply_draft_tone",
                current.reply_draft_tone,
            ),
            operator_must_review_ai=_optional_bool(
                payload,
                "operator_must_review_ai",
                current.operator_must_review_ai,
            ),
        )
    )


def normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().split())
    return normalized or None


def normalize_reply_draft_tone(value: str) -> str:
    normalized = (normalize_optional_string(value) or DEFAULT_REPLY_DRAFT_TONE).lower()
    if normalized not in ALLOWED_REPLY_DRAFT_TONES:
        raise ValueError(
            "reply_draft_tone must be one of: "
            f"{', '.join(sorted(ALLOWED_REPLY_DRAFT_TONES))}"
        )
    return normalized


def _optional_bool(payload: dict[str, object], key: str, default: bool) -> bool:
    if key not in payload:
        return default
    value = payload[key]
    if isinstance(value, bool):
        return value
    raise ValueError(f"{key} must be a boolean")


def _optional_int(payload: dict[str, object], key: str, default: int) -> int:
    if key not in payload:
        return default
    value = payload[key]
    if isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    if isinstance(value, int):
        return value
    raise ValueError(f"{key} must be an integer")


def _optional_string(payload: dict[str, object], key: str, default: str) -> str:
    if key not in payload:
        return default
    value = payload[key]
    if isinstance(value, str):
        return value
    raise ValueError(f"{key} must be a string")


def _optional_nullable_string(
    payload: dict[str, object],
    key: str,
    default: str | None,
) -> str | None:
    if key not in payload:
        return default
    value = payload[key]
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"{key} must be a string or null")
