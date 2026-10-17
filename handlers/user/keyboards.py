from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


def get_banned_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🙏 Попросить прощения (50 ⭐️)",
                    callback_data="buy_apology",
                )
            ]
        ]
    )


def get_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Мой статус / Баланс", callback_data="my_status"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Настройки профиля", callback_data="settings_menu"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Мои достижения", callback_data="my_achievements"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 Пополнить баланс Stars", callback_data="deposit_menu"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Приоритет (1 ⭐️)", callback_data="buy_priority"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 VIP-Оформление (100 ⭐️)", callback_data="buy_vip"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💨 Купить воздух (10 ⭐️)", callback_data="buy_air"
                )
            ],
        ]
    )


def get_profile_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚙️ Настройки профиля", callback_data="settings_menu"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Мои достижения", callback_data="my_achievements"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 Пополнить баланс Stars", callback_data="deposit_menu"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📲 Поделиться статусом", switch_inline_query=""
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Купить приоритет (1 ⭐️)", callback_data="buy_priority"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 VIP-Оформление (100 ⭐️)", callback_data="buy_vip"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💨 Купить воздух (10 ⭐️)", callback_data="buy_air"
                )
            ],
        ]
    )
