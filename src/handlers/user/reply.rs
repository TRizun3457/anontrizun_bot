//! Admin reply flow: the `↩️ Ответить` button and the delayed reply.

use std::sync::Arc;

use anyhow::Context;
use teloxide::types::{CallbackQuery, ChatId, Message};

use crate::app::AppState;
use crate::error::{HandlerResult, guarded_callback, guarded_message};
use crate::fsm::DialogState;
use crate::texts;

pub async fn handle_reply_button(state: Arc<AppState>, callback: CallbackQuery) -> HandlerResult {
    guarded_callback(&callback, async {
        let from = &callback.from;

        if from.id.0 as i64 != state.config.admin_id {
            state
                .api
                .answer_callback(callback.id.clone(), None, false)
                .await?;
            return Ok(());
        }

        let (Some(data), Some(message)) = (callback.data.as_deref(), callback.regular_message())
        else {
            state
                .api
                .answer_callback(
                    callback.id.clone(),
                    Some(texts::REPLY_BUTTON_ERROR_TEXT),
                    true,
                )
                .await?;
            return Ok(());
        };

        let sender_id: i64 = data
            .split('_')
            .nth(1)
            .context("malformed reply callback data")?
            .parse()
            .context("malformed reply callback user id")?;

        state.fsm.set(
            message.chat.id.0,
            from.id.0 as i64,
            DialogState::WaitingForReply { sender_id },
        );
        state
            .api
            .send_message(message.chat.id, texts::REPLY_PROMPT_TEXT)
            .await?;
        state
            .api
            .answer_callback(callback.id.clone(), None, false)
            .await?;
        Ok(())
    })
    .await
}

pub async fn send_reply_to_user(state: Arc<AppState>, message: Message) -> HandlerResult {
    guarded_message(&message, async {
        let Some(from) = message.from.as_ref() else {
            return Ok(());
        };
        let chat_id = message.chat.id.0;
        let user_id = from.id.0 as i64;

        let Some(DialogState::WaitingForReply { sender_id }) = state.fsm.get(chat_id, user_id)
        else {
            return Ok(());
        };
        state.fsm.clear(chat_id, user_id);

        if sender_id == 0 {
            state
                .api
                .send_message(message.chat.id, texts::REPLY_NO_RECIPIENT_TEXT)
                .await?;
            return Ok(());
        }

        let delivery = async {
            state
                .api
                .send_message(ChatId(sender_id), texts::REPLY_NOTICE_TEXT)
                .await?;
            state
                .api
                .copy_message(ChatId(sender_id), message.chat.id, message.id, None)
                .await?;
            Ok::<(), teloxide::RequestError>(())
        }
        .await;

        match delivery {
            Ok(()) => {
                state.db.increment_received_count(sender_id).await?;
                state.db.increment_answer_streak(sender_id).await?;
                state.db.check_and_grant_achievements(sender_id).await?;

                if let Err(error) = state
                    .api
                    .send_message(message.chat.id, texts::REPLY_SUCCESS_TEXT)
                    .await
                {
                    tracing::error!(%error, "failed to confirm the reply delivery");
                    state
                        .api
                        .send_message(message.chat.id, texts::REPLY_FAILURE_TEXT)
                        .await?;
                }
            }
            Err(error) => {
                tracing::error!(%error, "could not deliver the reply");
                state
                    .api
                    .send_message(message.chat.id, texts::REPLY_FAILURE_TEXT)
                    .await?;
            }
        }

        Ok(())
    })
    .await
}
