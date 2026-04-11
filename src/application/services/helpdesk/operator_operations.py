from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from application.contracts.actors import OperatorIdentity, RequestActor, actor_telegram_user_id
from application.services.audit import AuditTrail
from application.services.authorization import Permission
from application.services.helpdesk.components import HelpdeskComponents
from application.services.stats import (
    AnalyticsWindow,
    HelpdeskAnalyticsSnapshot,
    HelpdeskOperationalStats,
)
from application.use_cases.analytics.exports import (
    AnalyticsExportFormat,
    AnalyticsSection,
    AnalyticsSnapshotExport,
)
from application.use_cases.tickets.operator_invites import (
    OperatorInviteCodePreview,
    OperatorInviteCodeRedemptionResult,
    OperatorInviteCodeSummary,
)
from application.use_cases.tickets.summaries import OperatorRoleMutationResult, OperatorSummary


class HelpdeskOperatorOperations:
    _components: HelpdeskComponents
    _audit: AuditTrail
    _require_permission_if_actor: Callable[..., Awaitable[None]]

    async def list_operators(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[OperatorSummary]:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.operators.list_operators()

    async def promote_operator(
        self,
        operator: OperatorIdentity,
        actor: RequestActor | None = None,
    ) -> OperatorRoleMutationResult:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.operators.promote_operator(operator)
        await self._audit.write(
            action="operator.promote",
            entity_type="operator",
            outcome="applied" if result.changed else "noop",
            actor_telegram_user_id=actor_telegram_user_id(actor),
            metadata={
                "target_telegram_user_id": result.operator.telegram_user_id,
                "display_name": result.operator.display_name,
            },
        )
        return result

    async def revoke_operator(
        self,
        *,
        telegram_user_id: int,
        actor: RequestActor | None = None,
    ) -> OperatorRoleMutationResult | None:
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.operators.revoke_operator(
            telegram_user_id=telegram_user_id,
        )
        if result is None:
            await self._audit.write(
                action="operator.revoke",
                entity_type="operator",
                outcome="noop",
                actor_telegram_user_id=actor_telegram_user_id(actor),
                metadata={"target_telegram_user_id": telegram_user_id},
            )
            return None
        await self._audit.write(
            action="operator.revoke",
            entity_type="operator",
            outcome="applied",
            actor_telegram_user_id=actor_telegram_user_id(actor),
            metadata={
                "target_telegram_user_id": result.operator.telegram_user_id,
                "display_name": result.operator.display_name,
            },
        )
        return result

    async def create_operator_invite(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> OperatorInviteCodeSummary:
        actor_id = actor_telegram_user_id(actor)
        await self._require_permission_if_actor(
            permission=Permission.MANAGE_OPERATORS,
            actor_telegram_user_id=actor_id,
        )
        if actor_id is None:
            raise RuntimeError("Operator invite creation requires an actor.")
        result = await self._components.operators.create_operator_invite(
            created_by_telegram_user_id=actor_id
        )
        await self._audit.write(
            action="operator.invite.create",
            entity_type="operator_invite",
            outcome="generated",
            actor_telegram_user_id=actor_id,
            metadata={
                "expires_at": result.expires_at.isoformat(),
                "max_uses": result.max_uses,
            },
        )
        return result

    async def preview_operator_invite(
        self,
        *,
        code: str,
    ) -> OperatorInviteCodePreview:
        return await self._components.operators.preview_operator_invite(code=code)

    async def redeem_operator_invite(
        self,
        *,
        code: str,
        operator: OperatorIdentity,
    ) -> OperatorInviteCodeRedemptionResult:
        result = await self._components.operators.redeem_operator_invite(
            code=code,
            operator=operator,
        )
        await self._audit.write(
            action="operator.invite.redeem",
            entity_type="operator_invite",
            outcome="applied",
            actor_telegram_user_id=operator.telegram_user_id,
            metadata={
                "display_name": result.operator.operator.display_name,
                "expires_at": result.expires_at.isoformat(),
            },
        )
        return result

    async def get_operational_stats(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> HelpdeskOperationalStats:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.stats.get_operational_stats()

    async def get_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        actor: RequestActor | None = None,
    ) -> HelpdeskAnalyticsSnapshot:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.stats.get_analytics_snapshot(window=window)

    async def export_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        section: AnalyticsSection,
        format: AnalyticsExportFormat,
        actor: RequestActor | None = None,
    ) -> AnalyticsSnapshotExport:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        result = await self._components.operators.export_analytics_snapshot(
            window=window,
            section=section,
            format=format,
        )
        await self._audit.write(
            action="analytics.export",
            entity_type="analytics_snapshot",
            outcome="generated",
            actor_telegram_user_id=actor_telegram_user_id(actor),
            metadata={
                "window": window.value,
                "section": section.value,
                "format": format.value,
                "filename": result.filename,
            },
        )
        return result
