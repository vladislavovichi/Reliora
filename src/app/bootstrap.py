from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from application.services.authorization import (
    AuthorizationService,
    AuthorizationServiceFactory,
)
from application.services.helpdesk import HelpdeskService, HelpdeskServiceFactory
from bot.dispatcher import build_bot, build_dispatcher
from infrastructure.config import Settings
from infrastructure.db.repositories import (
    SqlAlchemyMacroRepository,
    SqlAlchemyOperatorRepository,
    SqlAlchemySLAPolicyRepository,
    SqlAlchemyTagRepository,
    SqlAlchemyTicketEventRepository,
    SqlAlchemyTicketMessageRepository,
    SqlAlchemyTicketRepository,
    SqlAlchemyTicketTagRepository,
)
from infrastructure.db.session import (
    build_engine,
    build_session_factory,
    dispose_engine,
    session_scope,
)
from infrastructure.redis.client import (
    build_redis_client,
    close_redis_client,
    ping_redis_client,
)
from infrastructure.redis.contracts import (
    ChatRateLimiter,
    GlobalRateLimiter,
    OperatorPresenceHelper,
    SLADeadlineScheduler,
    SLATimeoutProcessor,
    TicketLockManager,
    TicketStreamConsumer,
    TicketStreamPublisher,
)
from infrastructure.redis.locks import RedisTicketLockManager
from infrastructure.redis.presence import RedisOperatorPresenceHelper
from infrastructure.redis.rate_limit import RedisChatRateLimiter, RedisGlobalRateLimiter
from infrastructure.redis.sla import RedisSLADeadlineScheduler, RedisSLATimeoutProcessor
from infrastructure.redis.streams import (
    RedisTicketStreamConsumer,
    RedisTicketStreamPublisher,
)


@dataclass(slots=True)
class RedisWorkflowRuntime:
    ticket_lock_manager: TicketLockManager
    global_rate_limiter: GlobalRateLimiter
    chat_rate_limiter: ChatRateLimiter
    operator_presence: OperatorPresenceHelper
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
    redis_workflow: RedisWorkflowRuntime
    authorization_service_factory: AuthorizationServiceFactory
    helpdesk_service_factory: HelpdeskServiceFactory
    dispatcher: Dispatcher | None = None
    bot: Bot | None = None


def build_authorization_service(
    session: AsyncSession,
    *,
    super_admin_telegram_user_id: int,
) -> AuthorizationService:
    return AuthorizationService(
        operator_repository=SqlAlchemyOperatorRepository(session),
        super_admin_telegram_user_id=super_admin_telegram_user_id,
    )


def build_authorization_service_factory(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    super_admin_telegram_user_id: int,
) -> AuthorizationServiceFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[AuthorizationService]:
        async with session_scope(session_factory) as session:
            yield build_authorization_service(
                session,
                super_admin_telegram_user_id=super_admin_telegram_user_id,
            )

    return provide


def build_helpdesk_service(
    session: AsyncSession,
    *,
    sla_deadline_scheduler: SLADeadlineScheduler | None = None,
) -> HelpdeskService:
    return HelpdeskService(
        ticket_repository=SqlAlchemyTicketRepository(session),
        ticket_message_repository=SqlAlchemyTicketMessageRepository(session),
        ticket_event_repository=SqlAlchemyTicketEventRepository(session),
        operator_repository=SqlAlchemyOperatorRepository(session),
        macro_repository=SqlAlchemyMacroRepository(session),
        sla_policy_repository=SqlAlchemySLAPolicyRepository(session),
        tag_repository=SqlAlchemyTagRepository(session),
        ticket_tag_repository=SqlAlchemyTicketTagRepository(session),
        sla_deadline_scheduler=sla_deadline_scheduler,
    )


def build_helpdesk_service_factory(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    sla_deadline_scheduler: SLADeadlineScheduler | None = None,
) -> HelpdeskServiceFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskService]:
        async with session_scope(session_factory) as session:
            yield build_helpdesk_service(
                session,
                sla_deadline_scheduler=sla_deadline_scheduler,
            )

    return provide


def build_redis_workflow_runtime(redis: Redis) -> RedisWorkflowRuntime:
    sla_deadline_scheduler = RedisSLADeadlineScheduler(redis)
    return RedisWorkflowRuntime(
        ticket_lock_manager=RedisTicketLockManager(redis),
        global_rate_limiter=RedisGlobalRateLimiter(redis),
        chat_rate_limiter=RedisChatRateLimiter(redis),
        operator_presence=RedisOperatorPresenceHelper(redis),
        sla_deadline_scheduler=sla_deadline_scheduler,
        ticket_stream_publisher=RedisTicketStreamPublisher(redis),
        ticket_stream_consumer=RedisTicketStreamConsumer(redis),
        sla_timeout_processor=RedisSLATimeoutProcessor(sla_deadline_scheduler),
    )


async def build_runtime(settings: Settings) -> AppRuntime:
    db_engine = build_engine(settings.database)
    db_session_factory = build_session_factory(db_engine)
    redis = build_redis_client(settings.redis)
    redis_workflow = build_redis_workflow_runtime(redis)
    authorization_service_factory = build_authorization_service_factory(
        db_session_factory,
        super_admin_telegram_user_id=settings.authorization.super_admin_telegram_user_id,
    )
    helpdesk_service_factory = build_helpdesk_service_factory(
        db_session_factory,
        sla_deadline_scheduler=redis_workflow.sla_deadline_scheduler,
    )
    bot: Bot | None = None

    try:
        await ping_redis_client(redis)

        dispatcher: Dispatcher | None = None
        if settings.bot.token:
            bot = build_bot(settings.bot)
            dispatcher = build_dispatcher(
                settings=settings,
                authorization_service_factory=authorization_service_factory,
                helpdesk_service_factory=helpdesk_service_factory,
                global_rate_limiter=redis_workflow.global_rate_limiter,
                chat_rate_limiter=redis_workflow.chat_rate_limiter,
                operator_presence=redis_workflow.operator_presence,
                ticket_lock_manager=redis_workflow.ticket_lock_manager,
                ticket_stream_publisher=redis_workflow.ticket_stream_publisher,
            )

        return AppRuntime(
            settings=settings,
            db_engine=db_engine,
            db_session_factory=db_session_factory,
            redis=redis,
            redis_workflow=redis_workflow,
            authorization_service_factory=authorization_service_factory,
            helpdesk_service_factory=helpdesk_service_factory,
            dispatcher=dispatcher,
            bot=bot,
        )
    except Exception:
        if bot is not None:
            await bot.session.close()
        await close_redis_client(redis)
        await dispose_engine(db_engine)
        raise


async def close_runtime(runtime: AppRuntime) -> None:
    if runtime.bot is not None:
        await runtime.bot.session.close()

    await close_redis_client(runtime.redis)
    await dispose_engine(runtime.db_engine)
