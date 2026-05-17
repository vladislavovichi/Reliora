# ADR 002 — Local transformers for AI inference

**Status:** Accepted

## Context

The AI service needs to perform text classification (ticket category prediction), summarisation, and reply-draft generation. Options considered:

1. **Cloud LLM API (OpenAI, Anthropic, etc.)** — no infrastructure, pay-per-token.
2. **Self-hosted LLM (Ollama, vLLM, etc.)** — full control, higher ops overhead.
3. **HuggingFace `transformers` with small task-specific models** — local inference, no API cost, no external dependency.

## Decision

Use HuggingFace `transformers` with small task-specific models running inside the `ai_service` container. Cloud APIs are used only for reply-draft generation where generative quality matters more.

The `transformers` dependency is in a separate optional group (`[tool.poetry.group.local-ai]`) so the base image can omit it when only cloud AI is configured.

## Reasons

- **No per-request API cost** for classification tasks that are called on every new ticket.
- **No external network dependency** for the critical ticket intake path — the AI service can run fully air-gapped.
- **Low latency** for classification: a quantised sequence-classification model runs in <50 ms on CPU, acceptable for background category prediction.
- **Data residency** — ticket text never leaves the infrastructure boundary for classification.

## Consequences

- The `ai_service` container requires more RAM and optional GPU when `local-ai` deps are installed.
- Model weights must be bundled or downloaded at container startup; `ops/docker/` handles this.
- Upgrading models requires re-testing quality benchmarks (`tests/unit/ai/test_*_quality.py`).
- Reply drafts still make external API calls when an LLM is configured; those code paths must handle network failures gracefully.
