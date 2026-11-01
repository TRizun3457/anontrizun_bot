import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, override

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, TelegramObject

from media_groups import GroupGate


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(
        self,
        command_limit: float = 0.3,
        text_limit: float = 1.0,
        heavy_limit: float = 2.5,
        notify_cooldown: float = 3.0,
        cleanup_interval: int = 300,
    ) -> None:
        self.command_limit = command_limit
        self.text_limit = text_limit
        self.heavy_limit = heavy_limit
        self.notify_cooldown = notify_cooldown
        self.cleanup_interval = cleanup_interval

        self._user_timeouts: dict[int, float] = {}
        self._user_notify_timeouts: dict[int, float] = {}
        self._album_gate = GroupGate()
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self, *args: Any, **kwargs: Any) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self, *args: Any, **kwargs: Any) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.cleanup_interval)
            current_time = time.monotonic()
            max_limit = max(
                self.command_limit,
                self.text_limit,
                self.heavy_limit,
                self.notify_cooldown,
            )

            expired_users = [
                uid
                for uid, last_time in self._user_timeouts.items()
                if current_time - last_time > max_limit
            ]
            for uid in expired_users:
                self._user_timeouts.pop(uid, None)
                self._user_notify_timeouts.pop(uid, None)

    def _get_rate_limit(self, event: Message) -> float:
        if event.entities:
            for entity in event.entities:
                if entity.type == "bot_command":
                    return self.command_limit

        if event.photo or event.video or event.document or event.voice or event.audio:
            return self.heavy_limit

        return self.text_limit

    @staticmethod
    def _is_command_for_bot(event: Message, bot_username: str | None) -> bool:
        text = event.text or event.caption or ""
        for entity in event.entities or event.caption_entities or []:
            if entity.type != "bot_command" or entity.offset != 0:
                continue
            command = text[entity.offset : entity.offset + entity.length]
            _, _, target = command.partition("@")
            if not target:
                return True
            return bot_username is not None and target.lower() == bot_username.lower()
        return False

    @override
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)

        in_group = event.chat.type != "private"
        if in_group:
            bot = data.get("bot")
            bot_username = (await bot.me()).username if isinstance(bot, Bot) else None
            if not self._is_command_for_bot(event, bot_username):
                return await handler(event, data)

        user_id = event.from_user.id
        group_id = event.media_group_id
        if group_id is not None and self._album_gate.known(user_id, group_id):
            return await handler(event, data)

        current_time = time.monotonic()
        required_limit = self._get_rate_limit(event)

        last_msg_time = self._user_timeouts.get(user_id, 0.0)
        if current_time - last_msg_time < required_limit:
            last_notify_time = self._user_notify_timeouts.get(user_id, 0.0)
            if not in_group and current_time - last_notify_time >= self.notify_cooldown:
                self._user_notify_timeouts[user_id] = current_time
                try:
                    await event.answer(
                        "⏳ Не так быстро! Запросы отправляются слишком часто."
                    )
                except TelegramAPIError:
                    pass
            return None

        self._user_timeouts[user_id] = current_time
        if group_id is not None:
            self._album_gate.first(user_id, group_id)
        return await handler(event, data)
