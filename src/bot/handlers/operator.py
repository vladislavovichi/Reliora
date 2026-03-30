from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from application.services.helpdesk import HelpdeskServiceFactory
from application.use_cases.tickets import MacroSummary, QueuedTicketSummary, TicketDetailsSummary
from bot.callbacks import OperatorActionCallback, OperatorMacroCallback
from domain.enums.tickets import TicketEventType, TicketMessageSenderType, TicketStatus
from domain.tickets import InvalidTicketTransitionError, format_status_for_humans
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorPresenceHelper,
    TicketLockManager,
)

router = Router(name="operator")


class OperatorTicketStates(StatesGroup):
    replying = State()
    reassigning = State()


@router.message(Command("cancel"))
async def handle_cancel(
    message: Message,
    state: FSMContext,
) -> None:
    if await state.get_state() is None:
        await message.answer("Сейчас нет активного действия оператора.")
        return

    await state.clear()
    await message.answer("Действие оператора отменено.")


@router.message(Command("queue"))
async def handle_queue(
    message: Message,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await message.answer("Сервис временно недоступен. Попробуйте чуть позже.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        queued_tickets = await helpdesk_service.list_queued_tickets(limit=10)

    if not queued_tickets:
        await message.answer("Очередь пуста.")
        return

    await message.answer("Заявки в очереди:")
    for ticket in queued_tickets:
        await message.answer(
            _format_queued_ticket(ticket),
            reply_markup=_build_ticket_actions_markup(
                ticket_public_id=ticket.public_id,
                status=ticket.status,
            ),
        )


@router.message(Command("take"))
async def handle_take_next(
    message: Message,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить оператора для этого действия.")
        return

    if not await global_rate_limiter.allow():
        await message.answer("Сервис временно недоступен. Попробуйте чуть позже.")
        return

    await operator_presence.touch(operator_id=message.from_user.id)

    queue_lock = ticket_lock_manager.for_ticket("queue-next")
    if not await queue_lock.acquire():
        await message.answer("Очередь сейчас занята. Попробуйте чуть позже.")
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            ticket = await helpdesk_service.assign_next_ticket_to_operator(
                telegram_user_id=message.from_user.id,
                display_name=message.from_user.full_name,
                username=message.from_user.username,
            )
            ticket_details = None
            if ticket is not None:
                ticket_details = await helpdesk_service.get_ticket_details(
                    ticket_public_id=ticket.public_id
                )
    finally:
        await queue_lock.release()

    if ticket is None:
        await message.answer("Сейчас нет доступных заявок в очереди.")
        return

    if ticket_details is None:
        await message.answer(
            f"Следующая заявка {ticket.public_number} взята в работу. "
            f"Текущий статус: {_format_status(ticket.status)}."
        )
        return

    await message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.message(Command("ticket"))
async def handle_ticket_details(
    message: Message,
    command: CommandObject,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if command.args is None:
        await message.answer("Использование: /ticket <ticket_public_id>")
        return

    ticket_public_id = _parse_ticket_public_id(command.args.strip())
    if ticket_public_id is None:
        await message.answer("Некорректный идентификатор заявки.")
        return

    if not await global_rate_limiter.allow():
        await message.answer("Сервис временно недоступен. Попробуйте чуть позже.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id
        )

    if ticket_details is None:
        await message.answer("Заявка не найдена.")
        return

    await message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.message(Command("macros"))
async def handle_macros(
    message: Message,
    command: CommandObject,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    ticket_public_id: UUID | None = None
    if command.args is not None and command.args.strip():
        ticket_public_id = _parse_ticket_public_id(command.args.strip())
        if ticket_public_id is None:
            await message.answer("Использование: /macros [ticket_public_id]")
            return

    if not await global_rate_limiter.allow():
        await message.answer("Сервис временно недоступен. Попробуйте чуть позже.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        macros = await helpdesk_service.list_macros()
        ticket_details = None
        if ticket_public_id is not None:
            ticket_details = await helpdesk_service.get_ticket_details(
                ticket_public_id=ticket_public_id
            )

    if ticket_public_id is not None and ticket_details is None:
        await message.answer("Заявка не найдена.")
        return

    if not macros:
        await message.answer("Макросы пока не настроены.")
        return

    await message.answer(
        _format_macro_list(macros, ticket_details),
        reply_markup=(
            _build_macro_actions_markup(ticket_public_id=ticket_public_id, macros=macros)
            if ticket_public_id is not None
            else None
        ),
    )


@router.message(Command("tags"))
async def handle_ticket_tags(
    message: Message,
    command: CommandObject,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if command.args is None:
        await message.answer("Использование: /tags <ticket_public_id>")
        return

    ticket_public_id = _parse_ticket_public_id(command.args.strip())
    if ticket_public_id is None:
        await message.answer("Некорректный идентификатор заявки.")
        return

    if not await global_rate_limiter.allow():
        await message.answer("Сервис временно недоступен. Попробуйте чуть позже.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        tags_result = await helpdesk_service.list_ticket_tags(ticket_public_id=ticket_public_id)
        available_tags = await helpdesk_service.list_available_tags()

    if tags_result is None:
        await message.answer("Заявка не найдена.")
        return

    await message.answer(
        _format_ticket_tags_response(
            tags_result.public_number,
            tags_result.tags,
            available_tags,
        )
    )


@router.message(Command("alltags"))
async def handle_all_tags(
    message: Message,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await message.answer("Сервис временно недоступен. Попробуйте чуть позже.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        available_tags = await helpdesk_service.list_available_tags()

    if not available_tags:
        await message.answer("Теги пока не созданы.")
        return

    await message.answer("Доступные теги:\n" + "\n".join(f"- {tag}" for tag in available_tags))


@router.message(Command("addtag"))
async def handle_add_tag(
    message: Message,
    command: CommandObject,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    parsed = _parse_ticket_argument_with_text(command.args)
    if parsed is None:
        await message.answer("Использование: /addtag <ticket_public_id> <tag>")
        return

    ticket_public_id, tag_name = parsed
    if not await global_rate_limiter.allow():
        await message.answer("Сервис временно недоступен. Попробуйте чуть позже.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    lock = ticket_lock_manager.for_ticket(str(ticket_public_id))
    if not await lock.acquire():
        await message.answer("Заявка сейчас обрабатывается другим оператором.")
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            result = await helpdesk_service.add_tag_to_ticket(
                ticket_public_id=ticket_public_id,
                tag_name=tag_name,
            )
    finally:
        await lock.release()

    if result is None:
        await message.answer("Заявка не найдена.")
        return

    if result.changed:
        await message.answer(
            f"Тег {result.tag} добавлен к заявке {result.ticket.public_number}.\n"
            f"Текущие теги: {_format_tags(result.tags)}"
        )
        return

    await message.answer(
        f"Тег {result.tag} уже привязан к заявке {result.ticket.public_number}.\n"
        f"Текущие теги: {_format_tags(result.tags)}"
    )


@router.message(Command("rmtag"))
async def handle_remove_tag(
    message: Message,
    command: CommandObject,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    parsed = _parse_ticket_argument_with_text(command.args)
    if parsed is None:
        await message.answer("Использование: /rmtag <ticket_public_id> <tag>")
        return

    ticket_public_id, tag_name = parsed
    if not await global_rate_limiter.allow():
        await message.answer("Сервис временно недоступен. Попробуйте чуть позже.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    lock = ticket_lock_manager.for_ticket(str(ticket_public_id))
    if not await lock.acquire():
        await message.answer("Заявка сейчас обрабатывается другим оператором.")
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            result = await helpdesk_service.remove_tag_from_ticket(
                ticket_public_id=ticket_public_id,
                tag_name=tag_name,
            )
    finally:
        await lock.release()

    if result is None:
        await message.answer("Заявка не найдена.")
        return

    if result.changed:
        await message.answer(
            f"Тег {result.tag} снят с заявки {result.ticket.public_number}.\n"
            f"Текущие теги: {_format_tags(result.tags)}"
        )
        return

    await message.answer(
        f"Тег {result.tag} не найден у заявки {result.ticket.public_number}.\n"
        f"Текущие теги: {_format_tags(result.tags)}"
    )


@router.message(Command("stats"))
async def handle_stats(
    message: Message,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await message.answer("Сервис временно недоступен. Попробуйте чуть позже.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        stats = await helpdesk_service.get_basic_stats()

    lines = [
        "Статистика по заявкам:",
        f"всего={stats.total}",
        f"открыто={stats.open_total}",
    ]
    for status, count in sorted(stats.by_status.items(), key=lambda item: item[0].value):
        lines.append(f"{_format_status(status)}={count}")

    await message.answer("\n".join(lines))


@router.callback_query(OperatorActionCallback.filter(F.action == "view"))
async def handle_view_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await _respond_to_operator(callback, "Некорректный идентификатор заявки.")
        return

    if not await global_rate_limiter.allow():
        await _respond_to_operator(
            callback,
            "Сервис временно недоступен. Попробуйте чуть позже.",
        )
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id
        )

    if ticket_details is None:
        await _respond_to_operator(callback, "Заявка не найдена.")
        return

    await callback.answer(f"Открыта заявка {ticket_details.public_number}")
    if callback.message is not None:
        await callback.message.answer(
            _format_ticket_details(ticket_details),
            reply_markup=_build_ticket_actions_markup(
                ticket_public_id=ticket_details.public_id,
                status=ticket_details.status,
            ),
        )


@router.callback_query(OperatorActionCallback.filter(F.action == "take"))
async def handle_take_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket = None
    ticket_details = None
    error_message: str | None = None

    async with _operator_ticket_action(
        callback=callback,
        callback_data=callback_data,
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        ticket_lock_manager=ticket_lock_manager,
    ) as ticket_public_id:
        if ticket_public_id is None:
            return

        async with helpdesk_service_factory() as helpdesk_service:
            try:
                ticket = await helpdesk_service.assign_ticket_to_operator(
                    ticket_public_id=ticket_public_id,
                    telegram_user_id=callback.from_user.id,
                    display_name=callback.from_user.full_name,
                    username=callback.from_user.username,
                )
                if ticket is not None:
                    ticket_details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=ticket.public_id
                    )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)

    if error_message is not None:
        await _respond_to_operator(callback, error_message)
        return

    if ticket is None:
        await _respond_to_operator(callback, "Заявка не найдена.")
        return

    if ticket.event_type == TicketEventType.REASSIGNED:
        answer_text = f"Заявка {ticket.public_number} переназначена."
    else:
        answer_text = f"Заявка {ticket.public_number} назначена."

    if callback.message is None or ticket_details is None:
        await _respond_to_operator(callback, answer_text)
        return

    await callback.answer(answer_text)
    await callback.message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "reply"))
async def handle_reply_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await _respond_to_operator(callback, "Некорректный идентификатор заявки.")
        return

    if not await global_rate_limiter.allow():
        await _respond_to_operator(
            callback,
            "Сервис временно недоступен. Попробуйте чуть позже.",
        )
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id
        )

    if ticket_details is None:
        await _respond_to_operator(callback, "Заявка не найдена.")
        return

    await state.set_state(OperatorTicketStates.replying)
    await state.update_data(ticket_public_id=str(ticket_public_id))
    await _respond_to_operator(
        callback,
        f"Режим ответа для заявки {ticket_details.public_number} включен.",
        (
            f"Отправьте текст ответа для заявки {ticket_details.public_number}.\n"
            "Используйте /cancel, чтобы отменить действие."
        ),
    )


@router.callback_query(OperatorMacroCallback.filter())
async def handle_apply_macro(
    callback: CallbackQuery,
    callback_data: OperatorMacroCallback,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await _respond_to_operator(callback, "Некорректный идентификатор заявки.")
        return

    if not await global_rate_limiter.allow():
        await _respond_to_operator(
            callback,
            "Сервис временно недоступен. Попробуйте чуть позже.",
        )
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    lock = ticket_lock_manager.for_ticket(callback_data.ticket_public_id)
    if not await lock.acquire():
        await _respond_to_operator(callback, "Заявка сейчас обрабатывается другим оператором.")
        return

    macro_result = None
    ticket_details = None
    error_message: str | None = None
    try:
        async with helpdesk_service_factory() as helpdesk_service:
            try:
                macro_result = await helpdesk_service.apply_macro_to_ticket(
                    ticket_public_id=ticket_public_id,
                    macro_id=callback_data.macro_id,
                    telegram_user_id=callback.from_user.id,
                    display_name=callback.from_user.full_name,
                    username=callback.from_user.username,
                )
                if macro_result is not None:
                    ticket_details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=ticket_public_id
                    )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)
    finally:
        await lock.release()

    if error_message is not None:
        await _respond_to_operator(callback, error_message)
        return

    if macro_result is None:
        await _respond_to_operator(callback, "Не удалось применить макрос.")
        return

    delivery_error: str | None = None
    try:
        await bot.send_message(macro_result.client_chat_id, macro_result.macro.body)
    except TelegramAPIError as exc:
        delivery_error = str(exc)

    if callback.message is None or ticket_details is None:
        answer_text = f"Макрос «{macro_result.macro.title}» применен."
        if delivery_error is not None:
            answer_text = (
                f"{answer_text} Ответ сохранен, но доставить его клиенту не удалось: "
                f"{delivery_error}"
            )
        await _respond_to_operator(callback, answer_text)
        return

    if delivery_error is None:
        await callback.answer(f"Макрос «{macro_result.macro.title}» отправлен.")
    else:
        await callback.answer(f"Макрос «{macro_result.macro.title}» сохранен.")
        await callback.message.answer(
            f"Макрос «{macro_result.macro.title}» сохранен, "
            f"но доставить его клиенту не удалось: {delivery_error}"
        )

    await callback.message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.message(StateFilter(OperatorTicketStates.replying), F.text)
async def handle_reply_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    if message.from_user is None or message.text is None:
        await message.answer("Не удалось определить оператора для этого действия.")
        return

    if message.text.startswith("/"):
        await message.answer(
            "Сейчас активен режим ответа. "
            "Отправьте текст или используйте /cancel."
        )
        return

    if not await global_rate_limiter.allow():
        await message.answer("Сервис временно недоступен. Попробуйте чуть позже.")
        return

    await operator_presence.touch(operator_id=message.from_user.id)

    state_data = await state.get_data()
    ticket_public_id = _parse_ticket_public_id(state_data.get("ticket_public_id"))
    if ticket_public_id is None:
        await state.clear()
        await message.answer("Контекст ответа потерян. Запустите действие заново.")
        return

    lock = ticket_lock_manager.for_ticket(str(ticket_public_id))
    if not await lock.acquire():
        await message.answer("Заявка сейчас обрабатывается другим оператором.")
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            try:
                reply_result = await helpdesk_service.reply_to_ticket_as_operator(
                    ticket_public_id=ticket_public_id,
                    telegram_user_id=message.from_user.id,
                    display_name=message.from_user.full_name,
                    username=message.from_user.username,
                    telegram_message_id=message.message_id,
                    text=message.text,
                )
            except InvalidTicketTransitionError as exc:
                await state.clear()
                await message.answer(str(exc))
                return

            if reply_result is None:
                await state.clear()
                await message.answer("Заявка не найдена.")
                return

            ticket_details = await helpdesk_service.get_ticket_details(
                ticket_public_id=ticket_public_id
            )
    finally:
        await lock.release()

    await state.clear()

    delivery_error: str | None = None
    try:
        await bot.send_message(
            reply_result.client_chat_id,
            f"Ответ по заявке {reply_result.ticket.public_number}:\n{message.text}",
        )
    except TelegramAPIError as exc:
        delivery_error = str(exc)

    if delivery_error is None:
        await message.answer(f"Ответ по заявке {reply_result.ticket.public_number} отправлен.")
    else:
        await message.answer(
            f"Ответ по заявке {reply_result.ticket.public_number} сохранен, "
            f"но доставить его клиенту не удалось: {delivery_error}"
        )

    if ticket_details is not None:
        await message.answer(
            _format_ticket_details(ticket_details),
            reply_markup=_build_ticket_actions_markup(
                ticket_public_id=ticket_details.public_id,
                status=ticket_details.status,
            ),
        )


@router.callback_query(OperatorActionCallback.filter(F.action == "reassign"))
async def handle_reassign_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await _respond_to_operator(callback, "Некорректный идентификатор заявки.")
        return

    if not await global_rate_limiter.allow():
        await _respond_to_operator(
            callback,
            "Сервис временно недоступен. Попробуйте чуть позже.",
        )
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id
        )

    if ticket_details is None:
        await _respond_to_operator(callback, "Заявка не найдена.")
        return

    await state.set_state(OperatorTicketStates.reassigning)
    await state.update_data(ticket_public_id=str(ticket_public_id))
    await _respond_to_operator(
        callback,
        f"Режим переназначения для заявки {ticket_details.public_number} включен.",
        (
            "Отправьте идентификатор пользователя Telegram "
            "целевого оператора, при необходимости добавьте "
            "имя.\nПример: 123456789 Иван Иванов\nИспользуйте /cancel, чтобы отменить действие."
        ),
    )


@router.message(StateFilter(OperatorTicketStates.reassigning), F.text)
async def handle_reassign_message(
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    if message.text is None:
        await message.answer("Отправьте идентификатор пользователя Telegram целевого оператора.")
        return

    if message.text.startswith("/"):
        await message.answer(
            "Сейчас активен режим переназначения. "
            "Отправьте данные оператора\n"
            "или используйте /cancel."
        )
        return

    if not await global_rate_limiter.allow():
        await message.answer("Сервис временно недоступен. Попробуйте чуть позже.")
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    target = _parse_reassign_target(message.text)
    if target is None:
        await message.answer(
            "Некорректный ввод. Отправьте идентификатор "
            "пользователя Telegram, при необходимости добавьте имя."
        )
        return

    state_data = await state.get_data()
    ticket_public_id = _parse_ticket_public_id(state_data.get("ticket_public_id"))
    if ticket_public_id is None:
        await state.clear()
        await message.answer("Контекст переназначения потерян. Запустите действие заново.")
        return

    lock = ticket_lock_manager.for_ticket(str(ticket_public_id))
    if not await lock.acquire():
        await message.answer("Заявка сейчас обрабатывается другим оператором.")
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            try:
                ticket = await helpdesk_service.assign_ticket_to_operator(
                    ticket_public_id=ticket_public_id,
                    telegram_user_id=target[0],
                    display_name=target[1],
                    username=None,
                )
            except InvalidTicketTransitionError as exc:
                await state.clear()
                await message.answer(str(exc))
                return

            if ticket is None:
                await state.clear()
                await message.answer("Заявка не найдена.")
                return

            ticket_details = await helpdesk_service.get_ticket_details(
                ticket_public_id=ticket_public_id
            )
    finally:
        await lock.release()

    await state.clear()

    if ticket_details is None:
        await message.answer(f"Заявка {ticket.public_number} обновлена.")
        return

    if ticket.event_type == TicketEventType.REASSIGNED:
        response_text = f"Заявка {ticket.public_number} переназначена."
    else:
        response_text = f"Заявка {ticket.public_number} назначена."

    await message.answer(response_text)
    await message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "close"))
async def handle_close_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket = None
    ticket_details = None
    error_message: str | None = None

    async with _operator_ticket_action(
        callback=callback,
        callback_data=callback_data,
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        ticket_lock_manager=ticket_lock_manager,
    ) as ticket_public_id:
        if ticket_public_id is None:
            return

        async with helpdesk_service_factory() as helpdesk_service:
            try:
                ticket = await helpdesk_service.close_ticket(ticket_public_id=ticket_public_id)
                if ticket is not None:
                    ticket_details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=ticket_public_id
                    )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)

    if error_message is not None:
        await _respond_to_operator(callback, error_message)
        return

    if ticket is None:
        await _respond_to_operator(callback, "Заявка не найдена.")
        return

    if callback.message is None or ticket_details is None:
        await _respond_to_operator(callback, f"Заявка {ticket.public_number} закрыта.")
        return

    await callback.answer(f"Заявка {ticket.public_number} закрыта.")
    await callback.message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "escalate"))
async def handle_escalate_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket = None
    ticket_details = None
    error_message: str | None = None

    async with _operator_ticket_action(
        callback=callback,
        callback_data=callback_data,
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        ticket_lock_manager=ticket_lock_manager,
    ) as ticket_public_id:
        if ticket_public_id is None:
            return

        async with helpdesk_service_factory() as helpdesk_service:
            try:
                ticket = await helpdesk_service.escalate_ticket(ticket_public_id=ticket_public_id)
                if ticket is not None:
                    ticket_details = await helpdesk_service.get_ticket_details(
                        ticket_public_id=ticket_public_id
                    )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)

    if error_message is not None:
        await _respond_to_operator(callback, error_message)
        return

    if ticket is None:
        await _respond_to_operator(callback, "Заявка не найдена.")
        return

    if callback.message is None or ticket_details is None:
        await _respond_to_operator(callback, f"Заявка {ticket.public_number} эскалирована.")
        return

    await callback.answer(f"Заявка {ticket.public_number} эскалирована.")
    await callback.message.answer(
        _format_ticket_details(ticket_details),
        reply_markup=_build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@asynccontextmanager
async def _operator_ticket_action(
    *,
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> AsyncIterator[UUID | None]:
    ticket_public_id = _parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await _respond_to_operator(callback, "Некорректный идентификатор заявки.")
        yield None
        return

    if not await global_rate_limiter.allow():
        await _respond_to_operator(
            callback,
            "Сервис временно недоступен. Попробуйте чуть позже.",
        )
        yield None
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    lock = ticket_lock_manager.for_ticket(callback_data.ticket_public_id)
    if not await lock.acquire():
        await _respond_to_operator(
            callback,
            "Заявка сейчас обрабатывается другим оператором.",
        )
        yield None
        return

    try:
        yield ticket_public_id
    finally:
        await lock.release()


async def _respond_to_operator(
    callback: CallbackQuery,
    answer_text: str,
    message_text: str | None = None,
) -> None:
    await callback.answer(answer_text)
    if callback.message is not None and message_text is not None:
        await callback.message.answer(message_text)


def _build_ticket_actions_markup(
    *,
    ticket_public_id: UUID,
    status: TicketStatus,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)

    first_row = [
        (
            "Открыть",
            OperatorActionCallback(action="view", ticket_public_id=callback_value).pack(),
        )
    ]
    if status == TicketStatus.QUEUED:
        first_row.append(
            (
                "Взять",
                OperatorActionCallback(action="take", ticket_public_id=callback_value).pack(),
            )
        )
    elif status in {TicketStatus.ASSIGNED, TicketStatus.ESCALATED}:
        first_row.append(
            (
                "Ответить",
                OperatorActionCallback(action="reply", ticket_public_id=callback_value).pack(),
            )
        )
    builder.row(*[_build_callback_button(text, data) for text, data in first_row])

    second_row: list[tuple[str, str]] = []
    if status in {TicketStatus.QUEUED, TicketStatus.ASSIGNED}:
        second_row.append(
            (
                "Эскалировать",
                OperatorActionCallback(action="escalate", ticket_public_id=callback_value).pack(),
            )
        )
    if status != TicketStatus.CLOSED:
        second_row.append(
            (
                "Закрыть",
                OperatorActionCallback(action="close", ticket_public_id=callback_value).pack(),
            )
        )
    if second_row:
        builder.row(*[_build_callback_button(text, data) for text, data in second_row])

    if status != TicketStatus.CLOSED:
        builder.row(
            _build_callback_button(
                "Переназначить",
                OperatorActionCallback(action="reassign", ticket_public_id=callback_value).pack(),
            )
        )

    return builder.as_markup()


def _build_macro_actions_markup(
    *,
    ticket_public_id: UUID,
    macros: Sequence[MacroSummary],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)
    for macro in macros:
        builder.row(
            _build_callback_button(
                _format_macro_button_text(macro),
                OperatorMacroCallback(
                    ticket_public_id=callback_value,
                    macro_id=macro.id,
                ).pack(),
            )
        )
    return builder.as_markup()


def _build_callback_button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _format_queued_ticket(ticket: QueuedTicketSummary) -> str:
    return "\n".join(
        [
            f"{ticket.public_number}",
            f"Публичный идентификатор: {ticket.public_id}",
            f"Статус: {_format_status(ticket.status)}",
            f"Приоритет: {_format_priority(ticket.priority)}",
            f"Тема: {ticket.subject}",
        ]
    )


def _format_ticket_details(ticket: TicketDetailsSummary) -> str:
    assigned_operator = "не назначен"
    if ticket.assigned_operator_id is not None:
        assigned_name = ticket.assigned_operator_name or "оператор"
        assigned_operator = f"{assigned_name} (id={ticket.assigned_operator_id})"

    lines = [
        f"{ticket.public_number}",
        f"Публичный идентификатор: {ticket.public_id}",
        f"Статус: {_format_status(ticket.status)}",
        f"Приоритет: {_format_priority(ticket.priority)}",
        f"Тема: {ticket.subject}",
        f"Назначен: {assigned_operator}",
        f"Теги: {_format_tags(ticket.tags)}",
        (
            "Последнее сообщение: "
            f"{_format_last_message(ticket.last_message_text, ticket.last_message_sender_type)}"
        ),
    ]
    return "\n".join(lines)


def _format_macro_list(
    macros: Sequence[MacroSummary],
    ticket_details: TicketDetailsSummary | None,
) -> str:
    lines: list[str] = []
    if ticket_details is None:
        lines.append("Доступные макросы:")
    else:
        lines.append(f"Макросы для заявки {ticket_details.public_number}:")

    for macro in macros:
        lines.append(f"{macro.id}. {macro.title} — {_format_macro_preview(macro.body)}")

    if ticket_details is None:
        lines.append("Используйте /macros <ticket_public_id>, чтобы применить макрос кнопкой.")
    else:
        lines.append("Выберите макрос кнопкой ниже.")
    return "\n".join(lines)


def _format_ticket_tags_response(
    public_number: str,
    ticket_tags: Sequence[str],
    available_tags: Sequence[str],
) -> str:
    lines = [
        f"Теги заявки {public_number}: {_format_tags(ticket_tags)}",
        f"Доступные теги: {_format_tags(available_tags)}",
        "Добавить: /addtag <ticket_public_id> <tag>",
        "Снять: /rmtag <ticket_public_id> <tag>",
    ]
    return "\n".join(lines)


def _format_tags(tags: Sequence[str]) -> str:
    if not tags:
        return "-"
    return ", ".join(tags)


def _format_last_message(
    message_text: str | None,
    sender_type: TicketMessageSenderType | None,
) -> str:
    if not message_text:
        return "-"

    preview = " ".join(message_text.split())
    if len(preview) > 120:
        preview = f"{preview[:117]}..."

    if sender_type is None:
        return preview

    return f"[{_format_sender_type(sender_type)}] {preview}"


def _format_macro_preview(text: str) -> str:
    preview = " ".join(text.split())
    if len(preview) > 80:
        return f"{preview[:77]}..."
    return preview


def _format_macro_button_text(macro: MacroSummary) -> str:
    label = macro.title.strip() or f"Макрос {macro.id}"
    if len(label) > 32:
        return f"{label[:29]}..."
    return label


def _format_status(status: TicketStatus) -> str:
    return format_status_for_humans(status)


def _format_priority(priority: str) -> str:
    priority_labels = {
        "low": "низкий",
        "normal": "обычный",
        "high": "высокий",
        "urgent": "срочный",
    }
    return priority_labels.get(priority, priority)


def _format_sender_type(sender_type: TicketMessageSenderType) -> str:
    sender_labels = {
        TicketMessageSenderType.CLIENT: "клиент",
        TicketMessageSenderType.OPERATOR: "оператор",
        TicketMessageSenderType.SYSTEM: "система",
    }
    return sender_labels.get(sender_type, sender_type.value)


def _parse_ticket_public_id(value: str | None) -> UUID | None:
    if value is None:
        return None

    try:
        return UUID(value)
    except ValueError:
        return None


def _parse_ticket_argument_with_text(args: str | None) -> tuple[UUID, str] | None:
    if args is None:
        return None

    parts = args.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None

    ticket_public_id = _parse_ticket_public_id(parts[0])
    if ticket_public_id is None:
        return None

    tag_name = parts[1].strip()
    if not tag_name:
        return None

    return ticket_public_id, tag_name


def _parse_reassign_target(text: str) -> tuple[int, str] | None:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return None

    try:
        telegram_user_id = int(parts[0])
    except ValueError:
        return None

    display_name = parts[1].strip() if len(parts) > 1 else f"Оператор {telegram_user_id}"
    if not display_name:
        display_name = f"Оператор {telegram_user_id}"
    return telegram_user_id, display_name
