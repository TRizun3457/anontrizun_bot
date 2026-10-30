import asyncio
import random
import sqlite3
from pathlib import Path

import pytest

from potato.store import (
    MAX_DURATION,
    MIN_DURATION,
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


def test_only_vip_can_opt_out_and_can_return():
    store, _ = make_store({1: 0, 2: 1})
    with pytest.raises(PotatoError):
        run(store.set_enabled(1, False))
    with pytest.raises(PotatoError):
        run(store.set_enabled(404, False))
    run(store.set_enabled(2, False))
    assert run(store.get_stats(2))["enabled"] == 0
    run(store.set_enabled(2, True))
    assert run(store.get_stats(2))["enabled"] == 1


def test_lost_vip_makes_optout_void():
    store, _ = make_store({1: 1, 2: 0})
    run(store.set_enabled(1, False))
    store._keep.execute("UPDATE users SET is_vip = 0 WHERE user_id = 1")
    game = run(store.create_game(-1, 2, 600))
    assert 1 in run(store.candidates(game.id, set(), None))


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
