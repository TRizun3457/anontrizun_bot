import logging
from collections.abc import Sequence
from typing import final, cast
from aiogram import Router, types, Bot, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultArticle, InputTextMessageContent
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import database as db
from config import ADMIN_ID

router = Router()


@final
class ReplyState(StatesGroup):
    waiting_for_reply = State()


@router.message(Command("anon"))
async def anon_group_cmd(message: types.Message, bot: Bot) -> None:
    bot_info = await bot.get_me()
    username = bot_info.username or ""

    if message.chat.type in ("group", "supergroup"):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✉️ Написать анонимно", url=f"https://t.me/{username}?start=anon")]
        ])
        text = "✉️ <b>Анонимные сообщения</b>\n\nНажмите кнопку ниже, чтобы отправить анонимный вопрос!"
        _ = await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        _ = await message.answer("ℹ️ Команду <code>/anon</code> можно использовать в чатах и группах.", parse_mode=ParseMode.HTML)


@router.message(CommandStart())
async def start_cmd(message: types.Message, command: CommandObject) -> None:
    if message.chat.type != "private" or not message.from_user:
        return

    referrer_id: int | None = None
    if command.args and command.args.startswith("ref_"):
        try:
            referrer_id = int(command.args.split("ref_")[1])
        except ValueError:
            pass

    _ = await db.register_user(message.from_user.id, referrer_id)

    if message.from_user.id == ADMIN_ID:
        admin_text = (
            "👑 <b>Вы админ анонимного бота.</b>\n\n"
            + "• <code>/ban</code> — забанить (в ответ на сообщение)\n"
            + "• <code>/unban КОД</code> — разбанить\n"
            + "• <code>/banlist</code> — список забаненных\n"
            + "• <code>/refund USER_ID</code> — возврат звёзд"
        )
        _ = await message.answer(admin_text, parse_mode=ParseMode.HTML)
        return

    if await db.is_banned(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🙏 Попросить прощения (50 ⭐️)", callback_data="buy_apology")]
        ])
        _ = await message.answer("❌ <b>Вы заблокированы в этом боте.</b>", reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мой статус / Баланс", callback_data="my_status")],
        [InlineKeyboardButton(text="💳 Пополнить баланс Stars", callback_data="deposit_menu")],
        [InlineKeyboardButton(text="⭐ Приоритет (1 ⭐️)", callback_data="buy_priority")],
        [InlineKeyboardButton(text="💎 VIP-Оформление (100 ⭐️)", callback_data="buy_vip")],
        [InlineKeyboardButton(text="💨 Купить воздух (10 ⭐️)", callback_data="buy_air")]
    ])

    _ = await message.answer(
        "Привет! Напиши сюда сообщение, и я передам его анонимно.",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )


@router.message(Command("status"))
@router.callback_query(F.data == "my_status")
async def show_status(event: types.Message | types.CallbackQuery) -> None:
    if not event.from_user:
        return

    user_id = event.from_user.id
    anon_code = await db.register_user(user_id)

    banned = await db.is_banned(user_id)
    balance, air_count, priority_count, sent_count, received_count, is_vip, user_code = await db.get_user_stats(user_id)

    code_to_show = user_code if user_code else anon_code

    status_text = "🚫 Заблокирован" if banned else "✅ Активен"
    vip_status = "💎 VIP Подписчик" if is_vip else "❌ Нет"
    air_status = "\n• <b>Статус:</b> ну и воздухан..." if air_count > 0 else ""

    text = (
        f"👤 <b>Статус аккаунта</b>\n\n"
        f"• <b>Ваш код:</b> <code>{code_to_show}</code>\n"
        f"• <b>ID:</b> <code>{user_id}</code>\n"
        f"• <b>Баланс:</b> <b>{balance}</b> ⭐️\n"
        f"• <b>Состояние:</b> {status_text}\n"
        f"• <b>VIP Поддержка:</b> {vip_status}\n"
        f"• <b>Отправлено анонимок:</b> {sent_count}\n"
        f"• <b>Получено ответов:</b> {received_count}\n"
        f"• <b>Оплачено приоритетных ответов:</b> {priority_count}\n"
        f"• <b>Куплено воздуха:</b> {air_count} шт.{air_status}\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить баланс Stars", callback_data="deposit_menu")],
        [InlineKeyboardButton(text="📲 Поделиться статусом", switch_inline_query="")],
        [InlineKeyboardButton(text="⭐ Купить приоритет (1 ⭐️)", callback_data="buy_priority")],
        [InlineKeyboardButton(text="💎 VIP-Оформление (100 ⭐️)", callback_data="buy_vip")],
        [InlineKeyboardButton(text="💨 Купить воздух (10 ⭐️)", callback_data="buy_air")]
    ])

    if isinstance(event, types.CallbackQuery):
        if event.message:
            _ = await event.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        _ = await event.answer()
    else:
        _ = await event.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.message_reaction()
async def handle_reactions(reaction: types.MessageReactionUpdated, bot: Bot) -> None:
    if not db.db_pool:
        return

    msg_id = reaction.message_id
    chat_id = reaction.chat.id
    new_reaction = reaction.new_reaction

    if chat_id == ADMIN_ID:
        async with db.db_pool.execute("SELECT sender_id, user_msg_id FROM messages WHERE admin_msg_id = ?", (msg_id,)) as cursor:
            raw_row = await cursor.fetchone()

        if raw_row is not None:
            row_data = cast(Sequence[object], raw_row)
            sender_id_val = row_data[0]
            user_msg_id_val = row_data[1]

            if isinstance(sender_id_val, int) and isinstance(user_msg_id_val, int):
                try:
                    _ = await bot.set_message_reaction(
                        chat_id=sender_id_val,
                        message_id=user_msg_id_val,
                        reaction=new_reaction
                    )
                except Exception as e:
                    logging.error(f"Reaction error: {e}")
    else:
        async with db.db_pool.execute("SELECT admin_msg_id FROM messages WHERE sender_id = ? AND user_msg_id = ?", (chat_id, msg_id)) as cursor:
            raw_admin_row = await cursor.fetchone()

        if raw_admin_row is not None:
            admin_row_data = cast(Sequence[object], raw_admin_row)
            admin_msg_id_val = admin_row_data[0]

            if isinstance(admin_msg_id_val, int):
                try:
                    _ = await bot.set_message_reaction(
                        chat_id=ADMIN_ID,
                        message_id=admin_msg_id_val,
                        reaction=new_reaction
                    )
                except Exception as e:
                    logging.error(f"Reaction error: {e}")


@router.inline_query()
async def inline_query_handler(inline_query: types.InlineQuery, bot: Bot) -> None:
    user_id = inline_query.from_user.id
    _ = await db.register_user(user_id)

    results: list[types.InlineQueryResultUnion] = []

    bot_info = await bot.get_me()
    username = bot_info.username or ""

    if user_id == ADMIN_ID:
        share_text = "✉️ <b>Задай мне анонимный вопрос!</b>\n\nНапиши всё, что думаешь — всё передастся анонимно!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать анонимно", url=f"https://t.me/{username}?start=anon")]
        ])
        results.append(
            InlineQueryResultArticle(
                id="admin_share",
                title="🚀 Поделиться ссылкой на анонимки",
                input_message_content=InputTextMessageContent(message_text=share_text, parse_mode=ParseMode.HTML),
                reply_markup=kb
            )
        )
    else:
        _, air_count, priority_count, _, _, _, _ = await db.get_user_stats(user_id)
        stats_text = f"📊 <b>Моя статистика:</b>\n\n💨 Воздуха: <b>{air_count}</b>\n⭐ Приоритетов: <b>{priority_count}</b>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✉️ Написать анонимно", url=f"https://t.me/{username}?start=share")]
        ])
        results.append(
            InlineQueryResultArticle(
                id="user_status_share",
                title="📊 Поделиться статусом",
                input_message_content=InputTextMessageContent(message_text=stats_text, parse_mode=ParseMode.HTML),
                reply_markup=kb
            )
        )

    _ = await inline_query.answer(results, cache_time=1)


@router.callback_query(F.data.startswith("reply_"))
async def handle_reply_button(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not callback.data or not callback.message:
        return
    sender_id = int(callback.data.split("_")[1])
    _ = await state.update_data(reply_to_user_id=sender_id)
    _ = await state.set_state(ReplyState.waiting_for_reply)
    _ = await callback.message.answer("📝 Введите ответ:", parse_mode=ParseMode.HTML)
    _ = await callback.answer()


@router.message(ReplyState.waiting_for_reply)
async def send_reply_to_user(message: types.Message, state: FSMContext, bot: Bot) -> None:
    if not db.db_pool:
        return

    data = await state.get_data()
    raw_sender_id = data.get("reply_to_user_id")
    _ = await state.clear()

    if not raw_sender_id or not isinstance(raw_sender_id, int):
        return

    sender_id: int = raw_sender_id

    try:
        _ = await bot.send_message(chat_id=sender_id, text="💬 <b>Ответ от владельца:</b>", parse_mode=ParseMode.HTML)
        sent_reply = await message.copy_to(chat_id=sender_id)

        _ = await db.db_pool.execute("UPDATE users SET received_count = received_count + 1 WHERE user_id = ?", (sender_id,))
        anon_code = await db.register_user(sender_id)

        _ = await db.db_pool.execute(
            "INSERT INTO messages (admin_msg_id, sender_id, anon_code, is_priority, user_msg_id) VALUES (?, ?, ?, 0, ?)",
            (message.message_id, sender_id, anon_code, sent_reply.message_id)
        )
        await db.db_pool.commit()
        _ = await message.answer("🚀 Ответ успешно отправлен!", parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Reply error: {e}")
        _ = await message.answer("❌ Не удалось отправить ответ.", parse_mode=ParseMode.HTML)


@router.message()
async def forward_anonymous_msg(message: types.Message, bot: Bot) -> None:
    if message.chat.type != "private" or not message.from_user or not db.db_pool:
        return

    if message.refunded_payment or message.successful_payment or message.content_type in (
        types.ContentType.NEW_CHAT_MEMBERS,
        types.ContentType.LEFT_CHAT_MEMBER,
        types.ContentType.NEW_CHAT_TITLE,
        types.ContentType.NEW_CHAT_PHOTO,
        types.ContentType.DELETE_CHAT_PHOTO,
        types.ContentType.SUCCESSFUL_PAYMENT,
        types.ContentType.REFUNDED_PAYMENT
    ):
        return

    user_id = message.from_user.id
    anon_code = await db.register_user(user_id)

    if user_id == ADMIN_ID:
        return

    if await db.is_banned(user_id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🙏 Попросить прощения (50 ⭐️)", callback_data="buy_apology")]
        ])
        _ = await message.answer("❌ Вы заблокированы в боте.", reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    try:
        _, _, priority_count, _, _, is_vip, _ = await db.get_user_stats(user_id)
        is_priority = 1 if priority_count > 0 else 0

        if is_priority:
            _ = await db.db_pool.execute(
                "UPDATE users SET priority_messages = priority_messages - 1 WHERE user_id = ?",
                (user_id,)
            )

        _ = await db.db_pool.execute(
            "UPDATE users SET sent_count = sent_count + 1 WHERE user_id = ?",
            (user_id,)
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Ответить", callback_data=f"reply_{user_id}")]
        ])

        if is_vip:
            vip_banner = "═════════════════════\n💎 <b>VIP-СООБЩЕНИЕ</b>\n═════════════════════"
            _ = await bot.send_message(chat_id=ADMIN_ID, text=vip_banner, parse_mode=ParseMode.HTML)

        if is_priority:
            _ = await bot.send_message(chat_id=ADMIN_ID, text="🌟 <b>[ПРИОРИТЕТНОЕ СООБЩЕНИЕ]</b>", parse_mode=ParseMode.HTML)

        sent_msg = await message.copy_to(chat_id=ADMIN_ID, reply_markup=keyboard)

        _ = await db.db_pool.execute(
            "INSERT INTO messages (admin_msg_id, sender_id, anon_code, is_priority, user_msg_id) VALUES (?, ?, ?, ?, ?)",
            (sent_msg.message_id, user_id, anon_code, is_priority, message.message_id)
        )
        await db.db_pool.commit()

        confirm_text = "⭐ <b>Приоритетное сообщение отправлено!</b>" if is_priority else "🚀 Сообщение отправлено анонимно!"
        _ = await message.answer(confirm_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logging.error(f"Forward error from {user_id}: {e}")
        _ = await message.answer("❌ Ошибка при отправке.", parse_mode=ParseMode.HTML)
