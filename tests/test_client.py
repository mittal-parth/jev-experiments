import math

import pytest

from krunker_jev.client import (
    JevClient,
    has_api_key,
    resolve_api_key,
    validate_answers,
    validate_choice,
    validate_noul,
    validate_score,
)
from krunker_jev.loop import default_policy


def test_validate_choice_accepts_peaked_distribution():
    answer = validate_choice(
        {
            "type": "choice",
            "choice": "hunt",
            "probabilities": {"hunt": 0.7, "retreat": 0.3},
            "confidence": 0.4,
        },
        {"hunt", "retreat"},
    )
    assert answer["choice"] == "hunt"


def test_validate_choice_rejects_unknown_option():
    with pytest.raises(ValueError):
        validate_choice(
            {
                "type": "choice",
                "choice": "dance",
                "probabilities": {"hunt": 1.0},
                "confidence": 1.0,
            },
            {"hunt"},
        )


def test_validate_noul_rejects_nan():
    with pytest.raises(ValueError):
        validate_noul({"type": "noul", "noul": math.nan})


def test_validate_score_and_bundle():
    questions = {
        "threat": {"type": "score", "criteria": ["a", "b", "c"]},
        "fire": {"type": "noul", "instructions": "x"},
    }
    answers = {
        "threat": {
            "type": "score",
            "score": 1.2,
            "probabilities": {"0": 0.2, "1": 0.6, "2": 0.2},
            "confidence": 0.5,
        },
        "fire": {"type": "noul", "noul": 0.4},
    }
    validate_score(answers["threat"], 3)
    validate_answers(answers, questions)


def test_jev_api_key_wins(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "from-jev")
    monkeypatch.setenv("TYPESAFE_API_KEY", "from-typesafe")
    assert resolve_api_key() == "from-jev"
    assert has_api_key() is True
    assert default_policy() == "jev"
    client = JevClient()
    assert client.api_key == "from-jev"
    client.close()


def test_typesafe_api_key_alias(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "from-typesafe")
    assert resolve_api_key() == "from-typesafe"
    assert default_policy() == "jev"


def test_missing_key_falls_back_to_heuristic(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert resolve_api_key() == ""
    assert has_api_key() is False
    assert default_policy() == "heuristic"
    with pytest.raises(RuntimeError, match="JEV_API_KEY"):
        JevClient()

