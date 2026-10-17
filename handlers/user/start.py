from aiogram import Bot, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import database as db
from config import ADMIN_ID

from .keyboards import get_banned_keyboard, get_start_keyboard

router = Router()


@router.message(Command("anon"))
async def anon_group_cmd(message: types.Message, bot: Bot) -> None:
    if message.chat.type in ("group", "supergroup"):
        bot_username = (await bot.me()).username
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✉️ Написать анонимно",
                        url=f"https://t.me/{bot_username}?start=anon",
                    )
                ]
            ]
        )
        text = "✉️ <b>Анонимные сообщения</b>\n\nНажмите кнопку ниже, чтобы отправить анонимный вопрос!"
        await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await message.answer(
            "ℹ️ Команду <code>/anon</code> можно использовать в чатах и группах.",
            parse_mode=ParseMode.HTML,
        )


@router.message(CommandStart())
async def start_cmd(message: types.Message, command: CommandObject) -> None:
    if message.from_user is None or message.chat.type != "private":
        return

    referrer_id: int | None = None
    if command.args and command.args.startswith("ref_"):
        try:
            referrer_id = int(command.args.split("ref_")[1])
        except (ValueError, IndexError):
            pass

    await db.register_user(message.from_user.id, referrer_id)

    if message.from_user.id == ADMIN_ID:
        admin_text = (
            "👑 <b>Панель администратора</b>\n\n"
            "<b>Управление блокировками:</b>\n"
            "• <code>/ban</code> — забанить (в ответ на сообщение)\n"
            "• <code>/unban КОД|ID</code> — разбанить пользователя\n"
            "• <code>/banlist</code> — список забаненных кодов\n\n"
            "<b>Финансы и Рассылка:</b>\n"
            "• <code>/addbalance КОД|ID СУММА</code> — пополнить баланс Stars\n"
            "• <code>/refund КОД|ID|STX_ID</code> — возврат звёзд\n"
            "• <code>/broadcast</code> — рассылка сообщений пользователям"
        )
        await message.answer(admin_text, parse_mode=ParseMode.HTML)
        return

    if await db.is_banned(message.from_user.id):
        await message.answer(
            "❌ <b>Вы заблокированы в этом боте.</b>",
            reply_markup=get_banned_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    await message.answer(
        "Привет! Напиши сюда сообщение, и я передам его анонимно.",
        reply_markup=get_start_keyboard(),
        parse_mode=ParseMode.HTML,
    )
