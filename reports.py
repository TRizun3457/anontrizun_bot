import html
import math
import time
from collections.abc import Callable

MAX_REPORT_LENGTH = 3000
REPORT_COOLDOWN_SECONDS = 60


class ReportLimiter:
    def __init__(
        self,
        cooldown: float = REPORT_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cooldown = cooldown
        self._clock = clock
        self._last: dict[int, float] = {}

    def remaining(self, user_id: int) -> int:
        last = self._last.get(user_id)
        if last is None:
            return 0
        left = self.cooldown - (self._clock() - last)
        return math.ceil(left) if left > 0 else 0

    def mark(self, user_id: int) -> None:
        now = self._clock()
        self._last[user_id] = now
        if len(self._last) > 5000:
            cutoff = now - self.cooldown
            self._last = {k: v for k, v in self._last.items() if v > cutoff}


def format_report_header(user_id: int, full_name: str, username: str | None) -> str:
    name = html.escape(full_name.strip() or "Без имени")
    handle = f"@{html.escape(username)}" if username else "нет username"
    return (
        "🛠 <b>Сообщение о проблеме</b>\n"
        "─────────────────────\n"
        f'👤 Пользователь: <a href="tg://user?id={user_id}">{name}</a>\n'
        f"🔗 Username: {handle}\n"
        f"🆔 ID: <code>{user_id}</code>"
    )


def is_too_long(text: str | None) -> bool:
    return text is not None and len(text) > MAX_REPORT_LENGTH


CANCEL_WORDS = frozenset({"cancel", "отмена", "отменить"})


def is_cancel_text(text: str | None) -> bool:
    word = (text or "").strip().lstrip("/").lower().split("@")[0]
    return word in CANCEL_WORDS
