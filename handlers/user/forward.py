import logging

from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import database as db
from config import ADMIN_ID

from .helpers import is_plain_message
from .keyboards import get_banned_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.chat.type == "private", F.func(is_plain_message))
async def forward_anonymous_msg(message: types.Message, bot: Bot) -> None:
    if message.from_user is None:
        return

    ignored_types = {
        types.ContentType.NEW_CHAT_MEMBERS,
        types.ContentType.LEFT_CHAT_MEMBER,
        types.ContentType.NEW_CHAT_TITLE,
        types.ContentType.NEW_CHAT_PHOTO,
        types.ContentType.DELETE_CHAT_PHOTO,
        types.ContentType.SUCCESSFUL_PAYMENT,
        types.ContentType.REFUNDED_PAYMENT,
    }

    if (
        message.refunded_payment
        or message.successful_payment
        or message.content_type in ignored_types
    ):
        return

    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        return

    user_stats = await db.register_user(user_id)
    if await db.is_banned(user_id):
        await message.answer(
            "❌ Вы заблокированы в боте.",
            reply_markup=get_banned_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    is_priority = user_stats.priority_messages > 0
    if is_priority:
        # The balance may have been spent by a concurrent message.
        is_priority = await db.waste_priority_message(user_id)

    try:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="↩️ Ответить", callback_data=f"reply_{user_id}"
                    )
                ]
            ]
        )

        if user_stats.is_vip:
            vip_banner = (
                "═════════════════════\n💎 VIP-СООБЩЕНИЕ\n═════════════════════"
            )
            await bot.send_message(
                chat_id=ADMIN_ID, text=vip_banner, parse_mode=ParseMode.HTML
            )

        if is_priority:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text="🌟 [ПРИОРИТЕТНОЕ СООБЩЕНИЕ]",
                parse_mode=ParseMode.HTML,
            )

        sent_msg = await message.copy_to(chat_id=ADMIN_ID, reply_markup=keyboard)
    except TelegramAPIError:
        logger.exception("Forward error from %s", user_id)
        if is_priority:
            await db.increment_priority_messages(user_id)
        await message.answer("❌ Ошибка при отправке.", parse_mode=ParseMode.HTML)
        return

    await db.add_message(
        sent_msg.message_id,
        user_id,
        user_stats.anon_code,
        is_priority,
        message.message_id,
    )
    if is_priority:
        await db.increment_priority_sent_count(user_id)
    await db.increment_sent_count(user_id)

    msg_text = (message.text or message.caption or "").lower()
    if "42" in msg_text:
        await db.grant_achievement(user_id, "bro_42")
    if "67" in msg_text:
        await db.grant_achievement(user_id, "degrade_67")

    await db.check_and_grant_achievements(user_id)

    try:
        confirm_text = (
            "⭐ Приоритетное сообщение отправлено!"
            if is_priority
            else "🚀 Сообщение отправлено анонимно!"
        )
        await message.answer(confirm_text, parse_mode=ParseMode.HTML)
    except TelegramAPIError:
        logger.exception("Confirm error to %s", user_id)
