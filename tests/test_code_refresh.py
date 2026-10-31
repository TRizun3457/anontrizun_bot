import asyncio

import pytest

from code_refresh import refresh_codes_once, run_code_refresh_loop


class FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def refresh_due_codes(self, now):
        self.calls.append(now)
        return self.rows


class FakeBot:
    def __init__(self, fail=()):
        self.sent = []
        self.fail = set(fail)

    async def send_message(self, chat_id, text, **kw):
        if chat_id in self.fail:
            raise RuntimeError("blocked")
        self.sent.append((chat_id, text))


def test_notifies_every_user_and_survives_blocked_ones():
    db = FakeDb([(1, "AAAA1111"), (2, "BBBB2222"), (3, "CCCC3333")])
    bot = FakeBot(fail={2})
    count = asyncio.run(refresh_codes_once(db, bot, now=123))
    assert count == 3 and db.calls == [123]
    assert [c for c, _ in bot.sent] == [1, 3]
    assert "AAAA1111" in bot.sent[0][1]


def test_nothing_due_sends_nothing():
    db = FakeDb([])
    bot = FakeBot()
    assert asyncio.run(refresh_codes_once(db, bot, now=1)) == 0
    assert bot.sent == []


def test_loop_survives_errors_and_cancels():
    class Broken(FakeDb):
        async def refresh_due_codes(self, now):
            self.calls.append(now)
            raise RuntimeError("db down")

    db = Broken([])

    async def go():
        task = asyncio.create_task(run_code_refresh_loop(db, FakeBot(), poll=0.01))
        await asyncio.sleep(0.06)
        assert len(db.calls) >= 2
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
