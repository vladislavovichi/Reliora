from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from application.ai.contracts import AIMessage, AIProvider, AIProviderError, AIProviderTimeoutError
from infrastructure.config.settings import AIConfig

_DEFAULT_HUGGINGFACE_URL = "https://router.huggingface.co/v1/chat/completions"


@dataclass(slots=True, frozen=True)
class DisabledAIProvider:
    disabled_reason: str = "AI provider is not configured."

    @property
    def is_enabled(self) -> bool:
        return False

    @property
    def model_id(self) -> str | None:
        return None

    async def complete(
        self,
        *,
        messages: Sequence[AIMessage],
        max_output_tokens: int,
        temperature: float,
    ) -> str:
        del messages, max_output_tokens, temperature
        raise AIProviderError(self.disabled_reason)


@dataclass(slots=True, frozen=True)
class HuggingFaceAIProvider:
    model_id: str
    api_token: str
    base_url: str = _DEFAULT_HUGGINGFACE_URL
    timeout_seconds: float = 20.0

    @property
    def is_enabled(self) -> bool:
        return True

    async def complete(
        self,
        *,
        messages: Sequence[AIMessage],
        max_output_tokens: int,
        temperature: float,
    ) -> str:
        payload = {
            "model": self.model_id,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in messages
            ],
            "max_tokens": max_output_tokens,
            "temperature": temperature,
        }
        return await asyncio.to_thread(self._send_request, payload)

    def _send_request(self, payload: dict[str, Any]) -> str:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.base_url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise AIProviderError(f"Hugging Face request failed: {detail or exc.reason}") from exc
        except error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise AIProviderTimeoutError("Hugging Face request timed out.") from exc
            raise AIProviderError(f"Hugging Face request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise AIProviderTimeoutError("Hugging Face request timed out.") from exc

        choices = raw.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AIProviderError("Hugging Face response did not include choices.")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise AIProviderError("Hugging Face response choice is malformed.")

        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise AIProviderError("Hugging Face response message is malformed.")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("Hugging Face response content is empty.")
        return content


def build_ai_provider(config: AIConfig) -> AIProvider:
    provider_name = config.normalized_provider
    if provider_name == "disabled" or not config.model_id:
        return DisabledAIProvider()
    if provider_name != "huggingface":
        return DisabledAIProvider(disabled_reason=f"Unsupported AI provider: {provider_name}")
    if not config.api_token:
        return DisabledAIProvider(
            disabled_reason="Hugging Face token is missing. Set AI__API_TOKEN."
        )
    return HuggingFaceAIProvider(
        model_id=config.model_id,
        api_token=config.api_token,
        base_url=config.base_url or _DEFAULT_HUGGINGFACE_URL,
        timeout_seconds=config.timeout_seconds,
    )
