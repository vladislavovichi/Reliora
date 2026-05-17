# ADR 001 — gRPC between mini-app / bot and backend

**Status:** Accepted

## Context

The system has four processes: Telegram bot (`app`), Mini App HTTP gateway (`mini_app`), backend business-logic service (`backend`), and AI service (`ai_service`). The bot and mini-app need to call helpdesk operations. We considered three transport options:

1. **In-process function calls** — run all code in one process.
2. **REST/HTTP** — lightweight, familiar, tool support is excellent.
3. **gRPC** — binary protocol, contract-first via `.proto`, strongly typed generated clients.

## Decision

Use gRPC for all inter-service calls: bot→backend, mini-app→backend, backend→ai-service.

## Reasons

- **Contract-first development** — `.proto` files act as the single source of truth for the API surface. The CI job `grpc-contracts` fails if generated code drifts from the proto, preventing accidental breakage.
- **Strong typing end-to-end** — generated stubs give mypy-checkable clients without manual serialization code.
- **Separate deployment** — the backend service runs in its own container with its own DB session pool. This lets us scale independently and prevents the bot from holding DB connections during long-running Telegram polling cycles.
- **Auth token per service** — each caller sends a shared secret (`x-helpdesk-internal-token`). With HTTP we would need the same mechanism; gRPC metadata makes it explicit.

## Consequences

- All API changes require updating the `.proto` file and regenerating stubs (`make proto`).
- Local development requires all services to be running or uses the Docker Compose stack.
- gRPC error codes (NOT_FOUND, ALREADY_EXISTS, …) are translated to application errors in `backend/grpc/translators*.py`; this mapping must be kept in sync when new error types are added.
