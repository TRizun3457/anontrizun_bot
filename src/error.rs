//! Per-endpoint error guard replacing aiogram's `ErrorGuardMiddleware`.
//!
//! Handlers are wrapped with [`guarded_message`], [`guarded_callback`],
//! [`guarded_inline`] or [`guarded_pre_checkout`]. On failure the error is
//! tagged with the fallback that must be delivered to the user, and
//! [`Guard`] (installed as the dispatcher error handler) performs that
//! delivery, suppressing its own errors just like the original middleware.

use std::{fmt, sync::Arc};

use futures::future::BoxFuture;
use teloxide::{
    error_handlers::ErrorHandler,
    types::{
        CallbackQuery, CallbackQueryId, ChatId, InlineQuery, InlineQueryId, Message,
        MessageEntityKind, PreCheckoutQuery,
    },
};

use crate::api::Api;
use crate::texts;

/// Where a failure should be reported back to the user.
#[derive(Clone, Debug)]
pub enum Fallback {
    Inline(InlineQueryId),
    Callback(CallbackQueryId),
    Message { chat_id: ChatId, addressed: bool },
    None,
}

#[derive(Debug)]
pub struct HandlerError {
    pub source: anyhow::Error,
    pub fallback: Fallback,
}

/// Result type returned by every endpoint.
pub type HandlerResult = Result<(), HandlerError>;

impl fmt::Display for HandlerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}", self.source)
    }
}

impl std::error::Error for HandlerError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(self.source.as_ref())
    }
}

/// Mirrors `is_addressed_to_bot` from the original error guard.
pub fn message_addressed_to_bot(message: &Message) -> bool {
    if message.chat.is_private() {
        return true;
    }

    message.entities().is_some_and(|entities| {
        entities
            .iter()
            .any(|entity| entity.kind == MessageEntityKind::BotCommand)
    })
}

macro_rules! guard {
    ($event:expr, $future:expr, $fallback:expr) => {{
        match $future.await {
            Ok(()) => Ok(()),
            Err(source) => Err(HandlerError {
                source,
                fallback: $fallback($event),
            }),
        }
    }};
}

pub async fn guarded_message<F>(message: &Message, future: F) -> Result<(), HandlerError>
where
    F: std::future::Future<Output = anyhow::Result<()>>,
{
    guard!(message, future, |message: &Message| Fallback::Message {
        chat_id: message.chat.id,
        addressed: message_addressed_to_bot(message),
    })
}

pub async fn guarded_callback<F>(callback: &CallbackQuery, future: F) -> Result<(), HandlerError>
where
    F: std::future::Future<Output = anyhow::Result<()>>,
{
    guard!(callback, future, |callback: &CallbackQuery| {
        Fallback::Callback(callback.id.clone())
    })
}

pub async fn guarded_inline<F>(inline_query: &InlineQuery, future: F) -> Result<(), HandlerError>
where
    F: std::future::Future<Output = anyhow::Result<()>>,
{
    guard!(inline_query, future, |inline_query: &InlineQuery| {
        Fallback::Inline(inline_query.id.clone())
    })
}

pub async fn guarded_pre_checkout<F>(
    _pre_checkout_query: &PreCheckoutQuery,
    future: F,
) -> Result<(), HandlerError>
where
    F: std::future::Future<Output = anyhow::Result<()>>,
{
    match future.await {
        Ok(()) => Ok(()),
        Err(source) => Err(HandlerError {
            source,
            fallback: Fallback::None,
        }),
    }
}

/// Dispatcher error handler delivering the recorded fallback.
pub struct Guard {
    api: Api,
}

impl Guard {
    pub fn new(api: Api) -> Self {
        Self { api }
    }
}

impl ErrorHandler<HandlerError> for Guard {
    fn handle_error(self: Arc<Self>, error: HandlerError) -> BoxFuture<'static, ()> {
        Box::pin(async move {
            tracing::error!(error = ?error.source, "handler failed");

            match error.fallback {
                Fallback::Inline(inline_query_id) => {
                    if let Err(error) = self.api.answer_inline(inline_query_id, Vec::new()).await {
                        tracing::error!(%error, "failed to answer inline query after an error");
                    }
                }
                Fallback::Callback(callback_query_id) => {
                    if let Err(error) = self
                        .api
                        .answer_callback(
                            callback_query_id,
                            Some(texts::ERROR_GUARD_CALLBACK_TEXT),
                            true,
                        )
                        .await
                    {
                        tracing::error!(%error, "failed to answer callback after an error");
                    }
                }
                Fallback::Message { chat_id, addressed } => {
                    if addressed
                        && let Err(error) = self
                            .api
                            .send_message(chat_id, texts::ERROR_GUARD_MESSAGE_TEXT)
                            .await
                    {
                        tracing::error!(%error, "failed to send error notice");
                    }
                }
                Fallback::None => {}
            }
        })
    }
}
