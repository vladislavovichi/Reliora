from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from aiogram import Bot

from application.contracts.actors import OperatorIdentity
from application.services.stats import AnalyticsWindow
from application.use_cases.ai.settings import AISettingsRepository, InMemoryAISettingsRepository
from application.use_cases.analytics.exports import AnalyticsExportFormat, AnalyticsSection
from application.use_cases.tickets.exports import TicketReportFormat
from backend.grpc.contracts import HelpdeskBackendClientFactory
from mini_app.auth import TelegramMiniAppUser
from mini_app.gateway.admin import MiniAppAdminGateway
from mini_app.gateway.ai import (
    MiniAppAIGateway,
    MiniAppAIRateLimiter,
    apply_ai_settings_to_snapshot_payload,
)
from mini_app.gateway.analytics import MiniAppAnalyticsGateway
from mini_app.gateway.dashboard import MiniAppDashboardGateway
from mini_app.gateway.exports import MiniAppExportsGateway
from mini_app.gateway.session import MiniAppSessionGateway
from mini_app.gateway.tickets import MiniAppTicketsGateway
from mini_app.responses import BinaryPayload


@dataclass(slots=True)
class MiniAppGateway:
    backend_client_factory: HelpdeskBackendClientFactory
    bot: Bot
    bot_username: str | None = None
    ai_settings_repository: AISettingsRepository = field(
        default_factory=InMemoryAISettingsRepository
    )
    ai_rate_limiter: MiniAppAIRateLimiter = field(default_factory=MiniAppAIRateLimiter)
    _session: MiniAppSessionGateway = field(init=False)
    _dashboard: MiniAppDashboardGateway = field(init=False)
    _tickets: MiniAppTicketsGateway = field(init=False)
    _ai: MiniAppAIGateway = field(init=False)
    _analytics: MiniAppAnalyticsGateway = field(init=False)
    _exports: MiniAppExportsGateway = field(init=False)
    _admin: MiniAppAdminGateway = field(init=False)

    def __post_init__(self) -> None:
        self._session = MiniAppSessionGateway(self.backend_client_factory)
        self._dashboard = MiniAppDashboardGateway(self.backend_client_factory)
        self._tickets = MiniAppTicketsGateway(self.backend_client_factory, self.bot)
        self._ai = MiniAppAIGateway(
            backend_client_factory=self.backend_client_factory,
            ai_settings_repository=self.ai_settings_repository,
            ai_rate_limiter=self.ai_rate_limiter,
        )
        self._analytics = MiniAppAnalyticsGateway(self.backend_client_factory)
        self._exports = MiniAppExportsGateway(self.backend_client_factory)
        self._admin = MiniAppAdminGateway(
            backend_client_factory=self.backend_client_factory,
            ai_settings_repository=self.ai_settings_repository,
            bot_username=self.bot_username,
        )

    async def get_session(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        return await self._session.get_session(user=user)

    async def get_dashboard(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        return await self._dashboard.get_dashboard(user=user)

    async def get_operator_dashboard(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        return await self._dashboard.get_operator_dashboard(user=user)

    async def list_queue(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        return await self._tickets.list_queue(user=user)

    async def take_next_ticket(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        return await self._tickets.take_next_ticket(user=user)

    async def list_my_tickets(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        return await self._tickets.list_my_tickets(user=user)

    async def list_archive(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        return await self._tickets.list_archive(user=user)

    async def get_ticket_workspace(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        payload = await self._tickets.get_ticket_workspace(
            user=user,
            ticket_public_id=ticket_public_id,
        )
        if payload.get("ai") is not None:
            payload["ai"] = apply_ai_settings_to_snapshot_payload(
                payload["ai"],
                ai_settings_repository=self.ai_settings_repository,
            )
        return payload

    async def refresh_ticket_ai_summary(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        return await self._ai.refresh_ticket_ai_summary(
            user=user,
            ticket_public_id=ticket_public_id,
        )

    async def generate_ticket_reply_draft(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        return await self._ai.generate_ticket_reply_draft(
            user=user,
            ticket_public_id=ticket_public_id,
        )

    async def take_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        return await self._tickets.take_ticket(user=user, ticket_public_id=ticket_public_id)

    async def close_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        return await self._tickets.close_ticket(user=user, ticket_public_id=ticket_public_id)

    async def escalate_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
    ) -> dict[str, Any]:
        return await self._tickets.escalate_ticket(user=user, ticket_public_id=ticket_public_id)

    async def assign_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
        operator_identity: OperatorIdentity,
    ) -> dict[str, Any]:
        return await self._tickets.assign_ticket(
            user=user,
            ticket_public_id=ticket_public_id,
            operator_identity=operator_identity,
        )

    async def add_note(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
        text: str,
    ) -> dict[str, Any]:
        return await self._tickets.add_note(
            user=user,
            ticket_public_id=ticket_public_id,
            text=text,
        )

    async def apply_macro(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
        macro_id: int,
    ) -> dict[str, Any]:
        return await self._tickets.apply_macro(
            user=user,
            ticket_public_id=ticket_public_id,
            macro_id=macro_id,
        )

    async def get_analytics(
        self,
        *,
        user: TelegramMiniAppUser,
        window: AnalyticsWindow,
    ) -> dict[str, Any]:
        return await self._analytics.get_analytics(user=user, window=window)

    async def export_ticket(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: UUID,
        format: TicketReportFormat,
    ) -> BinaryPayload:
        return await self._exports.export_ticket(
            user=user,
            ticket_public_id=ticket_public_id,
            format=format,
        )

    async def export_analytics(
        self,
        *,
        user: TelegramMiniAppUser,
        window: AnalyticsWindow,
        section: AnalyticsSection,
        format: AnalyticsExportFormat,
    ) -> BinaryPayload:
        return await self._analytics.export_analytics(
            user=user,
            window=window,
            section=section,
            format=format,
        )

    async def list_operators(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        return await self._admin.list_operators(user=user)

    async def create_operator_invite(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        return await self._admin.create_operator_invite(user=user)

    async def get_ai_settings(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        return await self._admin.get_ai_settings(user=user)

    async def update_ai_settings(
        self,
        *,
        user: TelegramMiniAppUser,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._admin.update_ai_settings(user=user, payload=payload)
