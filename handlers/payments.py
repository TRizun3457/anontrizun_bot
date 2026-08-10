from logging import getLogger

from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
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
logger = getLogger(__name__)


class ApologyState(StatesGroup):
    waiting_for_text: State = State()


async def pay_with_balance_or_invoice(
    user_id: int, price: int, item_type: str, callback: types.CallbackQuery, bot: Bot
) -> None:
    user_stats = await db.get_user_stats(user_id)

    if user_stats.balance >= price:
        await db.take_balance(price, user_id)
        await db.increment_total_spent_stars(user_id, price)
        await db.grant_achievement(user_id, "first_donate", bot)

        reply_text: str | None = None

        if item_type == "priority":
            await db.increment_priority_messages(user_id)
            reply_text = "🎉 <b>Оплачено с баланса!</b> Начислен 1 приоритетный ответ."

        elif item_type == "vip":
            await db.set_vip(user_id)
            reply_text = "💎 <b>Оплачено с баланса!</b> Активировано VIP-оформление."

        elif item_type == "air":
            await db.increment_air_purchased(user_id)
            reply_text = "💨 <b>Оплачено с баланса!</b> Вы приобрели воздух."

        await db.check_and_grant_achievements(user_id, bot)

        if isinstance(callback.message, types.Message) and reply_text:
            await callback.message.answer(
                reply_text,
                parse_mode=ParseMode.HTML,
            )

        await callback.answer()
    else:
        # Для обычных товаров выдается инвойс, кроме приоритета (п. 1 ТЗ)
        title_map = {
            "vip": "💎 VIP-Поддержка",
            "air": "💨 Покупка воздуха",
        }
        payload_map = {
            "vip": "buy_vip_sub",
            "air": "buy_air_pack",
        }
        if item_type in title_map:
            await bot.send_invoice(
                chat_id=user_id,
                title=title_map[item_type],
                description=f"Недостаточно средств на балансе. Прямая оплата {price} ⭐️",
                payload=payload_map[item_type],
                currency="XTR",
                prices=[LabeledPrice(label=title_map[item_type], amount=price)],
            )
        await callback.answer()


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
        await callback.message.answer(
            "💳 <b>Выберите сумму для пополнения баланса бота:</b>",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@router.callback_query(F.data.startswith("dep_"))
async def send_deposit_invoice(callback: types.CallbackQuery, bot: Bot) -> None:
    if not callback.data:
        return
    amount = int(callback.data.split("_")[1])
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"💳 Пополнение баланса на {amount} Stars",
        description=f"Пополнение внутреннего баланса бота на {amount} ⭐️",
        payload=f"deposit_{amount}",
        currency="XTR",
        prices=[LabeledPrice(label=f"Пополнение {amount} Stars", amount=amount)],
    )
    await callback.answer()


@router.callback_query(F.data == "buy_priority")
async def handle_buy_priority(callback: types.CallbackQuery, bot: Bot) -> None:
    user_id = callback.from_user.id
    user_stats = await db.get_user_stats(user_id)

    # Приоритет продается ИСКЛЮЧИТЕЛЬНО с баланса в боте (п. 1 ТЗ)
    if user_stats.balance >= 1:
        await pay_with_balance_or_invoice(user_id, 1, "priority", callback, bot)
    else:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💳 Пополнить баланс Stars", callback_data="deposit_menu"
                    )
                ]
            ]
        )
        if isinstance(callback.message, types.Message):
            await callback.message.answer(
                "❌ <b>Недостаточно средств на балансе!</b>\n\n"
                "Приоритет покупается <b>только с внутреннего баланса</b> (1 ⭐️).\n"
                "Пополните баланс в меню ниже:",
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        await callback.answer()


@router.callback_query(F.data == "buy_vip")
async def handle_buy_vip(callback: types.CallbackQuery, bot: Bot) -> None:
    await pay_with_balance_or_invoice(callback.from_user.id, 100, "vip", callback, bot)


@router.callback_query(F.data == "buy_air")
async def handle_buy_air(callback: types.CallbackQuery, bot: Bot) -> None:
    await pay_with_balance_or_invoice(callback.from_user.id, 10, "air", callback, bot)


@router.callback_query(F.data == "buy_apology")
async def handle_buy_apology(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    user_id = callback.from_user.id
    user_stats = await db.get_user_stats(user_id)

    if user_stats.balance >= 50:
        await state.set_state(ApologyState.waiting_for_text)
        await state.update_data(paid_by_balance=True)
        if isinstance(callback.message, types.Message):
            await callback.message.answer(
                "✍️ <b>Напишите сообщение с раскаянием для администратора:</b>",
                parse_mode=ParseMode.HTML,
            )
        await callback.answer()
    else:
        await bot.send_invoice(
            chat_id=user_id,
            title="🙏 Заявка на разбан",
            description="Шанс на разбан. Вы сможете отправить раскаяние админу.",
            payload="buy_apology_req",
            currency="XTR",
            prices=[LabeledPrice(label="Попросить прощения", amount=50)],
        )
        await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot) -> None:
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(
    message: types.Message, state: FSMContext, bot: Bot
) -> None:
    if not message.from_user or not message.successful_payment:
        return

    user_id = message.from_user.id
    payment = message.successful_payment
    charge_id = payment.telegram_payment_charge_id
    payload = payment.invoice_payload
    stars_amount = payment.total_amount

    await db.register_user(user_id)
    await db.create_payment(charge_id, user_id, payload)
    await db.increment_total_spent_stars(user_id, stars_amount)
    await db.grant_achievement(user_id, "first_donate", bot)

    reply_text: str | None = None

    if payload.startswith("deposit_"):
        amount = int(payload.split("_")[1])
        await db.give_balance(amount, user_id)
        reply_text = f"🎉 <b>Баланс пополнен на {amount} Stars!</b>"

    elif payload == "buy_vip_sub":
        await db.set_vip(user_id)
        reply_text = (
            "💎 <b>Огромное спасибо за поддержку!</b> Активировано VIP-оформление."
        )

    elif payload == "buy_air_pack":
        await db.increment_air_purchased(user_id)
        reply_text = "💨 <b>Спасибо за покупку воздуха!</b>"

    elif payload == "buy_apology_req":
        await state.set_state(ApologyState.waiting_for_text)
        await state.update_data(paid_by_balance=False)
        reply_text = "✍️ <b>Оплата получена!</b> Введите текст раскаяния:"

    await db.check_and_grant_achievements(user_id, bot)

    if reply_text:
        await message.answer(reply_text, parse_mode=ParseMode.HTML)


@router.message(ApologyState.waiting_for_text)
async def process_apology_text(
    message: types.Message, state: FSMContext, bot: Bot
) -> None:
    if not message.from_user or not message.text:
        return

    user_id = message.from_user.id
    data = await state.get_data()
    paid_by_balance = data.get("paid_by_balance", False)

    if not isinstance(paid_by_balance, bool):
        msg = f"paid_by_balance in state is {type(paid_by_balance)}, expected bool"
        raise TypeError(msg)

    if paid_by_balance:
        await db.take_balance(50, user_id)

    await state.clear()

    anon_code = await db.get_banned_anon_code_by_user_id(user_id)

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

    await bot.send_message(
        chat_id=ADMIN_ID,
        text=apology_text,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )
    await message.answer(
        "🚀 Ваша заявка отправлена администратору!", parse_mode=ParseMode.HTML
    )


@router.message(Command("refund"))
async def refund_user_payments(message: types.Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.id != ADMIN_ID or not message.text:
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "⚠️ Пример:\n<code>/refund USER_ID</code> или <code>/refund stx9B9...</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    input_param = args[1].strip()

    if input_param.startswith("stx"):
        charge_id = input_param
        refund_user_id = (
            await db.get_payment_user_id_by_charge_id(charge_id)
        ) or ADMIN_ID

        try:
            await bot.refund_star_payment(
                user_id=refund_user_id, telegram_payment_charge_id=charge_id
            )
            await db.set_payment_status_by_charge_id(charge_id, "refunded")
            await message.answer(
                f"✅ Успешный возврат по операции: <code>{charge_id}</code>",
                parse_mode=ParseMode.HTML,
            )
        except TelegramAPIError as err:
            await message.answer(
                f"❌ Ошибка при возврате: <code>{err!r}</code>",
                parse_mode=ParseMode.HTML,
            )
        return

    try:
        target_user_id = int(input_param)
    except ValueError:
        await message.answer(
            "❌ Введите числовой ID пользователя или ID операции `stx...`",
            parse_mode=ParseMode.HTML,
        )
        return

    charge_ids = await db.get_success_charge_ids_by_user_id(target_user_id)

    if not charge_ids:
        await message.answer(
            "❌ Нет успешных платежей для возврата.", parse_mode=ParseMode.HTML
        )
        return

    refunded_ids: list[str] = []
    for charge_id in charge_ids:
        try:
            await bot.refund_star_payment(
                user_id=target_user_id, telegram_payment_charge_id=charge_id
            )
            refunded_ids.append(charge_id)
        except TelegramAPIError:
            logger.exception("error while refunding star payments")

    await db.batch_set_payment_status_by_charge_ids(refunded_ids, "refunded")

    await message.answer(
        f"✅ Успешно возвращено транзакций: <b>{len(refunded_ids)}</b>",
        parse_mode=ParseMode.HTML,
    )
