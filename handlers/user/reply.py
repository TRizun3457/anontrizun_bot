import logging

from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import ADMIN_ID

router = Router()
logger = logging.getLogger(__name__)


class ReplyState(StatesGroup):
    waiting_for_reply = State()


@router.callback_query(F.data.startswith("reply_"))
async def handle_reply_button(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return

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
            text="📩 Вам пришёл ответ на анонимное сообщение:",
            parse_mode=ParseMode.HTML,
        )
        await message.copy_to(chat_id=sender_id)
        await db.increment_received_count(sender_id)
        await db.increment_answer_streak(sender_id)
        await db.check_and_grant_achievements(sender_id)
        await message.answer("✅ Ответ успешно отправлен!", parse_mode=ParseMode.HTML)
    except TelegramAPIError:
        logger.exception("Error sending reply to user %s", sender_id)
        await message.answer(
            "❌ Не удалось доставить ответ пользователю.", parse_mode=ParseMode.HTML
        )
