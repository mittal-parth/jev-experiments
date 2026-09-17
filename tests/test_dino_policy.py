from dino_jev.policy import compose_intent, obstacle_clearance, request_body
from dino_jev.questions import ACTION_MIN_CONFIDENCE, build_questions


def peaked(choice: str, options: list[str], confidence: float = 0.8) -> dict:
    rest = (1.0 - 0.72) / (len(options) - 1)
    probabilities = {option: (0.72 if option == choice else rest) for option in options}
    return {
        "type": "choice",
        "choice": choice,
        "probabilities": probabilities,
        "confidence": confidence,
    }


def sample_state(**overrides):
    state = {
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
            "width": 17,
            "height": 35,
            "gap_px": 46,
            "time_to_impact_s": 0.12,
            "clearance": "ground",
        },
        "obstacles": [],
        "last_action": "run",
    }
    state["run"].update(overrides.get("run", {}))
    state["dino"].update(overrides.get("dino", {}))
    if "nearest_obstacle" in overrides:
        state["nearest_obstacle"] = overrides["nearest_obstacle"]
    return state


def fixture_answers(action="jump", jump=0.9, duck=0.1, urgency=1.2, action_conf=0.8):
    return {
        "action": peaked(action, ["run", "jump", "duck"], action_conf),
        "jump_now": {"type": "noul", "noul": jump},
        "duck_now": {"type": "noul", "noul": duck},
        "urgency": {
            "type": "score",
            "score": urgency,
            "legend": {"0": "a", "1": "b", "2": "c"},
            "probabilities": {"0": 0.1, "1": 0.7, "2": 0.2},
            "confidence": 0.6,
        },
    }


def test_questions_are_the_four_heads():
    questions = build_questions(sample_state())
    assert set(questions) == {"action", "jump_now", "duck_now", "urgency"}
    assert set(questions["action"]["criteria"]) == {"run", "jump", "duck"}


def test_request_body_includes_state():
    state = sample_state()
    body = request_body(state, "jev-latest")
    assert body["state"]["dino"]["x"] == 50
    assert body["questions"]["jump_now"]["type"] == "noul"


def test_cactus_jump_is_executed():
    intent = compose_intent(
        fixture_answers(action="jump", jump=0.9),
        sample_state(),
        provider="fixture",
        latency_ms=12,
    )
    assert intent.jump is True
    assert intent.duck is False
    assert intent.action == "jump"


def test_cannot_jump_while_airborne():
    intent = compose_intent(
        fixture_answers(action="jump", jump=0.99),
        sample_state(dino={"jumping": True}),
        provider="fixture",
        latency_ms=12,
    )
    assert intent.jump is False
    assert intent.action == "run"


def test_cannot_duck_a_cactus():
    intent = compose_intent(
        fixture_answers(action="duck", jump=0.1, duck=0.99),
        sample_state(),
        provider="fixture",
        latency_ms=12,
    )
    assert intent.duck is False
    assert intent.jump is False
    assert intent.action == "run"


def test_high_pterodactyl_does_not_jump():
    bird = {
        "id": "o0",
        "kind": "pterodactyl",
        "type": "pterodactyl",
        "x": 120,
        "y": 50,
        "width": 46,
        "height": 40,
        "gap_px": 26,
        "time_to_impact_s": 0.07,
        "clearance": "high",
    }
    intent = compose_intent(
        fixture_answers(action="jump", jump=0.99, duck=0.2),
        sample_state(nearest_obstacle=bird),
        provider="fixture",
        latency_ms=12,
    )
    assert obstacle_clearance(bird) == "high"
    assert intent.jump is False
    assert intent.duck is False
    assert intent.action == "run"


def test_mid_pterodactyl_ducks():
    bird = {
        "id": "o0",
        "kind": "pterodactyl",
        "type": "pterodactyl",
        "x": 120,
        "y": 75,
        "width": 46,
        "height": 40,
        "gap_px": 26,
        "time_to_impact_s": 0.07,
        "clearance": "mid",
    }
    intent = compose_intent(
        fixture_answers(action="duck", jump=0.1, duck=0.95),
        sample_state(nearest_obstacle=bird),
        provider="fixture",
        latency_ms=12,
    )
    assert intent.duck is True
    assert intent.jump is False
    assert intent.action == "duck"


def test_low_confidence_keeps_previous_action():
    previous = compose_intent(
        fixture_answers(action="run", jump=0.1, duck=0.1),
        sample_state(nearest_obstacle=None),
        provider="fixture",
        latency_ms=4,
    )
    intent = compose_intent(
        fixture_answers(action="jump", jump=0.1, duck=0.1, action_conf=ACTION_MIN_CONFIDENCE - 0.1),
        sample_state(nearest_obstacle=None),
        provider="fixture",
        latency_ms=4,
        previous=previous,
    )
    assert intent.action == "run"
    assert intent.jump is False


def test_intent_hud_payload_exposes_typesafe_heads():
    intent = compose_intent(
        fixture_answers(action="jump", jump=0.9, duck=0.1, urgency=1.2),
        sample_state(),
        provider="jev",
        latency_ms=18.4,
    )
    payload = intent.hud_payload()
    dumped = intent.as_dict()
    assert payload["provider"] == "jev"
    assert payload["asked"] == "jump"
    assert payload["action"] == "jump"
    assert payload["gated"] is False
    assert payload["jump_p"] > payload["run_p"]
    assert payload["jump_now"] == 0.9
    assert payload["duck_now"] == 0.1
    assert payload["urgency"] == 1.2
    assert payload["latency_ms"] == 18.4
    assert payload["armed"] == "jump"
    assert payload["armed_id"] == "o0"
    assert payload["arm_gap"] == 46.0
    assert dumped["asked"] == "jump"
    assert dumped["gated"] is False


def test_intent_hud_payload_marks_gated_when_policy_overrides():
    intent = compose_intent(
        fixture_answers(action="jump", jump=0.99),
        sample_state(dino={"jumping": True}),
        provider="jev",
        latency_ms=12,
    )
    payload = intent.hud_payload()
    assert payload["asked"] == "jump"
    assert payload["action"] == "run"
    assert payload["gated"] is True
    assert intent.as_dict()["gated"] is True
