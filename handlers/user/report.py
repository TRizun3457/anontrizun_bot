import logging

from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from config import ADMIN_ID
from potato.service import PotatoService
from reports import (
    MAX_REPORT_LENGTH,
    ReportLimiter,
    format_report_header,
    is_cancel_text,
    is_too_long,
)

from .helpers import send_or_edit
from .settings import show_settings_menu

router = Router()
logger = logging.getLogger(__name__)
limiter = ReportLimiter()


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✖️ Отмена", callback_data="report_cancel")]
        ]
    )


@router.callback_query(F.data == "settings_report")
async def start_report(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        return
    if callback.from_user.id == ADMIN_ID:
        await callback.answer(
            "Вы владелец бота — сообщать о проблеме самому себе не нужно.",
            show_alert=True,
        )
        return
    left = limiter.remaining(callback.from_user.id)
    if left:
        await callback.answer(
            f"⏳ Следующее сообщение о проблеме можно отправить через {left} с.",
            show_alert=True,
        )
        return
    await state.set_state(ReportState.waiting_for_text)
    await send_or_edit(
        callback,
        "🛠 <b>СООБЩИТЬ О ПРОБЛЕМЕ</b>\n"
        "─────────────────────\n"
        "Опишите, что пошло не так, одним сообщением. Можно приложить скриншот, фото, видео или файл.\n\n"
        "⚠️ Это сообщение <b>не анонимное</b>: владелец бота увидит ваш профиль "
        "(имя, username и ID), чтобы ответить вам. Ваш анонимный код и ваши "
        "анонимки ему при этом <b>не раскрываются</b>.\n\n"
        f"Максимум {MAX_REPORT_LENGTH} символов. Отмена: кнопка ниже или /cancel.",
        cancel_keyboard(),
    )


@router.callback_query(F.data == "report_cancel", ReportState.waiting_for_text)
async def cancel_report_button(
    callback: types.CallbackQuery, state: FSMContext, potato_service: PotatoService
) -> None:
    await state.clear()
    await callback.answer("Отменено.")
    await show_settings_menu(callback, potato_service)


@router.message(
    ReportState.waiting_for_text,
    F.chat.type == "private",
    F.func(lambda m: is_cancel_text(m.text)),
)
async def cancel_report_command(
    message: types.Message, state: FSMContext, potato_service: PotatoService
) -> None:
    await state.clear()
    await message.answer("✖️ Отправка сообщения о проблеме отменена.")
    await show_settings_menu(message, potato_service)


@router.message(
    ReportState.waiting_for_text,
    F.chat.type == "private",
    F.func(lambda m: not (m.text or "").startswith("/")),
)
async def send_report(message: types.Message, state: FSMContext, bot: Bot) -> None:
    user = message.from_user
    if user is None:
        return
    if user.id == ADMIN_ID or message.successful_payment or message.refunded_payment:
        await state.clear()
        return
    if is_too_long(message.text or message.caption):
        await message.answer(
            f"❌ Слишком длинно: максимум {MAX_REPORT_LENGTH} символов. Сократите и отправьте снова.",
            reply_markup=cancel_keyboard(),
        )
        return
    left = limiter.remaining(user.id)
    if left:
        await state.clear()
        await message.answer(f"⏳ Подождите {left} с. перед следующим сообщением.")
        return
    await db.register_user(user.id)
    try:
        await bot.send_message(
            ADMIN_ID,
            format_report_header(user.id, user.full_name, user.username),
            parse_mode=ParseMode.HTML,
        )
        await message.copy_to(chat_id=ADMIN_ID)
    except TelegramAPIError:
        logger.exception("Failed to deliver problem report from %s", user.id)
        await message.answer(
            "❌ Не удалось отправить сообщение. Попробуйте позже.",
            parse_mode=ParseMode.HTML,
        )
        return
    limiter.mark(user.id)
    await state.clear()
    await message.answer(
        "✅ Спасибо! Сообщение о проблеме отправлено владельцу бота.",
        parse_mode=ParseMode.HTML,
    )
