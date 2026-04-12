from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from application.services.audit import AuditTrail


async def test_audit_trail_uses_injected_correlation_id_provider() -> None:
    repository = AsyncMock()
    public_id = uuid4()
    trail = AuditTrail(
        repository=repository,
        correlation_id_provider=lambda: "corr-123",
    )

    await trail.write(
        action="ticket.close",
        entity_type="ticket",
        outcome="applied",
        entity_public_id=public_id,
        metadata={"public_id": public_id, "ignored": {1, 2, 3}},
    )

    repository.add.assert_awaited_once_with(
        action="ticket.close",
        entity_type="ticket",
        outcome="applied",
        actor_telegram_user_id=None,
        entity_id=None,
        entity_public_id=public_id,
        correlation_id="corr-123",
        metadata_json={"public_id": str(public_id)},
    )
