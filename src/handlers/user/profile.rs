//! `/status` and the achievements screen.

use std::sync::Arc;

use teloxide::types::{CallbackQuery, Message};

use crate::app::AppState;
use crate::error::{HandlerResult, guarded_callback, guarded_message};
use crate::handlers::user::helpers;
use crate::keyboards;
use crate::texts;

async fn build_status_text(state: &AppState, user_id: i64) -> anyhow::Result<String> {
    let user_stats = state.db.register_user(user_id, None).await?;
    let banned = state.db.is_banned(user_id);
    let cat = helpers::cat_for(&user_stats);
    let achievements_count = state.db.get_user_achievements_count(user_id).await?;

    Ok(texts::profile_text(
        &user_stats,
        user_id,
        banned,
        achievements_count,
        &cat,
    ))
}

pub async fn show_status_message(state: Arc<AppState>, message: Message) -> HandlerResult {
    guarded_message(&message, async {
        let Some(from) = message.from.as_ref() else {
            return Ok(());
        };

        let text = build_status_text(&state, from.id.0 as i64).await?;
        state
            .api
            .send_message_with_markup(
                message.chat.id,
                &text,
                keyboards::profile_actions_keyboard(),
            )
            .await?;
        Ok(())
    })
    .await
}

pub async fn show_status_callback(state: Arc<AppState>, callback: CallbackQuery) -> HandlerResult {
    guarded_callback(&callback, async {
        let from = &callback.from;

        let text = build_status_text(&state, from.id.0 as i64).await?;
        helpers::send_or_edit_callback(
            &state.api,
            &callback,
            &text,
            keyboards::profile_actions_keyboard(),
        )
        .await?;
        Ok(())
    })
    .await
}

pub async fn show_achievements_callback(
    state: Arc<AppState>,
    callback: CallbackQuery,
) -> HandlerResult {
    guarded_callback(&callback, async {
        let from = &callback.from;

        let unlocked = state.db.get_user_achievements(from.id.0 as i64).await?;
        let text = texts::achievements_text(&unlocked);

        helpers::send_or_edit_callback(
            &state.api,
            &callback,
            &text,
            keyboards::profile_back_keyboard(),
        )
        .await?;
        Ok(())
    })
    .await
}
