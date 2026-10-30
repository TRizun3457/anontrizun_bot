import asyncio
import random
from types import SimpleNamespace

import pytest

from potato.service import PotatoService, fmt_duration
from potato.store import PotatoError, PotatoStore
from tests.test_potato_store import INIT_SQL, Clock


class FakeBot:
    def __init__(
        self, blocked: frozenset[int] = frozenset(), left: frozenset[int] = frozenset()
    ):
        self.sent: list[tuple[int, str]] = []
        self.blocked = set(blocked)
        self.left = set(left)
        self.fail_messages: set[int] = set()

    async def send_message(self, chat_id, text, **kw):
        if chat_id in self.blocked or chat_id in self.fail_messages:
            raise RuntimeError("blocked or simulated delivery failure")
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
    assert store is not None, "Store failed to initialize"

    asyncio.run(store.init())

    assert store._keep is not None, "Database connection is not established"

    store._keep.executescript(INIT_SQL)
    for uid, vip in users.items():
        store._keep.execute(
            "INSERT INTO users (user_id, is_vip) VALUES (?, ?)", (uid, vip)
        )
    for b in banned:
        store._keep.execute("INSERT INTO banned (user_id) VALUES (?)", (b,))

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
    bot = FakeBot(blocked=frozenset({1}), left=frozenset({2}))

    svc, bot, _ = make({1: 0, 2: 0, 3: 0}, bot)
    for chat in (-10, -11, -12):
        g = run(svc.start_game(chat, 99, 600))
        assert g.holder_id == 3


def test_admin_private_game_uses_global_pool_without_membership_check():
    bot = FakeBot(left=frozenset({1, 2, 3}))

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


def test_start_retries_when_dm_fails_after_reachability_check():
    bot = FakeBot()
    bot.fail_messages = {1, 2}
    svc, bot, _ = make({1: 0, 2: 0, 3: 0}, bot)
    game = run(svc.start_game(-50, 99, 600))
    assert game.holder_id == 3
    assert any("Вы — Гнилая картошка" in text for text in bot.to(3))
    assert run(svc.store.get_stats(1))["received"] == 0
    assert run(svc.store.get_stats(2))["received"] == 0


def test_start_cancels_game_if_every_dm_fails():
    bot = FakeBot()
    bot.fail_messages = {1, 2}
    svc, bot, _ = make({1: 0, 2: 0}, bot)
    with pytest.raises(PotatoError, match="не удалось найти доступного игрока"):
        run(svc.start_game(-51, 99, 600))
    assert run(svc.store.active_game(-51)) is None
    assert run(svc.store.get_stats(1))["received"] == 0
    assert run(svc.store.get_stats(2))["received"] == 0


def test_pass_retries_with_another_holder_when_dm_fails():
    bot = FakeBot()
    svc, bot, _ = make({1: 0, 2: 0, 3: 0}, bot)
    game = run(svc.start_game(-52, 99, 600))
    old_holder = game.holder_id
    target = next(uid for uid in (1, 2, 3) if uid != old_holder)

    async def choose_target(_game, _exclude):
        return target

    svc._pick_reachable = choose_target
    bot.fail_messages.add(target)

    result = run(svc.pass_potato(game.id, old_holder))
    assert result.new_holder in {1, 2, 3} - {old_holder, target}
    assert run(svc.store.get_stats(target))["received"] == 0
    assert any("Вы — Гнилая картошка" in text for text in bot.to(result.new_holder))


def test_store_rechecks_recipient_eligibility_inside_transaction():
    svc, _, _ = make({1: 0, 2: 1, 3: 0})
    game = run(svc.store.create_game(-53, 99, 600))
    assigned = run(svc.store.assign_holder(game.id, 1)).game
    run(svc.store.set_enabled(2, False))
    with pytest.raises(PotatoError, match="больше не может участвовать"):
        run(svc.store.pass_potato(assigned.id, 1, 2))
    assert run(svc.store.get_game(game.id)).holder_id == 1


def test_pass_reselects_recipient_if_opt_out_races_with_transfer():
    svc, bot, _ = make({1: 0, 2: 1, 3: 0})
    game = run(svc.store.create_game(-54, 99, 600))
    game = run(svc.store.assign_holder(game.id, 1)).game
    calls = 0

    async def choose_after_reachability_check(_game, exclude):
        nonlocal calls
        calls += 1
        if calls == 1:
            # Simulate the VIP opting out after the candidate check.
            await svc.store.set_enabled(2, False)
            return 2
        return 3 if 3 not in exclude else None

    svc._pick_reachable = choose_after_reachability_check
    result = run(svc.pass_potato(game.id, 1))
    assert result.new_holder == 3
    assert calls == 2
    assert run(svc.store.get_stats(2))["received"] == 0
    assert any("Вы — Гнилая картошка" in text for text in bot.to(3))


def test_pass_defuses_game_if_all_replacement_dms_fail():
    bot = FakeBot()
    svc, bot, _ = make({1: 0, 2: 0}, bot)
    game = run(svc.start_game(-55, 99, 600))
    holder = game.holder_id
    target = 2 if holder == 1 else 1

    async def choose_target(_game, _exclude):
        return target

    svc._pick_reachable = choose_target
    bot.fail_messages.add(target)
    result = run(svc.pass_potato(game.id, holder))
    assert result.new_holder is None
    assert result.game.status == "defused"
    assert run(svc.store.active_game(-55)) is None
    assert run(svc.store.get_stats(target))["received"] == 0
