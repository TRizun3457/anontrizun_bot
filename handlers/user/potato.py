import logging

from aiogram import F, Router, types
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from config import ADMIN_ID
from potato.formatting import format_achievements, format_stats
from potato.service import (
    GROUP_COOLDOWN_SECONDS,
    LAUNCH_PRICE,
    STRONG_ROT_PRICE,
    PotatoService,
    fmt_duration,
)
from potato.store import MAX_DURATION, MIN_DURATION, PotatoError, random_duration

from .helpers import pick_pet, send_or_edit

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


def _menu_kb(stats: dict, is_vip: bool, locked: bool = False) -> InlineKeyboardMarkup:
    leave_label = "🚪 Выйти из игры" if stats["enabled"] else "▶️ Вернуться в игру"
    if locked and stats["enabled"]:
        leave_label = "🔒 Выйти нельзя (вы запустили игру)"
    share_label = "📲 Чем делиться (VIP)" if is_vip else "🔒 Чем делиться (только VIP)"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=leave_label, callback_data="potato_leave"),
                InlineKeyboardButton(
                    text=share_label, callback_data="potato_share_menu"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Достижения игры", callback_data="potato_achievements"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Магазин гниения", callback_data="potato_shop"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📲 Поделиться статистикой игры", switch_inline_query=""
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
    lock = await service.store.leave_lock(event.from_user.id)
    lock_note = ""
    if lock is not None:
        lock_note = (
            "Вы запустили игру — выйти можно, когда она закончится."
            if lock[0] == "game"
            else f"Вы купили сильное гниение — выйти можно через {fmt_duration(lock[1])}."
        )
    pet = pick_pet(
        user_stats.is_vip, user_stats.show_vip_cats, bool(stats["show_dogs"])
    )
    await send_or_edit(
        event,
        format_stats(
            stats,
            user_stats.is_vip,
            await service.strong_rot_remaining(),
            pet,
            lock_note,
        ),
        _menu_kb(stats, user_stats.is_vip, lock is not None),
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
    try:
        await potato_service.store.set_enabled(callback.from_user.id, now_enabled)
    except PotatoError as exc:
        await callback.answer(f"🔒 {exc}", show_alert=True)
        return
    await callback.answer(
        "Вы снова в игре."
        if now_enabled
        else "Вы вышли из игры: картошки приходить не будут."
    )
    await _show(callback, potato_service)


SHARE_LABELS = {
    "share_received": "📥 Получено",
    "share_passed": "✅ Отражено",
    "share_exploded": "☠️ Сгнило",
    "share_streak": "🔥 Серия",
    "share_achievements": "🏆 Достижения",
}


async def _show_share_menu(
    callback: types.CallbackQuery, service: PotatoService
) -> None:
    stats = await service.store.get_stats(callback.from_user.id)
    rows = []
    for field, label in SHARE_LABELS.items():
        mark = "✅" if stats[field] else "❌"
        rows.append(
            InlineKeyboardButton(
                text=f"{label}: {mark}", callback_data=f"potato_share:{field}"
            )
        )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            rows[:2],
            rows[2:4],
            rows[4:],
            [
                InlineKeyboardButton(
                    text="🚀 Проверить и поделиться", switch_inline_query=""
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад в меню картошки", callback_data="settings_potato"
                )
            ],
        ]
    )
    await send_or_edit(
        callback,
        "📲 <b>ЧЕМ ДЕЛИТЬСЯ</b>\n─────────────────────\n"
        "Выберите, какие показатели игры увидят другие, когда вы поделитесь "
        "статистикой через инлайн-кнопку. Хотя бы один показатель всегда включён.",
        kb,
    )


@router.callback_query(F.data == "potato_share_menu")
async def potato_share_menu(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None:
        return
    user_stats = await db.get_user_stats(callback.from_user.id)
    if not user_stats.is_vip:
        await callback.answer(
            "💎 Настраивать, чем делиться, могут только VIP.", show_alert=True
        )
        return
    await _show_share_menu(callback, potato_service)


@router.callback_query(F.data.startswith("potato_share:"))
async def potato_share_toggle(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    field = callback.data.split(":", 1)[1]
    if field not in SHARE_LABELS:
        await callback.answer("⚠️ Ошибка выбора параметра.", show_alert=True)
        return
    stats = await potato_service.store.get_stats(callback.from_user.id)
    try:
        await potato_service.store.set_share(
            callback.from_user.id, field, not stats[field]
        )
    except PotatoError as exc:
        await callback.answer(f"💎 {exc}", show_alert=True)
        return
    await callback.answer("Готово.")
    await _show_share_menu(callback, potato_service)


SHOP_ITEMS = {
    "strong": (
        STRONG_ROT_PRICE,
        "🌋 СИЛЬНОЕ ГНИЕНИЕ",
        (
            "7 часов гнилые картошки (на час, как в день гниения) могут внезапно "
            "появляться у случайных пользователей бота."
        ),
    ),
    "launch": (
        LAUNCH_PRICE,
        "🥔💀 Запуск гнилой картошки",
        (
            "Немедленно запускает ещё одну гнилую картошку (час на передачу) "
            "в чате, не дожидаясь лимита."
        ),
    ),
}


def _back_to_shop_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Назад в магазин", callback_data="potato_shop"
                )
            ]
        ]
    )


@router.callback_query(F.data == "potato_shop")
async def potato_shop(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None:
        return
    user_stats = await db.get_user_stats(callback.from_user.id)
    left = await potato_service.strong_rot_remaining()
    lines = [
        "💰 <b>МАГАЗИН ГНИЕНИЯ</b>",
        "─────────────────────",
        f"Ваш баланс: <b>{user_stats.balance} ⭐</b>",
        "",
    ]
    for price, title, desc in SHOP_ITEMS.values():
        lines.append(f"<b>{title}</b> — {price} ⭐\n{desc}\n")
    if left > 0:
        lines.append(
            f"🌋 Сильное гниение уже идёт, осталось {fmt_duration(left)}. "
            "Покупка продлит его."
        )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🌋 Сильное гниение — {STRONG_ROT_PRICE} ⭐",
                    callback_data="potato_buy:strong",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🥔💀 Запуск картошки — {LAUNCH_PRICE} ⭐",
                    callback_data="potato_buy:launch",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 Пополнить баланс Stars", callback_data="deposit_menu"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад в меню картошки", callback_data="settings_potato"
                )
            ],
        ]
    )
    await send_or_edit(callback, "\n".join(lines), kb)


@router.callback_query(F.data.startswith("potato_buy:"))
async def potato_buy_confirm(callback: types.CallbackQuery) -> None:
    if callback.from_user is None or callback.data is None:
        return
    item = callback.data.split(":", 1)[1]
    if item not in SHOP_ITEMS:
        await callback.answer("⚠️ Неизвестный товар.", show_alert=True)
        return
    price, title, desc = SHOP_ITEMS[item]
    await send_or_edit(
        callback,
        f"<b>{title}</b>\n{desc}\n\nСтоимость: <b>{price} ⭐</b> "
        "(списывается с внутреннего баланса). Подтвердить покупку?",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"✅ Купить за {price} ⭐",
                        callback_data=f"potato_pay:{item}",
                    )
                ],
                [InlineKeyboardButton(text="◀️ Отмена", callback_data="potato_shop")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("potato_pay:"))
async def potato_pay(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    item = callback.data.split(":", 1)[1]
    if item not in SHOP_ITEMS:
        await callback.answer("⚠️ Неизвестный товар.", show_alert=True)
        return
    user_id = callback.from_user.id
    price, title, _ = SHOP_ITEMS[item]
    user_stats = await db.get_user_stats(user_id)
    if user_stats.balance < price or not await db.take_balance(price, user_id):
        await callback.answer(
            f"❌ Недостаточно звёзд на балансе (нужно {price} ⭐). "
            "Пополните баланс в магазине.",
            show_alert=True,
        )
        return
    try:
        if item == "strong":
            await potato_service.activate_strong_rot(user_id)
        else:
            await potato_service.launch_paid(user_id)
    except PotatoError as exc:
        await db.give_balance(price, user_id)
        await callback.answer(f"🥔 {exc} Звёзды возвращены.", show_alert=True)
        return
    except Exception:
        logger.exception("potato purchase failed")
        await db.give_balance(price, user_id)
        await callback.answer(
            "❌ Не удалось выполнить покупку, звёзды возвращены.", show_alert=True
        )
        return
    await db.increment_total_spent_stars(user_id, price)
    await db.grant_achievement(user_id, "first_donate")
    await potato_service.record_purchase(user_id, item, price)
    await db.check_and_grant_achievements(user_id)
    await callback.answer("✅ Покупка совершена!")
    await send_or_edit(
        callback,
        f"✅ <b>{title}</b> активировано. Списано {price} ⭐.",
        _back_to_shop_kb(),
    )


@router.callback_query(F.data == "potato_achievements")
async def potato_achievements(
    callback: types.CallbackQuery, potato_service: PotatoService
) -> None:
    if callback.from_user is None:
        return
    stats = await potato_service.store.get_stats(callback.from_user.id)
    user_stats = await db.get_user_stats(callback.from_user.id)
    await send_or_edit(
        callback,
        format_achievements(stats, user_stats.is_vip),
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
