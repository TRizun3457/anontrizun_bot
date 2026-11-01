from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import database as db
from achievements import ACHIEVEMENTS
from potato.service import PotatoService

from .helpers import pick_pet, send_or_edit
from .keyboards import get_profile_actions_keyboard

router = Router()


@router.message(Command("status"), F.chat.type == "private")
@router.callback_query(F.data == "my_status")
async def show_status(
    event: types.Message | types.CallbackQuery, potato_service: PotatoService
) -> None:
    if event.from_user is None:
        return

    user_id = event.from_user.id
    user_stats = await db.register_user(user_id)
    banned = await db.is_banned(user_id)

    show_dogs = bool((await potato_service.store.get_stats(user_id))["show_dogs"])

    def pet_str() -> str:
        pet = pick_pet(user_stats.is_vip, user_stats.show_vip_cats, show_dogs)
        return f" {pet} " if pet else ""

    code_spoiler = f"<tg-spoiler><code>{user_stats.anon_code}</code></tg-spoiler>"
    status_text = "🚫 Заблокирован" if banned else "✅ Активен"
    vip_status = f"💎 VIP Подписчик{pet_str()}" if user_stats.is_vip else "❌ Нет"
    ach_count = await db.get_user_achievements_count(user_id)
    total_ach_count = len(ACHIEVEMENTS)

    ident_block = (
        "🆔 <b>Идентификация</b>\n"
        f"├ <b>Ваш код:</b> {code_spoiler}\n"
        f"├ <b>ID:</b> <code>{user_id}</code>\n"
        f"└ <b>Состояние:</b> {status_text}"
    )
    stats_block = (
        "📈 <b>Статистика сообщений</b>\n"
        f"├ <b>Отправлено анонимок:</b> <code>{user_stats.sent_count}</code> ✉️\n"
        f"├ <b>Получено ответов:</b> <code>{user_stats.received_count}</code> 💬\n"
        f"└ <b>Оплачено приоритетных:</b> <code>{user_stats.priority_messages}</code> ⭐️"
    )
    ach_block = (
        "🏆 <b>Достижения и Статусы</b>\n"
        f"├ <b>Достижений:</b> <code>{ach_count}/{total_ach_count}</code> 🎖️\n"
        f"└ <b>Куплено воздуха:</b> <code>{user_stats.air_purchased}</code> шт. 💨"
    )
    if user_stats.air_purchased > 0:
        ach_block += f"\n└ <b>Оценка:</b> <i>Ну и воздухан...{pet_str()}</i>"

    if user_stats.is_vip:
        top_block = (
            f"✨ 👑 <b>VIP-ПРОФИЛЬ{pet_str()}</b> 👑 \n"
            "⚡️ <i>Премиум-статус активирован</i>"
        )
    else:
        top_block = "👤 <b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>\n─────────────────────"

    finance_block = (
        f"💰 <b>Финансы{' и Status' if user_stats.is_vip else ''}</b>\n"
        f"├ <b>Баланс:</b> <b>{user_stats.balance}</b> ⭐️\n"
        f"└ <b>VIP Поддержка:</b> {vip_status}"
    )

    text = (
        f"{top_block}\n\n"
        f"{ident_block}\n\n"
        f"{finance_block}\n\n"
        f"{stats_block}\n\n"
        f"{ach_block}"
    )

    await send_or_edit(event, text, get_profile_actions_keyboard())


@router.callback_query(F.data == "my_achievements")
async def show_achievements(callback: types.CallbackQuery) -> None:
    if callback.from_user is None:
        return

    user_id = callback.from_user.id
    unlocked_ids = await db.get_user_achievements(user_id)
    total_ach_count = len(ACHIEVEMENTS)

    if not unlocked_ids:
        text = "🏆 <b>Ваши достижения</b>\n\nУ вас пока нет открытых достижений."
    else:
        text = f"🏆 <b>Открытые достижения ({len(unlocked_ids)}/{total_ach_count}):</b>\n\n"
        for ach_id in unlocked_ids:
            ach = ACHIEVEMENTS.get(ach_id)
            if ach:
                text += f"{ach['icon']} <b>{ach['title']}</b>\n{ach['description']}\n\n"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="my_status")]
        ]
    )
    await send_or_edit(callback, text, kb)
