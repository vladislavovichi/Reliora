from __future__ import annotations

import pytest

from infrastructure.config import Settings


@pytest.fixture
def sample_settings() -> Settings:
    return Settings(
        app={"dry_run": True},
        telegram={"token": ""},
        postgres={
            "host": "postgres",
            "port": 5432,
            "user": "helpdesk",
            "password": "secret",
            "database": "helpdesk",
        },
        redis={
            "host": "redis",
            "port": 6379,
            "db": 2,
        },
    )
