import os
import re
import logging
import asyncio
import sqlite3
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

# --- НАСТРОЙКИ ---
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = "/webhook"
DB_PATH = "wb_bot.db"
FREE_LIMIT = 3
STARS_PRICE = 300

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, paid_until INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS tracks (user_id INTEGER, nm INTEGER, target INTEGER DEFAULT 0, last_price INTEGER, PRIMARY KEY (user_id, nm))")
    conn.commit()
    conn.close()

def db_all(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return rows

def db_run(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(sql, params)
    conn.commit()
    conn.close()

# --- ПАРСЕР WB ---
async def fetch_wb_prices(nms):
    if not nms: return {}
    import aiohttp
    url = f"https://card.wb.ru/cards/v4/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={';'.join(map(str, nms))}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            out = {}
            for p in data.get("products", []):
                for size in p.get("sizes", []):
                    price = (size.get("price") or {}).get("product")
                    if price:
                        out[p["id"]] = price // 100
                        break
            return out

# --- КЛАВИАТУРЫ ---
def reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Мои товары"), KeyboardButton(text="💎 Безлимит")],
            [KeyboardButton(text="🔍 Проверить цены"), KeyboardButton(text="❓ Инструкция")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Кинь ссылку на товар WB..."
    )

def item_menu(nm):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить товар", callback_data=f"del_{nm}")]
    ])

def buy_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐️ Оплатить {STARS_PRICE} Stars", callback_data="pay")]
    ])

# --- ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    welcome_text = (
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        "Я — <b>WB-Детектор</b>. Слежу за ценами на Wildberries.\n\n"
        "📌 <b>Что делать:</b>\n"
        "1. Кидай ссылку на товар (например: <code>https://www.wildberries.ru/catalog/14671602/detail.aspx</code>).\n"
        "2. Я проверяю цену каждый час.\n"
        "3. Если упадет на 5% или достигнет цели — пришлю уведомление.\n\n"
        f"🎁 <b>Бесплатно:</b> {FREE_LIMIT} товара.\n"
        "💎 <b>Безлимит:</b> 300 ⭐️ на 30 дней.\n\n"
        "👇 <b>Используй меню внизу, чтобы управлять ботом:</b>"
    )
    await message.answer(welcome_text, reply_markup=reply_menu())

# --- ОБРАБОТЧИКИ КНОПОК НИЖНЕГО МЕНЮ ---
@dp.message(F.text == "📋 Мои товары")
async def show_list(message: Message):
    rows = db_all("SELECT nm, target, last_price FROM tracks WHERE user_id = ?", (message.chat.id,))
    
    if not rows:
        await message.answer("📭 Пока ничего не отслеживается.\nКинь ссылку на товар!", reply_markup=reply_menu())
        return
    
    await message.answer("📋 <b>Твои товары:</b>")
    for nm, target, last_price in rows:
        price = f"{last_price} ₽" if last_price else "—"
        tgt = f" (цель: {target} ₽)" if target else ""
        text = f"🔹 <b>Артикул:</b> <code>{nm}</code>\n💰 <b>Цена:</b> {price}{tgt}\nhttps://www.wildberries.ru/catalog/{nm}/detail.aspx"
        await message.answer(text, reply_markup=item_menu(nm), disable_web_page_preview=True)

@dp.message(F.text == "💎 Безлимит")
async def show_buy(message: Message):
    await message.answer(
        f"💎 <b>Безлимит на 30 дней</b>\n\n"
        f"Снимает лимит в {FREE_LIMIT} товара.\n"
        f"Стоимость: {STARS_PRICE} ⭐️ (Telegram Stars).",
        reply_markup=buy_menu()
    )

@dp.message(F.text == "🔍 Проверить цены")
async def manual_check(message: Message):
    await message.answer("⏳ Проверяю цены для твоих товаров...")
    await check_prices(manual=True, user_id=message.chat.id)
    await message.answer("✅ Проверка завершена. Если цены изменились — я пришлю уведомление.", reply_markup=reply_menu())

@dp.message(F.text == "❓ Инструкция")
async def show_help(message: Message):
    text = (
        "❓ <b>Инструкция по использованию:</b>\n\n"
        "1. <b>Добавление:</b> Скопируй ссылку на товар с Wildberries и отправь её мне в чат.\n"
        "2. <b>Цель:</b> Чтобы задать цену, допиши её через пробел: <code>...detail.aspx 1500</code>\n"
        "3. <b>Проверка:</b> Я проверяю цены каждый час или по кнопке «Проверить цены».\n"
        "4. <b>Уведомления:</b> Пришлю сообщение, если цена упадёт на 5% или достигнет цели.\n"
    )
    await message.answer(text, reply_markup=reply_menu())

# --- ОБРАБОТЧИКИ CALLBACK (ИНЛАЙН КНОПОК) ---
@dp.callback_query(F.data.startswith("del_"))
async def cb_delete(callback: CallbackQuery):
    nm = int(callback.data.split("_")[1])
    db_run("DELETE FROM tracks WHERE user_id = ? AND nm = ?", (callback.from_user.id, nm))
    await callback.message.edit_text(f"🗑 Товар <code>{nm}</code> удален.")
    await callback.answer("Удалено!")

@dp.callback_query(F.data == "pay")
async def cb_pay(callback: CallbackQuery):
    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title="Безлимит WB-Детектор (30 дней)",
        description="Неограниченное количество товаров и приоритетная проверка цен.",
        payload="unlimited_30d",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="30 дней", amount=STARS_PRICE)]
    )
    await callback.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    now = int(asyncio.get_event_loop().time())
    db_run("INSERT OR REPLACE INTO users (id, paid_until) VALUES (?, ?)", (message.chat.id, now + 30 * 86400))
    await message.answer("✅ <b>Оплата прошла!</b>\nБезлимит активирован на 30 дней. Спасибо!", reply_markup=reply_menu())

# --- ОБРАБОТКА ССЫЛОК ---
@dp.message(F.text)
async def handle_text(message: Message):
    text = message.text.strip()
    if text in ["📋 Мои товары", "💎 Безлимит", "🔍 Проверить цены", "❓ Инструкция"]:
        return

    match = re.search(r"catalog/(\d+)/detail", text)
    if not match:
        await message.answer("🤔 Не вижу ссылку на товар. Кинь ссылку с WB или используй меню.", reply_markup=reply_menu())
        return
    
    nm = int(match.group(1))
    user = db_all("SELECT paid_until FROM users WHERE id = ?", (message.chat.id,))
    paid_until = user[0][0] if user else 0
    
    if paid_until < asyncio.get_event_loop().time():
        count = db_all("SELECT COUNT(*) FROM tracks WHERE user_id = ?", (message.chat.id,))[0][0]
        if count >= FREE_LIMIT:
            await message.answer(f"🚫 Бесплатный лимит ({FREE_LIMIT} шт.) исчерпан.\nКупи безлимит в меню ниже.", reply_markup=reply_menu())
            return
    
    target = 0
    t_match = re.search(r"\s(\d{3,7})\s*$", text)
    if t_match:
        target = int(t_match.group(1))
    
    prices = await fetch_wb_prices([nm])
    price = prices.get(nm)
    
    db_run("INSERT OR REPLACE INTO tracks (user_id, nm, target, last_price) VALUES (?, ?, ?, ?)", (message.chat.id, nm, target, price))
    db_run("INSERT OR IGNORE INTO users (id) VALUES (?)", (message.chat.id,))
    
    if price is None:
        await message.answer(f"✅ Товар <code>{nm}</code> добавлен.\n⚠️ Сейчас его нет в наличии, сообщу, когда появится.", reply_markup=reply_menu())
    else:
        msg = f"✅ Товар <code>{nm}</code> добавлен.\n💰 Текущая цена: <b>{price} ₽</b>\n"
        msg += f"🎯 Алерт при цене <= {target} ₽" if target else "🎯 Алерт при падении на 5%+"
        await message.answer(msg, reply_markup=reply_menu())

# --- ФОНОВАЯ ПРОВЕРКА ЦЕН ---
async def check_prices(manual=False, user_id=None):
    logging.info("Запуск проверки цен...")
    if manual and user_id:
        rows = db_all("SELECT user_id, nm, target, last_price FROM tracks WHERE user_id = ?", (user_id,))
    else:
        rows = db_all("SELECT user_id, nm, target, last_price FROM tracks")
    
    if not rows: return
    
    by_nm = {}
    for uid, nm, target, last_price in rows:
        if nm not in by_nm: by_nm[nm] = []
        by_nm[nm].append((uid, target, last_price))
    
    nms = list(by_nm.keys())
    for i in range(0, len(nms), 50):
        chunk = nms[i:i+50]
        prices = await fetch_wb_prices(chunk)
        
        for nm in chunk:
            if nm not in prices: continue
            new_price = prices[nm]
            
            for uid, target, old_price in by_nm[nm]:
                hit = False
                if old_price and new_price < old_price:
                    if target and new_price <= target:
                        hit = True
                    elif not target and (old_price - new_price) >= old_price * 0.05:
                        hit = True
                
                if hit:
                    url = f"https://www.wildberries.ru/catalog/{nm}/detail.aspx"
                    await bot.send_message(uid, f"📉 <b>Цена упала!</b>\nБыло: {old_price} ₽ → Стало: {new_price} ₽\n{url}", disable_web_page_preview=True)
                
                if new_price != old_price:
                    db_run("UPDATE tracks SET last_price = ? WHERE user_id = ? AND nm = ?", (new_price, uid, nm))

async def periodic_check():
    while True:
        await asyncio.sleep(3600)
        await check_prices()

# --- ЗАПУСК ---
async def on_startup(app):
    init_db()
    await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}")
    logging.info(f"Webhook set to {WEBHOOK_URL}{WEBHOOK_PATH}")
    asyncio.create_task(periodic_check())

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
