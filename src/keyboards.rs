//! Inline keyboard layouts, byte-identical to the original screens.

use anyhow::{Context, Result};
use teloxide::types::{InlineKeyboardButton, InlineKeyboardMarkup};
use url::Url;

use crate::db::models::UserStats;
use crate::texts;

fn url_button(text: &str, url: &str) -> Result<InlineKeyboardButton> {
    let url = Url::parse(url).with_context(|| format!("invalid keyboard URL: {url}"))?;
    Ok(InlineKeyboardButton::url(text.to_string(), url))
}

/// Keyboard attached to the "you are blocked" notice in `/start` and forwarding.
pub fn banned_notice_keyboard() -> InlineKeyboardMarkup {
    InlineKeyboardMarkup::new(vec![vec![InlineKeyboardButton::callback(
        "🙏 Попросить прощения (50 ⭐️)",
        "buy_apology",
    )]])
}

/// Keyboard attached to the ban notification sent from `/ban`.
///
/// The original had a leading space and no emoji here; keep it verbatim.
pub fn ban_notification_keyboard() -> InlineKeyboardMarkup {
    InlineKeyboardMarkup::new(vec![vec![InlineKeyboardButton::callback(
        " Попросить прощения (50 ⭐️)",
        "buy_apology",
    )]])
}

pub fn start_keyboard() -> InlineKeyboardMarkup {
    InlineKeyboardMarkup::new(vec![
        vec![InlineKeyboardButton::callback(
            "📊 Мой статус / Баланс",
            "my_status",
        )],
        vec![InlineKeyboardButton::callback(
            "⚙️ Настройки профиля",
            "settings_menu",
        )],
        vec![InlineKeyboardButton::callback(
            "🏆 Мои достижения",
            "my_achievements",
        )],
        vec![InlineKeyboardButton::callback(
            "💳 Пополнить баланс Stars",
            "deposit_menu",
        )],
        vec![InlineKeyboardButton::callback(
            "⭐ Приоритет (1 ⭐️)",
            "buy_priority",
        )],
        vec![InlineKeyboardButton::callback(
            "💎 VIP-Оформление (100 ⭐️)",
            "buy_vip",
        )],
        vec![InlineKeyboardButton::callback(
            "💨 Купить воздух (10 ⭐️)",
            "buy_air",
        )],
    ])
}

pub fn profile_actions_keyboard() -> InlineKeyboardMarkup {
    InlineKeyboardMarkup::new(vec![
        vec![InlineKeyboardButton::callback(
            "⚙️ Настройки профиля",
            "settings_menu",
        )],
        vec![InlineKeyboardButton::callback(
            "🏆 Мои достижения",
            "my_achievements",
        )],
        vec![InlineKeyboardButton::callback(
            "💳 Пополнить баланс Stars",
            "deposit_menu",
        )],
        vec![InlineKeyboardButton::switch_inline_query(
            "📲 Поделиться статусом",
            "",
        )],
        vec![InlineKeyboardButton::callback(
            "⭐ Купить приоритет (1 ⭐️)",
            "buy_priority",
        )],
        vec![InlineKeyboardButton::callback(
            "💎 VIP-Оформление (100 ⭐️)",
            "buy_vip",
        )],
        vec![InlineKeyboardButton::callback(
            "💨 Купить воздух (10 ⭐️)",
            "buy_air",
        )],
    ])
}

pub fn profile_back_keyboard() -> InlineKeyboardMarkup {
    InlineKeyboardMarkup::new(vec![vec![InlineKeyboardButton::callback(
        "◀️ Назад в профиль",
        "my_status",
    )]])
}

pub fn deposit_keyboard() -> InlineKeyboardMarkup {
    InlineKeyboardMarkup::new(vec![
        vec![
            InlineKeyboardButton::callback("10 ⭐️", "dep_10"),
            InlineKeyboardButton::callback("50 ⭐️", "dep_50"),
            InlineKeyboardButton::callback("100 ⭐️", "dep_100"),
        ],
        vec![
            InlineKeyboardButton::callback("200 ⭐️", "dep_200"),
            InlineKeyboardButton::callback("500 ⭐️", "dep_500"),
            InlineKeyboardButton::callback("1000 ⭐️", "dep_1000"),
        ],
    ])
}

pub fn priority_insufficient_keyboard() -> InlineKeyboardMarkup {
    InlineKeyboardMarkup::new(vec![vec![InlineKeyboardButton::callback(
        "💳 Пополнить баланс Stars",
        "deposit_menu",
    )]])
}

pub fn reply_keyboard(user_id: i64) -> InlineKeyboardMarkup {
    InlineKeyboardMarkup::new(vec![vec![InlineKeyboardButton::callback(
        "↩️ Ответить",
        format!("reply_{user_id}"),
    )]])
}

pub fn apology_admin_keyboard(anon_code: &str, user_id: i64) -> InlineKeyboardMarkup {
    InlineKeyboardMarkup::new(vec![
        vec![InlineKeyboardButton::callback(
            "✅ Разбанить",
            format!("accept_unban_{anon_code}"),
        )],
        vec![InlineKeyboardButton::callback(
            "❌ Отклонить",
            format!("decline_unban_{user_id}"),
        )],
    ])
}

pub fn settings_keyboard(stats: &UserStats) -> InlineKeyboardMarkup {
    let refresh_str = texts::refresh_label(&stats.code_auto_refresh);
    let cats_str = texts::cats_label(stats.show_vip_cats);

    InlineKeyboardMarkup::new(vec![
        vec![InlineKeyboardButton::callback(
            "🔄 Обновить код вручную",
            "settings_refresh_code",
        )],
        vec![InlineKeyboardButton::callback(
            format!("⏱ Авто-смена кода: {refresh_str}"),
            "settings_toggle_autorefresh",
        )],
        vec![InlineKeyboardButton::callback(
            format!("🐱 Котики (VIP): {cats_str}"),
            "settings_toggle_cats",
        )],
        vec![InlineKeyboardButton::callback(
            "📲 Настройки шеринга",
            "settings_share_menu",
        )],
        vec![InlineKeyboardButton::callback(
            "◀️ Назад в профиль",
            "my_status",
        )],
    ])
}

pub fn share_settings_keyboard(stats: &UserStats) -> InlineKeyboardMarkup {
    let vis_sent = if stats.show_sent { "✅" } else { "❌" };
    let vis_received = if stats.show_received { "✅" } else { "❌" };
    let vis_priority = if stats.show_priority { "✅" } else { "❌" };
    let vis_air = if stats.show_air { "✅" } else { "❌" };
    let vis_ach = if stats.show_achievements {
        "✅"
    } else {
        "❌"
    };

    InlineKeyboardMarkup::new(vec![
        vec![
            InlineKeyboardButton::callback(
                format!("✉️ Анонимки: {vis_sent}"),
                "toggle_share_vis_sent",
            ),
            InlineKeyboardButton::callback(
                format!("💬 Ответы: {vis_received}"),
                "toggle_share_vis_received",
            ),
        ],
        vec![
            InlineKeyboardButton::callback(
                format!("⭐ Приоритеты: {vis_priority}"),
                "toggle_share_vis_priority",
            ),
            InlineKeyboardButton::callback(format!("💨 Воздух: {vis_air}"), "toggle_share_vis_air"),
        ],
        vec![InlineKeyboardButton::callback(
            format!("🏆 Достижения: {vis_ach}"),
            "toggle_share_vis_achievements",
        )],
        vec![InlineKeyboardButton::switch_inline_query(
            "🚀 Проверить и поделиться в чате",
            "",
        )],
        vec![InlineKeyboardButton::callback(
            "◀️ Назад в настройки",
            "settings_menu",
        )],
    ])
}

/// Keyboard used by `/anon` in groups: a deep link that starts the bot.
pub fn anon_share_keyboard(bot_username: &str) -> Result<InlineKeyboardMarkup> {
    let button = url_button(
        "✉️ Написать анонимно",
        &format!("https://t.me/{bot_username}?start=anon"),
    )?;
    Ok(InlineKeyboardMarkup::new(vec![vec![button]]))
}

/// Admin entry of the inline query results.
pub fn inline_admin_keyboard(bot_username: &str) -> Result<InlineKeyboardMarkup> {
    let button = url_button(
        "💬 Написать анонимно",
        &format!("https://t.me/{bot_username}?start=anon"),
    )?;
    Ok(InlineKeyboardMarkup::new(vec![vec![button]]))
}

/// Regular user entry of the inline query results.
pub fn inline_user_keyboard(bot_username: &str) -> Result<InlineKeyboardMarkup> {
    let button = url_button(
        "✉️ Написать анонимно",
        &format!("https://t.me/{bot_username}?start=share"),
    )?;
    Ok(InlineKeyboardMarkup::new(vec![vec![button]]))
}

#[cfg(test)]
mod tests {
    use teloxide::types::InlineKeyboardButtonKind;

    use super::*;

    #[test]
    fn url_keyboards_verify_the_deep_link() {
        let keyboard = anon_share_keyboard("my_bot").unwrap();
        assert_eq!(keyboard.inline_keyboard.len(), 1);
        assert_eq!(keyboard.inline_keyboard[0].len(), 1);

        let button = &keyboard.inline_keyboard[0][0];
        assert_eq!(button.text, "✉️ Написать анонимно");
        match &button.kind {
            InlineKeyboardButtonKind::Url(url) => {
                assert_eq!(url.as_str(), "https://t.me/my_bot?start=anon");
            }
            other => panic!("expected a URL button, got {other:?}"),
        }
    }

    #[test]
    fn relative_urls_are_rejected() {
        assert!(url_button("x", "not-a-url").is_err());
    }
}
