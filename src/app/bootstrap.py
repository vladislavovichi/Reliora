from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.runtime import AppRuntime, RedisWorkflowRuntime
from app.runtime_factories import (
    build_ai_settings_repository,
    build_authorization_service_factory,
    build_diagnostics_service,
    build_helpdesk_ai_client_factory,
    build_helpdesk_backend_client_factory,
    build_helpdesk_service_factory,
    build_redis_workflow_runtime,
)
from backend.grpc.client import ping_helpdesk_backend
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
from infrastructure.startup_checks import (
    StartupDependencyCheck,
    run_startup_dependency_checks,
    validate_app_startup_settings,
)


def _database_target(settings: Settings) -> str:
    return (
        settings.database.url
        or f"{settings.database.host}:{settings.database.port}/{settings.database.database}"
    )


def _redis_target(settings: Settings) -> str:
    return settings.redis.url or f"{settings.redis.host}:{settings.redis.port}/{settings.redis.db}"


def _backend_target(settings: Settings) -> str:
    return settings.backend_service.target


def _log_mini_app_configuration(logger: logging.Logger, settings: Settings) -> None:
    if settings.mini_app.public_url_is_valid:
        logger.info(
            "Mini App launch enabled public_url=%s host=%s temporary=%s healthcheck=%s",
            settings.mini_app.telegram_launch_url,
            settings.mini_app.public_url_hostname or "<unknown>",
            settings.mini_app.public_url_looks_temporary,
            settings.mini_app.healthcheck_url,
        )
        return

    logger.warning(
        (
            "Mini App launch disabled detail=%s configured_public_url=%s "
            "host=%s temporary=%s healthcheck=%s"
        ),
        settings.mini_app.public_url_status_detail,
        settings.mini_app.public_url or "<not-set>",
        settings.mini_app.public_url_hostname or "<unknown>",
        settings.mini_app.public_url_looks_temporary,
        settings.mini_app.healthcheck_url,
    )


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
        except (OSError, RuntimeError):
            logger.exception("Failed to close Telegram bot session cleanly.")

    if fsm_storage is not None:
        try:
            await fsm_storage.close()
        except (OSError, RedisError, RuntimeError):
            logger.exception("Failed to close FSM storage cleanly.")

    if redis is not None:
        try:
            await close_redis_client(redis)
        except (OSError, RedisError, RuntimeError):
            logger.exception("Failed to close Redis client cleanly.")

    if db_engine is not None:
        try:
            await dispose_engine(db_engine)
        except (OSError, RuntimeError, SQLAlchemyError):
            logger.exception("Failed to dispose SQLAlchemy engine cleanly.")


async def build_runtime(settings: Settings) -> AppRuntime:
    logger = logging.getLogger(__name__)
    try:
        validate_app_startup_settings(settings)
    except RuntimeError:
        logger.exception("Runtime startup configuration is invalid.")
        raise
    logger.info(
        "Initializing runtime dependencies database=%s redis=%s backend=%s dry_run=%s",
        _database_target(settings),
        _redis_target(settings),
        _backend_target(settings),
        settings.app.dry_run,
    )
    _log_mini_app_configuration(logger, settings)

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
        redis = build_redis_client(settings.redis)
        await run_startup_dependency_checks(
            component="bot",
            checks=(
                StartupDependencyCheck(
                    name="postgresql",
                    target=_database_target(settings),
                    check=lambda: ping_database_engine(db_engine),
                ),
                StartupDependencyCheck(
                    name="redis",
                    target=_redis_target(settings),
                    check=lambda: ping_redis_client(redis),
                ),
                StartupDependencyCheck(
                    name="backend_grpc",
                    target=settings.backend_service.target,
                    check=lambda: ping_helpdesk_backend(
                        settings.backend_service,
                        auth_config=settings.backend_auth,
                        resilience_config=settings.resilience,
                    ),
                ),
            ),
            settings=settings,
            logger=logger,
        )

        fsm_storage = build_fsm_storage(redis)
        redis_workflow = build_redis_workflow_runtime(redis)
        ai_client_factory = build_helpdesk_ai_client_factory(settings)
        ai_settings_repository = build_ai_settings_repository(settings)
        helpdesk_service_factory = build_helpdesk_service_factory(
            db_session_factory,
            super_admin_telegram_user_ids=super_admin_telegram_user_ids,
            ai_client_factory=ai_client_factory,
            ai_settings_provider=ai_settings_repository,
            include_internal_notes_in_ticket_reports=(
                settings.exports.include_internal_notes_in_ticket_reports
            ),
            sla_deadline_scheduler=redis_workflow.sla_deadline_scheduler,
        )
        helpdesk_backend_client_factory = build_helpdesk_backend_client_factory(settings)

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
            backend_check=lambda: ping_helpdesk_backend(
                settings.backend_service,
                auth_config=settings.backend_auth,
                resilience_config=settings.resilience,
            ),
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
