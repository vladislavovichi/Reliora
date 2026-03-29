from __future__ import annotations

from redis.asyncio import Redis

from infrastructure.config import RedisConfig


def build_redis_client(config: RedisConfig) -> Redis:
    return Redis.from_url(
        config.url_with_auth,
        encoding="utf-8",
        decode_responses=True,
    )


async def ping_redis_client(client: Redis) -> bool:
    return bool(await client.ping())


async def close_redis_client(client: Redis) -> None:
    await client.aclose()
