import secrets
from dataclasses import dataclass

import aiosqlite

from config import DB_NAME

_db_conn: aiosqlite.Connection | None = None
ban_cache: set[int] = set()


@dataclass
class UserStats:
    balance: int = 0
    air_purchased: int = 0
    priority_messages: int = 0
    sent_count: int = 0
    received_count: int = 0
    is_vip: bool = False
    anon_code: str = "НЕИЗВЕСТНО"


@dataclass
class SenderWithMessage:
    sender_id: int
    user_msg_id: int


@dataclass
class SenderWithCode:
    sender_id: int
    anon_code: str


@dataclass
class BannedUser:
    user_id: int
    anon_code: str


def get_db() -> aiosqlite.Connection:
    if _db_conn is None:
        raise RuntimeError("База данных не инициализирована! Вызовите init_db().")
    return _db_conn


async def init_db() -> None:
    global _db_conn
    _db_conn = await aiosqlite.connect(DB_NAME)

    db = get_db()
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA synchronous=NORMAL;")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            admin_msg_id INTEGER PRIMARY KEY,
            sender_id INTEGER,
            anon_code TEXT,
            is_priority INTEGER DEFAULT 0,
            user_msg_id INTEGER
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS banned (
            user_id INTEGER PRIMARY KEY,
            anon_code TEXT
        )
    """)
    await db.execute("""
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
    await db.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            charge_id TEXT PRIMARY KEY,
            user_id INTEGER,
            payload TEXT,
            status TEXT DEFAULT 'success'
        )
    """)
    await db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS anon_code TEXT;")
    await db.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referrer_id INTEGER DEFAULT NULL;"
    )
    await db.commit()

    await load_ban_cache()


async def load_ban_cache() -> None:
    global ban_cache
    db = get_db()
    async with db.execute("SELECT user_id FROM banned") as cursor:
        rows = await cursor.fetchall()
        ban_cache = {row[0] for row in rows}


async def is_banned(user_id: int) -> bool:
    return user_id in ban_cache


async def ban_user(user_id: int, anon_code: str) -> None:
    db = get_db()
    await db.execute(
        "INSERT OR REPLACE INTO banned (user_id, anon_code) VALUES (?, ?)",
        (user_id, anon_code),
    )
    await db.commit()
    ban_cache.add(user_id)


async def unban_user(user_id: int) -> None:
    db = get_db()
    await db.execute("DELETE FROM banned WHERE user_id = ?", (user_id,))
    await db.commit()
    ban_cache.discard(user_id)


async def register_user(user_id: int, referrer_id: int | None = None) -> UserStats:
    db = get_db()
    async with db.execute(
        "SELECT anon_code FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            if row[0] is None:
                raise RuntimeError("user exists but anon code is None")
            return UserStats(anon_code=row[0])

    anon_code = secrets.token_hex(4).upper()
    await db.execute(
        "INSERT OR IGNORE INTO users (user_id, anon_code, referrer_id) VALUES (?, ?, ?)",
        (user_id, anon_code, referrer_id if referrer_id != user_id else None),
    )
    await db.execute(
        "UPDATE users SET anon_code = ? WHERE user_id = ? AND (anon_code IS NULL OR anon_code = '')",
        (anon_code, user_id),
    )
    await db.commit()

    return UserStats(anon_code=anon_code)


async def get_user_stats(user_id: int) -> UserStats:
    db = get_db()
    async with db.execute(
        "SELECT balance, air_purchased, priority_messages, sent_count, received_count, is_vip, anon_code FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return (
            UserStats(
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5] == 1,
                row[6] if row[6] else "НЕИЗВЕСТНО",
            )
            if row
            else UserStats()
        )


async def waste_priority_message(user_id: int):
    db = get_db()

    await db.execute(
        "UPDATE users SET priority_messages = priority_messages - 1 WHERE user_id = ?",
        (user_id,),
    )
    await db.commit()


async def increment_sent_count(user_id: int):
    db = get_db()

    await db.execute(
        "UPDATE users SET sent_count = sent_count + 1 WHERE user_id = ?", (user_id,)
    )
    await db.commit()


async def increment_received_count(user_id: int):
    db = get_db()

    await db.execute(
        "UPDATE users SET received_count = received_count + 1 WHERE user_id = ?",
        (user_id,),
    )
    await db.commit()


async def add_message(
    admin_msg_id: int,
    sender_id: int,
    anon_code: str,
    is_priority: bool,
    user_msg_id: int,
):
    db = get_db()

    await db.execute(
        "INSERT INTO messages (admin_msg_id, sender_id, anon_code, is_priority, user_msg_id) VALUES (?, ?, ?, ?, ?)",
        (admin_msg_id, sender_id, anon_code, 1 if is_priority else 0, user_msg_id),
    )
    await db.commit()


async def get_admin_msg_id_by_user_msg_id(
    sender_id: int, user_msg_id: int
) -> int | None:
    db = get_db()

    async with db.execute(
        "SELECT admin_msg_id FROM messages WHERE sender_id = ? AND user_msg_id = ?",
        (sender_id, user_msg_id),
    ) as cursor:
        row = await cursor.fetchone()

    return row[0] if row else None


async def get_sender_with_message_by_admin_msg(
    admin_msg_id: int,
) -> SenderWithMessage | None:
    db = get_db()

    async with db.execute(
        "SELECT sender_id, user_msg_id FROM messages WHERE admin_msg_id = ?",
        (admin_msg_id,),
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return None

    sender_id, user_msg_id = row

    # both params must be not None
    if any(x is None for x in (sender_id, user_msg_id)):
        return None

    return SenderWithMessage(sender_id, user_msg_id)


async def take_balance(amount: int, user_id: int):
    db = get_db()

    await db.execute(
        "UPDATE users SET balance = balance - ? WHERE user_id = ?",
        (amount, user_id),
    )

    await db.commit()


async def increment_priority_messages(user_id: int):
    db = get_db()

    await db.execute(
        "UPDATE users SET priority_messages = priority_messages + 1 WHERE user_id = ?",
        (user_id,),
    )

    await db.commit()


async def set_vip(user_id: int, vip: bool = True):
    db = get_db()

    await db.execute(
        "UPDATE users SET is_vip = ? WHERE user_id = ?",
        (
            1 if vip else 0,
            user_id,
        ),
    )

    await db.commit()


async def increment_air_purchased(user_id: int):
    db = get_db()

    await db.execute(
        "UPDATE users SET air_purchased = air_purchased + 1 WHERE user_id = ?",
        (user_id,),
    )

    await db.commit()


async def get_banned_users() -> list[BannedUser]:
    db = get_db()

    async with db.execute("SELECT user_id, anon_code FROM banned") as cursor:
        rows = await cursor.fetchall()
        return [BannedUser(user_id=row[0], anon_code=row[1]) for row in rows]


async def get_banned_user_id_by_anon_code(anon_code: str) -> int | None:
    db = get_db()

    async with db.execute(
        "SELECT user_id FROM banned WHERE anon_code = ?", (anon_code,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_sender_with_code_by_admin_msg(admin_msg_id: int) -> SenderWithCode | None:
    db = get_db()

    async with db.execute(
        "SELECT sender_id, anon_code FROM messages WHERE admin_msg_id = ?",
        (admin_msg_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return SenderWithCode(sender_id=row[0], anon_code=row[1]) if row else None


async def create_payment(charge_id: str, user_id: int, payload: str):
    db = get_db()

    await db.execute(
        "INSERT INTO payments (charge_id, user_id, payload, status) VALUES (?, ?, ?, 'success')",
        (charge_id, user_id, payload),
    )

    await db.commit()


async def give_balance(amount: int, user_id: int):
    db = get_db()

    await db.execute(
        "UPDATE users SET balance = balance + ? WHERE user_id = ?",
        (amount, user_id),
    )

    await db.commit()


async def get_banned_anon_code_by_user_id(user_id: int) -> str:
    db = get_db()

    async with db.execute(
        "SELECT anon_code FROM banned WHERE user_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return "НЕИЗВЕСТНО" if row is None else row[0]


async def get_payment_user_id_by_charge_id(charge_id: str) -> int | None:
    db = get_db()

    async with db.execute(
        "SELECT user_id FROM payments WHERE charge_id = ?", (charge_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else None


async def set_payment_status_by_charge_id(charge_id: str, status: str):
    db = get_db()

    await db.execute(
        "UPDATE payments SET status = ? WHERE charge_id = ?",
        (
            status,
            charge_id,
        ),
    )

    await db.commit()


async def batch_set_payment_status_by_charge_ids(charge_ids: list[str], status: str):
    if not charge_ids:
        return

    db = get_db()

    placeholders = ", ".join(["?"] * len(charge_ids))
    await db.execute(
        f"UPDATE payments SET status = ? WHERE charge_id IN ({placeholders})",
        (status, *charge_ids),
    )

    await db.commit()


async def get_success_charge_ids_by_user_id(user_id: int) -> list[str]:
    db = get_db()

    async with db.execute(
        "SELECT charge_id FROM payments WHERE user_id = ? AND status = 'success'",
        (user_id,),
    ) as cursor:
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
