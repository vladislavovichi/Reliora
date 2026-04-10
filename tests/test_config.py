from __future__ import annotations

import pytest

from infrastructure.config import settings as settings_module
from infrastructure.config.settings import Settings


def test_database_url_is_built_from_parts(
    monkeypatch: pytest.MonkeyPatch,
    sample_settings: Settings,
) -> None:
    monkeypatch.delenv("POSTGRES_EXPOSE_PORT", raising=False)
    assert (
        sample_settings.database.sqlalchemy_url
        == "postgresql+asyncpg://helpdesk:secret@postgres:5432/helpdesk"
    )


def test_redis_url_is_built_from_parts(
    monkeypatch: pytest.MonkeyPatch,
    sample_settings: Settings,
) -> None:
    monkeypatch.delenv("REDIS_EXPOSE_PORT", raising=False)
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
        {"authorization": {"super_admin_telegram_user_ids": "12345, 67890, , 12345, 11111"}}
    )

    assert settings.authorization.super_admin_telegram_user_ids == (12345, 67890, 11111)


def test_super_admin_ids_reject_non_positive_values() -> None:
    with pytest.raises(ValueError):
        Settings.model_validate({"authorization": {"super_admin_telegram_user_ids": "123,0,-5"}})


def test_database_url_uses_published_docker_port_on_host(
    monkeypatch: pytest.MonkeyPatch,
    sample_settings: Settings,
) -> None:
    monkeypatch.setattr(settings_module, "_is_running_in_docker", lambda: False)
    sample_settings.database.expose_port = 5434

    assert (
        sample_settings.database.sqlalchemy_url
        == "postgresql+asyncpg://helpdesk:secret@localhost:5434/helpdesk"
    )


def test_redis_url_uses_published_docker_port_on_host(
    monkeypatch: pytest.MonkeyPatch,
    sample_settings: Settings,
) -> None:
    monkeypatch.setattr(settings_module, "_is_running_in_docker", lambda: False)
    sample_settings.redis.expose_port = 6381

    assert sample_settings.redis.url_with_auth == "redis://localhost:6381/2"


def test_settings_apply_root_expose_ports_to_nested_configs() -> None:
    settings = Settings.model_validate(
        {
            "authorization": {"super_admin_telegram_user_ids": [99]},
            "POSTGRES_EXPOSE_PORT": 5434,
            "REDIS_EXPOSE_PORT": 6381,
        }
    )

    assert settings.database.expose_port == 5434
    assert settings.redis.expose_port == 6381
