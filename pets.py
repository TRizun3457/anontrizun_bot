import random
from collections.abc import Sequence


def pick_pet_from(
    cats: Sequence[str],
    dogs: Sequence[str],
    show_cats: bool,
    show_dogs: bool,
    rng: random.Random | None = None,
) -> str:
    r = rng or random
    pools: list[Sequence[str]] = []
    if show_cats and cats:
        pools.append(cats)
    if show_dogs and dogs:
        pools.append(dogs)
    if not pools:
        return ""
    return r.choice(r.choice(pools)).strip()
