//! Admin commands: bans, unbans, balance adjustments, refunds and broadcast.

use std::sync::Arc;

use anyhow::Context;
use futures::stream::{self, StreamExt};
use teloxide::RequestError;
use teloxide::types::{CallbackQuery, ChatId, Message, MessageId};
use teloxide::utils::render::RenderMessageTextHelper;

use crate::app::AppState;
use crate::error::{HandlerResult, guarded_callback, guarded_message};
use crate::keyboards;
use crate::texts;
use crate::utils::retry::request_error_description;
use crate::utils::split::split_maxsplit1;

fn is_admin(state: &AppState, message: &Message) -> bool {
    message
        .from
        .as_ref()
        .is_some_and(|user| user.id.0 as i64 == state.config.admin_id)
}

pub async fn list_banned_codes(state: Arc<AppState>, message: Message) -> HandlerResult {
    guarded_message(&message, async {
        if !is_admin(&state, &message) {
            return Ok(());
        }

        let banned_users = state.db.get_banned_users().await?;
        if banned_users.is_empty() {
            state
                .api
                .send_message(message.chat.id, texts::BANLIST_EMPTY_TEXT)
                .await?;
            return Ok(());
        }

        state
            .api
            .send_message(message.chat.id, &texts::banlist_text(&banned_users))
            .await?;
        Ok(())
    })
    .await
}

pub async fn ban_by_reply(state: Arc<AppState>, message: Message) -> HandlerResult {
    guarded_message(&message, async {
        if !is_admin(&state, &message) {
            return Ok(());
        }

        let Some(reply) = message.reply_to_message() else {
            state
                .api
                .send_message(message.chat.id, texts::BAN_USAGE_TEXT)
                .await?;
            return Ok(());
        };

        let admin_msg_id = reply.id.0 as i64;
        let Some(sender) = state
            .db
            .get_sender_with_code_by_admin_msg(admin_msg_id)
            .await?
        else {
            state
                .api
                .send_message(message.chat.id, texts::BAN_NOT_FOUND_TEXT)
                .await?;
            return Ok(());
        };

        state
            .db
            .ban_user(sender.sender_id, &sender.anon_code)
            .await?;

        let notify_status = match state
            .api
            .send_message_with_markup(
                ChatId(sender.sender_id),
                texts::BAN_NOTICE_TEXT,
                keyboards::ban_notification_keyboard(),
            )
            .await
        {
            Ok(_) => texts::BAN_NOTIFY_OK,
            Err(error) => {
                tracing::error!(%error, "error while sending ban message to user");
                texts::BAN_NOTIFY_FAILED
            }
        };

        state
            .api
            .send_message(
                message.chat.id,
                &texts::ban_success_text(sender.sender_id, &sender.anon_code, notify_status),
            )
            .await?;
        Ok(())
    })
    .await
}

pub async fn unban_by_code(state: Arc<AppState>, message: Message) -> HandlerResult {
    guarded_message(&message, async {
        if !is_admin(&state, &message) || message.text().is_none() {
            return Ok(());
        }

        let (_, args) = split_maxsplit1(message.text().unwrap_or_default());
        let Some(args) = args else {
            state
                .api
                .send_message(message.chat.id, texts::UNBAN_USAGE_TEXT)
                .await?;
            return Ok(());
        };
        let anon_code = args.trim();

        let Some(user_id) = state.db.get_banned_user_id_by_anon_code(anon_code).await? else {
            state
                .api
                .send_message(message.chat.id, texts::UNBAN_NOT_FOUND_TEXT)
                .await?;
            return Ok(());
        };

        let new_code = state.db.unban_user(user_id).await?;

        if let Err(error) = state
            .api
            .send_message(ChatId(user_id), &texts::unban_user_text(&new_code))
            .await
        {
            tracing::error!(%error, "error while sending unblocked message to user");
        }

        state
            .api
            .send_message(
                message.chat.id,
                &texts::unban_result_text(anon_code, &new_code),
            )
            .await?;
        Ok(())
    })
    .await
}

pub async fn accept_unban_handler(state: Arc<AppState>, callback: CallbackQuery) -> HandlerResult {
    guarded_callback(&callback, async {
        if callback.from.id.0 as i64 != state.config.admin_id {
            state
                .api
                .answer_callback(callback.id.clone(), None, false)
                .await?;
            return Ok(());
        }

        let (Some(data), Some(message)) = (callback.data.as_deref(), callback.regular_message())
        else {
            return Ok(());
        };

        let anon_code = data.strip_prefix("accept_unban_").unwrap_or_default();
        let Some(user_id) = state.db.get_banned_user_id_by_anon_code(anon_code).await? else {
            state
                .api
                .answer_callback(
                    callback.id.clone(),
                    Some(texts::ACCEPT_UNBAN_ALREADY_TEXT),
                    true,
                )
                .await?;
            return Ok(());
        };

        let new_code = state.db.unban_user(user_id).await?;

        if let Err(error) = state
            .api
            .send_message(ChatId(user_id), &texts::accept_unban_user_text(&new_code))
            .await
        {
            tracing::error!(%error, "error while sending unban application accept message to user");
        }

        let current_text = message.html_text().unwrap_or_default();
        let edited_text = format!(
            "{current_text}{}",
            texts::accept_unban_edit_suffix(&new_code)
        );
        state
            .api
            .edit_text(message.chat.id, message.id, &edited_text, None)
            .await?;
        state
            .api
            .answer_callback(callback.id.clone(), None, false)
            .await?;
        Ok(())
    })
    .await
}

pub async fn decline_unban_handler(state: Arc<AppState>, callback: CallbackQuery) -> HandlerResult {
    guarded_callback(&callback, async {
        if callback.from.id.0 as i64 != state.config.admin_id {
            state
                .api
                .answer_callback(callback.id.clone(), None, false)
                .await?;
            return Ok(());
        }

        let (Some(data), Some(message)) = (callback.data.as_deref(), callback.regular_message())
        else {
            return Ok(());
        };

        let user_id: i64 = data
            .strip_prefix("decline_unban_")
            .context("malformed decline callback data")?
            .parse()
            .context("malformed decline user id")?;

        if let Err(error) = state
            .api
            .send_message(ChatId(user_id), texts::DECLINE_UNBAN_USER_TEXT)
            .await
        {
            tracing::error!(%error, "error while sending unban application deny message to user");
        }

        let current_text = message.html_text().unwrap_or_default();
        let edited_text = format!("{current_text}{}", texts::DECLINE_UNBAN_EDIT_SUFFIX);
        state
            .api
            .edit_text(message.chat.id, message.id, &edited_text, None)
            .await?;
        state
            .api
            .answer_callback(callback.id.clone(), None, false)
            .await?;
        Ok(())
    })
    .await
}

pub async fn add_balance_cmd(state: Arc<AppState>, message: Message) -> HandlerResult {
    guarded_message(&message, async {
        if !is_admin(&state, &message) || message.text().is_none() {
            return Ok(());
        }

        let (_, args) = split_maxsplit1(message.text().unwrap_or_default());
        let Some(args) = args else {
            state
                .api
                .send_message(message.chat.id, texts::ADD_BALANCE_USAGE_TEXT)
                .await?;
            return Ok(());
        };
        let (identifier, amount_raw) = split_maxsplit1(args);
        let Some(amount_raw) = amount_raw else {
            state
                .api
                .send_message(message.chat.id, texts::ADD_BALANCE_USAGE_TEXT)
                .await?;
            return Ok(());
        };

        let identifier = identifier.unwrap_or_default().trim();

        let Some(target_user_id) = state.db.get_user_id_by_id_or_code(identifier).await? else {
            state
                .api
                .send_message(message.chat.id, texts::ADD_BALANCE_NOT_FOUND_TEXT)
                .await?;
            return Ok(());
        };

        let amount_raw = amount_raw.trim();
        let Ok(amount) = amount_raw.parse::<i64>() else {
            state
                .api
                .send_message(message.chat.id, texts::ADD_BALANCE_INVALID_AMOUNT_TEXT)
                .await?;
            return Ok(());
        };

        state.db.give_balance(amount, target_user_id).await?;
        let stats = state.db.get_user_stats(target_user_id).await?;
        state
            .api
            .send_message(
                message.chat.id,
                &texts::add_balance_result_text(target_user_id, amount, stats.balance),
            )
            .await?;
        Ok(())
    })
    .await
}

pub async fn refund_cmd(state: Arc<AppState>, message: Message) -> HandlerResult {
    guarded_message(&message, async {
        if !is_admin(&state, &message) || message.text().is_none() {
            return Ok(());
        }

        let (_, args) = split_maxsplit1(message.text().unwrap_or_default());
        let Some(args) = args else {
            state
                .api
                .send_message(message.chat.id, texts::REFUND_USAGE_TEXT)
                .await?;
            return Ok(());
        };
        let target = args.trim();

        if target.starts_with("stx_") || !target.chars().all(|c| c.is_ascii_digit()) {
            let charge_id = target.to_string();
            let Some(payment) = state.db.get_payment_by_charge_id(&charge_id).await? else {
                state
                    .api
                    .send_message(message.chat.id, &texts::refund_not_found_text(&charge_id))
                    .await?;
                return Ok(());
            };

            if payment.status == "refunded" {
                state
                    .api
                    .send_message(message.chat.id, &texts::refund_already_text(&charge_id))
                    .await?;
                return Ok(());
            }

            process_single_refund(&state, Some(&message), payment.user_id, &charge_id).await?;
            return Ok(());
        }

        let user_id: i64 = target.parse().context("malformed refund user id")?;
        let successful_payments = state.db.get_success_charge_ids_by_user_id(user_id).await?;

        if successful_payments.is_empty() {
            state
                .api
                .send_message(message.chat.id, &texts::refund_no_payments_text(user_id))
                .await?;
            return Ok(());
        }

        let status_message = state
            .api
            .send_message(
                message.chat.id,
                &texts::refund_started_text(user_id, successful_payments.len()),
            )
            .await?;

        let mut success_count = 0u64;
        let mut fail_count = 0u64;

        for charge_id in &successful_payments {
            let is_success = process_single_refund(&state, None, user_id, charge_id).await?;
            if is_success {
                success_count += 1;
            } else {
                fail_count += 1;
            }
        }

        state
            .api
            .edit_text(
                status_message.chat.id,
                status_message.id,
                &texts::refund_result_text(user_id, success_count, fail_count),
                None,
            )
            .await?;
        Ok(())
    })
    .await
}

async fn process_single_refund(
    state: &AppState,
    message: Option<&Message>,
    user_id: i64,
    charge_id: &str,
) -> anyhow::Result<bool> {
    let is_updated = state
        .db
        .set_payment_status_if_current(charge_id, "success", "refund_pending")
        .await?;

    if !is_updated {
        if let Some(message) = message {
            state
                .api
                .send_message(message.chat.id, &texts::refund_busy_text(charge_id))
                .await?;
        }
        return Ok(false);
    }

    match state.api.refund_star_payment(user_id, charge_id).await {
        Ok(_) => {
            state
                .db
                .set_payment_status_by_charge_id(charge_id, "refunded")
                .await?;

            if let Some(message) = message {
                state
                    .api
                    .send_message(
                        message.chat.id,
                        &texts::refund_success_text(charge_id, user_id),
                    )
                    .await?;
            }
            Ok(true)
        }
        Err(error) => {
            tracing::error!(%error, charge_id, "Refund error via Telegram API");
            state
                .db
                .set_payment_status_by_charge_id(charge_id, "refund_failed")
                .await?;

            if let Some(message) = message {
                state
                    .api
                    .send_message(
                        message.chat.id,
                        &texts::refund_error_text(charge_id, &request_error_description(&error)),
                    )
                    .await?;
            }
            Ok(false)
        }
    }
}

async fn broadcast_one(
    state: &AppState,
    user_id: i64,
    source: Option<(ChatId, MessageId)>,
    text_to_send: Option<&str>,
) -> bool {
    loop {
        let result = if let Some((from_chat_id, message_id)) = source {
            state
                .api
                .copy_message(ChatId(user_id), from_chat_id, message_id, None)
                .await
                .map(|_| ())
        } else if let Some(text) = text_to_send {
            state
                .api
                .send_message(ChatId(user_id), text)
                .await
                .map(|_| ())
        } else {
            return true;
        };

        match result {
            Ok(()) => return true,
            Err(RequestError::RetryAfter(seconds)) => {
                tokio::time::sleep(seconds.duration()).await;
            }
            Err(error) => {
                tracing::debug!(%error, user_id, "broadcast delivery failed");
                return false;
            }
        }
    }
}

pub async fn broadcast_cmd(state: Arc<AppState>, message: Message) -> HandlerResult {
    guarded_message(&message, async {
        if !is_admin(&state, &message) {
            return Ok(());
        }

        let has_reply = message.reply_to_message().is_some();
        let has_text_argument = message
            .text()
            .is_some_and(|text| split_maxsplit1(text).1.is_some());

        if !has_reply && !has_text_argument {
            state
                .api
                .send_message(message.chat.id, texts::BROADCAST_INSTRUCTION_TEXT)
                .await?;
            return Ok(());
        }

        let user_ids = state.db.get_all_user_ids().await?;
        let status_message = state
            .api
            .send_message(
                message.chat.id,
                &texts::broadcast_started_text(user_ids.len()),
            )
            .await?;

        let source: Option<(ChatId, MessageId)> = message
            .reply_to_message()
            .map(|reply| (reply.chat.id, reply.id));
        let text_to_send: Option<String> = if source.is_none() {
            message
                .text()
                .and_then(|text| split_maxsplit1(text).1)
                .map(str::to_string)
        } else {
            None
        };

        let mut deliveries = stream::iter(user_ids.into_iter().map(|user_id| {
            let state = state.clone();
            let text_to_send = text_to_send.clone();
            async move { broadcast_one(&state, user_id, source, text_to_send.as_deref()).await }
        }))
        .buffer_unordered(20);

        let mut success_count = 0u64;
        let mut fail_count = 0u64;

        while let Some(is_success) = deliveries.next().await {
            if is_success {
                success_count += 1;
            } else {
                fail_count += 1;
            }
        }

        state
            .api
            .edit_text(
                status_message.chat.id,
                status_message.id,
                &texts::broadcast_result_text(success_count, fail_count),
                None,
            )
            .await?;
        Ok(())
    })
    .await
}
