//! Small helpers replicating Python's `str.split(maxsplit=1)`.

/// Splits `text` into the first whitespace-separated token and the rest.
///
/// Mirrors Python semantics: leading/trailing whitespace is ignored, runs of
/// whitespace are collapsed, and whitespace-only input yields `(None, None)`.
pub fn split_maxsplit1(text: &str) -> (Option<&str>, Option<&str>) {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return (None, None);
    }

    match trimmed.find(char::is_whitespace) {
        Some(index) => {
            let head = &trimmed[..index];
            let rest = trimmed[index..].trim_start();
            if rest.is_empty() {
                (Some(head), None)
            } else {
                (Some(head), Some(rest))
            }
        }
        None => (Some(trimmed), None),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_python_for_typical_inputs() {
        assert_eq!(split_maxsplit1("/start"), (Some("/start"), None));
        assert_eq!(
            split_maxsplit1("/start ref_1"),
            (Some("/start"), Some("ref_1"))
        );
        assert_eq!(
            split_maxsplit1("/ban  spaced   args"),
            (Some("/ban"), Some("spaced   args"))
        );
        assert_eq!(
            split_maxsplit1("  /start  x  "),
            (Some("/start"), Some("x"))
        );
        assert_eq!(split_maxsplit1(""), (None, None));
        assert_eq!(split_maxsplit1("   "), (None, None));
    }

    #[test]
    fn splits_tabs_and_newlines() {
        assert_eq!(split_maxsplit1("/x\targ"), (Some("/x"), Some("arg")));
        assert_eq!(split_maxsplit1("/x\narg"), (Some("/x"), Some("arg")));
    }
}
