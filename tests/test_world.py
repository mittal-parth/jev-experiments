from krunker_jev.world import Game, Intent


def idle_intent(**overrides) -> Intent:
    data = dict(
        stance="hold_angle",
        move="stop",
        aim="hold",
        fire=False,
        reload=False,
        jump=False,
        threat=0.2,
        confidence={"stance": 0.9},
        probabilities={},
        nouls={"fire": 0.0, "reload": 0.0, "jump": 0.0},
        latency_ms=1,
        provider="fixture",
    )
    data.update(overrides)
    return Intent(**data)


def test_walls_block_line_of_sight():
    game = Game(seed=1)
    assert game.line_of_sight(4.5, 16.5, 4.5, 3.5) is True
    assert game.line_of_sight(4.5, 10.5, 20.5, 10.5) is False


def test_player_cannot_walk_through_walls():
    game = Game(seed=1)
    game.player.x = 1.2
    game.player.y = 10.5
    game.player.yaw = 180.0
    game.apply(idle_intent(move="forward"), 0.2)
    assert game.player.x >= 1.0


def test_fov_hides_enemy_behind_player():
    game = Game(seed=1, scenario="duel")
    game.player.x = 4.5
    game.player.y = 16.5
    game.player.yaw = 90.0
    visible = game.observe()["visible_enemies"]
    assert visible == []


def test_fov_shows_enemy_ahead():
    game = Game(seed=1, scenario="duel")
    visible = game.observe()["visible_enemies"]
    assert visible and visible[0]["id"] == "e1"
    assert visible[0]["distance"] > 10


def test_hitscan_damages_aligned_target():
    game = Game(seed=1, scenario="duel")
    start = game.enemies[0].health
    game.apply(idle_intent(aim="e1", fire=True, move="stop"), 0.1)
    assert game.enemies[0].health == start - 24
    assert game.player.mag == 19


def test_reload_refills_magazine():
    game = Game(seed=1, scenario="duel")
    game.player.mag = 2
    game.apply(idle_intent(reload=True), 0.1)
    assert game.player.reloading
    game.step(1.2)
    assert game.player.mag == 20
    assert game.player.reserve == 62


def test_kill_and_respawn():
    game = Game(seed=1, scenario="duel")
    game.enemies[0].health = 10
    game.apply(idle_intent(aim="e1", fire=True), 0.1)
    assert game.enemies[0].alive is False
    assert game.player.kills == 1
    game.step(1.7)
    assert game.enemies[0].alive is True
    assert game.enemies[0].health == 100
