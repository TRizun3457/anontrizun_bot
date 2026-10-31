import asyncio

from refunds import PendingRefunds, describe_payload, revoke_benefit


class FakeDb:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def revoke_purchase(self, user_id, kind, amount):
        self.calls.append((user_id, kind, amount))
        return self.result


def run(c):
    return asyncio.run(c)


def test_pending_tokens_are_single_use_and_bounded():
    pending = PendingRefunds(limit=3)
    tokens = [pending.add("charge", f"stx_{i}") for i in range(5)]
    assert pending.pop(tokens[0]) is None
    assert pending.pop(tokens[4]) == ("charge", "stx_4")
    assert pending.pop(tokens[4]) is None
    assert all(len(t) == 8 for t in tokens)


def test_describe_payload():
    assert "100" in describe_payload("deposit_100")
    assert describe_payload("buy_vip_sub") == "VIP-оформление"
    assert describe_payload("buy_air_pack") == "воздух"
    assert describe_payload("zzz") == "неизвестная покупка"
    assert describe_payload(None) == "неизвестная покупка"


def test_revoke_each_kind():
    db = FakeDb(1)
    assert "VIP снят" in run(revoke_benefit(db, 7, "buy_vip_sub"))
    assert "воздух" in run(revoke_benefit(db, 7, "buy_air_pack")).lower()
    assert "списано 1" in run(revoke_benefit(db, 7, "deposit_50"))
    assert db.calls == [(7, "vip", 0), (7, "air", 0), (7, "balance", 50)]


def test_revoke_nothing_to_take():
    db = FakeDb(0)
    assert "уже не было" in run(revoke_benefit(db, 7, "buy_vip_sub"))
    assert "нет" in run(revoke_benefit(db, 7, "buy_air_pack"))


def test_revoke_unknown_and_bad_payloads_do_not_touch_db():
    db = FakeDb(1)
    assert "нечего" in run(revoke_benefit(db, 7, "buy_apology_req"))
    assert "нечего" in run(revoke_benefit(db, 7, None))
    assert "Не удалось" in run(revoke_benefit(db, 7, "deposit_abc"))
    assert db.calls == []
