"""Redis client scaffolding."""

from infrastructure.redis.client import build_redis_client, close_redis_client, ping_redis_client
from infrastructure.redis.contracts import (
    ChatRateLimiter,
    GlobalRateLimiter,
    OperatorPresenceHelper,
    SLADeadlineScheduler,
    SLATimeoutProcessor,
    TicketLock,
    TicketLockManager,
    TicketStreamConsumer,
    TicketStreamPublisher,
)
from infrastructure.redis.keys import (
    GLOBAL_RATE_LIMIT_KEY,
    SLA_DEADLINES_KEY,
    STREAM_TICKETS_NEW,
    chat_rate_limit_key,
    operator_presence_key,
    ticket_lock_key,
)
from infrastructure.redis.locks import RedisTicketLock, RedisTicketLockManager
from infrastructure.redis.presence import RedisOperatorPresenceHelper
from infrastructure.redis.rate_limit import RedisChatRateLimiter, RedisGlobalRateLimiter
from infrastructure.redis.sla import RedisSLADeadlineScheduler, RedisSLATimeoutProcessor
from infrastructure.redis.streams import RedisTicketStreamConsumer, RedisTicketStreamPublisher

__all__ = [
    "ChatRateLimiter",
    "GLOBAL_RATE_LIMIT_KEY",
    "GlobalRateLimiter",
    "OperatorPresenceHelper",
    "RedisChatRateLimiter",
    "RedisGlobalRateLimiter",
    "RedisOperatorPresenceHelper",
    "RedisSLADeadlineScheduler",
    "RedisSLATimeoutProcessor",
    "RedisTicketLock",
    "RedisTicketLockManager",
    "RedisTicketStreamConsumer",
    "RedisTicketStreamPublisher",
    "SLADeadlineScheduler",
    "SLATimeoutProcessor",
    "SLA_DEADLINES_KEY",
    "STREAM_TICKETS_NEW",
    "TicketLock",
    "TicketLockManager",
    "TicketStreamConsumer",
    "TicketStreamPublisher",
    "build_redis_client",
    "chat_rate_limit_key",
    "close_redis_client",
    "operator_presence_key",
    "ping_redis_client",
    "ticket_lock_key",
]
