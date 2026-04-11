from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from domain.contracts.repositories import AuditLogRepository
from infrastructure.runtime_context import get_correlation_id


@dataclass(slots=True)
class AuditTrail:
    repository: AuditLogRepository

    async def write(
        self,
        *,
        action: str,
        entity_type: str,
        outcome: str,
        actor_telegram_user_id: int | None = None,
        entity_id: int | None = None,
        entity_public_id: UUID | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        await self.repository.add(
            action=action,
            entity_type=entity_type,
            outcome=outcome,
            actor_telegram_user_id=actor_telegram_user_id,
            entity_id=entity_id,
            entity_public_id=entity_public_id,
            correlation_id=get_correlation_id(),
            metadata_json=_normalize_metadata(metadata),
        )


def _normalize_metadata(metadata: Mapping[str, object] | None) -> dict[str, object] | None:
    if metadata is None:
        return None
    normalized = {
        key: _normalize_value(value)
        for key, value in metadata.items()
        if _is_supported_audit_value(value)
    }
    return normalized or None


def _normalize_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _normalize_value(item)
            for key, item in value.items()
            if isinstance(key, str) and _is_supported_audit_value(item)
        }
    return value


def _is_supported_audit_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, UUID):
        return True
    if isinstance(value, tuple):
        return all(_is_supported_audit_value(item) for item in value)
    if isinstance(value, list):
        return all(_is_supported_audit_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_supported_audit_value(item) for key, item in value.items()
        )
    return False
