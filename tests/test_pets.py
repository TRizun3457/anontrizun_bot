import random

from pets import pick_pet_from

CATS = ["c1", "c2", "c3", "c4"]
DOGS = ["d1", "d2", "d3", "d4"]


def test_nothing_enabled_gives_empty():
    assert pick_pet_from(CATS, DOGS, False, False) == ""


def test_only_cats_or_only_dogs():
    assert pick_pet_from(CATS, DOGS, True, False) in CATS
    assert pick_pet_from(CATS, DOGS, False, True) in DOGS


def test_both_enabled_gives_single_pet_that_alternates_between_kinds():
    rng = random.Random(3)
    results = [pick_pet_from(CATS, DOGS, True, True, rng) for _ in range(100)]
    assert all(r in CATS + DOGS for r in results)
    assert any(r in CATS for r in results)
    assert any(r in DOGS for r in results)


def test_each_call_is_independent_and_repeats_are_possible():
    rng = random.Random(1)
    results = [pick_pet_from(CATS, DOGS, True, True, rng) for _ in range(200)]
    assert len(set(results)) > 1
    assert len(set(results)) <= len(CATS) + len(DOGS)
