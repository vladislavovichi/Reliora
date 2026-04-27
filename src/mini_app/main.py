from __future__ import annotations

import logging
from pathlib import Path

from backend.grpc.client import build_helpdesk_backend_client_factory
from infrastructure.config.ai_settings import (
    JsonAISettingsRepository,
    build_runtime_ai_settings_defaults,
)
from infrastructure.config.settings import Settings, get_settings
from infrastructure.logging import configure_logging
from mini_app.api import MiniAppAIRateLimiter, MiniAppGateway
from mini_app.http import MiniAppHttpServer


def _log_mini_app_configuration(logger: logging.Logger, settings: Settings) -> None:
    if settings.mini_app.public_url_is_valid:
        logger.info(
            "Mini App public URL is ready for Telegram public_url=%s host=%s temporary=%s",
            settings.mini_app.telegram_launch_url,
            settings.mini_app.public_url_hostname or "<unknown>",
            settings.mini_app.public_url_looks_temporary,
        )
        return

    if not settings.mini_app.public_url_is_configured:
        logger.warning(
            "Mini App public URL is missing. Telegram launch button will stay hidden detail=%s",
            settings.mini_app.public_url_status_detail,
        )
        return

    logger.warning(
        (
            "Mini App public URL is not suitable for Telegram detail=%s "
            "configured_public_url=%s host=%s temporary=%s"
        ),
        settings.mini_app.public_url_status_detail,
        settings.mini_app.public_url or "<not-set>",
        settings.mini_app.public_url_hostname or "<unknown>",
        settings.mini_app.public_url_looks_temporary,
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.logging, app=settings.app)

    logger = logging.getLogger(__name__)
    _log_mini_app_configuration(logger, settings)
    gateway = MiniAppGateway(
        backend_client_factory=build_helpdesk_backend_client_factory(
            settings.backend_service,
            auth_config=settings.backend_auth,
            resilience_config=settings.resilience,
        ),
        ai_settings_repository=JsonAISettingsRepository(
            path=settings.ai_runtime_settings.path,
            defaults=build_runtime_ai_settings_defaults(settings.ai.model_id),
        ),
        ai_rate_limiter=MiniAppAIRateLimiter(
            summary_limit=settings.mini_app.ai_summary_rate_limit,
            reply_draft_limit=settings.mini_app.ai_reply_draft_rate_limit,
            window_seconds=settings.mini_app.ai_rate_limit_window_seconds,
        ),
    )
    server = MiniAppHttpServer(
        config=settings.mini_app,
        bot_token=settings.bot.token,
        gateway=gateway,
        static_dir=Path(__file__).resolve().parent / "static",
    ).build_server()

    logger.info(
        (
            "Starting Mini App HTTP gateway bind=%s:%s public_url=%s "
            "host=%s temporary=%s healthcheck=%s"
        ),
        settings.mini_app.listen_host,
        settings.mini_app.port,
        settings.mini_app.telegram_launch_url or "<not-available>",
        settings.mini_app.public_url_hostname or "<unknown>",
        settings.mini_app.public_url_looks_temporary,
        settings.mini_app.healthcheck_url,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Mini App shutdown requested.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
