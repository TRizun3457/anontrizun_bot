def mention_matches(text: str | None, bot_username: str | None) -> bool:
    first = (text or "").split(maxsplit=1)[0] if (text or "").strip() else ""
    _, _, target = first.partition("@")
    if not target:
        return True
    return bot_username is not None and target.casefold() == bot_username.casefold()
