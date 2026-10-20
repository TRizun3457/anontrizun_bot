use std::collections::HashMap;

use anyhow::{Result, bail};

/// Runtime configuration loaded from the environment (and an optional `.env`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Config {
    pub bot_token: String,
    pub admin_id: i64,
    pub allowed_chat_id: Option<i64>,
    pub allowed_chat_link: String,
    pub db_name: String,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        let _ = dotenvy::dotenv();
        Self::from_map(&std::env::vars().collect())
    }

    pub fn from_map(vars: &HashMap<String, String>) -> Result<Self> {
        let bot_token = vars
            .get("BOT_TOKEN")
            .filter(|value| !value.is_empty())
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("BOT_TOKEN не найден в файле .env!"))?;

        let admin_id_raw = vars
            .get("ADMIN_ID")
            .filter(|value| !value.is_empty())
            .ok_or_else(|| anyhow::anyhow!("ADMIN_ID не найден в файле .env!"))?;

        let admin_id: i64 = match admin_id_raw.parse() {
            Ok(value) => value,
            Err(_) => bail!("Ошибка конфигурации: ADMIN_ID в .env должен быть целым числом."),
        };

        let allowed_chat_id = match vars.get("ALLOWED_CHAT_ID").filter(|v| !v.is_empty()) {
            Some(raw) => match raw.parse() {
                Ok(value) => Some(value),
                Err(_) => {
                    bail!("Ошибка конфигурации: ALLOWED_CHAT_ID в .env должен быть целым числом.")
                }
            },
            None => None,
        };

        Ok(Self {
            bot_token,
            admin_id,
            allowed_chat_id,
            allowed_chat_link: vars
                .get("ALLOWED_CHAT_LINK")
                .cloned()
                .unwrap_or_else(|| "https://t.me/trizunchat".to_string()),
            db_name: vars
                .get("DB_NAME")
                .cloned()
                .unwrap_or_else(|| "bot_data.db".to_string()),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn map(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        pairs
            .iter()
            .map(|(key, value)| ((*key).to_string(), (*value).to_string()))
            .collect()
    }

    #[test]
    fn parses_full_configuration() {
        let config = Config::from_map(&map(&[
            ("BOT_TOKEN", "token"),
            ("ADMIN_ID", "42"),
            ("ALLOWED_CHAT_ID", "-100123"),
            ("ALLOWED_CHAT_LINK", "https://t.me/custom"),
            ("DB_NAME", "custom.db"),
        ]))
        .unwrap();

        assert_eq!(
            config,
            Config {
                bot_token: "token".to_string(),
                admin_id: 42,
                allowed_chat_id: Some(-100123),
                allowed_chat_link: "https://t.me/custom".to_string(),
                db_name: "custom.db".to_string(),
            }
        );
    }

    #[test]
    fn applies_defaults() {
        let config = Config::from_map(&map(&[("BOT_TOKEN", "token"), ("ADMIN_ID", "1")])).unwrap();

        assert_eq!(config.allowed_chat_id, None);
        assert_eq!(config.allowed_chat_link, "https://t.me/trizunchat");
        assert_eq!(config.db_name, "bot_data.db");
    }

    #[test]
    fn rejects_missing_token() {
        let error = Config::from_map(&map(&[("ADMIN_ID", "1")])).unwrap_err();
        assert_eq!(error.to_string(), "BOT_TOKEN не найден в файле .env!");
    }

    #[test]
    fn rejects_missing_admin() {
        let error = Config::from_map(&map(&[("BOT_TOKEN", "token")])).unwrap_err();
        assert_eq!(error.to_string(), "ADMIN_ID не найден в файле .env!");
    }

    #[test]
    fn rejects_invalid_admin() {
        let error =
            Config::from_map(&map(&[("BOT_TOKEN", "token"), ("ADMIN_ID", "abc")])).unwrap_err();
        assert_eq!(
            error.to_string(),
            "Ошибка конфигурации: ADMIN_ID в .env должен быть целым числом."
        );
    }

    #[test]
    fn rejects_invalid_allowed_chat() {
        let error = Config::from_map(&map(&[
            ("BOT_TOKEN", "token"),
            ("ADMIN_ID", "1"),
            ("ALLOWED_CHAT_ID", "oops"),
        ]))
        .unwrap_err();
        assert_eq!(
            error.to_string(),
            "Ошибка конфигурации: ALLOWED_CHAT_ID в .env должен быть целым числом."
        );
    }
}
