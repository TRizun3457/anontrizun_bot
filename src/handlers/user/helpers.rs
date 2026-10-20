//! Shared user-handler helpers.

use anyhow::{Context, Result};
use teloxide::types::{CallbackQuery, InlineKeyboardMarkup, Message};

use crate::api::Api;
use crate::constants::{CAT_KAOMOJI_LIST, cat_string};
use crate::db::{Database, models::UserStats};

/// Mirrors the original `is_plain_message` predicate (text only, not caption).
pub fn is_plain_message(message: &Message) -> bool {
    !message.text().unwrap_or("").starts_with('/')
}

/// Picks a random kaomoji formatted as `" {kaomoji} "`.
pub fn random_cat() -> String {
    let index = rand::random_range(0..CAT_KAOMOJI_LIST.len());
    cat_string(CAT_KAOMOJI_LIST[index])
}

/// Returns the decoration string only when VIP cats are enabled.
pub fn cat_for(stats: &UserStats) -> String {
    if stats.is_vip && stats.show_vip_cats {
        random_cat()
    } else {
        String::new()
    }
}

/// `send_or_edit` for message events: always sends a new message.
pub async fn send_or_edit_message(
    api: &Api,
    message: &Message,
    text: &str,
    reply_markup: InlineKeyboardMarkup,
) -> Result<()> {
    api.send_message_with_markup(message.chat.id, text, reply_markup)
        .await?;
    Ok(())
}

/// `send_or_edit` for callback events: edits when the message is accessible,
/// then always answers the callback.
pub async fn send_or_edit_callback(
    api: &Api,
    callback: &CallbackQuery,
    text: &str,
    reply_markup: InlineKeyboardMarkup,
) -> Result<()> {
    if let Some(message) = callback.regular_message() {
        api.edit_text(message.chat.id, message.id, text, Some(reply_markup))
            .await?;
    }
    api.answer_callback(callback.id.clone(), None, false)
        .await?;
    Ok(())
}

fn visibility_value(stats: &UserStats, field_name: &str) -> Option<bool> {
    match field_name {
        "show_sent" => Some(stats.show_sent),
        "show_received" => Some(stats.show_received),
        "show_priority" => Some(stats.show_priority),
        "show_air" => Some(stats.show_air),
        "show_achievements" => Some(stats.show_achievements),
        _ => None,
    }
}

/// Flips the given visibility flag unless it would hide every card entry.
pub async fn toggle_visibility_field(
    database: &Database,
    user_id: i64,
    field_name: &str,
) -> Result<bool> {
    let stats = database.get_user_stats(user_id).await?;

    let active_count = [
        stats.show_sent,
        stats.show_received,
        stats.show_priority,
        stats.show_air,
        stats.show_achievements,
    ]
    .into_iter()
    .filter(|value| *value)
    .count();

    let current_value = visibility_value(&stats, field_name).context("unknown visibility field")?;

    if current_value && active_count <= 1 {
        return Ok(false);
    }

    database
        .update_user_setting(user_id, field_name, if current_value { "0" } else { "1" })
        .await?;
    Ok(true)
}
