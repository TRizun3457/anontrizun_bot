//! Fixed lists shared by the user-facing screens.

/// Kaomoji that VIP users may enable in their profile decorations.
pub const CAT_KAOMOJI_LIST: &[&str] = &[
    "( =ω= )",
    "(ฅ^•ﻌ•^ฅ)",
    "(=^･ω･^=)",
    "(✿^ω^)",
    "(≡^∇^)",
    "(=^-ω-^=)",
    "(๑ↀᴥ๑)",
    "(ฅ'ω'ฅ)",
];

/// Maps a callback suffix to the corresponding visibility column.
pub const VIS_FIELD_MAP: &[(&str, &str)] = &[
    ("sent", "show_sent"),
    ("received", "show_received"),
    ("priority", "show_priority"),
    ("air", "show_air"),
    ("achievements", "show_achievements"),
];

pub fn visibility_field(target: &str) -> Option<&'static str> {
    VIS_FIELD_MAP
        .iter()
        .find(|(suffix, _)| *suffix == target)
        .map(|(_, field)| *field)
}

/// Formats a kaomoji the way the original code did: `" {kaomoji} "`.
pub fn cat_string(kaomoji: &str) -> String {
    format!(" {kaomoji} ")
}
