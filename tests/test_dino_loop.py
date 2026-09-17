from dino_jev.client import FixtureClient
from dino_jev.fake import FakeDino
from dino_jev.heuristic import HeuristicClient
from dino_jev.loop import RunLoop, default_policy, make_client
from dino_jev.policy import request_body
from dino_jev.questions import build_questions


def _peaked(choice, options, confidence=0.86):
    rest = (1.0 - 0.8) / (len(options) - 1)
    return {
        "type": "choice",
        "choice": choice,
        "probabilities": {option: (0.8 if option == choice else rest) for option in options},
        "confidence": confidence,
    }


def jump_answers(state):
    questions = build_questions(state)
    return {
        "action": _peaked("jump", list(questions["action"]["criteria"])),
        "jump_now": {"type": "noul", "noul": 0.95},
        "duck_now": {"type": "noul", "noul": 0.05},
        "urgency": {
            "type": "score",
            "score": 1.4,
            "legend": {"0": "a", "1": "b", "2": "c"},
            "probabilities": {"0": 0.1, "1": 0.3, "2": 0.6},
            "confidence": 0.7,
        },
    }


class ScriptedClient:
    provider = "fixture"

    def decide(self, body):
        return jump_answers(body["state"]), 1.0, None


def test_make_client_and_default_policy(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert default_policy() == "heuristic"
    assert make_client("heuristic").provider == "heuristic"


def test_fake_loop_jumps_with_scripted_client():
    session = FakeDino()
    loop = RunLoop(session, ScriptedClient())
    frames = loop.run(8, stop_on_crash=False)
    assert frames
    assert any(frame["dino"]["jumping"] or frame["last_intent"]["jump"] for frame in frames)
    session.close()


def test_heuristic_fake_loop_ticks():
    session = FakeDino()
    loop = RunLoop(session, HeuristicClient())
    frames = loop.run(12, stop_on_crash=False)
    assert len(frames) == 12
    assert frames[-1]["ticks"] == 12
    assert frames[-1]["last_intent"]["provider"] == "heuristic"
    session.close()


def test_fixture_client_validates_bundle():
    session = FakeDino()
    session.start_run()
    state = session.observe()
    answers = jump_answers(state)
    client = FixtureClient(answers)
    got, latency, usage = client.decide(request_body(state, "jev-latest"))
    assert got["action"]["choice"] == "jump"
    assert latency == 1.0
    assert usage is None
    session.close()
