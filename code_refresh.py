import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

REFRESH_POLL_SECONDS = 600


async def refresh_codes_once(db: Any, now: int | None = None) -> int:
    current = int(time.time()) if now is None else now
    refreshed = await db.refresh_due_codes(current)
    return len(refreshed)


async def run_code_refresh_loop(db: Any, poll: float = REFRESH_POLL_SECONDS) -> None:
    while True:
        try:
            await refresh_codes_once(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("code refresh iteration failed")
        await asyncio.sleep(poll)
