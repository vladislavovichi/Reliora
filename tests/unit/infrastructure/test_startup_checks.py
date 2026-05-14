import logging

import pytest

from infrastructure.config.settings import AuthorizationConfig, ResilienceConfig, Settings
from infrastructure.startup_checks import StartupDependencyCheck, run_startup_dependency_checks


async def test_run_startup_dependency_checks_retries_expected_failures() -> None:
    attempts = 0

    async def flaky_check() -> bool:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise RuntimeError("redis temporarily unavailable")
        return True

    await run_startup_dependency_checks(
        component="bot",
        checks=(
            StartupDependencyCheck(
                name="redis",
                target="redis://localhost:6379/0",
                check=flaky_check,
            ),
        ),
        settings=_settings(),
        logger=logging.getLogger(__name__),
    )

    assert attempts == 2


async def test_run_startup_dependency_checks_propagates_unexpected_programming_error() -> None:
    async def broken_check() -> bool:
        raise KeyError("unexpected bug")

    with pytest.raises(KeyError, match="unexpected bug"):
        await run_startup_dependency_checks(
            component="backend",
            checks=(
                StartupDependencyCheck(
                    name="postgresql",
                    target="127.0.0.1:5432/helpdesk",
                    check=broken_check,
                ),
            ),
            settings=_settings(),
            logger=logging.getLogger(__name__),
        )


async def test_run_startup_dependency_checks_fails_after_configured_attempts() -> None:
    attempts = 0

    async def unavailable_check() -> bool:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("redis unavailable")

    with pytest.raises(RuntimeError, match="Критическая зависимость redis недоступна"):
        await run_startup_dependency_checks(
            component="bot",
            checks=(
                StartupDependencyCheck(
                    name="redis",
                    target="redis://localhost:6379/0",
                    check=unavailable_check,
                ),
            ),
            settings=_settings(),
            logger=logging.getLogger(__name__),
        )

    assert attempts == 2


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        authorization=AuthorizationConfig(super_admin_telegram_user_ids=(1,)),
        resilience=ResilienceConfig(
            startup_retry_attempts=2,
            startup_check_timeout_seconds=0.1,
            startup_retry_backoff_seconds=0.0,
        ),
    )  # type: ignore[call-arg]
