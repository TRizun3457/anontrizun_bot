import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher

import database as db
from code_refresh import run_code_refresh_loop
from config import ADMIN_ID, ALLOWED_CHAT_ID, BOT_TOKEN, DB_NAME, POTATO_UTC_OFFSET
from handlers import admin, payments, user
from handlers.user.potato import pass_markup
from middlewares.chat_check import AllowedChatMiddleware
from middlewares.throttling import ThrottlingMiddleware
from potato.service import PotatoService
from potato.store import PotatoStore
from resilience import ErrorGuardMiddleware, RetrySession
from schema_repair import repair_legacy_schema

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    repair_legacy_schema(DB_NAME)
    await db.init_db(DB_NAME)

    bot = Bot(token=BOT_TOKEN, session=RetrySession(timeout=60))
    dp = Dispatcher()

    potato_store = PotatoStore(DB_NAME)
    await potato_store.init(apply_migrations=False)
    potato_service = PotatoService(
        potato_store,
        bot,
        admin_id=ADMIN_ID,
        pass_markup=pass_markup,
        auto_chat_id=ALLOWED_CHAT_ID,
        utc_offset=POTATO_UTC_OFFSET,
    )
    dp["potato_service"] = potato_service
    potato_tasks = [
        asyncio.create_task(potato_service.run_expiry_loop(), name="potato-expiry"),
        asyncio.create_task(
            potato_service.run_scheduler_loop(), name="potato-scheduler"
        ),
        asyncio.create_task(run_code_refresh_loop(db), name="code-refresh"),
    ]

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
        for task in potato_tasks:
            task.cancel()
        for task in potato_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await potato_store.close()
        await bot.session.close()
        await db.close_db()
        logger.info("🛑 Бот успешно остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
