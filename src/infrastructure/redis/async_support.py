from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import cast


async def resolve_redis_result[ResultT](value: Awaitable[ResultT] | ResultT) -> ResultT:
    if isawaitable(value):
        return await cast(Awaitable[ResultT], value)
    return value
