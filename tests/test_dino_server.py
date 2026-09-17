import time

from dino_jev.server import DinoServer


def test_fake_server_start_is_rate_limited():
    arena = DinoServer(policy="heuristic", backend="fake", auto_restart=False)
    arena.start()
    time.sleep(0.35)
    arena.stop()
    if arena.worker is not None:
        arena.worker.join(timeout=1)
    assert 1 <= arena.loop.ticks < 20
    assert arena.running is False
    arena.close()
