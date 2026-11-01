from media_groups import GroupGate


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_first_then_known():
    gate = GroupGate(clock=Clock())
    assert not gate.known(1, "g")
    assert gate.first(1, "g") is True
    assert gate.known(1, "g")
    assert gate.first(1, "g") is False
    assert gate.first(2, "g") is True


def test_expires_and_prunes():
    clock = Clock()
    gate = GroupGate(ttl=10, max_size=3, clock=clock)
    for i in range(3):
        gate.first(1, str(i))
    clock.t = 11
    gate.first(1, "new")
    gate.first(1, "newer")
    assert not gate.known(1, "0")
    assert len(gate._seen) <= 3
    assert gate.first(1, "0") is True
