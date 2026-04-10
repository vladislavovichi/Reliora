from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from application.services.authorization import AuthorizationServiceFactory
from application.services.diagnostics import DiagnosticsService
from application.services.helpdesk.service import HelpdeskServiceFactory
from backend.grpc.contracts import HelpdeskBackendClientFactory
from infrastructure.config.settings import Settings
from infrastructure.redis.contracts import (
    ChatRateLimiter,
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    SLADeadlineScheduler,
    SLATimeoutProcessor,
    TicketLiveSessionStore,
    TicketLockManager,
    TicketStreamConsumer,
    TicketStreamPublisher,
)


@dataclass(slots=True)
class RedisWorkflowRuntime:
    ticket_lock_manager: TicketLockManager
    global_rate_limiter: GlobalRateLimiter
    chat_rate_limiter: ChatRateLimiter
    operator_presence: OperatorPresenceHelper
    ticket_live_session_store: TicketLiveSessionStore
    operator_active_ticket_store: OperatorActiveTicketStore
    sla_deadline_scheduler: SLADeadlineScheduler
    ticket_stream_publisher: TicketStreamPublisher
    ticket_stream_consumer: TicketStreamConsumer
    sla_timeout_processor: SLATimeoutProcessor


@dataclass(slots=True)
class AppRuntime:
    settings: Settings
    db_engine: AsyncEngine
    db_session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    fsm_storage: BaseStorage
    redis_workflow: RedisWorkflowRuntime
    authorization_service_factory: AuthorizationServiceFactory
    helpdesk_service_factory: HelpdeskServiceFactory
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory
    diagnostics_service: DiagnosticsService
    dispatcher: Dispatcher | None = None
    bot: Bot | None = None
