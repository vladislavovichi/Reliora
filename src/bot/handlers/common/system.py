from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from application.services.diagnostics import DiagnosticsService
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.formatters.system import build_help_text, build_start_text, format_diagnostics_report
from bot.handlers.user.operator_invites import start_operator_invite_onboarding
from bot.keyboards.reply.main_menu import build_main_menu
from bot.texts.buttons import HELP_BUTTON_TEXT
from bot.texts.system import PING_RESPONSE_TEXT
from domain.enums.roles import UserRole
from infrastructure.config.settings import Settings

router = Router(name="system")


@router.message(CommandStart())
async def handle_start(
    message: Message,
    command: CommandObject | None,
    state: FSMContext,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    settings: Settings,
    event_user_role: UserRole = UserRole.USER,
) -> None:
    mini_app_url = settings.mini_app.telegram_launch_url
    mini_app_available = settings.mini_app.public_url_is_valid
    if (
        event_user_role == UserRole.USER
        and command is not None
        and isinstance(command.args, str)
        and command.args.strip()
    ):
        started = await start_operator_invite_onboarding(
            message=message,
            state=state,
            helpdesk_backend_client_factory=helpdesk_backend_client_factory,
            code=command.args.strip(),
        )
        if started:
            return
    await message.answer(
        build_start_text(event_user_role, mini_app_available=mini_app_available),
        reply_markup=build_main_menu(
            event_user_role,
            mini_app_url=mini_app_url,
        ),
    )


@router.message(Command("help"))
@router.message(F.text == HELP_BUTTON_TEXT)
async def handle_help(
    message: Message,
    settings: Settings,
    event_user_role: UserRole = UserRole.USER,
) -> None:
    mini_app_url = settings.mini_app.telegram_launch_url
    await message.answer(
        build_help_text(
            event_user_role,
            mini_app_available=settings.mini_app.public_url_is_valid,
        ),
        reply_markup=build_main_menu(
            event_user_role,
            mini_app_url=mini_app_url,
        ),
    )


@router.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    await message.answer(PING_RESPONSE_TEXT)


@router.message(Command("health"))
async def handle_health(
    message: Message,
    diagnostics_service: DiagnosticsService,
    settings: Settings,
    event_user_role: UserRole = UserRole.USER,
) -> None:
    report = await diagnostics_service.collect_report()
    await message.answer(
        format_diagnostics_report(report),
        reply_markup=build_main_menu(
            event_user_role,
            mini_app_url=settings.mini_app.telegram_launch_url,
        ),
    )
