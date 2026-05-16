from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError

from application.ai.contracts import AIMessage, AIProvider, AIProviderError, AIProviderTimeoutError


class AICompletionFailureReason(StrEnum):
    AI_UNAVAILABLE = "ai_unavailable"
    LOCAL_MODEL_LOAD_FAILED = "local_model_load_failed"
    LOCAL_MODEL_NOT_FOUND = "local_model_not_found"
    LOCAL_GENERATION_FAILED = "local_generation_failed"
    LOCAL_OUT_OF_MEMORY = "local_out_of_memory"
    GRPC_UNAVAILABLE = "grpc_unavailable"
    TIMEOUT = "timeout"
    INVALID_JSON = "invalid_json"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class AIJSONCompletionResult[SchemaT: BaseModel]:
    payload: SchemaT | None
    failure_reason: AICompletionFailureReason | None = None
    retry_count: int = 0


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
            expect_json=True,
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
            expect_json=True,
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
            failure_reason=AICompletionFailureReason.SCHEMA_VALIDATION_FAILED,
        )


def build_json_retry_prompt(*, prompt: str, schema: type[BaseModel]) -> str:
    return "\n".join(
        [
            prompt,
            "",
            "The previous response was not valid JSON for the expected structure.",
            "Return strictly valid JSON only, with no markdown and no surrounding explanation.",
            "The structure must match this JSON Schema:",
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
    for reason in AICompletionFailureReason:
        if raw == reason.value:
            return reason
    return AICompletionFailureReason.UNKNOWN
