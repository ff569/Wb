from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CALLBACK_MAIN = "nav:main"
CALLBACK_MONITORING = "nav:monitoring"
CALLBACK_ADD_PRODUCT = "mon:add"
CALLBACK_MY_PRODUCTS = "mon:list"
CALLBACK_CHECK_NOW = "mon:check"
CALLBACK_HELP = "nav:help"
CALLBACK_FAQ = "help:faq"
CALLBACK_SETTINGS = "nav:settings"
CALLBACK_TOGGLE_ALERTS = "set:alerts"
CALLBACK_SET_PCT = "set:pct"
CALLBACK_PAY = "sub:pay"
CALLBACK_DELETE = "tr:del"
CALLBACK_DELETE_CONFIRM = "tr:dely"

DROP_PCT_CHOICES = (3, 5, 10, 15)


def back_to_monitoring() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f519 К мониторингу", callback_data=CALLBACK_MONITORING)]
        ]
    )


def monitoring() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\u2795 Добавить товар", callback_data=CALLBACK_ADD_PRODUCT)],
            [InlineKeyboardButton(text="\U0001f4cb Мои товары", callback_data=CALLBACK_MY_PRODUCTS)],
            [InlineKeyboardButton(text="\U0001f504 Проверить сейчас", callback_data=CALLBACK_CHECK_NOW)],
            [InlineKeyboardButton(text="\u2139\ufe0f Как это работает", callback_data=CALLBACK_HELP)],
        ]
    )


def product_actions(nm: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="\U0001f5d1 Удалить", callback_data=f"{CALLBACK_DELETE}:{nm}"),
                InlineKeyboardButton(
                    text="\U0001f30e Открыть на WB",
                    url=f"https://www.wildberries.ru/catalog/{nm}/detail.aspx",
                ),
            ]
        ]
    )


def delete_confirm(nm: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\u2705 Да, удалить", callback_data=f"{CALLBACK_DELETE_CONFIRM}:{nm}"
                ),
                InlineKeyboardButton(text="\u274c Отмена", callback_data=CALLBACK_MY_PRODUCTS),
            ]
        ]
    )


def subscription(pay_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pay_text, callback_data=CALLBACK_PAY)],
            [InlineKeyboardButton(text="\u2753 FAQ", callback_data=CALLBACK_FAQ)],
            [InlineKeyboardButton(text="\U0001f519 Назад", callback_data=CALLBACK_MAIN)],
        ]
    )


def help_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f4cb FAQ — частые вопросы", callback_data=CALLBACK_FAQ)],
            [InlineKeyboardButton(text="\U0001f519 Назад", callback_data=CALLBACK_MAIN)],
        ]
    )


def settings_menu(alerts_on: bool, current_pct: int) -> InlineKeyboardMarkup:
    alert_btn = "\U0001f514 Алерты: вкл" if alerts_on else "\U0001f507 Алерты: выкл"
    pct_row = [
        InlineKeyboardButton(
            text=f"{pct}%" + (" \u2705" if pct == current_pct else ""),
            callback_data=f"{CALLBACK_SET_PCT}:{pct}",
        )
        for pct in DROP_PCT_CHOICES
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=alert_btn, callback_data=CALLBACK_TOGGLE_ALERTS)],
            pct_row,
            [InlineKeyboardButton(text="\U0001f519 Назад", callback_data=CALLBACK_MAIN)],
        ]
    )


def back_to_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="\U0001f519 Назад", callback_data=CALLBACK_MAIN)]]
    )
