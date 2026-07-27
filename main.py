import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError

import database as db
from config import BOT_TOKEN
from handlers import admin, payments, user
from middlewares.throttling import ThrottlingMiddleware

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    await db.init_db()

    session = AiohttpSession(timeout=60)
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher()

    _ = dp.message.middleware(ThrottlingMiddleware(limit=1.2))

    dp.include_routers(
        user.router,
        admin.router,
        payments.router,
    )

    print("🚀 Бот успешно запущен в модульном режиме...")

    try:
        while True:
            try:
                await dp.start_polling(  # pyright: ignore[reportUnknownMemberType]
                    bot,
                    allowed_updates=dp.resolve_used_update_types(),
                    handle_signals=False,
                )
            except TelegramNetworkError as e:
                logging.error(f"Сетевая ошибка: {e}. Повторное подключение через 5 секунд...")
                await asyncio.sleep(5)
            except Exception as e:
                logging.critical(f"Критическая ошибка: {e}")
                break
    finally:
        await bot.session.close()
        if db.db_pool:
            await db.db_pool.close()
        print("\n🛑 Бот успешно остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
