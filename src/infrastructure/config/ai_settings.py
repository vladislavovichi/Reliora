from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from application.use_cases.ai.settings import (
    AISettingsRepository,
    RuntimeAISettings,
    build_ai_settings_from_update,
    normalize_ai_settings,
)


@dataclass(slots=True)
class JsonAISettingsRepository(AISettingsRepository):
    path: Path
    defaults: RuntimeAISettings

    def get(self) -> RuntimeAISettings:
        if not self.path.exists():
            return normalize_ai_settings(self.defaults)
        try:
            raw_payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return normalize_ai_settings(self.defaults)
        if not isinstance(raw_payload, dict):
            return normalize_ai_settings(self.defaults)
        try:
            return build_ai_settings_from_update(
                normalize_ai_settings(self.defaults),
                _string_key_dict(raw_payload),
            )
        except ValueError:
            return normalize_ai_settings(self.defaults)

    def save(self, settings: RuntimeAISettings) -> RuntimeAISettings:
        normalized = normalize_ai_settings(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(asdict(normalized), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary_path.replace(self.path)
        return normalized


def build_runtime_ai_settings_defaults(default_model_id: str | None) -> RuntimeAISettings:
    return RuntimeAISettings(default_model_id=default_model_id)


def _string_key_dict(payload: dict[object, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(key, str):
            result[key] = _json_value(value)
    return result


def _json_value(value: object) -> object:
    if value is None or isinstance(value, str | int | bool):
        return value
    return None
