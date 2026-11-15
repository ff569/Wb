import asyncio
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database import Repositories
from app.handlers.helpers import monitoring_text, user_limit
from app.keyboards import inline, reply
from app.services.wb_api import WBApiClient, WBApiError
from app.texts import (
    ADD_PRODUCT,
    err_limit_reached,
    CHECK_DONE,
    CHECK_STARTED,
    DELETE_CONFIRM,
    ERR_ADD_FAILED,
    ERR_NOT_A_LINK,
    ERR_PRODUCT_NOT_FOUND,
    ERR_WB_UNAVAILABLE,
    GENERIC_ERROR,
    MY_PRODUCTS_EMPTY,
    MY_PRODUCTS_HEADER,
    PRODUCT_ADDED,
    PRODUCT_ADDED_NO_PRICE,
    PRODUCT_CARD,
    PRODUCT_DELETED,
    PRODUCT_UPDATED,
    TARGET_LINE,
    TARGET_LINE_NONE,
)
from app.utils import product_url, split_link_and_target

logger = logging.getLogger(__name__)
router = Router()

_wb_clients: dict[str, WBApiClient] = {}


def get_wb_client(settings: Settings) -> WBApiClient:
    proxy = settings.proxy_url or ""
    if proxy not in _wb_clients:
        _wb_clients[proxy] = WBApiClient(settings.proxy_url)
    return _wb_clients[proxy]


def price_str(price: int | None) -> str:
    return f"{price} \u20bd" if price is not None else "\u2014 (нет в наличии)"


def target_line(target: int) -> str:
    if target:
        return TARGET_LINE.format(target=target)
    return TARGET_LINE_NONE


@router.callback_query(F.data == inline.CALLBACK_MONITORING)
async def cb_monitoring(
    callback: CallbackQuery, repos: Repositories, settings: Settings, user_row
) -> None:
    count = await repos.tracks.count_for_user(callback.from_user.id)
    limit = user_limit(settings, user_row)
    await callback.message.edit_text(
        monitoring_text(count, limit, settings), reply_markup=inline.monitoring()
    )
    await callback.answer()


@router.callback_query(F.data == inline.CALLBACK_ADD_PRODUCT)
async def cb_add_product(callback: CallbackQuery) -> None:
    await callback.message.edit_text(ADD_PRODUCT, reply_markup=inline.back_to_monitoring())
    await callback.answer()


@router.callback_query(F.data == inline.CALLBACK_MY_PRODUCTS)
async def cb_my_products(
    callback: CallbackQuery, repos: Repositories, settings: Settings, user_row
) -> None:
    rows = await repos.tracks.list_for_user(callback.from_user.id)
    if not rows:
        await callback.message.edit_text(MY_PRODUCTS_EMPTY, reply_markup=inline.back_to_monitoring())
        await callback.answer()
        return

    limit = user_limit(settings, user_row)
    lines = [MY_PRODUCTS_HEADER.format(count=len(rows), limit=limit), ""]
    for row in rows:
        lines.append(
            PRODUCT_CARD.format(
                name=row["name"] or f"Артикул {row['nm']}",
                nm=row["nm"],
                price=price_str(row["last_price"]),
                target_line=target_line(row["target"]),
                url=product_url(row["nm"]),
            )
        )
    text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=inline.back_to_monitoring())
    for row in rows:
        try:
            await callback.message.answer(
                f"\U0001f539 <b>{row['name'] or 'Артикул ' + str(row['nm'])}</b>\n"
                f"\U0001f4b0 {price_str(row['last_price'])}",
                reply_markup=inline.product_actions(row["nm"]),
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception("Failed to render product card nm=%s", row["nm"])
    await callback.answer()


@router.callback_query(F.data.startswith(inline.CALLBACK_DELETE + ":"))
async def cb_delete_ask(callback: CallbackQuery, repos: Repositories) -> None:
    nm = int(callback.data.split(":", 1)[1])
    row = await repos.tracks.get(callback.from_user.id, nm)
    if row is None:
        await callback.answer("Товар уже удалён", show_alert=True)
        return
    name = row["name"] or f"Артикул {nm}"
    await callback.message.edit_text(
        DELETE_CONFIRM.format(name=name, nm=nm), reply_markup=inline.delete_confirm(nm)
    )
    await callback.answer()


@router.callback_query(F.data.startswith(inline.CALLBACK_DELETE_CONFIRM + ":"))
async def cb_delete_confirm(callback: CallbackQuery, repos: Repositories) -> None:
    nm = int(callback.data.split(":", 1)[1])
    deleted = await repos.tracks.delete(callback.from_user.id, nm)
    if deleted:
        await callback.message.edit_text(PRODUCT_DELETED.format(name=f"Артикул {nm}", nm=nm))
        await callback.answer("Удалено")
    else:
        await callback.answer("Товар не найден", show_alert=True)


@router.callback_query(F.data == inline.CALLBACK_CHECK_NOW)
async def cb_check_now(
    callback: CallbackQuery, repos: Repositories, scheduler, settings: Settings
) -> None:
    count = await repos.tracks.count_for_user(callback.from_user.id)
    if count == 0:
        await callback.answer("Сначала добавь товары", show_alert=True)
        return
    await callback.message.answer(CHECK_STARTED)
    await callback.answer()
    try:
        alerts = await asyncio.wait_for(scheduler.check_all(), timeout=110)
        await callback.message.answer(CHECK_DONE.format(alerts=alerts))
    except Exception:
        logger.exception("Manual check failed")
        await callback.message.answer(GENERIC_ERROR.format(support=settings.support_url))


@router.message(F.text)
async def handle_product_link(
    message: Message, repos: Repositories, settings: Settings, user_row
) -> None:
    text = message.text.strip()
    if text in reply.ALL_BUTTONS:
        return

    article, target = split_link_and_target(text)
    if article is None:
        await message.answer(ERR_NOT_A_LINK)
        return

    count = await repos.tracks.count_for_user(message.from_user.id)
    limit = user_limit(settings, user_row)
    if count >= limit:
        await message.answer(err_limit_reached(settings, count))
        return

    try:
        info = await get_wb_client(settings).get_price(article)
    except WBApiError:
        logger.error("WB API unavailable while adding nm=%s", article)
        await repos.tracks.add(message.from_user.id, article, "", target, None)
        await message.answer(ERR_WB_UNAVAILABLE)
        return
    except Exception:
        logger.exception("Unexpected error while adding nm=%s", article)
        await message.answer(ERR_ADD_FAILED.format(support=settings.support_url))
        return

    if info is None:
        await message.answer(ERR_PRODUCT_NOT_FOUND.format(nm=article))
        return

    existing = await repos.tracks.get(message.from_user.id, article)
    await repos.tracks.add(
        message.from_user.id, article, info.name, target or existing_target(existing), info.price
    )

    name = info.name or f"Артикул {article}"
    final_target = target or existing_target(existing)
    if existing is not None and target == 0:
        await message.answer(
            PRODUCT_UPDATED.format(
                name=name, nm=article, price=price_str(info.price), target_line=target_line(final_target)
            )
        )
    elif info.price is None:
        await message.answer(PRODUCT_ADDED_NO_PRICE.format(name=name, nm=article))
    else:
        await message.answer(
            PRODUCT_ADDED.format(
                name=name,
                nm=article,
                price=info.price,
                target_line=target_line(final_target),
            )
        )
    logger.info(
        "User %s tracked nm=%s target=%s price=%s", message.from_user.id, article, final_target, info.price
    )


def existing_target(existing) -> int:
    if existing is None:
        return 0
    return existing["target"] or 0
