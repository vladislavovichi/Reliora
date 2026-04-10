from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from application.services.authorization import Permission
from application.services.helpdesk.components import HelpdeskComponents
from application.services.stats import (
    AnalyticsWindow,
    HelpdeskAnalyticsSnapshot,
    HelpdeskOperationalStats,
)
from application.use_cases.tickets.summaries import OperatorRoleMutationResult, OperatorSummary


class HelpdeskOperatorOperations:
    _components: HelpdeskComponents
    _require_permission_if_actor: Callable[..., Awaitable[None]]

    async def list_operators(
        self,
        *,
        actor_telegram_user_id: int | None = None,
    ) -> Sequence[OperatorSummary]:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.operators.list_operators()

    async def promote_operator(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
        actor_telegram_user_id: int | None = None,
    ) -> OperatorRoleMutationResult:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.operators.promote_operator(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )

    async def revoke_operator(
        self,
        *,
        telegram_user_id: int,
        actor_telegram_user_id: int | None = None,
    ) -> OperatorRoleMutationResult | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.operators.revoke_operator(
            telegram_user_id=telegram_user_id,
        )

    async def get_operational_stats(
        self,
        *,
        actor_telegram_user_id: int | None = None,
    ) -> HelpdeskOperationalStats:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.stats.get_operational_stats()

    async def get_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        actor_telegram_user_id: int | None = None,
    ) -> HelpdeskAnalyticsSnapshot:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        return await self._components.stats.get_analytics_snapshot(window=window)
