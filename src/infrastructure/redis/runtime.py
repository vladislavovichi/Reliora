from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from application.contracts.runtime import (
    ChatRateLimiter,
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    SLADeadlineScheduler,
    SLATimeoutProcessor,
    TicketLiveSessionStore,
    TicketLockManager,
    TicketStreamConsumer,
    TicketStreamPublisher,
)
from infrastructure.redis.locks import RedisTicketLockManager
from infrastructure.redis.operator_context import RedisTicketLiveSessionStore
from infrastructure.redis.presence import RedisOperatorPresenceHelper
from infrastructure.redis.rate_limit import RedisChatRateLimiter, RedisGlobalRateLimiter
from infrastructure.redis.sla import RedisSLADeadlineScheduler, RedisSLATimeoutProcessor
from infrastructure.redis.streams import RedisTicketStreamConsumer, RedisTicketStreamPublisher


@dataclass(slots=True)
class RedisWorkflowRuntime:
    ticket_lock_manager: TicketLockManager
    global_rate_limiter: GlobalRateLimiter
    chat_rate_limiter: ChatRateLimiter
    operator_presence: OperatorPresenceHelper
    ticket_live_session_store: TicketLiveSessionStore
    operator_active_ticket_store: OperatorActiveTicketStore
    sla_deadline_scheduler: SLADeadlineScheduler
    ticket_stream_publisher: TicketStreamPublisher
    ticket_stream_consumer: TicketStreamConsumer
    sla_timeout_processor: SLATimeoutProcessor


def build_redis_workflow_runtime(redis: Redis) -> RedisWorkflowRuntime:
    sla_deadline_scheduler = RedisSLADeadlineScheduler(redis)
    ticket_live_session_store = RedisTicketLiveSessionStore(redis)
    return RedisWorkflowRuntime(
        ticket_lock_manager=RedisTicketLockManager(redis),
        global_rate_limiter=RedisGlobalRateLimiter(redis),
        chat_rate_limiter=RedisChatRateLimiter(redis),
        operator_presence=RedisOperatorPresenceHelper(redis),
        ticket_live_session_store=ticket_live_session_store,
        operator_active_ticket_store=ticket_live_session_store,
        sla_deadline_scheduler=sla_deadline_scheduler,
        ticket_stream_publisher=RedisTicketStreamPublisher(redis),
        ticket_stream_consumer=RedisTicketStreamConsumer(redis),
        sla_timeout_processor=RedisSLATimeoutProcessor(sla_deadline_scheduler),
    )
