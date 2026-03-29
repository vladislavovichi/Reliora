from __future__ import annotations

import asyncio
import logging

from app.bootstrap import build_runtime, close_runtime
from infrastructure.config import get_settings
from infrastructure.logging import configure_logging


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.logging, app=settings.app)

    logger = logging.getLogger(__name__)
    logger.info(
        "Bootstrapping service name=%s environment=%s dry_run=%s",
        settings.app.name,
        settings.app.environment,
        settings.app.dry_run,
    )

    runtime = await build_runtime(settings)
    try:
        logger.info("Runtime resources initialized successfully.")

        if settings.app.dry_run:
            logger.info(
                "Dry-run mode is enabled. "
                "Infrastructure is initialized, but Telegram polling stays disabled."
            )
            await asyncio.Event().wait()
            return

        if runtime.bot is None or runtime.dispatcher is None:
            raise RuntimeError("BOT__TOKEN must be set when APP__DRY_RUN is false.")

        logger.info("Starting Telegram polling.")
        await runtime.dispatcher.start_polling(
            runtime.bot,
            allowed_updates=runtime.dispatcher.resolve_used_update_types(),
        )
    finally:
        await close_runtime(runtime)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutdown requested, stopping service.")
