from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseModel):
    name: str = "tg-helpdesk"
    environment: str = "dev"
    dry_run: bool = True


class BotConfig(BaseModel):
    token: str = ""


class AuthorizationConfig(BaseModel):
    super_admin_telegram_user_id: int = Field(gt=0)


class DatabaseConfig(BaseModel):
    url: str | None = None
    host: str = "postgres"
    port: int = 5432
    user: str = "helpdesk"
    password: str = "helpdesk"
    database: str = "helpdesk"
    echo: bool = False

    @property
    def sqlalchemy_url(self) -> str:
        if self.url:
            return self.url

        user = quote_plus(self.user)
        password = quote_plus(self.password)
        return f"postgresql+asyncpg://{user}:{password}@{self.host}:{self.port}/{self.database}"


class RedisConfig(BaseModel):
    url: str | None = None
    host: str = "redis"
    port: int = 6379
    db: int = 0
    password: str | None = None

    @property
    def url_with_auth(self) -> str:
        if self.url:
            return self.url

        if self.password:
            password = quote_plus(self.password)
            return f"redis://:{password}@{self.host}:{self.port}/{self.db}"

        return f"redis://{self.host}:{self.port}/{self.db}"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    structured: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app: AppConfig = Field(default_factory=AppConfig)
    bot: BotConfig = Field(default_factory=BotConfig)
    authorization: AuthorizationConfig
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
