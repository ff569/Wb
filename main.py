import asyncio
import logging
import sys

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from app.config import load_settings
from app.database import build_repositories
from app.database.db import Database
from app.handlers import setup_routers
from app.middlewares import AntiFloodMiddleware, RegistrationMiddleware
from app.services.scheduler import PriceScheduler

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def health(_request: web.Request) -> web.Response:
    return web.Response(text="OK")


# ИСПРАВЛЕНИЕ 1: Добавили аргумент dp в функцию on_startup
async def on_startup(webhook_url: str, webhook_path: str, secret: str, bot: Bot, dp: Dispatcher) -> None:
    if webhook_url:
        await bot.set_webhook(
            f"{webhook_url}{webhook_path}",
            secret_token=secret or None,
            # ИСПРАВЛЕНИЕ 2: Теперь dp доступен, и ошибка missing 'self' исчезнет
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
        logger.info("Webhook set: %s%s", webhook_url, webhook_path)
    else:
        logger.info("RENDER_EXTERNAL_URL is empty, running in polling mode")


async def run_webhook(bot: Bot, dp: Dispatcher, settings) -> None:
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook_secret or None,
    )
    handler.register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)

    # ИСПРАВЛЕНИЕ 3: Передаем dp в on_startup при вызове
    await on_startup(settings.webhook_url, settings.webhook_path, settings.webhook_secret, bot, dp)

    logger.info("HTTP server listening on 0.0.0.0:%s", settings.port)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=settings.port)
    await site.start()
    await asyncio.Event().wait()


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Starting long polling")
    await dp.start_polling(bot)


async def main() -> None:
    setup_logging()
    settings = load_settings()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    db = Database(settings.db_path)
    await db.connect()
    repos = build_repositories(db)

    dp.include_router(setup_routers())
    dp.message.middleware(RegistrationMiddleware(repos))
    dp.callback_query.middleware(RegistrationMiddleware(repos))
    dp.message.middleware(AntiFloodMiddleware())
    dp.callback_query.middleware(AntiFloodMiddleware())

    scheduler = PriceScheduler(bot, repos, settings)
    dp["settings"] = settings
    dp["repos"] = repos
    dp["scheduler"] = scheduler
    scheduler.start()

    try:
        if settings.webhook_url:
            await run_webhook(bot, dp, settings)
        else:
            await run_polling(bot, dp)
    finally:
        await scheduler.stop()
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
