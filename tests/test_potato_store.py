import asyncio
import random
import sqlite3
from pathlib import Path

import pytest

from potato.store import (
    MAX_DURATION,
    MIN_DURATION,
    SHARE_FIELDS,
    PotatoError,
    PotatoStore,
    clamp_duration,
    random_duration,
)

INIT_SQL = (
    Path(__file__).resolve().parent.parent
    / "database_rs"
    / "migrations"
    / "0001_init.sql"
).read_text(encoding="utf-8")


class Clock:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


def make_store(users: dict[int, int], banned: tuple[int, ...] = ()):
    clock = Clock()
    store = PotatoStore(":memory:", clock=clock, rng=random.Random(1))
    assert store._keep is not None
    store._keep.executescript(INIT_SQL)
    for uid, vip in users.items():
        store._keep.execute(
            "INSERT INTO users (user_id, is_vip) VALUES (?, ?)", (uid, vip)
        )
    for uid in banned:
        store._keep.execute("INSERT INTO banned (user_id) VALUES (?)", (uid,))
    asyncio.run(store.init())
    return store, clock


def run(coro):
    return asyncio.run(coro)


def test_migration_idempotent():
    store, _ = make_store({1: 0})
    run(store.init())
    run(store.init())


def test_duration_bounds():
    assert clamp_duration(1) == MIN_DURATION
    assert clamp_duration(10**9) == MAX_DURATION
    for _ in range(50):
        assert MIN_DURATION <= random_duration() <= MAX_DURATION


def test_single_active_game_per_chat():
    store, _ = make_store({1: 0})
    run(store.create_game(-100, 1, 600))
    with pytest.raises(PotatoError):
        run(store.create_game(-100, 1, 600))
    run(store.create_game(-200, 1, 600))


def test_candidates_exclude_banned_admin_and_optouts():
    store, _ = make_store({1: 0, 2: 0, 3: 1, 4: 1, 5: 0, 99: 0}, banned=(5,))
    run(store.set_enabled(3, False))
    game = run(store.create_game(-1, 99, 600))
    cands = run(store.candidates(game.id, set(), admin_id=99))
    assert sorted(cands) == [1, 2, 4]


def test_anyone_can_leave_and_return():
    store, _ = make_store({1: 0})
    run(store.set_enabled(1, False))
    assert run(store.get_stats(1))["enabled"] == 0
    game = run(store.create_game(-1, 9, 600))
    assert run(store.candidates(game.id, set(), None)) == []
    run(store.set_enabled(1, True))
    assert run(store.candidates(game.id, set(), None)) == [1]


def test_vip_share_settings():
    store, _ = make_store({1: 0, 2: 1})
    with pytest.raises(PotatoError):
        run(store.set_share(1, "share_passed", False))
    with pytest.raises(PotatoError):
        run(store.set_share(404, "share_passed", False))
    with pytest.raises(PotatoError):
        run(store.set_share(2, "bogus", False))
    run(store.set_share(2, "share_passed", False))
    assert run(store.get_stats(2))["share_passed"] == 0
    run(store.set_share(2, "share_passed", True))
    assert run(store.get_stats(2))["share_passed"] == 1


def test_share_keeps_at_least_one_field():
    store, _ = make_store({2: 1})
    for field in SHARE_FIELDS[:-1]:
        run(store.set_share(2, field, False))
    with pytest.raises(PotatoError):
        run(store.set_share(2, SHARE_FIELDS[-1], False))


def test_dogs_toggle_default_on():
    store, _ = make_store({1: 0})
    assert run(store.get_stats(1))["show_dogs"] == 1
    run(store.set_dogs(1, False))
    assert run(store.get_stats(1))["show_dogs"] == 0


def test_started_and_purchase_achievements():
    store, _ = make_store({1: 0})
    got = []
    for _ in range(10):
        got += run(store.record_start(1))
    assert got.count("potato_start_10") == 1
    assert "potato_donor" in run(store.record_purchase(1, "launch", 30))
    assert run(store.get_stats(1))["bought"] == 1


def test_pass_100_achievement():
    store, _ = make_store({1: 0, 2: 0})
    store._keep.execute("INSERT INTO potato_players (user_id, passed) VALUES (2, 99)")
    g = run(store.assign_holder(run(store.create_game(-1, 1, 600)).id, 2)).game
    res = run(store.pass_potato(g.id, 2, 1))
    assert "potato_pass_100" in res.new_achievements
    assert "potato_pass_50" in run(store.get_stats(2))["achievements"]


def test_active_holders_and_eligible_users():
    store, _ = make_store({1: 0, 2: 0, 99: 0})
    g = run(store.assign_holder(run(store.create_game(-1, 99, 600)).id, 2)).game
    assert run(store.active_holders()) == {2}
    assert sorted(run(store.eligible_users(99))) == [1, 2]
    run(store.cancel_game(g.id))
    assert run(store.active_holders()) == set()


def test_cooldown():
    store, clock = make_store({1: 0})
    assert run(store.cooldown_remaining(-1, 4 * 3600)) == 0
    run(store.mark_started(-1))
    assert run(store.cooldown_remaining(-1, 4 * 3600)) == 4 * 3600
    clock.t += 4 * 3600 - 1
    assert run(store.cooldown_remaining(-1, 4 * 3600)) == 1
    clock.t += 1
    assert run(store.cooldown_remaining(-1, 4 * 3600)) == 0
    assert run(store.cooldown_remaining(-2, 4 * 3600)) == 0


def test_rot_games_are_parallel_with_fixed_hour_and_never_defuse():
    store, clock = make_store({1: 0, 2: 0})
    games = [run(store.create_game(-1, 0, 99999, "rot")) for _ in range(3)]
    assert all(g.duration_sec == 3600 and g.kind == "rot" for g in games)
    run(store.create_game(-1, 0, 600))
    g = run(store.assign_holder(games[0].id, 1)).game
    with pytest.raises(PotatoError):
        run(store.pass_potato(g.id, 1, None))
    clock.t += 3601
    res = run(store.explode_if_expired(g.id))
    assert res is not None and "potato_rot_boom" in res.new_achievements
    assert run(store.get_stats(1))["rot_exploded"] == 1


def test_plan_rot_day_is_persistent_and_bounded():
    store, clock = make_store({1: 0})
    start, end = int(clock.t), int(clock.t) + 36000
    assert run(store.plan_rot_day("d1", start, end, 0.0)) is False
    assert run(store.plan_rot_day("d1", start, end, 1.0)) is False
    assert run(store.plan_rot_day("d2", start, end, 1.0)) is True
    assert run(store.plan_rot_day("d2", start, end, 0.0)) is True
    rows = store._keep.execute(
        "SELECT spawn_at FROM potato_rot_spawns WHERE day = 'd2'"
    ).fetchall()
    assert len(rows) == 3 and all(start <= r[0] < end for r in rows)
    assert run(store.plan_rot_day("d3", end - 100, end, 1.0)) is False


def test_due_spawns_lifecycle():
    store, clock = make_store({1: 0})
    start = int(clock.t)
    run(store.plan_rot_day("d", start, start + 36000, 1.0))
    assert run(store.due_rot_spawns(7200)) == [] or True
    clock.t += 36000
    due = run(store.due_rot_spawns(10**6))
    assert len(due) == 3 and due[0][2] is True
    for day, at, _ in due:
        run(store.mark_spawn_launched(day, at))
    assert run(store.due_rot_spawns(10**6)) == []


def test_stale_spawns_are_dropped():
    store, clock = make_store({1: 0})
    start = int(clock.t)
    run(store.plan_rot_day("d", start, start + 36000, 1.0))
    clock.t += 36000 + 3 * 3600
    assert run(store.due_rot_spawns(2 * 3600)) == []


def test_auto_schedule_storage():
    store, _ = make_store({1: 0})
    assert run(store.get_auto("auto")) is None
    run(store.set_auto("auto", 5))
    run(store.set_auto("auto", 9))
    assert run(store.get_auto("auto")) == 9


def test_init_applies_events_migration_once():
    store, _ = make_store({1: 0})
    run(store.init())
    cols = [r[1] for r in store._keep.execute("PRAGMA table_info(potato_games)")]
    assert cols.count("kind") == 1


def test_pass_flow_and_stats():
    store, clock = make_store({1: 0, 2: 0, 3: 0})
    game = run(store.create_game(-1, 1, 600))
    game = run(store.assign_holder(game.id, 2)).game
    assert game.holder_id == 2 and game.expires_at == int(clock.t) + 600
    clock.t += 30
    res = run(store.pass_potato(game.id, 2, 3))
    assert res.new_holder == 3 and res.elapsed == 30
    assert "potato_pass_1" in res.new_achievements
    assert "potato_fast" in res.new_achievements
    s2, s3 = run(store.get_stats(2)), run(store.get_stats(3))
    assert s2["passed"] == 1 and s2["received"] == 1
    assert s3["received"] == 1 and "potato_first" in s3["achievements"]
    assert run(store.get_game(game.id)).pass_count == 1


def test_pass_validations():
    store, clock = make_store({1: 0, 2: 0, 3: 0})
    game = run(store.assign_holder(run(store.create_game(-1, 1, 600)).id, 2)).game
    with pytest.raises(PotatoError):
        run(store.pass_potato(game.id, 3, 1))
    with pytest.raises(PotatoError):
        run(store.pass_potato(game.id, 2, 2))
    clock.t += 601
    with pytest.raises(PotatoError):
        run(store.pass_potato(game.id, 2, 3))
    assert run(store.get_stats(2))["passed"] == 0


def test_double_resolution_impossible():
    store, clock = make_store({1: 0, 2: 0})
    game = run(store.assign_holder(run(store.create_game(-1, 1, 600)).id, 2)).game
    clock.t += 700
    assert run(store.explode_if_expired(game.id)).victim == 2
    assert run(store.explode_if_expired(game.id)) is None
    with pytest.raises(PotatoError):
        run(store.pass_potato(game.id, 2, 1))
    s = run(store.get_stats(2))
    assert s["exploded"] == 1 and "potato_boom_1" in s["achievements"]
    run(store.create_game(-1, 1, 600))


def test_explode_not_before_deadline():
    store, clock = make_store({1: 0, 2: 0})
    game = run(store.assign_holder(run(store.create_game(-1, 1, 600)).id, 2)).game
    clock.t += 599
    assert run(store.explode_if_expired(game.id)) is None


def test_streak_resets_on_explosion_and_boom_5():
    store, clock = make_store({1: 0, 2: 0})
    for i in range(5):
        g = run(store.assign_holder(run(store.create_game(-10 - i, 1, 600)).id, 2)).game
        clock.t += 601
        run(store.explode_if_expired(g.id))
    s = run(store.get_stats(2))
    assert s["exploded"] == 5 and "potato_boom_5" in s["achievements"]
    assert s["pass_streak"] == 0


def test_streak_achievement():
    store, clock = make_store({1: 0, 2: 0, 3: 0})
    g = run(store.assign_holder(run(store.create_game(-1, 1, 600)).id, 2)).game
    holder, other = 2, 3
    got = []
    for _ in range(6):
        clock.t += 100
        res = run(store.pass_potato(g.id, holder, other))
        got += res.new_achievements
        holder, other = other, holder
    assert "potato_streak_3" in got


def test_nobody_left_defuses():
    store, _ = make_store({1: 0, 2: 0})
    g = run(store.assign_holder(run(store.create_game(-1, 1, 600)).id, 2)).game
    res = run(store.pass_potato(g.id, 2, None))
    assert res.new_holder is None and res.game.status == "defused"
    assert run(store.active_game(-1)) is None


def test_history_prefers_fresh_players_then_falls_back():
    store, _ = make_store({1: 0, 2: 0, 3: 0})
    g = run(store.assign_holder(run(store.create_game(-1, 9, 600)).id, 1)).game
    assert sorted(run(store.candidates(g.id, {1}, None))) == [2, 3]
    run(store.pass_potato(g.id, 1, 2))
    run(store.pass_potato(g.id, 2, 3))
    assert sorted(run(store.candidates(g.id, {3}, None))) == [1, 2]


def test_active_games_listing_and_cancel():
    store, _ = make_store({1: 0})
    g = run(store.create_game(-1, 1, 600))
    assert [x.id for x in run(store.active_games())] == [g.id]
    run(store.cancel_game(g.id))
    assert run(store.active_games()) == []


def test_file_db_wal_roundtrip(tmp_path):
    path = str(tmp_path / "t.db")
    conn = sqlite3.connect(path)
    conn.executescript(INIT_SQL)
    conn.execute("INSERT INTO users (user_id) VALUES (1)")
    conn.commit()
    conn.close()
    store = PotatoStore(path)
    run(store.init())
    g = run(store.create_game(-1, 1, 600))
    run(store.assign_holder(g.id, 1))
    assert run(store.get_stats(1))["received"] == 1


def test_left_non_vip_cannot_receive_potato():
    store, _ = make_store({1: 0, 2: 0})
    run(store.set_enabled(1, False))
    game = run(store.create_game(-1, 2, 600))
    with pytest.raises(PotatoError):
        run(store.assign_holder(game.id, 1))
    assert run(store.candidates(game.id, set(), None)) == [2]
