import logging
from aiogram import Router, types, Bot, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultArticle, InputTextMessageContent
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import database as db
from config import ADMIN_ID, BOT_USERNAME

router = Router()

class ReplyState(StatesGroup):
    waiting_for_reply = State()

@router.message(Command("anon"))
async def anon_group_cmd(message: types.Message):
    if message.chat.type in ("group", "supergroup"):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✉️ Написать анонимно", url=f"https://t.me/{BOT_USERNAME}?start=anon")]
        ])
        text = "✉️ <b>Анонимные сообщения</b>\n\nНажмите кнопку ниже, чтобы отправить анонимный вопрос!"
        await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await message.answer("ℹ️ Команду <code>/anon</code> можно использовать в чатах и группах.", parse_mode=ParseMode.HTML)

@router.message(CommandStart())
async def start_cmd(message: types.Message, command: CommandObject):
    if message.chat.type != "private":
        return

    referrer_id = None
    if command.args and command.args.startswith("ref_"):
        try:
            referrer_id = int(command.args.split("ref_")[1])
        except ValueError:
            pass

    await db.register_user(message.from_user.id, referrer_id)
    
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "👑 <b>Вы админ анонимного бота.</b>\n\n"
            "• <code>/ban</code> — забанить (в ответ на сообщение)\n"
            "• <code>/unban КОД</code> — разбанить\n"
            "• <code>/banlist</code> — список забаненных\n"
            "• <code>/refund USER_ID</code> — возврат звёзд",
            parse_mode=ParseMode.HTML
        )
        return
    
    if await db.is_banned(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🙏 Попросить прощения (50 ⭐️)", callback_data="buy_apology")]
        ])
        await message.answer("❌ <b>Вы заблокированы в этом боте.</b>", reply_markup=kb, parse_mode=ParseMode.HTML)
        return
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мой статус / Баланс", callback_data="my_status")],
        [InlineKeyboardButton(text="💳 Пополнить баланс Stars", callback_data="deposit_menu")],
        [InlineKeyboardButton(text="⭐ Приоритет (1 ⭐️)", callback_data="buy_priority")],
        [InlineKeyboardButton(text="💎 VIP-Оформление (100 ⭐️)", callback_data="buy_vip")],
        [InlineKeyboardButton(text="💨 Купить воздух (10 ⭐️)", callback_data="buy_air")]
    ])
    
    await message.answer(
        "Привет! Напиши сюда сообщение, и я передам его анонимно.",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )

@router.message(Command("status"))
@router.callback_query(F.data == "my_status")
async def show_status(event: types.Message | types.CallbackQuery):
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
        await event.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)

@router.message_reaction()
async def handle_reactions(reaction: types.MessageReactionUpdated, bot: Bot):
    msg_id = reaction.message_id
    chat_id = reaction.chat.id
    new_reaction = reaction.new_reaction

    if chat_id == ADMIN_ID:
        async with db.db_pool.execute("SELECT sender_id, user_msg_id FROM messages WHERE admin_msg_id = ?", (msg_id,)) as cursor:
            res = await cursor.fetchone()
        if res and res[1]:
            try:
                await bot.set_message_reaction(chat_id=res[0], message_id=res[1], reaction=new_reaction)
            except Exception as e:
                logging.error(f"Reaction error: {e}")
    else:
        async with db.db_pool.execute("SELECT admin_msg_id FROM messages WHERE sender_id = ? AND user_msg_id = ?", (chat_id, msg_id)) as cursor:
            res = await cursor.fetchone()
        if res:
            try:
                await bot.set_message_reaction(chat_id=ADMIN_ID, message_id=res[0], reaction=new_reaction)
            except Exception as e:
                logging.error(f"Reaction error: {e}")

@router.inline_query()
async def inline_query_handler(inline_query: types.InlineQuery):
    user_id = inline_query.from_user.id
    await db.register_user(user_id)
    results = []

    if user_id == ADMIN_ID:
        share_text = "✉️ <b>Задай мне анонимный вопрос!</b>\n\nНапиши всё, что думаешь — всё передастся анонимно!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать анонимно", url=f"https://t.me/{BOT_USERNAME}?start=anon")]
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
            [InlineKeyboardButton(text="✉️ Написать анонимно", url=f"https://t.me/{BOT_USERNAME}?start=share")]
        ])
        results.append(
            InlineQueryResultArticle(
                id="user_status_share",
                title="📊 Поделиться статусом",
                input_message_content=InputTextMessageContent(message_text=stats_text, parse_mode=ParseMode.HTML),
                reply_markup=kb
            )
        )

    await inline_query.answer(results, cache_time=1)

@router.callback_query(F.data.startswith("reply_"))
async def handle_reply_button(callback: types.CallbackQuery, state: FSMContext):
    sender_id = int(callback.data.split("_")[1])
    await state.update_data(reply_to_user_id=sender_id)
    await state.set_state(ReplyState.waiting_for_reply)
    await callback.message.answer("📝 Введите ответ:", parse_mode=ParseMode.HTML)
    await callback.answer()

@router.message(ReplyState.waiting_for_reply)
async def send_reply_to_user(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    sender_id = data.get("reply_to_user_id")
    await state.clear()
    
    try:
        await bot.send_message(chat_id=sender_id, text="💬 <b>Ответ от владельца:</b>", parse_mode=ParseMode.HTML)
        sent_reply = await message.copy_to(chat_id=sender_id)
        
        await db.db_pool.execute("UPDATE users SET received_count = received_count + 1 WHERE user_id = ?", (sender_id,))
        anon_code = await db.register_user(sender_id)

        await db.db_pool.execute(
            "INSERT INTO messages (admin_msg_id, sender_id, anon_code, is_priority, user_msg_id) VALUES (?, ?, ?, 0, ?)",
            (message.message_id, sender_id, anon_code, sent_reply.message_id)
        )
        await db.db_pool.commit()
        await message.answer("🚀 Ответ успешно отправлен!", parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Reply error: {e}")
        await message.answer("❌ Не удалось отправить ответ.", parse_mode=ParseMode.HTML)

@router.message()
async def forward_anonymous_msg(message: types.Message, bot: Bot):
    if message.chat.type != "private":
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
        await message.answer("❌ Вы заблокированы в боте.", reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    try:
        _, _, priority_count, _, _, is_vip, _ = await db.get_user_stats(user_id)
        is_priority = 1 if priority_count > 0 else 0

        if is_priority:
            await db.db_pool.execute("UPDATE users SET priority_messages = priority_messages - 1 WHERE user_id = ?", (user_id,))

        await db.db_pool.execute("UPDATE users SET sent_count = sent_count + 1 WHERE user_id = ?", (user_id,))

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Ответить", callback_data=f"reply_{user_id}")]
        ])
        
        if is_vip:
            vip_banner = "═════════════════════\n💎 <b>VIP-СООБЩЕНИЕ</b>\n═════════════════════"
            await bot.send_message(chat_id=ADMIN_ID, text=vip_banner, parse_mode=ParseMode.HTML)

        if is_priority:
            await bot.send_message(chat_id=ADMIN_ID, text="🌟 <b>[ПРИОРИТЕТНОЕ СООБЩЕНИЕ]</b>", parse_mode=ParseMode.HTML)

        sent_msg = await message.copy_to(chat_id=ADMIN_ID, reply_markup=keyboard)
        
        await db.db_pool.execute(
            "INSERT INTO messages (admin_msg_id, sender_id, anon_code, is_priority, user_msg_id) VALUES (?, ?, ?, ?, ?)",
            (sent_msg.message_id, user_id, anon_code, is_priority, message.message_id)
        )
        await db.db_pool.commit()
        
        confirm_text = "⭐ <b>Приоритетное сообщение отправлено!</b>" if is_priority else "🚀 Сообщение отправлено анонимно!"
        await message.answer(confirm_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logging.error(f"Forward error from {user_id}: {e}")
        await message.answer("❌ Ошибка при отправке.", parse_mode=ParseMode.HTML)