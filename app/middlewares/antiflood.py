import logging
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.texts import FLOOD_WARNING

logger = logging.getLogger(__name__)


class AntiFloodMiddleware(BaseMiddleware):
    """Sliding-window rate limiter per user."""

    def __init__(self, max_events: int = 20, window_seconds: int = 60) -> None:
        self._max_events = max_events
        self._window = window_seconds
        self._history: dict[int, deque[float]] = defaultdict(deque)
        self._warned: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.is_bot:
            return await handler(event, data)

        now = time.monotonic()
        bucket = self._history[user.id]
        while bucket and now - bucket[0] > self._window:
            bucket.popleft()

        if len(bucket) >= self._max_events:
            if now - self._warned.get(user.id, 0) > self._window:
                self._warned[user.id] = now
                logger.info("Flood protection triggered for user %s", user.id)
                if isinstance(event, CallbackQuery):
                    await event.answer("Слишком быстро! Подожди минуту.", show_alert=True)
                elif isinstance(event, Message):
                    await event.answer(FLOOD_WARNING)
            return None

        bucket.append(now)
        return await handler(event, data)
