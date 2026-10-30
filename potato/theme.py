import random

RANKS = (
    (0, "🌱", "Росток"),
    (1, "🥔", "Клубень"),
    (5, "🍟", "Картошка фри"),
    (15, "🥘", "Мастер пюре"),
    (40, "🔥", "Печёный ветеран"),
    (100, "🏰", "Картофельный бастион"),
    (250, "👑", "Король картошки"),
)

FLAVOR = (
    "Говорят, ядовитый картофель — не лучший завтрак. Передай его скорее! 🤢",
    "Эта картошка уже позеленела и подозрительно пахнет…",
    "Съесть её — значит отравиться. Лучше подкинуть кому-нибудь другому! 😈",
    "Картошка шепчет: «Я ещё свежая… почти».",
    "Позеленела, как крипер на рассвете. Не держи её долго!",
    "Кто-то в чате очень надеется, что картошка достанется не ему. Не повезло. 🥔",
)

VIP_FLAVOR = (
    "Даже золотая картошка гниёт, если её держать слишком долго. 👑",
    "VIP-гниль: сгнить с достоинством или передать с шиком!",
    "Королевская гнилушка требует королевской скорости.",
)


def fmt_duration(seconds: int) -> str:
    minutes = max(1, round(seconds / 60))
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} ч. {mins} мин."
    if hours:
        return f"{hours} ч."
    return f"{mins} мин."


def rank_for(passed: int) -> tuple[str, str, int | None]:
    current = RANKS[0]
    next_threshold: int | None = None
    for index, rank in enumerate(RANKS):
        if passed >= rank[0]:
            current = rank
            next_threshold = RANKS[index + 1][0] if index + 1 < len(RANKS) else None
    return current[1], current[2], next_threshold


def bar(current: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "▰" * width
    filled = max(0, min(width, round(width * current / total)))
    return "▰" * filled + "▱" * (width - filled)


def line(is_vip: bool) -> str:
    return "✦━━━━━━━━━━━━━━━━✦" if is_vip else "◈────────────────◈"


def thin(is_vip: bool) -> str:
    return "· · · · · · · · · · · ·" if is_vip else "╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌"


def tree(rows: list[str]) -> str:
    if len(rows) == 1:
        return f"╺ {rows[0]}"
    out = []
    for index, row in enumerate(rows):
        if index == 0:
            mark = "┌"
        elif index == len(rows) - 1:
            mark = "└"
        else:
            mark = "├"
        out.append(f"{mark} {row}")
    return "\n".join(out)


def banner(title: str, is_vip: bool, pet: str = "") -> str:
    tail = f" {pet}" if pet else ""
    mark = "❖" if is_vip else "◆"
    return f"{line(is_vip)}\n{mark} <b>{title}</b> {mark}{tail}\n{line(is_vip)}"


def holder_text(
    kind: str,
    duration_text: str,
    deadline: str | None,
    is_vip: bool,
    rng: random.Random | None = None,
) -> str:
    r = rng or random
    flavor = r.choice(VIP_FLAVOR if is_vip else FLAVOR)
    if kind == "rot":
        title = (
            "ДЕНЬ ГНИЕНИЯ: золотая гнилушка у вас!"
            if is_vip
            else "ДЕНЬ ГНИЕНИЯ: вы — Гнилая картошка!"
        )
        tail = "Сегодня картошек несколько, и кто-то обязательно сгниёт! ☠️"
    else:
        title = "Золотая гнилушка — вам, VIP!" if is_vip else "Вы — Гнилая картошка!"
        tail = "Не успеете — она сгниёт у вас в руках, и вы отравитесь! ☠️"
    deadline_line = f"\n⏰ Сгниёт в <b>{deadline}</b>" if deadline else ""
    return (
        f"{banner(title, is_vip)}\n\n{flavor}\n\n"
        f"⏳ Время на передачу: <b>{duration_text}</b>{deadline_line}\n\n"
        f"➡️ Нажмите кнопку ниже — картошка анонимно уйдёт другому игроку. {tail}"
    )


def poison_text(is_vip: bool) -> str:
    head = "☠️ <b>СГНИЛО!</b>"
    body = "Картошка сгнила у вас в руках — вы не успели её передать и отравились. 🤢"
    if is_vip:
        return f"{head} 👑\n{body}\nДаже VIP-гниль не щадит!"
    return f"{head}\n{body}"
