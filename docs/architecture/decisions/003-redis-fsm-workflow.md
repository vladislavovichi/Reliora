# ADR 003 — Redis FSM for bot conversation state

**Status:** Accepted

## Context

The Telegram bot conducts multi-step conversations with clients (e.g. "describe your issue → choose category → confirm"). Aiogram supports several FSM storage backends:

1. **In-memory storage** — zero ops overhead, lost on restart.
2. **PostgreSQL storage** — durable, already provisioned, adds latency per state transition.
3. **Redis storage** — durable (with AOF/RDB), sub-millisecond reads, native TTL for automatic cleanup.

Separately, background workflow tasks (SLA deadlines, scheduled escalations) also need lightweight durable state.

## Decision

Use Redis for both aiogram FSM storage and the internal workflow runtime (`RedisWorkflowRuntime`).

## Reasons

- **Durability without DB coupling** — bot conversation state has a different lifecycle from ticket data. Storing it in Redis keeps the Postgres schema clean and avoids serialising Telegram message payloads into relational rows.
- **Automatic TTL** — abandoned conversations expire without a cleanup job.
- **Atomic Lua scripts** — the rate-limiter (`infrastructure/redis/`) uses an atomic INCR + EXPIRE Lua script to prevent race conditions, which is idiomatic Redis.
- **Already provisioned** — Redis is required for the workflow runtime regardless, so there is no additional infrastructure component.

## Consequences

- Redis must be treated as a required dependency, not optional. Health checks (`healthz`) reflect its status.
- FSM state is lost on Redis data loss (acceptable — users restart the conversation).
- The workflow runtime key schema is documented in `infrastructure/redis/runtime.py`; changes to key naming require a migration comment.
