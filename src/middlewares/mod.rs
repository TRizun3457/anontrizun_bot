//! Chat allow-list and rate limiting applied to message updates.

pub mod chat_check;
pub mod throttling;

use std::sync::Arc;

use teloxide::types::Message;

use crate::app::AppState;

/// Returns `true` when the message should reach the handlers.
///
/// Mirrors the middleware order of the original bot: the chat allow-list is
/// checked first, then the throttling middleware.
pub async fn preprocess_message(message: Message, state: Arc<AppState>) -> bool {
    if !chat_check::chat_allowed(&message.chat, state.config.allowed_chat_id) {
        return false;
    }

    state
        .throttle
        .check(&message, &state.bot_username, &state.api)
        .await
}
