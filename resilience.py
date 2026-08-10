import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramServerError
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import TelegramObject, Update

logger = logging.getLogger(__name__)

RETRYABLE = (TelegramNetworkError, TelegramServerError, asyncio.TimeoutError)


class RetrySession(AiohttpSession):
    """Повторяет запрос к Telegram API при сбое сети. Без прокси."""

    def __init__(self, retries: int = 3, delay: float = 1.0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.retries = retries
        self.delay = delay

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
        **kwargs: Any,
    ) -> TelegramType:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                return await super().make_request(
                    bot, method, timeout=timeout, **kwargs
                )
            except RETRYABLE as error:
                last_error = error
                logger.warning(
                    "Сбой сети при запросе %s (попытка %s/%s): %s",
                    method,
                    attempt + 1,
                    self.retries,
                    error,
                )
                await asyncio.sleep(self.delay * (attempt + 1))
        if last_error is not None:
            raise last_error
        raise RuntimeError("RetrySession: нет попыток запроса")


class ErrorGuardMiddleware(BaseMiddleware):
    """Если обработчик упал — пользователь всё равно получает ответ."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            logger.exception(
                "Обработчик упал на update %s", getattr(event, "update_id", "?")
            )
            message = None
            if isinstance(event, Update):
                message = event.message
                if message is None and event.callback_query is not None:
                    message = event.callback_query.message
            if message is None:
                return None
            bot: Bot = data["bot"]
            for attempt in range(3):
                try:
                    await bot.send_message(
                        chat_id=message.chat.id,
                        text="⚠️ <b>Временные неполадки.</b> Попробуйте ещё раз.",
                        parse_mode=ParseMode.HTML,
                    )
                    break
                except RETRYABLE:
                    await asyncio.sleep(1.0 * (attempt + 1))
                except Exception:
                    logger.exception("Не удалось отправить заглушку об ошибке")
                    break
            return None
