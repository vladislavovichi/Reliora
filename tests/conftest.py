from __future__ import annotations

import pytest

from infrastructure.config.settings import Settings


@pytest.fixture
def sample_settings() -> Settings:
    return Settings.model_validate(
        {
            "app": {"dry_run": True},
            "bot": {"token": ""},
            "authorization": {"super_admin_telegram_user_ids": [42]},
            "postgres_expose_port": None,
            "redis_expose_port": None,
            "database": {
                "host": "postgres",
                "port": 5432,
                "user": "helpdesk",
                "password": "secret",
                "database": "helpdesk",
            },
            "redis": {
                "host": "redis",
                "port": 6379,
                "db": 2,
            },
            "logging": {"level": "DEBUG"},
        }
    )
