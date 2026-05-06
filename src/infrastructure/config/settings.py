from __future__ import annotations

import os
from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from infrastructure.config.parsers import parse_positive_int_list

_DOCKER_ENV_PATH = Path("/.dockerenv")
_LOCAL_ENV_FILE = ".env.local"
_TEST_ENV_FILE = ".env.test"
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


def _is_pytest_running() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ or "PYTEST_VERSION" in os.environ


def settings_env_files(*, testing: bool | None = None) -> tuple[str, ...]:
    """Return dotenv files in increasing priority order.

    Pydantic loads OS environment variables before dotenv files. For multiple
    dotenv files, later files override earlier ones, so the effective order is:
    environment variables, .env.local, then .env.test only during pytest runs.
    """

    should_load_test_env = _is_pytest_running() if testing is None else testing
    if should_load_test_env:
        return (_TEST_ENV_FILE, _LOCAL_ENV_FILE)
    return (_LOCAL_ENV_FILE,)


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
    username: str | None = None

    @field_validator("username", mode="before")
    @classmethod
    def validate_username(cls, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip().removeprefix("@").strip()
        return normalized or None


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
    model_id: str = "Qwen/Qwen2.5-0.5B-Instruct"
    local_model_path: Path | None = None
    local_cache_dir: Path = Path("/cache/huggingface")
    local_torch_cache_dir: Path = Path("/cache/torch")
    local_torch_kernel_cache_dir: Path = Path("/cache/torch_kernels")
    local_device: str = "auto"
    local_dtype: str = "auto"
    local_max_input_tokens: int = 4096
    local_max_concurrent_requests: int = 1
    local_top_p: float = 0.9
    local_repetition_penalty: float = 1.05
    local_trust_remote_code: bool = False
    summary_temperature: float = 0.2
    summary_max_output_tokens: int = 700
    reply_draft_temperature: float = 0.4
    reply_draft_max_output_tokens: int = 1000
    macros_temperature: float = 0.2
    macros_max_output_tokens: int = 280
    category_temperature: float = 0.1
    category_max_output_tokens: int = 400

    @property
    def normalized_provider(self) -> str:
        return "local"

    @property
    def effective_model_id(self) -> str:
        if self.local_model_path is not None:
            return str(self.local_model_path)
        return self.model_id

    @field_validator(
        "local_model_path",
        "local_cache_dir",
        "local_torch_cache_dir",
        "local_torch_kernel_cache_dir",
        mode="before",
    )
    @classmethod
    def validate_local_paths(cls, value: object) -> Path | None:
        if value is None or isinstance(value, Path):
            return value
        if isinstance(value, str):
            normalized = value.strip()
            return Path(normalized) if normalized else None
        return None

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("AI__MODEL_ID must not be empty.")
        return normalized

    @field_validator("local_device")
    @classmethod
    def validate_local_device(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"auto", "cpu", "cuda", "mps"}:
            return normalized
        if normalized.startswith("cuda:"):
            suffix = normalized.removeprefix("cuda:")
            if suffix.isdigit():
                return normalized
        raise ValueError("AI__LOCAL_DEVICE must be auto, cpu, cuda, cuda:N, or mps.")

    @field_validator("local_dtype")
    @classmethod
    def validate_local_dtype(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"auto", "float16", "bfloat16", "float32"}:
            raise ValueError("AI__LOCAL_DTYPE must be one of: auto, float16, bfloat16, float32.")
        return normalized

    @field_validator("local_max_input_tokens", "local_max_concurrent_requests")
    @classmethod
    def validate_local_positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("AI local numeric limits must be positive.")
        return value

    @field_validator(
        "summary_max_output_tokens",
        "reply_draft_max_output_tokens",
        "macros_max_output_tokens",
        "category_max_output_tokens",
    )
    @classmethod
    def validate_positive_token_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("AI output token limits must be positive.")
        return value

    @field_validator(
        "summary_temperature",
        "reply_draft_temperature",
        "macros_temperature",
        "category_temperature",
    )
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if value < 0:
            raise ValueError("AI temperatures must be zero or positive.")
        return value

    @field_validator("local_top_p")
    @classmethod
    def validate_local_top_p(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("AI__LOCAL_TOP_P must be in the range (0, 1].")
        return value

    @field_validator("local_repetition_penalty")
    @classmethod
    def validate_local_repetition_penalty(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("AI__LOCAL_REPETITION_PENALTY must be positive.")
        return value


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
        env_file=settings_env_files(),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        populate_by_name=True,
        extra="ignore",
    )

    app: AppConfig = Field(default_factory=AppConfig)
    bot: BotConfig = Field(default_factory=BotConfig)
    telegram_bot_token: str = Field(
        default="",
        validation_alias="TELEGRAM_BOT_TOKEN",
        exclude=True,
    )
    authorization: AuthorizationConfig
    database_url: str = Field(default="", validation_alias="DATABASE_URL", exclude=True)
    redis_url: str = Field(default="", validation_alias="REDIS_URL", exclude=True)
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
    ai_runtime_settings: RuntimeAISettingsConfig = Field(default_factory=RuntimeAISettingsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)
    attachments: AttachmentLimitsConfig = Field(default_factory=AttachmentLimitsConfig)
    exports: ExportConfig = Field(default_factory=ExportConfig)
    assets: AssetsConfig = Field(default_factory=AssetsConfig)
    mini_app: MiniAppConfig = Field(default_factory=MiniAppConfig)

    @model_validator(mode="after")
    def apply_runtime_service_targets(self) -> Settings:
        self.bot.token = self.telegram_bot_token.strip()
        self.database.url = self.database_url.strip() or None
        self.redis.url = self.redis_url.strip() or None
        self.database.expose_port = self.postgres_expose_port
        self.redis.expose_port = self.redis_expose_port
        self.backend_service.expose_port = self.backend_expose_port
        self.ai_service.expose_port = self.ai_service_expose_port
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
