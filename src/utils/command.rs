//! Bot command parsing matching aiogram's `Command`/`CommandStart` filters.

use teloxide::types::Message;

use super::split::split_maxsplit1;

/// Returns the message text, falling back to the caption like aiogram does.
pub fn message_text(message: &Message) -> Option<&str> {
    message
        .text()
        .filter(|text| !text.is_empty())
        .or_else(|| message.caption().filter(|caption| !caption.is_empty()))
}

/// Extracts the arguments of `expected` from `text`.
///
/// Returns `Some(args)` (possibly empty) when the text is a command named
/// `expected` that either has no mention or mentions `bot_username`
/// (case-insensitively). Mirrors aiogram's default `ignore_mention = False`,
/// `ignore_case = False` behaviour.
pub fn extract_command<'a>(text: &'a str, expected: &str, bot_username: &str) -> Option<&'a str> {
    let (full_command, args) = split_maxsplit1(text);
    let full_command = full_command?;

    let mut characters = full_command.chars();
    let prefix = characters.next()?;
    if prefix != '/' {
        return None;
    }

    let rest = characters.as_str();
    let (command, mention) = match rest.split_once('@') {
        Some((command, mention)) => (command, mention),
        None => (rest, ""),
    };

    if command != expected {
        return None;
    }
    if !mention.is_empty() && mention.to_lowercase() != bot_username.to_lowercase() {
        return None;
    }

    Some(args.unwrap_or(""))
}

#[cfg(test)]
mod tests {
    use super::*;

    const BOT: &str = "MyBot";

    #[test]
    fn accepts_bare_commands() {
        assert_eq!(extract_command("/start", "start", BOT), Some(""));
        assert_eq!(
            extract_command("/start ref_42", "start", BOT),
            Some("ref_42")
        );
    }

    #[test]
    fn accepts_matching_mentions_case_insensitively() {
        assert_eq!(
            extract_command("/start@mybot ref_1", "start", BOT),
            Some("ref_1")
        );
        assert_eq!(extract_command("/start@MYBOT", "start", BOT), Some(""));
    }

    #[test]
    fn rejects_other_mentions_and_commands() {
        assert_eq!(extract_command("/start@other_bot", "start", BOT), None);
        assert_eq!(extract_command("/stop", "start", BOT), None);
        assert_eq!(extract_command("start", "start", BOT), None);
        assert_eq!(extract_command("/Start", "start", BOT), None);
    }

    #[test]
    fn empty_mention_is_accepted_like_aiogram() {
        assert_eq!(extract_command("/start@", "start", BOT), Some(""));
    }

    #[test]
    fn collapses_argument_whitespace() {
        assert_eq!(
            extract_command("/unban   ABC  DEF", "unban", BOT),
            Some("ABC  DEF")
        );
    }
}
