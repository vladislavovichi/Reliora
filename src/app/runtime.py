from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from application.services.authorization import AuthorizationServiceFactory
from application.services.diagnostics import DiagnosticsService
from backend.grpc.contracts import HelpdeskBackendClientFactory
from infrastructure.config.settings import Settings
from infrastructure.redis.runtime import RedisWorkflowRuntime


@dataclass(slots=True)
class AppRuntime:
    settings: Settings
    db_engine: AsyncEngine
    db_session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    fsm_storage: BaseStorage
    redis_workflow: RedisWorkflowRuntime
    authorization_service_factory: AuthorizationServiceFactory
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory
    diagnostics_service: DiagnosticsService
    dispatcher: Dispatcher | None = None
    bot: Bot | None = None
