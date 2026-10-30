import asyncio
import random
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .achievements import RULES

MIGRATION = (
    Path(__file__).resolve().parent.parent
    / "database_rs"
    / "migrations"
    / "0002_potato.sql"
)

MIN_DURATION = 10 * 60
MAX_DURATION = 6 * 60 * 60


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
    )


def clamp_duration(seconds: int) -> int:
    return max(MIN_DURATION, min(MAX_DURATION, int(seconds)))


def random_duration(rng: random.Random | None = None) -> int:
    r = rng or random
    return r.randint(MIN_DURATION, MAX_DURATION)


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
        self._rng = rng or random.Random()
        self._lock = asyncio.Lock()
        self._keep: sqlite3.Connection | None = None
        if db_path == ":memory:":
            self._keep = self._open()

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
        conn = self._keep or self._open()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                result = fn(conn)
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
            return result
        finally:
            if self._keep is None:
                conn.close()

    async def _run(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        async with self._lock:
            return await asyncio.to_thread(self._run_sync, fn)

    async def init(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        conn = self._keep or self._open()
        try:
            conn.executescript(sql)
        finally:
            if self._keep is None:
                conn.close()

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
    def _grant(conn: sqlite3.Connection, user_id: int) -> list[str]:
        stats = dict(PotatoStore._player(conn, user_id))
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
            data["achievements"] = [
                r["ach_id"]
                for r in conn.execute(
                    "SELECT ach_id FROM potato_achievements WHERE user_id = ? ORDER BY unlocked_at, ach_id",
                    (user_id,),
                )
            ]
            return data

        return await self._run(fn)

    async def set_enabled(self, user_id: int, enabled: bool) -> None:

        def fn(conn: sqlite3.Connection) -> None:
            if not enabled:
                row = conn.execute(
                    "SELECT is_vip FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                if row is None or not row["is_vip"]:
                    raise PotatoError("Скрыть игру могут только VIP-пользователи.")
            self._ensure_player(conn, user_id)
            conn.execute(
                "UPDATE potato_players SET enabled = ? WHERE user_id = ?",
                (1 if enabled else 0, user_id),
            )

        await self._run(fn)

    def _candidates(
        self,
        conn: sqlite3.Connection,
        exclude: set[int],
        admin_id: int | None,
    ) -> list[int]:
        rows = conn.execute(
            """
            SELECT u.user_id FROM users u
            LEFT JOIN potato_players p ON p.user_id = u.user_id
            WHERE u.user_id NOT IN (SELECT user_id FROM banned)
              AND (COALESCE(p.enabled, 1) = 1 OR u.is_vip = 0)
            """
        ).fetchall()
        return [
            r["user_id"]
            for r in rows
            if r["user_id"] not in exclude and r["user_id"] != admin_id
        ]

    async def candidates(
        self, game_id: int, extra_exclude: set[int], admin_id: int | None
    ) -> list[int]:

        def fn(conn: sqlite3.Connection) -> list[int]:
            seen = {
                r["user_id"]
                for r in conn.execute(
                    "SELECT user_id FROM potato_history WHERE game_id = ?", (game_id,)
                )
            }
            fresh = self._candidates(conn, seen | extra_exclude, admin_id)
            if fresh:
                self._rng.shuffle(fresh)
                return fresh
            again = self._candidates(conn, extra_exclude, admin_id)
            self._rng.shuffle(again)
            return again

        return await self._run(fn)

    async def get_game(self, game_id: int) -> Game | None:
        def fn(conn: sqlite3.Connection) -> Game | None:
            return _game(
                conn.execute(
                    "SELECT * FROM potato_games WHERE id = ?", (game_id,)
                ).fetchone()
            )

        return await self._run(fn)

    async def active_game(self, chat_id: int) -> Game | None:
        def fn(conn: sqlite3.Connection) -> Game | None:
            return _game(
                conn.execute(
                    "SELECT * FROM potato_games WHERE chat_id = ? AND status = 'active'",
                    (chat_id,),
                ).fetchone()
            )

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
        self, chat_id: int, starter_id: int, duration_sec: int
    ) -> Game:
        duration = clamp_duration(duration_sec)

        def fn(conn: sqlite3.Connection) -> Game:
            exists = conn.execute(
                "SELECT 1 FROM potato_games WHERE chat_id = ? AND status = 'active'",
                (chat_id,),
            ).fetchone()
            if exists:
                raise PotatoError("В этом чате уже идёт игра в картошку.")
            cur = conn.execute(
                """INSERT INTO potato_games
                   (chat_id, starter_id, duration_sec, created_at) VALUES (?, ?, ?, ?)""",
                (chat_id, starter_id, duration, self._now()),
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
                "UPDATE potato_players SET received = received + 1 WHERE user_id = ?",
                (user_id,),
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
                raise PotatoError("Поздно — картошка уже взорвалась! 💥")
            if to_user == from_user:
                raise PotatoError("Нельзя передать картошку самому себе.")

            elapsed = max(0, now - (game.holder_since or now))
            self._ensure_player(conn, from_user)
            conn.execute(
                """UPDATE potato_players SET
                     passed = passed + 1,
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
                    "UPDATE potato_players SET received = received + 1 WHERE user_id = ?",
                    (to_user,),
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
                """UPDATE potato_players SET exploded = exploded + 1, pass_streak = 0
                   WHERE user_id = ?""",
                (victim,),
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
