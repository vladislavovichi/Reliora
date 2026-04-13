from __future__ import annotations

from redis.asyncio import Redis

from infrastructure.config.settings import RedisConfig
from infrastructure.redis.async_support import resolve_redis_result


def build_redis_client(config: RedisConfig) -> Redis:
    return Redis.from_url(
        config.url_with_auth,
        encoding="utf-8",
        decode_responses=True,
    )


async def ping_redis_client(client: Redis) -> bool:
    result = await resolve_redis_result(client.ping())
    return bool(result)


async def close_redis_client(client: Redis) -> None:
    await client.aclose()
