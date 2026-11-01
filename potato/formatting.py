from typing import Any

from .achievements import POTATO_ACHIEVEMENTS
from .theme import banner, bar, fmt_duration, rank_for, thin, tree


def build_share_text(stats: dict[str, Any], is_vip: bool, decor: str = "") -> str:
    def shown(field: str) -> bool:
        return True if not is_vip else bool(stats.get(field, 1))

    lines: list[str] = []
    if shown("share_received"):
        lines.append(f"📥 Получено картошек: <b>{stats['received']}</b>")
    if shown("share_passed"):
        emoji, title, _ = rank_for(stats["passed"])
        lines.append(f"{emoji} Ранг: <b>{title}</b>")
        lines.append(f"✅ Отражено (передано вовремя): <b>{stats['passed']}</b>")
    if shown("share_exploded"):
        lines.append(f"☠️ Сгнило: <b>{stats['exploded']}</b>")
    if shown("share_streak"):
        lines.append(f"🔥 Лучшая серия передач: <b>{stats['best_pass_streak']}</b>")
    if shown("share_achievements"):
        lines.append(
            f"🏆 Достижений игры: <b>{len(stats['achievements'])}/{len(POTATO_ACHIEVEMENTS)}</b>"
        )
    if not lines:
        lines.append("🥔 Пока без статистики")
    if is_vip:
        return (
            f"{banner('КАРТОШКА-ПРОФИЛЬ', True, decor)}\n"
            f"💎 Статус: <b>VIP</b>\n{thin(True)}\n{tree(lines)}"
        )
    return f"{banner('ГНИЛАЯ КАРТОШКА', False)}\n{tree(lines)}"


def format_stats(
    stats: dict,
    is_vip: bool,
    strong_left: int = 0,
    pet: str = "",
    lock_note: str = "",
) -> str:
    emoji, title, next_at = rank_for(stats["passed"])
    if next_at is None:
        progress = f"{bar(1, 1)} максимальный ранг!"
    else:
        progress = f"{bar(stats['passed'], next_at)} {stats['passed']}/{next_at}"
    rows = [
        "🎮 Участие: "
        + ("<b>вы в игре</b>" if stats["enabled"] else "<b>вы вышли из игры</b>"),
        f"📥 Получено картошек: <b>{stats['received']}</b>",
        f"✅ Отражено (передано вовремя): <b>{stats['passed']}</b>",
        f"☠️ Сгнило у вас: <b>{stats['exploded']}</b>",
        f"🔥 Лучшая серия передач: <b>{stats['best_pass_streak']}</b>",
        f"📣 Запусков картошки: <b>{stats['started']}</b>",
    ]
    if stats["fastest_pass_sec"] is not None:
        rows.append(f"⚡ Самая быстрая передача: <b>{stats['fastest_pass_sec']} с.</b>")
    lines = [
        banner("ГНИЛАЯ КАРТОШКА", is_vip, pet),
        "",
        f"{emoji} Ранг: <b>{title}</b>",
        f"╰ {progress}",
        thin(is_vip),
        tree(rows),
    ]
    notes: list[str] = []
    if lock_note:
        notes.append(f"🔒 {lock_note}")
    if strong_left > 0:
        notes.append(
            f"🌋 <b>Идёт СИЛЬНОЕ ГНИЕНИЕ</b> — ещё {fmt_duration(strong_left)}"
        )
    if not is_vip:
        notes.append("💎 Выбор того, чем делиться, и золотое оформление — для VIP.")
    if notes:
        lines += [thin(is_vip), *notes]
    return "\n".join(lines)


def format_achievements(stats: dict, is_vip: bool = False) -> str:
    unlocked = set(stats["achievements"])
    total = len(POTATO_ACHIEVEMENTS)
    rows = []
    for ach_id, (title, desc) in POTATO_ACHIEVEMENTS.items():
        mark = "✅" if ach_id in unlocked else "🔒"
        rows.append(f"{mark} {title}\n│  <i>{desc}</i>")
    lines = [
        banner("ДОСТИЖЕНИЯ ИГРЫ", is_vip),
        "",
        f"{bar(len(unlocked), total)} <b>{len(unlocked)}/{total}</b>",
        thin(is_vip),
        "\n".join(rows),
    ]
    return "\n".join(lines)
