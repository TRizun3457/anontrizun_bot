import random

from pets import pick_pet_pair

CATS = ["c1", "c2", "c3", "c4"]
DOGS = ["d1", "d2", "d3", "d4"]


def test_nothing_enabled_gives_empty():
    assert pick_pet_pair(CATS, DOGS, False, False) == ""


def test_only_cats_or_only_dogs():
    assert pick_pet_pair(CATS, DOGS, True, False) in CATS
    assert pick_pet_pair(CATS, DOGS, False, True) in DOGS


def test_both_appear_together_as_a_pair():
    for seed in range(30):
        cat, dog = pick_pet_pair(CATS, DOGS, True, True, random.Random(seed)).split()
        assert cat in CATS and dog in DOGS


def test_each_call_is_independent_and_repeats_are_possible():
    rng = random.Random(1)
    results = [pick_pet_pair(CATS, DOGS, True, True, rng) for _ in range(200)]
    assert len(set(results)) > 1
    assert len(set(results)) <= len(CATS) * len(DOGS)
