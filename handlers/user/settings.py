from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import database as db
from achievements import ACHIEVEMENTS
from potato.service import PotatoService

from .constants import VIS_FIELD_MAP
from .helpers import (
    get_share_preview_text,
    send_or_edit,
    toggle_visibility_field,
)

router = Router()


@router.message(Command("settings"), F.chat.type == "private")
@router.callback_query(F.data == "settings_menu")
async def show_settings_menu(
    event: types.Message | types.CallbackQuery, potato_service: PotatoService
) -> None:
    if event.from_user is None:
        return

    user_id = event.from_user.id
    user_stats = await db.get_user_stats(user_id)
    refresh_map = {
        "never": "Никогда",
        "8h": "Раз в 8 ч.",
        "daily": "Раз в 24 ч.",
        "weekly": "Раз в 7 дней",
    }
    refresh_str = refresh_map.get(user_stats.code_auto_refresh, "Никогда")
    cats_str = "Включены ✅" if user_stats.show_vip_cats else "Выключены ❌"
    show_dogs = bool((await potato_service.store.get_stats(user_id))["show_dogs"])
    dogs_str = "Включены ✅" if show_dogs else "Выключены ❌"

    text = (
        "⚙️ <b>НАСТРОЙКИ ПРОФИЛЯ</b>\n"
        "─────────────────────\n\n"
        f"🔑 Ваш анонимный код: <code>{user_stats.anon_code}</code>\n\n"
        f"• Авто-обновление кода: {refresh_str}\n"
        f"• Кастомизация котиков (VIP): {cats_str}\n"
        f"• Кастомизация собачек (VIP): {dogs_str}\n\n"
        "Выберите параметр для изменения ниже:"
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
                    text=f"🐶 Собачки (VIP): {dogs_str}",
                    callback_data="settings_toggle_dogs",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📲 Настройки шеринга",
                    callback_data="settings_share_menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛠 Сообщить о проблеме", callback_data="settings_report"
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="my_status")],
        ]
    )
    await send_or_edit(event, text, kb)


@router.callback_query(F.data == "settings_refresh_code")
async def handle_refresh_code_manual(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None:
        return

    success, result = await db.regenerate_user_code(callback.from_user.id)
    if success:
        await callback.answer(
            f"✅ Ваш код успешно обновлен на: {result}", show_alert=True
        )
        await show_settings_menu(callback, potato_service)
    else:
        await callback.answer(f"❌ {result}", show_alert=True)


@router.callback_query(F.data == "settings_toggle_autorefresh")
async def handle_toggle_autorefresh(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None:
        return

    user_stats = await db.get_user_stats(callback.from_user.id)
    cycle = {"never": "8h", "8h": "daily", "daily": "weekly", "weekly": "never"}
    new_val = cycle.get(user_stats.code_auto_refresh, "never")

    await db.update_user_setting(callback.from_user.id, "code_auto_refresh", new_val)
    await callback.answer("⏱ Интервал авто-смены кода изменен.")
    await show_settings_menu(callback, potato_service)


@router.callback_query(F.data == "settings_toggle_cats")
async def handle_toggle_cats(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None:
        return

    user_stats = await db.get_user_stats(callback.from_user.id)
    new_val = "0" if user_stats.show_vip_cats else "1"

    await db.update_user_setting(callback.from_user.id, "show_vip_cats", new_val)
    status_text = "включены" if new_val == "1" else "выключены"
    await callback.answer(f"🐱 Котики в оформлении {status_text}.")
    await show_settings_menu(callback, potato_service)


DOGS_OFF_TEXT = (
    '🐕 Собакам тут не место! <a href="https://band.link/sob4ki">Им сюда</a>'
)


@router.callback_query(F.data == "settings_toggle_dogs")
async def handle_toggle_dogs(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None:
        return

    stats = await potato_service.store.get_stats(callback.from_user.id)
    new_val = not stats["show_dogs"]
    await potato_service.store.set_dogs(callback.from_user.id, new_val)
    await callback.answer(
        "🐶 Собачки в оформлении включены."
        if new_val
        else "🐶 Собачки в оформлении выключены."
    )
    await show_settings_menu(callback, potato_service)
    if not new_val and isinstance(callback.message, types.Message):
        await callback.message.answer(DOGS_OFF_TEXT, parse_mode="HTML")


@router.callback_query(F.data == "settings_share_menu")
async def show_share_settings_menu(
    event: types.Message | types.CallbackQuery, potato_service: PotatoService
) -> None:
    if event.from_user is None:
        return

    user_id = event.from_user.id
    user_stats = await db.get_user_stats(user_id)
    ach_count = await db.get_user_achievements_count(user_id)
    total_ach = len(ACHIEVEMENTS)

    show_dogs = bool((await potato_service.store.get_stats(user_id))["show_dogs"])
    preview_text = get_share_preview_text(user_stats, ach_count, total_ach, show_dogs)
    vis_sent = "✅" if user_stats.show_sent else "❌"
    vis_received = "✅" if user_stats.show_received else "❌"
    vis_priority = "✅" if user_stats.show_priority else "❌"
    vis_air = "✅" if user_stats.show_air else "❌"
    vis_ach = "✅" if user_stats.show_achievements else "❌"

    text = (
        "📲 <b>НАСТРОЙКИ ИНЛАЙН-ШЕРИНГА</b>\n"
        "─────────────────────\n"
        "🔒 Конфиденциальность: Ваш анонимный код и Telegram ID никогда не публикуются при шеринге.\n\n"
        "👁️ Предпросмотр сообщения (как его увидят в чате):\n\n"
        f"{preview_text}\n\n"
        "─────────────────────\n"
        "⚠️ Хотя бы один параметр всегда должен быть включён.\n"
        "Отметьте, что показывать в карточке:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✉️ Анонимки: {vis_sent}",
                    callback_data="toggle_share_vis_sent",
                ),
                InlineKeyboardButton(
                    text=f"💬 Ответы: {vis_received}",
                    callback_data="toggle_share_vis_received",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"⭐ Приоритеты: {vis_priority}",
                    callback_data="toggle_share_vis_priority",
                ),
                InlineKeyboardButton(
                    text=f"💨 Воздух: {vis_air}",
                    callback_data="toggle_share_vis_air",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"🏆 Достижения: {vis_ach}",
                    callback_data="toggle_share_vis_achievements",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚀 Проверить и поделиться в чате", switch_inline_query=""
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад в настройки", callback_data="settings_menu"
                )
            ],
        ]
    )
    await send_or_edit(event, text, kb)


@router.callback_query(F.data.startswith("toggle_share_vis_"))
async def handle_toggle_share_visibility(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None or callback.data is None:
        return

    target = callback.data.replace("toggle_share_vis_", "")
    if target not in VIS_FIELD_MAP:
        await callback.answer("⚠️ Ошибка выбора параметра.", show_alert=True)
        return

    ok = await toggle_visibility_field(callback.from_user.id, VIS_FIELD_MAP[target])
    if not ok:
        await callback.answer(
            "❌ Нельзя скрыть все элементы! В карточке должен быть виден хотя бы один показатель.",
            show_alert=True,
        )
        return

    await callback.answer("✅ Видимость показателя изменена.")
    await show_share_settings_menu(callback, potato_service)
