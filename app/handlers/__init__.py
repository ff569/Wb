from aiogram import Router

from app.handlers import admin, common, monitoring, settings, subscription


def setup_routers() -> Router:
    router = Router()
    router.include_routers(
        common.router,
        admin.router,
        subscription.router,
        settings.router,
        monitoring.router,
    )
    return router
