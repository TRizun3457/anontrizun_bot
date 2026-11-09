import random
from collections.abc import Sequence

NEVER_RECEIVED_WEIGHT = 2.0
MAX_WAIT_BONUS = 2.0
WAIT_BONUS_HOURS = 12.0
RECENT_SECONDS = 30 * 60
RECENT_FACTOR = 0.3
BUSY_FACTOR = 0.25


def candidate_weight(
    seconds_since_received: float | None,
    busy: bool,
    *,
    recent_seconds: int = RECENT_SECONDS,
) -> float:
    if seconds_since_received is None:
        weight = NEVER_RECEIVED_WEIGHT
    else:
        hours = max(0.0, seconds_since_received) / 3600.0
        weight = 1.0 + min(hours / WAIT_BONUS_HOURS, MAX_WAIT_BONUS)
        if seconds_since_received < recent_seconds:
            weight *= RECENT_FACTOR
    if busy:
        weight *= BUSY_FACTOR
    return weight


def weighted_order(
    ids: Sequence[int], weights: Sequence[float], rng: random.Random
) -> list[int]:
    keyed: list[tuple[float, int]] = []
    for uid, weight in zip(ids, weights, strict=True):
        draw = rng.random() or 1e-12
        keyed.append((draw ** (1.0 / max(weight, 1e-6)), uid))
    keyed.sort(reverse=True)
    return [uid for _, uid in keyed]
