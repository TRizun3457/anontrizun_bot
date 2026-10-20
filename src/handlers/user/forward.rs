//! Anonymous forwarding to the admin.

use std::sync::Arc;

use teloxide::types::{ChatId, Message, MessageKind};

use crate::app::AppState;
use crate::error::{HandlerResult, guarded_message};
use crate::keyboards;
use crate::texts;

fn is_ignored_kind(message: &Message) -> bool {
    matches!(
        message.kind,
        MessageKind::NewChatMembers(_)
            | MessageKind::LeftChatMember(_)
            | MessageKind::NewChatTitle(_)
            | MessageKind::NewChatPhoto(_)
            | MessageKind::DeleteChatPhoto(_)
            | MessageKind::SuccessfulPayment(_)
            | MessageKind::RefundedPayment(_)
    )
}

pub async fn forward_anonymous_msg(state: Arc<AppState>, message: Message) -> HandlerResult {
    guarded_message(&message, async {
        let Some(from) = message.from.as_ref() else {
            return Ok(());
        };

        if message.successful_payment().is_some() || is_ignored_kind(&message) {
            return Ok(());
        }

        let user_id = from.id.0 as i64;
        if user_id == state.config.admin_id {
            return Ok(());
        }

        let user_stats = state.db.register_user(user_id, None).await?;
        if state.db.is_banned(user_id) {
            state
                .api
                .send_message_with_markup(
                    message.chat.id,
                    texts::FORWARD_BANNED_TEXT,
                    keyboards::banned_notice_keyboard(),
                )
                .await?;
            return Ok(());
        }

        let is_priority = user_stats.priority_messages > 0;
        if is_priority {
            state.db.waste_priority_message(user_id).await?;
        }

        let admin_chat = ChatId(state.config.admin_id);
        let keyboard = keyboards::reply_keyboard(user_id);

        let forward_result = async {
            if user_stats.is_vip {
                state
                    .api
                    .send_message(admin_chat, texts::FORWARD_VIP_BANNER)
                    .await?;
            }
            if is_priority {
                state
                    .api
                    .send_message(admin_chat, texts::FORWARD_PRIORITY_BANNER)
                    .await?;
            }
            state
                .api
                .copy_message(admin_chat, message.chat.id, message.id, Some(keyboard))
                .await
        }
        .await;

        let sent_message_id = match forward_result {
            Ok(message_id) => message_id,
            Err(error) => {
                tracing::error!(%error, user_id, "forward error");
                if is_priority {
                    state.db.increment_priority_messages(user_id).await?;
                }
                state
                    .api
                    .send_message(message.chat.id, texts::FORWARD_ERROR_TEXT)
                    .await?;
                return Ok(());
            }
        };

        state
            .db
            .add_message(
                sent_message_id.0 as i64,
                user_id,
                &user_stats.anon_code,
                is_priority,
                message.id.0 as i64,
            )
            .await?;
        if is_priority {
            state.db.increment_priority_sent_count(user_id).await?;
        }
        state.db.increment_sent_count(user_id).await?;

        let message_text = message
            .text()
            .or_else(|| message.caption())
            .unwrap_or_default()
            .to_lowercase();
        if message_text.contains("42") {
            state.db.grant_achievement(user_id, "bro_42").await?;
        }
        if message_text.contains("67") {
            state.db.grant_achievement(user_id, "degrade_67").await?;
        }

        state.db.check_and_grant_achievements(user_id).await?;

        let confirm_text = if is_priority {
            texts::FORWARD_CONFIRM_PRIORITY
        } else {
            texts::FORWARD_CONFIRM_TEXT
        };
        if let Err(error) = state.api.send_message(message.chat.id, confirm_text).await {
            tracing::error!(%error, user_id, "confirm error");
        }

        Ok(())
    })
    .await
}
