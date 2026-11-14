import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database import Repositories
from app.keyboards import inline, reply
from app.texts import SETTINGS, SETTINGS_ALERT_OFF, SETTINGS_ALERT_ON, SETTINGS_SAVED

logger = logging.getLogger(__name__)
router = Router()


def settings_text(settings: Settings, user_row) -> str:
    return SETTINGS.format(
        alert_status=SETTINGS_ALERT_ON if user_row["alerts_enabled"] else SETTINGS_ALERT_OFF,
        drop_pct=user_row["drop_pct"] or settings.default_drop_pct,
    )


@router.message(F.text == reply.BTN_SETTINGS)
async def show_settings(message: Message, repos: Repositories, settings: Settings, user_row) -> None:
    await message.answer(
        settings_text(settings, user_row),
        reply_markup=inline.settings_menu(bool(user_row["alerts_enabled"]), user_row["drop_pct"]),
    )


@router.callback_query(F.data == inline.CALLBACK_SETTINGS)
async def cb_settings(callback: CallbackQuery, repos: Repositories, settings: Settings, user_row) -> None:
    await callback.message.edit_text(
        settings_text(settings, user_row),
        reply_markup=inline.settings_menu(bool(user_row["alerts_enabled"]), user_row["drop_pct"]),
    )
    await callback.answer()


@router.callback_query(F.data == inline.CALLBACK_TOGGLE_ALERTS)
async def cb_toggle_alerts(callback: CallbackQuery, repos: Repositories, settings: Settings) -> None:
    user_id = callback.from_user.id
    row = await repos.users.get(user_id)
    new_state = not bool(row["alerts_enabled"])
    await repos.users.set_alerts_enabled(user_id, new_state)
    await repos.users.set_drop_pct(user_id, row["drop_pct"] or settings.default_drop_pct)
    await callback.message.edit_text(
        SETTINGS.format(
            alert_status=SETTINGS_ALERT_ON if new_state else SETTINGS_ALERT_OFF,
            drop_pct=row["drop_pct"] or settings.default_drop_pct,
        ),
        reply_markup=inline.settings_menu(new_state, row["drop_pct"] or settings.default_drop_pct),
    )
    await callback.answer(SETTINGS_SAVED)
    logger.info("User %s toggled alerts to %s", user_id, new_state)


@router.callback_query(F.data.startswith(inline.CALLBACK_SET_PCT + ":"))
async def cb_set_pct(callback: CallbackQuery, repos: Repositories, settings: Settings) -> None:
    user_id = callback.from_user.id
    pct = int(callback.data.split(":", 1)[1])
    row = await repos.users.get(user_id)
    await repos.users.set_drop_pct(user_id, pct)
    await callback.message.edit_text(
        SETTINGS.format(
            alert_status=SETTINGS_ALERT_ON if row["alerts_enabled"] else SETTINGS_ALERT_OFF,
            drop_pct=pct,
        ),
        reply_markup=inline.settings_menu(bool(row["alerts_enabled"]), pct),
    )
    await callback.answer(SETTINGS_SAVED)
    logger.info("User %s set drop pct to %s", user_id, pct)
