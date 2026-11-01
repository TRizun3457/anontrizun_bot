import time
from collections.abc import Callable


class GroupGate:
    def __init__(
        self,
        ttl: float = 30.0,
        max_size: int = 4000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl = ttl
        self.max_size = max_size
        self._clock = clock
        self._seen: dict[tuple[int, str], float] = {}

    def known(self, user_id: int, group_id: str) -> bool:
        stamp = self._seen.get((user_id, group_id))
        return stamp is not None and self._clock() - stamp <= self.ttl

    def first(self, user_id: int, group_id: str) -> bool:
        if self.known(user_id, group_id):
            return False
        now = self._clock()
        self._seen[(user_id, group_id)] = now
        if len(self._seen) > self.max_size:
            cutoff = now - self.ttl
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
        return True
