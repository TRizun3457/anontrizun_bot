//! Plain data types returned by the database layer.

/// Aggregated per-user statistics used across the whole bot.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UserStats {
    pub balance: i64,
    pub air_purchased: i64,
    pub priority_messages: i64,
    pub sent_count: i64,
    pub received_count: i64,
    pub is_vip: bool,
    pub anon_code: String,
    pub code_auto_refresh: String,
    pub show_vip_cats: bool,
    pub show_air: bool,
    pub show_priority: bool,
    pub show_sent: bool,
    pub show_received: bool,
    pub show_achievements: bool,
}

impl Default for UserStats {
    fn default() -> Self {
        Self {
            balance: 0,
            air_purchased: 0,
            priority_messages: 0,
            sent_count: 0,
            received_count: 0,
            is_vip: false,
            anon_code: "НЕИЗВЕСТНО".to_string(),
            code_auto_refresh: "never".to_string(),
            show_vip_cats: true,
            show_air: true,
            show_priority: true,
            show_sent: true,
            show_received: true,
            show_achievements: true,
        }
    }
}

/// Message mapping stored for the anonymous forwarding flow.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SenderWithMessage {
    pub sender_id: i64,
    pub user_msg_id: i64,
}

/// Sender plus the anonymous code frozen at forwarding time.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SenderWithCode {
    pub sender_id: i64,
    pub anon_code: String,
}

/// A row of the `banned` table.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BannedUser {
    pub user_id: i64,
    pub anon_code: String,
}

/// A row of the `payments` table.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PaymentRecord {
    pub charge_id: String,
    pub user_id: i64,
    pub payload: Option<String>,
    pub status: String,
}
