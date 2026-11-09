import asyncio
import datetime
import html
import logging
import random
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Protocol

from .achievements import POTATO_ACHIEVEMENTS
from .store import (
    Assignment,
    ExplodeResult,
    Game,
    PassResult,
    PotatoError,
    PotatoStore,
    random_duration,
    random_rot_duration,
    roll_spawn_count,
)
from .theme import (
    LAUNCH_AUTO,
    LAUNCH_MEMBER,
    LAUNCH_PAID,
    fmt_duration,
    holder_text,
    launch_text,
    poison_text,
)

logger = logging.getLogger(__name__)

MAX_DELIVERY_ATTEMPTS = 40
CHAT_LEVEL_ERRORS = (
    "chat not found",
    "member list is inaccessible",
    "not a member",
    "bot was kicked",
    "bot is not a member",
)
EXPIRY_POLL_SECONDS = 15
SCHEDULER_POLL_SECONDS = 30
GROUP_COOLDOWN_SECONDS = 2 * 60 * 60
AUTO_MIN_SECONDS = 10 * 60 * 60
AUTO_MAX_SECONDS = 30 * 60 * 60
AUTO_RETRY_SECONDS = 60 * 60
ROT_DAY_PROBABILITY = 0.1
STRONG_ROT_PRICE = 142
LAUNCH_PRICE = 30
STRONG_ROT_SECONDS = 7 * 60 * 60
STRONG_ROT_CHANCE = 6.7 / 4267
STRONG_ROLL_SECONDS = 10 * 60
STRONG_ANNOUNCE = (
    "🌋 <b>СИЛЬНОЕ ГНИЕНИЕ!</b>\n"
    "Ближайшие 7 часов гнилые картошки могут внезапно появляться у случайных "
    "пользователей бота. На передачу — совсем немного времени, как в день гниения. Берегитесь! 🥔💀"
)
ROT_MAX_LATENESS = 2 * 60 * 60
SPAWN_LOG_EVERY = 20
ACTIVE_FROM_HOUR = 10
ACTIVE_TO_HOUR = 21
ROT_ANNOUNCE_FROM_HOUR = 7
ROT_ANNOUNCE_TO_HOUR = 10.5
MSK_OFFSET_HOURS = 3


class BotLike(Protocol):
    async def send_message(self, *args: Any, **kwargs: Any) -> Any: ...
    async def send_chat_action(self, *args: Any, **kwargs: Any) -> Any: ...
    async def get_chat_member(self, *args: Any, **kwargs: Any) -> Any: ...


ROT_ANNOUNCE = (
    "🤢 <b>ДЕНЬ ГНИЕНИЯ!</b>\n"
    "Сегодня по боту гуляют гнилые картошки, и сколько их будет — заранее не знает "
    "никто. У каждой свой короткий таймер, передавать их можно бесконечно, "
    "но кому-то всё равно не повезёт."
)


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
        self.strong_chance = STRONG_ROT_CHANCE
        self._unverifiable_chats: set[int] = set()
        self._undeliverable_logged: set[int] = set()
        self._spawn_attempts: dict[tuple[str, int], int] = {}
        self._announced: set[tuple[int, str]] = set()
        self._flagged: set[int] | None = None
        self._pass_markup = pass_markup or (lambda _game_id: None)

    async def _reachable(self, user_id: int, group_chat_id: int | None) -> bool:
        try:
            await self.bot.send_chat_action(user_id, "typing")
        except Exception:
            return False
        if (
            group_chat_id is None
            or group_chat_id >= 0
            or group_chat_id in self._unverifiable_chats
        ):
            return True
        try:
            member = await self.bot.get_chat_member(group_chat_id, user_id)
        except Exception as exc:
            text = str(exc).lower()
            if any(marker in text for marker in CHAT_LEVEL_ERRORS):
                self._unverifiable_chats.add(group_chat_id)
                logger.warning(
                    "potato: бот не видит чат %s (%s). Проверьте ALLOWED_CHAT_ID и что "
                    "бот добавлен в чат (лучше администратором). Проверка участия "
                    "отключена, играют все пользователи бота.",
                    group_chat_id,
                    exc,
                )
                return True
            logger.warning(
                "potato: cannot verify membership for user %s in chat %s",
                user_id,
                group_chat_id,
                exc_info=True,
            )
            return False
        return getattr(member, "status", None) not in ("left", "kicked")

    async def _pick_reachable(self, game: Game, exclude: set[int]) -> int | None:
        cands = await self.store.candidates(game.id, exclude)
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
        except Exception as exc:
            if any(marker in str(exc).lower() for marker in CHAT_LEVEL_ERRORS):
                if chat_id not in self._undeliverable_logged:
                    self._undeliverable_logged.add(chat_id)
                    logger.warning(
                        "potato: не удаётся отправить сообщение в %s (%s)", chat_id, exc
                    )
            else:
                logger.warning(
                    "potato: cannot deliver message to %s", chat_id, exc_info=True
                )
            return False

    async def _notify_holder(self, game: Game) -> bool:
        assert game.holder_id is not None
        deadline = (
            self._local(game.expires_at).strftime("%H:%M")
            if game.expires_at is not None
            else None
        )
        text = holder_text(
            game.kind,
            fmt_duration(game.duration_sec),
            deadline,
            await self.store.is_vip(game.holder_id),
            self._rng,
        )
        return await self._say(game.holder_id, text, self._pass_markup(game.id))

    async def _assign_and_notify(
        self, game: Game, exclude: set[int]
    ) -> Assignment | None:
        group = game.chat_id if game.chat_id != game.starter_id else None
        candidates = await self.store.candidates(game.id, exclude)
        for user_id in candidates[:MAX_DELIVERY_ATTEMPTS]:
            if user_id in exclude or not await self._reachable(user_id, group):
                continue
            try:
                assignment = await self.store.assign_holder(game.id, user_id)
            except PotatoError as exc:
                if str(exc) != "Пользователь больше не может участвовать в игре.":
                    raise
                logger.info(
                    "potato: candidate %s became ineligible for game %s",
                    user_id,
                    game.id,
                )
                exclude.add(user_id)
                continue
            if await self._notify_holder(assignment.game):
                return assignment

            logger.warning(
                "potato: holder notification failed for user %s in game %s; retrying",
                user_id,
                game.id,
            )
            await self.store.rollback_undelivered_holder(
                game.id, user_id, assignment.new_achievements
            )
            exclude.add(user_id)
        return None

    async def _announce_achievements(self, user_id: int, ids: list[str]) -> None:
        fresh = [a for a in dict.fromkeys(ids) if (user_id, a) not in self._announced]
        if not fresh:
            return
        self._announced.update((user_id, a) for a in fresh)
        if not await self._say(
            user_id, "🏆 <b>Новое достижение игры!</b>\n" + fmt_achievements(fresh)
        ):
            self._announced.difference_update((user_id, a) for a in fresh)

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
        starter_name: str | None = None,
    ) -> Game:
        if cooldown_sec > 0:
            left = await self.store.cooldown_remaining(chat_id, cooldown_sec)
            if left > 0:
                raise PotatoError(
                    f"Следующую картошку в этом чате можно запустить через {fmt_duration(left)}."
                )
        game = await self.store.create_game(chat_id, starter_id, duration_sec, kind)
        try:
            assigned = await self._assign_and_notify(game, set())
            if assigned is None:
                await self.store.cancel_game(game.id)
                raise PotatoError(
                    "Некому передавать картошку: не удалось найти доступного игрока."
                )
            game = assigned.game
        except BaseException:
            await self.store.cancel_game(game.id)
            raise
        if mark_cooldown:
            await self.store.mark_started(chat_id)
        assert game.holder_id is not None
        await self._announce_achievements(game.holder_id, assigned.new_achievements)
        if starter_id > 0:
            await self._announce_achievements(
                starter_id, await self.store.record_start(starter_id)
            )
        if announce and kind == "normal":
            source = LAUNCH_MEMBER if starter_id > 0 else LAUNCH_AUTO
            await self._say(
                chat_id,
                launch_text(
                    source,
                    fmt_duration(game.duration_sec),
                    html.escape(starter_name) if starter_name else None,
                ),
            )
        return game

    async def strong_rot_remaining(self) -> int:
        until = await self.store.get_auto("strong_until")
        if until is None:
            return 0
        return max(0, until - self.store.now())

    async def activate_strong_rot(self, buyer_id: int | None = None) -> int:
        now = self.store.now()
        current = await self.store.get_auto("strong_until") or 0
        until = max(current, now) + STRONG_ROT_SECONDS
        await self.store.set_auto("strong_until", until)
        if buyer_id is not None:
            await self.store.lock_until(buyer_id, until)
        await self._say(self.auto_chat_id, STRONG_ANNOUNCE)
        return until

    async def launch_paid(self, buyer_id: int) -> Game:
        game = await self.start_game(
            self.auto_chat_id,
            buyer_id,
            random_rot_duration(self._rng),
            kind="rot",
            announce=False,
        )
        await self._say(
            self.auto_chat_id, launch_text(LAUNCH_PAID, fmt_duration(game.duration_sec))
        )
        return game

    async def record_purchase(self, user_id: int, item: str, stars: int) -> None:
        await self._announce_achievements(
            user_id, await self.store.record_purchase(user_id, item, stars)
        )

    async def _spawn_rot_for(self, user_id: int) -> bool:
        game = await self.store.create_game(
            self.auto_chat_id, 0, random_rot_duration(self._rng), "rot"
        )
        group = self.auto_chat_id if self.auto_chat_id < 0 else None
        try:
            if not await self._reachable(user_id, group):
                raise PotatoError("unreachable")
            assigned = await self.store.assign_holder(game.id, user_id)
            if not await self._notify_holder(assigned.game):
                await self.store.rollback_undelivered_holder(
                    game.id, user_id, assigned.new_achievements
                )
                raise PotatoError("undeliverable")
        except PotatoError:
            await self.store.cancel_game(game.id)
            return False
        except BaseException:
            await self.store.cancel_game(game.id)
            raise
        await self._announce_achievements(user_id, assigned.new_achievements)
        return True

    async def _strong_rot_roll(self) -> int:
        holders = await self.store.active_holders()
        spawned = 0
        for user_id in await self.store.eligible_users():
            if user_id in holders or self._rng.random() >= self.strong_chance:
                continue
            if await self._spawn_rot_for(user_id):
                holders.add(user_id)
                spawned += 1
        return spawned

    async def start_rot_day(self, chat_id: int, starter_id: int) -> list[Game]:
        games: list[Game] = []
        for _ in range(roll_spawn_count(self._rng)):
            games.append(
                await self.start_game(
                    chat_id,
                    starter_id,
                    random_rot_duration(self._rng),
                    kind="rot",
                    announce=False,
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

    async def _launch_planned_spawns(self) -> None:
        for day, spawn_at in await self.store.expire_rot_spawns(ROT_MAX_LATENESS):
            attempts = self._spawn_attempts.pop((day, spawn_at), 0)
            logger.error(
                "potato: картошка дня гниения %s (на %s) окончательно пропущена: "
                "попыток запуска: %s (0 — бот был выключен или планировщик не успел)",
                day,
                self._local(spawn_at).strftime("%H:%M"),
                attempts,
            )
        for day, spawn_at, _is_first in await self.store.due_rot_spawns(
            ROT_MAX_LATENESS
        ):
            key = (day, spawn_at)
            try:
                await self.start_game(
                    self.auto_chat_id,
                    0,
                    random_rot_duration(self._rng),
                    kind="rot",
                    announce=False,
                )
            except Exception as exc:
                attempts = self._spawn_attempts.get(key, 0) + 1
                self._spawn_attempts[key] = attempts
                if attempts == 1 or attempts % SPAWN_LOG_EVERY == 0:
                    logger.warning(
                        "potato: не удалось запустить картошку дня гниения %s "
                        "(попытка %s, повторю позже): %s",
                        day,
                        attempts,
                        exc,
                        exc_info=not isinstance(exc, PotatoError),
                    )
                continue
            attempts = self._spawn_attempts.pop(key, 0) + 1
            if attempts > 1:
                logger.info(
                    "potato: картошка дня гниения %s запущена с попытки %s",
                    day,
                    attempts,
                )
            await self.store.mark_spawn_launched(day, spawn_at)

    async def _announce_rot_days(self) -> None:
        for day in await self.store.pending_rot_announces():
            if await self._say(self.auto_chat_id, ROT_ANNOUNCE):
                await self.store.mark_rot_announced(day)
            else:
                logger.warning(
                    "potato: не удалось объявить день гниения %s, повторю", day
                )

    async def note_activity(self, user_id: int) -> None:
        if self._flagged is None:
            self._flagged = await self.store.flagged_users()
        if user_id not in self._flagged:
            return
        self._flagged.discard(user_id)
        try:
            await self.store.touch_activity(user_id)
        except Exception:
            self._flagged.add(user_id)
            logger.exception("potato: не удалось снять паузу с игрока %s", user_id)

    async def tick(self) -> None:
        now = self.store.now()
        local = self._local(now)
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        base = int(midnight.timestamp())
        day = midnight.date().isoformat()
        await self.store.plan_rot_day(
            day,
            base + ROT_ANNOUNCE_FROM_HOUR * 3600,
            base + ACTIVE_TO_HOUR * 3600,
            ROT_DAY_PROBABILITY,
            announce_from=base + int(ROT_ANNOUNCE_FROM_HOUR * 3600),
            announce_to=base + int(ROT_ANNOUNCE_TO_HOUR * 3600),
        )
        await self._announce_rot_days()

        strong_until = await self.store.get_auto("strong_until")
        if strong_until is not None and now < strong_until:
            last_roll = await self.store.get_auto("strong_roll")
            if last_roll is None or now - last_roll >= STRONG_ROLL_SECONDS:
                await self.store.set_auto("strong_roll", now)
                try:
                    await self._strong_rot_roll()
                except Exception:
                    logger.exception("potato: strong rot roll failed")

        await self._launch_planned_spawns()

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
        if await self.store.active_game(self.auto_chat_id, auto=True) is not None:
            await self.store.set_auto("auto", retry)
            return
        try:
            await self.start_game(
                self.auto_chat_id,
                0,
                random_duration(self._rng),
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
        excluded = {user_id}
        target = await self._pick_reachable(game, excluded)
        while True:
            try:
                result = await self.store.pass_potato(game_id, user_id, target)
                break
            except PotatoError as exc:
                if target is None or str(exc) != (
                    "Получатель больше не может участвовать в игре."
                ):
                    raise
                excluded.add(target)
                target = await self._pick_reachable(game, excluded)
        if target is None:
            await self._say(
                user_id,
                "✅ Вы передали картошку — других игроков не осталось, игра окончена.",
            )
            await self._say(
                game.chat_id, "🥔 Картошку обезвредили: передавать её больше некому. 🎉"
            )
        elif not await self._notify_holder(result.game):
            await self.store.rollback_undelivered_holder(
                game_id, target, result.receiver_achievements
            )
            replacement = await self._assign_and_notify(result.game, {user_id, target})
            if replacement is None:
                finished = await self.store.defuse_unheld_game(game_id)
                result = replace(
                    result,
                    game=finished,
                    new_holder=None,
                    receiver_achievements=[],
                )
                await self._say(
                    user_id,
                    "✅ Передача засчитана, но уведомить других игроков не удалось. Игра завершена.",
                )
                await self._say(
                    game.chat_id,
                    "🥔 Картошку обезвредили: не удалось доставить её другим игрокам. 🎉",
                )
            else:
                result = replace(
                    result,
                    game=replacement.game,
                    new_holder=replacement.game.holder_id,
                    receiver_achievements=replacement.new_achievements,
                )
                assert replacement.game.holder_id is not None
                await self._announce_achievements(
                    replacement.game.holder_id, replacement.new_achievements
                )
        else:
            assert result.new_holder is not None
            await self._announce_achievements(
                result.new_holder, result.receiver_achievements
            )
        await self._announce_achievements(user_id, result.new_achievements)
        if self._flagged is not None:
            self._flagged.discard(user_id)
        return result

    async def resolve_expired(self) -> list[ExplodeResult]:
        results: list[ExplodeResult] = []
        now = self.store.now()
        for game in await self.store.active_games():
            if game.expires_at is None or game.expires_at > now:
                continue
            try:
                res = await self.store.explode_if_expired(game.id)
            except Exception:
                logger.exception("potato: expiry check failed for game %s", game.id)
                continue
            if res is None:
                continue
            results.append(res)
            if self._flagged is not None:
                self._flagged.add(res.victim)
            await self._say(
                res.victim,
                poison_text(await self.store.is_vip(res.victim)),
            )
            await self._announce_achievements(res.victim, res.new_achievements)
            title = (
                "🤢☠️ <b>Одна из гнилых картошек дня гниения сгнила!</b>"
                if game.kind == "rot"
                else "☠️ <b>Гнилая картошка сгнила!</b>"
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
