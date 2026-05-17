# ADR 005 — Composition over mixin inheritance in HelpdeskService

**Status:** Accepted

## Context

`HelpdeskService` started as a flat class. As operations accumulated it was split into five mixin classes (`HelpdeskTicketOperations`, `HelpdeskCatalogOperations`, `HelpdeskOperatorOperations`, `HelpdeskSLAOperations`, `HelpdeskAIOperations`), each composed into `HelpdeskService` via multiple inheritance.

The problem: Python's MRO is implicit and can produce surprising behaviour when mixin classes share base classes or are reordered. Attributes like `_components` and `_audit` were declared as class-level annotations on each mixin but actually lived on the concrete `HelpdeskService` instance — a fragile coupling that mypy accepted but that was easy to break silently during refactoring.

## Decision

Replace multiple inheritance with explicit composition:

1. A shared `_HelpdeskContext` dataclass holds all cross-cutting dependencies (`HelpdeskComponents`, `AuditTrail`, `SLADeadlineScheduler`) and exposes helper methods (`ensure_permission`, `require_permission_if_actor`, `sync_sla_deadline`).
2. Each operation class receives `_HelpdeskContext` via `__init__` and stores it as `self._ctx`.
3. `HelpdeskService` is a plain `@dataclass` with five private handler instances. Every public method is a one-line delegation to the appropriate handler.

## Reasons

- **No implicit MRO** — the delegation graph is explicit and visible in `service.py`.
- **Testable handlers** — each handler class can be instantiated with a mock `_HelpdeskContext` independently.
- **`_sync_sla_deadline` is shared cleanly** — previously it was defined in `HelpdeskSLAOperations` but needed by ticket and catalog handlers via `HelpdeskSLASync` (another mixin). Now it is a method on `_HelpdeskContext` accessed by all handlers without any inheritance.

## Consequences

- `service.py` now contains ~56 one-line delegation methods. This is verbose but completely explicit — the full public API of `HelpdeskService` is visible in one file.
- Adding a new operation means: implement in the relevant handler, add a delegation method in `service.py`.
- The five handler classes (`HelpdeskTicketOperations`, etc.) are now standalone classes, not mixins, and can be unit-tested independently.
