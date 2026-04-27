from __future__ import annotations

import asyncio
import http.client
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ai_service.grpc.client import build_ai_service_client_factory
from app.runtime import RedisWorkflowRuntime
from application.contracts.ai import AIServiceClientFactory
from application.contracts.runtime import SLADeadlineScheduler
from application.services.authorization import (
    AuthorizationService,
    AuthorizationServiceFactory,
)
from application.services.diagnostics import DiagnosticsService
from application.services.helpdesk.components import HelpdeskExportRenderers
from application.services.helpdesk.service import HelpdeskService, HelpdeskServiceFactory
from application.use_cases.ai.settings import AISettingsProvider, InMemoryAISettingsRepository
from backend.grpc.client import build_helpdesk_backend_client_factory as build_grpc_client_factory
from backend.grpc.contracts import HelpdeskBackendClientFactory
from infrastructure.config.ai_settings import (
    JsonAISettingsRepository,
    build_runtime_ai_settings_defaults,
)
from infrastructure.config.settings import MiniAppConfig, Settings
from infrastructure.db.repositories.ai import SqlAlchemyTicketAISummaryRepository
from infrastructure.db.repositories.audit import SqlAlchemyAuditLogRepository
from infrastructure.db.repositories.catalog import (
    SqlAlchemyMacroRepository,
    SqlAlchemySLAPolicyRepository,
    SqlAlchemyTagRepository,
    SqlAlchemyTicketCategoryRepository,
    SqlAlchemyTicketTagRepository,
)
from infrastructure.db.repositories.feedback import SqlAlchemyTicketFeedbackRepository
from infrastructure.db.repositories.operator_invites import SqlAlchemyOperatorInviteCodeRepository
from infrastructure.db.repositories.operators import SqlAlchemyOperatorRepository
from infrastructure.db.repositories.tickets import (
    SqlAlchemyTicketEventRepository,
    SqlAlchemyTicketInternalNoteRepository,
    SqlAlchemyTicketMessageRepository,
    SqlAlchemyTicketRepository,
)
from infrastructure.db.session import ping_database_engine, session_scope
from infrastructure.exports.analytics_snapshot_csv import render_analytics_snapshot_csv
from infrastructure.exports.analytics_snapshot_html import render_analytics_snapshot_html
from infrastructure.exports.ticket_report_csv import render_ticket_report_csv
from infrastructure.exports.ticket_report_html import render_ticket_report_html
from infrastructure.redis.client import ping_redis_client
from infrastructure.redis.locks import RedisTicketLockManager
from infrastructure.redis.operator_context import RedisTicketLiveSessionStore
from infrastructure.redis.presence import RedisOperatorPresenceHelper
from infrastructure.redis.rate_limit import RedisChatRateLimiter, RedisGlobalRateLimiter
from infrastructure.redis.sla import RedisSLADeadlineScheduler, RedisSLATimeoutProcessor
from infrastructure.redis.streams import (
    RedisTicketStreamConsumer,
    RedisTicketStreamPublisher,
)
from infrastructure.runtime_context import get_correlation_id


def _ping_mini_app_http_blocking(config: MiniAppConfig) -> bool:
    host = config.listen_host
    if host == "0.0.0.0":
        host = "127.0.0.1"

    connection = http.client.HTTPConnection(host=host, port=config.port, timeout=5)
    try:
        connection.request("GET", "/healthz")
        response = connection.getresponse()
        response.read()
        return response.status == 200
    finally:
        connection.close()


async def ping_mini_app_http(config: MiniAppConfig) -> bool:
    return await asyncio.to_thread(_ping_mini_app_http_blocking, config)


def build_authorization_service(
    session: AsyncSession,
    *,
    super_admin_telegram_user_ids: frozenset[int],
) -> AuthorizationService:
    return AuthorizationService(
        operator_repository=SqlAlchemyOperatorRepository(session),
        super_admin_telegram_user_ids=super_admin_telegram_user_ids,
    )


def build_authorization_service_factory(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    super_admin_telegram_user_ids: frozenset[int],
) -> AuthorizationServiceFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[AuthorizationService]:
        async with session_scope(session_factory) as session:
            yield build_authorization_service(
                session,
                super_admin_telegram_user_ids=super_admin_telegram_user_ids,
            )

    return provide


def build_helpdesk_service(
    session: AsyncSession,
    *,
    super_admin_telegram_user_ids: frozenset[int],
    ai_client_factory: AIServiceClientFactory,
    ai_settings_provider: AISettingsProvider | None = None,
    include_internal_notes_in_ticket_reports: bool = True,
    sla_deadline_scheduler: SLADeadlineScheduler | None = None,
) -> HelpdeskService:
    ticket_repository = SqlAlchemyTicketRepository(session)
    resolved_ai_settings_provider = ai_settings_provider or InMemoryAISettingsRepository()
    return HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_analytics_repository=ticket_repository,
        ticket_feedback_repository=SqlAlchemyTicketFeedbackRepository(session),
        ticket_ai_summary_repository=SqlAlchemyTicketAISummaryRepository(session),
        ticket_message_repository=SqlAlchemyTicketMessageRepository(session),
        ticket_internal_note_repository=SqlAlchemyTicketInternalNoteRepository(session),
        ticket_event_repository=SqlAlchemyTicketEventRepository(session),
        audit_log_repository=SqlAlchemyAuditLogRepository(session),
        operator_repository=SqlAlchemyOperatorRepository(session),
        operator_invite_repository=SqlAlchemyOperatorInviteCodeRepository(session),
        macro_repository=SqlAlchemyMacroRepository(session),
        sla_policy_repository=SqlAlchemySLAPolicyRepository(session),
        tag_repository=SqlAlchemyTagRepository(session),
        ticket_category_repository=SqlAlchemyTicketCategoryRepository(session),
        ticket_tag_repository=SqlAlchemyTicketTagRepository(session),
        ai_client_factory=ai_client_factory,
        ai_settings_provider=resolved_ai_settings_provider,
        export_renderers=HelpdeskExportRenderers(
            ticket_report_csv=render_ticket_report_csv,
            ticket_report_html=render_ticket_report_html,
            analytics_snapshot_csv=render_analytics_snapshot_csv,
            analytics_snapshot_html=render_analytics_snapshot_html,
        ),
        sla_deadline_scheduler=sla_deadline_scheduler,
        correlation_id_provider=get_correlation_id,
        super_admin_telegram_user_ids=super_admin_telegram_user_ids,
        include_internal_notes_in_ticket_reports=include_internal_notes_in_ticket_reports,
    )


def build_helpdesk_service_factory(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    super_admin_telegram_user_ids: frozenset[int],
    ai_client_factory: AIServiceClientFactory,
    ai_settings_provider: AISettingsProvider | None = None,
    include_internal_notes_in_ticket_reports: bool = True,
    sla_deadline_scheduler: SLADeadlineScheduler | None = None,
) -> HelpdeskServiceFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskService]:
        async with session_scope(session_factory) as session:
            yield build_helpdesk_service(
                session,
                super_admin_telegram_user_ids=super_admin_telegram_user_ids,
                ai_client_factory=ai_client_factory,
                ai_settings_provider=ai_settings_provider,
                include_internal_notes_in_ticket_reports=include_internal_notes_in_ticket_reports,
                sla_deadline_scheduler=sla_deadline_scheduler,
            )

    return provide


def build_helpdesk_backend_client_factory(
    settings: Settings,
) -> HelpdeskBackendClientFactory:
    return build_grpc_client_factory(
        settings.backend_service,
        auth_config=settings.backend_auth,
        resilience_config=settings.resilience,
    )


def build_helpdesk_ai_client_factory(settings: Settings) -> AIServiceClientFactory:
    return build_ai_service_client_factory(
        settings.ai_service,
        auth_config=settings.ai_service_auth,
        resilience_config=settings.resilience,
    )


def build_ai_settings_repository(settings: Settings) -> JsonAISettingsRepository:
    return JsonAISettingsRepository(
        path=settings.ai_runtime_settings.path,
        defaults=build_runtime_ai_settings_defaults(settings.ai.model_id),
    )


def build_redis_workflow_runtime(redis: Redis) -> RedisWorkflowRuntime:
    sla_deadline_scheduler = RedisSLADeadlineScheduler(redis)
    ticket_live_session_store = RedisTicketLiveSessionStore(redis)
    return RedisWorkflowRuntime(
        ticket_lock_manager=RedisTicketLockManager(redis),
        global_rate_limiter=RedisGlobalRateLimiter(redis),
        chat_rate_limiter=RedisChatRateLimiter(redis),
        operator_presence=RedisOperatorPresenceHelper(redis),
        ticket_live_session_store=ticket_live_session_store,
        operator_active_ticket_store=ticket_live_session_store,
        sla_deadline_scheduler=sla_deadline_scheduler,
        ticket_stream_publisher=RedisTicketStreamPublisher(redis),
        ticket_stream_consumer=RedisTicketStreamConsumer(redis),
        sla_timeout_processor=RedisSLATimeoutProcessor(sla_deadline_scheduler),
    )


def build_diagnostics_service(
    *,
    settings: Settings,
    db_engine: AsyncEngine,
    redis: Redis,
    backend_check: Callable[[], Awaitable[bool]],
    fsm_storage: BaseStorage,
    redis_workflow: RedisWorkflowRuntime,
    bot: Bot | None,
    dispatcher: Dispatcher | None,
) -> DiagnosticsService:
    return DiagnosticsService(
        database_check=lambda: ping_database_engine(db_engine),
        redis_check=lambda: ping_redis_client(redis),
        backend_check=backend_check,
        backend_auth_configured=bool(settings.backend_auth.token.strip()),
        dry_run=settings.app.dry_run,
        bot_configured=bool(settings.bot.token.strip()),
        bot_initialized=bot is not None,
        dispatcher_initialized=dispatcher is not None,
        fsm_storage_initialized=fsm_storage is not None,
        redis_workflow_initialized=redis_workflow is not None,
        mini_app_url_valid=settings.mini_app.public_url_is_valid,
        mini_app_url_detail=settings.mini_app.public_url_status_detail,
        mini_app_http_check=lambda: ping_mini_app_http(settings.mini_app),
        mini_app_http_target=settings.mini_app.healthcheck_url,
    )
