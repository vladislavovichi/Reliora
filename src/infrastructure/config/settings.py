from __future__ import annotations

from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from infrastructure.config.parsers import parse_positive_int_list

_DOCKER_ENV_PATH = Path("/.dockerenv")
_LOCAL_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1"})
_LOCAL_HOST_SUFFIXES = (".internal", ".local", ".localhost", ".test", ".invalid")
_TEMPORARY_PUBLIC_HOST_SUFFIXES = (
    ".trycloudflare.com",
    ".ngrok-free.app",
    ".ngrok.app",
    ".ngrok.io",
    ".loca.lt",
)


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


def _validate_telegram_mini_app_public_url(value: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return "MINI_APP__PUBLIC_URL не задан."

    parsed = urlsplit(normalized)
    if parsed.scheme.lower() != "https":
        return "MINI_APP__PUBLIC_URL должен начинаться с https://."
    if not parsed.netloc:
        return "MINI_APP__PUBLIC_URL должен быть абсолютным публичным URL."
    if parsed.fragment:
        return "MINI_APP__PUBLIC_URL не должен содержать fragment."

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return "MINI_APP__PUBLIC_URL должен содержать домен."
    if hostname in _LOCAL_HOSTNAMES or hostname.endswith(_LOCAL_HOST_SUFFIXES):
        return "MINI_APP__PUBLIC_URL должен указывать на публичный домен, доступный Telegram."

    try:
        address = ip_address(hostname)
    except ValueError:
        if "." not in hostname:
            return "MINI_APP__PUBLIC_URL должен указывать на публичный домен с HTTPS."
    else:
        if not address.is_global:
            return (
                "MINI_APP__PUBLIC_URL с IP-адресом должен быть глобально "
                "маршрутизируемым и доступным Telegram."
            )

    return None


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


class BackendServiceConfig(BaseModel):
    host: str = "backend"
    port: int = 50051
    expose_port: int | None = None
    listen_host: str = "0.0.0.0"

    @property
    def runtime_target(self) -> tuple[str, int]:
        return _resolve_service_target(
            host=self.host,
            port=self.port,
            service_host="backend",
            expose_port=self.expose_port,
        )

    @property
    def target(self) -> str:
        host, port = self.runtime_target
        return f"{host}:{port}"

    @property
    def bind_target(self) -> str:
        return f"{self.listen_host}:{self.port}"


class AIServiceConfig(BaseModel):
    host: str = "ai-service"
    port: int = 50061
    expose_port: int | None = None
    listen_host: str = "0.0.0.0"

    @property
    def runtime_target(self) -> tuple[str, int]:
        return _resolve_service_target(
            host=self.host,
            port=self.port,
            service_host="ai-service",
            expose_port=self.expose_port,
        )

    @property
    def target(self) -> str:
        host, port = self.runtime_target
        return f"{host}:{port}"

    @property
    def bind_target(self) -> str:
        return f"{self.listen_host}:{self.port}"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    structured: bool = True


class BackendAuthConfig(BaseModel):
    token: str = ""
    caller: str = "telegram-bot"


class AIServiceAuthConfig(BaseModel):
    token: str = ""
    caller: str = "helpdesk-backend"


class AIConfig(BaseModel):
    provider: str = "disabled"
    model_id: str | None = None
    api_token: str | None = None
    base_url: str = "https://router.huggingface.co/v1/chat/completions"
    timeout_seconds: float = 20.0
    summary_temperature: float = 0.15
    summary_max_output_tokens: int = 320
    macros_temperature: float = 0.2
    macros_max_output_tokens: int = 280
    category_temperature: float = 0.1
    category_max_output_tokens: int = 160

    @property
    def normalized_provider(self) -> str:
        provider = self.provider.strip().lower()
        return provider or "disabled"


class RuntimeAISettingsConfig(BaseModel):
    path: Path = Path("assets/ai_settings.json")

    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, value: object) -> Path:
        if isinstance(value, Path):
            return value
        if isinstance(value, str) and value.strip():
            return Path(value.strip())
        return Path("assets/ai_settings.json")


class ResilienceConfig(BaseModel):
    startup_check_timeout_seconds: float = 5.0
    startup_retry_attempts: int = 3
    startup_retry_backoff_seconds: float = 0.5
    grpc_connect_timeout_seconds: float = 5.0
    grpc_request_timeout_seconds: float = 10.0
    grpc_read_retry_attempts: int = 2
    grpc_retry_backoff_seconds: float = 0.25
    telegram_send_timeout_seconds: float = 10.0
    telegram_send_attempts: int = 3


class AttachmentLimitsConfig(BaseModel):
    photo_max_bytes: int = 10 * 1024 * 1024
    document_max_bytes: int = 20 * 1024 * 1024
    voice_max_bytes: int = 10 * 1024 * 1024
    video_max_bytes: int = 20 * 1024 * 1024
    blocked_document_mime_types: tuple[str, ...] = (
        "application/java-archive",
        "application/javascript",
        "application/vnd.microsoft.portable-executable",
        "application/x-bat",
        "application/x-dosexec",
        "application/x-executable",
        "application/x-msdownload",
        "application/x-msi",
        "application/x-powershell",
        "application/x-sh",
    )
    blocked_document_extensions: tuple[str, ...] = (
        ".bat",
        ".cmd",
        ".com",
        ".exe",
        ".js",
        ".jar",
        ".msi",
        ".ps1",
        ".scr",
        ".sh",
        ".vbs",
    )


class ExportConfig(BaseModel):
    include_internal_notes_in_ticket_reports: bool = True


class AssetsConfig(BaseModel):
    path: Path = Path("assets")

    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, value: object) -> Path:
        if isinstance(value, Path):
            return value
        if isinstance(value, str) and value.strip():
            return Path(value.strip())
        return Path("assets")


class MiniAppConfig(BaseModel):
    listen_host: str = "0.0.0.0"
    port: int = 8080
    public_url: str = ""
    init_data_ttl_seconds: int = 3600
    ai_rate_limit_window_seconds: int = 60
    ai_summary_rate_limit: int = 3
    ai_reply_draft_rate_limit: int = 5

    @field_validator("public_url", mode="before")
    @classmethod
    def validate_public_url(cls, value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""

    @property
    def public_url_validation_error(self) -> str | None:
        return _validate_telegram_mini_app_public_url(self.public_url)

    @property
    def public_url_is_configured(self) -> bool:
        return bool(self.public_url)

    @property
    def public_url_is_valid(self) -> bool:
        return self.public_url_validation_error is None

    @property
    def telegram_launch_url(self) -> str | None:
        if not self.public_url_is_valid:
            return None
        return self.public_url

    @property
    def public_url_hostname(self) -> str | None:
        normalized = self.public_url.strip()
        if not normalized:
            return None
        hostname = urlsplit(normalized).hostname
        if hostname is None:
            return None
        return hostname.strip().lower() or None

    @property
    def public_url_looks_temporary(self) -> bool:
        hostname = self.public_url_hostname
        if hostname is None:
            return False
        return hostname.endswith(_TEMPORARY_PUBLIC_HOST_SUFFIXES)

    @property
    def public_url_status_detail(self) -> str:
        error = self.public_url_validation_error
        if error is None:
            if self.public_url_looks_temporary:
                return (
                    f"Mini App URL готов для Telegram: {self.public_url} "
                    "(временный публичный домен)"
                )
            return f"Mini App URL готов для Telegram: {self.public_url}"
        return error

    @property
    def healthcheck_url(self) -> str:
        host = self.listen_host
        if host == "0.0.0.0":
            host = "127.0.0.1"
        return f"http://{host}:{self.port}/healthz"


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
    backend_expose_port: int | None = Field(default=None, validation_alias="BACKEND_EXPOSE_PORT")
    ai_service_expose_port: int | None = Field(
        default=None,
        validation_alias="AI_SERVICE_EXPOSE_PORT",
    )
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    backend_service: BackendServiceConfig = Field(default_factory=BackendServiceConfig)
    ai_service: AIServiceConfig = Field(default_factory=AIServiceConfig)
    backend_auth: BackendAuthConfig = Field(default_factory=BackendAuthConfig)
    ai_service_auth: AIServiceAuthConfig = Field(default_factory=AIServiceAuthConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    ai_runtime_settings: RuntimeAISettingsConfig = Field(
        default_factory=RuntimeAISettingsConfig
    )
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)
    attachments: AttachmentLimitsConfig = Field(default_factory=AttachmentLimitsConfig)
    exports: ExportConfig = Field(default_factory=ExportConfig)
    assets: AssetsConfig = Field(default_factory=AssetsConfig)
    mini_app: MiniAppConfig = Field(default_factory=MiniAppConfig)

    @model_validator(mode="after")
    def apply_runtime_service_targets(self) -> Settings:
        self.database.expose_port = self.postgres_expose_port
        self.redis.expose_port = self.redis_expose_port
        self.backend_service.expose_port = self.backend_expose_port
        self.ai_service.expose_port = self.ai_service_expose_port
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
