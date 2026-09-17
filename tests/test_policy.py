from krunker_jev.heuristic import HeuristicClient, heuristic_answers
from krunker_jev.policy import compose_intent, request_body
from krunker_jev.questions import HOLD_AIM, STANCE_MIN_CONFIDENCE, build_questions
from krunker_jev.world import Game


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
    game = Game(seed=1, scenario="duel")
    state = game.observe()
    state["self"].update(overrides.get("self", {}))
    if "visible_enemies" in overrides:
        state["visible_enemies"] = overrides["visible_enemies"]
    return state


def test_questions_always_include_scan_options():
    questions = build_questions(sample_state(visible_enemies=[]))
    assert set(questions) == {
        "stance",
        "move",
        "aim_target",
        "fire",
        "reload",
        "jump",
        "threat",
    }
    assert HOLD_AIM in questions["aim_target"]["criteria"]
    assert "scan_left" in questions["aim_target"]["criteria"]


def test_questions_index_visible_enemies():
    state = sample_state(
        visible_enemies=[
            {
                "id": "e1",
                "bearing_deg": -4,
                "distance": 6,
                "health": 80,
                "in_crosshair": True,
                "behind_cover": False,
                "moving": False,
            }
        ]
    )
    criteria = build_questions(state)["aim_target"]["criteria"]
    assert "e1" in criteria
    assert criteria["e1"]["in_crosshair"] is True


def fixture_answers(state, stance="hunt", move="forward", aim="e1", fire=0.95, reload=0.1, jump=0.05, threat=1.2, stance_conf=0.8):
    questions = build_questions(state)
    return {
        "stance": peaked(stance, list(questions["stance"]["criteria"]), stance_conf),
        "move": peaked(move, list(questions["move"]["criteria"])),
        "aim_target": peaked(aim, list(questions["aim_target"]["criteria"])),
        "fire": {"type": "noul", "noul": fire},
        "reload": {"type": "noul", "noul": reload},
        "jump": {"type": "noul", "noul": jump},
        "threat": {
            "type": "score",
            "score": threat,
            "legend": {"0": "a", "1": "b", "2": "c"},
            "probabilities": {"0": 0.1, "1": 0.7, "2": 0.2},
            "confidence": 0.6,
        },
    }


def test_fire_gated_on_empty_mag():
    state = sample_state()
    state["self"]["ammo_in_mag"] = 0
    state["visible_enemies"] = [
        {
            "id": "e1",
            "bearing_deg": 0,
            "distance": 5,
            "health": 100,
            "in_crosshair": True,
            "behind_cover": False,
            "moving": False,
        }
    ]
    intent = compose_intent(fixture_answers(state), state, provider="fixture", latency_ms=1)
    assert intent.fire is False


def test_reload_ignored_when_full():
    state = sample_state()
    state["self"]["ammo_in_mag"] = 20
    intent = compose_intent(
        fixture_answers(state, reload=0.99, fire=0.01, aim="hold"),
        state,
        provider="fixture",
        latency_ms=1,
    )
    assert intent.reload is False


def test_low_confidence_keeps_previous_stance():
    state = sample_state()
    first = compose_intent(fixture_answers(state, stance="retreat"), state, provider="fixture", latency_ms=1)
    second = compose_intent(
        fixture_answers(state, stance="hunt", stance_conf=STANCE_MIN_CONFIDENCE - 0.1),
        state,
        provider="fixture",
        latency_ms=1,
        previous=first,
    )
    assert first.stance == "retreat"
    assert second.stance == "retreat"


def test_speculative_aim_falls_back_if_enemy_gone():
    state = sample_state(visible_enemies=[])
    intent = compose_intent(fixture_answers(state, aim="e9", fire=0.99), state, provider="fixture", latency_ms=1)
    assert intent.aim == HOLD_AIM
    assert intent.fire is False


def test_reload_cover_suppresses_speculative_fire():
    state = sample_state()
    state["visible_enemies"] = [
        {
            "id": "e1",
            "bearing_deg": 0,
            "distance": 5,
            "health": 100,
            "in_crosshair": True,
            "behind_cover": False,
            "moving": False,
        }
    ]
    intent = compose_intent(
        fixture_answers(state, stance="reload_cover", fire=0.99),
        state,
        provider="fixture",
        latency_ms=1,
    )
    assert intent.fire is False
    assert intent.stance == "reload_cover"


def test_request_body_uses_named_state():
    body = request_body(sample_state(), "jev-latest")
    assert body["model"] == "jev-latest"
    assert "self" in body["state"]
    assert body["questions"]["fire"]["type"] == "noul"


def test_heuristic_answers_match_question_ids():
    state = sample_state()
    answers = heuristic_answers(state)
    assert set(answers) == set(build_questions(state))
    client = HeuristicClient()
    again, latency = client.decide(request_body(state, "jev-latest"))
    assert latency >= 0
    assert again["stance"]["choice"] in {"hunt", "hold_angle", "retreat", "reload_cover"}
