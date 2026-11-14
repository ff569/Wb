import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database import Repositories
from app.handlers.helpers import monitoring_text, user_limit
from app.keyboards import inline, reply
from app.texts import help_text, main_menu_text, welcome

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings) -> None:
    name = message.from_user.first_name or "друг"
    await message.answer(welcome(name, settings), reply_markup=reply.main_menu())
    logger.info("User %s started the bot", message.from_user.id)


@router.message(Command("help"))
@router.message(F.text == reply.BTN_HELP)
async def show_help(message: Message, settings: Settings) -> None:
    await message.answer(help_text(settings), reply_markup=inline.help_menu())


@router.message(F.text == reply.BTN_MAIN)
async def show_main_menu(message: Message, settings: Settings) -> None:
    await message.answer(main_menu_text(settings), reply_markup=reply.main_menu())


@router.message(F.text == reply.BTN_MONITORING)
async def show_monitoring(
    message: Message, repos: Repositories, settings: Settings, user_row
) -> None:
    count = await repos.tracks.count_for_user(message.from_user.id)
    limit = user_limit(settings, user_row)
    await message.answer(monitoring_text(count, limit, settings), reply_markup=inline.monitoring())


@router.callback_query(F.data == inline.CALLBACK_MAIN)
async def cb_main(callback: CallbackQuery, settings: Settings) -> None:
    await callback.message.edit_text(main_menu_text(settings))
    await callback.answer()


@router.callback_query(F.data == inline.CALLBACK_HELP)
async def cb_help(callback: CallbackQuery, settings: Settings) -> None:
    await callback.message.edit_text(help_text(settings), reply_markup=inline.help_menu())
    await callback.answer()
