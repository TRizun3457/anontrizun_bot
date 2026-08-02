import secrets
from dataclasses import dataclass

import aiosqlite
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from config import DB_NAME

_db_conn: aiosqlite.Connection | None = None
ban_cache: set[int] = set()

ACHIEVEMENTS: dict[str, dict[str, str]] = {
    "bro_42": {
        "title": "42 братуха",
        "description": "Написать '42' в анонимном сообщении",
        "icon": "🤖",
    },
    "air_1": {
        "title": "Воздухан обнаружен!",
        "description": "Купить воздух 1 раз",
        "icon": "💨",
    },
    "air_10": {
        "title": "Становится ветренно",
        "description": "Купить воздух 10 раз",
        "icon": "🌬️",
    },
    "air_100": {
        "title": "Ураган",
        "description": "Купить воздух 100 раз",
        "icon": "🌪️",
    },
    "vip_access": {
        "title": "Добро пожаловать в VIP зону",
        "description": "Приобрести VIP-оформление",
        "icon": "💎",
    },
    "degrade_67": {
        "title": "Деградируем",
        "description": "Отправить '67' анонимно",
        "icon": "🤪",
    },
    "anon_first": {
        "title": "Аноним",
        "description": "Отправить первое анонимное сообщение",
        "icon": "🕵️",
    },
    "who_are_you": {
        "title": "Кто ты?",
        "description": "Отправить 100 анонимных сообщений",
        "icon": "❓",
    },
    "secret_fan": {
        "title": "Тайный фанат",
        "description": "Отправить 200 анонимных сообщений",
        "icon": "❤️",
    },
    "vip_person": {
        "title": "Важная персона",
        "description": "Отправить 10 приоритетных сообщений",
        "icon": "⭐",
    },
    "first_donate": {
        "title": "Оооо кто-то мне задонатил!",
        "description": "Сделать первую любую покупку в боте",
        "icon": "🤑",
    },
    "not_interested": {
        "title": "Сорри не интересно",
        "description": "Не получить ответа 20 раз",
        "icon": "💔",
    },
    "answer_streak_15": {
        "title": "Целая серия",
        "description": "Получить 15 ответов подряд на разных сообщениях",
        "icon": "🔥",
    },
    "star_fall": {
        "title": "Звезда упала",
        "description": "Потратить более 100 звезд в боте",
        "icon": "🌠",
    },
    "impossible": {
        "title": "Невозможное возможно",
        "description": "Выдается одним из Contributors проекта",
        "icon": "🏆",
    },
}


def anon_code_fallback() -> str:
    return "НЕИЗВЕСТНО"


@dataclass
class UserStats:
    balance: int = 0
    air_purchased: int = 0
    priority_messages: int = 0
    sent_count: int = 0
    received_count: int = 0
    is_vip: bool = False
    anon_code: str = anon_code_fallback()


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
    global _db_conn, ban_cache
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
            anon_code TEXT,
            priority_sent_count INTEGER DEFAULT 0,
            total_spent_stars INTEGER DEFAULT 0,
            answer_streak INTEGER DEFAULT 0
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
    await db.execute("""
        CREATE TABLE IF NOT EXISTS user_achievements (
            user_id INTEGER,
            ach_id TEXT,
            unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, ach_id)
        )
    """)

    for query in (
        "ALTER TABLE users ADD COLUMN anon_code TEXT;",
        "ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT NULL;",
        "ALTER TABLE users ADD COLUMN priority_sent_count INTEGER DEFAULT 0;",
        "ALTER TABLE users ADD COLUMN total_spent_stars INTEGER DEFAULT 0;",
        "ALTER TABLE users ADD COLUMN answer_streak INTEGER DEFAULT 0;",
    ):
        try:
            await db.execute(query)
        except aiosqlite.OperationalError:
            pass

    await db.commit()

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
            return await get_user_stats(user_id)

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

    return await get_user_stats(user_id)


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
                row[6] if row[6] else anon_code_fallback(),
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

    if row is None or any(x is None for x in row):
        return None

    return SenderWithMessage(row[0], row[1])


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
        (1 if vip else 0, user_id),
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
        return anon_code_fallback() if row is None else row[0]


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
        (status, charge_id),
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


async def get_all_user_ids() -> list[int]:
    db = get_db()
    async with db.execute("SELECT user_id FROM users") as cursor:
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def get_user_id_by_id_or_code(identifier: str) -> int | None:
    db = get_db()
    identifier = identifier.strip()
    if identifier.isdigit():
        uid = int(identifier)
        async with db.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (uid,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
        async with db.execute(
            "SELECT user_id FROM banned WHERE user_id = ?", (uid,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
        return uid

    async with db.execute(
        "SELECT user_id FROM users WHERE UPPER(anon_code) = UPPER(?)", (identifier,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            return row[0]

    async with db.execute(
        "SELECT user_id FROM banned WHERE UPPER(anon_code) = UPPER(?)", (identifier,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            return row[0]

    return None


async def grant_achievement(user_id: int, ach_id: str, bot: Bot | None = None) -> bool:
    if ach_id not in ACHIEVEMENTS:
        return False

    db = get_db()
    async with db.execute(
        "SELECT 1 FROM user_achievements WHERE user_id = ? AND ach_id = ?",
        (user_id, ach_id),
    ) as cursor:
        if await cursor.fetchone():
            return False

    await db.execute(
        "INSERT OR IGNORE INTO user_achievements (user_id, ach_id) VALUES (?, ?)",
        (user_id, ach_id),
    )
    await db.commit()

    if bot:
        ach = ACHIEVEMENTS[ach_id]
        text = (
            f"🏆 <b>Новое достижение разблокировано!</b>\n\n"
            f"{ach['icon']} <b>{ach['title']}</b>\n"
            f"<i>{ach['description']}</i>"
        )
        try:
            await bot.send_message(
                chat_id=user_id, text=text, parse_mode=ParseMode.HTML
            )
        except TelegramAPIError:
            pass

    return True


async def grant_all_achievements(user_id: int, bot: Bot | None = None) -> int:
    count = 0
    for ach_id in ACHIEVEMENTS:
        if await grant_achievement(user_id, ach_id, bot):
            count += 1
    return count


async def get_user_achievements(user_id: int) -> list[str]:
    db = get_db()
    async with db.execute(
        "SELECT ach_id FROM user_achievements WHERE user_id = ?", (user_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def get_user_achievements_count(user_id: int) -> int:
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) FROM user_achievements WHERE user_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def increment_priority_sent_count(user_id: int):
    db = get_db()
    await db.execute(
        "UPDATE users SET priority_sent_count = priority_sent_count + 1 WHERE user_id = ?",
        (user_id,),
    )
    await db.commit()


async def increment_total_spent_stars(user_id: int, amount: int):
    db = get_db()
    await db.execute(
        "UPDATE users SET total_spent_stars = total_spent_stars + ? WHERE user_id = ?",
        (amount, user_id),
    )
    await db.commit()


async def increment_answer_streak(user_id: int):
    db = get_db()
    await db.execute(
        "UPDATE users SET answer_streak = answer_streak + 1 WHERE user_id = ?",
        (user_id,),
    )
    await db.commit()


async def check_and_grant_achievements(user_id: int, bot: Bot | None = None):
    db = get_db()
    async with db.execute(
        """
        SELECT air_purchased, sent_count, received_count, is_vip,
               priority_sent_count, total_spent_stars, answer_streak
        FROM users WHERE user_id = ?
        """,
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        return

    (
        air_purchased,
        sent_count,
        received_count,
        is_vip,
        priority_sent_count,
        total_spent_stars,
        answer_streak,
    ) = row

    if air_purchased >= 1:
        await grant_achievement(user_id, "air_1", bot)
    if air_purchased >= 10:
        await grant_achievement(user_id, "air_10", bot)
    if air_purchased >= 100:
        await grant_achievement(user_id, "air_100", bot)

    if is_vip:
        await grant_achievement(user_id, "vip_access", bot)

    if sent_count >= 1:
        await grant_achievement(user_id, "anon_first", bot)
    if sent_count >= 100:
        await grant_achievement(user_id, "who_are_you", bot)
    if sent_count >= 200:
        await grant_achievement(user_id, "secret_fan", bot)

    if (priority_sent_count or 0) >= 10:
        await grant_achievement(user_id, "vip_person", bot)

    if (sent_count - received_count) >= 20:
        await grant_achievement(user_id, "not_interested", bot)

    if (answer_streak or 0) >= 15:
        await grant_achievement(user_id, "answer_streak_15", bot)

    if (total_spent_stars or 0) > 100:
        await grant_achievement(user_id, "star_fall", bot)
