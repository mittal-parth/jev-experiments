import time

from krunker_jev.server import ArenaServer


def test_arena_start_is_rate_limited():
    arena = ArenaServer(policy="heuristic", seed=1)
    arena.start()
    time.sleep(0.35)
    arena.stop()
    if arena.worker is not None:
        arena.worker.join(timeout=1)
    assert 1 <= arena.loop.ticks < 12
    assert arena.running is False
