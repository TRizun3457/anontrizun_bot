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
                    text="🥔 Гнилая картошка", callback_data="settings_potato"
                )
            ],
            [InlineKeyboardButton(text="🛒 Магазин", callback_data="main_shop")],
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
                    text="🥔 Гнилая картошка", callback_data="settings_potato"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📲 Поделиться статусом", switch_inline_query=""
                )
            ],
            [InlineKeyboardButton(text="🛒 Магазин", callback_data="main_shop")],
        ]
    )
