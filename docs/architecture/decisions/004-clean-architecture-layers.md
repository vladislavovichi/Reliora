# ADR 004 — Clean architecture with enforced import boundaries

**Status:** Accepted

## Context

As the codebase grew, we needed a rule to prevent ad-hoc coupling between concerns — e.g. a Telegram handler importing SQLAlchemy directly, or a domain entity importing aiogram.

## Decision

Adopt a four-layer clean architecture and enforce import boundaries via an AST-based CI script:

```
domain  ←  application  ←  infrastructure  ←  bot / mini_app / backend
```

- **`domain`** — pure entities and repository protocols. No framework imports.
- **`application`** — use cases, service orchestration. Depends only on `domain` and Python stdlib.
- **`infrastructure`** — SQLAlchemy, Redis, aiogram, gRPC concrete implementations.
- **Transport adapters** (`bot`, `mini_app`, `backend`) — HTTP/gRPC/Telegram handlers. Depend on `infrastructure` and `application`.

The script `ops/scripts/check_architecture_boundaries.py` runs as the `architecture-boundaries` CI step and fails if any forbidden import is found (e.g. `bot` importing `infrastructure.db`).

## Reasons

- **Testability** — application layer tests (`tests/component/application/`) use stub repositories with no DB. This is only possible because the application layer depends on protocols, not SQLAlchemy.
- **Swappability** — the PostgreSQL repositories can be replaced without touching use cases.
- **Prevents regressions** — the boundary check catches accidental coupling before it reaches main.

## Consequences

- New infrastructure concerns (e.g. a caching layer) must be introduced as a protocol in `application/contracts/` first, then implemented in `infrastructure/`.
- The boundary checker must be updated when new top-level packages are added.
- Some boilerplate is required: every repository is defined twice (protocol in `domain/contracts/`, implementation in `infrastructure/db/repositories/`).
