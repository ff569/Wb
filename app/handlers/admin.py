import logging
import time
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import Settings
from app.database import Repositories
from app.texts import ADMIN_ONLY, ADMIN_STATS

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("stats"))
async def cmd_stats(message: Message, repos: Repositories, settings: Settings) -> None:
    if message.from_user.id not in settings.admin_ids:
        await message.answer(ADMIN_ONLY)
        return

    now = int(time.time())
    day_ago = now - 86400
    users = await repos.users.count_all()
    new_today = await repos.users.count_new_since(day_ago)
    pro = await repos.users.count_active_pro(now)
    tracks = await repos.tracks.count_all()
    revenue = await repos.payments.total_revenue()
    revenue_today = await repos.payments.revenue_since(day_ago)
    payments = await repos.payments.count_all()

    await message.answer(
        ADMIN_STATS.format(
            users=users,
            new_today=new_today,
            pro=pro,
            tracks=tracks,
            revenue=revenue,
            revenue_today=revenue_today,
            payments=payments,
            now=datetime.now().strftime("%d.%m.%Y %H:%M"),
        )
    )
    logger.info("Admin %s requested stats", message.from_user.id)
