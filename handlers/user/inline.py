from typing import Any

from aiogram import Bot, Router, types
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

import database as db
from achievements import ACHIEVEMENTS
from config import ADMIN_ID

from .helpers import get_share_preview_text

router = Router()


@router.inline_query()
async def inline_query_handler(inline_query: types.InlineQuery, bot: Bot) -> None:
    bot_username = (await bot.me()).username
    user_id = inline_query.from_user.id
    user_stats = await db.register_user(user_id)
    results: list[Any] = []

    if user_id == ADMIN_ID:
        share_text = "✉️ Задай мне анонимный вопрос!\n\nНапиши всё, что думаешь — всё передастся анонимно!"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💬 Написать анонимно",
                        url=f"https://t.me/{bot_username}?start=anon",
                    )
                ]
            ]
        )
        results.append(
            InlineQueryResultArticle(
                id="admin_share",
                title="🚀 Поделиться ссылкой на анонимки",
                description="Отправить ссылку на бота",
                input_message_content=InputTextMessageContent(
                    message_text=share_text, parse_mode=ParseMode.HTML
                ),
                reply_markup=kb,
            )
        )

    ach_count = await db.get_user_achievements_count(user_id)
    total_ach_count = len(ACHIEVEMENTS)
    stats_text = get_share_preview_text(user_stats, ach_count, total_ach_count)
    share_title = (
        "👑 Поделиться VIP профилем"
        if user_stats.is_vip
        else "📊 Поделиться статистикой"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✉️ Написать анонимно",
                    url=f"https://t.me/{bot_username}?start=share",
                )
            ]
        ]
    )
    results.append(
        InlineQueryResultArticle(
            id="user_status_share",
            title=share_title,
            description="Показать мою статистику",
            input_message_content=InputTextMessageContent(
                message_text=stats_text, parse_mode=ParseMode.HTML
            ),
            reply_markup=kb,
        )
    )
    await inline_query.answer(results, cache_time=1, is_personal=True)
