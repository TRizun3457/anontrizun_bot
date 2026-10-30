from typing import Any

from .achievements import POTATO_ACHIEVEMENTS
from .theme import banner, bar, fmt_duration, rank_for


def build_share_text(stats: dict[str, Any], is_vip: bool, decor: str = "") -> str:
    def shown(field: str) -> bool:
        return True if not is_vip else bool(stats.get(field, 1))

    lines: list[str] = []
    if shown("share_received"):
        lines.append(f"📥 Получено картошек: <b>{stats['received']}</b>")
    if shown("share_passed"):
        lines.append(f"✅ Отражено (передано вовремя): <b>{stats['passed']}</b>")
    if shown("share_exploded"):
        lines.append(f"☠️ Сгнило: <b>{stats['exploded']}</b>")
    if shown("share_streak"):
        lines.append(f"🔥 Лучшая серия передач: <b>{stats['best_pass_streak']}</b>")
    if shown("share_achievements"):
        lines.append(
            f"🏆 Достижений игры: <b>{len(stats['achievements'])}/{len(POTATO_ACHIEVEMENTS)}</b>"
        )
    body = "\n".join(lines)
    if is_vip:
        pet = f" {decor}" if decor else ""
        return (
            f"✨ 👑 <b>КАРТОШКА-ПРОФИЛЬ{pet}</b> 👑 ✨\n💎 <b>Статус:</b> VIP\n\n{body}"
        )
    return f"🥔 <b>Статистика «Гнилой картошки»:</b>\n{body}"


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
    lines = [
        banner("ГНИЛАЯ КАРТОШКА", is_vip, pet),
        f"🏅 Ранг: {emoji} <b>{title}</b>",
        f"📈 До следующего: {progress}",
        "",
        "🎮 Участие в игре: "
        + ("<b>вы в игре</b>" if stats["enabled"] else "<b>вы вышли из игры</b>"),
        f"📥 Получено картошек: <b>{stats['received']}</b>",
        f"✅ Отражено (передано вовремя): <b>{stats['passed']}</b>",
        f"☠️ Сгнило у вас: <b>{stats['exploded']}</b>",
        f"🔥 Лучшая серия передач: <b>{stats['best_pass_streak']}</b>",
        f"📣 Запусков картошки: <b>{stats['started']}</b>",
    ]
    if stats["fastest_pass_sec"] is not None:
        lines.append(
            f"⚡ Самая быстрая передача: <b>{stats['fastest_pass_sec']} с.</b>"
        )
    if lock_note:
        lines.append(f"\n🔒 {lock_note}")
    if strong_left > 0:
        lines.append(
            f"\n🌋 <b>Идёт СИЛЬНОЕ ГНИЕНИЕ</b> — ещё {fmt_duration(strong_left)}."
        )
    if not is_vip:
        lines.append(
            "\n💎 Настраивать, чем делиться, и золотое оформление игры — для VIP."
        )
    return "\n".join(lines)


def format_achievements(stats: dict, is_vip: bool = False) -> str:
    unlocked = set(stats["achievements"])
    total = len(POTATO_ACHIEVEMENTS)
    lines = [
        banner(f"ДОСТИЖЕНИЯ ИГРЫ ({len(unlocked)}/{total})", is_vip),
        f"{bar(len(unlocked), total)} {len(unlocked)}/{total}",
        "",
    ]
    for ach_id, (title, desc) in POTATO_ACHIEVEMENTS.items():
        mark = "✅" if ach_id in unlocked else "🔒"
        lines.append(f"{mark} {title} — {desc}")
    return "\n".join(lines)
