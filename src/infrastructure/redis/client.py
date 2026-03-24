from __future__ import annotations

from redis.asyncio import Redis

from infrastructure.config import RedisConfig


def build_redis_client(config: RedisConfig) -> Redis:
    return Redis.from_url(
        config.url_with_auth,
        encoding="utf-8",
        decode_responses=True,
    )
