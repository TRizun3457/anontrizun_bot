import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import override

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    rate_limit: float
    user_timeouts: dict[int, float]
    cleanup_interval: int

    def __init__(self, limit: float = 1.2, cleanup_interval: int = 300) -> None:
        """
        :param limit: Минимальный интервал между сообщениями (в секундах).
        :param cleanup_interval: Интервал очистки неактивных пользователей (в секундах).
        """
        self.rate_limit = limit
        self.user_timeouts = {}
        self.cleanup_interval = cleanup_interval

        _ = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """Фоновый цикл для удаления устаревших записей из памяти."""
        while True:
            await asyncio.sleep(self.cleanup_interval)
            current_time = time.time()

            expired_users = [
                user_id
                for user_id, last_time in self.user_timeouts.items()
                if current_time - last_time > self.rate_limit
            ]

            for user_id in expired_users:
                del self.user_timeouts[user_id]

    @override
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, object]], Awaitable[object]],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object:
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)

        user_id = event.from_user.id
        current_time = time.time()

        if user_id in self.user_timeouts:
            delta = current_time - self.user_timeouts[user_id]
            if delta < self.rate_limit:
                return None

        self.user_timeouts[user_id] = current_time
        return await handler(event, data)
