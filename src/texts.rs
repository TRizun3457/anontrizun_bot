//! Every user-visible string, kept exactly as in the original bot.
//!
//! Telegram HTML parse mode is used everywhere unless a constant says
//! otherwise.

use crate::achievements::get as achievement;
use crate::db::models::{BannedUser, UserStats};

// ---------------------------------------------------------------------------
// /start and /anon
// ---------------------------------------------------------------------------

pub const ANON_GROUP_TEXT: &str =
    "✉️ <b>Анонимные сообщения</b>\n\nНажмите кнопку ниже, чтобы отправить анонимный вопрос!";

pub const ANON_PRIVATE_TEXT: &str =
    "ℹ️ Команду <code>/anon</code> можно использовать в чатах и группах.";

pub const START_PRIVATE_TEXT: &str = "Привет! Напиши сюда сообщение, и я передам его анонимно.";

pub const START_BANNED_TEXT: &str = "❌ <b>Вы заблокированы в этом боте.</b>";

pub const ADMIN_PANEL_TEXT: &str = "👑 <b>Панель администратора</b>\n\n\
<b>Управление блокировками:</b>\n\
• <code>/ban</code> — забанить (в ответ на сообщение)\n\
• <code>/unban КОД|ID</code> — разбанить пользователя\n\
• <code>/banlist</code> — список забаненных кодов\n\n\
<b>Финансы и Рассылка:</b>\n\
• <code>/addbalance КОД|ID СУММА</code> — пополнить баланс Stars\n\
• <code>/refund КОД|ID|STX_ID</code> — возврат звёзд\n\
• <code>/broadcast</code> — рассылка сообщений пользователям";

// ---------------------------------------------------------------------------
// Profile / achievements
// ---------------------------------------------------------------------------

pub const ACHIEVEMENTS_EMPTY_TEXT: &str =
    "🏆 <b>Ваши достижения</b>\n\nУ вас пока нет открытых достижений.";

pub fn profile_text(
    stats: &UserStats,
    user_id: i64,
    banned: bool,
    ach_count: i64,
    cat: &str,
) -> String {
    let code_spoiler = format!("<tg-spoiler><code>{}</code></tg-spoiler>", stats.anon_code);
    let status_text = if banned {
        "🚫 Заблокирован"
    } else {
        "✅ Активен"
    };
    let vip_status = if stats.is_vip {
        format!("💎 VIP Подписчик{cat}")
    } else {
        "❌ Нет".to_string()
    };

    let ident_block = format!(
        "🆔 <b>Идентификация</b>\n\
├ <b>Ваш код:</b> {code_spoiler}\n\
├ <b>ID:</b> <code>{user_id}</code>\n\
└ <b>Состояние:</b> {status_text}",
    );
    let stats_block = format!(
        "📈 <b>Статистика сообщений</b>\n\
├ <b>Отправлено анонимок:</b> <code>{}</code> ✉️\n\
├ <b>Получено ответов:</b> <code>{}</code> 💬\n\
└ <b>Оплачено приоритетных:</b> <code>{}</code> ⭐️",
        stats.sent_count, stats.received_count, stats.priority_messages
    );
    let mut ach_block = format!(
        "🏆 <b>Достижения и Статусы</b>\n\
├ <b>Достижений:</b> <code>{ach_count}/{}</code> 🎖️\n\
└ <b>Куплено воздуха:</b> <code>{}</code> шт. 💨",
        crate::achievements::total_count(),
        stats.air_purchased
    );
    if stats.air_purchased > 0 {
        ach_block += &format!("\n└ <b>Оценка:</b> <i>Ну и воздухан...{cat}</i>");
    }

    let top_block = if stats.is_vip {
        format!("✨ 👑 <b>VIP-ПРОФИЛЬ{cat}</b> 👑 \n⚡️ <i>Премиум-статус активирован</i>")
    } else {
        "👤 <b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>\n─────────────────────".to_string()
    };

    let finance_suffix = if stats.is_vip { " и Status" } else { "" };
    let finance_block = format!(
        "💰 <b>Финансы{finance_suffix}</b>\n\
├ <b>Баланс:</b> <b>{}</b> ⭐️\n\
└ <b>VIP Поддержка:</b> {vip_status}",
        stats.balance
    );

    format!("{top_block}\n\n{ident_block}\n\n{finance_block}\n\n{stats_block}\n\n{ach_block}")
}

pub fn achievements_text(unlocked: &[String]) -> String {
    if unlocked.is_empty() {
        return ACHIEVEMENTS_EMPTY_TEXT.to_string();
    }

    let total = crate::achievements::total_count();
    let mut text = format!(
        "🏆 <b>Открытые достижения ({total_count}/{total}):</b>\n\n",
        total_count = unlocked.len()
    );
    for ach_id in unlocked {
        if let Some(ach) = achievement(ach_id) {
            text += &format!("{} <b>{}</b>\n{}\n\n", ach.icon, ach.title, ach.description);
        }
    }
    text
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

pub fn refresh_label(code: &str) -> &'static str {
    match code {
        "8h" => "Раз в 8 ч.",
        "daily" => "Раз в 24 ч.",
        "weekly" => "Раз в 7 дней",
        _ => "Никогда",
    }
}

pub fn cats_label(show: bool) -> &'static str {
    if show {
        "Включены ✅"
    } else {
        "Выключены ❌"
    }
}

pub fn settings_text(stats: &UserStats) -> String {
    format!(
        "⚙️ <b>НАСТРОЙКИ ПРОФИЛЯ</b>\n\
─────────────────────\n\n\
🔑 Ваш анонимный код: <code>{}</code>\n\n\
• Авто-обновление кода: {}\n\
• Кастомизация котиков (VIP): {}\n\n\
Выберите параметр для изменения ниже:",
        stats.anon_code,
        refresh_label(&stats.code_auto_refresh),
        cats_label(stats.show_vip_cats)
    )
}

pub fn share_preview_text(
    stats: &UserStats,
    ach_count: i64,
    total_ach: usize,
    cat: &str,
) -> String {
    let mut stats_items: Vec<String> = Vec::new();
    if stats.show_sent {
        stats_items.push(format!(
            "✉️ Отправлено анонимок: <b>{}</b>",
            stats.sent_count
        ));
    }
    if stats.show_received {
        stats_items.push(format!(
            "💬 Получено ответов: <b>{}</b>",
            stats.received_count
        ));
    }
    if stats.show_priority {
        stats_items.push(format!(
            "⭐ Приоритетных: <b>{}</b>",
            stats.priority_messages
        ));
    }
    if stats.show_air {
        stats_items.push(format!(
            "💨 Воздуха куплено: <b>{}</b>",
            stats.air_purchased
        ));
    }
    if stats.show_achievements {
        stats_items.push(format!("🏆 Достижений: <b>{ach_count}/{total_ach}</b>"));
    }

    let stats_body = stats_items.join("\n");

    if stats.is_vip {
        let header_vip = format!("✨ 👑 <b>VIP-ПРОФИЛЬ{cat}</b> 👑 ✨");
        format!(
            "{header_vip}\n\
💎 <b>Статус:</b> VIP Подписчик\n\n\
📊 <b>Статистика:</b>\n\
{stats_body}"
        )
    } else {
        format!("📊 <b>Анонимная статистика:</b>\n{stats_body}")
    }
}

pub fn share_settings_text(preview_text: &str) -> String {
    format!(
        "📲 <b>НАСТРОЙКИ ИНЛАЙН-ШЕРИНГА</b>\n\
─────────────────────\n\
🔒 Конфиденциальность: Ваш анонимный код и Telegram ID никогда не публикуются при шеринге.\n\n\
👁️ Предпросмотр сообщения (как его увидят в чате):\n\n\
{preview_text}\n\n\
─────────────────────\n\
⚠️ Хотя бы один параметр всегда должен быть включён.\n\
Отметьте, что показывать в карточке:"
    )
}

// ---------------------------------------------------------------------------
// Inline sharing
// ---------------------------------------------------------------------------

pub const INLINE_ADMIN_SHARE_TEXT: &str =
    "✉️ Задай мне анонимный вопрос!\n\nНапиши всё, что думаешь — всё передастся анонимно!";
pub const INLINE_ADMIN_TITLE: &str = "🚀 Поделиться ссылкой на анонимки";
pub const INLINE_ADMIN_DESCRIPTION: &str = "Отправить ссылку на бота";
pub const INLINE_VIP_TITLE: &str = "👑 Поделиться VIP профилем";
pub const INLINE_STATS_TITLE: &str = "📊 Поделиться статистикой";
pub const INLINE_STATS_DESCRIPTION: &str = "Показать мою статистику";

pub fn inline_share_title(stats: &UserStats) -> &'static str {
    if stats.is_vip {
        INLINE_VIP_TITLE
    } else {
        INLINE_STATS_TITLE
    }
}

// ---------------------------------------------------------------------------
// Anonymous forwarding
// ---------------------------------------------------------------------------

pub const FORWARD_BANNED_TEXT: &str = "❌ Вы заблокированы в боте.";
pub const FORWARD_VIP_BANNER: &str =
    "═════════════════════\n💎 VIP-СООБЩЕНИЕ\n═════════════════════";
pub const FORWARD_PRIORITY_BANNER: &str = "🌟 [ПРИОРИТЕТНОЕ СООБЩЕНИЕ]";
pub const FORWARD_ERROR_TEXT: &str = "❌ Ошибка при отправке.";
pub const FORWARD_CONFIRM_PRIORITY: &str = "⭐ Приоритетное сообщение отправлено!";
pub const FORWARD_CONFIRM_TEXT: &str = "🚀 Сообщение отправлено анонимно!";

// ---------------------------------------------------------------------------
// Admin replies
// ---------------------------------------------------------------------------

pub const REPLY_PROMPT_TEXT: &str = "📝 Введите ответ:";
pub const REPLY_NOTICE_TEXT: &str = "📩 Вам пришёл ответ на анонимное сообщение:";
pub const REPLY_SUCCESS_TEXT: &str = "✅ Ответ успешно отправлен!";
pub const REPLY_FAILURE_TEXT: &str = "❌ Не удалось доставить ответ пользователю.";
pub const REPLY_NO_RECIPIENT_TEXT: &str = "❌ Ошибка: не удалось найти получателя.";
pub const REPLY_BUTTON_ERROR_TEXT: &str = "Ошибка вызова кнопки.";

// ---------------------------------------------------------------------------
// Payments
// ---------------------------------------------------------------------------

pub const BALANCE_INSUFFICIENT_ALERT: &str = "❌ Недостаточно средств на балансе.";
pub const BALANCE_PAID_PRIORITY_TEXT: &str =
    "🎉 <b>Оплачено с баланса!</b> Начислен 1 приоритетный ответ.";
pub const BALANCE_PAID_VIP_TEXT: &str =
    "💎 <b>Оплачено с баланса!</b> Активировано VIP-оформление.";
pub const BALANCE_PAID_AIR_TEXT: &str = "💨 <b>Оплачено с баланса!</b> Вы приобрели воздух.";

pub const VIP_INVOICE_TITLE: &str = "💎 VIP-Поддержка";
pub const AIR_INVOICE_TITLE: &str = "💨 Покупка воздуха";
pub const VIP_INVOICE_PAYLOAD: &str = "buy_vip_sub";
pub const AIR_INVOICE_PAYLOAD: &str = "buy_air_pack";

pub const DEPOSIT_MENU_TEXT: &str = "💳 <b>Выберите сумму для пополнения баланса бота:</b>";

pub const PRIORITY_INSUFFICIENT_TEXT: &str = "❌ <b>Недостаточно средств на балансе!</b>\n\n\
Приоритет покупается <b>только с внутреннего баланса</b> (1 ⭐️).\n\
Пополните баланс в меню ниже:";

pub const APOLOGY_NOT_BANNED_TEXT: &str = "ℹ️ Вы не заблокированы.";
pub const APOLOGY_PROMPT_TEXT: &str =
    "✍️ <b>Напишите сообщение с раскаянием для администратора:</b>";
pub const APOLOGY_INVOICE_TITLE: &str = "🙏 Заявка на разбан";
pub const APOLOGY_INVOICE_DESCRIPTION: &str =
    "Шанс на разбан. Вы сможете отправить раскаяние админу.";
pub const APOLOGY_INVOICE_PAYLOAD: &str = "buy_apology_req";
pub const APOLOGY_INVOICE_LABEL: &str = "Попросить прощения";
pub const APOLOGY_BALANCE_INSUFFICIENT_TEXT: &str = "❌ Недостаточно средств на балансе.";
pub const APOLOGY_SEND_ERROR_TEXT: &str = "❌ Ошибка при отправке.";
pub const APOLOGY_SENT_TEXT: &str = "🚀 Ваша заявка отправлена администратору!";

pub const PAYMENT_BALANCE_TOPPED_UP: &str = "🎉 <b>Баланс пополнен на {} Stars!</b>";
pub const PAYMENT_VIP_TEXT: &str =
    "💎 <b>Огромное спасибо за поддержку!</b> Активировано VIP-оформление.";
pub const PAYMENT_AIR_TEXT: &str = "💨 <b>Спасибо за покупку воздуха!</b>";
pub const PAYMENT_APOLOGY_TEXT: &str = "✍️ <b>Оплата получена!</b> Введите текст раскаяния:";

pub fn deposit_invoice_title(amount: i64) -> String {
    format!("💳 Пополнение баланса на {amount} Stars")
}

pub fn deposit_invoice_description(amount: i64) -> String {
    format!("Пополнение внутреннего баланса бота на {amount} ⭐️")
}

pub fn deposit_invoice_payload(amount: i64) -> String {
    format!("deposit_{amount}")
}

pub fn deposit_invoice_label(amount: i64) -> String {
    format!("Пополнение {amount} Stars")
}

pub fn balance_invoice_description(price: i64) -> String {
    format!("Недостаточно средств на балансе. Прямая оплата {price} ⭐️")
}

pub fn balance_topped_up_text(amount: i64) -> String {
    format!("🎉 <b>Баланс пополнен на {amount} Stars!</b>")
}

pub fn apology_admin_text(anon_code: &str, user_id: i64, escaped_text: &str) -> String {
    format!(
        "🙏 <b>ЗАЯВКА НА РАЗБАН (ОПЛАЧЕНО 50 ⭐️)</b>\n\n\
• <b>Код забаненного:</b> <code>{anon_code}</code>\n\
• <b>User ID:</b> <code>{user_id}</code>\n\n\
<b>Сообщение с раскаянием:</b>\n<i>{escaped_text}</i>"
    )
}

// ---------------------------------------------------------------------------
// Admin commands
// ---------------------------------------------------------------------------

pub const BANLIST_EMPTY_TEXT: &str = " Список забаненных пользователей пуст.";
pub const BANLIST_HEADER: &str = "🚫 <b>Список забаненных кодов:</b>\n\n";
pub const BAN_USAGE_TEXT: &str =
    "⚠️ Чтобы забанить, ответьте командой <code>/ban</code> на сообщение.";
pub const BAN_NOT_FOUND_TEXT: &str = "❌ Не удалось найти автора этого сообщения в базе.";
pub const BAN_NOTICE_TEXT: &str = "❌ <b>Вы были заблокированы администратором.</b>\n\n\
Ваш код заморожен. Вы можете подать заявку на разбан за 50 ⭐️.";
pub const BAN_NOTIFY_OK: &str = "Оповещение доставлено.";
pub const BAN_NOTIFY_FAILED: &str = "Не удалось доставить оповещение.";

pub fn banlist_text(banned_users: &[BannedUser]) -> String {
    let mut text = BANLIST_HEADER.to_string();
    for banned_user in banned_users {
        text += &format!(
            "• Код: <code>{}</code> (ID: <code>{}</code>)\n",
            banned_user.anon_code, banned_user.user_id
        );
    }
    text
}

pub fn ban_success_text(user_id: i64, anon_code: &str, notify_status: &str) -> String {
    format!(
        "🚫 Пользователь (ID: <code>{user_id}</code>) заблокирован!\n\
Код: <code>{anon_code}</code> (Заморожен)\n<i>{notify_status}</i>"
    )
}

pub const UNBAN_USAGE_TEXT: &str = "⚠️ Пример: <code>/unban XXXXXX</code>";
pub const UNBAN_NOT_FOUND_TEXT: &str = "❌ Пользователь с таким кодом не найден.";

pub fn unban_user_text(new_code: &str) -> String {
    format!(
        "✅ <b>Вы были разблокированы!</b>\n\n\
Ваш анонимный код сброшен и сгенерирован заново: <code>{new_code}</code>"
    )
}

pub fn unban_result_text(old_code: &str, new_code: &str) -> String {
    format!(
        "✅ Пользователь разбанен!\n\
Старый код: <code>{old_code}</code>\n\
Новый сгенерированный код: <code>{new_code}</code>"
    )
}

pub fn accept_unban_user_text(new_code: &str) -> String {
    format!(
        "✅ <b>Ваша заявка одобрена! Вы успешно разбанены.</b>\n\n\
Ваш новый анонимный код: <code>{new_code}</code>"
    )
}

pub fn accept_unban_edit_suffix(new_code: &str) -> String {
    format!("\n\n<b>Статус: РАЗБАНЕН ✅ (Новый код: <code>{new_code}</code>)</b>")
}

pub const ACCEPT_UNBAN_ALREADY_TEXT: &str = "Пользователь уже разбанен.";
pub const DECLINE_UNBAN_USER_TEXT: &str = "❌ <b>Ваша заявка на разбан отклонена.</b>";
pub const DECLINE_UNBAN_EDIT_SUFFIX: &str = "\n\n<b>Статус: ОТКЛОНЕНО ❌</b>";

pub const ADD_BALANCE_USAGE_TEXT: &str = "⚠️ Пример: <code>/addbalance КОД|USER_ID СУММА</code>";
pub const ADD_BALANCE_NOT_FOUND_TEXT: &str =
    "❌ Пользователь с таким ID или анонимным кодом не найден.";
pub const ADD_BALANCE_INVALID_AMOUNT_TEXT: &str = "❌ Сумма должна быть числом.";

pub fn add_balance_result_text(user_id: i64, amount: i64, balance: i64) -> String {
    format!(
        "✅ Баланс пользователя <code>{user_id}</code> изменён на <b>{amount}</b> ⭐️.\n\
Текущий баланс: <b>{balance}</b> ⭐️."
    )
}

pub const REFUND_USAGE_TEXT: &str = "⚠️ Пример использования:\n\
• <code>/refund STX_ID</code> — возврат конкретной транзакции\n\
• <code>/refund USER_ID</code> — возврат всех транзакций пользователя";

pub fn refund_not_found_text(charge_id: &str) -> String {
    format!("❌ Платёж <code>{charge_id}</code> не найден в базе данных.")
}

pub fn refund_already_text(charge_id: &str) -> String {
    format!("⚠️ Платёж <code>{charge_id}</code> уже был возвращён ранее.")
}

pub fn refund_no_payments_text(user_id: i64) -> String {
    format!("❌ У пользователя <code>{user_id}</code> нет успешных платежей для возврата.")
}

pub fn refund_started_text(user_id: i64, count: usize) -> String {
    format!("🔄 Начат процесс возврата для пользователя <code>{user_id}</code> ({count} шт.)...")
}

pub fn refund_result_text(user_id: i64, success: u64, fail: u64) -> String {
    format!(
        "📊 <b>Результат возврата средств для {user_id}:</b>\n\n\
✅ Успешно возвращено: <b>{success}</b>\n\
❌ Ошибок возврата: <b>{fail}</b>"
    )
}

pub fn refund_busy_text(charge_id: &str) -> String {
    format!("⚠️ Платёж <code>{charge_id}</code> уже обрабатывается или статус изменён.")
}

pub fn refund_success_text(charge_id: &str, user_id: i64) -> String {
    format!(
        "✅ Возврат платежа <code>{charge_id}</code> для пользователя <code>{user_id}</code> выполнен успешно."
    )
}

pub fn refund_error_text(charge_id: &str, message: &str) -> String {
    format!("❌ Ошибка Telegram API при возврате <code>{charge_id}</code>:\n<code>{message}</code>")
}

pub const BROADCAST_INSTRUCTION_TEXT: &str = "\u{fe0f} <b>Инструкция по рассылке:</b>\n\n\
• Ответьте командой <code>/broadcast</code> на любое сообщение/медиа для рассылки.\n\
• Или отправьте текст: <code>/broadcast Текст сообщения</code>";

pub fn broadcast_started_text(count: usize) -> String {
    format!("🔄 Запуск рассылки для <b>{count}</b> пользователей...")
}

pub fn broadcast_result_text(success: u64, fail: u64) -> String {
    format!(
        "📊 <b>Рассылка завершена!</b>\n\n\
✅ Успешно отправлено: <b>{success}</b>\n\
❌ Ошибок / заблокировали: <b>{fail}</b>"
    )
}

// ---------------------------------------------------------------------------
// Throttling and the global error guard
// ---------------------------------------------------------------------------

/// Sent without a parse mode, exactly like the original `Message.answer`.
pub const THROTTLE_NOTICE_TEXT: &str = "⏳ Не так быстро! Запросы отправляются слишком часто.";
pub const ERROR_GUARD_CALLBACK_TEXT: &str = "⚠️ Временная ошибка. Попробуйте еще раз.";
pub const ERROR_GUARD_MESSAGE_TEXT: &str = "⚠️ <b>Временные неполадки.</b> Попробуйте ещё раз.";
