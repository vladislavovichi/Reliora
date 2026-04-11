from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from application.services.diagnostics import DiagnosticsService
from application.services.helpdesk.service import HelpdeskServiceFactory
from bot.formatters.system import build_help_text, build_start_text, format_diagnostics_report
from bot.handlers.user.operator_invites import start_operator_invite_onboarding
from bot.keyboards.reply.main_menu import build_main_menu
from bot.texts.buttons import HELP_BUTTON_TEXT
from bot.texts.system import PING_RESPONSE_TEXT
from domain.enums.roles import UserRole

router = Router(name="system")


@router.message(CommandStart())
async def handle_start(
    message: Message,
    command: CommandObject | None,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    event_user_role: UserRole = UserRole.USER,
) -> None:
    if (
        event_user_role == UserRole.USER
        and command is not None
        and isinstance(command.args, str)
        and command.args.strip()
    ):
        started = await start_operator_invite_onboarding(
            message=message,
            state=state,
            helpdesk_service_factory=helpdesk_service_factory,
            code=command.args.strip(),
        )
        if started:
            return
    await message.answer(
        build_start_text(event_user_role),
        reply_markup=build_main_menu(event_user_role),
    )


@router.message(Command("help"))
@router.message(F.text == HELP_BUTTON_TEXT)
async def handle_help(
    message: Message,
    event_user_role: UserRole = UserRole.USER,
) -> None:
    await message.answer(
        build_help_text(event_user_role),
        reply_markup=build_main_menu(event_user_role),
    )


@router.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    await message.answer(PING_RESPONSE_TEXT)


@router.message(Command("health"))
async def handle_health(
    message: Message,
    diagnostics_service: DiagnosticsService,
    event_user_role: UserRole = UserRole.USER,
) -> None:
    report = await diagnostics_service.collect_report()
    await message.answer(
        format_diagnostics_report(report),
        reply_markup=build_main_menu(event_user_role),
    )
