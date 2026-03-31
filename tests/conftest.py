from __future__ import annotations

import pytest

from infrastructure.config import Settings


@pytest.fixture
def sample_settings() -> Settings:
    return Settings.model_validate(
        {
            "app": {"dry_run": True},
            "bot": {"token": ""},
            "authorization": {"super_admin_telegram_user_id": 42},
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
