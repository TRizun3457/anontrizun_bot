import logging
import random
from typing import cast

from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResult,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

import database as db
from config import ADMIN_ID

router = Router()
logger = logging.getLogger(__name__)

CAT_KAOMOJI_LIST = [
    "( =ω= ) ",
    "(ฅ^•ﻌ•^ฅ) ",
    "(=^･ω･^=) ",
    "(✿^ω^) ",
    "(≡^∇^≡) ",
    "(=^-ω-^=) ",
    "(๑ↀᴥ๑) ",
    "(ฅ'ω'ฅ) ",
]


class ReplyState(StatesGroup):
    waiting_for_reply = State()


@router.message(Command("anon"))
async def anon_group_cmd(message: types.Message, bot_username: str) -> None:
    if message.chat.type in ("group", "supergroup"):
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
        except ValueError:
            pass
    await db.register_user(message.from_user.id, referrer_id)
    if message.from_user.id == ADMIN_ID:
        admin_text = (
            "👑 <b>Панель администратора</b>\n\n"
            "<b>Управление блокировками:</b>\n"
            "• <code>/ban</code> — забанить (в ответ на сообщение)\n"
            "• <code>/unban КОД|ID</code> — разбанить пользователя\n"
            "• <code>/banlist</code> — список забаненных кодов\n\n"
            "<b>Достижения и Баланс:</b>\n"
            "• <code>/grant КОД|ID [ACH_ID]</code> — выдать достижение\n"
            "• <code>/grant_all КОД|ID</code> — выдать все достижения\n"
            "• <code>/achlist</code> — список всех ACH_ID достижений\n"
            "• <code>/addbalance КОД|ID СУММА</code> — пополнить баланс Stars\n\n"
            "<b>Финансы и Рассылка:</b>\n"
            "• <code>/refund КОД|ID|STX_ID</code> — возврат звёзд\n"
            "• <code>/broadcast</code> — рассылка сообщений пользователям"
        )
        await message.answer(admin_text, parse_mode=ParseMode.HTML)
        return
    if await db.is_banned(message.from_user.id):
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
        await message.answer(
            "❌ <b>Вы заблокированы в этом боте.</b>",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Мой статус / Баланс", callback_data="my_status"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Настройки профиля", callback_data="settings_menu"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Мои достижения", callback_data="my_achievements"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 Пополнить баланс Stars", callback_data="deposit_menu"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Приоритет (1 ⭐️)", callback_data="buy_priority"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 VIP-Оформление (100 ⭐️)", callback_data="buy_vip"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💨 Купить воздух (10 ⭐️)", callback_data="buy_air"
                )
            ],
        ]
    )
    await message.answer(
        "Привет! Напиши сюда сообщение, и я передам его анонимно.",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("status"))
@router.callback_query(F.data == "my_status")
async def show_status(event: types.Message | types.CallbackQuery) -> None:
    if event.from_user is None:
        return
    user_id = event.from_user.id
    user_stats = await db.register_user(user_id)
    banned = await db.is_banned(user_id)
    use_cats = user_stats.is_vip and user_stats.show_vip_cats
    cat_header = f" {random.choice(CAT_KAOMOJI_LIST).strip()}" if use_cats else ""
    cat_vip = f" {random.choice(CAT_KAOMOJI_LIST).strip()}" if use_cats else ""
    cat_air = f" {random.choice(CAT_KAOMOJI_LIST).strip()}" if use_cats else ""
    code_spoiler = f"<tg-spoiler><code>{user_stats.anon_code}</code></tg-spoiler>"
    status_text = "🚫 Заблокирован" if banned else "✅ Активен"
    vip_status = f"💎 VIP Подписчик{cat_vip}" if user_stats.is_vip else "❌ Нет"
    ach_count = await db.get_user_achievements_count(user_id)
    total_ach_count = len(db.ACHIEVEMENTS)

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
        ach_block += f"\n└ <b>Оценка:</b> <i>Ну и воздухан...{cat_air}</i>"

    if user_stats.is_vip:
        top_block = (
            f"✨ 👑 <b>VIP-ПРОФИЛЬ{cat_header}</b> 👑 ✨\n"
            "⚡️ <i>Премиум-статус активирован</i>"
        )
        finance_block = (
            "💰 <b>Финансы и Статус</b>\n"
            f"├ <b>Баланс:</b> <b>{user_stats.balance}</b> ⭐️\n"
            f"└ <b>VIP Поддержка:</b> {vip_status}"
        )
    else:
        top_block = "👤 <b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>\n─────────────────────"
        finance_block = (
            "💰 <b>Финансы</b>\n"
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

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚙️ Настройки профиля", callback_data="settings_menu"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Мои достижения", callback_data="my_achievements"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 Пополнить баланс Stars", callback_data="deposit_menu"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📲 Поделиться статусом", switch_inline_query=""
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Купить приоритет (1 ⭐️)", callback_data="buy_priority"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 VIP-Оформление (100 ⭐️)", callback_data="buy_vip"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💨 Купить воздух (10 ⭐️)", callback_data="buy_air"
                )
            ],
        ]
    )
    if isinstance(event, types.CallbackQuery):
        if isinstance(event.message, types.Message):
            await event.message.edit_text(
                text, reply_markup=kb, parse_mode=ParseMode.HTML
            )
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.message(Command("settings"))
@router.callback_query(F.data == "settings_menu")
async def show_settings_menu(event: types.Message | types.CallbackQuery) -> None:
    if event.from_user is None:
        return
    user_id = event.from_user.id
    user_stats = await db.get_user_stats(user_id)
    refresh_map = {
        "never": "Никогда",
        "8h": "Раз в 8 ч.",
        "daily": "Раз в 24 ч.",
        "weekly": "Раз в 7 дней",
    }
    refresh_str = refresh_map.get(user_stats.code_auto_refresh, "Никогда")
    cats_str = "Включены ✅" if user_stats.show_vip_cats else "Выключены ❌"
    code_spoiler = f"<tg-spoiler><code>{user_stats.anon_code}</code></tg-spoiler>"
    text = (
        "⚙️ <b>НАСТРОЙКИ ПРОФИЛЯ</b>\n"
        "─────────────────────\n\n"
        f"🔑 <b>Ваш анонимный код:</b> {code_spoiler}\n\n"
        f"• <b>Авто-обновление кода:</b> {refresh_str}\n"
        f"• <b>Кастомизация котиков (VIP):</b> {cats_str}\n\n"
        "<i>Выберите параметр для изменения ниже:</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить код вручную",
                    callback_data="settings_refresh_code",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"⏱ Авто-смена кода: {refresh_str}",
                    callback_data="settings_toggle_autorefresh",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🐱 Котики (VIP): {cats_str}",
                    callback_data="settings_toggle_cats",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📲 Настройки шеринга",
                    callback_data="settings_share_menu",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="my_status")],
        ]
    )
    if isinstance(event, types.CallbackQuery):
        if isinstance(event.message, types.Message):
            await event.message.edit_text(
                text, reply_markup=kb, parse_mode=ParseMode.HTML
            )
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "settings_refresh_code")
async def handle_refresh_code_manual(callback: types.CallbackQuery) -> None:
    if callback.from_user is None:
        return
    user_id = callback.from_user.id
    success, result = await db.regenerate_user_code(user_id)
    if success:
        await callback.answer(
            f"✅ Ваш код успешно обновлен на: {result}", show_alert=True
        )
        await show_settings_menu(callback)
    else:
        await callback.answer(f"❌ {result}", show_alert=True)


@router.callback_query(F.data == "settings_toggle_autorefresh")
async def handle_toggle_autorefresh(callback: types.CallbackQuery) -> None:
    if callback.from_user is None:
        return
    user_stats = await db.get_user_stats(callback.from_user.id)
    cycle = {"never": "8h", "8h": "daily", "daily": "weekly", "weekly": "never"}
    new_val = cycle.get(user_stats.code_auto_refresh, "never")
    await db.update_user_setting(callback.from_user.id, "code_auto_refresh", new_val)
    await callback.answer("⏱ Интервал авто-смены кода изменен.")
    await show_settings_menu(callback)


@router.callback_query(F.data == "settings_toggle_cats")
async def handle_toggle_cats(callback: types.CallbackQuery) -> None:
    if callback.from_user is None:
        return
    user_stats = await db.get_user_stats(callback.from_user.id)
    new_val = 0 if user_stats.show_vip_cats else 1
    await db.update_user_setting(callback.from_user.id, "show_vip_cats", new_val)
    status_text = "включены" if new_val == 1 else "выключены"
    await callback.answer(f"🐱 Котики в оформлении {status_text}.")
    await show_settings_menu(callback)


VIS_FIELD_MAP = {
    "sent": "show_sent",
    "received": "show_received",
    "priority": "show_priority",
    "air": "show_air",
    "achievements": "show_achievements",
}


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
    await db.update_user_setting(user_id, field_name, 0 if current_val else 1)
    return True


def get_share_preview_text(
    user_stats: db.UserStats, ach_count: int, total_ach: int
) -> str:
    use_cats = user_stats.is_vip and user_stats.show_vip_cats
    cat_inline = f" {random.choice(CAT_KAOMOJI_LIST).strip()}" if use_cats else ""
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


@router.message(Command("share_settings"))
@router.callback_query(F.data == "settings_share_menu")
async def show_share_settings_menu(event: types.Message | types.CallbackQuery) -> None:
    if event.from_user is None:
        return
    user_id = event.from_user.id
    user_stats = await db.get_user_stats(user_id)
    ach_count = await db.get_user_achievements_count(user_id)
    total_ach = len(db.ACHIEVEMENTS)
    preview_text = get_share_preview_text(user_stats, ach_count, total_ach)
    vis_sent = "✅" if user_stats.show_sent else "❌"
    vis_received = "✅" if user_stats.show_received else "❌"
    vis_priority = "✅" if user_stats.show_priority else "❌"
    vis_air = "✅" if user_stats.show_air else "❌"
    vis_ach = "✅" if user_stats.show_achievements else "❌"
    text = (
        "📲 <b>НАСТРОЙКИ ИНЛАЙН-ШЕРИНГА</b>\n"
        "─────────────────────\n"
        "🔒 <i>Конфиденциальность: Ваш анонимный код и Telegram ID <b>никогда не публикуются</b> при шеринге.</i>\n\n"
        "👁️ <b>Предпросмотр сообщения (как его увидят в чате):</b>\n\n"
        f"{preview_text}\n\n"
        "─────────────────────\n"
        "⚠️ <i>Хотя бы один параметр всегда должен быть включён.</i>\n"
        "<i>Отметьте, что показывать в карточке:</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✉️ Анонимки: {vis_sent}",
                    callback_data="toggle_share_vis_sent",
                ),
                InlineKeyboardButton(
                    text=f"💬 Ответы: {vis_received}",
                    callback_data="toggle_share_vis_received",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"⭐ Приоритеты: {vis_priority}",
                    callback_data="toggle_share_vis_priority",
                ),
                InlineKeyboardButton(
                    text=f"💨 Воздух: {vis_air}",
                    callback_data="toggle_share_vis_air",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"🏆 Достижения: {vis_ach}",
                    callback_data="toggle_share_vis_achievements",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚀 Проверить и поделиться в чате", switch_inline_query=""
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад в настройки", callback_data="settings_menu"
                )
            ],
        ]
    )
    if isinstance(event, types.CallbackQuery):
        if isinstance(event.message, types.Message):
            await event.message.edit_text(
                text, reply_markup=kb, parse_mode=ParseMode.HTML
            )
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("toggle_share_vis_"))
async def handle_toggle_share_visibility(callback: types.CallbackQuery) -> None:
    if callback.from_user is None or callback.data is None:
        return
    target = callback.data.replace("toggle_share_vis_", "")
    if target not in VIS_FIELD_MAP:
        await callback.answer("❌ Ошибка выбора параметра.", show_alert=True)
        return
    ok = await toggle_visibility_field(callback.from_user.id, VIS_FIELD_MAP[target])
    if not ok:
        await callback.answer(
            "❌ Нельзя скрыть все элементы! В карточке должен быть виден хотя бы один показатель.",
            show_alert=True,
        )
        return
    await callback.answer("✅ Видимость показателя изменена.")
    await show_share_settings_menu(callback)


@router.callback_query(F.data == "my_achievements")
async def show_achievements(callback: types.CallbackQuery) -> None:
    if callback.from_user is None:
        return
    user_id = callback.from_user.id
    unlocked_ids = await db.get_user_achievements(user_id)
    total_ach_count = len(db.ACHIEVEMENTS)
    if not unlocked_ids:
        text = "🏆 <b>Ваши достижения</b>\n\nУ вас пока нет открытых достижений."
    else:
        text = f"🏆 <b>Открытые достижения ({len(unlocked_ids)}/{total_ach_count}):</b>\n\n"
        for ach_id in unlocked_ids:
            ach = db.ACHIEVEMENTS.get(ach_id)
            if ach:
                text += f"{ach['icon']} <b>{ach['title']}</b>\n<i>{ach['description']}</i>\n\n"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в статус", callback_data="my_status")]
        ]
    )
    if isinstance(callback.message, types.Message):
        await callback.message.edit_text(
            text, reply_markup=kb, parse_mode=ParseMode.HTML
        )
    await callback.answer()


@router.message_reaction()
async def handle_reactions(reaction: types.MessageReactionUpdated, bot: Bot) -> None:
    msg_id = reaction.message_id
    chat_id = reaction.chat.id
    new_reaction = reaction.new_reaction
    if chat_id == ADMIN_ID:
        res = await db.get_sender_with_message_by_admin_msg(msg_id)
        if res:
            try:
                await bot.set_message_reaction(
                    chat_id=res.sender_id,
                    message_id=res.user_msg_id,
                    reaction=new_reaction,
                )
            except TelegramAPIError:
                logger.exception("Reaction error")
    else:
        admin_msg_id = await db.get_admin_msg_id_by_user_msg_id(chat_id, msg_id)
        if admin_msg_id:
            try:
                await bot.set_message_reaction(
                    chat_id=ADMIN_ID, message_id=admin_msg_id, reaction=new_reaction
                )
            except TelegramAPIError:
                logger.exception("Reaction error")


@router.inline_query()
async def inline_query_handler(
    inline_query: types.InlineQuery, bot_username: str
) -> None:
    user_id = inline_query.from_user.id
    user_stats = await db.register_user(user_id)
    results: list[InlineQueryResult] = []
    if user_id == ADMIN_ID:
        share_text = "✉️ <b>Задай мне анонимный вопрос!</b>\n\nНапиши всё, что думаешь — всё передастся анонимно!"
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
                input_message_content=InputTextMessageContent(
                    message_text=share_text, parse_mode=ParseMode.HTML
                ),
                reply_markup=kb,
            )
        )
    ach_count = await db.get_user_achievements_count(user_id)
    total_ach_count = len(db.ACHIEVEMENTS)
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
            input_message_content=InputTextMessageContent(
                message_text=stats_text, parse_mode=ParseMode.HTML
            ),
            reply_markup=kb,
        )
    )
    await inline_query.answer(cast(list, results), cache_time=1)


@router.callback_query(F.data.startswith("reply_"))
async def handle_reply_button(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.data is None or not isinstance(callback.message, types.Message):
        await callback.answer("Ошибка вызова кнопки.", show_alert=True)
        return
    sender_id = int(callback.data.split("_")[1])
    await state.update_data(reply_to_user_id=sender_id)
    await state.set_state(ReplyState.waiting_for_reply)
    await callback.message.answer("📝 Введите ответ:", parse_mode=ParseMode.HTML)
    await callback.answer()


@router.message(ReplyState.waiting_for_reply)
async def send_reply_to_user(
    message: types.Message, state: FSMContext, bot: Bot
) -> None:
    data = await state.get_data()
    sender_id = data.get("reply_to_user_id")
    await state.clear()
    if not sender_id:
        await message.answer(
            "❌ Ошибка: не удалось найти получателя.", parse_mode=ParseMode.HTML
        )
        return
    try:
        await bot.send_message(
            chat_id=sender_id,
            text="📩 <b>Вам пришёл ответ на анонимное сообщение:</b>",
            parse_mode=ParseMode.HTML,
        )
        await message.copy_to(chat_id=sender_id)
        await db.increment_received_count(sender_id)
        await db.increment_answer_streak(sender_id)
        await db.check_and_grant_achievements(sender_id, bot)
        await message.answer("✅ Ответ успешно отправлен!", parse_mode=ParseMode.HTML)
    except TelegramAPIError:
        logger.exception("Error sending reply to user %s", sender_id)
        await message.answer(
            "❌ Не удалось доставить ответ пользователю.", parse_mode=ParseMode.HTML
        )


@router.message(~F.text.startswith("/"))
async def forward_anonymous_msg(message: types.Message, bot: Bot) -> None:
    if message.chat.type != "private" or message.from_user is None:
        return
    if (
        message.refunded_payment
        or message.successful_payment
        or message.content_type
        in (
            types.ContentType.NEW_CHAT_MEMBERS,
            types.ContentType.LEFT_CHAT_MEMBER,
            types.ContentType.NEW_CHAT_TITLE,
            types.ContentType.NEW_CHAT_PHOTO,
            types.ContentType.DELETE_CHAT_PHOTO,
            types.ContentType.SUCCESSFUL_PAYMENT,
            types.ContentType.REFUNDED_PAYMENT,
        )
    ):
        return
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        return
    user_stats = await db.register_user(user_id)
    if await db.is_banned(user_id):
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
        await message.answer(
            "❌ Вы заблокированы в боте.", reply_markup=kb, parse_mode=ParseMode.HTML
        )
        return
    try:
        user_stats = await db.get_user_stats(user_id)
        is_priority = user_stats.priority_messages > 0
        if is_priority:
            await db.waste_priority_message(user_id)
            await db.increment_priority_sent_count(user_id)
        await db.increment_sent_count(user_id)
        msg_text = (message.text or message.caption or "").lower()
        if "42" in msg_text:
            await db.grant_achievement(user_id, "bro_42", bot)
        if "67" in msg_text:
            await db.grant_achievement(user_id, "degrade_67", bot)
        await db.check_and_grant_achievements(user_id, bot)
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
                "═════════════════════\n💎 <b>VIP-СООБЩЕНИЕ</b>\n═════════════════════"
            )
            await bot.send_message(
                chat_id=ADMIN_ID, text=vip_banner, parse_mode=ParseMode.HTML
            )
        if is_priority:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text="🌟 <b>[ПРИОРИТЕТНОЕ СООБЩЕНИЕ]</b>",
                parse_mode=ParseMode.HTML,
            )
        sent_msg = await message.copy_to(chat_id=ADMIN_ID, reply_markup=keyboard)
        await db.add_message(
            sent_msg.message_id,
            user_id,
            user_stats.anon_code,
            is_priority,
            message.message_id,
        )
        confirm_text = (
            "⭐ <b>Приоритетное сообщение отправлено!</b>"
            if is_priority
            else "🚀 Сообщение отправлено анонимно!"
        )
        await message.answer(confirm_text, parse_mode=ParseMode.HTML)
    except TelegramAPIError:
        logger.exception(f"Forward error from {user_id}")
        await message.answer("❌ Ошибка при отправке.", parse_mode=ParseMode.HTML)
