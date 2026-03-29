from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from infrastructure.config import AppConfig, LoggingConfig

PLAIN_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


class JsonFormatter(logging.Formatter):
    def __init__(self, *, app_name: str, environment: str) -> None:
        super().__init__()
        self.app_name = app_name
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "app": self.app_name,
            "environment": self.environment,
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=True)


def configure_logging(config: LoggingConfig, *, app: AppConfig) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter(app_name=app.name, environment=app.environment)
        if config.structured
        else logging.Formatter(PLAIN_LOG_FORMAT)
    )
    logging.basicConfig(
        level=getattr(logging, config.level.upper(), logging.INFO),
        handlers=[handler],
        force=True,
    )
