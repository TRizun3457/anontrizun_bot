from typing import cast
from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    PreCheckoutQuery,
)

import database as db
from config import ADMIN_ID

router = Router()


class ApologyState(StatesGroup):
    waiting_for_text: State = State()


async def pay_with_balance_or_invoice(
    user_id: int, price: int, item_type: str, callback: types.CallbackQuery, bot: Bot
) -> None:
    balance, *_ = await db.get_user_stats(user_id)
    db_conn = db.get_db()

    if balance >= price:
        _ = await db_conn.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ?",
            (price, user_id),
        )

        if item_type == "priority":
            _ = await db_conn.execute(
                "UPDATE users SET priority_messages = priority_messages + 1 WHERE user_id = ?",
                (user_id,),
            )
            if isinstance(callback.message, types.Message):
                _ = await callback.message.answer(
                    "🎉 <b>Оплачено с баланса!</b> Начислен 1 приоритетный ответ.",
                    parse_mode=ParseMode.HTML,
                )
        elif item_type == "vip":
            _ = await db_conn.execute(
                "UPDATE users SET is_vip = 1 WHERE user_id = ?", (user_id,)
            )
            if isinstance(callback.message, types.Message):
                _ = await callback.message.answer(
                    "💎 <b>Оплачено с баланса!</b> Активировано VIP-оформление.",
                    parse_mode=ParseMode.HTML,
                )
        elif item_type == "air":
            _ = await db_conn.execute(
                "UPDATE users SET air_purchased = air_purchased + 1 WHERE user_id = ?",
                (user_id,),
            )
            if isinstance(callback.message, types.Message):
                _ = await callback.message.answer(
                    "💨 <b>Оплачено с баланса!</b> Вы приобрели воздух.",
                    parse_mode=ParseMode.HTML,
                )

        await db_conn.commit()
        _ = await callback.answer()
    else:
        title_map = {
            "priority": "⭐ Гарантированный ответ",
            "vip": "💎 VIP-Поддержка",
            "air": "💨 Покупка воздуха",
        }
        payload_map = {
            "priority": "buy_priority_msg",
            "vip": "buy_vip_sub",
            "air": "buy_air_pack",
        }
        _ = await bot.send_invoice(
            chat_id=user_id,
            title=title_map[item_type],
            description=f"Недостаточно средств на балансе. Прямая оплата {price} ⭐️",
            payload=payload_map[item_type],
            currency="XTR",
            prices=[LabeledPrice(label=title_map[item_type], amount=price)],
        )
        _ = await callback.answer()


@router.callback_query(F.data == "deposit_menu")
async def deposit_menu_handler(callback: types.CallbackQuery) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10 ⭐️", callback_data="dep_10"),
                InlineKeyboardButton(text="50 ⭐️", callback_data="dep_50"),
                InlineKeyboardButton(text="100 ⭐️", callback_data="dep_100"),
            ],
            [
                InlineKeyboardButton(text="200 ⭐️", callback_data="dep_200"),
                InlineKeyboardButton(text="500 ⭐️", callback_data="dep_500"),
                InlineKeyboardButton(text="1000 ⭐️", callback_data="dep_1000"),
            ],
        ]
    )
    if isinstance(callback.message, types.Message):
        _ = await callback.message.answer(
            "💳 <b>Выберите сумму для пополнения баланса бота:</b>",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    _ = await callback.answer()


@router.callback_query(F.data.startswith("dep_"))
async def send_deposit_invoice(callback: types.CallbackQuery, bot: Bot) -> None:
    if not callback.data:
        return
    amount = int(callback.data.split("_")[1])
    _ = await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"💳 Пополнение баланса на {amount} Stars",
        description=f"Пополнение внутреннего баланса бота на {amount} ⭐️",
        payload=f"deposit_{amount}",
        currency="XTR",
        prices=[LabeledPrice(label=f"Пополнение {amount} Stars", amount=amount)],
    )
    _ = await callback.answer()


@router.callback_query(F.data == "buy_priority")
async def handle_buy_priority(callback: types.CallbackQuery, bot: Bot) -> None:
    await pay_with_balance_or_invoice(
        callback.from_user.id, 1, "priority", callback, bot
    )


@router.callback_query(F.data == "buy_vip")
async def handle_buy_vip(callback: types.CallbackQuery, bot: Bot) -> None:
    await pay_with_balance_or_invoice(
        callback.from_user.id, 100, "vip", callback, bot
    )


@router.callback_query(F.data == "buy_air")
async def handle_buy_air(callback: types.CallbackQuery, bot: Bot) -> None:
    await pay_with_balance_or_invoice(
        callback.from_user.id, 10, "air", callback, bot
    )


@router.callback_query(F.data == "buy_apology")
async def handle_buy_apology(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    user_id = callback.from_user.id
    balance, *_ = await db.get_user_stats(user_id)

    if balance >= 50:
        await state.set_state(ApologyState.waiting_for_text)
        _ = await state.update_data(paid_by_balance=True)
        if isinstance(callback.message, types.Message):
            _ = await callback.message.answer(
                "✍️ <b>Напишите сообщение с раскаянием для администратора:</b>",
                parse_mode=ParseMode.HTML,
            )
        _ = await callback.answer()
    else:
        _ = await bot.send_invoice(
            chat_id=user_id,
            title="🙏 Заявка на разбан",
            description="Шанс на разбан. Вы сможете отправить раскаяние админу.",
            payload="buy_apology_req",
            currency="XTR",
            prices=[LabeledPrice(label="Попросить прощения", amount=50)],
        )
        _ = await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(
    pre_checkout_query: PreCheckoutQuery, bot: Bot
) -> None:
    _ = await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(
    message: types.Message, state: FSMContext
) -> None:
    if not message.from_user or not message.successful_payment:
        return

    user_id = message.from_user.id
    payment = message.successful_payment
    charge_id = payment.telegram_payment_charge_id
    payload = payment.invoice_payload

    _ = await db.register_user(user_id)
    db_conn = db.get_db()

    _ = await db_conn.execute(
        "INSERT INTO payments (charge_id, user_id, payload, status) VALUES (?, ?, ?, 'success')",
        (charge_id, user_id, payload),
    )

    if payload.startswith("deposit_"):
        amount = int(payload.split("_")[1])
        _ = await db_conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id),
        )
        _ = await message.answer(
            f"🎉 <b>Баланс пополнен на {amount} Stars!</b>",
            parse_mode=ParseMode.HTML,
        )

    elif payload == "buy_priority_msg":
        _ = await db_conn.execute(
            "UPDATE users SET priority_messages = priority_messages + 1 WHERE user_id = ?",
            (user_id,),
        )
        _ = await message.answer(
            "🎉 <b>Оплата прошла успешно!</b> Вам начислен 1 приоритетный ответ.",
            parse_mode=ParseMode.HTML,
        )

    elif payload == "buy_vip_sub":
        _ = await db_conn.execute(
            "UPDATE users SET is_vip = 1 WHERE user_id = ?", (user_id,)
        )
        _ = await message.answer(
            "💎 <b>Огромное спасибо за поддержку!</b> Активировано VIP-оформление.",
            parse_mode=ParseMode.HTML,
        )

    elif payload == "buy_air_pack":
        _ = await db_conn.execute(
            "UPDATE users SET air_purchased = air_purchased + 1 WHERE user_id = ?",
            (user_id,),
        )
        _ = await message.answer(
            "💨 <b>Спасибо за покупку воздуха!</b>", parse_mode=ParseMode.HTML
        )

    elif payload == "buy_apology_req":
        await state.set_state(ApologyState.waiting_for_text)
        _ = await state.update_data(paid_by_balance=False)
        _ = await message.answer(
            "✍️ <b>Оплата получена!</b> Введите текст раскаяния:",
            parse_mode=ParseMode.HTML,
        )

    await db_conn.commit()


@router.message(ApologyState.waiting_for_text)
async def process_apology_text(
    message: types.Message, state: FSMContext, bot: Bot
) -> None:
    if not message.from_user or not message.text:
        return

    user_id = message.from_user.id
    data = await state.get_data()
    paid_by_balance = cast(bool, data.get("paid_by_balance", False))

    db_conn = db.get_db()

    if paid_by_balance:
        _ = await db_conn.execute(
            "UPDATE users SET balance = balance - 50 WHERE user_id = ?", (user_id,)
        )
        await db_conn.commit()

    await state.clear()

    async with db_conn.execute(
        "SELECT anon_code FROM banned WHERE user_id = ?", (user_id,)
    ) as cursor:
        fetched = await cursor.fetchone()
        res = cast(tuple[str] | None, fetched)
        anon_code = res[0] if res else "НЕИЗВЕСТНО"

    apology_text = (
        f"🙏 <b>ЗАЯВКА НА РАЗБАН (ОПЛАЧЕНО 50 ⭐️)</b>\n\n"
        f"• <b>Код забаненного:</b> <code>{anon_code}</code>\n"
        f"• <b>User ID:</b> <code>{user_id}</code>\n\n"
        f"<b>Сообщение с раскаянием:</b>\n<i>{message.text}</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Разбанить", callback_data=f"accept_unban_{anon_code}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"decline_unban_{user_id}"
                )
            ],
        ]
    )

    _ = await bot.send_message(
        chat_id=ADMIN_ID,
        text=apology_text,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )
    _ = await message.answer(
        "🚀 Ваша заявка отправлена администратору!", parse_mode=ParseMode.HTML
    )


@router.message(Command("refund"))
async def refund_user_payments(message: types.Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        _ = await message.answer(
            "⚠️ Пример:\n<code>/refund USER_ID</code> или <code>/refund stx9B9...</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    input_param = args[1].strip()
    db_conn = db.get_db()

    if input_param.startswith("stx"):
        charge_id = input_param
        async with db_conn.execute(
            "SELECT user_id FROM payments WHERE charge_id = ?", (charge_id,)
        ) as cursor:
            fetched = await cursor.fetchone()
            row = cast(tuple[int] | None, fetched)

        user_to_refund = row[0] if row else ADMIN_ID
        try:
            _ = await bot.refund_star_payment(
                user_id=user_to_refund, telegram_payment_charge_id=charge_id
            )
            _ = await db_conn.execute(
                "UPDATE payments SET status = 'refunded' WHERE charge_id = ?",
                (charge_id,),
            )
            await db_conn.commit()
            _ = await message.answer(
                f"✅ Успешный возврат по операции: <code>{charge_id}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            _ = await message.answer(
                f"❌ Ошибка при возврате: <code>{e}</code>", parse_mode=ParseMode.HTML
            )
        return

    try:
        target_user_id = int(input_param)
    except ValueError:
        _ = await message.answer(
            "❌ Введите числовой ID пользователя или ID операции `stx...`",
            parse_mode=ParseMode.HTML,
        )
        return

    async with db_conn.execute(
        "SELECT charge_id FROM payments WHERE user_id = ? AND status = 'success'",
        (target_user_id,),
    ) as cursor:
        fetched = await cursor.fetchall()
        rows = cast(list[tuple[str]], fetched)

    if not rows:
        _ = await message.answer(
            "❌ Нет успешных платежей для возврата.", parse_mode=ParseMode.HTML
        )
        return

    refunded_count = 0
    for (charge_id,) in rows:
        try:
            _ = await bot.refund_star_payment(
                user_id=target_user_id, telegram_payment_charge_id=charge_id
            )
            _ = await db_conn.execute(
                "UPDATE payments SET status = 'refunded' WHERE charge_id = ?",
                (charge_id,),
            )
            refunded_count += 1
        except Exception:
            pass

    await db_conn.commit()
    _ = await message.answer(
        f"✅ Успешно возвращено транзакций: <b>{refunded_count}</b>",
        parse_mode=ParseMode.HTML,
    )
