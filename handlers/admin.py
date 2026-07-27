from typing import cast
from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from config import ADMIN_ID

router = Router()


@router.message(Command("banlist"))
async def list_banned_codes(message: types.Message) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return

    db_conn = db.get_db()
    async with db_conn.execute("SELECT user_id, anon_code FROM banned") as cursor:
        fetched = await cursor.fetchall()
        rows = cast(list[tuple[int, str]], fetched)

    if not rows:
        _ = await message.answer("🚫 Список забаненных пользователей пуст.", parse_mode=ParseMode.HTML)
        return

    text = "🚫 <b>Список забаненных кодов:</b>\n\n"
    for uid, code in rows:
        text += f"• Код: <code>{code}</code> (ID: <code>{uid}</code>)\n"

    _ = await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("ban"))
async def ban_by_reply(message: types.Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return

    if not message.reply_to_message:
        _ = await message.answer(
            "⚠️ Чтобы забанить, ответьте командой <code>/ban</code> на сообщение.",
            parse_mode=ParseMode.HTML,
        )
        return

    admin_msg_id = message.reply_to_message.message_id
    db_conn = db.get_db()

    async with db_conn.execute(
        "SELECT sender_id, anon_code FROM messages WHERE admin_msg_id = ?",
        (admin_msg_id,),
    ) as cursor:
        fetched = await cursor.fetchone()
        result = cast(tuple[int, str] | None, fetched)

    if result:
        sender_id, anon_code = result

        await db.ban_user(sender_id, anon_code)

        try:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🙏 Попросить прощения (50 ⭐️)",
                            callback_data="buy_apology",
                        )
                    ]
                ]
            )
            _ = await bot.send_message(
                chat_id=sender_id,
                text="❌ <b>Вы были заблокированы администратором.</b>\n\nВы можете подать заявку на разбан за 50 ⭐️.",
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
            notify_status = "Оповещение доставлено."
        except Exception:
            notify_status = "Не удалось доставить оповещение."

        _ = await message.answer(
            f"🚫 Пользователь (ID: <code>{sender_id}</code>) заблокирован!\nКод: <code>{anon_code}</code>\n<i>{notify_status}</i>",
            parse_mode=ParseMode.HTML,
        )
    else:
        _ = await message.answer(
            "❌ Не удалось найти автора этого сообщения в базе.",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("unban"))
async def unban_by_code(message: types.Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return

    command_args = message.text.split(maxsplit=1)
    if len(command_args) < 2:
        _ = await message.answer(
            "⚠️ Пример: <code>/unban XXXXXX</code>", parse_mode=ParseMode.HTML
        )
        return

    anon_code = command_args[1].strip()
    db_conn = db.get_db()

    async with db_conn.execute(
        "SELECT user_id FROM banned WHERE anon_code = ?", (anon_code,)
    ) as cursor:
        fetched = await cursor.fetchone()
        result = cast(tuple[int] | None, fetched)

    if result:
        user_id = result[0]
        await db.unban_user(user_id)

        try:
            _ = await bot.send_message(
                chat_id=user_id,
                text="✅ <b>Вы были разблокированы!</b>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        _ = await message.answer(
            f"✅ Пользователь с кодом <code>{anon_code}</code> успешно разбанен.",
            parse_mode=ParseMode.HTML,
        )
    else:
        _ = await message.answer(
            "❌ Пользователь с таким кодом не найден.", parse_mode=ParseMode.HTML
        )


@router.callback_query(F.data.startswith("accept_unban_"))
async def accept_unban_handler(callback: types.CallbackQuery, bot: Bot) -> None:
    if not callback.data or not isinstance(callback.message, types.Message):
        return

    anon_code = callback.data.split("accept_unban_")[1]
    db_conn = db.get_db()

    async with db_conn.execute(
        "SELECT user_id FROM banned WHERE anon_code = ?", (anon_code,)
    ) as cursor:
        fetched = await cursor.fetchone()
        res = cast(tuple[int] | None, fetched)

    if res:
        user_id = res[0]
        await db.unban_user(user_id)

        try:
            _ = await bot.send_message(
                chat_id=user_id,
                text="✅ <b>Ваша заявка одобрена! Вы успешно разбанены.</b>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        current_text = callback.message.text or ""
        _ = await callback.message.edit_text(
            current_text + "\n\n<b>Статус: РАЗБАНЕН ✅</b>",
            parse_mode=ParseMode.HTML,
        )
    else:
        _ = await callback.answer("Пользователь уже разбанен.", show_alert=True)


@router.callback_query(F.data.startswith("decline_unban_"))
async def decline_unban_handler(callback: types.CallbackQuery, bot: Bot) -> None:
    if not callback.data or not isinstance(callback.message, types.Message):
        return

    user_id = int(callback.data.split("decline_unban_")[1])
    try:
        _ = await bot.send_message(
            chat_id=user_id,
            text="❌ <b>Ваша заявка на разбан отклонена.</b>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    current_text = callback.message.text or ""
    _ = await callback.message.edit_text(
        current_text + "\n\n<b>Статус: ОТКЛОНЕНО ❌</b>",
        parse_mode=ParseMode.HTML,
    )
    _ = await callback.answer()
