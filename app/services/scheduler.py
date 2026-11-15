import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from app.config import Settings
from app.database import Repositories
from app.services.wb_api import WBApiClient, WBApiError
from app.texts import ALERT_DROP, ALERT_TARGET

logger = logging.getLogger(__name__)

ALERT_BATCH_PAUSE = 0.05


class PriceScheduler:
    """Background loop that checks tracked prices and fires alerts."""

    def __init__(self, bot: Bot, repos: Repositories, settings: Settings) -> None:
        self._bot = bot
        self._repos = repos
        self._settings = settings
        self._wb = WBApiClient(settings.proxy_url)
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="price-scheduler")
        logger.info("Price scheduler started (interval=%ss)", self._settings.check_interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._wb.close()
        logger.info("Price scheduler stopped")

    async def check_all(self) -> int:
        """Run one full check cycle. Returns number of alerts sent."""
        nms = await self._repos.tracks.distinct_nms()
        if not nms:
            return 0

        alerts = 0
        for offset in range(0, len(nms), 100):
            batch = nms[offset : offset + 100]
            try:
                products = await self._wb.fetch_products(batch)
            except WBApiError:
                logger.error("Check cycle skipped batch of %s items (WB API down)", len(batch))
                continue
            for nm in batch:
                info = products.get(nm)
                if info is None:
                    continue
                alerts += await self._process_nm(nm, info)
                await asyncio.sleep(ALERT_BATCH_PAUSE)
        return alerts

    async def _process_nm(self, nm: int, info) -> int:
        watchers = await self._repos.tracks.watchers(nm)
        alerts = 0
        for row in watchers:
            old_price = row["last_price"]
            new_price = info.price

            if new_price is not None and new_price != old_price:
                await self._repos.tracks.update_price(row["user_id"], nm, new_price)

            if not row["alerts_enabled"]:
                continue
            if old_price is None or new_price is None or new_price >= old_price:
                continue

            triggered, text = self._build_alert(row, info, old_price, new_price)
            if not triggered:
                continue

            if await self._send_alert(row["user_id"], text):
                alerts += 1
        return alerts

    def _build_alert(self, row, info, old_price: int, new_price: int) -> tuple[bool, str]:
        target = row["target"] or 0
        url = f"https://www.wildberries.ru/catalog/{info.nm}/detail.aspx"
        name = info.name or f"Артикул {info.nm}"

        if target and new_price <= target:
            return True, ALERT_TARGET.format(
                name=name, nm=info.nm, target=target, new=new_price, url=url
            )

        drop_pct = row["drop_pct"] or self._settings.default_drop_pct
        drop = (old_price - new_price) / old_price * 100
        if drop >= drop_pct:
            return True, ALERT_DROP.format(
                name=name,
                nm=info.nm,
                old=old_price,
                new=new_price,
                pct=round(drop, 1),
                url=url,
            )
        return False, ""

    async def _send_alert(self, user_id: int, text: str) -> bool:
        try:
            await self._bot.send_message(user_id, text, disable_web_page_preview=True)
            return True
        except TelegramRetryAfter as exc:
            logger.warning("Rate limited on alert to %s, retry after %ss", user_id, exc.retry_after)
            await asyncio.sleep(exc.retry_after)
            return await self._send_alert(user_id, text)
        except TelegramAPIError as exc:
            logger.warning("Alert to %s failed: %s", user_id, exc)
            return False

    async def _loop(self) -> None:
        await asyncio.sleep(15)
        while True:
            started = time.monotonic()
            try:
                alerts = await self.check_all()
                logger.info(
                    "Check cycle done in %.1fs, alerts=%s", time.monotonic() - started, alerts
                )
            except Exception:
                logger.exception("Check cycle crashed, will retry next interval")
            await asyncio.sleep(self._settings.check_interval)
