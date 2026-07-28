import logging

from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from config import ADMIN_ID

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("banlist"))
async def list_banned_codes(message: types.Message) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return

    banned_users = await db.get_banned_users()

    if len(banned_users) == 0:
        await message.answer(
            "🚫 Список забаненных пользователей пуст.", parse_mode=ParseMode.HTML
        )
        return

    text = "🚫 <b>Список забаненных кодов:</b>\n\n"
    for banned_user in banned_users:
        text += f"• Код: <code>{banned_user.anon_code}</code> (ID: <code>{banned_user.user_id}</code>)\n"

    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("ban"))
async def ban_by_reply(message: types.Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return

    if not message.reply_to_message:
        await message.answer(
            "⚠️ Чтобы забанить, ответьте командой <code>/ban</code> на сообщение.",
            parse_mode=ParseMode.HTML,
        )
        return

    admin_msg_id = message.reply_to_message.message_id

    sender_with_code = await db.get_sender_with_code_by_admin_msg(admin_msg_id)

    if sender_with_code:
        await db.ban_user(sender_with_code.sender_id, sender_with_code.anon_code)

        try:
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
            await bot.send_message(
                chat_id=sender_with_code.sender_id,
                text="❌ <b>Вы были заблокированы администратором.</b>\n\nВы можете подать заявку на разбан за 50 ⭐️.",
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
            notify_status = "Оповещение доставлено."
        except TelegramAPIError:
            notify_status = "Не удалось доставить оповещение."
            logger.exception("error while sending ban message to user")

        await message.answer(
            f"🚫 Пользователь (ID: <code>{sender_with_code.sender_id}</code>) заблокирован!\nКод: <code>{sender_with_code.anon_code}</code>\n<i>{notify_status}</i>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(
            "❌ Не удалось найти автора этого сообщения в базе.",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("unban"))
async def unban_by_code(message: types.Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return

    command_args = message.text.split(maxsplit=1)
    if len(command_args) < 2:
        await message.answer(
            "⚠️ Пример: <code>/unban XXXXXX</code>", parse_mode=ParseMode.HTML
        )
        return

    anon_code = command_args[1].strip()

    user_id = await db.get_banned_user_id_by_anon_code(anon_code)

    if user_id:
        await db.unban_user(user_id)

        try:
            await bot.send_message(
                chat_id=user_id,
                text="✅ <b>Вы были разблокированы!</b>",
                parse_mode=ParseMode.HTML,
            )
        except TelegramAPIError:
            logger.exception("error while sending unblocked message to user")

        await message.answer(
            f"✅ Пользователь с кодом <code>{anon_code}</code> успешно разбанен.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(
            "❌ Пользователь с таким кодом не найден.", parse_mode=ParseMode.HTML
        )


@router.callback_query(F.data.startswith("accept_unban_"))
async def accept_unban_handler(callback: types.CallbackQuery, bot: Bot) -> None:
    if not callback.data or not isinstance(callback.message, types.Message):
        return

    anon_code = callback.data.split("accept_unban_")[1]

    user_id = await db.get_banned_user_id_by_anon_code(anon_code)

    if user_id:
        await db.unban_user(user_id)

        try:
            await bot.send_message(
                chat_id=user_id,
                text="✅ <b>Ваша заявка одобрена! Вы успешно разбанены.</b>",
                parse_mode=ParseMode.HTML,
            )
        except TelegramAPIError:
            logger.exception(
                "error while sending unban application accept message to user"
            )

        current_text = callback.message.text or ""
        await callback.message.edit_text(
            current_text + "\n\n<b>Статус: РАЗБАНЕН ✅</b>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await callback.answer("Пользователь уже разбанен.", show_alert=True)


@router.callback_query(F.data.startswith("decline_unban_"))
async def decline_unban_handler(callback: types.CallbackQuery, bot: Bot) -> None:
    if not callback.data or not isinstance(callback.message, types.Message):
        return

    user_id = int(callback.data.split("decline_unban_")[1])
    try:
        await bot.send_message(
            chat_id=user_id,
            text="❌ <b>Ваша заявка на разбан отклонена.</b>",
            parse_mode=ParseMode.HTML,
        )
    except TelegramAPIError:
        logger.exception("error while sending unban application deny message to user")

    current_text = callback.message.text or ""
    await callback.message.edit_text(
        current_text + "\n\n<b>Статус: ОТКЛОНЕНО ❌</b>",
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.message(Command("achlist", "achievements"))
async def list_achievements_cmd(message: types.Message) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return

    text = "🏆 <b>Список всех доступных достижений (ACH_ID):</b>\n\n"
    for ach_id, data in db.ACHIEVEMENTS.items():
        text += f"{data['icon']} <b>{data['title']}</b>\n• ACH_ID: <code>{ach_id}</code>\n• Описание: <i>{data['description']}</i>\n\n"

    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("grant"))
async def grant_achievement_cmd(message: types.Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        ach_list = "\n".join(
            [f"• <code>{k}</code> — {v['title']}" for k, v in db.ACHIEVEMENTS.items()]
        )
        await message.answer(
            f"⚠️ Пример: <code>/grant КОД|USER_ID [ACH_ID]</code>\n\n"
            f"<b>Доступные ACH_ID:</b>\n{ach_list}",
            parse_mode=ParseMode.HTML,
        )
        return

    target_user_id = await db.get_user_id_by_id_or_code(args[1])
    if not target_user_id:
        await message.answer(
            "❌ Пользователь с таким ID или анонимным кодом не найден.",
            parse_mode=ParseMode.HTML,
        )
        return

    ach_id = args[2].strip() if len(args) > 2 else "impossible"

    if ach_id not in db.ACHIEVEMENTS:
        ach_list = "\n".join(
            [f"• <code>{k}</code> — {v['title']}" for k, v in db.ACHIEVEMENTS.items()]
        )
        await message.answer(
            f"❌ Достижение <code>{ach_id}</code> не найдено.\n\n"
            f"<b>Список доступных ACH_ID:</b>\n{ach_list}",
            parse_mode=ParseMode.HTML,
        )
        return

    granted = await db.grant_achievement(target_user_id, ach_id, bot)
    if granted:
        await message.answer(
            f"✅ Достижение <b>{db.ACHIEVEMENTS[ach_id]['title']}</b> (<code>{ach_id}</code>) успешно выдано пользователю <code>{target_user_id}</code>!",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(
            f"⚠️ У пользователя <code>{target_user_id}</code> уже есть это достижение или произошла ошибка.",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("grant_all"))
async def grant_all_achievements_cmd(message: types.Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "⚠️ Пример: <code>/grant_all КОД|USER_ID</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    target_user_id = await db.get_user_id_by_id_or_code(args[1].strip())
    if not target_user_id:
        await message.answer(
            "❌ Пользователь с таким ID или анонимным кодом не найден.",
            parse_mode=ParseMode.HTML,
        )
        return

    added_count = await db.grant_all_achievements(target_user_id, bot)
    total_count = len(db.ACHIEVEMENTS)
    await message.answer(
        f"✅ Выданы все достижения пользователю <code>{target_user_id}</code>!\n"
        f"Разблокировано новых: <b>{added_count}</b> / Всего в базе: <b>{total_count}</b>.",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("addbalance"))
async def add_balance_cmd(message: types.Message) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "⚠️ Пример: <code>/addbalance КОД|USER_ID СУММА</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    target_user_id = await db.get_user_id_by_id_or_code(args[1].strip())
    if not target_user_id:
        await message.answer(
            "❌ Пользователь с таким ID или анонимным кодом не найден.",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        amount = int(args[2].strip())
    except ValueError:
        await message.answer(
            "❌ Сумма должна быть числом.",
            parse_mode=ParseMode.HTML,
        )
        return

    await db.give_balance(amount, target_user_id)
    stats = await db.get_user_stats(target_user_id)
    await message.answer(
        f"✅ Баланс пользователя <code>{target_user_id}</code> изменён на <b>{amount}</b> ⭐️.\n"
        f"Текущий баланс: <b>{stats.balance}</b> ⭐️.",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("broadcast"))
async def broadcast_cmd(message: types.Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return

    if not message.reply_to_message and (
        not message.text or len(message.text.split(maxsplit=1)) < 2
    ):
        await message.answer(
            "⚠️ <b>Инструкция по рассылке:</b>\n\n"
            "• Ответьте командой <code>/broadcast</code> на любое сообщение/медиа для рассылки.\n"
            "• Или отправьте текст: <code>/broadcast Текст сообщения</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    user_ids = await db.get_all_user_ids()
    success_count = 0
    fail_count = 0

    status_msg = await message.answer(
        f"🔄 Запуск рассылки для <b>{len(user_ids)}</b> пользователей...",
        parse_mode=ParseMode.HTML,
    )

    for uid in user_ids:
        try:
            if message.reply_to_message:
                await message.reply_to_message.copy_to(chat_id=uid)
            elif message.text:
                text_to_send = message.text.split(maxsplit=1)[1]
                await bot.send_message(
                    chat_id=uid, text=text_to_send, parse_mode=ParseMode.HTML
                )
            success_count += 1
        except TelegramAPIError:
            fail_count += 1

    await status_msg.edit_text(
        f"📊 <b>Рассылка завершена!</b>\n\n"
        f"✅ Успешно отправлено: <b>{success_count}</b>\n"
        f"❌ Ошибок / заблокировали: <b>{fail_count}</b>",
        parse_mode=ParseMode.HTML,
    )
