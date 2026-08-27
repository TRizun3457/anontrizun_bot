import asyncio
import logging

from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
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
            " Список забаненных пользователей пуст.", parse_mode=ParseMode.HTML
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
                            text=" Попросить прощения (50 ⭐️)",
                            callback_data="buy_apology",
                        )
                    ]
                ]
            )
            await bot.send_message(
                chat_id=sender_with_code.sender_id,
                text="❌ <b>Вы были заблокированы администратором.</b>\n\n"
                "Ваш код заморожен. Вы можете подать заявку на разбан за 50 ⭐️.",
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
            notify_status = "Оповещение доставлено."
        except TelegramAPIError:
            notify_status = "Не удалось доставить оповещение."
            logger.exception("error while sending ban message to user")
        await message.answer(
            f"🚫 Пользователь (ID: <code>{sender_with_code.sender_id}</code>) заблокирован!\n"
            f"Код: <code>{sender_with_code.anon_code}</code> (Заморожен)\n<i>{notify_status}</i>",
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
        new_code = await db.unban_user(user_id)
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"✅ <b>Вы были разблокированы!</b>\n\n"
                f"Ваш анонимный код сброшен и сгенерирован заново: <code>{new_code}</code>",
                parse_mode=ParseMode.HTML,
            )
        except TelegramAPIError:
            logger.exception("error while sending unblocked message to user")
        await message.answer(
            f"✅ Пользователь разбанен!\n"
            f"Старый код: <code>{anon_code}</code>\n"
            f"Новый сгенерированный код: <code>{new_code}</code>",
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
        new_code = await db.unban_user(user_id)
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"✅ <b>Ваша заявка одобрена! Вы успешно разбанены.</b>\n\n"
                f"Ваш новый анонимный код: <code>{new_code}</code>",
                parse_mode=ParseMode.HTML,
            )
        except TelegramAPIError:
            logger.exception(
                "error while sending unban application accept message to user"
            )
        current_text = callback.message.text or ""
        await callback.message.edit_text(
            current_text
            + f"\n\n<b>Статус: РАЗБАНЕН ✅ (Новый код: <code>{new_code}</code>)</b>",
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


@router.message(Command("refund"))
async def refund_cmd(message: types.Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "⚠️ Пример использования:\n"
            "• <code>/refund STX_ID</code> — возврат конкретной транзакции\n"
            "• <code>/refund USER_ID</code> — возврат всех транзакций пользователя",
            parse_mode=ParseMode.HTML,
        )
        return

    target = args[1].strip()

    if target.startswith("stx_") or not target.isdigit():
        charge_id = target
        payment = await db.get_payment_by_charge_id(charge_id)

        if not payment:
            await message.answer(
                f"❌ Платёж <code>{charge_id}</code> не найден в базе данных.",
                parse_mode=ParseMode.HTML,
            )
            return

        if payment.status == "refunded":
            await message.answer(
                f"⚠️ Платёж <code>{charge_id}</code> уже был возвращён ранее.",
                parse_mode=ParseMode.HTML,
            )
            return

        await process_single_refund(bot, message, payment.user_id, charge_id)
        return

    user_id = int(target)
    successful_payments = await db.get_success_charge_ids_by_user_id(user_id)

    if not successful_payments:
        await message.answer(
            f"❌ У пользователя <code>{user_id}</code> нет успешных платежей для возврата.",
            parse_mode=ParseMode.HTML,
        )
        return

    status_msg = await message.answer(
        f"🔄 Начат процесс возврата для пользователя <code>{user_id}</code> ({len(successful_payments)} шт.)...",
        parse_mode=ParseMode.HTML,
    )

    success_count = 0
    fail_count = 0

    for charge_id in successful_payments:
        is_success = await process_single_refund(
            bot=bot,
            message=None,
            user_id=user_id,
            charge_id=charge_id,
        )
        if is_success:
            success_count += 1
        else:
            fail_count += 1

    await status_msg.edit_text(
        f"📊 <b>Результат возврата средств для {user_id}:</b>\n\n"
        f"✅ Успешно возвращено: <b>{success_count}</b>\n"
        f"❌ Ошибок возврата: <b>{fail_count}</b>",
        parse_mode=ParseMode.HTML,
    )


async def process_single_refund(
    bot: Bot,
    message: types.Message | None,
    user_id: int,
    charge_id: str,
) -> bool:
    is_updated = await db.set_payment_status_if_current(
        charge_id=charge_id,
        expected_status="success",
        new_status="refund_pending",
    )

    if not is_updated:
        if message:
            await message.answer(
                f"⚠️ Платёж <code>{charge_id}</code> уже обрабатывается или статус изменён.",
                parse_mode=ParseMode.HTML,
            )
        return False

    try:
        await bot.refund_star_payment(
            user_id=user_id,
            telegram_payment_charge_id=charge_id,
        )
        await db.set_payment_status_by_charge_id(charge_id=charge_id, status="refunded")

        if message:
            await message.answer(
                f"✅ Возврат платежа <code>{charge_id}</code> для пользователя <code>{user_id}</code> выполнен успешно.",
                parse_mode=ParseMode.HTML,
            )
        return True

    except TelegramAPIError as exc:
        logger.exception("Refund error via Telegram API for charge %s", charge_id)
        await db.set_payment_status_by_charge_id(
            charge_id=charge_id, status="refund_failed"
        )

        if message:
            await message.answer(
                f"❌ Ошибка Telegram API при возврате <code>{charge_id}</code>:\n<code>{exc.message}</code>",
                parse_mode=ParseMode.HTML,
            )
        return False


@router.message(Command("broadcast"))
async def broadcast_cmd(message: types.Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message and (
        not message.text or len(message.text.split(maxsplit=1)) < 2
    ):
        await message.answer(
            "️ <b>Инструкция по рассылке:</b>\n\n"
            "• Ответьте командой <code>/broadcast</code> на любое сообщение/медиа для рассылки.\n"
            "• Или отправьте текст: <code>/broadcast Текст сообщения</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    user_ids = await db.get_all_user_ids()
    status_msg = await message.answer(
        f"🔄 Запуск рассылки для <b>{len(user_ids)}</b> пользователей...",
        parse_mode=ParseMode.HTML,
    )

    text_to_send = None
    if not message.reply_to_message and message.text:
        text_to_send = message.text.split(maxsplit=1)[1]

    semaphore = asyncio.Semaphore(20)
    lock = asyncio.Lock()
    success_count = 0
    fail_count = 0

    async def send_to_user(uid: int) -> None:
        nonlocal success_count, fail_count
        async with semaphore:
            while True:
                try:
                    if message.reply_to_message:
                        await message.reply_to_message.copy_to(chat_id=uid)
                    elif text_to_send:
                        await bot.send_message(
                            chat_id=uid, text=text_to_send, parse_mode=ParseMode.HTML
                        )
                    async with lock:
                        success_count += 1
                    break
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                except TelegramAPIError:
                    async with lock:
                        fail_count += 1
                    break

    await asyncio.gather(*(send_to_user(uid) for uid in user_ids))

    await status_msg.edit_text(
        f"📊 <b>Рассылка завершена!</b>\n\n"
        f"✅ Успешно отправлено: <b>{success_count}</b>\n"
        f"❌ Ошибок / заблокировали: <b>{fail_count}</b>",
        parse_mode=ParseMode.HTML,
    )
