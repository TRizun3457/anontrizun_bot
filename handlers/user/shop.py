from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db

from .helpers import send_or_edit

router = Router()


@router.callback_query(F.data == "main_shop")
async def show_main_shop(callback: types.CallbackQuery) -> None:
    if callback.from_user is None:
        return
    user_stats = await db.get_user_stats(callback.from_user.id)
    text = (
        "🛒 <b>МАГАЗИН</b>\n"
        "─────────────────────\n"
        f"Ваш баланс: <b>{user_stats.balance} ⭐</b>\n\n"
        "💳 Пополнить баланс Stars\n"
        "💎 VIP-оформление — 100 ⭐\n"
        "💨 Воздух — 10 ⭐\n"
        "⭐ Приоритетный ответ — 1 ⭐\n"
        "🥔 Магазин гниения — сильное гниение и запуск картошки"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Пополнить баланс Stars", callback_data="deposit_menu"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 VIP-оформление (100 ⭐️)", callback_data="buy_vip"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💨 Купить воздух (10 ⭐️)", callback_data="buy_air"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Приоритет (1 ⭐️)", callback_data="buy_priority"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🥔 Магазин гниения", callback_data="potato_shop"
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="my_status")],
        ]
    )
    await send_or_edit(callback, text, kb)
