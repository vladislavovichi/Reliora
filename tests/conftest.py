from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.config.settings import (
    AppConfig,
    AuthorizationConfig,
    BackendAuthConfig,
    DatabaseConfig,
    LoggingConfig,
    RedisConfig,
    Settings,
)

_TAXONOMY_MARKERS: tuple[tuple[str, str], ...] = (
    ("unit", "unit"),
    ("component", "component"),
    ("integration", "integration"),
    ("e2e", "e2e"),
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path_parts = Path(item.path).parts
        if "tests" not in path_parts:
            continue

        category_index = path_parts.index("tests") + 1
        if category_index >= len(path_parts):
            continue

        category = path_parts[category_index]
        for directory, marker in _TAXONOMY_MARKERS:
            if category == directory:
                item.add_marker(getattr(pytest.mark, marker))
                break


@pytest.fixture
def sample_settings() -> Settings:
    return Settings(
        _env_file=None,
        app=AppConfig(dry_run=True),
        telegram_bot_token="",
        authorization=AuthorizationConfig(super_admin_telegram_user_ids=(42,)),
        backend_auth=BackendAuthConfig(token="test-internal-token"),
        database_url="",
        redis_url="",
        postgres_expose_port=None,
        redis_expose_port=None,
        database=DatabaseConfig(
            host="postgres",
            port=5432,
            user="helpdesk",
            password="secret",
            database="helpdesk",
        ),
        redis=RedisConfig(host="redis", port=6379, db=2),
        logging=LoggingConfig(level="DEBUG"),
    )  # type: ignore[call-arg]
