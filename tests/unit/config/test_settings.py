from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.config import settings as settings_module
from infrastructure.config.settings import AuthorizationConfig, Settings, settings_env_files


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
            "DATABASE_URL": "postgresql+asyncpg://user:pass@db:5432/app",
            "REDIS_URL": "redis://cache:6379/4",
        }
    )

    assert settings.database.sqlalchemy_url == "postgresql+asyncpg://user:pass@db:5432/app"
    assert settings.redis.url_with_auth == "redis://cache:6379/4"


def test_super_admin_ids_are_loaded_from_settings(sample_settings: Settings) -> None:
    assert sample_settings.authorization.super_admin_telegram_user_ids == (42,)


def test_ai_reply_draft_generation_settings_have_separate_defaults() -> None:
    settings = Settings(
        _env_file=None,
        authorization=AuthorizationConfig(super_admin_telegram_user_ids=(99,)),
    )  # type: ignore[call-arg]

    assert settings.ai.normalized_provider == "local"
    assert settings.ai.model_id == "Qwen/Qwen2.5-0.5B-Instruct"
    assert settings.ai.summary_temperature == 0.2
    assert settings.ai.summary_max_output_tokens == 700
    assert settings.ai.reply_draft_temperature == 0.4
    assert settings.ai.reply_draft_max_output_tokens == 1000
    assert settings.ai.category_max_output_tokens == 400
    assert settings.ai.local_top_p == 0.9
    assert settings.ai.local_repetition_penalty == 1.05


def test_ai_reply_draft_generation_settings_load_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI__REPLY_DRAFT_TEMPERATURE", "0.47")
    monkeypatch.setenv("AI__REPLY_DRAFT_MAX_OUTPUT_TOKENS", "777")

    settings = Settings(
        _env_file=None,
        authorization=AuthorizationConfig(super_admin_telegram_user_ids=(99,)),
    )  # type: ignore[call-arg]

    assert settings.ai.reply_draft_temperature == 0.47
    assert settings.ai.reply_draft_max_output_tokens == 777


def test_settings_env_file_order_is_explicit() -> None:
    assert settings_env_files(testing=False) == (".env.local",)
    assert settings_env_files(testing=True) == (".env.test", ".env.local")


def test_settings_load_env_local_with_test_fallback_and_env_precedence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath(".env.test").write_text(
        "\n".join(
            (
                "AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS=111",
                "TELEGRAM_BOT_TOKEN=from-test",
            )
        ),
        encoding="utf-8",
    )
    local_env = tmp_path.joinpath(".env.local")
    local_env.write_text(
        "\n".join(
            (
                "AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS=222",
                "TELEGRAM_BOT_TOKEN=from-local",
                "DATABASE_URL=postgresql+asyncpg://local:pass@localhost:5432/app",
                "REDIS_URL=redis://localhost:6379/3",
            )
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS", "333")
    settings = Settings(_env_file=settings_env_files(testing=True))  # type: ignore[call-arg]

    assert settings.authorization.super_admin_telegram_user_ids == (333,)
    assert settings.bot.token == "from-local"
    assert settings.database.sqlalchemy_url == "postgresql+asyncpg://local:pass@localhost:5432/app"
    assert settings.redis.url_with_auth == "redis://localhost:6379/3"

    monkeypatch.delenv("AUTHORIZATION__SUPER_ADMIN_TELEGRAM_USER_IDS")
    settings = Settings(_env_file=settings_env_files(testing=True))  # type: ignore[call-arg]
    assert settings.authorization.super_admin_telegram_user_ids == (222,)

    local_env.unlink()
    settings = Settings(_env_file=settings_env_files(testing=True))  # type: ignore[call-arg]
    assert settings.authorization.super_admin_telegram_user_ids == (111,)


def test_removed_env_names_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT__TOKEN", "old-token")
    monkeypatch.setenv("DATABASE__URL", "postgresql+asyncpg://old:pass@db:5432/app")
    monkeypatch.setenv("REDIS__URL", "redis://old-cache:6379/4")

    settings = Settings(
        _env_file=None,
        authorization=AuthorizationConfig(super_admin_telegram_user_ids=(99,)),
    )  # type: ignore[call-arg]

    assert settings.bot.token == ""
    assert settings.database.url is None
    assert settings.redis.url is None


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


def test_mini_app_public_url_is_exposed_only_when_valid() -> None:
    settings = Settings.model_validate(
        {
            "authorization": {"super_admin_telegram_user_ids": [99]},
            "mini_app": {"public_url": "https://mini-app.example.com/workspace"},
        }
    )

    assert settings.mini_app.public_url_is_valid is True
    assert settings.mini_app.telegram_launch_url == "https://mini-app.example.com/workspace"
    assert settings.mini_app.public_url_hostname == "mini-app.example.com"
    assert settings.mini_app.public_url_looks_temporary is False


def test_mini_app_public_url_rejects_local_http_address() -> None:
    settings = Settings.model_validate(
        {
            "authorization": {"super_admin_telegram_user_ids": [99]},
            "mini_app": {"public_url": "http://localhost:8080"},
        }
    )

    assert settings.mini_app.public_url_is_valid is False
    assert settings.mini_app.telegram_launch_url is None
    assert "https://" in settings.mini_app.public_url_status_detail


def test_mini_app_public_url_marks_temporary_public_domains_in_diagnostics() -> None:
    settings = Settings.model_validate(
        {
            "authorization": {"super_admin_telegram_user_ids": [99]},
            "mini_app": {"public_url": "https://helpdesk-demo.trycloudflare.com"},
        }
    )

    assert settings.mini_app.public_url_is_valid is True
    assert settings.mini_app.public_url_looks_temporary is True
    assert settings.mini_app.public_url_hostname == "helpdesk-demo.trycloudflare.com"
    assert "временный публичный домен" in settings.mini_app.public_url_status_detail
