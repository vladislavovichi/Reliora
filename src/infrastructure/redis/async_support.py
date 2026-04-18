from __future__ import annotations

from collections.abc import Awaitable


async def resolve_redis_result[ResultT](value: Awaitable[ResultT] | ResultT) -> ResultT:
    if isinstance(value, Awaitable):
        return await value
    return value
