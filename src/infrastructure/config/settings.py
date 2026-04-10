from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from infrastructure.config.parsers import parse_positive_int_list

_DOCKER_ENV_PATH = Path("/.dockerenv")


def _is_running_in_docker() -> bool:
    return _DOCKER_ENV_PATH.exists()


def _resolve_service_target(
    *,
    host: str,
    port: int,
    service_host: str,
    expose_port: int | None,
) -> tuple[str, int]:
    if host != service_host or _is_running_in_docker():
        return host, port

    if expose_port is None:
        return host, port

    return "localhost", expose_port


class AppConfig(BaseModel):
    name: str = "tg-helpdesk"
    environment: str = "dev"
    dry_run: bool = True


class BotConfig(BaseModel):
    token: str = ""


class AuthorizationConfig(BaseModel):
    super_admin_telegram_user_ids: tuple[int, ...]

    @field_validator("super_admin_telegram_user_ids", mode="before")
    @classmethod
    def validate_super_admin_telegram_user_ids(cls, value: object) -> tuple[int, ...]:
        return parse_positive_int_list(value)


class DatabaseConfig(BaseModel):
    url: str | None = None
    host: str = "postgres"
    port: int = 5432
    expose_port: int | None = None
    user: str = "helpdesk"
    password: str = "helpdesk"
    database: str = "helpdesk"
    echo: bool = False

    @property
    def runtime_target(self) -> tuple[str, int]:
        return _resolve_service_target(
            host=self.host,
            port=self.port,
            service_host="postgres",
            expose_port=self.expose_port,
        )

    @property
    def sqlalchemy_url(self) -> str:
        if self.url:
            return self.url

        host, port = self.runtime_target
        user = quote_plus(self.user)
        password = quote_plus(self.password)
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{self.database}"


class RedisConfig(BaseModel):
    url: str | None = None
    host: str = "redis"
    port: int = 6379
    expose_port: int | None = None
    db: int = 0
    password: str | None = None

    @property
    def runtime_target(self) -> tuple[str, int]:
        return _resolve_service_target(
            host=self.host,
            port=self.port,
            service_host="redis",
            expose_port=self.expose_port,
        )

    @property
    def url_with_auth(self) -> str:
        if self.url:
            return self.url

        host, port = self.runtime_target
        if self.password:
            password = quote_plus(self.password)
            return f"redis://:{password}@{host}:{port}/{self.db}"

        return f"redis://{host}:{port}/{self.db}"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    structured: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        populate_by_name=True,
        extra="ignore",
    )

    app: AppConfig = Field(default_factory=AppConfig)
    bot: BotConfig = Field(default_factory=BotConfig)
    authorization: AuthorizationConfig
    postgres_expose_port: int | None = Field(default=None, validation_alias="POSTGRES_EXPOSE_PORT")
    redis_expose_port: int | None = Field(default=None, validation_alias="REDIS_EXPOSE_PORT")
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @model_validator(mode="after")
    def apply_runtime_service_targets(self) -> Settings:
        self.database.expose_port = self.postgres_expose_port
        self.redis.expose_port = self.redis_expose_port
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
