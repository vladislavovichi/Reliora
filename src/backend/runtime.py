from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from application.services.helpdesk.service import HelpdeskServiceFactory
from backend.grpc.server import HelpdeskBackendGrpcServer
from infrastructure.config.settings import Settings
from infrastructure.redis.runtime import RedisWorkflowRuntime


@dataclass(slots=True)
class BackendRuntime:
    settings: Settings
    db_engine: AsyncEngine
    db_session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    redis_workflow: RedisWorkflowRuntime
    helpdesk_service_factory: HelpdeskServiceFactory
    grpc_server: HelpdeskBackendGrpcServer
