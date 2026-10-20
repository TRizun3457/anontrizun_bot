//! Handler modules and the dispatcher schema.
//!
//! Branch order mirrors the original router registration order:
//! `handlers/payments.py`, `handlers/admin.py`, then the `handlers/user`
//! package (`start`, `profile`, `settings`, `inline`, `reply`, `forward`).

pub mod admin;
pub mod payments;
pub mod user;

use std::sync::Arc;

use teloxide::{
    dispatching::{DpHandlerDescription, UpdateFilterExt, UpdateHandler},
    dptree,
    types::{CallbackQuery, Message, Update},
};

use crate::app::AppState;
use crate::error::HandlerError;
use crate::fsm::DialogState;
use crate::middlewares::preprocess_message;
use crate::utils::command;

pub type Schema = UpdateHandler<HandlerError>;

fn from_id(message: &Message) -> Option<i64> {
    message.from.as_ref().map(|user| user.id.0 as i64)
}

fn is_command(message: &Message, expected: &str, state: &AppState) -> bool {
    command::message_text(message)
        .is_some_and(|text| command::extract_command(text, expected, &state.bot_username).is_some())
}

fn is_private(message: &Message) -> bool {
    message.chat.is_private()
}

/// All message updates, in the same order as the original routers.
fn message_branch()
-> teloxide::dptree::Handler<'static, Result<(), HandlerError>, DpHandlerDescription> {
    Update::filter_message()
        .filter_async(preprocess_message)
        // handlers/payments.py
        .branch(
            dptree::filter(|message: Message| message.successful_payment().is_some())
                .endpoint(payments::process_successful_payment),
        )
        .branch(
            dptree::filter(|message: Message, state: Arc<AppState>| {
                let has_state = from_id(&message).is_some_and(|user_id| {
                    matches!(
                        state.fsm.get(message.chat.id.0, user_id),
                        Some(DialogState::Apology { .. })
                    )
                });
                let Some(text) = message.text() else {
                    return false;
                };
                has_state && !text.is_empty() && !text.starts_with('/')
            })
            .endpoint(payments::process_apology_text),
        )
        // handlers/admin.py
        .branch(
            dptree::filter(|message: Message, state: Arc<AppState>| {
                is_command(&message, "banlist", &state)
            })
            .endpoint(admin::list_banned_codes),
        )
        .branch(
            dptree::filter(|message: Message, state: Arc<AppState>| {
                is_command(&message, "ban", &state)
            })
            .endpoint(admin::ban_by_reply),
        )
        .branch(
            dptree::filter(|message: Message, state: Arc<AppState>| {
                is_command(&message, "unban", &state)
            })
            .endpoint(admin::unban_by_code),
        )
        .branch(
            dptree::filter(|message: Message, state: Arc<AppState>| {
                is_command(&message, "addbalance", &state)
            })
            .endpoint(admin::add_balance_cmd),
        )
        .branch(
            dptree::filter(|message: Message, state: Arc<AppState>| {
                is_command(&message, "refund", &state)
            })
            .endpoint(admin::refund_cmd),
        )
        .branch(
            dptree::filter(|message: Message, state: Arc<AppState>| {
                is_command(&message, "broadcast", &state)
            })
            .endpoint(admin::broadcast_cmd),
        )
        // handlers/user/start.py
        .branch(
            dptree::filter(|message: Message, state: Arc<AppState>| {
                is_command(&message, "anon", &state)
            })
            .endpoint(user::start::anon_group_cmd),
        )
        .branch(
            dptree::filter(|message: Message, state: Arc<AppState>| {
                is_command(&message, "start", &state)
            })
            .endpoint(user::start::start_cmd),
        )
        // handlers/user/profile.py
        .branch(
            dptree::filter(|message: Message, state: Arc<AppState>| {
                is_private(&message) && is_command(&message, "status", &state)
            })
            .endpoint(user::profile::show_status_message),
        )
        // handlers/user/settings.py
        .branch(
            dptree::filter(|message: Message, state: Arc<AppState>| {
                is_private(&message) && is_command(&message, "settings", &state)
            })
            .endpoint(user::settings::show_settings_menu_message),
        )
        // handlers/user/reply.py
        .branch(
            dptree::filter(|message: Message, state: Arc<AppState>| {
                from_id(&message).is_some_and(|user_id| {
                    matches!(
                        state.fsm.get(message.chat.id.0, user_id),
                        Some(DialogState::WaitingForReply { .. })
                    )
                })
            })
            .endpoint(user::reply::send_reply_to_user),
        )
        // handlers/user/forward.py
        .branch(
            dptree::filter(|message: Message| {
                is_private(&message) && user::helpers::is_plain_message(&message)
            })
            .endpoint(user::forward::forward_anonymous_msg),
        )
        .endpoint(|_: Message| async { Ok(()) })
}

/// All callback-query updates, in router registration order.
fn callback_branch()
-> teloxide::dptree::Handler<'static, Result<(), HandlerError>, DpHandlerDescription> {
    let data_is = |expected: &'static str| {
        move |callback: CallbackQuery| callback.data.as_deref() == Some(expected)
    };
    let data_starts_with = |prefix: &'static str| {
        move |callback: CallbackQuery| {
            callback
                .data
                .as_deref()
                .is_some_and(|data| data.starts_with(prefix))
        }
    };

    Update::filter_callback_query()
        // handlers/payments.py
        .branch(dptree::filter(data_is("deposit_menu")).endpoint(payments::deposit_menu_handler))
        .branch(dptree::filter(data_starts_with("dep_")).endpoint(payments::send_deposit_invoice))
        .branch(dptree::filter(data_is("buy_priority")).endpoint(payments::handle_buy_priority))
        .branch(dptree::filter(data_is("buy_vip")).endpoint(payments::handle_buy_vip))
        .branch(dptree::filter(data_is("buy_air")).endpoint(payments::handle_buy_air))
        .branch(dptree::filter(data_is("buy_apology")).endpoint(payments::handle_buy_apology))
        // handlers/admin.py
        .branch(
            dptree::filter(data_starts_with("accept_unban_")).endpoint(admin::accept_unban_handler),
        )
        .branch(
            dptree::filter(data_starts_with("decline_unban_"))
                .endpoint(admin::decline_unban_handler),
        )
        // handlers/user/profile.py
        .branch(dptree::filter(data_is("my_status")).endpoint(user::profile::show_status_callback))
        .branch(
            dptree::filter(data_is("my_achievements"))
                .endpoint(user::profile::show_achievements_callback),
        )
        // handlers/user/settings.py
        .branch(
            dptree::filter(data_is("settings_menu"))
                .endpoint(user::settings::show_settings_menu_callback),
        )
        .branch(
            dptree::filter(data_is("settings_refresh_code"))
                .endpoint(user::settings::handle_refresh_code_manual),
        )
        .branch(
            dptree::filter(data_is("settings_toggle_autorefresh"))
                .endpoint(user::settings::handle_toggle_autorefresh),
        )
        .branch(
            dptree::filter(data_is("settings_toggle_cats"))
                .endpoint(user::settings::handle_toggle_cats),
        )
        .branch(
            dptree::filter(data_is("settings_share_menu"))
                .endpoint(user::settings::show_share_settings_menu),
        )
        .branch(
            dptree::filter(data_starts_with("toggle_share_vis_"))
                .endpoint(user::settings::handle_toggle_share_visibility),
        )
        // handlers/user/reply.py
        .branch(
            dptree::filter(data_starts_with("reply_")).endpoint(user::reply::handle_reply_button),
        )
        .endpoint(|_: CallbackQuery| async { Ok(()) })
}

/// Full update dispatch tree.
pub fn schema() -> Schema {
    dptree::entry()
        .branch(message_branch())
        .branch(callback_branch())
        .branch(Update::filter_inline_query().endpoint(user::inline::inline_query_handler))
        .branch(Update::filter_pre_checkout_query().endpoint(payments::process_pre_checkout))
}
