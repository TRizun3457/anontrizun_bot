"""Rotten Potato orchestration: picks victims, notifies them, resolves expiry.

The Telegram bot is used through a tiny duck-typed surface (``send_message``,
``send_chat_action``, ``get_chat_member``) so the logic is testable without
aiogram. Identities of holders are never revealed in any message.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any, Protocol

from .achievements import POTATO_ACHIEVEMENTS
from .store import ExplodeResult, Game, PassResult, PotatoError, PotatoStore

logger = logging.getLogger(__name__)

MAX_DELIVERY_ATTEMPTS = 40
EXPIRY_POLL_SECONDS = 15


class BotLike(Protocol):
    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> Any: ...
    async def send_chat_action(
        self, chat_id: int, action: str, **kwargs: Any
    ) -> Any: ...
    async def get_chat_member(
        self, chat_id: int, user_id: int, **kwargs: Any
    ) -> Any: ...


def fmt_duration(seconds: int) -> str:
    minutes = max(1, round(seconds / 60))
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} ч. {mins} мин."
    if hours:
        return f"{hours} ч."
    return f"{mins} мин."


def fmt_achievements(ids: list[str]) -> str:
    return "\n".join(
        f"🏅 <b>{POTATO_ACHIEVEMENTS[a][0]}</b> — {POTATO_ACHIEVEMENTS[a][1]}"
        for a in ids
        if a in POTATO_ACHIEVEMENTS
    )


class PotatoService:
    def __init__(
        self,
        store: PotatoStore,
        bot: BotLike,
        admin_id: int,
        pass_markup: Callable[[int], Any] | None = None,
    ) -> None:
        self.store = store
        self.bot = bot
        self.admin_id = admin_id
        self._pass_markup = pass_markup or (lambda _game_id: None)

    # ---- delivery -----------------------------------------------------
    async def _reachable(self, user_id: int, group_chat_id: int | None) -> bool:
        try:
            await self.bot.send_chat_action(user_id, "typing")
        except Exception:  # noqa: BLE001 - any delivery failure means unreachable
            return False
        if group_chat_id is not None and group_chat_id < 0:
            try:
                member = await self.bot.get_chat_member(group_chat_id, user_id)
            except Exception:  # noqa: BLE001
                return False
            if getattr(member, "status", None) in ("left", "kicked"):
                return False
        return True

    async def _pick_reachable(self, game: Game, exclude: set[int]) -> int | None:
        cands = await self.store.candidates(game.id, exclude, self.admin_id)
        group = game.chat_id if game.chat_id != game.starter_id else None
        for uid in cands[:MAX_DELIVERY_ATTEMPTS]:
            if await self._reachable(uid, group):
                return uid
        return None

    async def _say(self, chat_id: int, text: str, markup: Any = None) -> bool:
        try:
            await self.bot.send_message(
                chat_id, text, reply_markup=markup, parse_mode="HTML"
            )
            return True
        except Exception:
            logger.warning(
                "potato: cannot deliver message to %s", chat_id, exc_info=True
            )
            return False

    async def _notify_holder(self, game: Game) -> None:
        assert game.holder_id is not None
        text = (
            "🥔🔥 <b>Вы — Гнилая картошка!</b>\n\n"
            f"У вас есть <b>{fmt_duration(game.duration_sec)}</b>, чтобы анонимно "
            "передать её другому пользователю бота. Иначе она взорвётся! 💥"
        )
        await self._say(game.holder_id, text, self._pass_markup(game.id))

    async def _announce_achievements(self, user_id: int, ids: list[str]) -> None:
        if ids:
            await self._say(
                user_id, "🏆 <b>Новое достижение игры!</b>\n" + fmt_achievements(ids)
            )

    # ---- lifecycle ----------------------------------------------------
    async def start_game(
        self, chat_id: int, starter_id: int, duration_sec: int
    ) -> Game:
        game = await self.store.create_game(chat_id, starter_id, duration_sec)
        try:
            victim = await self._pick_reachable(game, set())
            if victim is None:
                raise PotatoError("Некому передавать картошку: нет доступных игроков.")
            assigned = await self.store.assign_holder(game.id, victim)
            game = assigned.game
        except BaseException:
            await self.store.cancel_game(game.id)
            raise
        await self._notify_holder(game)
        await self._announce_achievements(victim, assigned.new_achievements)
        await self._say(
            chat_id,
            "🥔 <b>Гнилая картошка запущена!</b>\n"
            f"Случайный пользователь бота уже получил её анонимно. "
            f"Время на передачу: {fmt_duration(game.duration_sec)}.",
        )
        return game

    async def pass_potato(self, game_id: int, user_id: int) -> PassResult:
        game = await self.store.get_game(game_id)
        if game is None or game.status != "active":
            raise PotatoError("Эта картошка уже не активна.")
        if game.holder_id != user_id:
            raise PotatoError("Картошка сейчас не у вас.")
        target = await self._pick_reachable(game, {user_id})
        result = await self.store.pass_potato(game_id, user_id, target)
        if target is None:
            await self._say(
                user_id,
                "✅ Вы передали картошку — других игроков не осталось, игра окончена.",
            )
            await self._say(
                game.chat_id, "🥔 Картошку обезвредили: передавать её больше некому. 🎉"
            )
        else:
            await self._notify_holder(result.game)
            await self._announce_achievements(target, result.receiver_achievements)
        await self._announce_achievements(user_id, result.new_achievements)
        return result

    async def resolve_expired(self) -> list[ExplodeResult]:
        results: list[ExplodeResult] = []
        for game in await self.store.active_games():
            try:
                res = await self.store.explode_if_expired(game.id)
            except Exception:
                logger.exception("potato: expiry check failed for game %s", game.id)
                continue
            if res is None:
                continue
            results.append(res)
            await self._say(
                res.victim,
                "💥 <b>БАБАХ!</b> Картошка взорвалась у вас в руках — вы не успели её передать.",
            )
            await self._announce_achievements(res.victim, res.new_achievements)
            await self._say(
                game.chat_id,
                f"💥 <b>Гнилая картошка взорвалась!</b>\nУспешных передач: {res.game.pass_count}.",
            )
        return results

    async def run_expiry_loop(self, poll: float = EXPIRY_POLL_SECONDS) -> None:
        while True:
            try:
                await self.resolve_expired()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("potato: expiry loop iteration failed")
            await asyncio.sleep(poll)
