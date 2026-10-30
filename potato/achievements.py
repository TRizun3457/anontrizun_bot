POTATO_ACHIEVEMENTS: dict[str, tuple[str, str]] = {
    "potato_first": ("🥔 Первая картошка", "Получить горячую картошку в первый раз"),
    "potato_pass_1": ("🤲 Вовремя!", "Успешно передать картошку 1 раз"),
    "potato_pass_10": ("🔥 Мастер передач", "Успешно передать картошку 10 раз"),
    "potato_streak_3": (
        "⚡ Без осечек",
        "Передать картошку 3 раза подряд, не взорвавшись",
    ),
    "potato_boom_1": ("💥 Бабах!", "Взорваться с картошкой в первый раз"),
    "potato_boom_5": ("🧨 Любитель фейерверков", "Взорваться 5 раз"),
    "potato_fast": ("🏎 Скорострел", "Передать картошку быстрее чем за 60 секунд"),
}

RULES = (
    ("potato_first", lambda s: s["received"] >= 1),
    ("potato_pass_1", lambda s: s["passed"] >= 1),
    ("potato_pass_10", lambda s: s["passed"] >= 10),
    ("potato_streak_3", lambda s: s["best_pass_streak"] >= 3),
    ("potato_boom_1", lambda s: s["exploded"] >= 1),
    ("potato_boom_5", lambda s: s["exploded"] >= 5),
    (
        "potato_fast",
        lambda s: s["fastest_pass_sec"] is not None and s["fastest_pass_sec"] < 60,
    ),
)
