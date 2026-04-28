from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError

from application.ai.contracts import AIMessage, AIProvider, AIProviderError, AIProviderTimeoutError


class AICompletionFailureReason(StrEnum):
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    INVALID_JSON = "invalid_json"
    VALIDATION_FAILED = "validation_failed"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class AIJSONCompletionResult[SchemaT: BaseModel]:
    payload: SchemaT | None
    failure_reason: AICompletionFailureReason | None = None
    retry_count: int = 0


async def complete_json[SchemaT: BaseModel](
    *,
    provider: AIProvider,
    instructions: str,
    prompt: str,
    schema: type[SchemaT],
    max_output_tokens: int,
    temperature: float,
) -> SchemaT | None:
    result = await complete_json_with_metadata(
        provider=provider,
        instructions=instructions,
        prompt=prompt,
        schema=schema,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )
    return result.payload


async def complete_json_with_metadata[SchemaT: BaseModel](
    *,
    provider: AIProvider,
    instructions: str,
    prompt: str,
    schema: type[SchemaT],
    max_output_tokens: int,
    temperature: float,
) -> AIJSONCompletionResult[SchemaT]:
    messages = (
        AIMessage(role="system", content=instructions),
        AIMessage(role="user", content=prompt),
    )
    try:
        raw = await provider.complete(
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
    except TimeoutError as exc:
        return AIJSONCompletionResult(
            payload=None,
            failure_reason=_provider_failure_reason(AIProviderTimeoutError(str(exc))),
        )
    except AIProviderError as exc:
        return AIJSONCompletionResult(
            payload=None,
            failure_reason=_provider_failure_reason(exc),
        )

    result = _validate_json_payload(raw=raw, schema=schema)
    if result.payload is not None:
        return result

    retry_prompt = build_json_retry_prompt(prompt=prompt, schema=schema)
    try:
        retry_raw = await provider.complete(
            messages=(
                AIMessage(role="system", content=instructions),
                AIMessage(role="user", content=retry_prompt),
            ),
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
    except TimeoutError as exc:
        return AIJSONCompletionResult(
            payload=None,
            failure_reason=_provider_failure_reason(AIProviderTimeoutError(str(exc))),
            retry_count=1,
        )
    except AIProviderError as exc:
        return AIJSONCompletionResult(
            payload=None,
            failure_reason=_provider_failure_reason(exc),
            retry_count=1,
        )

    retry_result = _validate_json_payload(raw=retry_raw, schema=schema)
    return AIJSONCompletionResult(
        payload=retry_result.payload,
        failure_reason=retry_result.failure_reason,
        retry_count=1,
    )


def _validate_json_payload[SchemaT: BaseModel](
    *,
    raw: str,
    schema: type[SchemaT],
) -> AIJSONCompletionResult[SchemaT]:
    payload = extract_json_object(raw)
    if payload is None:
        return AIJSONCompletionResult(
            payload=None,
            failure_reason=AICompletionFailureReason.INVALID_JSON,
        )
    try:
        return AIJSONCompletionResult(payload=schema.model_validate(payload))
    except ValidationError:
        return AIJSONCompletionResult(
            payload=None,
            failure_reason=AICompletionFailureReason.VALIDATION_FAILED,
        )


def build_json_retry_prompt(*, prompt: str, schema: type[BaseModel]) -> str:
    return "\n".join(
        [
            prompt,
            "",
            "Предыдущий ответ не был валидным JSON для ожидаемой структуры.",
            "Return strictly valid JSON only, with no markdown and no surrounding explanation.",
            "Верни строго валидный JSON-объект без markdown, комментариев и пояснений вокруг.",
            "Структура должна соответствовать этой JSON Schema:",
            json.dumps(schema.model_json_schema(), ensure_ascii=False),
        ]
    )


def extract_json_object(raw: str) -> dict[str, Any] | None:
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


def _provider_failure_reason(exc: AIProviderError) -> AICompletionFailureReason:
    raw = getattr(exc, "failure_category", None)
    if raw == AICompletionFailureReason.TIMEOUT.value:
        return AICompletionFailureReason.TIMEOUT
    if raw == AICompletionFailureReason.PROVIDER_UNAVAILABLE.value:
        return AICompletionFailureReason.PROVIDER_UNAVAILABLE
    return AICompletionFailureReason.UNKNOWN
