use dashmap::DashSet;
use once_cell::sync::Lazy;
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3_async_runtimes::tokio::future_into_py;
use rand::Rng;
use sqlx::{sqlite::SqlitePoolOptions, Row};
use std::sync::Arc;

fn db_err(e: impl std::fmt::Display) -> PyErr {
    PyRuntimeError::new_err(e.to_string())
}

#[derive(Clone)]
pub struct DbState {
    pool: sqlx::SqlitePool,
    ban_cache: Arc<DashSet<i64>>,
}

static DB_STATE: Lazy<Arc<tokio::sync::RwLock<Option<DbState>>>> =
    Lazy::new(|| Arc::new(tokio::sync::RwLock::new(None)));

#[pyclass(get_all, set_all)]
#[derive(Clone)]
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

#[pyclass(get_all)]
#[derive(Clone)]
pub struct SenderWithMessage {
    pub sender_id: i64,
    pub user_msg_id: i64,
}

#[pyclass(get_all)]
#[derive(Clone)]
pub struct SenderWithCode {
    pub sender_id: i64,
    pub anon_code: String,
}

#[pyclass(get_all)]
#[derive(Clone)]
pub struct BannedUser {
    pub user_id: i64,
    pub anon_code: String,
}

fn generate_anon_code() -> String {
    const CHARSET: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    let mut rng = rand::thread_rng();
    (0..8)
        .map(|_| CHARSET[rng.gen_range(0..CHARSET.len())] as char)
        .collect()
}

#[pymodule]
fn database(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<UserStats>()?;
    m.add_class::<SenderWithMessage>()?;
    m.add_class::<SenderWithCode>()?;
    m.add_class::<BannedUser>()?;
    m.add_function(wrap_pyfunction!(init_db, m)?)?;
    m.add_function(wrap_pyfunction!(is_banned, m)?)?;
    m.add_function(wrap_pyfunction!(ban_user, m)?)?;
    m.add_function(wrap_pyfunction!(delete_old_user_code_records, m)?)?;
    m.add_function(wrap_pyfunction!(unban_user, m)?)?;
    m.add_function(wrap_pyfunction!(regenerate_user_code, m)?)?;
    m.add_function(wrap_pyfunction!(register_user, m)?)?;
    m.add_function(wrap_pyfunction!(get_user_stats, m)?)?;
    m.add_function(wrap_pyfunction!(update_user_setting, m)?)?;
    m.add_function(wrap_pyfunction!(waste_priority_message, m)?)?;
    m.add_function(wrap_pyfunction!(increment_sent_count, m)?)?;
    m.add_function(wrap_pyfunction!(increment_received_count, m)?)?;
    m.add_function(wrap_pyfunction!(add_message, m)?)?;
    m.add_function(wrap_pyfunction!(get_admin_msg_id_by_user_msg_id, m)?)?;
    m.add_function(wrap_pyfunction!(get_sender_with_message_by_admin_msg, m)?)?;
    m.add_function(wrap_pyfunction!(take_balance, m)?)?;
    m.add_function(wrap_pyfunction!(increment_priority_messages, m)?)?;
    m.add_function(wrap_pyfunction!(set_vip, m)?)?;
    m.add_function(wrap_pyfunction!(increment_air_purchased, m)?)?;
    m.add_function(wrap_pyfunction!(get_banned_users, m)?)?;
    m.add_function(wrap_pyfunction!(get_banned_user_id_by_anon_code, m)?)?;
    m.add_function(wrap_pyfunction!(get_sender_with_code_by_admin_msg, m)?)?;
    m.add_function(wrap_pyfunction!(create_payment, m)?)?;
    m.add_function(wrap_pyfunction!(give_balance, m)?)?;
    m.add_function(wrap_pyfunction!(get_banned_anon_code_by_user_id, m)?)?;
    m.add_function(wrap_pyfunction!(get_payment_user_id_by_charge_id, m)?)?;
    m.add_function(wrap_pyfunction!(set_payment_status_by_charge_id, m)?)?;
    m.add_function(wrap_pyfunction!(batch_set_payment_status_by_charge_ids, m)?)?;
    m.add_function(wrap_pyfunction!(get_success_charge_ids_by_user_id, m)?)?;
    m.add_function(wrap_pyfunction!(get_all_user_ids, m)?)?;
    m.add_function(wrap_pyfunction!(get_user_id_by_id_or_code, m)?)?;
    m.add_function(wrap_pyfunction!(grant_achievement, m)?)?;
    m.add_function(wrap_pyfunction!(get_user_achievements, m)?)?;
    m.add_function(wrap_pyfunction!(get_user_achievements_count, m)?)?;
    m.add_function(wrap_pyfunction!(increment_priority_sent_count, m)?)?;
    m.add_function(wrap_pyfunction!(increment_total_spent_stars, m)?)?;
    m.add_function(wrap_pyfunction!(increment_answer_streak, m)?)?;
    m.add_function(wrap_pyfunction!(check_and_grant_achievements, m)?)?;
    Ok(())
}

async fn get_state() -> PyResult<DbState> {
    let state = DB_STATE.read().await;
    state
        .clone()
        .ok_or_else(|| PyRuntimeError::new_err("Database not initialized"))
}

#[pyfunction]
#[pyo3(signature = (db_path = String::from("bot.db")))]
fn init_db(py: Python<'_>, db_path: String) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let pool = SqlitePoolOptions::new()
            .max_connections(5)
            .connect(&db_path)
            .await
            .map_err(db_err)?;

        sqlx::query("PRAGMA journal_mode=WAL;")
            .execute(&pool)
            .await
            .map_err(db_err)?;
        sqlx::query("PRAGMA synchronous=NORMAL;")
            .execute(&pool)
            .await
            .map_err(db_err)?;

        sqlx::query(
            r#"CREATE TABLE IF NOT EXISTS messages (
                admin_msg_id INTEGER PRIMARY KEY,
                sender_id INTEGER,
                anon_code TEXT,
                is_priority INTEGER DEFAULT 0,
                user_msg_id INTEGER
            )"#,
        )
        .execute(&pool)
        .await
        .map_err(db_err)?;

        sqlx::query(
            r#"CREATE TABLE IF NOT EXISTS banned (
                user_id INTEGER PRIMARY KEY,
                anon_code TEXT
            )"#,
        )
        .execute(&pool)
        .await
        .map_err(db_err)?;

        sqlx::query(
            r#"CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 0,
                air_purchased INTEGER DEFAULT 0,
                priority_messages INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                received_count INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0,
                referrer_id INTEGER DEFAULT NULL,
                anon_code TEXT,
                priority_sent_count INTEGER DEFAULT 0,
                total_spent_stars INTEGER DEFAULT 0,
                answer_streak INTEGER DEFAULT 0,
                code_auto_refresh TEXT DEFAULT 'never',
                show_vip_cats INTEGER DEFAULT 1,
                inline_share_mode TEXT DEFAULT 'full',
                show_air INTEGER DEFAULT 1,
                show_priority INTEGER DEFAULT 1,
                show_sent INTEGER DEFAULT 1,
                show_received INTEGER DEFAULT 1,
                show_achievements INTEGER DEFAULT 1
            )"#,
        )
        .execute(&pool)
        .await
        .map_err(db_err)?;

        sqlx::query(
            r#"CREATE TABLE IF NOT EXISTS payments (
                charge_id TEXT PRIMARY KEY,
                user_id INTEGER,
                payload TEXT,
                status TEXT DEFAULT 'success'
            )"#,
        )
        .execute(&pool)
        .await
        .map_err(db_err)?;

        sqlx::query(
            r#"CREATE TABLE IF NOT EXISTS user_achievements (
                user_id INTEGER,
                ach_id TEXT,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, ach_id)
            )"#,
        )
        .execute(&pool)
        .await
        .map_err(db_err)?;

        let migrations = [
            "ALTER TABLE users ADD COLUMN anon_code TEXT",
            "ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN priority_sent_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN total_spent_stars INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN answer_streak INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN code_auto_refresh TEXT DEFAULT 'never'",
            "ALTER TABLE users ADD COLUMN show_vip_cats INTEGER DEFAULT 1",
            "ALTER TABLE users ADD COLUMN inline_share_mode TEXT DEFAULT 'full'",
            "ALTER TABLE users ADD COLUMN show_air INTEGER DEFAULT 1",
            "ALTER TABLE users ADD COLUMN show_priority INTEGER DEFAULT 1",
            "ALTER TABLE users ADD COLUMN show_sent INTEGER DEFAULT 1",
            "ALTER TABLE users ADD COLUMN show_received INTEGER DEFAULT 1",
            "ALTER TABLE users ADD COLUMN show_achievements INTEGER DEFAULT 1",
        ];

        for query in migrations {
            let _ = sqlx::query(query).execute(&pool).await;
        }

        let ban_cache = DashSet::new();
        let rows = sqlx::query("SELECT user_id FROM banned")
            .fetch_all(&pool)
            .await
            .map_err(db_err)?;
        for row in rows {
            ban_cache.insert(row.get::<i64, _>(0));
        }

        let mut state = DB_STATE.write().await;
        *state = Some(DbState {
            pool,
            ban_cache: Arc::new(ban_cache),
        });

        Ok(())
    })
}

#[pyfunction]
fn is_banned(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        Ok(state.ban_cache.contains(&user_id))
    })
}

#[pyfunction]
fn ban_user(py: Python<'_>, user_id: i64, anon_code: String) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query("INSERT OR REPLACE INTO banned (user_id, anon_code) VALUES (?, ?)")
            .bind(user_id)
            .bind(&anon_code)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        state.ban_cache.insert(user_id);
        Ok(())
    })
}

#[pyfunction]
fn delete_old_user_code_records(
    py: Python<'_>,
    user_id: i64,
    old_code: String,
) -> PyResult<Bound<'_, PyAny>> {
    if old_code.is_empty() || old_code == "НЕИЗВЕСТНО" {
        return future_into_py(py, async move { Ok(()) });
    }
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query(
            "UPDATE messages SET anon_code = NULL WHERE sender_id = ? AND UPPER(anon_code) = UPPER(?)"
        )
        .bind(user_id)
        .bind(&old_code)
        .execute(&state.pool)
        .await
        .map_err(db_err)?;

        sqlx::query("DELETE FROM banned WHERE user_id = ? AND UPPER(anon_code) = UPPER(?)")
            .bind(user_id)
            .bind(&old_code)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn unban_user(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;

        let old_code: Option<String> =
            sqlx::query_scalar("SELECT anon_code FROM banned WHERE user_id = ?")
                .bind(user_id)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?;

        let old_code = if let Some(code) = old_code {
            code
        } else {
            sqlx::query_scalar("SELECT anon_code FROM users WHERE user_id = ?")
                .bind(user_id)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?
                .unwrap_or_else(|| "НЕИЗВЕСТНО".to_string())
        };

        let new_anon_code = generate_anon_code();

        sqlx::query("UPDATE users SET anon_code = ? WHERE user_id = ?")
            .bind(&new_anon_code)
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;

        sqlx::query("DELETE FROM banned WHERE user_id = ?")
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;

        if old_code != "НЕИЗВЕСТНО" {
            sqlx::query(
                "UPDATE messages SET anon_code = NULL WHERE sender_id = ? AND UPPER(anon_code) = UPPER(?)"
            )
            .bind(user_id)
            .bind(&old_code)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
            sqlx::query("DELETE FROM banned WHERE user_id = ? AND UPPER(anon_code) = UPPER(?)")
                .bind(user_id)
                .bind(&old_code)
                .execute(&state.pool)
                .await
                .map_err(db_err)?;
        }

        state.ban_cache.remove(&user_id);
        Ok(new_anon_code)
    })
}

#[pyfunction]
fn regenerate_user_code(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        if state.ban_cache.contains(&user_id) {
            return Ok((
                false,
                "Вы заблокированы! Изменение кода заблокировано до разбана.".to_string(),
            ));
        }

        let old_code: Option<String> =
            sqlx::query_scalar("SELECT anon_code FROM users WHERE user_id = ?")
                .bind(user_id)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?;

        let new_code = generate_anon_code();

        sqlx::query("UPDATE users SET anon_code = ? WHERE user_id = ?")
            .bind(&new_code)
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;

        if let Some(ref old) = old_code {
            if old != "НЕИЗВЕСТНО" {
                sqlx::query(
                    "UPDATE messages SET anon_code = NULL WHERE sender_id = ? AND UPPER(anon_code) = UPPER(?)"
                )
                .bind(user_id)
                .bind(old)
                .execute(&state.pool)
                .await
                .map_err(db_err)?;
                sqlx::query("DELETE FROM banned WHERE user_id = ? AND UPPER(anon_code) = UPPER(?)")
                    .bind(user_id)
                    .bind(old)
                    .execute(&state.pool)
                    .await
                    .map_err(db_err)?;
            }
        }

        Ok((true, new_code))
    })
}

async fn get_user_stats_int(user_id: i64, state: &DbState) -> PyResult<UserStats> {
    let row: Option<(
        i64,
        i64,
        i64,
        i64,
        i64,
        i64,
        Option<String>,
        Option<String>,
        i64,
        i64,
        i64,
        i64,
        i64,
        i64,
    )> = sqlx::query_as(
        r#"SELECT balance, air_purchased, priority_messages, sent_count, received_count,
               is_vip, anon_code, code_auto_refresh, show_vip_cats, show_achievements,
               show_air, show_priority, show_sent, show_received
               FROM users WHERE user_id = ?"#,
    )
    .bind(user_id)
    .fetch_optional(&state.pool)
    .await
    .map_err(db_err)?;

    if let Some(r) = row {
        Ok(UserStats {
            balance: r.0,
            air_purchased: r.1,
            priority_messages: r.2,
            sent_count: r.3,
            received_count: r.4,
            is_vip: r.5 != 0,
            anon_code: r.6.unwrap_or_else(|| "НЕИЗВЕСТНО".to_string()),
            code_auto_refresh: r.7.unwrap_or_else(|| "never".to_string()),
            show_vip_cats: r.8 != 0,
            show_achievements: r.9 != 0,
            show_air: r.10 != 0,
            show_priority: r.11 != 0,
            show_sent: r.12 != 0,
            show_received: r.13 != 0,
        })
    } else {
        Ok(UserStats::default())
    }
}

#[pyfunction]
#[pyo3(signature = (user_id, referrer_id=None))]
fn register_user(
    py: Python<'_>,
    user_id: i64,
    referrer_id: Option<i64>,
) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;

        let existing: Option<String> =
            sqlx::query_scalar("SELECT anon_code FROM users WHERE user_id = ?")
                .bind(user_id)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?;

        if existing.is_some() {
            return get_user_stats_int(user_id, &state).await;
        }

        let anon_code = generate_anon_code();
        let ref_id = referrer_id.filter(|&r| r != user_id);

        sqlx::query(
            "INSERT OR IGNORE INTO users (user_id, anon_code, referrer_id) VALUES (?, ?, ?)",
        )
        .bind(user_id)
        .bind(&anon_code)
        .bind(ref_id)
        .execute(&state.pool)
        .await
        .map_err(db_err)?;

        sqlx::query(
            "UPDATE users SET anon_code = ? WHERE user_id = ? AND (anon_code IS NULL OR anon_code = '')"
        )
        .bind(&anon_code)
        .bind(user_id)
        .execute(&state.pool)
        .await
        .map_err(db_err)?;

        get_user_stats_int(user_id, &state).await
    })
}

#[pyfunction]
fn get_user_stats(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        get_user_stats_int(user_id, &state).await
    })
}

#[pyfunction]
fn update_user_setting(
    py: Python<'_>,
    user_id: i64,
    key: String,
    value: String,
) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let allowed = [
            "code_auto_refresh",
            "show_vip_cats",
            "show_air",
            "show_priority",
            "show_sent",
            "show_received",
            "show_achievements",
            "inline_share_mode",
        ];
        if !allowed.contains(&key.as_str()) {
            return Err(PyRuntimeError::new_err(format!(
                "Invalid setting key: {}",
                key
            )));
        }
        let state = get_state().await?;
        let query = format!("UPDATE users SET {} = ? WHERE user_id = ?", key);
        sqlx::query(&query)
            .bind(value)
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn waste_priority_message(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query("UPDATE users SET priority_messages = priority_messages - 1 WHERE user_id = ?")
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn increment_sent_count(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query("UPDATE users SET sent_count = sent_count + 1 WHERE user_id = ?")
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn increment_received_count(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query("UPDATE users SET received_count = received_count + 1 WHERE user_id = ?")
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn add_message(
    py: Python<'_>,
    admin_msg_id: i64,
    sender_id: i64,
    anon_code: String,
    is_priority: bool,
    user_msg_id: i64,
) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query(
            "INSERT INTO messages (admin_msg_id, sender_id, anon_code, is_priority, user_msg_id) VALUES (?, ?, ?, ?, ?)"
        )
        .bind(admin_msg_id)
        .bind(sender_id)
        .bind(anon_code)
        .bind(if is_priority { 1 } else { 0 })
        .bind(user_msg_id)
        .execute(&state.pool)
        .await
        .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn get_admin_msg_id_by_user_msg_id(
    py: Python<'_>,
    sender_id: i64,
    user_msg_id: i64,
) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let res: Option<i64> = sqlx::query_scalar(
            "SELECT admin_msg_id FROM messages WHERE sender_id = ? AND user_msg_id = ?",
        )
        .bind(sender_id)
        .bind(user_msg_id)
        .fetch_optional(&state.pool)
        .await
        .map_err(db_err)?;
        Ok(res)
    })
}

#[pyfunction]
fn get_sender_with_message_by_admin_msg(
    py: Python<'_>,
    admin_msg_id: i64,
) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let row: Option<(i64, i64)> =
            sqlx::query_as("SELECT sender_id, user_msg_id FROM messages WHERE admin_msg_id = ?")
                .bind(admin_msg_id)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?;

        if let Some((sender_id, user_msg_id)) = row {
            Ok(Some(SenderWithMessage {
                sender_id,
                user_msg_id,
            }))
        } else {
            Ok(None)
        }
    })
}

#[pyfunction]
fn take_balance(py: Python<'_>, amount: i64, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query("UPDATE users SET balance = balance - ? WHERE user_id = ?")
            .bind(amount)
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn increment_priority_messages(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query("UPDATE users SET priority_messages = priority_messages + 1 WHERE user_id = ?")
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn set_vip(py: Python<'_>, user_id: i64, vip: bool) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query("UPDATE users SET is_vip = ? WHERE user_id = ?")
            .bind(if vip { 1 } else { 0 })
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn increment_air_purchased(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query("UPDATE users SET air_purchased = air_purchased + 1 WHERE user_id = ?")
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn get_banned_users(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let rows: Vec<(i64, String)> = sqlx::query_as("SELECT user_id, anon_code FROM banned")
            .fetch_all(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(rows
            .into_iter()
            .map(|(user_id, anon_code)| BannedUser { user_id, anon_code })
            .collect::<Vec<_>>())
    })
}

#[pyfunction]
fn get_banned_user_id_by_anon_code(
    py: Python<'_>,
    anon_code: String,
) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let res: Option<i64> = sqlx::query_scalar("SELECT user_id FROM banned WHERE anon_code = ?")
            .bind(anon_code)
            .fetch_optional(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(res)
    })
}

#[pyfunction]
fn get_sender_with_code_by_admin_msg(
    py: Python<'_>,
    admin_msg_id: i64,
) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let row: Option<(i64, Option<String>)> =
            sqlx::query_as("SELECT sender_id, anon_code FROM messages WHERE admin_msg_id = ?")
                .bind(admin_msg_id)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?;

        if let Some((sender_id, anon_code)) = row {
            let code = if let Some(c) = anon_code {
                c
            } else {
                let stats = get_user_stats_int(sender_id, &state).await?;
                stats.anon_code
            };
            Ok(Some(SenderWithCode {
                sender_id,
                anon_code: code,
            }))
        } else {
            Ok(None)
        }
    })
}

#[pyfunction]
fn create_payment(
    py: Python<'_>,
    charge_id: String,
    user_id: i64,
    payload: String,
) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let result = sqlx::query(
            "INSERT OR IGNORE INTO payments (charge_id, user_id, payload, status) VALUES (?, ?, ?, 'success')"
        )
        .bind(charge_id)
        .bind(user_id)
        .bind(payload)
        .execute(&state.pool)
        .await
        .map_err(db_err)?;

        Ok(result.rows_affected() > 0)
    })
}

#[pyfunction]
fn give_balance(py: Python<'_>, amount: i64, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query("UPDATE users SET balance = balance + ? WHERE user_id = ?")
            .bind(amount)
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn get_banned_anon_code_by_user_id(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let res: Option<String> =
            sqlx::query_scalar("SELECT anon_code FROM banned WHERE user_id = ?")
                .bind(user_id)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?;
        Ok(res.unwrap_or_else(|| "НЕИЗВЕСТНО".to_string()))
    })
}

#[pyfunction]
fn get_payment_user_id_by_charge_id(
    py: Python<'_>,
    charge_id: String,
) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let res: Option<i64> =
            sqlx::query_scalar("SELECT user_id FROM payments WHERE charge_id = ?")
                .bind(charge_id)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?;
        Ok(res)
    })
}

#[pyfunction]
fn set_payment_status_by_charge_id(
    py: Python<'_>,
    charge_id: String,
    status: String,
) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query("UPDATE payments SET status = ? WHERE charge_id = ?")
            .bind(status)
            .bind(charge_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn batch_set_payment_status_by_charge_ids(
    py: Python<'_>,
    charge_ids: Vec<String>,
    status: String,
) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        if charge_ids.is_empty() {
            return Ok(());
        }
        let state = get_state().await?;
        let placeholders = vec!["?"; charge_ids.len()].join(", ");
        let query = format!(
            "UPDATE payments SET status = ? WHERE charge_id IN ({})",
            placeholders
        );

        let mut q = sqlx::query(&query).bind(&status);
        for id in charge_ids {
            q = q.bind(id);
        }
        q.execute(&state.pool).await.map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn get_success_charge_ids_by_user_id(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let rows: Vec<String> = sqlx::query_scalar(
            "SELECT charge_id FROM payments WHERE user_id = ? AND status = 'success'",
        )
        .bind(user_id)
        .fetch_all(&state.pool)
        .await
        .map_err(db_err)?;
        Ok(rows)
    })
}

#[pyfunction]
fn get_all_user_ids(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let rows: Vec<i64> = sqlx::query_scalar("SELECT user_id FROM users")
            .fetch_all(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(rows)
    })
}

#[pyfunction]
fn get_user_id_by_id_or_code(py: Python<'_>, identifier: String) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let ident = identifier.trim();

        if let Ok(uid) = ident.parse::<i64>() {
            let res: Option<i64> =
                sqlx::query_scalar("SELECT user_id FROM users WHERE user_id = ?")
                    .bind(uid)
                    .fetch_optional(&state.pool)
                    .await
                    .map_err(db_err)?;
            if res.is_some() {
                return Ok(res);
            }
            let res: Option<i64> =
                sqlx::query_scalar("SELECT user_id FROM banned WHERE user_id = ?")
                    .bind(uid)
                    .fetch_optional(&state.pool)
                    .await
                    .map_err(db_err)?;
            if res.is_some() {
                return Ok(res);
            }
            return Ok(Some(uid));
        }

        let res: Option<i64> =
            sqlx::query_scalar("SELECT user_id FROM users WHERE UPPER(anon_code) = UPPER(?)")
                .bind(ident)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?;
        if res.is_some() {
            return Ok(res);
        }

        let res: Option<i64> =
            sqlx::query_scalar("SELECT user_id FROM banned WHERE UPPER(anon_code) = UPPER(?)")
                .bind(ident)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?;
        Ok(res)
    })
}

#[pyfunction]
fn grant_achievement(py: Python<'_>, user_id: i64, ach_id: String) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let exists: Option<i64> =
            sqlx::query_scalar("SELECT 1 FROM user_achievements WHERE user_id = ? AND ach_id = ?")
                .bind(user_id)
                .bind(&ach_id)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?;

        if exists.is_some() {
            return Ok(false);
        }

        sqlx::query("INSERT OR IGNORE INTO user_achievements (user_id, ach_id) VALUES (?, ?)")
            .bind(user_id)
            .bind(&ach_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(true)
    })
}

#[pyfunction]
fn get_user_achievements(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let rows: Vec<String> =
            sqlx::query_scalar("SELECT ach_id FROM user_achievements WHERE user_id = ?")
                .bind(user_id)
                .fetch_all(&state.pool)
                .await
                .map_err(db_err)?;
        Ok(rows)
    })
}

#[pyfunction]
fn get_user_achievements_count(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let count: Option<i64> =
            sqlx::query_scalar("SELECT COUNT(*) FROM user_achievements WHERE user_id = ?")
                .bind(user_id)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?;
        Ok(count.unwrap_or(0))
    })
}

#[pyfunction]
fn increment_priority_sent_count(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query(
            "UPDATE users SET priority_sent_count = priority_sent_count + 1 WHERE user_id = ?",
        )
        .bind(user_id)
        .execute(&state.pool)
        .await
        .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn increment_total_spent_stars(
    py: Python<'_>,
    user_id: i64,
    amount: i64,
) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query("UPDATE users SET total_spent_stars = total_spent_stars + ? WHERE user_id = ?")
            .bind(amount)
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn increment_answer_streak(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        sqlx::query("UPDATE users SET answer_streak = answer_streak + 1 WHERE user_id = ?")
            .bind(user_id)
            .execute(&state.pool)
            .await
            .map_err(db_err)?;
        Ok(())
    })
}

#[pyfunction]
fn check_and_grant_achievements(py: Python<'_>, user_id: i64) -> PyResult<Bound<'_, PyAny>> {
    future_into_py(py, async move {
        let state = get_state().await?;
        let row: Option<(i64, i64, i64, i64, Option<i64>, Option<i64>, Option<i64>)> =
            sqlx::query_as(
                r#"SELECT air_purchased, sent_count, received_count, is_vip,
                       priority_sent_count, total_spent_stars, answer_streak
                       FROM users WHERE user_id = ?"#,
            )
            .bind(user_id)
            .fetch_optional(&state.pool)
            .await
            .map_err(db_err)?;

        if row.is_none() {
            return Ok(Vec::<String>::new());
        }

        let (
            air_purchased,
            sent_count,
            received_count,
            is_vip,
            priority_sent_count,
            total_spent_stars,
            answer_streak,
        ) = row.unwrap();

        let mut granted = Vec::new();
        let achievements_to_check = [
            ("air_1", air_purchased >= 1),
            ("air_10", air_purchased >= 10),
            ("air_100", air_purchased >= 100),
            ("vip_access", is_vip != 0),
            ("anon_first", sent_count >= 1),
            ("who_are_you", sent_count >= 100),
            ("secret_fan", sent_count >= 200),
            ("vip_person", priority_sent_count.unwrap_or(0) >= 10),
            ("not_interested", (sent_count - received_count) >= 20),
            ("answer_streak_15", answer_streak.unwrap_or(0) >= 15),
            ("star_fall", total_spent_stars.unwrap_or(0) > 100),
        ];

        for (ach_id, condition) in achievements_to_check {
            if condition {
                let exists: Option<i64> = sqlx::query_scalar(
                    "SELECT 1 FROM user_achievements WHERE user_id = ? AND ach_id = ?",
                )
                .bind(user_id)
                .bind(ach_id)
                .fetch_optional(&state.pool)
                .await
                .map_err(db_err)?;

                if exists.is_none() {
                    sqlx::query(
                        "INSERT OR IGNORE INTO user_achievements (user_id, ach_id) VALUES (?, ?)",
                    )
                    .bind(user_id)
                    .bind(ach_id)
                    .execute(&state.pool)
                    .await
                    .map_err(db_err)?;
                    granted.push(ach_id.to_string());
                }
            }
        }

        Ok(granted)
    })
}
