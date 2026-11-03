import os
import logging
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import asyncio

# Настройка логов
logging.basicConfig(level=logging.INFO)

# Получаем токен из переменных окружения Render
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Инициализация бота
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я слежу за ценами на Wildberries.\n\n"
        "Просто пришли ссылку на товар, например:\n"
        "https://www.wildberries.ru/catalog/14671602/detail.aspx\n\n"
        "Я запомню его и буду проверять цену."
    )

# Обработчик ссылок
@dp.message()
async def handle_message(message: Message):
    text = message.text or ""
    # Ищем ссылку на WB
    match = re.search(r"catalog/(\d+)/detail", text)
    
    if match:
        nm = match.group(1)
        await message.answer(f"Товар с артикулом <b>{nm}</b> добавлен в отслеживание!\n(Пока я просто запомнил его, проверка цен будет дальше).")
    else:
        await message.answer("Пришли ссылку на товар Wildberries или напиши /start.")

# Запуск
async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
