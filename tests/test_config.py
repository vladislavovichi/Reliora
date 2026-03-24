from __future__ import annotations

from infrastructure.config import Settings


def test_postgres_url_is_built_from_parts(sample_settings: Settings) -> None:
    assert (
        sample_settings.postgres.sqlalchemy_url
        == "postgresql+asyncpg://helpdesk:secret@postgres:5432/helpdesk"
    )


def test_redis_url_is_built_from_parts(sample_settings: Settings) -> None:
    assert sample_settings.redis.url_with_auth == "redis://redis:6379/2"


def test_explicit_urls_override_component_settings() -> None:
    settings = Settings(
        postgres={"url": "postgresql+asyncpg://user:pass@db:5432/app"},
        redis={"url": "redis://cache:6379/4"},
    )

    assert settings.postgres.sqlalchemy_url == "postgresql+asyncpg://user:pass@db:5432/app"
    assert settings.redis.url_with_auth == "redis://cache:6379/4"
