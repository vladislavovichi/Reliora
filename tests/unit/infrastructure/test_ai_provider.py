from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest

from application.ai.contracts import AIMessage
from infrastructure.ai import local_transformers as local_transformers_module
from infrastructure.ai.local_transformers import LocalTransformersAIProvider
from infrastructure.ai.provider import build_ai_provider
from infrastructure.config.settings import AIConfig


def test_provider_factory_always_returns_local_transformers_provider() -> None:
    provider = build_ai_provider(AIConfig(model_id="custom/local-model"))

    assert isinstance(provider, LocalTransformersAIProvider)
    assert provider.model_id == "custom/local-model"


async def test_local_model_load_is_performed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"tokenizer": 0, "model": 0}

    class FakeTokenizer:
        eos_token = "</s>"
        eos_token_id = 1
        pad_token_id = None

    class FakeAutoTokenizer:
        @staticmethod
        def from_pretrained(*args: object, **kwargs: object) -> FakeTokenizer:
            del args, kwargs
            calls["tokenizer"] += 1
            return FakeTokenizer()

    class FakeModel:
        generation_config = SimpleNamespace(pad_token_id=None)

        def to(self, device: str) -> FakeModel:
            del device
            return self

        def eval(self) -> None:
            return None

    class FakeAutoModel:
        @staticmethod
        def from_pretrained(*args: object, **kwargs: object) -> FakeModel:
            del args, kwargs
            calls["model"] += 1
            return FakeModel()

    fake_torch = ModuleType("torch")
    fake_torch.float16 = "float16"  # type: ignore[attr-defined]
    fake_torch.bfloat16 = "bfloat16"  # type: ignore[attr-defined]
    fake_torch.float32 = "float32"  # type: ignore[attr-defined]
    fake_torch.cuda = SimpleNamespace(is_available=lambda: False)  # type: ignore[attr-defined]
    fake_torch.backends = SimpleNamespace(  # type: ignore[attr-defined]
        mps=SimpleNamespace(is_available=lambda: False)
    )
    fake_transformers = ModuleType("transformers")
    fake_transformers.AutoTokenizer = FakeAutoTokenizer  # type: ignore[attr-defined]
    fake_transformers.AutoModelForCausalLM = FakeAutoModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    provider = LocalTransformersAIProvider(
        configured_model_id="unit-test-model",
        model_path=None,
    )
    _run_to_thread_inline(monkeypatch)

    await provider.load()
    await provider.load()

    assert provider.is_loaded is True
    assert calls == {"tokenizer": 1, "model": 1}


async def test_generation_uses_configured_concurrency_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = 0
    max_active = 0

    async def to_thread(func: object, /, *args: object, **kwargs: object) -> object:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        result = func(*args, **kwargs)  # type: ignore[operator]
        active -= 1
        return result

    def complete_blocking(
        self: LocalTransformersAIProvider,
        messages: tuple[AIMessage, ...],
        max_output_tokens: int,
        temperature: float,
    ) -> str:
        del self, messages, max_output_tokens, temperature
        return "{}"

    monkeypatch.setattr(local_transformers_module.asyncio, "to_thread", to_thread)
    monkeypatch.setattr(
        LocalTransformersAIProvider,
        "_complete_blocking",
        complete_blocking,
    )
    provider = LocalTransformersAIProvider(
        configured_model_id="unit-test-model",
        model_path=None,
        max_concurrent_requests=1,
    )

    await asyncio.gather(
        provider.complete(messages=(), max_output_tokens=10, temperature=0),
        provider.complete(messages=(), max_output_tokens=10, temperature=0),
    )

    assert max_active == 1


async def test_json_expected_mode_adds_local_json_only_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[AIMessage, ...]] = []

    def complete_blocking(
        self: LocalTransformersAIProvider,
        messages: tuple[AIMessage, ...],
        max_output_tokens: int,
        temperature: float,
    ) -> str:
        del self, max_output_tokens, temperature
        captured.append(messages)
        return "{}"

    monkeypatch.setattr(
        LocalTransformersAIProvider,
        "_complete_blocking",
        complete_blocking,
    )
    _run_to_thread_inline(monkeypatch)
    provider = LocalTransformersAIProvider(
        configured_model_id="unit-test-model",
        model_path=None,
    )

    await provider.complete(
        messages=(
            AIMessage(role="system", content="Base instruction."),
            AIMessage(role="user", content="Return status."),
        ),
        max_output_tokens=10,
        temperature=0,
        expect_json=True,
    )

    assert "Base instruction." in captured[0][0].content
    assert "Return strictly valid JSON only" in captured[0][0].content
    assert "Do not use Markdown" in captured[0][0].content


def _run_to_thread_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def to_thread(func: object, /, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[operator]

    monkeypatch.setattr(local_transformers_module.asyncio, "to_thread", to_thread)
