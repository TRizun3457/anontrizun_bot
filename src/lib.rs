//! AnonTrizun bot: anonymous messaging for Telegram.
//!
//! The crate is split into small modules: [`config`] and [`db`] hold the
//! infrastructure, [`handlers`] contains the user-facing behaviour, and
//! [`api`]/[`error`] wrap the Telegram client with the original retry and
//! error-guard policies.

pub mod achievements;
pub mod api;
pub mod app;
pub mod config;
pub mod constants;
pub mod db;
pub mod error;
pub mod fsm;
pub mod handlers;
pub mod keyboards;
pub mod middlewares;
pub mod texts;
pub mod utils;

use std::{sync::Arc, time::Duration};

use anyhow::{Context, Result};
use teloxide::{
    dispatching::Dispatcher, error_handlers::LoggingErrorHandler, update_listeners::Polling,
};

use crate::api::Api;
use crate::app::AppState;
use crate::config::Config;
use crate::db::Database;
use crate::error::Guard;
use crate::fsm::Fsm;
use crate::middlewares::throttling::Throttle;

/// Throttling limits from the original `main.py`.
const COMMAND_LIMIT_SECONDS: f64 = 0.3;
const TEXT_LIMIT_SECONDS: f64 = 1.2;
const HEAVY_LIMIT_SECONDS: f64 = 2.5;
const NOTIFY_COOLDOWN_SECONDS: f64 = 3.0;
const CLEANUP_INTERVAL_SECONDS: u64 = 300;

/// Initializes `tracing` with `RUST_LOG` support and an `info` default.
pub fn init_tracing() {
    let filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info"));
    tracing_subscriber::fmt().with_env_filter(filter).init();
}

/// Runs the bot until a shutdown signal is received.
pub async fn run() -> Result<()> {
    let config = Config::from_env()?;
    let database = Database::connect(&config.db_name).await?;
    let api = Api::new(teloxide::Bot::new(&config.bot_token));

    let me = api
        .get_me()
        .await
        .context("failed to call getMe for the configured bot token")?;
    let bot_username = me
        .user
        .username
        .clone()
        .context("the bot has no username, commands with mentions cannot be matched")?;

    let state = Arc::new(AppState {
        config,
        db: database.clone(),
        fsm: Fsm::new(),
        throttle: Throttle::new(
            COMMAND_LIMIT_SECONDS,
            TEXT_LIMIT_SECONDS,
            HEAVY_LIMIT_SECONDS,
            NOTIFY_COOLDOWN_SECONDS,
            Duration::from_secs(CLEANUP_INTERVAL_SECONDS),
        ),
        api: api.clone(),
        bot_username,
    });

    let cleanup_task = state.throttle.spawn_cleanup();

    let mut dispatcher = Dispatcher::builder(api.bot().clone(), handlers::schema())
        .dependencies(teloxide::dptree::deps![state.clone()])
        .error_handler(Arc::new(Guard::new(api.clone())))
        .build();

    let shutdown_token = dispatcher.shutdown_token();
    let shutdown_task = tokio::spawn(async move {
        match shutdown_signal().await {
            Ok(()) => {
                if shutdown_token.shutdown().is_err() {
                    tracing::debug!("dispatcher is already shutting down");
                }
            }
            Err(error) => tracing::error!(%error, "failed to install signal handlers"),
        }
    });

    let polling = Polling::builder(api.bot().clone())
        .timeout(Duration::from_secs(60))
        .delete_webhook()
        .await
        .build();

    tracing::info!("🚀 Бот запущен...");

    let dispatch_result = dispatcher
        .try_dispatch_with_listener(polling, LoggingErrorHandler::new())
        .await;

    cleanup_task.abort();
    shutdown_task.abort();
    database.close().await;

    dispatch_result?;

    tracing::info!("🛑 Бот успешно остановлен.");
    Ok(())
}

/// Resolves on `Ctrl+C` (all platforms) or `SIGTERM` (Unix).
async fn shutdown_signal() -> Result<()> {
    #[cfg(unix)]
    {
        use tokio::signal::unix::{SignalKind, signal};

        let mut terminate = signal(SignalKind::terminate())?;
        tokio::select! {
            result = tokio::signal::ctrl_c() => result?,
            _ = terminate.recv() => {}
        }
    }

    #[cfg(not(unix))]
    {
        tokio::signal::ctrl_c().await?;
    }

    Ok(())
}
