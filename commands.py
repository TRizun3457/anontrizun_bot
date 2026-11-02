from collections.abc import Iterable


def mention_matches(text: str | None, bot_usernames: Iterable[str | None]) -> bool:
    stripped = (text or "").strip()
    first = stripped.split(maxsplit=1)[0] if stripped else ""
    _, _, target = first.partition("@")
    if not target:
        return True
    wanted = target.casefold()
    return any(name is not None and name.casefold() == wanted for name in bot_usernames)


def parse_usernames(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    parts = (part.strip().lstrip("@") for part in raw.replace(";", ",").split(","))
    return frozenset(part for part in parts if part)
