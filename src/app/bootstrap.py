from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.runtime import AppRuntime, RedisWorkflowRuntime
from app.runtime_factories import (
    build_authorization_service_factory,
    build_diagnostics_service,
    build_helpdesk_backend_client_factory,
    build_helpdesk_backend_server,
    build_helpdesk_service_factory,
    build_redis_workflow_runtime,
)
from bot.dispatcher import build_bot, build_dispatcher
from infrastructure.config.settings import Settings
from infrastructure.db.session import (
    build_engine,
    build_session_factory,
    dispose_engine,
    ping_database_engine,
)
from infrastructure.redis.client import (
    build_redis_client,
    close_redis_client,
    ping_redis_client,
)
from infrastructure.redis.fsm import build_fsm_storage


def _validate_startup_settings(settings: Settings) -> None:
    if settings.app.dry_run:
        return
    if not settings.bot.token.strip():
        raise RuntimeError("Невозможно запустить polling: BOT__TOKEN не задан.")


def _database_target(settings: Settings) -> str:
    return (
        settings.database.url
        or f"{settings.database.host}:{settings.database.port}/{settings.database.database}"
    )


def _redis_target(settings: Settings) -> str:
    return settings.redis.url or f"{settings.redis.host}:{settings.redis.port}/{settings.redis.db}"


async def _close_runtime_resources(
    *,
    db_engine: AsyncEngine | None = None,
    redis: Redis | None = None,
    fsm_storage: BaseStorage | None = None,
    bot: Bot | None = None,
) -> None:
    logger = logging.getLogger(__name__)

    if bot is not None:
        try:
            await bot.session.close()
        except Exception:
            logger.exception("Failed to close Telegram bot session cleanly.")

    if fsm_storage is not None:
        try:
            await fsm_storage.close()
        except Exception:
            logger.exception("Failed to close FSM storage cleanly.")

    if redis is not None:
        try:
            await close_redis_client(redis)
        except Exception:
            logger.exception("Failed to close Redis client cleanly.")

    if db_engine is not None:
        try:
            await dispose_engine(db_engine)
        except Exception:
            logger.exception("Failed to dispose SQLAlchemy engine cleanly.")


async def build_runtime(settings: Settings) -> AppRuntime:
    logger = logging.getLogger(__name__)
    _validate_startup_settings(settings)
    logger.info(
        "Initializing runtime dependencies database=%s redis=%s dry_run=%s",
        _database_target(settings),
        _redis_target(settings),
        settings.app.dry_run,
    )

    db_engine = build_engine(settings.database)
    db_session_factory = build_session_factory(db_engine)
    super_admin_telegram_user_ids = frozenset(settings.authorization.super_admin_telegram_user_ids)
    authorization_service_factory = build_authorization_service_factory(
        db_session_factory,
        super_admin_telegram_user_ids=super_admin_telegram_user_ids,
    )

    redis: Redis | None = None
    fsm_storage: BaseStorage | None = None
    redis_workflow: RedisWorkflowRuntime | None = None
    helpdesk_service_factory = None
    helpdesk_backend_client_factory = None
    diagnostics_service = None
    bot: Bot | None = None
    dispatcher: Dispatcher | None = None

    try:
        logger.info("Checking PostgreSQL connectivity.")
        await ping_database_engine(db_engine)
        logger.info("PostgreSQL connectivity check passed.")

        redis = build_redis_client(settings.redis)
        logger.info("Checking Redis connectivity.")
        await ping_redis_client(redis)
        logger.info("Redis connectivity check passed.")

        fsm_storage = build_fsm_storage(redis)
        redis_workflow = build_redis_workflow_runtime(redis)
        helpdesk_service_factory = build_helpdesk_service_factory(
            db_session_factory,
            super_admin_telegram_user_ids=super_admin_telegram_user_ids,
            sla_deadline_scheduler=redis_workflow.sla_deadline_scheduler,
        )
        helpdesk_backend_server = build_helpdesk_backend_server(
            helpdesk_service_factory=helpdesk_service_factory
        )
        helpdesk_backend_client_factory = build_helpdesk_backend_client_factory(
            helpdesk_backend_server
        )

        if settings.bot.token.strip():
            logger.info("Initializing Telegram bot runtime.")
            bot = build_bot(settings.bot)
            dispatcher = build_dispatcher(
                storage=fsm_storage,
                settings=settings,
                authorization_service_factory=authorization_service_factory,
                helpdesk_service_factory=helpdesk_service_factory,
                helpdesk_backend_client_factory=helpdesk_backend_client_factory,
                global_rate_limiter=redis_workflow.global_rate_limiter,
                chat_rate_limiter=redis_workflow.chat_rate_limiter,
                operator_presence=redis_workflow.operator_presence,
                ticket_live_session_store=redis_workflow.ticket_live_session_store,
                operator_active_ticket_store=redis_workflow.operator_active_ticket_store,
                ticket_lock_manager=redis_workflow.ticket_lock_manager,
                ticket_stream_publisher=redis_workflow.ticket_stream_publisher,
            )
        else:
            logger.info(
                "Telegram bot runtime is skipped because BOT__TOKEN is empty "
                "and dry-run mode is enabled."
            )

        diagnostics_service = build_diagnostics_service(
            settings=settings,
            db_engine=db_engine,
            redis=redis,
            fsm_storage=fsm_storage,
            redis_workflow=redis_workflow,
            bot=bot,
            dispatcher=dispatcher,
        )
        if dispatcher is not None:
            dispatcher.workflow_data["diagnostics_service"] = diagnostics_service

        logger.info("Runtime dependencies initialized successfully.")
        return AppRuntime(
            settings=settings,
            db_engine=db_engine,
            db_session_factory=db_session_factory,
            redis=redis,
            fsm_storage=fsm_storage,
            redis_workflow=redis_workflow,
            authorization_service_factory=authorization_service_factory,
            helpdesk_service_factory=helpdesk_service_factory,
            helpdesk_backend_client_factory=helpdesk_backend_client_factory,
            diagnostics_service=diagnostics_service,
            dispatcher=dispatcher,
            bot=bot,
        )
    except Exception:
        logger.exception("Runtime initialization failed.")
        await _close_runtime_resources(
            db_engine=db_engine,
            redis=redis,
            fsm_storage=fsm_storage,
            bot=bot,
        )
        raise


async def close_runtime(runtime: AppRuntime) -> None:
    logger = logging.getLogger(__name__)
    logger.info("Closing runtime resources.")
    await _close_runtime_resources(
        db_engine=runtime.db_engine,
        redis=runtime.redis,
        fsm_storage=runtime.fsm_storage,
        bot=runtime.bot,
    )
    logger.info("Runtime resources closed.")
