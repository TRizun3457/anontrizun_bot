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


def make(users, bot=None, banned=(), **kw):
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
        PotatoService(
            store, bot, admin_id=99, pass_markup=lambda gid: f"kb{gid}", **kw
        ),
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


def test_group_cooldown_blocks_second_start_but_not_after_4h():
    svc, _, clock = make({1: 0, 2: 0})
    g = run(svc.start_game(-1, 5, 600, cooldown_sec=4 * 3600, mark_cooldown=True))
    run(svc.store.cancel_game(g.id))
    with pytest.raises(PotatoError) as err:
        run(svc.start_game(-1, 5, 600, cooldown_sec=4 * 3600, mark_cooldown=True))
    assert "через" in str(err.value)
    clock.t += 4 * 3600
    run(svc.start_game(-1, 5, 600, cooldown_sec=4 * 3600, mark_cooldown=True))


def test_failed_start_does_not_consume_cooldown():
    svc, _, _ = make({99: 0})
    with pytest.raises(PotatoError):
        run(svc.start_game(-1, 5, 600, cooldown_sec=4 * 3600, mark_cooldown=True))
    assert run(svc.store.cooldown_remaining(-1, 4 * 3600)) == 0


def test_admin_start_ignores_cooldown():
    svc, _, _ = make({1: 0})
    run(svc.store.mark_started(-1))
    run(svc.start_game(-1, 99, 600))


def test_left_players_get_no_notifications():
    svc, bot, _ = make({1: 0, 2: 0})
    run(svc.store.set_enabled(1, False))
    for chat in (-1, -2, -3):
        g = run(svc.start_game(chat, 99, 600))
        assert g.holder_id == 2
    assert bot.to(1) == []


def test_rot_day_launches_three_parallel_potatoes():
    svc, bot, _ = make({1: 0, 2: 0, 3: 0, 4: 0})
    games = run(svc.start_rot_day(-1, 99))
    assert len(games) == 3 and all(g.kind == "rot" for g in games)
    assert len({g.id for g in games}) == 3
    assert any("ДЕНЬ ГНИЕНИЯ" in t for t in bot.to(-1))
    run(svc.start_game(-1, 99, 600))


def test_rot_potato_cannot_be_defused_and_keeps_timer():
    svc, _bot, _clock = make({1: 0, 2: 0})
    g = run(svc.start_rot_day(-1, 99))[0]
    holder = g.holder_id
    other = 2 if holder == 1 else 1
    svc.bot.blocked.add(other)
    with pytest.raises(PotatoError):
        run(svc.pass_potato(g.id, holder))
    assert run(svc.store.get_game(g.id)).holder_id == holder
    svc.bot.blocked.discard(other)
    res = run(svc.pass_potato(g.id, holder))
    assert res.game.duration_sec == 3600 and res.new_holder == other


def test_rot_potatoes_always_rot_someone():
    svc, bot, clock = make({1: 0, 2: 0, 3: 0})
    run(svc.start_rot_day(-1, 99))
    clock.t += 3601
    out = run(svc.resolve_expired())
    assert len(out) == 3
    assert any("дня гниения" in t for t in bot.to(-1))


def local_noon_clock(svc):
    day = svc._local(svc.store.now()).replace(hour=12, minute=0, second=0)
    return int(day.timestamp())


def test_tick_auto_starts_in_active_hours_only():
    svc, _bot, clock = make({1: 0, 2: 0}, auto_chat_id=-7, utc_offset=0)
    clock.t = 1_700_000_000 - (1_700_000_000 % 86400) + 3 * 3600
    run(svc.store.set_auto("auto", int(clock.t) - 1))
    run(svc.tick())
    assert run(svc.store.active_game(-7)) is None
    clock.t += 9 * 3600
    run(svc.tick())
    assert run(svc.store.active_game(-7)) is not None
    nxt = run(svc.store.get_auto("auto"))
    assert 4 * 3600 <= nxt - int(clock.t) <= 12 * 3600
    assert run(svc.store.cooldown_remaining(-7, 4 * 3600)) > 0


def test_tick_schedules_first_auto_and_retries_when_busy():
    svc, _, clock = make({1: 0, 2: 0}, auto_chat_id=-7, utc_offset=0)
    clock.t = 1_700_000_000 - (1_700_000_000 % 86400) + 12 * 3600
    run(svc.tick())
    first = run(svc.store.get_auto("auto"))
    assert first is not None and first > clock.t
    run(svc.start_game(-7, 99, 600))
    run(svc.store.set_auto("auto", int(clock.t) - 1))
    run(svc.tick())
    assert run(svc.store.get_auto("auto")) == int(clock.t) + 3600


def test_tick_launches_planned_rot_spawns():
    svc, bot, clock = make({1: 0, 2: 0, 3: 0}, auto_chat_id=-7, utc_offset=0)
    base = 1_700_000_000 - (1_700_000_000 % 86400)
    clock.t = base + 10 * 3600 + 1
    day = svc._local(int(clock.t)).date().isoformat()
    run(svc.store.plan_rot_day(day, int(clock.t), base + 21 * 3600, 1.0))
    run(svc.store.set_auto("auto", base + 10**7))
    while clock.t < base + 21 * 3600:
        run(svc.tick())
        clock.t += 600
    run(svc.tick())
    games = [g for g in run(svc.store.active_games()) if g.kind == "rot"]
    assert len(games) == 3
    assert sum("ДЕНЬ ГНИЕНИЯ" in t for t in bot.to(-7)) == 1
    run(svc.tick())
    assert len([g for g in run(svc.store.active_games()) if g.kind == "rot"]) == 3


def test_tick_skips_when_day_decided_not_rot():
    svc, _, clock = make({1: 0, 2: 0}, auto_chat_id=-7, utc_offset=0)
    base = 1_700_000_000 - (1_700_000_000 % 86400)
    clock.t = base + 12 * 3600
    day = svc._local(int(clock.t)).date().isoformat()
    run(svc.store.plan_rot_day(day, base + 10 * 3600, base + 21 * 3600, 0.0))
    run(svc.store.set_auto("auto", base + 10**7))
    run(svc.tick())
    assert run(svc.store.active_games()) == []


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


def test_strong_rot_activation_extends_and_announces():
    svc, bot, clock = make({1: 0})
    first = run(svc.activate_strong_rot())
    assert first == int(clock.t) + 7 * 3600
    second = run(svc.activate_strong_rot())
    assert second == first + 7 * 3600
    assert any("СИЛЬНОЕ ГНИЕНИЕ" in t for _, t in bot.sent)
    assert run(svc.strong_rot_remaining()) == 14 * 3600


def test_strong_rot_spawns_only_while_active_and_respects_roll_interval():
    svc, _bot, clock = make({1: 0, 2: 0, 3: 0})
    svc.strong_chance = 1.0
    run(svc.store.set_auto("auto", int(clock.t) + 10**7))
    run(svc.tick())
    assert run(svc.store.active_games()) == []
    run(svc.activate_strong_rot())
    run(svc.tick())
    games = run(svc.store.active_games())
    assert len(games) == 3
    assert {g.kind for g in games} == {"rot"}
    assert {g.duration_sec for g in games} == {3600}
    assert len({g.holder_id for g in games}) == 3
    run(svc.tick())
    assert len(run(svc.store.active_games())) == 3
    clock.t += 3 * 3600
    for g in run(svc.store.active_games()):
        run(svc.store.cancel_game(g.id))
    run(svc.store.set_auto("auto", int(clock.t) + 10**7))
    run(svc.tick())
    assert len(run(svc.store.active_games())) == 3


def test_strong_rot_zero_chance_spawns_nothing_and_skips_holders():
    svc, _, clock = make({1: 0, 2: 0})
    svc.strong_chance = 0.0
    run(svc.store.set_auto("auto", int(clock.t) + 10**7))
    run(svc.activate_strong_rot())
    run(svc.tick())
    assert run(svc.store.active_games()) == []
    svc.strong_chance = 1.0
    g = run(svc.start_game(-1, 99, 600))
    assert run(svc._strong_rot_roll()) == 1
    holders = {x.holder_id for x in run(svc.store.active_games())}
    assert len(holders) == 2 and g.holder_id in holders


def test_strong_rot_skips_unreachable_users():
    bot = FakeBot(blocked=frozenset({1}))
    svc, bot, _clock = make({1: 0, 2: 0}, bot)
    svc.strong_chance = 1.0
    assert run(svc._strong_rot_roll()) == 1
    assert [g.holder_id for g in run(svc.store.active_games())] == [2]


def test_paid_launch_creates_rot_potato_and_counts_start():
    svc, bot, _ = make({1: 0, 2: 0})
    game = run(svc.launch_paid(2))
    assert game.kind == "rot" and game.duration_sec == 3600
    assert run(svc.store.get_stats(2))["started"] == 1
    assert any("запустил гнилую картошку" in t for _, t in bot.sent)
    second = run(svc.launch_paid(2))
    assert second.id != game.id


def test_manual_start_counts_and_awards_start_achievement():
    svc, bot, _clock = make({1: 0})
    for i in range(10):
        run(svc.start_game(-100 - i, 5, 600))
    assert run(svc.store.get_stats(5))["started"] == 10
    assert "potato_start_10" in run(svc.store.get_stats(5))["achievements"]
    assert any("Заводила" in t for t in bot.to(5))


def test_record_purchase_announces_achievement():
    svc, bot, _ = make({1: 0})
    run(svc.record_purchase(1, "launch", 30))
    assert any("Друг гниения" in t for t in bot.to(1))
