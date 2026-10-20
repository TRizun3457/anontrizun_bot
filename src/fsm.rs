//! Minimal in-memory FSM replacing aiogram's `FSMContext`.
//!
//! Only the two states used by the bot exist. The chat id is always resolved
//! from `message.chat.id` (aiogram resolves it the same way for messages and
//! for callbacks whose message is accessible).

use std::sync::Arc;

use dashmap::DashMap;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DialogState {
    /// Admin is expected to send the reply for `sender_id`.
    WaitingForReply { sender_id: i64 },
    /// User is expected to send the apology text for a `/ban` appeal.
    Apology { paid_by_balance: bool },
}

#[derive(Clone, Default)]
pub struct Fsm {
    states: Arc<DashMap<(i64, i64), DialogState>>,
}

impl Fsm {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn set(&self, chat_id: i64, user_id: i64, state: DialogState) {
        self.states.insert((chat_id, user_id), state);
    }

    pub fn get(&self, chat_id: i64, user_id: i64) -> Option<DialogState> {
        self.states.get(&(chat_id, user_id)).map(|entry| *entry)
    }

    pub fn clear(&self, chat_id: i64, user_id: i64) {
        self.states.remove(&(chat_id, user_id));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn set_get_and_clear() {
        let fsm = Fsm::new();
        assert_eq!(fsm.get(1, 2), None);

        fsm.set(
            1,
            2,
            DialogState::Apology {
                paid_by_balance: true,
            },
        );
        assert_eq!(
            fsm.get(1, 2),
            Some(DialogState::Apology {
                paid_by_balance: true
            })
        );

        fsm.clear(1, 2);
        assert_eq!(fsm.get(1, 2), None);
    }

    #[test]
    fn state_is_scoped_by_chat_and_user() {
        let fsm = Fsm::new();
        fsm.set(1, 2, DialogState::WaitingForReply { sender_id: 7 });
        assert_eq!(fsm.get(1, 3), None);
        assert_eq!(fsm.get(2, 2), None);
    }
}
