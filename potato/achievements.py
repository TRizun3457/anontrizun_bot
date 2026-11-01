POTATO_ACHIEVEMENTS: dict[str, tuple[str, str]] = {
    "potato_first": ("🥔 Первая картошка", "Получить горячую картошку в первый раз"),
    "potato_pass_1": ("🤲 Вовремя!", "Успешно передать картошку 1 раз"),
    "potato_pass_10": ("🔥 Мастер передач", "Успешно передать картошку 10 раз"),
    "potato_streak_3": (
        "⚡ Без осечек",
        "Передать картошку 3 раза подряд, не сгнив",
    ),
    "potato_boom_1": ("☠️ Отравился!", "Сгнить с картошкой в первый раз"),
    "potato_boom_5": ("🧪 Любитель ядов", "Сгнить с картошкой 5 раз"),
    "potato_fast": (
        "🥔 Туда мистера картошку",
        "Передать картошку быстрее чем за 60 секунд",
    ),
    "potato_pass_50": ("🛡 Щит", "Отразить (передать вовремя) 50 картошек"),
    "potato_pass_100": ("🏰 Бастион", "Отразить 100 картошек"),
    "potato_pass_250": ("👑 Король картошки", "Отразить 250 картошек"),
    "potato_start_10": ("📣 Заводила", "Запустить картошку в чате 10 раз"),
    "potato_start_30": ("🎪 Главный затейник", "Запустить картошку в чате 30 раз"),
    "potato_streak_10": (
        "🧊 Хладнокровие",
        "Передать картошку 10 раз подряд, ни разу не сгнив",
    ),
    "potato_received_50": ("🎯 Магнит для картошки", "Получить картошку 50 раз"),
    "potato_boom_10": ("🧟 Хроническая гниль", "Сгнить с картошкой 10 раз"),
    "potato_donor": ("🌋 Друг гниения", "Купить что-нибудь в магазине картошки"),
    "potato_rot_boom": (
        "🤢 Жертва дня гниения",
        "Сгнить с картошкой в день гниения",
    ),
}

RULES = (
    ("potato_first", lambda s: s["received"] >= 1),
    ("potato_pass_1", lambda s: s["passed"] >= 1),
    ("potato_pass_10", lambda s: s["passed"] >= 10),
    ("potato_streak_3", lambda s: s["best_pass_streak"] >= 3),
    ("potato_boom_1", lambda s: s["exploded"] >= 1),
    ("potato_boom_5", lambda s: s["exploded"] >= 5),
    ("potato_pass_50", lambda s: s["passed"] >= 50),
    ("potato_pass_100", lambda s: s["passed"] >= 100),
    ("potato_pass_250", lambda s: s["passed"] >= 250),
    ("potato_start_10", lambda s: s["started"] >= 10),
    ("potato_start_30", lambda s: s["started"] >= 30),
    ("potato_streak_10", lambda s: s["best_pass_streak"] >= 10),
    ("potato_received_50", lambda s: s["received"] >= 50),
    ("potato_boom_10", lambda s: s["exploded"] >= 10),
    ("potato_donor", lambda s: s["bought"] >= 1),
    ("potato_rot_boom", lambda s: s["rot_exploded"] >= 1),
    (
        "potato_fast",
        lambda s: s["fastest_pass_sec"] is not None and s["fastest_pass_sec"] < 60,
    ),
)
