import asyncio
import datetime
import logging
import random
from collections.abc import Callable
from typing import Any, Protocol

from .achievements import POTATO_ACHIEVEMENTS
from .store import (
    ROT_DURATION,
    ROT_SPAWNS,
    ExplodeResult,
    Game,
    PassResult,
    PotatoError,
    PotatoStore,
    random_duration,
)

logger = logging.getLogger(__name__)

MAX_DELIVERY_ATTEMPTS = 40
EXPIRY_POLL_SECONDS = 15
SCHEDULER_POLL_SECONDS = 30
GROUP_COOLDOWN_SECONDS = 4 * 60 * 60
AUTO_MIN_SECONDS = 4 * 60 * 60
AUTO_MAX_SECONDS = 12 * 60 * 60
AUTO_RETRY_SECONDS = 60 * 60
ROT_DAY_PROBABILITY = 0.1
ROT_MAX_LATENESS = 2 * 60 * 60
ACTIVE_FROM_HOUR = 10
ACTIVE_TO_HOUR = 21


class BotLike(Protocol):
    async def send_message(self, *args: Any, **kwargs: Any) -> Any: ...
    async def send_chat_action(self, *args: Any, **kwargs: Any) -> Any: ...
    async def get_chat_member(self, *args: Any, **kwargs: Any) -> Any: ...


ROT_ANNOUNCE = (
    "🤢 <b>ДЕНЬ ГНИЕНИЯ!</b>\n"
    "Сегодня по боту гуляют сразу несколько гнилых картошек. Таймер у каждой — 1 час, "
    "передавать их можно бесконечно, но кому-то всё равно не повезёт."
)


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
        *,
        auto_chat_id: int | None = None,
        utc_offset: int = 0,
        rng: random.Random | None = None,
    ) -> None:
        self.auto_chat_id = auto_chat_id if auto_chat_id is not None else admin_id
        self.utc_offset = utc_offset
        self._rng = rng or random.Random()
        self.store = store
        self.bot = bot
        self.admin_id = admin_id
        self._pass_markup = pass_markup or (lambda _game_id: None)

    async def _reachable(self, user_id: int, group_chat_id: int | None) -> bool:
        try:
            await self.bot.send_chat_action(user_id, "typing")
        except Exception:
            return False
        if group_chat_id is not None and group_chat_id < 0:
            try:
                member = await self.bot.get_chat_member(group_chat_id, user_id)
            except Exception:
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
        if game.kind == "rot":
            text = (
                "🤢🥔 <b>День гниения! Вы — Гнилая картошка!</b>\n\n"
                f"У вас всего <b>{fmt_duration(game.duration_sec)}</b>, чтобы анонимно "
                "перекинуть её другому пользователю бота. Сегодня картошек несколько, "
                "и кто-то обязательно загниёт! 💥"
            )
        else:
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

    async def start_game(
        self,
        chat_id: int,
        starter_id: int,
        duration_sec: int,
        *,
        kind: str = "normal",
        cooldown_sec: int = 0,
        mark_cooldown: bool = False,
        announce: bool = True,
    ) -> Game:
        if cooldown_sec > 0:
            left = await self.store.cooldown_remaining(chat_id, cooldown_sec)
            if left > 0:
                raise PotatoError(
                    f"Следующую картошку в этом чате можно запустить через {fmt_duration(left)}."
                )
        game = await self.store.create_game(chat_id, starter_id, duration_sec, kind)
        try:
            victim = await self._pick_reachable(game, set())
            if victim is None:
                raise PotatoError("Некому передавать картошку: нет доступных игроков.")
            assigned = await self.store.assign_holder(game.id, victim)
            game = assigned.game
        except BaseException:
            await self.store.cancel_game(game.id)
            raise
        if mark_cooldown:
            await self.store.mark_started(chat_id)
        await self._notify_holder(game)
        await self._announce_achievements(victim, assigned.new_achievements)
        if announce and kind == "normal":
            await self._say(
                chat_id,
                "🥔 <b>Гнилая картошка запущена!</b>\n"
                "Случайный пользователь бота уже получил её анонимно. "
                f"Время на передачу: {fmt_duration(game.duration_sec)}.",
            )
        return game

    async def start_rot_day(self, chat_id: int, starter_id: int) -> list[Game]:
        games: list[Game] = []
        for _ in range(ROT_SPAWNS):
            games.append(
                await self.start_game(
                    chat_id, starter_id, ROT_DURATION, kind="rot", announce=False
                )
            )
        await self._say(chat_id, ROT_ANNOUNCE)
        return games

    def _local(self, ts: int) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(
            ts, tz=datetime.timezone(datetime.timedelta(hours=self.utc_offset))
        )

    def _in_active_hours(self, ts: int) -> bool:
        return ACTIVE_FROM_HOUR <= self._local(ts).hour < ACTIVE_TO_HOUR

    async def tick(self) -> None:
        now = self.store.now()
        local = self._local(now)
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = int(midnight.timestamp()) + ACTIVE_FROM_HOUR * 3600
        window_end = int(midnight.timestamp()) + ACTIVE_TO_HOUR * 3600
        await self.store.plan_rot_day(
            midnight.date().isoformat(), window_start, window_end, ROT_DAY_PROBABILITY
        )

        first_in_batch = True
        for day, spawn_at, is_first in await self.store.due_rot_spawns(
            ROT_MAX_LATENESS
        ):
            try:
                await self.start_game(
                    self.auto_chat_id,
                    0,
                    ROT_DURATION,
                    kind="rot",
                    announce=False,
                )
                if is_first and first_in_batch:
                    await self._say(self.auto_chat_id, ROT_ANNOUNCE)
                first_in_batch = False
            except PotatoError:
                logger.info("potato: rot spawn skipped, no available players")
            except Exception:
                logger.exception("potato: rot spawn failed")
            await self.store.mark_spawn_launched(day, spawn_at)

        next_at = await self.store.get_auto("auto")
        if next_at is None:
            await self.store.set_auto(
                "auto",
                now + self._rng.randint(AUTO_MIN_SECONDS, AUTO_MAX_SECONDS),
            )
            return
        if now < next_at or not self._in_active_hours(now):
            return
        retry = now + AUTO_RETRY_SECONDS
        if await self.store.active_game(self.auto_chat_id) is not None:
            await self.store.set_auto("auto", retry)
            return
        try:
            await self.start_game(
                self.auto_chat_id,
                0,
                random_duration(self._rng),
                mark_cooldown=True,
            )
        except PotatoError:
            await self.store.set_auto("auto", retry)
            return
        await self.store.set_auto(
            "auto", now + self._rng.randint(AUTO_MIN_SECONDS, AUTO_MAX_SECONDS)
        )

    async def run_scheduler_loop(self, poll: float = SCHEDULER_POLL_SECONDS) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("potato: scheduler iteration failed")
            await asyncio.sleep(poll)

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
            title = (
                "🤢💥 <b>Одна из гнилых картошек дня гниения взорвалась!</b>"
                if game.kind == "rot"
                else "💥 <b>Гнилая картошка взорвалась!</b>"
            )
            await self._say(
                game.chat_id,
                f"{title}\nУспешных передач: {res.game.pass_count}.",
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
