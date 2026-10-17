from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from config import ALLOWED_CHAT_ID


class AllowedChatMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if ALLOWED_CHAT_ID is None:
            return await handler(event, data)

        if (
            isinstance(event, Message)
            and event.chat.type != "private"
            and event.chat.id != ALLOWED_CHAT_ID
        ):
            return None

        return await handler(event, data)
