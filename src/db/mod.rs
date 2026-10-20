//! SQLite persistence layer.
//!
//! The schema is created by the migration in `migrations/0001_init.sql`,
//! which is preserved byte-for-byte from the original project. Every method
//! mirrors the behaviour of the previous `database` module.

pub mod models;

use std::{str::FromStr, sync::Arc, time::Duration};

use anyhow::{Context, Result, bail};
use dashmap::DashSet;
use sqlx::{
    SqlitePool,
    sqlite::{SqliteConnectOptions, SqliteJournalMode, SqlitePoolOptions, SqliteSynchronous},
};

use self::models::{BannedUser, PaymentRecord, SenderWithCode, SenderWithMessage, UserStats};
use crate::achievements::{self, AchievementStats};

/// Settings columns that users are allowed to toggle.
const ALLOWED_SETTINGS: &[&str] = &[
    "code_auto_refresh",
    "show_vip_cats",
    "show_air",
    "show_priority",
    "show_sent",
    "show_received",
    "show_achievements",
    "inline_share_mode",
];

#[derive(sqlx::FromRow)]
struct UserStatsRow {
    balance: i64,
    air_purchased: i64,
    priority_messages: i64,
    sent_count: i64,
    received_count: i64,
    is_vip: i64,
    anon_code: Option<String>,
    code_auto_refresh: Option<String>,
    show_vip_cats: i64,
    show_achievements: i64,
    show_air: i64,
    show_priority: i64,
    show_sent: i64,
    show_received: i64,
}

impl UserStatsRow {
    fn into_stats(self) -> UserStats {
        UserStats {
            balance: self.balance,
            air_purchased: self.air_purchased,
            priority_messages: self.priority_messages,
            sent_count: self.sent_count,
            received_count: self.received_count,
            is_vip: self.is_vip != 0,
            anon_code: self.anon_code.unwrap_or_else(|| "НЕИЗВЕСТНО".to_string()),
            code_auto_refresh: self
                .code_auto_refresh
                .unwrap_or_else(|| "never".to_string()),
            show_vip_cats: self.show_vip_cats != 0,
            show_achievements: self.show_achievements != 0,
            show_air: self.show_air != 0,
            show_priority: self.show_priority != 0,
            show_sent: self.show_sent != 0,
            show_received: self.show_received != 0,
        }
    }
}

#[derive(sqlx::FromRow)]
struct AchievementStatsRow {
    air_purchased: i64,
    sent_count: i64,
    received_count: i64,
    is_vip: i64,
    priority_sent_count: Option<i64>,
    total_spent_stars: Option<i64>,
    answer_streak: Option<i64>,
}

fn generate_anon_code() -> String {
    const CHARSET: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    (0..8)
        .map(|_| CHARSET[rand::random_range(0..CHARSET.len())] as char)
        .collect()
}

/// Handle to the SQLite database with a preloaded in-memory ban cache.
#[derive(Clone)]
pub struct Database {
    pool: SqlitePool,
    ban_cache: Arc<DashSet<i64>>,
}

impl Database {
    /// Opens (creating if needed) the SQLite file and runs the migrations.
    pub async fn connect(path: &str) -> Result<Self> {
        let options = SqliteConnectOptions::new()
            .filename(path)
            .create_if_missing(true)
            .journal_mode(SqliteJournalMode::Wal)
            .synchronous(SqliteSynchronous::Normal)
            .busy_timeout(Duration::from_secs(30));

        let pool = SqlitePoolOptions::new()
            .max_connections(5)
            .connect_with(options)
            .await
            .with_context(|| format!("failed to open SQLite database `{path}`"))?;

        let database = Self::from_pool(pool);
        database.migrate().await?;
        Ok(database)
    }

    /// Single-connection in-memory database used by the tests.
    pub async fn connect_in_memory() -> Result<Self> {
        let options = SqliteConnectOptions::from_str("sqlite::memory:")?;
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect_with(options)
            .await
            .context("failed to open in-memory SQLite database")?;

        let database = Self::from_pool(pool);
        database.migrate().await?;
        Ok(database)
    }

    fn from_pool(pool: SqlitePool) -> Self {
        Self {
            pool,
            ban_cache: Arc::new(DashSet::new()),
        }
    }

    async fn migrate(&self) -> Result<()> {
        sqlx::migrate!("./migrations")
            .run(&self.pool)
            .await
            .context("database migration failed")?;

        self.ban_cache.clear();
        for banned in self.get_banned_users().await? {
            self.ban_cache.insert(banned.user_id);
        }
        Ok(())
    }

    /// Closes the connection pool.
    pub async fn close(&self) {
        self.pool.close().await;
    }

    pub fn is_banned(&self, user_id: i64) -> bool {
        self.ban_cache.contains(&user_id)
    }

    pub async fn ban_user(&self, user_id: i64, anon_code: &str) -> Result<()> {
        sqlx::query("INSERT OR REPLACE INTO banned (user_id, anon_code) VALUES (?, ?)")
            .bind(user_id)
            .bind(anon_code)
            .execute(&self.pool)
            .await?;
        self.ban_cache.insert(user_id);
        Ok(())
    }

    pub async fn delete_old_user_code_records(&self, user_id: i64, old_code: &str) -> Result<()> {
        if old_code.is_empty() || old_code == "НЕИЗВЕСТНО" {
            return Ok(());
        }

        sqlx::query(
            "UPDATE messages SET anon_code = NULL WHERE sender_id = ? AND UPPER(anon_code) = UPPER(?)",
        )
        .bind(user_id)
        .bind(old_code)
        .execute(&self.pool)
        .await?;

        sqlx::query("DELETE FROM banned WHERE user_id = ? AND UPPER(anon_code) = UPPER(?)")
            .bind(user_id)
            .bind(old_code)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    /// Unbans the user, regenerates the code and returns the new code.
    pub async fn unban_user(&self, user_id: i64) -> Result<String> {
        let old_code: Option<String> =
            sqlx::query_scalar("SELECT anon_code FROM banned WHERE user_id = ?")
                .bind(user_id)
                .fetch_optional(&self.pool)
                .await?;

        let old_code = match old_code {
            Some(code) => code,
            None => {
                sqlx::query_scalar::<_, String>("SELECT anon_code FROM users WHERE user_id = ?")
                    .bind(user_id)
                    .fetch_optional(&self.pool)
                    .await?
                    .unwrap_or_else(|| "НЕИЗВЕСТНО".to_string())
            }
        };

        let new_anon_code = generate_anon_code();

        sqlx::query("UPDATE users SET anon_code = ? WHERE user_id = ?")
            .bind(&new_anon_code)
            .bind(user_id)
            .execute(&self.pool)
            .await?;

        sqlx::query("DELETE FROM banned WHERE user_id = ?")
            .bind(user_id)
            .execute(&self.pool)
            .await?;

        if old_code != "НЕИЗВЕСТНО" {
            sqlx::query(
                "UPDATE messages SET anon_code = NULL WHERE sender_id = ? AND UPPER(anon_code) = UPPER(?)",
            )
            .bind(user_id)
            .bind(&old_code)
            .execute(&self.pool)
            .await?;
            sqlx::query("DELETE FROM banned WHERE user_id = ? AND UPPER(anon_code) = UPPER(?)")
                .bind(user_id)
                .bind(&old_code)
                .execute(&self.pool)
                .await?;
        }

        self.ban_cache.remove(&user_id);
        Ok(new_anon_code)
    }

    /// Returns `(success, new_code_or_error_message)`.
    pub async fn regenerate_user_code(&self, user_id: i64) -> Result<(bool, String)> {
        if self.ban_cache.contains(&user_id) {
            return Ok((
                false,
                "Вы заблокированы! Изменение кода заблокировано до разбана.".to_string(),
            ));
        }

        let old_code: Option<String> =
            sqlx::query_scalar("SELECT anon_code FROM users WHERE user_id = ?")
                .bind(user_id)
                .fetch_optional(&self.pool)
                .await?;

        let new_code = generate_anon_code();

        sqlx::query("UPDATE users SET anon_code = ? WHERE user_id = ?")
            .bind(&new_code)
            .bind(user_id)
            .execute(&self.pool)
            .await?;

        if let Some(ref old) = old_code
            && old != "НЕИЗВЕСТНО"
        {
            sqlx::query(
                "UPDATE messages SET anon_code = NULL WHERE sender_id = ? AND UPPER(anon_code) = UPPER(?)",
            )
            .bind(user_id)
            .bind(old)
            .execute(&self.pool)
            .await?;
            sqlx::query("DELETE FROM banned WHERE user_id = ? AND UPPER(anon_code) = UPPER(?)")
                .bind(user_id)
                .bind(old)
                .execute(&self.pool)
                .await?;
        }

        Ok((true, new_code))
    }

    /// Creates the user when missing and returns the current statistics.
    ///
    /// The fast path (user already exists) only performs a single query.
    pub async fn register_user(&self, user_id: i64, referrer_id: Option<i64>) -> Result<UserStats> {
        let existing: Option<String> =
            sqlx::query_scalar("SELECT anon_code FROM users WHERE user_id = ?")
                .bind(user_id)
                .fetch_optional(&self.pool)
                .await?;

        if existing.is_some() {
            return self.get_user_stats(user_id).await;
        }

        let valid_referrer_id = match referrer_id {
            Some(ref_id) if ref_id != user_id => {
                let exists: Option<i64> =
                    sqlx::query_scalar("SELECT 1 FROM users WHERE user_id = ?")
                        .bind(ref_id)
                        .fetch_optional(&self.pool)
                        .await?;
                exists.map(|_| ref_id)
            }
            _ => None,
        };

        for _ in 0..5 {
            let anon_code = generate_anon_code();

            let result =
                sqlx::query("INSERT INTO users (user_id, anon_code, referrer_id) VALUES (?, ?, ?)")
                    .bind(user_id)
                    .bind(&anon_code)
                    .bind(valid_referrer_id)
                    .execute(&self.pool)
                    .await;

            match result {
                Ok(_) => return self.get_user_stats(user_id).await,
                Err(sqlx::Error::Database(error)) if error.is_unique_violation() => {
                    let message = error.message();
                    if message.contains("users.user_id") || message.contains("user_id") {
                        return self.get_user_stats(user_id).await;
                    }
                    continue;
                }
                Err(error) => return Err(error.into()),
            }
        }

        bail!("Не удалось сгенерировать уникальный anon_code")
    }

    pub async fn get_user_stats(&self, user_id: i64) -> Result<UserStats> {
        let row: Option<UserStatsRow> = sqlx::query_as(
            r#"SELECT balance, air_purchased, priority_messages, sent_count, received_count,
                      is_vip, anon_code, code_auto_refresh, show_vip_cats, show_achievements,
                      show_air, show_priority, show_sent, show_received
               FROM users WHERE user_id = ?"#,
        )
        .bind(user_id)
        .fetch_optional(&self.pool)
        .await?;

        Ok(row.map(UserStatsRow::into_stats).unwrap_or_default())
    }

    pub async fn update_user_setting(&self, user_id: i64, key: &str, value: &str) -> Result<()> {
        if !ALLOWED_SETTINGS.contains(&key) {
            bail!("Invalid setting key: {key}");
        }

        let query = match key {
            "code_auto_refresh" => "UPDATE users SET code_auto_refresh = ? WHERE user_id = ?",
            "show_vip_cats" => "UPDATE users SET show_vip_cats = ? WHERE user_id = ?",
            "show_air" => "UPDATE users SET show_air = ? WHERE user_id = ?",
            "show_priority" => "UPDATE users SET show_priority = ? WHERE user_id = ?",
            "show_sent" => "UPDATE users SET show_sent = ? WHERE user_id = ?",
            "show_received" => "UPDATE users SET show_received = ? WHERE user_id = ?",
            "show_achievements" => "UPDATE users SET show_achievements = ? WHERE user_id = ?",
            "inline_share_mode" => "UPDATE users SET inline_share_mode = ? WHERE user_id = ?",
            _ => unreachable!("checked against ALLOWED_SETTINGS"),
        };

        sqlx::query(query)
            .bind(value)
            .bind(user_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn waste_priority_message(&self, user_id: i64) -> Result<bool> {
        let result = sqlx::query(
            "UPDATE users SET priority_messages = priority_messages - 1 WHERE user_id = ? AND priority_messages > 0",
        )
        .bind(user_id)
        .execute(&self.pool)
        .await?;

        Ok(result.rows_affected() > 0)
    }

    pub async fn increment_sent_count(&self, user_id: i64) -> Result<()> {
        sqlx::query("UPDATE users SET sent_count = sent_count + 1 WHERE user_id = ?")
            .bind(user_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn increment_received_count(&self, user_id: i64) -> Result<()> {
        sqlx::query("UPDATE users SET received_count = received_count + 1 WHERE user_id = ?")
            .bind(user_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn add_message(
        &self,
        admin_msg_id: i64,
        sender_id: i64,
        anon_code: &str,
        is_priority: bool,
        user_msg_id: i64,
    ) -> Result<()> {
        sqlx::query(
            "INSERT INTO messages (admin_msg_id, sender_id, anon_code, is_priority, user_msg_id) VALUES (?, ?, ?, ?, ?)",
        )
        .bind(admin_msg_id)
        .bind(sender_id)
        .bind(anon_code)
        .bind(if is_priority { 1 } else { 0 })
        .bind(user_msg_id)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn get_admin_msg_id_by_user_msg_id(
        &self,
        sender_id: i64,
        user_msg_id: i64,
    ) -> Result<Option<i64>> {
        let result: Option<i64> = sqlx::query_scalar(
            "SELECT admin_msg_id FROM messages WHERE sender_id = ? AND user_msg_id = ?",
        )
        .bind(sender_id)
        .bind(user_msg_id)
        .fetch_optional(&self.pool)
        .await?;
        Ok(result)
    }

    pub async fn get_sender_with_message_by_admin_msg(
        &self,
        admin_msg_id: i64,
    ) -> Result<Option<SenderWithMessage>> {
        let row: Option<(i64, i64)> =
            sqlx::query_as("SELECT sender_id, user_msg_id FROM messages WHERE admin_msg_id = ?")
                .bind(admin_msg_id)
                .fetch_optional(&self.pool)
                .await?;

        Ok(row.map(|(sender_id, user_msg_id)| SenderWithMessage {
            sender_id,
            user_msg_id,
        }))
    }

    pub async fn take_balance(&self, amount: i64, user_id: i64) -> Result<bool> {
        let result = sqlx::query(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
        )
        .bind(amount)
        .bind(user_id)
        .bind(amount)
        .execute(&self.pool)
        .await?;

        Ok(result.rows_affected() > 0)
    }

    pub async fn increment_priority_messages(&self, user_id: i64) -> Result<()> {
        sqlx::query("UPDATE users SET priority_messages = priority_messages + 1 WHERE user_id = ?")
            .bind(user_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn set_vip(&self, user_id: i64, vip: bool) -> Result<()> {
        sqlx::query("UPDATE users SET is_vip = ? WHERE user_id = ?")
            .bind(if vip { 1 } else { 0 })
            .bind(user_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn increment_air_purchased(&self, user_id: i64) -> Result<()> {
        sqlx::query("UPDATE users SET air_purchased = air_purchased + 1 WHERE user_id = ?")
            .bind(user_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn get_banned_users(&self) -> Result<Vec<BannedUser>> {
        let rows: Vec<(i64, String)> = sqlx::query_as("SELECT user_id, anon_code FROM banned")
            .fetch_all(&self.pool)
            .await?;
        Ok(rows
            .into_iter()
            .map(|(user_id, anon_code)| BannedUser { user_id, anon_code })
            .collect())
    }

    pub async fn get_banned_user_id_by_anon_code(&self, anon_code: &str) -> Result<Option<i64>> {
        let result: Option<i64> =
            sqlx::query_scalar("SELECT user_id FROM banned WHERE anon_code = ?")
                .bind(anon_code)
                .fetch_optional(&self.pool)
                .await?;
        Ok(result)
    }

    pub async fn get_sender_with_code_by_admin_msg(
        &self,
        admin_msg_id: i64,
    ) -> Result<Option<SenderWithCode>> {
        let row: Option<(i64, Option<String>)> =
            sqlx::query_as("SELECT sender_id, anon_code FROM messages WHERE admin_msg_id = ?")
                .bind(admin_msg_id)
                .fetch_optional(&self.pool)
                .await?;

        match row {
            Some((sender_id, Some(anon_code))) => Ok(Some(SenderWithCode {
                sender_id,
                anon_code,
            })),
            Some((sender_id, None)) => {
                let stats = self.get_user_stats(sender_id).await?;
                Ok(Some(SenderWithCode {
                    sender_id,
                    anon_code: stats.anon_code,
                }))
            }
            None => Ok(None),
        }
    }

    pub async fn create_payment(
        &self,
        charge_id: &str,
        user_id: i64,
        payload: &str,
    ) -> Result<bool> {
        let result = sqlx::query(
            "INSERT OR IGNORE INTO payments (charge_id, user_id, payload, status) VALUES (?, ?, ?, 'success')",
        )
        .bind(charge_id)
        .bind(user_id)
        .bind(payload)
        .execute(&self.pool)
        .await?;

        Ok(result.rows_affected() > 0)
    }

    pub async fn give_balance(&self, amount: i64, user_id: i64) -> Result<()> {
        sqlx::query("UPDATE users SET balance = balance + ? WHERE user_id = ?")
            .bind(amount)
            .bind(user_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn get_banned_anon_code_by_user_id(&self, user_id: i64) -> Result<String> {
        let result: Option<String> =
            sqlx::query_scalar("SELECT anon_code FROM banned WHERE user_id = ?")
                .bind(user_id)
                .fetch_optional(&self.pool)
                .await?;
        Ok(result.unwrap_or_else(|| "НЕИЗВЕСТНО".to_string()))
    }

    pub async fn get_payment_user_id_by_charge_id(&self, charge_id: &str) -> Result<Option<i64>> {
        let result: Option<i64> =
            sqlx::query_scalar("SELECT user_id FROM payments WHERE charge_id = ?")
                .bind(charge_id)
                .fetch_optional(&self.pool)
                .await?;
        Ok(result)
    }

    pub async fn get_payment_by_charge_id(&self, charge_id: &str) -> Result<Option<PaymentRecord>> {
        let row: Option<(String, i64, Option<String>, String)> = sqlx::query_as(
            "SELECT charge_id, user_id, payload, status FROM payments WHERE charge_id = ?",
        )
        .bind(charge_id)
        .fetch_optional(&self.pool)
        .await?;

        Ok(
            row.map(|(charge_id, user_id, payload, status)| PaymentRecord {
                charge_id,
                user_id,
                payload,
                status,
            }),
        )
    }

    pub async fn set_payment_status_by_charge_id(
        &self,
        charge_id: &str,
        status: &str,
    ) -> Result<()> {
        sqlx::query("UPDATE payments SET status = ? WHERE charge_id = ?")
            .bind(status)
            .bind(charge_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn set_payment_status_if_current(
        &self,
        charge_id: &str,
        expected_status: &str,
        new_status: &str,
    ) -> Result<bool> {
        let result =
            sqlx::query("UPDATE payments SET status = ? WHERE charge_id = ? AND status = ?")
                .bind(new_status)
                .bind(charge_id)
                .bind(expected_status)
                .execute(&self.pool)
                .await?;

        Ok(result.rows_affected() > 0)
    }

    pub async fn batch_set_payment_status_by_charge_ids(
        &self,
        charge_ids: &[String],
        status: &str,
    ) -> Result<()> {
        if charge_ids.is_empty() {
            return Ok(());
        }

        let mut builder = sqlx::QueryBuilder::new("UPDATE payments SET status = ");
        builder.push_bind(status);
        builder.push(" WHERE charge_id IN (");
        let mut separated = builder.separated(", ");
        for id in charge_ids {
            separated.push_bind(id);
        }
        separated.push_unseparated(")");
        builder.build().execute(&self.pool).await?;
        Ok(())
    }

    pub async fn get_success_charge_ids_by_user_id(&self, user_id: i64) -> Result<Vec<String>> {
        let rows: Vec<String> = sqlx::query_scalar(
            "SELECT charge_id FROM payments WHERE user_id = ? AND status = 'success'",
        )
        .bind(user_id)
        .fetch_all(&self.pool)
        .await?;
        Ok(rows)
    }

    pub async fn get_all_user_ids(&self) -> Result<Vec<i64>> {
        let rows: Vec<i64> = sqlx::query_scalar("SELECT user_id FROM users")
            .fetch_all(&self.pool)
            .await?;
        Ok(rows)
    }

    pub async fn get_user_id_by_id_or_code(&self, identifier: &str) -> Result<Option<i64>> {
        let ident = identifier.trim();

        if let Ok(uid) = ident.parse::<i64>() {
            let result: Option<i64> =
                sqlx::query_scalar("SELECT user_id FROM users WHERE user_id = ?")
                    .bind(uid)
                    .fetch_optional(&self.pool)
                    .await?;
            if result.is_some() {
                return Ok(result);
            }

            let result: Option<i64> =
                sqlx::query_scalar("SELECT user_id FROM banned WHERE user_id = ?")
                    .bind(uid)
                    .fetch_optional(&self.pool)
                    .await?;
            return Ok(result);
        }

        let result: Option<i64> =
            sqlx::query_scalar("SELECT user_id FROM users WHERE UPPER(anon_code) = UPPER(?)")
                .bind(ident)
                .fetch_optional(&self.pool)
                .await?;
        if result.is_some() {
            return Ok(result);
        }

        let result: Option<i64> =
            sqlx::query_scalar("SELECT user_id FROM banned WHERE UPPER(anon_code) = UPPER(?)")
                .bind(ident)
                .fetch_optional(&self.pool)
                .await?;
        Ok(result)
    }

    /// Grants the achievement unless it is already unlocked.
    pub async fn grant_achievement(&self, user_id: i64, ach_id: &str) -> Result<bool> {
        let exists: Option<i64> =
            sqlx::query_scalar("SELECT 1 FROM user_achievements WHERE user_id = ? AND ach_id = ?")
                .bind(user_id)
                .bind(ach_id)
                .fetch_optional(&self.pool)
                .await?;

        if exists.is_some() {
            return Ok(false);
        }

        sqlx::query("INSERT OR IGNORE INTO user_achievements (user_id, ach_id) VALUES (?, ?)")
            .bind(user_id)
            .bind(ach_id)
            .execute(&self.pool)
            .await?;
        Ok(true)
    }

    pub async fn get_user_achievements(&self, user_id: i64) -> Result<Vec<String>> {
        let rows: Vec<String> =
            sqlx::query_scalar("SELECT ach_id FROM user_achievements WHERE user_id = ?")
                .bind(user_id)
                .fetch_all(&self.pool)
                .await?;
        Ok(rows)
    }

    pub async fn get_user_achievements_count(&self, user_id: i64) -> Result<i64> {
        let count: i64 =
            sqlx::query_scalar("SELECT COUNT(*) FROM user_achievements WHERE user_id = ?")
                .bind(user_id)
                .fetch_one(&self.pool)
                .await?;
        Ok(count)
    }

    pub async fn increment_priority_sent_count(&self, user_id: i64) -> Result<()> {
        sqlx::query(
            "UPDATE users SET priority_sent_count = priority_sent_count + 1 WHERE user_id = ?",
        )
        .bind(user_id)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn increment_total_spent_stars(&self, user_id: i64, amount: i64) -> Result<()> {
        sqlx::query("UPDATE users SET total_spent_stars = total_spent_stars + ? WHERE user_id = ?")
            .bind(amount)
            .bind(user_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn increment_answer_streak(&self, user_id: i64) -> Result<()> {
        sqlx::query("UPDATE users SET answer_streak = answer_streak + 1 WHERE user_id = ?")
            .bind(user_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    /// Evaluates every achievement condition and stores the newly reached
    /// ones. Returns the list of achievements granted by this call.
    pub async fn check_and_grant_achievements(&self, user_id: i64) -> Result<Vec<String>> {
        let row: Option<AchievementStatsRow> = sqlx::query_as(
            r#"SELECT air_purchased, sent_count, received_count, is_vip,
                      priority_sent_count, total_spent_stars, answer_streak
               FROM users WHERE user_id = ?"#,
        )
        .bind(user_id)
        .fetch_optional(&self.pool)
        .await?;

        let Some(row) = row else {
            return Ok(Vec::new());
        };

        let stats = AchievementStats {
            air_purchased: row.air_purchased,
            sent_count: row.sent_count,
            received_count: row.received_count,
            is_vip: row.is_vip != 0,
            priority_sent_count: row.priority_sent_count.unwrap_or(0),
            total_spent_stars: row.total_spent_stars.unwrap_or(0),
            answer_streak: row.answer_streak.unwrap_or(0),
        };

        let mut granted = Vec::new();
        for ach_id in achievements::satisfied(&stats) {
            let inserted = sqlx::query(
                "INSERT OR IGNORE INTO user_achievements (user_id, ach_id) VALUES (?, ?)",
            )
            .bind(user_id)
            .bind(ach_id)
            .execute(&self.pool)
            .await?;
            if inserted.rows_affected() > 0 {
                granted.push(ach_id.to_string());
            }
        }

        Ok(granted)
    }
}
