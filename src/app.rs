//! Shared state injected into every handler.

use crate::api::Api;
use crate::config::Config;
use crate::db::Database;
use crate::fsm::Fsm;
use crate::middlewares::throttling::Throttle;

#[derive(Clone)]
pub struct AppState {
    pub config: Config,
    pub db: Database,
    pub fsm: Fsm,
    pub throttle: Throttle,
    pub api: Api,
    pub bot_username: String,
}
