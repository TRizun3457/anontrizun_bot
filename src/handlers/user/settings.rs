//! `/settings`, the code refresh flow and the inline-sharing menu.

use std::sync::Arc;

use teloxide::types::{CallbackQuery, InlineKeyboardMarkup, Message};

use crate::app::AppState;
use crate::constants;
use crate::error::{HandlerResult, guarded_callback, guarded_message};
use crate::handlers::user::helpers;
use crate::keyboards;
use crate::texts;

async fn settings_screen(
    state: &AppState,
    user_id: i64,
) -> anyhow::Result<(String, InlineKeyboardMarkup)> {
    let user_stats = state.db.get_user_stats(user_id).await?;
    let text = texts::settings_text(&user_stats);
    let keyboard = keyboards::settings_keyboard(&user_stats);
    Ok((text, keyboard))
}

async fn show_settings_menu(state: &AppState, callback: &CallbackQuery) -> anyhow::Result<()> {
    let from = &callback.from;

    let (text, keyboard) = settings_screen(state, from.id.0 as i64).await?;
    helpers::send_or_edit_callback(&state.api, callback, &text, keyboard).await
}

pub async fn show_settings_menu_message(state: Arc<AppState>, message: Message) -> HandlerResult {
    guarded_message(&message, async {
        let Some(from) = message.from.as_ref() else {
            return Ok(());
        };

        let (text, keyboard) = settings_screen(&state, from.id.0 as i64).await?;
        helpers::send_or_edit_message(&state.api, &message, &text, keyboard).await
    })
    .await
}

pub async fn show_settings_menu_callback(
    state: Arc<AppState>,
    callback: CallbackQuery,
) -> HandlerResult {
    guarded_callback(&callback, async {
        show_settings_menu(&state, &callback).await
    })
    .await
}

pub async fn handle_refresh_code_manual(
    state: Arc<AppState>,
    callback: CallbackQuery,
) -> HandlerResult {
    guarded_callback(&callback, async {
        let from = &callback.from;

        let (success, result) = state.db.regenerate_user_code(from.id.0 as i64).await?;
        if success {
            state
                .api
                .answer_callback(
                    callback.id.clone(),
                    Some(&format!("✅ Ваш код успешно обновлен на: {result}")),
                    true,
                )
                .await?;
            show_settings_menu(&state, &callback).await?;
        } else {
            state
                .api
                .answer_callback(callback.id.clone(), Some(&format!("❌ {result}")), true)
                .await?;
        }
        Ok(())
    })
    .await
}

pub async fn handle_toggle_autorefresh(
    state: Arc<AppState>,
    callback: CallbackQuery,
) -> HandlerResult {
    guarded_callback(&callback, async {
        let from = &callback.from;
        let user_id = from.id.0 as i64;

        let user_stats = state.db.get_user_stats(user_id).await?;
        let new_value = match user_stats.code_auto_refresh.as_str() {
            "never" => "8h",
            "8h" => "daily",
            "daily" => "weekly",
            "weekly" => "never",
            _ => "never",
        };

        state
            .db
            .update_user_setting(user_id, "code_auto_refresh", new_value)
            .await?;
        state
            .api
            .answer_callback(
                callback.id.clone(),
                Some("⏱ Интервал авто-смены кода изменен."),
                false,
            )
            .await?;
        show_settings_menu(&state, &callback).await
    })
    .await
}

pub async fn handle_toggle_cats(state: Arc<AppState>, callback: CallbackQuery) -> HandlerResult {
    guarded_callback(&callback, async {
        let from = &callback.from;
        let user_id = from.id.0 as i64;

        let user_stats = state.db.get_user_stats(user_id).await?;
        let new_value = if user_stats.show_vip_cats { "0" } else { "1" };

        state
            .db
            .update_user_setting(user_id, "show_vip_cats", new_value)
            .await?;

        let status_text = if new_value == "1" {
            "включены"
        } else {
            "выключены"
        };
        state
            .api
            .answer_callback(
                callback.id.clone(),
                Some(&format!("🐱 Котики в оформлении {status_text}.")),
                false,
            )
            .await?;
        show_settings_menu(&state, &callback).await
    })
    .await
}

async fn share_settings_screen(
    state: &AppState,
    user_id: i64,
) -> anyhow::Result<(String, InlineKeyboardMarkup)> {
    let user_stats = state.db.get_user_stats(user_id).await?;
    let achievements_count = state.db.get_user_achievements_count(user_id).await?;
    let cat = helpers::cat_for(&user_stats);

    let preview_text = texts::share_preview_text(
        &user_stats,
        achievements_count,
        crate::achievements::total_count(),
        &cat,
    );
    let text = texts::share_settings_text(&preview_text);
    let keyboard = keyboards::share_settings_keyboard(&user_stats);
    Ok((text, keyboard))
}

pub async fn show_share_settings_menu(
    state: Arc<AppState>,
    callback: CallbackQuery,
) -> HandlerResult {
    guarded_callback(&callback, async {
        let from = &callback.from;

        let (text, keyboard) = share_settings_screen(&state, from.id.0 as i64).await?;
        helpers::send_or_edit_callback(&state.api, &callback, &text, keyboard).await
    })
    .await
}

pub async fn handle_toggle_share_visibility(
    state: Arc<AppState>,
    callback: CallbackQuery,
) -> HandlerResult {
    guarded_callback(&callback, async {
        let (from, Some(data)) = (&callback.from, callback.data.as_deref()) else {
            return Ok(());
        };

        let target = data.replace("toggle_share_vis_", "");
        let Some(field) = constants::visibility_field(&target) else {
            state
                .api
                .answer_callback(
                    callback.id.clone(),
                    Some("⚠️ Ошибка выбора параметра."),
                    true,
                )
                .await?;
            return Ok(());
        };

        let toggled = helpers::toggle_visibility_field(&state.db, from.id.0 as i64, field).await?;
        if !toggled {
            state
                .api
                .answer_callback(
                    callback.id.clone(),
                    Some("❌ Нельзя скрыть все элементы! В карточке должен быть виден хотя бы один показатель."),
                    true,
                )
                .await?;
            return Ok(());
        }

        state
            .api
            .answer_callback(
                callback.id.clone(),
                Some("✅ Видимость показателя изменена."),
                false,
            )
            .await?;

        let (text, keyboard) = share_settings_screen(&state, from.id.0 as i64).await?;
        helpers::send_or_edit_callback(&state.api, &callback, &text, keyboard).await
    })
    .await
}
