import logging

from aiogram import F, Router, types
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from config import ADMIN_ID
from potato.achievements import POTATO_ACHIEVEMENTS
from potato.service import PotatoService
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
    unlocked = set(stats["achievements"])
    lines = [
        "🥔 <b>ГНИЛАЯ КАРТОШКА — ваша статистика</b>",
        "─────────────────────",
        f"📥 Получено картошек: <b>{stats['received']}</b>",
        f"✅ Передано вовремя: <b>{stats['passed']}</b>",
        f"💥 Взорвалось у вас: <b>{stats['exploded']}</b>",
        f"🔥 Лучшая серия передач: <b>{stats['best_pass_streak']}</b>",
    ]
    if stats["fastest_pass_sec"] is not None:
        lines.append(
            f"⚡ Самая быстрая передача: <b>{stats['fastest_pass_sec']} с.</b>"
        )
    lines.append(
        "👁 Участие в игре: "
        + ("<b>включено</b>" if stats["enabled"] else "<b>скрыто (VIP)</b>")
    )
    lines.append(
        f"\n🏆 <b>Достижения игры ({len(unlocked)}/{len(POTATO_ACHIEVEMENTS)}):</b>"
    )
    for ach_id, (title, desc) in POTATO_ACHIEVEMENTS.items():
        mark = "✅" if ach_id in unlocked else "🔒"
        lines.append(f"{mark} {title} — {desc}")
    if not is_vip:
        lines.append("\n💎 Скрыть игру из своего профиля могут только VIP.")
    return "\n".join(lines)


def _settings_kb(enabled: bool, is_vip: bool) -> InlineKeyboardMarkup:
    if is_vip:
        label = "🙈 Скрыть игру от меня" if enabled else "👁 Вернуть игру"
    else:
        label = "🔒 Скрыть игру (только VIP)"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data="potato_toggle")],
            [
                InlineKeyboardButton(
                    text="◀️ Назад в настройки", callback_data="settings_menu"
                )
            ],
        ]
    )


async def _show(event: types.Message | types.CallbackQuery, store) -> None:
    if event.from_user is None:
        return
    user_stats = await db.get_user_stats(event.from_user.id)
    stats = await store.get_stats(event.from_user.id)
    await send_or_edit(
        event,
        format_stats(stats, user_stats.is_vip),
        _settings_kb(bool(stats["enabled"]), user_stats.is_vip),
    )


@router.message(Command("potata_info"), F.chat.type == ChatType.PRIVATE)
async def potata_info(message: types.Message, potato_service: PotatoService) -> None:
    if message.from_user is None:
        return
    await db.register_user(message.from_user.id)
    await _show(message, potato_service.store)


@router.callback_query(F.data == "settings_potato")
async def potato_settings(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    await _show(callback, potato_service.store)


@router.callback_query(F.data == "potato_toggle")
async def potato_toggle(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None:
        return
    stats = await potato_service.store.get_stats(callback.from_user.id)
    try:
        await potato_service.store.set_enabled(
            callback.from_user.id, not stats["enabled"]
        )
    except PotatoError as exc:
        await callback.answer(f"💎 {exc}", show_alert=True)
        return
    await callback.answer("Готово.")
    await _show(callback, potato_service.store)


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
        await service.start_game(message.chat.id, message.from_user.id, duration)
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
