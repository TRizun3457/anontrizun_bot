import secrets
from typing import Any


class PendingRefunds:
    def __init__(self, limit: int = 200) -> None:
        self._limit = limit
        self._items: dict[str, tuple[str, str]] = {}

    def add(self, kind: str, value: str) -> str:
        token = secrets.token_hex(4)
        while token in self._items:
            token = secrets.token_hex(4)
        self._items[token] = (kind, value)
        while len(self._items) > self._limit:
            self._items.pop(next(iter(self._items)))
        return token

    def pop(self, token: str) -> tuple[str, str] | None:
        return self._items.pop(token, None)


def describe_payload(payload: str | None) -> str:
    if payload is None:
        return "неизвестная покупка"
    if payload.startswith("deposit_"):
        amount = payload.split("_", 1)[1]
        return f"пополнение баланса на {amount} ⭐"
    return {
        "buy_vip_sub": "VIP-оформление",
        "buy_air_pack": "воздух",
        "buy_apology_req": "заявка на разбан",
    }.get(payload, "неизвестная покупка")


async def revoke_benefit(db: Any, user_id: int, payload: str | None) -> str:
    if payload is None:
        return "Забирать нечего: тип покупки неизвестен."
    if payload.startswith("deposit_"):
        try:
            amount = int(payload.split("_", 1)[1])
        except ValueError:
            return "Не удалось определить сумму пополнения."
        taken = await db.revoke_purchase(user_id, "balance", amount)
        return f"С баланса списано {taken} ⭐ из {amount} ⭐."
    if payload == "buy_vip_sub":
        taken = await db.revoke_purchase(user_id, "vip", 0)
        return "VIP снят." if taken else "VIP у пользователя уже не было."
    if payload == "buy_air_pack":
        taken = await db.revoke_purchase(user_id, "air", 0)
        return "Купленный воздух списан." if taken else "Воздуха у пользователя нет."
    return "Для этой покупки забирать нечего."
