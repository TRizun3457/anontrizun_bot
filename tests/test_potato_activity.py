import random

from potato.randomness import candidate_weight, weighted_order
from potato.store import DORMANT_AFTER
from tests.test_potato_service import make, run
from tests.test_potato_store import make_store


def _explode_once(store, clock, user, chat):
    game = run(store.assign_holder(run(store.create_game(chat, 1, 600)).id, user)).game
    clock.t += 601
    run(store.explode_if_expired(game.id))


def test_player_goes_dormant_after_missing_many_in_a_row():
    store, clock = make_store({1: 0, 2: 0})
    for i in range(DORMANT_AFTER):
        _explode_once(store, clock, 2, -10 - i)
    stats = run(store.get_stats(2))
    assert stats["dormant"] == 1 and stats["miss_streak"] == DORMANT_AFTER
    game = run(store.create_game(-1, 1, 600))
    assert run(store.candidates(game.id, set())) == [1]
    assert 2 not in run(store.eligible_users())


def test_activity_brings_potatoes_back():
    store, clock = make_store({1: 0, 2: 0})
    for i in range(DORMANT_AFTER):
        _explode_once(store, clock, 2, -10 - i)
    assert run(store.touch_activity(2)) is True
    assert run(store.touch_activity(2)) is False
    stats = run(store.get_stats(2))
    assert stats["dormant"] == 0 and stats["miss_streak"] == 0
    game = run(store.create_game(-1, 1, 600))
    assert sorted(run(store.candidates(game.id, set()))) == [1, 2]


def test_few_misses_do_not_pause_and_pass_resets_streak():
    store, clock = make_store({1: 0, 2: 0, 3: 0})
    for i in range(DORMANT_AFTER - 1):
        _explode_once(store, clock, 2, -10 - i)
    assert run(store.get_stats(2))["dormant"] == 0
    game = run(store.assign_holder(run(store.create_game(-50, 1, 600)).id, 2)).game
    run(store.pass_potato(game.id, 2, 3))
    assert run(store.get_stats(2))["miss_streak"] == 0
    assert run(store.flagged_users()) == set()


def test_flagged_users_lists_missers_and_dormant():
    store, clock = make_store({1: 0, 2: 0})
    _explode_once(store, clock, 2, -10)
    assert run(store.flagged_users()) == {2}


def test_service_activity_hook_resumes_dormant_player():
    svc, _, clock = make({1: 0, 2: 0})
    for i in range(DORMANT_AFTER):
        _explode_once(svc.store, clock, 2, -10 - i)
    run(svc.note_activity(2))
    assert run(svc.store.get_stats(2))["dormant"] == 0
    run(svc.note_activity(1))
    run(svc.note_activity(2))


def test_service_flags_victim_in_memory_after_expiry():
    svc, _, clock = make({1: 0, 2: 0})
    run(svc.note_activity(1))
    for i in range(DORMANT_AFTER):
        game = run(
            svc.store.assign_holder(run(svc.store.create_game(-10 - i, 1, 600)).id, 2)
        ).game
        clock.t += 601
        run(svc.resolve_expired())
        assert game.id
    assert 2 in svc._flagged
    run(svc.note_activity(2))
    assert 2 not in svc._flagged
    assert run(svc.store.get_stats(2))["dormant"] == 0


def test_owner_can_receive_potatoes():
    svc, _, _ = make({99: 0})
    game = run(svc.start_game(-1, 5, 600))
    assert game.holder_id == 99


def test_weights_prefer_long_waiting_and_penalize_busy_and_recent():
    fresh = candidate_weight(None, False)
    waited = candidate_weight(10 * 3600, False)
    recent = candidate_weight(60, False)
    busy = candidate_weight(10 * 3600, True)
    assert recent < 1.0 < waited <= 3.0 and fresh == 2.0
    assert busy < waited
    assert candidate_weight(10**9, False) == 3.0


def test_weighted_order_is_random_but_biased():
    rng = random.Random(11)
    first = {1: 0, 2: 0}
    for _ in range(4000):
        first[weighted_order([1, 2], [3.0, 1.0], rng)[0]] += 1
    assert 0.65 < first[1] / 4000 < 0.85
    orders = {tuple(weighted_order([1, 2, 3, 4], [1.0] * 4, rng)) for _ in range(300)}
    assert len(orders) > 12


def test_store_uses_system_random_by_default():
    import random as rnd

    from potato.store import PotatoStore

    assert isinstance(PotatoStore(":memory:")._rng, rnd.SystemRandom)
