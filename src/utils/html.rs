//! HTML escaping identical to Python's `html.escape(text)` (quote = true).

/// Escapes `&`, `<`, `>`, `"` and `'` in one pass.
pub fn escape_html(text: &str) -> String {
    let mut escaped = String::with_capacity(text.len());
    for character in text.chars() {
        match character {
            '&' => escaped.push_str("&amp;"),
            '<' => escaped.push_str("&lt;"),
            '>' => escaped.push_str("&gt;"),
            '"' => escaped.push_str("&quot;"),
            '\'' => escaped.push_str("&#x27;"),
            _ => escaped.push(character),
        }
    }
    escaped
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn escapes_python_special_characters() {
        assert_eq!(
            escape_html("a & b < c > d \" e ' f"),
            "a &amp; b &lt; c &gt; d &quot; e &#x27; f"
        );
    }

    #[test]
    fn leaves_regular_text_untouched() {
        assert_eq!(escape_html("Привет, мир! 42"), "Привет, мир! 42");
    }

    #[test]
    fn escapes_ampersand_first() {
        assert_eq!(escape_html("&lt;"), "&amp;lt;");
    }
}
