//! `/anon` and `/start`.

use std::sync::Arc;

use teloxide::types::{Chat, ChatKind, PublicChatKind};

use crate::app::AppState;
use crate::error::{HandlerResult, guarded_message};
use crate::keyboards;
use crate::texts;
use crate::utils::command;

fn is_group_or_supergroup(chat: &Chat) -> bool {
    matches!(
        &chat.kind,
        ChatKind::Public(public)
            if matches!(public.kind, PublicChatKind::Group | PublicChatKind::Supergroup(_))
    )
}

pub async fn anon_group_cmd(
    state: Arc<AppState>,
    message: teloxide::types::Message,
) -> HandlerResult {
    guarded_message(&message, async {
        if is_group_or_supergroup(&message.chat) {
            let keyboard = keyboards::anon_share_keyboard(&state.bot_username)?;
            state
                .api
                .send_message_with_markup(message.chat.id, texts::ANON_GROUP_TEXT, keyboard)
                .await?;
        } else {
            state
                .api
                .send_message(message.chat.id, texts::ANON_PRIVATE_TEXT)
                .await?;
        }
        Ok(())
    })
    .await
}

pub async fn start_cmd(state: Arc<AppState>, message: teloxide::types::Message) -> HandlerResult {
    guarded_message(&message, async {
        let Some(from) = message.from.as_ref() else {
            return Ok(());
        };
        if !message.chat.is_private() {
            return Ok(());
        }

        let text = command::message_text(&message).unwrap_or_default();
        let args = command::extract_command(text, "start", &state.bot_username).unwrap_or_default();

        let referrer_id = args
            .strip_prefix("ref_")
            .and_then(|value| value.parse::<i64>().ok());

        let user_id = from.id.0 as i64;
        state.db.register_user(user_id, referrer_id).await?;

        if user_id == state.config.admin_id {
            state
                .api
                .send_message(message.chat.id, texts::ADMIN_PANEL_TEXT)
                .await?;
            return Ok(());
        }

        if state.db.is_banned(user_id) {
            state
                .api
                .send_message_with_markup(
                    message.chat.id,
                    texts::START_BANNED_TEXT,
                    keyboards::banned_notice_keyboard(),
                )
                .await?;
            return Ok(());
        }

        state
            .api
            .send_message_with_markup(
                message.chat.id,
                texts::START_PRIVATE_TEXT,
                keyboards::start_keyboard(),
            )
            .await?;
        Ok(())
    })
    .await
}
