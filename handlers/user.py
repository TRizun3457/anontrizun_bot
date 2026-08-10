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
    "( =ω= )",
    "(ฅ^•ﻌ•^ฅ)",
    "(=^･ω･^=)",
    "(✿^ω^)",
    "(≡^∇^≡)",
    "(=^-ω-^=)",
    "(๑ↀᴥↀ๑)",
    "(ฅ'ω'ฅ)",
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
    cat_header = random.choice(CAT_KAOMOJI_LIST) if use_cats else ""
    cat_vip = random.choice(CAT_KAOMOJI_LIST) if use_cats else ""
    cat_air = random.choice(CAT_KAOMOJI_LIST) if use_cats else ""

    code_to_show = user_stats.anon_code
    status_text = "🚫 Заблокирован" if banned else "✅ Активен"
    vip_status = (
        f"💎 VIP Подписчик {cat_vip}".strip() if user_stats.is_vip else "❌ Нет"
    )

    ach_count = await db.get_user_achievements_count(user_id)
    total_ach_count = len(db.ACHIEVEMENTS)

    air_badge = (
        f"\n└ <b>Оценка:</b> <i>Ну и воздухан... {cat_air}</i>".strip()
        if user_stats.air_purchased > 0
        else ""
    )

    if user_stats.is_vip:
        header = f"✨ 👑 <b>VIP-ПРОФИЛЬ {cat_header}</b> ✨".strip()
        text = (
            f"{header}\n"
            f"⚡ <i>Премиум-статус активирован</i>\n\n"
            f"🆔 <b>Идентификация</b>\n"
            f"├ <b>Ваш код:</b> <code>{code_to_show}</code>\n"
            f"├ <b>ID:</b> <code>{user_id}</code>\n"
            f"└ <b>Состояние:</b> {status_text}\n\n"
            f"💰 <b>Финансы и Статус</b>\n"
            f"├ <b>Баланс:</b> <b>{user_stats.balance}</b> ⭐️\n"
            f"└ <b>VIP Поддержка:</b> {vip_status}\n\n"
            f"📈 <b>Статистика сообщений</b>\n"
            f"├ <b>Отправлено анонимок:</b> <code>{user_stats.sent_count}</code> ✉️\n"
            f"├ <b>Получено ответов:</b> <code>{user_stats.received_count}</code> 💬\n"
            f"└ <b>Оплачено приоритетных:</b> <code>{user_stats.priority_messages}</code> ⭐\n\n"
            f"🏆 <b>Достижения и Статусы</b>\n"
            f"├ <b>Достижений:</b> <code>{ach_count}/{total_ach_count}</code> 🎖️\n"
            f"└ <b>Куплено воздуха:</b> <code>{user_stats.air_purchased}</code> шт. 💨{air_badge}"
        )
    else:
        text = (
            f"👤 <b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>\n"
            f"─────────────────────\n\n"
            f"🆔 <b>Идентификация</b>\n"
            f"├ <b>Ваш код:</b> <code>{code_to_show}</code>\n"
            f"├ <b>ID:</b> <code>{user_id}</code>\n"
            f"└ <b>Состояние:</b> {status_text}\n\n"
            f"💰 <b>Финансы</b>\n"
            f"├ <b>Баланс:</b> <b>{user_stats.balance}</b> ⭐️\n"
            f"└ <b>VIP Поддержка:</b> {vip_status}\n\n"
            f"📈 <b>Статистика сообщений</b>\n"
            f"├ <b>Отправлено анонимок:</b> <code>{user_stats.sent_count}</code> ✉️\n"
            f"├ <b>Получено ответов:</b> <code>{user_stats.received_count}</code> 💬\n"
            f"└ <b>Оплачено приоритетных:</b> <code>{user_stats.priority_messages}</code> ⭐\n\n"
            f"🏆 <b>Достижения и Статусы</b>\n"
            f"├ <b>Достижений:</b> <code>{ach_count}/{total_ach_count}</code> 🎖️\n"
            f"└ <b>Куплено воздуха:</b> <code>{user_stats.air_purchased}</code> шт. 💨{air_badge}"
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
        "daily": "Раз в 24 ч.",
        "weekly": "Раз в 7 дней",
    }
    share_map = {
        "full": "Полная информация",
        "code_only": "Только код",
        "stats_only": "Только статистика",
    }

    refresh_str = refresh_map.get(user_stats.code_auto_refresh, "Никогда")
    share_str = share_map.get(user_stats.inline_share_mode, "Полная информация")
    cats_str = "Включены ✅" if user_stats.show_vip_cats else "Выключены ❌"

    text = (
        f"⚙️ <b>НАСТРОЙКИ ПРОФИЛЯ</b>\n"
        f"─────────────────────\n\n"
        f"🔑 <b>Ваш анонимный код:</b> <code>{user_stats.anon_code}</code>\n\n"
        f"• <b>Авто-обновление кода:</b> {refresh_str}\n"
        f"• <b>Кастомизация котиков (VIP):</b> {cats_str}\n"
        f"• <b>Режим шеринга в чатах:</b> {share_str}\n\n"
        f"<i>Выберите параметр для изменения ниже:</i>"
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
                    text=f"📲 Инлайн шеринг: {share_str}",
                    callback_data="settings_toggle_share",
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
    cycle = {"never": "daily", "daily": "weekly", "weekly": "never"}
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


@router.callback_query(F.data == "settings_toggle_share")
async def handle_toggle_share(callback: types.CallbackQuery) -> None:
    if callback.from_user is None:
        return

    user_stats = await db.get_user_stats(callback.from_user.id)
    cycle = {"full": "code_only", "code_only": "stats_only", "stats_only": "full"}
    new_val = cycle.get(user_stats.inline_share_mode, "full")

    await db.update_user_setting(callback.from_user.id, "inline_share_mode", new_val)
    await callback.answer("📲 Вид отображения при шеринге изменен.")
    await show_settings_menu(callback)


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

    use_cats = user_stats.is_vip and user_stats.show_vip_cats
    cat_inline = random.choice(CAT_KAOMOJI_LIST) if use_cats else ""

    share_mode = user_stats.inline_share_mode

    if share_mode == "code_only":
        stats_text = (
            f"🔑 <b>Мой анонимный код:</b> <code>{user_stats.anon_code}</code>\n"
            f"✉️ Напиши мне анонимное сообщение в боте!"
        )
        share_title = "🔑 Поделиться только кодом"
    elif share_mode == "stats_only":
        stats_text = (
            f"📊 <b>Моя статистика:</b>\n"
            f"💨 Воздуха: <b>{user_stats.air_purchased}</b>\n"
            f"⭐ Приоритетов: <b>{user_stats.priority_messages}</b>\n"
            f"🏆 Достижений: <b>{ach_count}/{total_ach_count}</b>"
        )
        share_title = "📊 Поделиться статистикой"
    else:
        if user_stats.is_vip:
            header_vip = f"✨ 👑 <b>VIP-ПРОФИЛЬ {cat_inline}</b> ✨".strip()
            stats_text = (
                f"{header_vip}\n"
                f"🔑 <b>Код:</b> <code>{user_stats.anon_code}</code>\n"
                f"💎 <b>Статус:</b> VIP Подписчик\n\n"
                f"📊 <b>Статистика:</b>\n"
                f"💨 <b>Воздуха:</b> <b>{user_stats.air_purchased}</b>\n"
                f"⭐ <b>Приоритетов:</b> <b>{user_stats.priority_messages}</b>\n"
                f"🏆 <b>Достижений:</b> <b>{ach_count}/{total_ach_count}</b>"
            )
            share_title = f"👑 Поделиться VIP статусом {cat_inline}".strip()
        else:
            stats_text = (
                f"👤 <b>Профиль анонима:</b>\n"
                f"🔑 <b>Код:</b> <code>{user_stats.anon_code}</code>\n\n"
                f"📊 <b>Статистика:</b>\n"
                f"💨 Воздуха: <b>{user_stats.air_purchased}</b>\n"
                f"⭐ Приоритетов: <b>{user_stats.priority_messages}</b>\n"
                f"🏆 Достижений: <b>{ach_count}/{total_ach_count}</b>"
            )
            share_title = "📊 Поделиться статусом"

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

        # Trigger words check
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
