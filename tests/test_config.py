from __future__ import annotations

import pytest

from infrastructure.config import Settings


def test_database_url_is_built_from_parts(sample_settings: Settings) -> None:
    assert (
        sample_settings.database.sqlalchemy_url
        == "postgresql+asyncpg://helpdesk:secret@postgres:5432/helpdesk"
    )


def test_redis_url_is_built_from_parts(sample_settings: Settings) -> None:
    assert sample_settings.redis.url_with_auth == "redis://redis:6379/2"


def test_explicit_urls_override_component_settings() -> None:
    settings = Settings.model_validate(
        {
            "authorization": {"super_admin_telegram_user_ids": [99]},
            "database": {"url": "postgresql+asyncpg://user:pass@db:5432/app"},
            "redis": {"url": "redis://cache:6379/4"},
        }
    )

    assert settings.database.sqlalchemy_url == "postgresql+asyncpg://user:pass@db:5432/app"
    assert settings.redis.url_with_auth == "redis://cache:6379/4"


def test_super_admin_ids_are_loaded_from_settings(sample_settings: Settings) -> None:
    assert sample_settings.authorization.super_admin_telegram_user_ids == (42,)


def test_super_admin_ids_are_parsed_from_comma_separated_env_style_value() -> None:
    settings = Settings.model_validate(
        {
            "authorization": {
                "super_admin_telegram_user_ids": "12345, 67890, , 12345, 11111"
            }
        }
    )

    assert settings.authorization.super_admin_telegram_user_ids == (12345, 67890, 11111)


def test_super_admin_ids_reject_non_positive_values() -> None:
    with pytest.raises(ValueError):
        Settings.model_validate(
            {"authorization": {"super_admin_telegram_user_ids": "123,0,-5"}}
        )
