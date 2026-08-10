import asyncio
import logging

from aiogram import Bot, Dispatcher

import database as db
from config import BOT_TOKEN
from handlers import admin, payments, user
from middlewares.throttling import ThrottlingMiddleware
from resilience import ErrorGuardMiddleware, RetrySession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    await db.init_db()
    bot = Bot(token=BOT_TOKEN, session=RetrySession(timeout=60))
    dp = Dispatcher()
    dp.update.outer_middleware(ErrorGuardMiddleware())
    dp.message.middleware(ThrottlingMiddleware(limit=1.2))
    dp.include_routers(
        user.router,
        admin.router,
        payments.router,
    )
    bot_username = (await bot.get_me()).username
    if bot_username is None:
        raise RuntimeError("bot username is None")
    logger.info("🚀 Бот запущен...")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        handle_signals=False,
        polling_timeout=60,
        bot_username=bot_username,
    )
    if db._db_conn:
        await db._db_conn.close()
    logger.info("🛑 Бот успешно остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
