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


def test_refreshes_silently_and_counts():
    db = FakeDb([(1, "AAAA1111"), (2, "BBBB2222")])
    assert asyncio.run(refresh_codes_once(db, now=123)) == 2
    assert db.calls == [123]


def test_nothing_due_returns_zero():
    assert asyncio.run(refresh_codes_once(FakeDb([]), now=1)) == 0


def test_loop_survives_errors_and_cancels():
    class Broken(FakeDb):
        async def refresh_due_codes(self, now):
            self.calls.append(now)
            raise RuntimeError("db down")

    db = Broken([])

    async def go():
        task = asyncio.create_task(run_code_refresh_loop(db, poll=0.01))
        await asyncio.sleep(0.06)
        assert len(db.calls) >= 2
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
