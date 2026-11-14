import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from app.database import Repositories

logger = logging.getLogger(__name__)


class RegistrationMiddleware(BaseMiddleware):
    """Ensures every user exists in the DB and injects repositories."""

    def __init__(self, repos: Repositories) -> None:
        self._repos = repos

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is not None and not user.is_bot:
            await self._repos.users.upsert(
                user.id,
                user.username,
                user.first_name,
            )
            row = await self._repos.users.get(user.id)
            data["repos"] = self._repos
            data["user_row"] = row
        return await handler(event, data)
