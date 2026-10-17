import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramServerError
from aiogram.methods import CopyMessage, SendMessage, TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import Message, TelegramObject, Update

logger = logging.getLogger(__name__)

RETRYABLE = (TelegramNetworkError, TelegramServerError, asyncio.TimeoutError)
NON_RETRYABLE_METHODS = (SendMessage, CopyMessage)


class RetrySession(AiohttpSession):
    def __init__(
        self,
        retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.retries = retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
        **kwargs: Any,
    ) -> TelegramType:
        if isinstance(method, NON_RETRYABLE_METHODS) or getattr(
            method, "__api_method__", ""
        ) in {"refundStarPayment", "refund_star_payment"}:
            return await super().make_request(bot, method, timeout=timeout, **kwargs)

        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                return await super().make_request(
                    bot, method, timeout=timeout, **kwargs
                )
            except RETRYABLE as error:
                last_error = error
                if attempt == self.retries - 1:
                    break

                delay = min(self.max_delay, self.base_delay * (2**attempt))
                jitter = random.uniform(0, 0.1 * delay)
                total_delay = delay + jitter

                logger.warning(
                    "Сбой сети при запросе %s (попытка %s/%s): %s. Повтор через %.2f сек",
                    method.__class__.__name__,
                    attempt + 1,
                    self.retries,
                    error,
                    total_delay,
                )
                await asyncio.sleep(total_delay)

        if last_error is not None:
            raise last_error
        raise RuntimeError("RetrySession: нет попыток запроса")


def is_addressed_to_bot(message: Message) -> bool:
    if message.chat.type == "private":
        return True
    return any(entity.type == "bot_command" for entity in message.entities or [])


class ErrorGuardMiddleware(BaseMiddleware):
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

            bot: Bot | None = data.get("bot")
            if not bot or not isinstance(event, Update):
                return None

            try:
                if event.inline_query is not None:
                    await bot.answer_inline_query(
                        inline_query_id=event.inline_query.id,
                        results=[],
                        cache_time=1,
                        is_personal=True,
                    )
                elif event.callback_query is not None:
                    await bot.answer_callback_query(
                        callback_query_id=event.callback_query.id,
                        text="⚠️ Временная ошибка. Попробуйте еще раз.",
                        show_alert=True,
                    )
                elif event.message is not None and is_addressed_to_bot(event.message):
                    await bot.send_message(
                        chat_id=event.message.chat.id,
                        text="⚠️ <b>Временные неполадки.</b> Попробуйте ещё раз.",
                        parse_mode=ParseMode.HTML,
                    )
            except Exception:
                logger.exception("Не удалось отправить заглушку об ошибке")

            return None
