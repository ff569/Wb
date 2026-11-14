from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_MAIN = "\U0001f3e0 Главное меню"
BTN_MONITORING = "\U0001f4ca Мониторинг"
BTN_SUBSCRIPTION = "\U0001f48e Подписка"
BTN_HELP = "\u2753 Помощь"
BTN_SETTINGS = "\u2699\ufe0f Настройки"

ALL_BUTTONS = {BTN_MAIN, BTN_MONITORING, BTN_SUBSCRIPTION, BTN_HELP, BTN_SETTINGS}


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_MONITORING), KeyboardButton(text=BTN_SUBSCRIPTION)],
            [KeyboardButton(text=BTN_HELP), KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Ссылка на товар WB или вопрос...",
    )
