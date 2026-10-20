//! Request retry policy.
//!
//! The original `RetrySession` retried network failures, timeouts and Telegram
//! server errors up to three times with `1s`, `2s` delays plus up to 10% jitter,
//! and skipped retries for `sendMessage`, `copyMessage` and `refundStarPayment`.
//! Requests built with [`retry_request`] follow the same policy; the excluded
//! methods call the bot directly.
//!
//! Two differences come from the HTTP layer itself:
//!
//! * `teloxide` already waits 10 seconds before parsing a `5xx` response, and
//!   it reports such responses as an API error without the status code, so they
//!   cannot be retried here and end up in the error guard instead.
//! * Timeouts and connection resets arrive as `RequestError::Network`, and a
//!   response body that cannot be parsed as JSON is retried as well, because
//!   both usually mean a truncated or corrupted response.

use std::time::Duration;

use teloxide::{
    errors::{ApiError, RequestError},
    requests::{Output, Request},
};

pub const MAX_ATTEMPTS: usize = 3;
const BASE_DELAY_SECONDS: f64 = 1.0;
const MAX_DELAY_SECONDS: f64 = 30.0;

/// Network-level failures that are worth retrying.
pub fn is_retryable(error: &RequestError) -> bool {
    matches!(
        error,
        RequestError::Network(_) | RequestError::InvalidJson { .. }
    )
}

/// Human-readable description used by the refund command.
pub fn request_error_description(error: &RequestError) -> String {
    match error {
        RequestError::Api(ApiError::Unknown(message)) => message.clone(),
        other => other.to_string(),
    }
}

/// Sends `request`, retrying retryable failures with exponential backoff.
pub async fn retry_request<R>(request: R) -> Result<Output<R>, RequestError>
where
    R: Request<Err = RequestError> + Clone,
{
    let mut attempt = 0;

    loop {
        attempt += 1;

        match request.clone().send().await {
            Ok(output) => return Ok(output),
            Err(error) if attempt < MAX_ATTEMPTS && is_retryable(&error) => {
                let exponent = u32::try_from(attempt - 1).unwrap_or(u32::MAX);
                let delay =
                    (BASE_DELAY_SECONDS * 2f64.powi(exponent as i32)).min(MAX_DELAY_SECONDS);
                let jitter = rand::random_range(0.0..=(0.1 * delay));
                let total_delay = delay + jitter;

                tracing::warn!(
                    attempt,
                    max_attempts = MAX_ATTEMPTS,
                    delay_seconds = total_delay,
                    error = %error,
                    "network failure, retrying Telegram request"
                );

                tokio::time::sleep(Duration::from_secs_f64(total_delay)).await;
            }
            Err(error) => return Err(error),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_network_and_json_errors_are_retryable() {
        let invalid_json = RequestError::InvalidJson {
            source: std::sync::Arc::new(
                serde_json::from_str::<i32>("not json").expect_err("must fail"),
            ),
            raw: "not json".into(),
        };
        assert!(is_retryable(&invalid_json));
        assert!(!is_retryable(&RequestError::Api(ApiError::Unknown(
            "Bad Request".to_string()
        ))));
        assert!(!is_retryable(&RequestError::RetryAfter(
            teloxide::types::Seconds::from_seconds(5)
        )));
    }

    #[test]
    fn refund_error_uses_the_api_description() {
        let error = RequestError::Api(ApiError::Unknown("CHARGE_ALREADY_REFUNDED".to_string()));
        assert_eq!(request_error_description(&error), "CHARGE_ALREADY_REFUNDED");
    }
}
