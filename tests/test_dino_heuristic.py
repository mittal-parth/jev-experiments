from dino_jev.heuristic import HeuristicClient, heuristic_answers
from dino_jev.policy import compose_intent, request_body


def _cactus(gap_px=80, tti=0.22, width=17):
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
            "x": 50,
            "y": 93,
            "ground_y": 93,
            "width": 44,
            "height": 47,
            "jumping": False,
            "ducking": False,
        },
        "nearest_obstacle": {
            "id": "o0",
            "kind": "cactus",
            "type": "cactusSmall",
            "x": 140,
            "y": 105,
            "width": width,
            "height": 35,
            "gap_px": gap_px,
            "time_to_impact_s": tti,
            "clearance": "ground",
        },
        "obstacles": [],
        "last_action": "run",
    }


def test_heuristic_runs_when_path_is_clear():
    state = _cactus()
    state["nearest_obstacle"] = None
    answers = heuristic_answers(state)
    assert answers["action"]["choice"] == "run"
    assert answers["jump_now"]["noul"] < 0.5


def test_heuristic_jumps_close_cactus():
    state = _cactus()
    answers = heuristic_answers(state)
    intent = compose_intent(answers, state, provider="heuristic", latency_ms=0.4)
    assert answers["action"]["choice"] == "jump"
    assert intent.jump is True


def test_heuristic_ducks_mid_bird():
    state = _cactus()
    state["nearest_obstacle"] = {
        "id": "o0",
        "kind": "pterodactyl",
        "type": "pterodactyl",
        "x": 120,
        "y": 75,
        "width": 46,
        "height": 40,
        "gap_px": 40,
        "time_to_impact_s": 0.1,
        "clearance": "mid",
    }
    answers = heuristic_answers(state)
    intent = compose_intent(answers, state, provider="heuristic", latency_ms=0.4)
    assert answers["action"]["choice"] == "duck"
    assert intent.duck is True


def test_heuristic_does_not_jump_too_early_on_wide_cactus():
    state = _cactus(gap_px=200, tti=0.48, width=51)
    answers = heuristic_answers(state)
    intent = compose_intent(answers, state, provider="heuristic", latency_ms=0.4)
    assert answers["action"]["choice"] == "run"
    assert intent.jump is False


def test_heuristic_client_matches_questions():
    client = HeuristicClient()
    state = _cactus()
    answers, latency = client.decide(request_body(state, "jev-latest"))
    assert latency == 0.4
    assert set(answers) == {"action", "jump_now", "duck_now", "urgency"}
