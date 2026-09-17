from krunker_jev.client import FixtureClient
from krunker_jev.heuristic import HeuristicClient
from krunker_jev.loop import MatchLoop
from krunker_jev.policy import request_body
from krunker_jev.questions import build_questions
from krunker_jev.world import Game


def _peaked(choice, options, confidence=0.86):
    rest = (1.0 - 0.8) / (len(options) - 1)
    return {
        "type": "choice",
        "choice": choice,
        "probabilities": {option: (0.8 if option == choice else rest) for option in options},
        "confidence": confidence,
    }


def duel_answers(state):
    questions = build_questions(state)
    aim = "e1" if any(enemy["id"] == "e1" for enemy in state["visible_enemies"]) else "hold"
    return {
        "stance": _peaked("hunt", list(questions["stance"]["criteria"])),
        "move": _peaked("stop", list(questions["move"]["criteria"])),
        "aim_target": _peaked(aim, list(questions["aim_target"]["criteria"])),
        "fire": {"type": "noul", "noul": 0.97},
        "reload": {"type": "noul", "noul": 0.05},
        "jump": {"type": "noul", "noul": 0.02},
        "threat": {
            "type": "score",
            "score": 1.1,
            "legend": {"0": "s", "1": "c", "2": "l"},
            "probabilities": {"0": 0.2, "1": 0.7, "2": 0.1},
            "confidence": 0.7,
        },
    }


class ScriptedClient:
    provider = "fixture"

    def decide(self, body):
        return duel_answers(body["state"]), 2.0


def test_scripted_duel_gets_a_kill():
    loop = MatchLoop(Game(seed=1, scenario="duel"), ScriptedClient())
    frames = loop.run(12)
    assert frames[-1]["player"]["kills"] >= 1
    assert frames[-1]["last_intent"]["provider"] == "fixture"
    assert any(frame["last_intent"]["fire"] for frame in frames)


def test_heuristic_match_runs():
    loop = MatchLoop(Game(seed=3, scenario="ffa"), HeuristicClient())
    frames = loop.run(25)
    assert frames[-1]["time"] > 0
    assert frames[-1]["player"]["health"] <= 100
    assert frames[-1]["last_intent"]["provider"] == "heuristic"


def test_fixture_client_validates_shape():
    game = Game(seed=1, scenario="duel")
    state = game.observe()
    client = FixtureClient(duel_answers(state))
    answers, latency = client.decide(request_body(state, "jev-latest"))
    assert latency == 1.0
    assert answers["stance"]["choice"] == "hunt"
