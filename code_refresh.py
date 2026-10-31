import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

REFRESH_POLL_SECONDS = 600


async def refresh_codes_once(db: Any, bot: Any, now: int | None = None) -> int:
    current = int(time.time()) if now is None else now
    refreshed = await db.refresh_due_codes(current)
    for user_id, code in refreshed:
        try:
            await bot.send_message(
                user_id,
                f"🔑 Ваш анонимный код обновлён автоматически: <code>{code}</code>",
                parse_mode="HTML",
            )
        except Exception:
            logger.warning("code refresh: cannot notify %s", user_id, exc_info=True)
    return len(refreshed)


async def run_code_refresh_loop(
    db: Any, bot: Any, poll: float = REFRESH_POLL_SECONDS
) -> None:
    while True:
        try:
            await refresh_codes_once(db, bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("code refresh iteration failed")
        await asyncio.sleep(poll)
