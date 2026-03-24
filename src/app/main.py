from __future__ import annotations

import asyncio
import logging

from app.bootstrap import build_runtime
from infrastructure.config import get_settings
from infrastructure.logging import configure_logging


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.app.log_level)

    logger = logging.getLogger(__name__)
    logger.info(
        "Bootstrapping service name=%s environment=%s dry_run=%s",
        settings.app.name,
        settings.app.environment,
        settings.app.dry_run,
    )

    if settings.app.dry_run:
        logger.info(
            "Dry-run mode is enabled. Infrastructure is wired, but Telegram polling stays disabled."
        )
        await asyncio.Event().wait()
        return

    runtime = build_runtime(settings)
    logger.info("Starting Telegram polling.")

    try:
        await runtime.dispatcher.start_polling(
            runtime.bot,
            allowed_updates=runtime.dispatcher.resolve_used_update_types(),
        )
    finally:
        await runtime.bot.session.close()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutdown requested, stopping service.")
