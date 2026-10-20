//! Payments, deposits and the ban-appeal (apology) flow.

use std::sync::Arc;

use anyhow::Context;
use teloxide::types::{CallbackQuery, ChatId, LabeledPrice, Message, PreCheckoutQuery};

use crate::app::AppState;
use crate::error::{HandlerResult, guarded_callback, guarded_message, guarded_pre_checkout};
use crate::fsm::DialogState;
use crate::keyboards;
use crate::texts;
use crate::utils::html;

/// Charges the internal balance, or sends a Stars invoice when it is too low.
async fn pay_with_balance_or_invoice(
    state: &AppState,
    user_id: i64,
    price: i64,
    item_type: &str,
    callback: &CallbackQuery,
) -> anyhow::Result<()> {
    let user_stats = state.db.get_user_stats(user_id).await?;

    if user_stats.balance >= price {
        if !state.db.take_balance(price, user_id).await? {
            state
                .api
                .answer_callback(
                    callback.id.clone(),
                    Some(texts::BALANCE_INSUFFICIENT_ALERT),
                    true,
                )
                .await?;
            return Ok(());
        }

        state.db.increment_total_spent_stars(user_id, price).await?;
        state.db.grant_achievement(user_id, "first_donate").await?;

        let reply_text = match item_type {
            "priority" => {
                state.db.increment_priority_messages(user_id).await?;
                Some(texts::BALANCE_PAID_PRIORITY_TEXT)
            }
            "vip" => {
                state.db.set_vip(user_id, true).await?;
                Some(texts::BALANCE_PAID_VIP_TEXT)
            }
            "air" => {
                state.db.increment_air_purchased(user_id).await?;
                Some(texts::BALANCE_PAID_AIR_TEXT)
            }
            _ => None,
        };

        state.db.check_and_grant_achievements(user_id).await?;

        if let (Some(message), Some(reply_text)) = (callback.regular_message(), reply_text) {
            state.api.send_message(message.chat.id, reply_text).await?;
        }
        state
            .api
            .answer_callback(callback.id.clone(), None, false)
            .await?;
    } else {
        let invoice = match item_type {
            "vip" => Some((texts::VIP_INVOICE_TITLE, texts::VIP_INVOICE_PAYLOAD)),
            "air" => Some((texts::AIR_INVOICE_TITLE, texts::AIR_INVOICE_PAYLOAD)),
            _ => None,
        };

        if let Some((title, payload)) = invoice {
            state
                .api
                .send_invoice(
                    user_id,
                    title,
                    &texts::balance_invoice_description(price),
                    payload,
                    vec![LabeledPrice::new(
                        title,
                        u32::try_from(price).unwrap_or_default(),
                    )],
                )
                .await?;
        }

        state
            .api
            .answer_callback(callback.id.clone(), None, false)
            .await?;
    }

    Ok(())
}

pub async fn deposit_menu_handler(state: Arc<AppState>, callback: CallbackQuery) -> HandlerResult {
    guarded_callback(&callback, async {
        if let Some(message) = callback.regular_message() {
            state
                .api
                .send_message_with_markup(
                    message.chat.id,
                    texts::DEPOSIT_MENU_TEXT,
                    keyboards::deposit_keyboard(),
                )
                .await?;
        }
        state
            .api
            .answer_callback(callback.id.clone(), None, false)
            .await?;
        Ok(())
    })
    .await
}

pub async fn send_deposit_invoice(state: Arc<AppState>, callback: CallbackQuery) -> HandlerResult {
    guarded_callback(&callback, async {
        let Some(data) = callback.data.as_deref() else {
            return Ok(());
        };

        let amount: i64 = data
            .split('_')
            .nth(1)
            .context("malformed deposit callback data")?
            .parse()
            .context("malformed deposit amount")?;

        state
            .api
            .send_invoice(
                callback.from.id.0 as i64,
                &texts::deposit_invoice_title(amount),
                &texts::deposit_invoice_description(amount),
                &texts::deposit_invoice_payload(amount),
                vec![LabeledPrice::new(
                    texts::deposit_invoice_label(amount),
                    u32::try_from(amount).unwrap_or_default(),
                )],
            )
            .await?;

        state
            .api
            .answer_callback(callback.id.clone(), None, false)
            .await?;
        Ok(())
    })
    .await
}

pub async fn handle_buy_priority(state: Arc<AppState>, callback: CallbackQuery) -> HandlerResult {
    guarded_callback(&callback, async {
        let user_id = callback.from.id.0 as i64;
        let user_stats = state.db.get_user_stats(user_id).await?;

        if user_stats.balance >= 1 {
            pay_with_balance_or_invoice(&state, user_id, 1, "priority", &callback).await?;
        } else {
            if let Some(message) = callback.regular_message() {
                state
                    .api
                    .send_message_with_markup(
                        message.chat.id,
                        texts::PRIORITY_INSUFFICIENT_TEXT,
                        keyboards::priority_insufficient_keyboard(),
                    )
                    .await?;
            }
            state
                .api
                .answer_callback(callback.id.clone(), None, false)
                .await?;
        }

        Ok(())
    })
    .await
}

pub async fn handle_buy_vip(state: Arc<AppState>, callback: CallbackQuery) -> HandlerResult {
    guarded_callback(&callback, async {
        pay_with_balance_or_invoice(&state, callback.from.id.0 as i64, 100, "vip", &callback).await
    })
    .await
}

pub async fn handle_buy_air(state: Arc<AppState>, callback: CallbackQuery) -> HandlerResult {
    guarded_callback(&callback, async {
        pay_with_balance_or_invoice(&state, callback.from.id.0 as i64, 10, "air", &callback).await
    })
    .await
}

pub async fn handle_buy_apology(state: Arc<AppState>, callback: CallbackQuery) -> HandlerResult {
    guarded_callback(&callback, async {
        let user_id = callback.from.id.0 as i64;

        if !state.db.is_banned(user_id) {
            state
                .api
                .answer_callback(
                    callback.id.clone(),
                    Some(texts::APOLOGY_NOT_BANNED_TEXT),
                    true,
                )
                .await?;
            return Ok(());
        }

        let user_stats = state.db.get_user_stats(user_id).await?;

        if user_stats.balance >= 50 {
            let chat_id = callback
                .regular_message()
                .map_or(user_id, |message| message.chat.id.0);
            state.fsm.set(
                chat_id,
                user_id,
                DialogState::Apology {
                    paid_by_balance: true,
                },
            );

            if let Some(message) = callback.regular_message() {
                state
                    .api
                    .send_message(message.chat.id, texts::APOLOGY_PROMPT_TEXT)
                    .await?;
            }
            state
                .api
                .answer_callback(callback.id.clone(), None, false)
                .await?;
        } else {
            state
                .api
                .send_invoice(
                    user_id,
                    texts::APOLOGY_INVOICE_TITLE,
                    texts::APOLOGY_INVOICE_DESCRIPTION,
                    texts::APOLOGY_INVOICE_PAYLOAD,
                    vec![LabeledPrice::new(texts::APOLOGY_INVOICE_LABEL, 50)],
                )
                .await?;
            state
                .api
                .answer_callback(callback.id.clone(), None, false)
                .await?;
        }

        Ok(())
    })
    .await
}

pub async fn process_pre_checkout(
    state: Arc<AppState>,
    pre_checkout_query: PreCheckoutQuery,
) -> HandlerResult {
    guarded_pre_checkout(&pre_checkout_query, async {
        state
            .api
            .answer_pre_checkout(pre_checkout_query.id.clone())
            .await?;
        Ok(())
    })
    .await
}

pub async fn process_successful_payment(state: Arc<AppState>, message: Message) -> HandlerResult {
    guarded_message(&message, async {
        let (Some(from), Some(payment)) = (message.from.as_ref(), message.successful_payment())
        else {
            return Ok(());
        };

        let user_id = from.id.0 as i64;
        let charge_id = payment.telegram_payment_charge_id.0.clone();
        let payload = payment.invoice_payload.clone();
        let stars_amount = payment.total_amount as i64;

        state.db.register_user(user_id, None).await?;
        let is_created = state
            .db
            .create_payment(&charge_id, user_id, &payload)
            .await?;
        if !is_created {
            return Ok(());
        }

        state
            .db
            .increment_total_spent_stars(user_id, stars_amount)
            .await?;
        state.db.grant_achievement(user_id, "first_donate").await?;

        let mut reply_text: Option<String> = None;

        if payload.starts_with("deposit_") {
            let amount: i64 = payload
                .split('_')
                .nth(1)
                .context("malformed deposit payload")?
                .parse()
                .context("malformed deposit amount")?;
            state.db.give_balance(amount, user_id).await?;
            reply_text = Some(texts::balance_topped_up_text(amount));
        } else if payload == texts::VIP_INVOICE_PAYLOAD {
            state.db.set_vip(user_id, true).await?;
            reply_text = Some(texts::PAYMENT_VIP_TEXT.to_string());
        } else if payload == texts::AIR_INVOICE_PAYLOAD {
            state.db.increment_air_purchased(user_id).await?;
            reply_text = Some(texts::PAYMENT_AIR_TEXT.to_string());
        } else if payload == texts::APOLOGY_INVOICE_PAYLOAD {
            state.fsm.set(
                message.chat.id.0,
                user_id,
                DialogState::Apology {
                    paid_by_balance: false,
                },
            );
            reply_text = Some(texts::PAYMENT_APOLOGY_TEXT.to_string());
        }

        state.db.check_and_grant_achievements(user_id).await?;

        if let Some(reply_text) = reply_text {
            state.api.send_message(message.chat.id, &reply_text).await?;
        }

        Ok(())
    })
    .await
}

pub async fn process_apology_text(state: Arc<AppState>, message: Message) -> HandlerResult {
    guarded_message(&message, async {
        let (Some(from), Some(text)) = (message.from.as_ref(), message.text()) else {
            return Ok(());
        };

        let user_id = from.id.0 as i64;
        let chat_id = message.chat.id.0;
        let paid_by_balance = matches!(
            state.fsm.get(chat_id, user_id),
            Some(DialogState::Apology {
                paid_by_balance: true
            })
        );

        if paid_by_balance && !state.db.take_balance(50, user_id).await? {
            state.fsm.clear(chat_id, user_id);
            state
                .api
                .send_message(message.chat.id, texts::APOLOGY_BALANCE_INSUFFICIENT_TEXT)
                .await?;
            return Ok(());
        }
        state.fsm.clear(chat_id, user_id);

        let anon_code = state.db.get_banned_anon_code_by_user_id(user_id).await?;
        let apology_text = texts::apology_admin_text(&anon_code, user_id, &html::escape_html(text));
        let keyboard = keyboards::apology_admin_keyboard(&anon_code, user_id);

        if let Err(error) = state
            .api
            .send_message_with_markup(ChatId(state.config.admin_id), &apology_text, keyboard)
            .await
        {
            tracing::error!(%error, user_id, "could not send the ban appeal to the admin");
            if paid_by_balance {
                state.db.give_balance(50, user_id).await?;
            }
            state
                .api
                .send_message(message.chat.id, texts::APOLOGY_SEND_ERROR_TEXT)
                .await?;
            return Ok(());
        }

        state
            .api
            .send_message(message.chat.id, texts::APOLOGY_SENT_TEXT)
            .await?;
        Ok(())
    })
    .await
}
