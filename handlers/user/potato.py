import logging

from aiogram import F, Router, types
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from config import ADMIN_ID
from potato.achievements import POTATO_ACHIEVEMENTS
from potato.service import GROUP_COOLDOWN_SECONDS, PotatoService
from potato.store import MAX_DURATION, MIN_DURATION, PotatoError, random_duration

from .helpers import send_or_edit

router = Router()
logger = logging.getLogger(__name__)


def pass_markup(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🥔➡️ Передать картошку анонимно",
                    callback_data=f"potato_pass:{game_id}",
                )
            ]
        ]
    )


def format_stats(stats: dict, is_vip: bool) -> str:
    lines = [
        "🥔 <b>ГНИЛАЯ КАРТОШКА</b>",
        "─────────────────────",
        "🎮 Участие в игре: "
        + ("<b>вы в игре</b>" if stats["enabled"] else "<b>вы вышли из игры</b>"),
    ]
    if stats["hide_stats"]:
        lines.append("🙈 Статистика скрыта (VIP).")
    else:
        lines += [
            f"📥 Получено картошек: <b>{stats['received']}</b>",
            f"✅ Передано вовремя: <b>{stats['passed']}</b>",
            f"💥 Взорвалось у вас: <b>{stats['exploded']}</b>",
            f"🔥 Лучшая серия передач: <b>{stats['best_pass_streak']}</b>",
        ]
        if stats["fastest_pass_sec"] is not None:
            lines.append(
                f"⚡ Самая быстрая передача: <b>{stats['fastest_pass_sec']} с.</b>"
            )
    if not is_vip:
        lines.append("\n💎 Скрыть статистику могут только VIP.")
    return "\n".join(lines)


def format_achievements(stats: dict) -> str:
    unlocked = set(stats["achievements"])
    lines = [
        f"🏆 <b>ДОСТИЖЕНИЯ ИГРЫ ({len(unlocked)}/{len(POTATO_ACHIEVEMENTS)})</b>",
        "─────────────────────",
    ]
    for ach_id, (title, desc) in POTATO_ACHIEVEMENTS.items():
        mark = "✅" if ach_id in unlocked else "🔒"
        lines.append(f"{mark} {title} — {desc}")
    return "\n".join(lines)


def _menu_kb(stats: dict, is_vip: bool) -> InlineKeyboardMarkup:
    leave_label = "🚪 Выйти из игры" if stats["enabled"] else "▶️ Вернуться в игру"
    if is_vip:
        hide_label = (
            "👁 Показать статистику" if stats["hide_stats"] else "🙈 Скрыть статистику"
        )
    else:
        hide_label = "🔒 Скрыть статистику (VIP)"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=leave_label, callback_data="potato_leave"),
                InlineKeyboardButton(text=hide_label, callback_data="potato_hide"),
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Достижения игры", callback_data="potato_achievements"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад в настройки", callback_data="settings_menu"
                )
            ],
        ]
    )


async def _show(
    event: types.Message | types.CallbackQuery, service: PotatoService
) -> None:
    if event.from_user is None:
        return
    user_stats = await db.get_user_stats(event.from_user.id)
    stats = await service.store.get_stats(event.from_user.id)
    await send_or_edit(
        event,
        format_stats(stats, user_stats.is_vip),
        _menu_kb(stats, user_stats.is_vip),
    )


@router.message(Command("potata_info"), F.chat.type == ChatType.PRIVATE)
async def potata_info(message: types.Message, potato_service: PotatoService) -> None:
    if message.from_user is None:
        return
    await db.register_user(message.from_user.id)
    await _show(message, potato_service)


@router.callback_query(F.data == "settings_potato")
async def potato_settings(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    await _show(callback, potato_service)


@router.callback_query(F.data == "potato_leave")
async def potato_leave(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None:
        return
    stats = await potato_service.store.get_stats(callback.from_user.id)
    now_enabled = not stats["enabled"]
    await potato_service.store.set_enabled(callback.from_user.id, now_enabled)
    await callback.answer(
        "Вы снова в игре."
        if now_enabled
        else "Вы вышли из игры: картошки приходить не будут."
    )
    await _show(callback, potato_service)


@router.callback_query(F.data == "potato_hide")
async def potato_hide(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None:
        return
    stats = await potato_service.store.get_stats(callback.from_user.id)
    try:
        await potato_service.store.set_hide_stats(
            callback.from_user.id, not stats["hide_stats"]
        )
    except PotatoError as exc:
        await callback.answer(f"💎 {exc}", show_alert=True)
        return
    await callback.answer("Готово.")
    await _show(callback, potato_service)


@router.callback_query(F.data == "potato_achievements")
async def potato_achievements(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None:
        return
    stats = await potato_service.store.get_stats(callback.from_user.id)
    await send_or_edit(
        callback,
        format_achievements(stats),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад в меню картошки", callback_data="settings_potato"
                    )
                ]
            ]
        ),
    )


@router.message(Command("potata"), F.chat.type == ChatType.PRIVATE)
async def potata_private(
    message: types.Message, command: CommandObject, potato_service: PotatoService
) -> None:
    if message.from_user is None:
        return
    if message.from_user.id != ADMIN_ID:
        await message.answer(
            "🥔 Игру запускают командой <code>/potata</code> в чате, где есть бот.\n"
            "Статистика: /potata_info",
            parse_mode=ParseMode.HTML,
        )
        return
    await _start(message, command, potato_service, admin=True)


@router.message(
    Command("potata"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP})
)
async def potata_group(
    message: types.Message, command: CommandObject, potato_service: PotatoService
) -> None:
    if message.from_user is None:
        return
    await _start(
        message, command, potato_service, admin=message.from_user.id == ADMIN_ID
    )


async def _start(
    message: types.Message,
    command: CommandObject,
    service: PotatoService,
    *,
    admin: bool,
) -> None:
    assert message.from_user is not None
    duration = random_duration()
    if command.args and admin:
        try:
            minutes = int(command.args.split()[0])
        except ValueError:
            await message.answer(
                "Использование: <code>/potata [минуты]</code>, "
                f"от {MIN_DURATION // 60} до {MAX_DURATION // 60}.",
                parse_mode=ParseMode.HTML,
            )
            return
        if not MIN_DURATION // 60 <= minutes <= MAX_DURATION // 60:
            await message.answer(
                f"⏱ Допустимо от {MIN_DURATION // 60} до {MAX_DURATION // 60} минут."
            )
            return
        duration = minutes * 60
    try:
        await service.start_game(
            message.chat.id,
            message.from_user.id,
            duration,
            cooldown_sec=0 if admin else GROUP_COOLDOWN_SECONDS,
            mark_cooldown=not admin,
        )
    except PotatoError as exc:
        await message.answer(f"🥔 {exc}")
    except Exception:
        logger.exception("potato start failed")
        await message.answer("❌ Не удалось запустить игру, попробуйте позже.")


@router.callback_query(F.data.startswith("potato_pass:"))
async def potato_pass(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        game_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("⚠️ Некорректная кнопка.", show_alert=True)
        return
    try:
        await potato_service.pass_potato(game_id, callback.from_user.id)
    except PotatoError as exc:
        await callback.answer(f"🥔 {exc}", show_alert=True)
        return
    except Exception:
        logger.exception("potato pass failed")
        await callback.answer("❌ Ошибка, попробуйте ещё раз.", show_alert=True)
        return
    await callback.answer("✅ Картошка передана!")
    if isinstance(callback.message, types.Message):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramAPIError:
            logger.debug("cannot clear potato keyboard", exc_info=True)


@router.message(Command("potata_rot"), F.chat.type == ChatType.PRIVATE)
async def potata_rot(message: types.Message, potato_service: PotatoService) -> None:
    if message.from_user is None or message.from_user.id != ADMIN_ID:
        return
    try:
        await potato_service.start_rot_day(message.chat.id, message.from_user.id)
    except PotatoError as exc:
        await message.answer(f"🥔 {exc}")
    except Exception:
        logger.exception("potato rot day failed")
        await message.answer("❌ Не удалось запустить день гниения.")
