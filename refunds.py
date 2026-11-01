import logging
import secrets
from typing import Any

logger = logging.getLogger(__name__)

BALANCE_PREFIX = "bal:"
BALANCE_ITEMS = {
    "priority": "приоритет",
    "vip": "VIP-оформление",
    "air": "воздух",
    "apology": "заявка на разбан",
    "strong": "сильное гниение",
    "launch": "запуск гнилой картошки",
}


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


def balance_payload(item: str, price: int) -> str:
    return f"{BALANCE_PREFIX}{item}:{price}"


def parse_balance_payload(payload: str | None) -> tuple[str, int] | None:
    if payload is None or not payload.startswith(BALANCE_PREFIX):
        return None
    parts = payload[len(BALANCE_PREFIX) :].split(":")
    if len(parts) != 2 or parts[0] not in BALANCE_ITEMS:
        return None
    try:
        price = int(parts[1])
    except ValueError:
        return None
    return (parts[0], price) if price >= 0 else None


async def record_balance_purchase(db: Any, user_id: int, item: str, price: int) -> str:
    charge_id = f"bal_{secrets.token_hex(8)}"
    try:
        await db.create_payment(charge_id, user_id, balance_payload(item, price))
    except Exception:
        logger.exception("cannot record balance purchase %s for %s", item, user_id)
        return ""
    return charge_id


def describe_payload(payload: str | None) -> str:
    if payload is None:
        return "неизвестная покупка"
    balance = parse_balance_payload(payload)
    if balance is not None:
        return f"покупка с баланса: {BALANCE_ITEMS[balance[0]]} ({balance[1]} ⭐)"
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
    balance = parse_balance_payload(payload)
    if balance is not None:
        kind = {"vip": "vip", "air": "air", "priority": "priority"}.get(balance[0])
        if kind is None:
            return "Эффект покупки уже использован, забирать нечего."
        taken = await db.revoke_purchase(user_id, kind, 0)
        return (
            f"Забрано: {BALANCE_ITEMS[balance[0]]}."
            if taken
            else "Купленное уже отсутствует у пользователя."
        )
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
