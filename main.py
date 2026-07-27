import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

import database as db
from config import BOT_TOKEN
from handlers import admin, payments, user
from middlewares.throttling import ThrottlingMiddleware

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


async def main() -> None:
    await db.init_db()

    session = AiohttpSession(timeout=60)
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher()

    dp.message.middleware(ThrottlingMiddleware(limit=1.2))

    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(payments.router)

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
