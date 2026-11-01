import random
from collections.abc import Sequence


def pick_pet_pair(
    cats: Sequence[str],
    dogs: Sequence[str],
    show_cats: bool,
    show_dogs: bool,
    rng: random.Random | None = None,
) -> str:
    r = rng or random
    parts: list[str] = []
    if show_cats and cats:
        parts.append(r.choice(cats).strip())
    if show_dogs and dogs:
        parts.append(r.choice(dogs).strip())
    return " ".join(parts)
