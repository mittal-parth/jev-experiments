from dino_jev.heuristic import heuristic_answers
from dino_jev.physics import decide_action, first_hit_frame, jump_clears
from dino_jev.policy import compose_intent


def _cactus(gap_px=80, tti=0.22, width=17, height=35):
    dino_x = 50
    dino_w = 44
    return {
        "goal": "survive",
        "run": {
            "playing": True,
            "crashed": False,
            "intro": False,
            "speed": 6.0,
            "score": 12,
            "distance_ran": 480,
            "speed_cap": 9.0,
        },
        "dino": {
            "x": dino_x,
            "y": 93,
            "ground_y": 93,
            "width": dino_w,
            "height": 47,
            "jumping": False,
            "ducking": False,
        },
        "nearest_obstacle": {
            "id": "o0",
            "kind": "cactus",
            "type": "cactusSmall",
            "x": dino_x + dino_w + gap_px,
            "y": 105,
            "width": width,
            "height": height,
            "gap_px": gap_px,
            "time_to_impact_s": tti,
            "clearance": "ground",
        },
        "obstacles": [
            {
                "id": "o0",
                "kind": "cactus",
                "type": "cactusSmall",
                "x": dino_x + dino_w + gap_px,
                "y": 105,
                "width": width,
                "height": height,
                "gap_px": gap_px,
                "time_to_impact_s": tti,
                "clearance": "ground",
            }
        ],
        "last_action": "run",
    }


def test_far_cactus_is_run():
    assert decide_action(_cactus(gap_px=200, tti=0.48, width=51)) == "run"


def test_close_cactus_is_jump():
    state = _cactus(gap_px=40, tti=0.11, width=17)
    assert decide_action(state) == "jump"


def test_early_wide_cactus_does_not_clear_a_jump():
    far_wide = _cactus(gap_px=200, tti=0.48, width=51)
    obstacles = far_wide["obstacles"]
    assert jump_clears(obstacles, speed=6.0, dino_x=50.0, ground_y=93.0) is False
    hit = first_hit_frame(
        obstacles,
        speed=6.0,
        dino_x=50.0,
        dino_y=93.0,
        dino_w=44.0,
        dino_h=47.0,
        max_frames=55,
    )
    assert hit is not None and hit > 8
    close = _cactus(gap_px=40, width=51)
    assert jump_clears(close["obstacles"], speed=6.0, dino_x=50.0, ground_y=93.0) is True


def test_higher_lead_jumps_sooner_on_a_still_clearable_cactus():
    state = _cactus(gap_px=80, width=51)
    assert decide_action(state, lead_frames=8) == "run"
    assert decide_action(state, lead_frames=16) == "jump"


def test_heuristic_uses_physics_jump():
    state = _cactus(gap_px=40, tti=0.11)
    answers = heuristic_answers(state)
    intent = compose_intent(answers, state, provider="heuristic", latency_ms=0.4)
    assert answers["action"]["choice"] == "jump"
    assert intent.jump is True


def _mid_bird(gap_px: float = 55, *, ducking: bool = False) -> dict:
    dino_x = 50.0
    dino_w = 44.0
    x = dino_x + dino_w + gap_px
    obstacle = {
        "id": "o0",
        "kind": "pterodactyl",
        "type": "pterodactyl",
        "x": x,
        "y": 75,
        "width": 46,
        "height": 40,
        "gap_px": gap_px,
        "time_to_impact_s": 0.12,
        "clearance": "mid",
    }
    return {
        "goal": "survive",
        "run": {"playing": True, "crashed": False, "intro": False, "speed": 8.0, "score": 40},
        "dino": {
            "x": dino_x,
            "y": 93,
            "ground_y": 93,
            "width": 59 if ducking else dino_w,
            "height": 25 if ducking else 47,
            "jumping": False,
            "ducking": ducking,
        },
        "nearest_obstacle": obstacle,
        "obstacles": [obstacle],
    }


def test_mid_pterodactyl_ducks_when_close():
    assert decide_action(_mid_bird(gap_px=42), lead_frames=12) == "duck"


def test_mid_pterodactyl_stays_ducked_until_bird_passes():
    state = _mid_bird(gap_px=-10, ducking=True)
    assert decide_action(state, lead_frames=12) == "duck"
    passed = _mid_bird(gap_px=-100, ducking=True)
    assert decide_action(passed, lead_frames=12) == "run"
