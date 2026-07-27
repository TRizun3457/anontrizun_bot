import logging
from typing import cast

import aiosqlite
from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

import database as db
from config import ADMIN_ID

router = Router()
logger = logging.getLogger(__name__)


class ReplyState(StatesGroup):
    waiting_for_reply = State()


@router.message(Command("anon"))
async def anon_group_cmd(message: types.Message, bot_username: str):
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
async def start_cmd(message: types.Message, command: CommandObject):
    if message.from_user is None:
        raise RuntimeError("event.from_user is None")

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
            parse_mode=ParseMode.HTML,
        )
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
async def show_status(event: types.Message | types.CallbackQuery):
    if event.from_user is None:
        raise RuntimeError("event.from_user is None")

    user_id = event.from_user.id
    user_stats = await db.register_user(user_id)

    banned = await db.is_banned(user_id)

    code_to_show = user_stats.anon_code

    status_text = "🚫 Заблокирован" if banned else "✅ Активен"
    vip_status = "💎 VIP Подписчик" if user_stats.is_vip else "❌ Нет"
    air_status = (
        "\n• <b>Статус:</b> ну и воздухан..." if user_stats.air_purchased > 0 else ""
    )

    text = (
        f"👤 <b>Статус аккаунта</b>\n\n"
        f"• <b>Ваш код:</b> <code>{code_to_show}</code>\n"
        f"• <b>ID:</b> <code>{user_id}</code>\n"
        f"• <b>Баланс:</b> <b>{user_stats.balance}</b> ⭐️\n"
        f"• <b>Состояние:</b> {status_text}\n"
        f"• <b>VIP Поддержка:</b> {vip_status}\n"
        f"• <b>Отправлено анонимок:</b> {user_stats.sent_count}\n"
        f"• <b>Получено ответов:</b> {user_stats.received_count}\n"
        f"• <b>Оплачено приоритетных ответов:</b> {user_stats.priority_messages}\n"
        f"• <b>Куплено воздуха:</b> {user_stats.air_purchased} шт.{air_status}\n"
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
        msg_id = await db.get_admin_msg_id_by_user_msg_id(chat_id, msg_id)
        if msg_id:
            try:
                await bot.set_message_reaction(
                    chat_id=ADMIN_ID, message_id=msg_id, reaction=new_reaction
                )
            except TelegramAPIError:
                logger.exception("Reaction error")


@router.inline_query()
async def inline_query_handler(inline_query: types.InlineQuery, bot_username: str):
    user_id = inline_query.from_user.id
    user_stats = await db.register_user(user_id)
    results = []

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
    else:
        stats_text = f"📊 <b>Моя статистика:</b>\n\n💨 Воздуха: <b>{user_stats.air_purchased}</b>\n⭐ Приоритетов: <b>{user_stats.priority_messages}</b>"
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
                title="📊 Поделиться статусом",
                input_message_content=InputTextMessageContent(
                    message_text=stats_text, parse_mode=ParseMode.HTML
                ),
                reply_markup=kb,
            )
        )

    await inline_query.answer(results, cache_time=1)  # ty:ignore[invalid-argument-type]


@router.callback_query(F.data.startswith("reply_"))
async def handle_reply_button(callback: types.CallbackQuery, state: FSMContext):
    if callback.data is None:
        raise RuntimeError("callback.data is None")

    if not isinstance(callback.message, types.Message):
        raise TypeError("callback.message is not Message")

    sender_id = int(callback.data.split("_")[1])
    await state.update_data(reply_to_user_id=sender_id)
    await state.set_state(ReplyState.waiting_for_reply)
    await callback.message.answer("📝 Введите ответ:", parse_mode=ParseMode.HTML)
    await callback.answer()


@router.message(ReplyState.waiting_for_reply)
async def send_reply_to_user(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    sender_id = data.get("reply_to_user_id")

    if not isinstance(sender_id, int):
        msg = f"reply_to_user_id in state is {type(sender_id)}, expected int"
        raise TypeError(msg)

    sender_id = cast(int, sender_id)

    await state.clear()

    try:
        await bot.send_message(
            chat_id=sender_id,
            text="💬 <b>Ответ от владельца:</b>",
            parse_mode=ParseMode.HTML,
        )
        sent_reply = await message.copy_to(chat_id=sender_id)

        await db.increment_received_count(sender_id)
        user_stats = await db.register_user(sender_id)

        await db.add_message(
            message.message_id,
            sender_id,
            user_stats.anon_code,
            False,
            sent_reply.message_id,
        )
        await message.answer("🚀 Ответ успешно отправлен!", parse_mode=ParseMode.HTML)
    except TelegramAPIError:
        logger.exception("Reply error")
        await message.answer(
            "❌ Не удалось отправить ответ.", parse_mode=ParseMode.HTML
        )
    except aiosqlite.Error:
        logger.exception("database error")


@router.message()
async def forward_anonymous_msg(message: types.Message, bot: Bot):
    if message.chat.type != "private":
        return
    if message.from_user is None:
        raise RuntimeError("message.from_user is None")

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
    user_stats = await db.register_user(user_id)

    if user_id == ADMIN_ID:
        return

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

        await db.increment_sent_count(user_id)

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
