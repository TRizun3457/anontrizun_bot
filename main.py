import asyncio
import logging

from aiogram import Bot, Dispatcher

import database as db
from config import BOT_TOKEN, DB_NAME
from handlers import admin, payments, user
from middlewares.chat_check import AllowedChatMiddleware
from middlewares.throttling import ThrottlingMiddleware
from resilience import ErrorGuardMiddleware, RetrySession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    await db.init_db(DB_NAME)

    bot = Bot(token=BOT_TOKEN, session=RetrySession(timeout=60))
    dp = Dispatcher()

    throttling_middleware = ThrottlingMiddleware(
        command_limit=0.3,
        text_limit=1.2,
        heavy_limit=2.5,
    )

    dp.startup.register(throttling_middleware.start)
    dp.shutdown.register(throttling_middleware.stop)

    dp.update.outer_middleware(ErrorGuardMiddleware())
    dp.message.middleware(AllowedChatMiddleware())
    dp.message.middleware(throttling_middleware)

    dp.include_routers(
        payments.router,
        admin.router,
        user.router,
    )

    bot_info = await bot.get_me()
    if bot_info.username is None:
        raise RuntimeError("bot username is None")

    logger.info("🚀 Бот запущен...")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            handle_signals=False,
            polling_timeout=60,
        )
    finally:
        await bot.session.close()
        if hasattr(db, "close_db"):
            await db.close_db()
        logger.info("🛑 Бот успешно остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
