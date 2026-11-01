from aiogram import types
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineKeyboardMarkup,
)

import database as db
from pets import pick_pet_from

from .constants import CAT_KAOMOJI_LIST, DOG_KAOMOJI_LIST


def is_plain_message(message: types.Message) -> bool:
    return not (message.text or "").startswith("/")


async def send_or_edit(
    event: types.Message | types.CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    if isinstance(event, types.CallbackQuery):
        if isinstance(event.message, types.Message):
            await event.message.edit_text(
                text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
            )
        await event.answer()
    else:
        await event.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


def pick_pet(is_vip: bool, show_cats: bool, show_dogs: bool) -> str:
    if not is_vip:
        return ""
    return pick_pet_from(CAT_KAOMOJI_LIST, DOG_KAOMOJI_LIST, show_cats, show_dogs)


def get_share_preview_text(
    user_stats: db.UserStats,
    ach_count: int,
    total_ach: int,
    show_dogs: bool = False,
) -> str:
    pet = pick_pet(user_stats.is_vip, user_stats.show_vip_cats, show_dogs)
    cat_inline = f" {pet} " if pet else ""

    stats_items = []
    if user_stats.show_sent:
        stats_items.append(f"✉️ Отправлено анонимок: <b>{user_stats.sent_count}</b>")
    if user_stats.show_received:
        stats_items.append(f"💬 Получено ответов: <b>{user_stats.received_count}</b>")
    if user_stats.show_priority:
        stats_items.append(f"⭐ Приоритетных: <b>{user_stats.priority_messages}</b>")
    if user_stats.show_air:
        stats_items.append(f"💨 Воздуха куплено: <b>{user_stats.air_purchased}</b>")
    if user_stats.show_achievements:
        stats_items.append(f"🏆 Достижений: <b>{ach_count}/{total_ach}</b>")

    stats_body = "\n".join(stats_items)

    if user_stats.is_vip:
        header_vip = f"✨ 👑 <b>VIP-ПРОФИЛЬ{cat_inline}</b> 👑 ✨"
        return (
            f"{header_vip}\n"
            "💎 <b>Статус:</b> VIP Подписчик\n\n"
            "📊 <b>Статистика:</b>\n"
            f"{stats_body}"
        )
    return f"📊 <b>Анонимная статистика:</b>\n{stats_body}"


async def toggle_visibility_field(user_id: int, field_name: str) -> bool:
    user_stats = await db.get_user_stats(user_id)
    active_count = sum(
        1
        for val in (
            user_stats.show_sent,
            user_stats.show_received,
            user_stats.show_priority,
            user_stats.show_air,
            user_stats.show_achievements,
        )
        if val
    )
    current_val = getattr(user_stats, field_name)
    if current_val and active_count <= 1:
        return False
    await db.update_user_setting(user_id, field_name, "0" if current_val else "1")
    return True
