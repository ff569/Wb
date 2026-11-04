import os
import re
import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, LabeledPrice, PreCheckoutQuery,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- ENV ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = "/webhook"
DB_PATH = "wb_bot.db"

# --- Тарифы ---
FREE_LIMIT = 3
PRO_LIMIT = 50
BUSINESS_LIMIT = 500
PRO_PRICE_RUB = 2990
PRO_PRICE_STARS = 300
TRIAL_DAYS = 7
DROP_ALERT_PCT = 5

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ═══════════════════════════════════════════════════════════
# БАЗА ДАННЫХ
# ═══════════════════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            tariff TEXT DEFAULT 'trial',
            paid_until INTEGER DEFAULT 0,
            trial_until INTEGER DEFAULT 0,
            referrer_id INTEGER,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            user_id INTEGER,
            nm INTEGER,
            target INTEGER DEFAULT 0,
            last_price INTEGER,
            added_at INTEGER DEFAULT (strftime('%s','now')),
            PRIMARY KEY (user_id, nm)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            currency TEXT,
            payload TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        )
    """)
    conn.commit()
    conn.close()

def db_all(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return rows

def db_one(sql, params=()):
    rows = db_all(sql, params)
    return rows[0] if rows else None

def db_run(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(sql, params)
    conn.commit()
    conn.close()

# ═══════════════════════════════════════════════════════════
# WB API
# ═══════════════════════════════════════════════════════════

async def fetch_wb_prices(nms):
    if not nms:
        return {}
    import aiohttp
    url = f"https://card.wb.ru/cards/v4/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={';'.join(map(str, nms))}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                data = await resp.json()
                out = {}
                for p in data.get("products", []):
                    for size in p.get("sizes", []):
                        price = (size.get("price") or {}).get("product")
                        if price:
                            out[p["id"]] = price // 100
                            break
                return out
    except Exception as e:
        logging.error(f"WB API error: {e}")
        return {}

# ═══════════════════════════════════════════════════════════
# ТАРИФЫ И ЛИМИТЫ
# ═══════════════════════════════════════════════════════════

def get_user(user_id):
    return db_one("SELECT id, tariff, paid_until, trial_until FROM users WHERE id = ?", (user_id,))

def get_limit(user_id):
    u = get_user(user_id)
    if not u:
        return FREE_LIMIT
    now = int(datetime.now().timestamp())
    if u[1] == 'business' and u[2] > now:
        return BUSINESS_LIMIT
    if u[1] == 'pro' and u[2] > now:
        return PRO_LIMIT
    if u[3] > now:
        return PRO_LIMIT  # trial = Pro-функции
    return FREE_LIMIT

def is_paid(user_id):
    u = get_user(user_id)
    if not u:
        return False
    now = int(datetime.now().timestamp())
    return u[2] > now or u[3] > now

# ═══════════════════════════════════════════════════════════
# КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════════

def main_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Мониторинг"), KeyboardButton(text="💎 Подписка")],
            [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="⚙️ Настройки")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Кинь ссылку на товар WB..."
    )

def monitoring_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="add_product")],
        [InlineKeyboardButton(text="📋 Мои товары", callback_data="my_products")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])

def subscription_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐️ Оплатить {PRO_PRICE_STARS} Stars", callback_data="pay_stars")],
        [InlineKeyboardButton(text="🎁 Активировать промокод", callback_data="promo")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])

def back_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])

def item_menu(nm):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_{nm}")]
    ])

# ═══════════════════════════════════════════════════════════
# ХЕНДЛЕРЫ
# ═══════════════════════════════════════════════════════════

@dp.message(Command("start"))
async def cmd_start(message: Message):
    uid = message.from_user.id
    name = message.from_user.first_name or "друг"

    # Регистрация
    if not get_user(uid):
        trial_until = int((datetime.now() + timedelta(days=TRIAL_DAYS)).timestamp())
        db_run(
            "INSERT INTO users (id, username, first_name, tariff, trial_until) VALUES (?, ?, ?, 'trial', ?)",
            (uid, message.from_user.username, name, trial_until)
        )
        logging.info(f"New user: {uid} @{message.from_user.username}")

    text = (
        f"👋 <b>Привет, {name}!</b>\n\n"
        "Я — <b>WB Детектор</b>, твой личный аналитик Wildberries.\n\n"
        "Что я умею:\n"
        "📊 Слежу за ценами 24/7\n"
        "🔔 Присылаю алерты при падении цен\n"
        "🕵️ Показываю, кто демпингует\n\n"
        f"🎁 Твой триал: <b>{TRIAL_DAYS} дней Pro-функций бесплатно</b>.\n"
        "После — 2990₽/мес или 300⭐️.\n\n"
        "👇 Нажми кнопку внизу, чтобы начать."
    )
    await message.answer(text, reply_markup=main_reply_menu())

# --- Кнопки нижнего меню ---
@dp.message(F.text == "📊 Мониторинг")
async def show_monitoring(message: Message):
    uid = message.from_user.id
    count = db_one("SELECT COUNT(*) FROM tracks WHERE user_id = ?", (uid,))[0]
    limit = get_limit(uid)
    text = (
        f"📊 <b>Мониторинг цен</b>\n\n"
        f"Всего товаров: {count} / {limit}\n"
    )
    await message.answer(text, reply_markup=monitoring_menu())

@dp.message(F.text == "💎 Подписка")
async def show_subscription(message: Message):
    uid = message.from_user.id
    u = get_user(uid)
    now = int(datetime.now().timestamp())
    if u[2] > now:
        till = datetime.fromtimestamp(u[2]).strftime("%d.%m.%Y")
        status = f"💎 Pro (до {till})"
    elif u[3] > now:
        till = datetime.fromtimestamp(u[3]).strftime("%d.%m.%Y")
        status = f"🎁 Триал (до {till})"
    else:
        status = "🆓 Free"
    text = (
        f"💎 <b>Подписка</b>\n\n"
        f"Текущий статус: {status}\n\n"
        f"<b>Тарифы:</b>\n"
        f"🆓 Free — 3 товара, проверка раз в день\n"
        f"⭐️ Pro — 2990₽/мес, 50 товаров, проверка раз в час\n\n"
        f"Оплати Stars или активируй промокод:"
    )
    await message.answer(text, reply_markup=subscription_menu())

@dp.message(F.text == "❓ Помощь")
async def show_help(message: Message):
    text = (
        "❓ <b>Помощь</b>\n\n"
        "1. Открой «Мониторинг» → «Добавить товар».\n"
        "2. Отправь ссылку на товар с Wildberries.\n"
        "3. Можно добавить цель: <code>...detail.aspx 1500</code>.\n"
        "4. Я проверяю цену каждый час.\n"
        "5. При падении на 5% — пришлю алерт.\n\n"
        "💬 Поддержка: @wb_detector_support"
    )
    await message.answer(text, reply_markup=back_menu())

@dp.message(F.text == "⚙️ Настройки")
async def show_settings(message: Message):
    await message.answer(
        "⚙️ <b>Настройки</b>\n\n"
        "Скоро появятся: часовой пояс, настройка алертов, реферальная программа.",
        reply_markup=back_menu()
    )

# --- Inline-кнопки ---
@dp.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery):
    await callback.message.edit_text("🏠 Главное меню", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мониторинг", callback_data="monitoring_menu")]
    ]))
    await callback.answer()

@dp.callback_query(F.data == "monitoring_menu")
async def cb_monitoring(callback: CallbackQuery):
    await callback.message.edit_text("📊 Мониторинг", reply_markup=monitoring_menu())
    await callback.answer()

@dp.callback_query(F.data == "add_product")
async def cb_add_product(callback: CallbackQuery):
    await callback.message.edit_text(
        "➕ <b>Добавление товара</b>\n\n"
        "Отправь ссылку на карточку Wildberries:\n"
        "<code>https://www.wildberries.ru/catalog/14671602/detail.aspx</code>\n\n"
        "Можно указать цель через пробел:\n"
        "<code>...detail.aspx 1500</code>",
        reply_markup=back_menu()
    )
    await callback.answer()

@dp.callback_query(F.data == "my_products")
async def cb_my_products(callback: CallbackQuery):
    uid = callback.from_user.id
    rows = db_all("SELECT nm, target, last_price FROM tracks WHERE user_id = ?", (uid,))
    if not rows:
        await callback.message.edit_text("📭 Пока ничего не отслеживается.", reply_markup=back_menu())
        await callback.answer()
        return
    await callback.message.edit_text("📋 <b>Твои товары:</b>", reply_markup=back_menu())
    for nm, target, price in rows:
        p = f"{price} ₽" if price else "—"
        t = f" (цель: {target} ₽)" if target else ""
        await callback.message.answer(
            f"🔹 <code>{nm}</code>\n💰 {p}{t}\nhttps://www.wildberries.ru/catalog/{nm}/detail.aspx",
            reply_markup=item_menu(nm),
            disable_web_page_preview=True
        )
    await callback.answer()

@dp.callback_query(F.data.startswith("del_"))
async def cb_delete(callback: CallbackQuery):
    nm = int(callback.data.split("_")[1])
    db_run("DELETE FROM tracks WHERE user_id = ? AND nm = ?", (callback.from_user.id, nm))
    await callback.message.edit_text(f"🗑 Товар <code>{nm}</code> удалён.")
    await callback.answer("Удалено")

@dp.callback_query(F.data == "pay_stars")
async def cb_pay_stars(callback: CallbackQuery):
    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title="WB Детектор Pro (30 дней)",
        description="50 товаров, проверка раз в час, алерты",
        payload="pro_30d",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Pro 30 дней", amount=PRO_PRICE_STARS)]
    )
    await callback.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message(F.successful_payment)
async def process_payment(message: Message):
    uid = message.chat.id
    until = int((datetime.now() + timedelta(days=30)).timestamp())
    db_run("UPDATE users SET tariff='pro', paid_until=? WHERE id=?", (until, uid))
    db_run("INSERT INTO payments (user_id, amount, currency, payload) VALUES (?, ?, ?, ?)",
           (uid, PRO_PRICE_STARS, "XTR", "pro_30d"))
    till = datetime.fromtimestamp(until).strftime("%d.%m.%Y")
    await message.answer(
        f"✅ <b>Оплата прошла!</b>\n\n"
        f"Твой Pro активирован до {till}.\n"
        f"Теперь можешь добавить до {PRO_LIMIT} товаров.",
        reply_markup=main_reply_menu()
    )

# --- Обработка ссылок ---
@dp.message(F.text)
async def handle_text(message: Message):
    text = message.text.strip()
    if text in ["📊 Мониторинг", "💎 Подписка", "❓ Помощь", "⚙️ Настройки"]:
        return

    match = re.search(r"catalog/(\d+)/detail", text)
    if not match:
        await message.answer("🤔 Не вижу ссылку на товар. Кинь ссылку с WB или используй меню.")
        return

    nm = int(match.group(1))
    uid = message.chat.id
    count = db_one("SELECT COUNT(*) FROM tracks WHERE user_id = ?", (uid,))[0]
    limit = get_limit(uid)

    if count >= limit:
        await message.answer(
            f"🚫 <b>Лимит исчерпан</b>\n\n"
            f"На твоём тарифе доступно {limit} товаров.\n"
            f"У тебя уже {count}.\n\n"
            f"💎 Оформи Pro в разделе «Подписка».",
            reply_markup=main_reply_menu()
        )
        return

    target = 0
    t_match = re.search(r"\s(\d{3,7})\s*$", text)
    if t_match:
        target = int(t_match.group(1))

    prices = await fetch_wb_prices([nm])
    price = prices.get(nm)

    db_run("INSERT OR REPLACE INTO tracks (user_id, nm, target, last_price) VALUES (?, ?, ?, ?)",
           (uid, nm, target, price))

    if price is None:
        await message.answer(f"✅ Товар <code>{nm}</code> добавлен.\n⚠️ Нет в наличии, сообщу когда появится.")
    else:
        msg = f"✅ Товар <code>{nm}</code> добавлен.\n💰 Цена: <b>{price} ₽</b>\n"
        msg += f"🎯 Алерт при <= {target} ₽" if target else f"🎯 Алерт при падении на {DROP_ALERT_PCT}%+"
        await message.answer(msg)

# ═══════════════════════════════════════════════════════════
# МОНИТОРИНГ (APScheduler через asyncio)
# ═══════════════════════════════════════════════════════════

async def check_prices():
    logging.info("🔄 Запуск проверки цен")
    rows = db_all("SELECT user_id, nm, target, last_price FROM tracks")
    if not rows:
        return

    by_nm = {}
    for uid, nm, target, last_price in rows:
        by_nm.setdefault(nm, []).append((uid, target, last_price))

    nms = list(by_nm.keys())
    for i in range(0, len(nms), 50):
        chunk = nms[i:i+50]
        prices = await fetch_wb_prices(chunk)
        for nm in chunk:
            if nm not in prices:
                continue
            new_price = prices[nm]
            for uid, target, old_price in by_nm[nm]:
                if not old_price:
                    db_run("UPDATE tracks SET last_price=? WHERE user_id=? AND nm=?",
                           (new_price, uid, nm))
                    continue
                hit = False
                if new_price < old_price:
                    if target and new_price <= target:
                        hit = True
                    elif not target and (old_price - new_price) >= old_price * DROP_ALERT_PCT / 100:
                        hit = True
                if hit:
                    url = f"https://www.wildberries.ru/catalog/{nm}/detail.aspx"
                    try:
                        await bot.send_message(
                            uid,
                            f"📉 <b>Цена упала!</b>\n\n"
                            f"Артикул: <code>{nm}</code>\n"
                            f"Было: {old_price} ₽\n"
                            f"Стало: <b>{new_price} ₽</b>\n\n"
                            f"🔗 {url}",
                            disable_web_page_preview=True
                        )
                    except Exception as e:
                        logging.error(f"Alert to {uid} failed: {e}")
                if new_price != old_price:
                    db_run("UPDATE tracks SET last_price=? WHERE user_id=? AND nm=?",
                           (new_price, uid, nm))

async def scheduler_loop():
    await asyncio.sleep(10)
    while True:
        try:
            await check_prices()
        except Exception as e:
            logging.exception(f"Scheduler error: {e}")
        await asyncio.sleep(3600)  # раз в час

# ═══════════════════════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════════════════════

async def on_startup(app):
    init_db()
    if WEBHOOK_URL:
        await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}")
        logging.info(f"Webhook set: {WEBHOOK_URL}{WEBHOOK_PATH}")
    asyncio.create_task(scheduler_loop())

async def health(request):
    return web.Response(text="OK")

def main():
    app = web.Application()
    app.router.add_get("/health", health)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)

    port = int(os.environ.get("PORT", 8080))
    logging.info(f"Starting on 0.0.0.0:{port}")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
