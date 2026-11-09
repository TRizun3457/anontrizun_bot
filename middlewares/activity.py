from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from potato.service import PotatoService


class ActivityMiddleware(BaseMiddleware):
    def __init__(self, service: PotatoService) -> None:
        self.service = service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None and not getattr(user, "is_bot", False):
            await self.service.note_activity(user.id)
        return await handler(event, data)
