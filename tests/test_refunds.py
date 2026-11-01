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


def test_balance_payload_roundtrip_and_validation():
    from refunds import balance_payload, parse_balance_payload

    assert parse_balance_payload(balance_payload("vip", 100)) == ("vip", 100)
    assert parse_balance_payload("bal:unknown:5") is None
    assert parse_balance_payload("bal:vip:abc") is None
    assert parse_balance_payload("bal:vip:-5") is None
    assert parse_balance_payload("bal:vip") is None
    assert parse_balance_payload("buy_vip_sub") is None
    assert parse_balance_payload(None) is None


def test_record_balance_purchase_creates_payment_and_survives_db_errors():
    from refunds import record_balance_purchase

    class Db:
        def __init__(self, fail=False):
            self.fail = fail
            self.rows = []

        async def create_payment(self, charge_id, user_id, payload):
            if self.fail:
                raise RuntimeError("db")
            self.rows.append((charge_id, user_id, payload))
            return True

    db = Db()
    charge = run(record_balance_purchase(db, 5, "air", 10))
    assert charge.startswith("bal_") and db.rows == [(charge, 5, "bal:air:10")]
    assert run(record_balance_purchase(Db(fail=True), 5, "air", 10)) == ""


def test_describe_and_revoke_balance_purchases():
    assert "покупка с баланса: VIP-оформление (100 ⭐)" == describe_payload(
        "bal:vip:100"
    )
    db = FakeDb(1)
    assert "Забрано" in run(revoke_benefit(db, 3, "bal:priority:1"))
    assert "Забрано" in run(revoke_benefit(db, 3, "bal:vip:100"))
    assert "Забрано" in run(revoke_benefit(db, 3, "bal:air:10"))
    assert db.calls == [(3, "priority", 0), (3, "vip", 0), (3, "air", 0)]
    assert "использован" in run(revoke_benefit(db, 3, "bal:strong:142"))
    assert "использован" in run(revoke_benefit(db, 3, "bal:apology:50"))
    assert len(db.calls) == 3
    assert "отсутствует" in run(revoke_benefit(FakeDb(0), 3, "bal:vip:100"))
