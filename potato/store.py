import asyncio
import random
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .achievements import RULES
from .randomness import candidate_weight, weighted_order
from .theme import fmt_duration

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "database_rs" / "migrations"
BASE_MIGRATION = MIGRATIONS_DIR / "0002_potato.sql"
EVENTS_MIGRATION = MIGRATIONS_DIR / "0003_potato_events.sql"
EVENTS_VERSION = 3
EXTRAS_MIGRATION = MIGRATIONS_DIR / "0004_potato_extras.sql"
INDEXES_MIGRATION = MIGRATIONS_DIR / "0005_potato_indexes.sql"
SLOTS_MIGRATION = MIGRATIONS_DIR / "0008_potato_game_slots.sql"
MANY_MIGRATION = MIGRATIONS_DIR / "0009_potato_many_member_games.sql"
ACTIVITY_MIGRATION = MIGRATIONS_DIR / "0010_potato_activity_and_rot_days.sql"
ACTIVITY_VERSION = 10
DORMANT_AFTER = 3
SPAWN_PENDING = 0
SPAWN_LAUNCHED = 1
SPAWN_SKIPPED = 2
REQUIRED_TABLES = frozenset(
    {
        "potato_players",
        "potato_games",
        "potato_history",
        "potato_achievements",
        "potato_chat_cooldown",
        "potato_rot_days",
        "potato_rot_spawns",
        "potato_auto",
        "potato_extra",
        "potato_purchases",
    }
)
SHARE_FIELDS = (
    "share_received",
    "share_passed",
    "share_exploded",
    "share_streak",
    "share_achievements",
    "share_fastest",
)

MIN_DURATION = 10 * 60
MAX_DURATION = 6 * 60 * 60
ROT_MIN_DURATION = 15 * 60
ROT_MAX_DURATION = 60 * 60
ROT_MAX_SPAWNS = 6
ROT_CHAIN_CHANCE = 0.6
ROT_SPAWN_GAP = 10 * 60


class PotatoError(Exception):
    pass


@dataclass(frozen=True)
class Game:
    id: int
    chat_id: int
    starter_id: int
    status: str
    holder_id: int | None
    holder_since: int | None
    expires_at: int | None
    pass_count: int
    duration_sec: int
    kind: str = "normal"


@dataclass(frozen=True)
class PassResult:
    game: Game
    old_holder: int
    new_holder: int | None
    elapsed: int
    new_achievements: list[str]
    receiver_achievements: list[str]


@dataclass(frozen=True)
class Assignment:
    game: Game
    new_achievements: list[str]


@dataclass(frozen=True)
class ExplodeResult:
    game: Game
    victim: int
    new_achievements: list[str]


def _game(row: sqlite3.Row | None) -> Game | None:
    if row is None:
        return None
    return Game(
        row["id"],
        row["chat_id"],
        row["starter_id"],
        row["status"],
        row["holder_id"],
        row["holder_since"],
        row["expires_at"],
        row["pass_count"],
        row["duration_sec"],
        row["kind"],
    )


def clamp_duration(seconds: int) -> int:
    return max(MIN_DURATION, min(MAX_DURATION, int(seconds)))


def random_duration(rng: random.Random | None = None) -> int:
    r = rng or random
    return r.randint(MIN_DURATION, MAX_DURATION)


def random_rot_duration(rng: random.Random | None = None) -> int:
    r = rng or random
    return r.randint(ROT_MIN_DURATION, ROT_MAX_DURATION)


def clamp_rot_duration(seconds: int) -> int:
    return max(ROT_MIN_DURATION, min(ROT_MAX_DURATION, int(seconds)))


def roll_spawn_count(
    rng: random.Random | None = None,
    chance: float = ROT_CHAIN_CHANCE,
    cap: int = ROT_MAX_SPAWNS,
) -> int:
    r = rng or random
    count = 1
    while count < cap and r.random() < chance**count:
        count += 1
    return count


class PotatoStore:
    def __init__(
        self,
        db_path: str,
        *,
        clock: Callable[[], float] = time.time,
        rng: random.Random | None = None,
    ) -> None:
        self.db_path = db_path
        self._clock = clock
        self._rng = rng or random.SystemRandom()
        self._lock = asyncio.Lock()
        self._keep: sqlite3.Connection | None = None
        if db_path == ":memory:":
            self._keep = self._open()

    def _conn(self) -> sqlite3.Connection:
        if self._keep is None:
            self._keep = self._open()
        return self._keep

    async def close(self) -> None:
        async with self._lock:
            if self._keep is not None:
                await asyncio.to_thread(self._keep.close)
                self._keep = None

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path, timeout=10, isolation_level=None, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        if self.db_path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _now(self) -> int:
        return int(self._clock())

    def _run_sync(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            result = fn(conn)
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
        return result

    async def _run(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        async with self._lock:
            return await asyncio.to_thread(self._run_sync, fn)

    async def init(self, apply_migrations: bool = True) -> None:
        def apply(conn: sqlite3.Connection) -> None:
            conn.executescript(BASE_MIGRATION.read_text(encoding="utf-8"))
            has_marker = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'potato_schema'"
            ).fetchone()
            applied = (
                has_marker
                and conn.execute(
                    "SELECT 1 FROM potato_schema WHERE version = ?", (EVENTS_VERSION,)
                ).fetchone()
            )
            if not applied:
                conn.executescript(EVENTS_MIGRATION.read_text(encoding="utf-8"))
            conn.executescript(EXTRAS_MIGRATION.read_text(encoding="utf-8"))
            conn.executescript(INDEXES_MIGRATION.read_text(encoding="utf-8"))
            conn.executescript(SLOTS_MIGRATION.read_text(encoding="utf-8"))
            conn.executescript(MANY_MIGRATION.read_text(encoding="utf-8"))
            activity_applied = conn.execute(
                "SELECT 1 FROM potato_schema WHERE version = ?", (ACTIVITY_VERSION,)
            ).fetchone()
            if not activity_applied:
                conn.executescript(ACTIVITY_MIGRATION.read_text(encoding="utf-8"))

        def verify(conn: sqlite3.Connection) -> None:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            missing = REQUIRED_TABLES - tables
            columns = (
                {row[1] for row in conn.execute("PRAGMA table_info(potato_games)")}
                if "potato_games" in tables
                else set()
            )
            player_columns = (
                {row[1] for row in conn.execute("PRAGMA table_info(potato_players)")}
                if "potato_players" in tables
                else set()
            )
            indexes = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }
            stale = bool(
                indexes
                & {"idx_potato_one_normal_per_chat", "idx_potato_one_member_per_chat"}
            )
            if (
                missing
                or "kind" not in columns
                or "dormant" not in player_columns
                or stale
            ):
                raise RuntimeError(
                    "Схема игры «Гнилая картошка» не создана миграциями Rust-модуля. "
                    "Пересоберите модуль (maturin develop) и запустите бота снова. "
                    f"Не хватает: {sorted(missing) or 'актуальные индексы potato_games (миграции 0008–0010)'}"
                )

        conn = self._conn()
        await asyncio.to_thread(apply if apply_migrations else verify, conn)

    def now(self) -> int:
        return self._now()

    @staticmethod
    def _ensure_player(conn: sqlite3.Connection, user_id: int) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO potato_players (user_id) VALUES (?)", (user_id,)
        )

    @staticmethod
    def _player(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
        PotatoStore._ensure_player(conn, user_id)
        return conn.execute(
            "SELECT * FROM potato_players WHERE user_id = ?", (user_id,)
        ).fetchone()

    @staticmethod
    def _extra(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
        conn.execute(
            "INSERT OR IGNORE INTO potato_extra (user_id) VALUES (?)", (user_id,)
        )
        return conn.execute(
            "SELECT * FROM potato_extra WHERE user_id = ?", (user_id,)
        ).fetchone()

    @staticmethod
    def _is_eligible(conn: sqlite3.Connection, user_id: int) -> bool:
        row = conn.execute(
            """
            SELECT u.user_id
            FROM users u
            LEFT JOIN potato_players p ON p.user_id = u.user_id
            WHERE u.user_id = ?
              AND u.user_id NOT IN (SELECT user_id FROM banned)
              AND COALESCE(p.enabled, 1) = 1
              AND COALESCE(p.dormant, 0) = 0
            """,
            (user_id,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _grant(conn: sqlite3.Connection, user_id: int) -> list[str]:
        stats = dict(PotatoStore._player(conn, user_id))
        stats.update(dict(PotatoStore._extra(conn, user_id)))
        granted: list[str] = []
        for ach_id, pred in RULES:
            if not pred(stats):
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO potato_achievements (user_id, ach_id) VALUES (?, ?)",
                (user_id, ach_id),
            )
            if cur.rowcount > 0:
                granted.append(ach_id)
        return granted

    async def get_stats(self, user_id: int) -> dict[str, Any]:
        def fn(conn: sqlite3.Connection) -> dict[str, Any]:
            data = dict(self._player(conn, user_id))
            data.update(dict(self._extra(conn, user_id)))
            data["achievements"] = [
                r["ach_id"]
                for r in conn.execute(
                    "SELECT ach_id FROM potato_achievements WHERE user_id = ? ORDER BY unlocked_at, ach_id",
                    (user_id,),
                )
            ]
            return data

        return await self._run(fn)

    def _leave_lock(
        self, conn: sqlite3.Connection, user_id: int
    ) -> tuple[str, int] | None:
        game = conn.execute(
            "SELECT 1 FROM potato_games WHERE starter_id = ? AND status = 'active'",
            (user_id,),
        ).fetchone()
        if game:
            return ("game", 0)
        row = conn.execute(
            "SELECT next_at FROM potato_auto WHERE key = ?", (f"lock:{user_id}",)
        ).fetchone()
        if row and row["next_at"] > self._now():
            return ("strong", row["next_at"] - self._now())
        return None

    async def leave_lock(self, user_id: int) -> tuple[str, int] | None:
        def fn(conn: sqlite3.Connection) -> tuple[str, int] | None:
            return self._leave_lock(conn, user_id)

        return await self._run(fn)

    async def lock_until(self, user_id: int, until: int) -> None:
        def fn(conn: sqlite3.Connection) -> None:
            self._ensure_player(conn, user_id)
            conn.execute(
                "UPDATE potato_players SET enabled = 1 WHERE user_id = ?", (user_id,)
            )
            conn.execute(
                """INSERT INTO potato_auto (key, next_at) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET next_at = MAX(next_at, excluded.next_at)""",
                (f"lock:{user_id}", until),
            )

        await self._run(fn)

    async def is_vip(self, user_id: int) -> bool:
        def fn(conn: sqlite3.Connection) -> bool:
            row = conn.execute(
                "SELECT is_vip FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return bool(row and row["is_vip"])

        return await self._run(fn)

    async def set_enabled(self, user_id: int, enabled: bool) -> None:
        def fn(conn: sqlite3.Connection) -> None:
            if not enabled:
                lock = self._leave_lock(conn, user_id)
                if lock is not None:
                    if lock[0] == "game":
                        raise PotatoError(
                            "Вы запустили игру — выйти можно, когда она закончится."
                        )
                    raise PotatoError(
                        "Вы купили сильное гниение — выйти можно через "
                        f"{fmt_duration(lock[1])}."
                    )
            self._ensure_player(conn, user_id)
            conn.execute(
                "UPDATE potato_players SET enabled = ? WHERE user_id = ?",
                (1 if enabled else 0, user_id),
            )

        await self._run(fn)

    async def set_dogs(self, user_id: int, shown: bool) -> None:
        def fn(conn: sqlite3.Connection) -> None:
            self._extra(conn, user_id)
            conn.execute(
                "UPDATE potato_extra SET show_dogs = ? WHERE user_id = ?",
                (1 if shown else 0, user_id),
            )

        await self._run(fn)

    async def set_share(self, user_id: int, field: str, shown: bool) -> None:
        if field not in SHARE_FIELDS:
            raise PotatoError("Неизвестный параметр.")

        def fn(conn: sqlite3.Connection) -> None:
            row = conn.execute(
                "SELECT is_vip FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row is None or not row["is_vip"]:
                raise PotatoError(
                    "Настраивать, чем делиться, могут только VIP-пользователи."
                )
            extra = self._extra(conn, user_id)
            if not shown and sum(extra[f] for f in SHARE_FIELDS if f != field) == 0:
                raise PotatoError("Хотя бы один показатель должен остаться включён.")
            conn.execute(
                f"UPDATE potato_extra SET {field} = ? WHERE user_id = ?",
                (1 if shown else 0, user_id),
            )

        await self._run(fn)

    async def record_start(self, user_id: int) -> list[str]:
        def fn(conn: sqlite3.Connection) -> list[str]:
            self._extra(conn, user_id)
            self._ensure_player(conn, user_id)
            conn.execute(
                "UPDATE potato_players SET enabled = 1 WHERE user_id = ?", (user_id,)
            )
            conn.execute(
                "UPDATE potato_extra SET started = started + 1 WHERE user_id = ?",
                (user_id,),
            )
            return self._grant(conn, user_id)

        return await self._run(fn)

    async def record_purchase(self, user_id: int, item: str, stars: int) -> list[str]:
        def fn(conn: sqlite3.Connection) -> list[str]:
            self._extra(conn, user_id)
            self._ensure_player(conn, user_id)
            conn.execute(
                "UPDATE potato_players SET enabled = 1 WHERE user_id = ?", (user_id,)
            )
            conn.execute(
                "UPDATE potato_extra SET bought = bought + 1 WHERE user_id = ?",
                (user_id,),
            )
            conn.execute(
                "INSERT INTO potato_purchases (user_id, item, stars, created_at) VALUES (?, ?, ?, ?)",
                (user_id, item, stars, self._now()),
            )
            return self._grant(conn, user_id)

        return await self._run(fn)

    async def eligible_users(self) -> list[int]:
        def fn(conn: sqlite3.Connection) -> list[int]:
            return self._candidates(conn, set(), frozenset())

        return await self._run(fn)

    async def active_holders(self) -> set[int]:
        def fn(conn: sqlite3.Connection) -> set[int]:
            return {
                r["holder_id"]
                for r in conn.execute(
                    "SELECT holder_id FROM potato_games WHERE status = 'active' AND holder_id IS NOT NULL"
                )
            }

        return await self._run(fn)

    def _candidates(
        self,
        conn: sqlite3.Connection,
        exclude: set[int],
        busy: frozenset[int] | set[int],
    ) -> list[int]:
        now = self._now()
        rows = conn.execute(
            """
            SELECT u.user_id, p.last_received_at FROM users u
            LEFT JOIN potato_players p ON p.user_id = u.user_id
            WHERE u.user_id NOT IN (SELECT user_id FROM banned)
              AND COALESCE(p.enabled, 1) = 1
              AND COALESCE(p.dormant, 0) = 0
            """
        ).fetchall()
        ids: list[int] = []
        weights: list[float] = []
        for r in rows:
            uid = r["user_id"]
            if uid in exclude:
                continue
            last = r["last_received_at"]
            ids.append(uid)
            weights.append(
                candidate_weight(None if last is None else now - last, uid in busy)
            )
        return weighted_order(ids, weights, self._rng)

    async def candidates(self, game_id: int, extra_exclude: set[int]) -> list[int]:
        def fn(conn: sqlite3.Connection) -> list[int]:
            seen = {
                r["user_id"]
                for r in conn.execute(
                    "SELECT user_id FROM potato_history WHERE game_id = ?", (game_id,)
                )
            }
            busy = {
                r["holder_id"]
                for r in conn.execute(
                    "SELECT holder_id FROM potato_games "
                    "WHERE status = 'active' AND holder_id IS NOT NULL AND id <> ?",
                    (game_id,),
                )
            }
            fresh = self._candidates(conn, seen | extra_exclude, busy)
            if fresh:
                return fresh
            return self._candidates(conn, extra_exclude, busy)

        return await self._run(fn)

    async def get_game(self, game_id: int) -> Game | None:
        def fn(conn: sqlite3.Connection) -> Game | None:
            return _game(
                conn.execute(
                    "SELECT * FROM potato_games WHERE id = ?", (game_id,)
                ).fetchone()
            )

        return await self._run(fn)

    async def active_game(self, chat_id: int, auto: bool | None = None) -> Game | None:
        sql = (
            "SELECT * FROM potato_games WHERE chat_id = ? AND status = 'active' "
            "AND kind = 'normal'"
        )
        if auto is True:
            sql += " AND starter_id = 0"
        elif auto is False:
            sql += " AND starter_id <> 0"

        def fn(conn: sqlite3.Connection) -> Game | None:
            return _game(conn.execute(sql, (chat_id,)).fetchone())

        return await self._run(fn)

    async def active_games(self) -> list[Game]:
        def fn(conn: sqlite3.Connection) -> list[Game]:
            return [
                g
                for r in conn.execute(
                    "SELECT * FROM potato_games WHERE status = 'active'"
                )
                if (g := _game(r)) is not None
            ]

        return await self._run(fn)

    async def create_game(
        self, chat_id: int, starter_id: int, duration_sec: int, kind: str = "normal"
    ) -> Game:
        duration = (
            clamp_rot_duration(duration_sec)
            if kind == "rot"
            else clamp_duration(duration_sec)
        )

        def fn(conn: sqlite3.Connection) -> Game:
            exists = (
                kind == "normal"
                and starter_id == 0
                and conn.execute(
                    "SELECT 1 FROM potato_games WHERE chat_id = ? AND status = 'active' "
                    "AND kind = 'normal' AND starter_id = 0",
                    (chat_id,),
                ).fetchone()
            )
            if exists:
                raise PotatoError("Автоматическая картошка уже идёт в этом чате.")
            cur = conn.execute(
                """INSERT INTO potato_games
                   (chat_id, starter_id, duration_sec, created_at, kind)
                   VALUES (?, ?, ?, ?, ?)""",
                (chat_id, starter_id, duration, self._now(), kind),
            )
            game = _game(
                conn.execute(
                    "SELECT * FROM potato_games WHERE id = ?", (cur.lastrowid,)
                ).fetchone()
            )
            assert game is not None
            return game

        return await self._run(fn)

    async def cancel_game(self, game_id: int) -> None:
        def fn(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE potato_games SET status = 'cancelled' WHERE id = ? AND status = 'active'",
                (game_id,),
            )

        await self._run(fn)

    async def assign_holder(self, game_id: int, user_id: int) -> Assignment:

        def fn(conn: sqlite3.Connection) -> Assignment:
            now = self._now()
            row = conn.execute(
                "SELECT * FROM potato_games WHERE id = ? AND status = 'active'",
                (game_id,),
            ).fetchone()
            if row is None:
                raise PotatoError("Игра уже завершена.")
            if row["holder_id"] is not None:
                raise PotatoError("У игры уже есть получатель картошки.")
            if not self._is_eligible(conn, user_id):
                raise PotatoError("Пользователь больше не может участвовать в игре.")
            conn.execute(
                """UPDATE potato_games SET holder_id = ?, holder_since = ?, expires_at = ?
                   WHERE id = ?""",
                (user_id, now, now + row["duration_sec"], game_id),
            )
            conn.execute(
                "INSERT OR IGNORE INTO potato_history (game_id, user_id) VALUES (?, ?)",
                (game_id, user_id),
            )
            self._ensure_player(conn, user_id)
            conn.execute(
                "UPDATE potato_players SET received = received + 1, last_received_at = ? WHERE user_id = ?",
                (now, user_id),
            )
            granted = self._grant(conn, user_id)
            game = _game(
                conn.execute(
                    "SELECT * FROM potato_games WHERE id = ?", (game_id,)
                ).fetchone()
            )
            assert game is not None
            return Assignment(game, granted)

        return await self._run(fn)

    async def pass_potato(
        self, game_id: int, from_user: int, to_user: int | None
    ) -> PassResult:

        def fn(conn: sqlite3.Connection) -> PassResult:
            now = self._now()
            row = conn.execute(
                "SELECT * FROM potato_games WHERE id = ?", (game_id,)
            ).fetchone()
            game = _game(row)
            if game is None or game.status != "active":
                raise PotatoError("Эта картошка уже не активна.")
            if game.holder_id != from_user:
                raise PotatoError("Картошка сейчас не у вас.")
            if game.expires_at is not None and now >= game.expires_at:
                raise PotatoError("Поздно — картошка уже сгнила! ☠️")
            if to_user == from_user:
                raise PotatoError("Нельзя передать картошку самому себе.")
            if to_user is None and game.kind == "rot":
                raise PotatoError(
                    "Сейчас некому передать картошку — попробуйте чуть позже."
                )
            if to_user is not None and not self._is_eligible(conn, to_user):
                raise PotatoError("Получатель больше не может участвовать в игре.")

            elapsed = max(0, now - (game.holder_since or now))
            self._ensure_player(conn, from_user)
            conn.execute(
                """UPDATE potato_players SET
                     passed = passed + 1,
                     miss_streak = 0,
                     dormant = 0,
                     pass_streak = pass_streak + 1,
                     best_pass_streak = MAX(best_pass_streak, pass_streak + 1),
                     fastest_pass_sec = CASE
                        WHEN fastest_pass_sec IS NULL OR ? < fastest_pass_sec THEN ?
                        ELSE fastest_pass_sec END
                   WHERE user_id = ?""",
                (elapsed, elapsed, from_user),
            )
            granted = self._grant(conn, from_user)
            receiver_granted: list[str] = []

            if to_user is None:
                conn.execute(
                    """UPDATE potato_games SET status = 'defused', holder_id = NULL,
                       expires_at = NULL, pass_count = pass_count + 1 WHERE id = ?""",
                    (game_id,),
                )
            else:
                conn.execute(
                    """UPDATE potato_games SET holder_id = ?, holder_since = ?,
                       expires_at = ?, pass_count = pass_count + 1 WHERE id = ?""",
                    (to_user, now, now + game.duration_sec, game_id),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO potato_history (game_id, user_id) VALUES (?, ?)",
                    (game_id, to_user),
                )
                self._ensure_player(conn, to_user)
                conn.execute(
                    "UPDATE potato_players SET received = received + 1, last_received_at = ? WHERE user_id = ?",
                    (now, to_user),
                )
                receiver_granted = self._grant(conn, to_user)
            new_game = _game(
                conn.execute(
                    "SELECT * FROM potato_games WHERE id = ?", (game_id,)
                ).fetchone()
            )
            assert new_game is not None
            return PassResult(
                new_game, from_user, to_user, elapsed, granted, receiver_granted
            )

        return await self._run(fn)

    async def rollback_undelivered_holder(
        self, game_id: int, failed_holder: int, failed_achievements: list[str]
    ) -> None:

        def fn(conn: sqlite3.Connection) -> None:
            row = conn.execute(
                "SELECT status, holder_id FROM potato_games WHERE id = ?", (game_id,)
            ).fetchone()
            if (
                row is None
                or row["status"] != "active"
                or row["holder_id"] != failed_holder
            ):
                raise PotatoError("Состояние игры изменилось до отмены получателя.")
            conn.execute(
                "UPDATE potato_players SET received = MAX(0, received - 1) WHERE user_id = ?",
                (failed_holder,),
            )
            for achievement_id in failed_achievements:
                conn.execute(
                    "DELETE FROM potato_achievements WHERE user_id = ? AND ach_id = ?",
                    (failed_holder, achievement_id),
                )
            conn.execute(
                """UPDATE potato_games
                   SET holder_id = NULL, holder_since = NULL, expires_at = NULL
                   WHERE id = ? AND status = 'active' AND holder_id = ?""",
                (game_id, failed_holder),
            )

        await self._run(fn)

    async def defuse_unheld_game(self, game_id: int) -> Game:
        def fn(conn: sqlite3.Connection) -> Game:
            conn.execute(
                """UPDATE potato_games SET status = 'defused'
                   WHERE id = ? AND status = 'active' AND holder_id IS NULL""",
                (game_id,),
            )
            game = _game(
                conn.execute(
                    "SELECT * FROM potato_games WHERE id = ?", (game_id,)
                ).fetchone()
            )
            if game is None or game.status != "defused":
                raise PotatoError("Не удалось завершить игру без получателя.")
            return game

        return await self._run(fn)

    async def explode_if_expired(self, game_id: int) -> ExplodeResult | None:
        def fn(conn: sqlite3.Connection) -> ExplodeResult | None:
            now = self._now()
            game = _game(
                conn.execute(
                    "SELECT * FROM potato_games WHERE id = ?", (game_id,)
                ).fetchone()
            )
            if (
                game is None
                or game.status != "active"
                or game.holder_id is None
                or game.expires_at is None
                or now < game.expires_at
            ):
                return None
            victim = game.holder_id
            self._ensure_player(conn, victim)
            conn.execute(
                """UPDATE potato_players SET exploded = exploded + 1, pass_streak = 0,
                   rot_exploded = rot_exploded + ?,
                   miss_streak = miss_streak + 1,
                   dormant = CASE WHEN miss_streak + 1 >= ? THEN 1 ELSE dormant END
                   WHERE user_id = ?""",
                (1 if game.kind == "rot" else 0, DORMANT_AFTER, victim),
            )
            granted = self._grant(conn, victim)
            conn.execute(
                "UPDATE potato_games SET status = 'exploded' WHERE id = ?", (game_id,)
            )
            done = _game(
                conn.execute(
                    "SELECT * FROM potato_games WHERE id = ?", (game_id,)
                ).fetchone()
            )
            assert done is not None
            return ExplodeResult(done, victim, granted)

        return await self._run(fn)

    async def cooldown_remaining(self, chat_id: int, cooldown_sec: int) -> int:
        def fn(conn: sqlite3.Connection) -> int:
            row = conn.execute(
                "SELECT last_started FROM potato_chat_cooldown WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if row is None:
                return 0
            return max(0, row["last_started"] + cooldown_sec - self._now())

        return await self._run(fn)

    async def mark_started(self, chat_id: int) -> None:
        def fn(conn: sqlite3.Connection) -> None:
            conn.execute(
                """INSERT INTO potato_chat_cooldown (chat_id, last_started) VALUES (?, ?)
                   ON CONFLICT(chat_id) DO UPDATE SET last_started = excluded.last_started""",
                (chat_id, self._now()),
            )

        await self._run(fn)

    async def get_auto(self, key: str) -> int | None:
        def fn(conn: sqlite3.Connection) -> int | None:
            row = conn.execute(
                "SELECT next_at FROM potato_auto WHERE key = ?", (key,)
            ).fetchone()
            return None if row is None else row["next_at"]

        return await self._run(fn)

    async def set_auto(self, key: str, next_at: int) -> None:
        def fn(conn: sqlite3.Connection) -> None:
            conn.execute(
                """INSERT INTO potato_auto (key, next_at) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET next_at = excluded.next_at""",
                (key, next_at),
            )

        await self._run(fn)

    async def plan_rot_day(
        self,
        day: str,
        window_start: int,
        window_end: int,
        probability: float,
        force: bool = False,
        announce_from: int | None = None,
        announce_to: int | None = None,
    ) -> bool:
        def fn(conn: sqlite3.Connection) -> bool:
            row = conn.execute(
                "SELECT is_rot FROM potato_rot_days WHERE day = ?", (day,)
            ).fetchone()
            if row is not None:
                return bool(row["is_rot"])
            now = self._now()
            is_rot = force or self._rng.random() < probability
            announce_at = 0
            spawn_start = max(window_start, now)
            if is_rot and announce_from is not None:
                lo = max(announce_from, now)
                hi = max(lo, announce_to if announce_to is not None else lo)
                announce_at = self._rng.randint(lo, hi)
                spawn_start = max(spawn_start, announce_at + ROT_SPAWN_GAP)
            span = window_end - spawn_start
            count = min(roll_spawn_count(self._rng), span // ROT_SPAWN_GAP)
            is_rot = is_rot and count >= 1
            conn.execute(
                "INSERT INTO potato_rot_days (day, is_rot, announce_at, announced) "
                "VALUES (?, ?, ?, ?)",
                (
                    day,
                    1 if is_rot else 0,
                    announce_at,
                    0 if is_rot and announce_at else 1,
                ),
            )
            if is_rot:
                times = sorted(self._rng.sample(range(spawn_start, window_end), count))
                for at in times:
                    conn.execute(
                        "INSERT INTO potato_rot_spawns (day, spawn_at) VALUES (?, ?)",
                        (day, at),
                    )
            return is_rot

        return await self._run(fn)

    async def pending_rot_announces(self) -> list[str]:
        def fn(conn: sqlite3.Connection) -> list[str]:
            return [
                r["day"]
                for r in conn.execute(
                    "SELECT day FROM potato_rot_days "
                    "WHERE is_rot = 1 AND announced = 0 AND announce_at <= ? "
                    "ORDER BY announce_at",
                    (self._now(),),
                )
            ]

        return await self._run(fn)

    async def mark_rot_announced(self, day: str) -> None:
        def fn(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE potato_rot_days SET announced = 1 WHERE day = ?", (day,)
            )

        await self._run(fn)

    async def rot_day_info(self, day: str) -> tuple[bool, int, bool] | None:
        def fn(conn: sqlite3.Connection) -> tuple[bool, int, bool] | None:
            row = conn.execute(
                "SELECT is_rot, announce_at, announced FROM potato_rot_days WHERE day = ?",
                (day,),
            ).fetchone()
            if row is None:
                return None
            return bool(row["is_rot"]), row["announce_at"], bool(row["announced"])

        return await self._run(fn)

    async def touch_activity(self, user_id: int) -> bool:
        def fn(conn: sqlite3.Connection) -> bool:
            cur = conn.execute(
                "UPDATE potato_players SET miss_streak = 0, dormant = 0 "
                "WHERE user_id = ? AND (miss_streak > 0 OR dormant = 1)",
                (user_id,),
            )
            return cur.rowcount > 0

        return await self._run(fn)

    async def flagged_users(self) -> set[int]:
        def fn(conn: sqlite3.Connection) -> set[int]:
            return {
                r["user_id"]
                for r in conn.execute(
                    "SELECT user_id FROM potato_players WHERE miss_streak > 0 OR dormant = 1"
                )
            }

        return await self._run(fn)

    async def expire_rot_spawns(self, max_age: int) -> list[tuple[str, int]]:
        def fn(conn: sqlite3.Connection) -> list[tuple[str, int]]:
            cutoff = self._now() - max_age
            rows = conn.execute(
                "SELECT day, spawn_at FROM potato_rot_spawns WHERE launched = ? AND spawn_at < ?",
                (SPAWN_PENDING, cutoff),
            ).fetchall()
            conn.execute(
                "UPDATE potato_rot_spawns SET launched = ? WHERE launched = ? AND spawn_at < ?",
                (SPAWN_SKIPPED, SPAWN_PENDING, cutoff),
            )
            return [(r["day"], r["spawn_at"]) for r in rows]

        return await self._run(fn)

    async def due_rot_spawns(self, max_age: int) -> list[tuple[str, int, bool]]:
        await self.expire_rot_spawns(max_age)

        def fn(conn: sqlite3.Connection) -> list[tuple[str, int, bool]]:
            rows = conn.execute(
                """SELECT day, spawn_at,
                   (SELECT COUNT(*) FROM potato_rot_spawns s2
                    WHERE s2.day = s.day AND s2.launched = ?) AS done
                   FROM potato_rot_spawns s
                   WHERE launched = ? AND spawn_at <= ? ORDER BY spawn_at""",
                (SPAWN_LAUNCHED, SPAWN_PENDING, self._now()),
            ).fetchall()
            return [(r["day"], r["spawn_at"], r["done"] == 0) for r in rows]

        return await self._run(fn)

    async def mark_spawn_launched(self, day: str, spawn_at: int) -> None:
        def fn(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE potato_rot_spawns SET launched = ? WHERE day = ? AND spawn_at = ?",
                (SPAWN_LAUNCHED, day, spawn_at),
            )

        await self._run(fn)
