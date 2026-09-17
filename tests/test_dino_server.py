import time

from dino_jev.server import DinoServer


def test_fake_server_start_is_rate_limited():
    arena = DinoServer(policy="heuristic", backend="fake", auto_restart=False)
    arena.enqueue("start")
    started = time.perf_counter()
    while time.perf_counter() - started < 0.35:
        arena.pump()
    arena.enqueue("stop")
    arena.pump()
    assert 1 <= arena.loop.ticks < 20
    assert arena.running is False
    arena.close()


def test_fake_server_starts_from_page_command():
    arena = DinoServer(policy="heuristic", backend="fake", auto_restart=False)
    arena.session.pending_command = "start"
    arena.pump()
    assert arena.running is True
    assert arena.session.playing is True
    arena.enqueue("stop")
    arena.pump()
    arena.close()


def test_fake_server_accepts_fullscreen_flag():
    arena = DinoServer(
        policy="heuristic",
        backend="fake",
        auto_restart=False,
        fullscreen=False,
    )
    assert arena.fullscreen is False
    arena.close()
