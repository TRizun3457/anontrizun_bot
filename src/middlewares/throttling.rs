//! `ThrottlingMiddleware`: per-user rate limits with a notice cooldown.
//!
//! Limits are measured with a monotonic clock. In groups only commands
//! addressed to this bot are throttled, exact same as the original.

use std::{
    sync::Arc,
    time::{Duration, Instant},
};

use dashmap::DashMap;
use teloxide::types::{Message, MessageEntityKind};
use tokio::task::JoinHandle;

use crate::api::Api;
use crate::texts;

#[derive(Clone)]
pub struct Throttle {
    command_limit: Duration,
    text_limit: Duration,
    heavy_limit: Duration,
    notify_cooldown: Duration,
    cleanup_interval: Duration,
    timeouts: Arc<DashMap<i64, Instant>>,
    notify_timeouts: Arc<DashMap<i64, Instant>>,
}

impl Throttle {
    pub fn new(
        command_limit: f64,
        text_limit: f64,
        heavy_limit: f64,
        notify_cooldown: f64,
        cleanup_interval: Duration,
    ) -> Self {
        Self {
            command_limit: Duration::from_secs_f64(command_limit),
            text_limit: Duration::from_secs_f64(text_limit),
            heavy_limit: Duration::from_secs_f64(heavy_limit),
            notify_cooldown: Duration::from_secs_f64(notify_cooldown),
            cleanup_interval,
            timeouts: Arc::new(DashMap::new()),
            notify_timeouts: Arc::new(DashMap::new()),
        }
    }

    /// Starts the periodic cleanup task (equivalent to `start` in the
    /// original middleware).
    pub fn spawn_cleanup(&self) -> JoinHandle<()> {
        let throttle = self.clone();
        tokio::spawn(async move {
            let max_limit = throttle
                .command_limit
                .max(throttle.text_limit)
                .max(throttle.heavy_limit)
                .max(throttle.notify_cooldown);

            loop {
                tokio::time::sleep(throttle.cleanup_interval).await;
                let now = Instant::now();
                throttle
                    .timeouts
                    .retain(|_, last_time| now.duration_since(*last_time) <= max_limit);
                throttle
                    .notify_timeouts
                    .retain(|_, last_time| now.duration_since(*last_time) <= max_limit);
            }
        })
    }

    fn rate_limit(&self, message: &Message) -> Duration {
        if message.entities().is_some_and(|entities| {
            !entities.is_empty()
                && entities
                    .iter()
                    .any(|entity| entity.kind == MessageEntityKind::BotCommand)
        }) {
            return self.command_limit;
        }

        if message.photo().is_some()
            || message.video().is_some()
            || message.document().is_some()
            || message.voice().is_some()
            || message.audio().is_some()
        {
            return self.heavy_limit;
        }

        self.text_limit
    }

    /// Returns `true` when the message must be processed.
    pub async fn check(&self, message: &Message, bot_username: &str, api: &Api) -> bool {
        let Some(from) = message.from.as_ref() else {
            return true;
        };

        let in_group = !message.chat.is_private();
        if in_group && !is_command_for_bot(message, bot_username) {
            return true;
        }

        let user_id = from.id.0 as i64;
        let now = Instant::now();
        let required_limit = self.rate_limit(message);

        let too_fast = self
            .timeouts
            .get(&user_id)
            .is_some_and(|last_time| now.duration_since(*last_time) < required_limit);

        if too_fast {
            if !in_group {
                let notify_due = self
                    .notify_timeouts
                    .get(&user_id)
                    .is_none_or(|last_time| now.duration_since(*last_time) >= self.notify_cooldown);

                if notify_due {
                    self.notify_timeouts.insert(user_id, now);
                    if let Err(error) = api
                        .send_plain_message(message.chat.id, texts::THROTTLE_NOTICE_TEXT)
                        .await
                    {
                        tracing::debug!(%error, user_id, "throttle notice was not delivered");
                    }
                }
            }
            return false;
        }

        self.timeouts.insert(user_id, now);
        true
    }
}

/// Mirrors `ThrottlingMiddleware._is_command_for_bot`.
fn is_command_for_bot(message: &Message, bot_username: &str) -> bool {
    let text = message
        .text()
        .or_else(|| message.caption())
        .unwrap_or_default();

    let entities = message
        .entities()
        .filter(|entities| !entities.is_empty())
        .or_else(|| {
            message
                .caption_entities()
                .filter(|entities| !entities.is_empty())
        })
        .unwrap_or(&[]);

    for entity in entities {
        if entity.kind != MessageEntityKind::BotCommand || entity.offset != 0 {
            continue;
        }

        let units: Vec<u16> = text.encode_utf16().take(entity.length).collect();
        let command = String::from_utf16_lossy(&units);

        let target = match command.split_once('@') {
            Some((_, target)) => target,
            None => "",
        };

        if target.is_empty() {
            return true;
        }
        return target.to_lowercase() == bot_username.to_lowercase();
    }

    false
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use super::*;

    fn throttle() -> Throttle {
        Throttle::new(0.3, 1.2, 2.5, 3.0, Duration::from_secs(300))
    }

    #[test]
    fn limits_are_configured_as_in_main() {
        let throttle = throttle();
        assert_eq!(throttle.command_limit, Duration::from_secs_f64(0.3));
        assert_eq!(throttle.text_limit, Duration::from_secs_f64(1.2));
        assert_eq!(throttle.heavy_limit, Duration::from_secs_f64(2.5));
        assert_eq!(throttle.notify_cooldown, Duration::from_secs_f64(3.0));
    }
}
