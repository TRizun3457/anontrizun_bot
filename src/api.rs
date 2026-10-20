//! Thin wrapper around [`teloxide::Bot`] that applies the original retry
//! policy: network failures are retried for most methods, while
//! `sendMessage`, `copyMessage` and `refundStarPayment` are sent at most once.

use teloxide::{
    Bot, RequestError,
    payloads::{
        AnswerCallbackQuerySetters, AnswerInlineQuerySetters, CopyMessageSetters,
        EditMessageTextSetters, SendMessageSetters,
    },
    prelude::Requester,
    types::{
        CallbackQueryId, ChatId, InlineKeyboardMarkup, InlineQueryId, InlineQueryResult,
        LabeledPrice, Me, Message, MessageId, ParseMode, PreCheckoutQueryId, TelegramTransactionId,
        True, UserId,
    },
};

use crate::utils::retry::retry_request;

#[derive(Clone)]
pub struct Api {
    bot: Bot,
}

impl Api {
    pub fn new(bot: Bot) -> Self {
        Self { bot }
    }

    pub fn bot(&self) -> &Bot {
        &self.bot
    }

    /// `getMe`, retried on network failures.
    pub async fn get_me(&self) -> Result<Me, RequestError> {
        retry_request(self.bot.get_me()).await
    }

    /// `sendMessage` without a parse mode (used by the throttling notice).
    ///
    /// Like the original `RetrySession`, this method is never retried.
    pub async fn send_plain_message(
        &self,
        chat_id: ChatId,
        text: &str,
    ) -> Result<Message, RequestError> {
        self.bot.send_message(chat_id, text).await
    }

    /// `sendMessage` with HTML parse mode. Never retried.
    pub async fn send_message(&self, chat_id: ChatId, text: &str) -> Result<Message, RequestError> {
        self.bot
            .send_message(chat_id, text)
            .parse_mode(ParseMode::Html)
            .await
    }

    /// `sendMessage` with HTML parse mode and an inline keyboard. Never retried.
    pub async fn send_message_with_markup(
        &self,
        chat_id: ChatId,
        text: &str,
        reply_markup: InlineKeyboardMarkup,
    ) -> Result<Message, RequestError> {
        self.bot
            .send_message(chat_id, text)
            .parse_mode(ParseMode::Html)
            .reply_markup(reply_markup)
            .await
    }

    /// `editMessageText` with HTML parse mode, retried on network failures.
    pub async fn edit_text(
        &self,
        chat_id: ChatId,
        message_id: MessageId,
        text: &str,
        reply_markup: Option<InlineKeyboardMarkup>,
    ) -> Result<Message, RequestError> {
        let mut request = self
            .bot
            .edit_message_text(chat_id, message_id, text)
            .parse_mode(ParseMode::Html);

        if let Some(reply_markup) = reply_markup {
            request = request.reply_markup(reply_markup);
        }

        retry_request(request).await
    }

    /// `copyMessage`. Never retried, matching the original policy.
    pub async fn copy_message(
        &self,
        chat_id: ChatId,
        from_chat_id: ChatId,
        message_id: MessageId,
        reply_markup: Option<InlineKeyboardMarkup>,
    ) -> Result<MessageId, RequestError> {
        let mut request = self.bot.copy_message(chat_id, from_chat_id, message_id);

        if let Some(reply_markup) = reply_markup {
            request = request.reply_markup(reply_markup);
        }

        request.await
    }

    /// `sendInvoice` for Telegram Stars, retried on network failures.
    pub async fn send_invoice(
        &self,
        chat_id: i64,
        title: &str,
        description: &str,
        payload: &str,
        prices: Vec<LabeledPrice>,
    ) -> Result<Message, RequestError> {
        retry_request(self.bot.send_invoice(
            ChatId(chat_id),
            title,
            description,
            payload,
            "XTR",
            prices,
        ))
        .await
    }

    /// `answerCallbackQuery`, retried on network failures.
    pub async fn answer_callback(
        &self,
        callback_query_id: CallbackQueryId,
        text: Option<&str>,
        show_alert: bool,
    ) -> Result<True, RequestError> {
        let mut request = self.bot.answer_callback_query(callback_query_id);

        if let Some(text) = text {
            request = request.text(text.to_string());
        }
        if show_alert {
            request = request.show_alert(true);
        }

        retry_request(request).await
    }

    /// `answerInlineQuery` with `cache_time = 1` and `is_personal = true`.
    pub async fn answer_inline(
        &self,
        inline_query_id: InlineQueryId,
        results: Vec<InlineQueryResult>,
    ) -> Result<True, RequestError> {
        retry_request(
            self.bot
                .answer_inline_query(inline_query_id, results)
                .cache_time(1)
                .is_personal(true),
        )
        .await
    }

    /// `answerPreCheckoutQuery(ok = true)`.
    pub async fn answer_pre_checkout(
        &self,
        pre_checkout_query_id: PreCheckoutQueryId,
    ) -> Result<True, RequestError> {
        retry_request(
            self.bot
                .answer_pre_checkout_query(pre_checkout_query_id, true),
        )
        .await
    }

    /// `refundStarPayment`. Never retried, matching the original policy.
    pub async fn refund_star_payment(
        &self,
        user_id: i64,
        charge_id: &str,
    ) -> Result<True, RequestError> {
        self.bot
            .refund_star_payment(
                UserId(user_id as u64),
                TelegramTransactionId(charge_id.to_string()),
            )
            .await
    }
}
