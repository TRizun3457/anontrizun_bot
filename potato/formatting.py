from typing import Any

from .achievements import POTATO_ACHIEVEMENTS


def build_share_text(stats: dict[str, Any], is_vip: bool, decor: str = "") -> str:
    def shown(field: str) -> bool:
        return True if not is_vip else bool(stats.get(field, 1))

    lines: list[str] = []
    if shown("share_received"):
        lines.append(f"📥 Получено картошек: <b>{stats['received']}</b>")
    if shown("share_passed"):
        lines.append(f"✅ Отражено (передано вовремя): <b>{stats['passed']}</b>")
    if shown("share_exploded"):
        lines.append(f"💥 Взорвалось: <b>{stats['exploded']}</b>")
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
