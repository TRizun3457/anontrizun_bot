//! Golden-text tests.
//!
//! Every user-visible string is compared byte-for-byte with the output of the
//! original Python handlers. The fixtures in `tests/fixtures/texts.json` were
//! produced by running the Python implementation (with the Telegram client and
//! database stubbed out) once, so this file proves the Rust port is
//! message-identical. Every fixture must be consumed by a check below.

use std::collections::{BTreeMap, BTreeSet};

use anontrizun_bot::achievements;
use anontrizun_bot::constants::{CAT_KAOMOJI_LIST, cat_string};
use anontrizun_bot::db::models::{BannedUser, UserStats};
use anontrizun_bot::keyboards;
use anontrizun_bot::texts;
use anontrizun_bot::utils::html::escape_html;
use teloxide::types::{InlineKeyboardButtonKind, InlineKeyboardMarkup};

const NEUTRAL_CAT: &str = "";

fn fixtures() -> BTreeMap<String, String> {
    serde_json::from_str(include_str!("fixtures/texts.json")).expect("valid fixtures")
}

/// The kaomoji the fixture generator always picked: the first list entry.
fn golden_cat() -> String {
    cat_string(CAT_KAOMOJI_LIST[0])
}

struct Golden {
    fixtures: BTreeMap<String, String>,
    checked: BTreeSet<String>,
}

impl Golden {
    fn new() -> Self {
        Self {
            fixtures: fixtures(),
            checked: BTreeSet::new(),
        }
    }

    fn check(&mut self, name: &str, actual: String) {
        let expected = self
            .fixtures
            .get(name)
            .unwrap_or_else(|| panic!("missing fixture `{name}`"));
        assert_eq!(&actual, expected, "golden mismatch for `{name}`");
        self.checked.insert(name.to_string());
    }

    fn check_str(&mut self, name: &str, actual: &str) {
        self.check(name, actual.to_string());
    }

    fn finish(self) {
        let unused: Vec<&String> = self
            .fixtures
            .keys()
            .filter(|key| !self.checked.contains(*key))
            .collect();
        assert!(unused.is_empty(), "fixtures never checked: {unused:?}");
    }
}

fn callback_button(markup: &InlineKeyboardMarkup, row: usize, col: usize) -> (String, String) {
    let button = &markup.inline_keyboard[row][col];
    match &button.kind {
        InlineKeyboardButtonKind::CallbackData(data) => (button.text.clone(), data.clone()),
        other => panic!("expected a callback button, got {other:?}"),
    }
}

fn url_button(markup: &InlineKeyboardMarkup, row: usize, col: usize) -> (String, String) {
    let button = &markup.inline_keyboard[row][col];
    match &button.kind {
        InlineKeyboardButtonKind::Url(url) => (button.text.clone(), url.to_string()),
        other => panic!("expected a URL button, got {other:?}"),
    }
}

fn plain_stats(anon_code: &str) -> UserStats {
    UserStats {
        anon_code: anon_code.to_string(),
        ..UserStats::default()
    }
}

fn vip_stats() -> UserStats {
    UserStats {
        balance: 250,
        sent_count: 12,
        received_count: 7,
        priority_messages: 4,
        air_purchased: 3,
        is_vip: true,
        anon_code: "VIP12345".to_string(),
        ..UserStats::default()
    }
}

#[test]
fn golden_texts_match_the_python_implementation() {
    let mut golden = Golden::new();

    // --- /start and /anon ------------------------------------------------
    golden.check_str("start.admin_panel", texts::ADMIN_PANEL_TEXT);
    golden.check_str("start.banned", texts::START_BANNED_TEXT);
    golden.check_str("start.private", texts::START_PRIVATE_TEXT);
    golden.check_str("start.anon_group", texts::ANON_GROUP_TEXT);
    golden.check_str("start.anon_private", texts::ANON_PRIVATE_TEXT);

    // --- profile ---------------------------------------------------------
    golden.check(
        "profile.vip",
        texts::profile_text(&vip_stats(), 42, false, 5, &golden_cat()),
    );
    golden.check(
        "profile.plain",
        texts::profile_text(&plain_stats("PLAIN123"), 42, false, 1, NEUTRAL_CAT),
    );
    golden.check(
        "profile.banned",
        texts::profile_text(
            &UserStats {
                air_purchased: 3,
                ..plain_stats("BANNED12")
            },
            42,
            true,
            2,
            NEUTRAL_CAT,
        ),
    );
    golden.check("profile.achievements_empty", texts::achievements_text(&[]));
    golden.check(
        "profile.achievements_list",
        texts::achievements_text(&["anon_first".to_string(), "vip_access".to_string()]),
    );

    // --- settings and sharing --------------------------------------------
    golden.check(
        "settings.menu",
        texts::settings_text(&UserStats {
            code_auto_refresh: "daily".to_string(),
            ..plain_stats("ABCD1234")
        }),
    );

    let preview_vip =
        texts::share_preview_text(&vip_stats(), 5, achievements::total_count(), &golden_cat());
    golden.check_str("share.preview_vip", &preview_vip);

    // The share menu screen was captured with the priority row hidden.
    let share_menu_stats = UserStats {
        show_priority: false,
        ..vip_stats()
    };
    golden.check(
        "settings.share_menu",
        texts::share_settings_text(&texts::share_preview_text(
            &share_menu_stats,
            5,
            achievements::total_count(),
            &golden_cat(),
        )),
    );
    golden.check(
        "share.preview_hidden",
        texts::share_preview_text(
            &UserStats {
                priority_messages: 2,
                air_purchased: 1,
                show_sent: false,
                show_received: false,
                show_achievements: false,
                ..UserStats::default()
            },
            3,
            achievements::total_count(),
            NEUTRAL_CAT,
        ),
    );

    // --- inline sharing ---------------------------------------------------
    golden.check_str("inline.admin_text", texts::INLINE_ADMIN_SHARE_TEXT);
    golden.check_str("inline.admin_title", texts::INLINE_ADMIN_TITLE);
    golden.check_str("inline.admin_description", texts::INLINE_ADMIN_DESCRIPTION);
    golden.check_str("inline.user_description", texts::INLINE_STATS_DESCRIPTION);
    golden.check_str(
        "inline.user_text",
        &texts::share_preview_text(
            &plain_stats("ABCD1234"),
            2,
            achievements::total_count(),
            NEUTRAL_CAT,
        ),
    );
    golden.check_str("inline.user_title", texts::INLINE_STATS_TITLE);
    golden.check_str("inline.vip_title", texts::inline_share_title(&vip_stats()));
    golden.check_str("inline.admin_id", "admin_share");
    golden.check_str("inline.user_id", "user_status_share");

    let admin_keyboard = keyboards::inline_admin_keyboard("anontrizun_bot").unwrap();
    let (text, url) = url_button(&admin_keyboard, 0, 0);
    golden.check("inline.admin_button_text", text);
    golden.check("inline.admin_button_url", url);

    let user_keyboard = keyboards::inline_user_keyboard("anontrizun_bot").unwrap();
    let (text, url) = url_button(&user_keyboard, 0, 0);
    golden.check("inline.user_button_text", text);
    golden.check("inline.user_button_url", url);

    // --- anonymous forwarding --------------------------------------------
    golden.check_str("forward.banned", texts::FORWARD_BANNED_TEXT);
    golden.check_str("forward.vip_banner", texts::FORWARD_VIP_BANNER);
    golden.check_str("forward.priority_banner", texts::FORWARD_PRIORITY_BANNER);
    golden.check_str("forward.confirm", texts::FORWARD_CONFIRM_TEXT);
    golden.check_str("forward.confirm_priority", texts::FORWARD_CONFIRM_PRIORITY);

    let reply_keyboard = keyboards::reply_keyboard(42);
    let (text, data) = callback_button(&reply_keyboard, 0, 0);
    golden.check("forward.reply_button_text", text);
    golden.check("forward.reply_button_data", data);

    // --- replies from the admin ------------------------------------------
    golden.check_str("reply.prompt", texts::REPLY_PROMPT_TEXT);
    golden.check_str("reply.notice", texts::REPLY_NOTICE_TEXT);
    golden.check_str("reply.success", texts::REPLY_SUCCESS_TEXT);
    golden.check_str("reply.button_error", texts::REPLY_BUTTON_ERROR_TEXT);
    golden.check_str("reply.no_recipient", texts::REPLY_NO_RECIPIENT_TEXT);

    // --- payments ---------------------------------------------------------
    golden.check_str("payments.deposit_menu", texts::DEPOSIT_MENU_TEXT);
    golden.check(
        "payments.deposit_invoice.title",
        texts::deposit_invoice_title(100),
    );
    golden.check(
        "payments.deposit_invoice.description",
        texts::deposit_invoice_description(100),
    );
    golden.check(
        "payments.deposit_invoice.payload",
        texts::deposit_invoice_payload(100),
    );
    golden.check(
        "payments.deposit_invoice.label",
        texts::deposit_invoice_label(100),
    );
    golden.check_str("payments.deposit_invoice.amount", "100");
    golden.check_str("payments.deposit_invoice.currency", "XTR");

    golden.check_str("payments.vip_invoice.title", texts::VIP_INVOICE_TITLE);
    golden.check_str("payments.vip_invoice.payload", texts::VIP_INVOICE_PAYLOAD);
    golden.check_str("payments.vip_invoice.label", texts::VIP_INVOICE_TITLE);
    golden.check(
        "payments.vip_invoice.description",
        texts::balance_invoice_description(100),
    );
    golden.check_str("payments.vip_invoice.amount", "100");
    golden.check_str("payments.vip_invoice.currency", "XTR");

    golden.check_str("payments.air_invoice.title", texts::AIR_INVOICE_TITLE);
    golden.check_str("payments.air_invoice.payload", texts::AIR_INVOICE_PAYLOAD);
    golden.check_str("payments.air_invoice.label", texts::AIR_INVOICE_TITLE);
    golden.check(
        "payments.air_invoice.description",
        texts::balance_invoice_description(10),
    );
    golden.check_str("payments.air_invoice.amount", "10");
    golden.check_str("payments.air_invoice.currency", "XTR");

    golden.check_str(
        "payments.priority_insufficient",
        texts::PRIORITY_INSUFFICIENT_TEXT,
    );
    let (text, _) = callback_button(&keyboards::priority_insufficient_keyboard(), 0, 0);
    golden.check("payments.priority_insufficient.button", text);

    golden.check_str("payments.priority_paid", texts::BALANCE_PAID_PRIORITY_TEXT);
    golden.check_str("payments.vip_paid", texts::BALANCE_PAID_VIP_TEXT);
    golden.check_str("payments.air_paid", texts::BALANCE_PAID_AIR_TEXT);

    golden.check_str(
        "payments.apology_not_banned",
        texts::APOLOGY_NOT_BANNED_TEXT,
    );
    golden.check_str("payments.apology_prompt", texts::APOLOGY_PROMPT_TEXT);
    golden.check_str(
        "payments.apology_invoice.title",
        texts::APOLOGY_INVOICE_TITLE,
    );
    golden.check_str(
        "payments.apology_invoice.description",
        texts::APOLOGY_INVOICE_DESCRIPTION,
    );
    golden.check_str(
        "payments.apology_invoice.payload",
        texts::APOLOGY_INVOICE_PAYLOAD,
    );
    golden.check_str(
        "payments.apology_invoice.label",
        texts::APOLOGY_INVOICE_LABEL,
    );
    golden.check_str("payments.apology_invoice.amount", "50");
    golden.check_str("payments.apology_invoice.currency", "XTR");
    golden.check_str("payments.apology_sent", texts::APOLOGY_SENT_TEXT);
    golden.check_str(
        "payments.apology_insufficient",
        texts::APOLOGY_BALANCE_INSUFFICIENT_TEXT,
    );
    golden.check(
        "payments.apology_admin",
        texts::apology_admin_text("BANNED12", 42, &escape_html("Простите меня <за всё>")),
    );
    let (_, data) = callback_button(&keyboards::apology_admin_keyboard("BANNED12", 42), 0, 0);
    golden.check("payments.apology_admin.button_data", data);

    golden.check(
        "payments.successful_payment.deposit",
        texts::balance_topped_up_text(100),
    );
    golden.check_str("payments.successful_payment.vip", texts::PAYMENT_VIP_TEXT);
    golden.check_str("payments.successful_payment.air", texts::PAYMENT_AIR_TEXT);
    golden.check_str(
        "payments.successful_payment.apology",
        texts::PAYMENT_APOLOGY_TEXT,
    );

    // --- admin commands ---------------------------------------------------
    golden.check_str("admin.banlist_empty", texts::BANLIST_EMPTY_TEXT);
    golden.check(
        "admin.banlist",
        texts::banlist_text(&[
            BannedUser {
                user_id: 42,
                anon_code: "ABCD1234".to_string(),
            },
            BannedUser {
                user_id: 99,
                anon_code: "WXYZ9999".to_string(),
            },
        ]),
    );
    golden.check_str("admin.ban_usage", texts::BAN_USAGE_TEXT);
    golden.check_str("admin.ban_not_found", texts::BAN_NOT_FOUND_TEXT);
    golden.check_str("admin.ban_notice", texts::BAN_NOTICE_TEXT);
    golden.check(
        "admin.ban_success",
        texts::ban_success_text(42, "ABCD1234", texts::BAN_NOTIFY_OK),
    );
    let (text, data) = callback_button(&keyboards::ban_notification_keyboard(), 0, 0);
    golden.check("admin.ban_notice.button", text);
    golden.check("admin.ban_notice.button_data", data);

    golden.check_str("admin.unban_usage", texts::UNBAN_USAGE_TEXT);
    golden.check_str("admin.unban_not_found", texts::UNBAN_NOT_FOUND_TEXT);
    golden.check("admin.unban_user", texts::unban_user_text("NEWCODE1"));
    golden.check(
        "admin.unban_result",
        texts::unban_result_text("ABCD1234", "NEWCODE1"),
    );
    golden.check(
        "admin.accept_user",
        texts::accept_unban_user_text("NEWCODE1"),
    );
    golden.check(
        "admin.accept_edited",
        format!("🙏 ЗАЯВКА{}", texts::accept_unban_edit_suffix("NEWCODE1")),
    );
    golden.check_str("admin.accept_already", texts::ACCEPT_UNBAN_ALREADY_TEXT);
    golden.check_str("admin.decline_user", texts::DECLINE_UNBAN_USER_TEXT);
    golden.check(
        "admin.decline_edited",
        format!("🙏 ЗАЯВКА{}", texts::DECLINE_UNBAN_EDIT_SUFFIX),
    );

    golden.check_str("admin.addbalance_usage", texts::ADD_BALANCE_USAGE_TEXT);
    golden.check_str(
        "admin.addbalance_not_found",
        texts::ADD_BALANCE_NOT_FOUND_TEXT,
    );
    golden.check_str(
        "admin.addbalance_invalid",
        texts::ADD_BALANCE_INVALID_AMOUNT_TEXT,
    );
    golden.check(
        "admin.addbalance_result",
        texts::add_balance_result_text(42, 100, 350),
    );

    golden.check_str("admin.refund_usage", texts::REFUND_USAGE_TEXT);
    golden.check(
        "admin.refund_not_found",
        texts::refund_not_found_text("stx_1"),
    );
    golden.check("admin.refund_already", texts::refund_already_text("stx_1"));
    golden.check("admin.refund_none", texts::refund_no_payments_text(42));
    golden.check("admin.refund_started", texts::refund_started_text(42, 2));
    golden.check("admin.refund_busy", texts::refund_result_text(42, 0, 1));
    golden.check(
        "admin.refund_success",
        texts::refund_success_text("stx_1", 42),
    );
    golden.check(
        "admin.refund_error",
        texts::refund_error_text("stx_1", "Bad Request: CHARGE_ALREADY_REFUNDED"),
    );
    golden.check("admin.refund_result", texts::refund_result_text(42, 0, 2));

    golden.check_str(
        "admin.broadcast_instruction",
        texts::BROADCAST_INSTRUCTION_TEXT,
    );
    golden.check("admin.broadcast_started", texts::broadcast_started_text(3));
    golden.check("admin.broadcast_result", texts::broadcast_result_text(3, 0));

    // --- middleware and error guard ---------------------------------------
    golden.check_str("throttle.notice", texts::THROTTLE_NOTICE_TEXT);
    golden.check_str("guard.callback", texts::ERROR_GUARD_CALLBACK_TEXT);
    golden.check_str("guard.message", texts::ERROR_GUARD_MESSAGE_TEXT);

    golden.finish();
}

#[test]
fn golden_achievements_match_the_python_implementation() {
    let fixtures: Vec<serde_json::Value> =
        serde_json::from_str(include_str!("fixtures/achievements.json")).expect("valid fixtures");

    assert_eq!(fixtures.len(), achievements::total_count());
    assert_eq!(fixtures.len(), achievements::ACHIEVEMENTS.len());

    for (fixture, actual) in fixtures.iter().zip(achievements::ACHIEVEMENTS) {
        let field = |name: &str| {
            fixture[name]
                .as_str()
                .unwrap_or_else(|| panic!("`{name}` must be a string"))
        };
        assert_eq!(actual.id, field("id"));
        assert_eq!(actual.title, field("title"));
        assert_eq!(actual.description, field("description"));
        assert_eq!(actual.icon, field("icon"));
    }

    for entry in achievements::ACHIEVEMENTS {
        assert_eq!(achievements::get(entry.id), Some(entry));
    }
}
