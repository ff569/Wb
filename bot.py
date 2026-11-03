import os
import re
import logging
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL") # Render сам подставит ссылку
WEBHOOK_PATH = "/webhook"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я слежу за ценами на Wildberries.\n\n"
        "Просто пришли ссылку на товар, например:\n"
        "https://www.wildberries.ru/catalog/14671602/detail.aspx\n\n"
        "Я запомню его и буду проверять цену."
    )

@dp.message()
async def handle_message(message: Message):
    text = message.text or ""
    match = re.search(r"catalog/(\d+)/detail", text)
    
    if match:
        nm = match.group(1)
        await message.answer(f"Товар с артикулом <b>{nm}</b> добавлен в отслеживание!")
    else:
        await message.answer("Пришли ссылку на товар Wildberries или напиши /start.")

async def on_startup(app):
    # Привязываем вебхук при запуске
    await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}")
    logging.info(f"Webhook set to {WEBHOOK_URL}{WEBHOOK_PATH}")

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    # Запускаем веб-сервер на порту, который даст Render
    port = int(os.environ.get("PORT", 8080))
    app.on_startup.append(on_startup)
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
