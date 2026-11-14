import time

from app.config import Settings
from app.database import Repositories
from app.texts import MONITORING


def user_limit(settings: Settings, user_row) -> int:
    if user_row is not None and user_row["paid_until"] > int(time.time()):
        return settings.pro_limit
    return settings.free_limit


def is_pro(user_row) -> bool:
    return user_row is not None and user_row["paid_until"] > int(time.time())


def monitoring_text(count: int, limit: int, settings: Settings) -> str:
    return MONITORING.format(
        count=count,
        limit=limit,
        example_url="https://www.wildberries.ru/catalog/14671602/detail.aspx",
    )
