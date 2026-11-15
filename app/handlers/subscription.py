import logging
import time
from datetime import datetime

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from app.config import Settings
from app.database import Repositories
from app.handlers.helpers import is_pro
from app.keyboards import inline, reply
from app.texts import (
    faq,
    PAY_ALREADY_PRO,
    PAY_INVOICE_DESCRIPTION,
    PAY_INVOICE_TITLE,
    PAY_SUCCESS,
    STATUS_FREE,
    STATUS_PRO,
    SUBSCRIPTION,
)

logger = logging.getLogger(__name__)
router = Router()


def _status_text(user_row) -> str:
    if is_pro(user_row):
        till = datetime.fromtimestamp(user_row["paid_until"]).strftime("%d.%m.%Y")
        return STATUS_PRO.format(till=till)
    return STATUS_FREE


def subscription_text(settings: Settings, user_row) -> str:
    return SUBSCRIPTION.format(
        status=_status_text(user_row),
        FREE="\U0001f193",
        free_limit=settings.free_limit,
        pro_limit=settings.pro_limit,
        pro_price=settings.pro_price_stars,
    )


@router.message(F.text == reply.BTN_SUBSCRIPTION)
async def show_subscription(message: Message, settings: Settings, user_row) -> None:
    await message.answer(
        subscription_text(settings, user_row),
        reply_markup=inline.subscription(f"\u2b50\ufe0f Оплатить {settings.pro_price_stars} Stars"),
    )


@router.callback_query(F.data == inline.CALLBACK_FAQ)
async def cb_faq(callback: CallbackQuery, settings: Settings) -> None:
    await callback.message.edit_text(faq(settings), reply_markup=inline.back_to_main())
    await callback.answer()


@router.callback_query(F.data == inline.CALLBACK_PAY)
async def cb_pay(callback: CallbackQuery, bot, settings: Settings) -> None:
    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title=PAY_INVOICE_TITLE,
        description=PAY_INVOICE_DESCRIPTION,
        payload="pro_subscription",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Pro на 30 дней", amount=settings.pro_price_stars)],
    )
    await callback.answer()
    logger.info("Invoice sent to %s", callback.from_user.id)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message, repos: Repositories, settings: Settings
) -> None:
    payment = message.successful_payment
    user_id = message.from_user.id

    if await repos.payments.exists_charge(payment.telegram_payment_charge_id):
        logger.warning("Duplicate payment from %s, ignoring", user_id)
        return

    user_row = await repos.users.get(user_id)
    now = int(time.time())
    if user_row and user_row["paid_until"] > now:
        paid_until = user_row["paid_until"] + settings.pro_days * 86400
    else:
        paid_until = now + settings.pro_days * 86400

    await repos.users.set_pro(user_id, paid_until)
    await repos.payments.add(
        user_id,
        payment.total_amount,
        payment.currency,
        payment.invoice_payload,
        payment.telegram_payment_charge_id,
    )

    till = datetime.fromtimestamp(paid_until).strftime("%d.%m.%Y")
    was_pro = is_pro(user_row)
    text = PAY_ALREADY_PRO.format(till=till) if was_pro else PAY_SUCCESS.format(
        till=till, limit=settings.pro_limit
    )
    await message.answer(text, reply_markup=reply.main_menu())
    logger.info(
        "User %s paid %s %s, pro until %s",
        user_id,
        payment.total_amount,
        payment.currency,
        till,
    )
