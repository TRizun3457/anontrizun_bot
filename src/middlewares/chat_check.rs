//! `AllowedChatMiddleware`: drops non-private messages outside the allowed
//! chat when `ALLOWED_CHAT_ID` is configured.

use teloxide::types::Chat;

/// Pure predicate kept separate for testability.
pub fn chat_is_allowed(is_private: bool, chat_id: i64, allowed_chat_id: Option<i64>) -> bool {
    match allowed_chat_id {
        None => true,
        Some(allowed) => is_private || chat_id == allowed,
    }
}

pub fn chat_allowed(chat: &Chat, allowed_chat_id: Option<i64>) -> bool {
    chat_is_allowed(chat.is_private(), chat.id.0, allowed_chat_id)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn without_configuration_every_chat_is_allowed() {
        assert!(chat_is_allowed(false, -100, None));
        assert!(chat_is_allowed(true, 1, None));
    }

    #[test]
    fn private_chats_are_always_allowed() {
        assert!(chat_is_allowed(true, 1, Some(-100)));
    }

    #[test]
    fn only_the_allowed_group_is_accepted() {
        assert!(chat_is_allowed(false, -100, Some(-100)));
        assert!(!chat_is_allowed(false, -200, Some(-100)));
    }
}
