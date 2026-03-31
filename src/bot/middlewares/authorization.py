from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject

from application.services.authorization import Permission
from bot.access import deny_event_access, resolve_required_permission
from domain.enums.roles import UserRole


class AuthorizationMiddleware(BaseMiddleware):
    """Resolve Telegram roles and enforce centralized access checks."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        authorization_service_factory = data.get("authorization_service_factory")
        if authorization_service_factory is None:
            return await handler(event, data)

        event_user_id = data.get("event_user_id")
        state = data.get("state")
        state_name = await self._get_state_name(state)
        required_permission = self._resolve_required_permission(
            event=event,
            state_name=state_name,
        )

        async with authorization_service_factory() as authorization_service:
            context = await authorization_service.resolve_context(
                telegram_user_id=event_user_id,
            )
            role = UserRole.USER if context is None else context.role
            data["authorization_context"] = context
            data["event_user_role"] = role
            data["event_is_super_admin"] = role == UserRole.SUPER_ADMIN

            if required_permission is not None and (
                context is None or not context.has_permission(required_permission)
            ):
                await deny_event_access(
                    event,
                    permission=required_permission,
                )
                return None

        return await handler(event, data)

    async def _get_state_name(self, state: object) -> str | None:
        if not isinstance(state, FSMContext):
            return None
        return await state.get_state()

    def _resolve_required_permission(
        self,
        *,
        event: TelegramObject,
        state_name: str | None,
    ) -> Permission | None:
        if isinstance(event, Message):
            return resolve_required_permission(
                message_text=event.text,
                state_name=state_name,
            )

        if isinstance(event, CallbackQuery):
            return resolve_required_permission(
                callback_data=event.data,
                state_name=state_name,
            )

        return None
