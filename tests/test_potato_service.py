import asyncio
import random
from types import SimpleNamespace

import pytest

from potato.service import PotatoService, fmt_duration
from potato.store import PotatoError, PotatoStore
from tests.test_potato_store import INIT_SQL, Clock


class FakeBot:
    def __init__(self, blocked: set[int] = frozenset(), left: set[int] = frozenset()):
        self.sent: list[tuple[int, str]] = []
        self.blocked = set(blocked)
        self.left = set(left)

    async def send_message(self, chat_id, text, **kw):
        if chat_id in self.blocked:
            raise RuntimeError("blocked")
        self.sent.append((chat_id, text))

    async def send_chat_action(self, chat_id, action, **kw):
        if chat_id in self.blocked:
            raise RuntimeError("blocked")

    async def get_chat_member(self, chat_id, user_id, **kw):
        return SimpleNamespace(status="left" if user_id in self.left else "member")

    def to(self, chat_id):
        return [t for c, t in self.sent if c == chat_id]


def make(users, bot=None, banned=()):
    clock = Clock()
    store = PotatoStore(":memory:", clock=clock, rng=random.Random(7))
    store._keep.executescript(INIT_SQL)
    for uid, vip in users.items():
        store._keep.execute(
            "INSERT INTO users (user_id, is_vip) VALUES (?, ?)", (uid, vip)
        )
    for b in banned:
        store._keep.execute("INSERT INTO banned (user_id) VALUES (?)", (b,))
    asyncio.run(store.init())
    bot = bot or FakeBot()
    return (
        PotatoService(store, bot, admin_id=99, pass_markup=lambda gid: f"kb{gid}"),
        bot,
        clock,
    )


def run(c):
    return asyncio.run(c)


def test_fmt_duration():
    assert fmt_duration(600) == "10 мин."
    assert fmt_duration(3600) == "1 ч."
    assert fmt_duration(5400) == "1 ч. 30 мин."


def test_start_notifies_one_holder_and_announces():
    svc, bot, _ = make({1: 0, 2: 0, 3: 0})
    game = run(svc.start_game(-5, 99, 900))
    assert game.holder_id in (1, 2, 3)
    assert any("Вы — Гнилая картошка" in t for t in bot.to(game.holder_id))
    assert any("запущена" in t for t in bot.to(-5))
    assert str(game.holder_id) not in " ".join(bot.to(-5))


def test_start_skips_blocked_and_nonmembers():
    bot = FakeBot(blocked={1}, left={2})
    svc, bot, _ = make({1: 0, 2: 0, 3: 0}, bot)
    for chat in (-10, -11, -12):
        g = run(svc.start_game(chat, 99, 600))
        assert g.holder_id == 3


def test_admin_private_game_uses_global_pool_without_membership_check():
    bot = FakeBot(left={1, 2, 3})
    svc, bot, _ = make({1: 0, 2: 0, 3: 0}, bot)
    g = run(svc.start_game(99, 99, 600))
    assert g.holder_id in (1, 2, 3)


def test_start_without_players_cleans_up():
    svc, _, _ = make({99: 0})
    with pytest.raises(PotatoError):
        run(svc.start_game(-1, 99, 600))
    assert run(svc.store.active_game(-1)) is None
    svc2, _, _ = make({1: 0})
    run(svc2.start_game(-1, 99, 600))


def test_pass_moves_potato_and_notifies_new_holder_only():
    svc, bot, _ = make({1: 0, 2: 0, 3: 0})
    g = run(svc.start_game(-1, 99, 600))
    first = g.holder_id
    res = run(svc.pass_potato(g.id, first))
    assert res.new_holder not in (None, first)
    assert any("Вы — Гнилая картошка" in t for t in bot.to(res.new_holder))
    with pytest.raises(PotatoError):
        run(svc.pass_potato(g.id, first))


def test_pass_with_nobody_left_defuses():
    svc, _bot, _ = make({1: 0, 2: 0})
    g = run(svc.start_game(-1, 99, 600))
    holder = g.holder_id
    other = 2 if holder == 1 else 1
    svc.bot.blocked.add(other)
    res = run(svc.pass_potato(g.id, holder))
    assert res.new_holder is None
    assert run(svc.store.active_game(-1)) is None


def test_expiry_explodes_and_reports():
    svc, bot, clock = make({1: 0, 2: 0})
    g = run(svc.start_game(-1, 99, 600))
    holder = g.holder_id
    assert run(svc.resolve_expired()) == []
    clock.t += 601
    out = run(svc.resolve_expired())
    assert [r.victim for r in out] == [holder]
    assert any("БАБАХ" in t for t in bot.to(holder))
    assert any("взорвалась" in t for t in bot.to(-1))
    assert run(svc.resolve_expired()) == []
    stats = run(svc.store.get_stats(holder))
    assert stats["exploded"] == 1


def test_expiry_survives_undeliverable_victim():
    svc, bot, clock = make({1: 0})
    g = run(svc.start_game(-1, 99, 600))
    bot.blocked.add(g.holder_id)
    clock.t += 700
    assert len(run(svc.resolve_expired())) == 1


def test_expiry_loop_cancellable():
    svc, _, _ = make({1: 0})

    async def go():
        t = asyncio.create_task(svc.run_expiry_loop(poll=0.01))
        await asyncio.sleep(0.05)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    run(go())
