from __future__ import annotations

import asyncio
import logging

from ai_service.bootstrap import build_runtime, close_runtime
from infrastructure.config.settings import get_settings
from infrastructure.logging import configure_logging


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.logging, app=settings.app)

    logger = logging.getLogger(__name__)
    logger.info(
        "Bootstrapping ai-service name=%s environment=%s bind=%s",
        settings.app.name,
        settings.app.environment,
        settings.ai_service.bind_target,
    )

    runtime = await build_runtime(settings)
    try:
        await runtime.grpc_server.start()
        logger.info(
            "AI-service gRPC server started bind=%s bound_port=%s",
            settings.ai_service.bind_target,
            runtime.grpc_server.bound_port,
        )
        await runtime.grpc_server.wait_for_termination()
    except Exception:
        logger.exception("AI-service runtime failed.")
        raise
    finally:
        await runtime.grpc_server.stop()
        await close_runtime(runtime)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutdown requested, stopping ai-service.")


if __name__ == "__main__":
    main()
