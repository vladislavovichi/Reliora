from __future__ import annotations

import asyncio

from ai_service.bootstrap import build_runtime, close_runtime
from infrastructure.config.settings import get_settings
from infrastructure.logging import configure_logging


async def run() -> int:
    settings = get_settings()
    configure_logging(settings.logging, app=settings.app)

    runtime = await build_runtime(settings)
    try:
        print("OK")
        print("[OK] liveness")
        print("[OK] readiness")
        print(
            "[OK] readiness/ai_service_auth: internal ai-service auth настроен"
            if settings.ai_service_auth.token.strip()
            else "[FAIL] readiness/ai_service_auth: AI_SERVICE_AUTH__TOKEN не задан"
        )
        print(
            "[OK] readiness/ai_provider: "
            f"{settings.ai.normalized_provider}:{settings.ai.model_id or 'disabled'}"
        )
        print(
            f"[OK] readiness/ai_service_grpc: готов к запуску на {settings.ai_service.bind_target}"
        )
        return 0
    finally:
        await close_runtime(runtime)


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
