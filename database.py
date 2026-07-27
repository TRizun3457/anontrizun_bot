import secrets
from typing import cast
import aiosqlite
from config import DB_NAME

db_pool: aiosqlite.Connection | None = None
ban_cache: set[int] = set()


def get_db() -> aiosqlite.Connection:
    if db_pool is None:
        raise RuntimeError("База данных не инициализирована! Вызовите init_db().")
    return db_pool


async def init_db() -> None:
    global db_pool
    db_pool = await aiosqlite.connect(DB_NAME)

    db = get_db()
    _ = await db.execute("PRAGMA journal_mode=WAL;")
    _ = await db.execute("PRAGMA synchronous=NORMAL;")

    _ = await db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            admin_msg_id INTEGER PRIMARY KEY,
            sender_id INTEGER,
            anon_code TEXT,
            is_priority INTEGER DEFAULT 0,
            user_msg_id INTEGER
        )
    """)
    _ = await db.execute("""
        CREATE TABLE IF NOT EXISTS banned (
            user_id INTEGER PRIMARY KEY,
            anon_code TEXT
        )
    """)
    _ = await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            air_purchased INTEGER DEFAULT 0,
            priority_messages INTEGER DEFAULT 0,
            sent_count INTEGER DEFAULT 0,
            received_count INTEGER DEFAULT 0,
            is_vip INTEGER DEFAULT 0,
            referrer_id INTEGER DEFAULT NULL,
            anon_code TEXT
        )
    """)
    _ = await db.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            charge_id TEXT PRIMARY KEY,
            user_id INTEGER,
            payload TEXT,
            status TEXT DEFAULT 'success'
        )
    """)
    await db.commit()


    async with db.execute("PRAGMA table_info(users)") as cursor:
        fetched = await cursor.fetchall()
        rows = cast(list[tuple[int, str, str, int, object, int]], fetched)
        columns = [row[1] for row in rows]
        if "anon_code" not in columns:
            _ = await db.execute("ALTER TABLE users ADD COLUMN anon_code TEXT;")
        if "referrer_id" not in columns:
            _ = await db.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT NULL;")
        await db.commit()

    await load_ban_cache()


async def load_ban_cache() -> None:
    global ban_cache
    db = get_db()
    async with db.execute("SELECT user_id FROM banned") as cursor:
        fetched = await cursor.fetchall()
        rows = cast(list[tuple[int]], fetched)
        ban_cache = {row[0] for row in rows}


async def is_banned(user_id: int) -> bool:
    return user_id in ban_cache


async def ban_user(user_id: int, anon_code: str) -> None:
    db = get_db()
    _ = await db.execute(
        "INSERT OR REPLACE INTO banned (user_id, anon_code) VALUES (?, ?)",
        (user_id, anon_code),
    )
    await db.commit()
    ban_cache.add(user_id)


async def unban_user(user_id: int) -> None:
    db = get_db()
    _ = await db.execute("DELETE FROM banned WHERE user_id = ?", (user_id,))
    await db.commit()
    ban_cache.discard(user_id)


async def register_user(user_id: int, referrer_id: int | None = None) -> str:
    db = get_db()
    async with db.execute("SELECT anon_code FROM users WHERE user_id = ?", (user_id,)) as cursor:
        fetched = await cursor.fetchone()
        row = cast(tuple[str | None] | None, fetched)
        if row and row[0]:
            return row[0]

    anon_code = secrets.token_hex(4).upper()
    _ = await db.execute(
        "INSERT OR IGNORE INTO users (user_id, anon_code, referrer_id) VALUES (?, ?, ?)",
        (user_id, anon_code, referrer_id if referrer_id != user_id else None),
    )
    _ = await db.execute(
        "UPDATE users SET anon_code = ? WHERE user_id = ? AND (anon_code IS NULL OR anon_code = '')",
        (anon_code, user_id),
    )
    await db.commit()
    return anon_code


async def get_user_stats(user_id: int) -> tuple[int, int, int, int, int, int, str]:
    db = get_db()
    async with db.execute(
        "SELECT balance, air_purchased, priority_messages, sent_count, received_count, is_vip, anon_code FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        fetched = await cursor.fetchone()
        res = cast(tuple[int, int, int, int, int, int, str | None] | None, fetched)
        if res:
            return (
                res[0],
                res[1],
                res[2],
                res[3],
                res[4],
                res[5],
                res[6] if res[6] is not None else "НЕИЗВЕСТНО",
            )
        return (0, 0, 0, 0, 0, 0, "НЕИЗВЕСТНО")
