from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

import grpc
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from infrastructure.config.settings import Settings

AsyncStartupCheck = Callable[[], Awaitable[bool]]
EXPECTED_STARTUP_FAILURES = (
    TimeoutError,
    OSError,
    RuntimeError,
    PermissionError,
    ValueError,
    SQLAlchemyError,
    RedisError,
    grpc.RpcError,
)


@dataclass(slots=True, frozen=True)
class StartupDependencyCheck:
    name: str
    target: str
    check: AsyncStartupCheck


def validate_app_startup_settings(settings: Settings) -> None:
    _validate_helpdesk_settings(settings)
    _validate_backend_auth(settings)
    if settings.app.dry_run:
        return
    if not settings.bot.token.strip():
        raise RuntimeError("Невозможно запустить polling: TELEGRAM_BOT_TOKEN не задан.")


def validate_backend_startup_settings(settings: Settings) -> None:
    _validate_helpdesk_settings(settings)
    _validate_backend_auth(settings)
    _validate_ai_service_auth(settings)


def validate_ai_service_startup_settings(settings: Settings) -> None:
    _validate_ai_service_auth(settings)


async def run_startup_dependency_checks(
    *,
    component: str,
    checks: Sequence[StartupDependencyCheck],
    settings: Settings,
    logger: logging.Logger,
) -> None:
    for check in checks:
        await _run_single_dependency_check(
            component=component,
            check=check,
            settings=settings,
            logger=logger,
        )


async def _run_single_dependency_check(
    *,
    component: str,
    check: StartupDependencyCheck,
    settings: Settings,
    logger: logging.Logger,
) -> None:
    attempts = max(settings.resilience.startup_retry_attempts, 1)
    timeout = max(settings.resilience.startup_check_timeout_seconds, 0.1)
    backoff = max(settings.resilience.startup_retry_backoff_seconds, 0.0)

    for attempt in range(1, attempts + 1):
        try:
            logger.info(
                "Startup dependency check started component=%s dependency=%s target=%s attempt=%s",
                component,
                check.name,
                check.target,
                attempt,
            )
            is_ready = await asyncio.wait_for(check.check(), timeout=timeout)
            if not is_ready:
                raise RuntimeError("dependency returned negative readiness state")

            logger.info(
                "Startup dependency check passed component=%s dependency=%s target=%s attempt=%s",
                component,
                check.name,
                check.target,
                attempt,
            )
            return
        except EXPECTED_STARTUP_FAILURES as exc:
            is_final_attempt = attempt >= attempts
            log_method = logger.error if is_final_attempt else logger.warning
            log_method(
                "Startup dependency check failed component=%s dependency=%s target=%s "
                "attempt=%s failure_class=%s error_type=%s error=%s final=%s",
                component,
                check.name,
                check.target,
                attempt,
                _classify_startup_failure(exc),
                exc.__class__.__name__,
                exc,
                is_final_attempt,
            )
            if is_final_attempt:
                raise RuntimeError(
                    f"Критическая зависимость {check.name} недоступна: {exc}"
                ) from exc
            await asyncio.sleep(backoff * attempt)


def _validate_helpdesk_settings(settings: Settings) -> None:
    if not settings.authorization.super_admin_telegram_user_ids:
        raise RuntimeError("AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS не настроен.")


def _validate_backend_auth(settings: Settings) -> None:
    if not settings.backend_auth.token.strip():
        raise RuntimeError("BACKEND_AUTH__TOKEN не задан.")


def _validate_ai_service_auth(settings: Settings) -> None:
    if not settings.ai_service_auth.token.strip():
        raise RuntimeError("AI_SERVICE_AUTH__TOKEN не задан.")


def _classify_startup_failure(exc: Exception) -> str:
    if isinstance(exc, PermissionError):
        return "auth_issue"
    if isinstance(exc, ValueError):
        return "config_issue"
    if isinstance(exc, (TimeoutError, OSError, SQLAlchemyError, RedisError, grpc.RpcError)):
        return "dependency_issue"
    return "runtime_issue"
