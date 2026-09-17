import math

import pytest

from dino_jev.client import (
    JevClient,
    has_api_key,
    resolve_api_key,
    validate_answers,
    validate_choice,
    validate_noul,
    validate_score,
)
from dino_jev.loop import default_policy


def test_validate_choice_accepts_peaked_distribution():
    answer = validate_choice(
        {
            "type": "choice",
            "choice": "jump",
            "probabilities": {"jump": 0.7, "run": 0.3},
            "confidence": 0.4,
        },
        {"jump", "run"},
    )
    assert answer["choice"] == "jump"


def test_validate_choice_rejects_unknown_option():
    with pytest.raises(ValueError):
        validate_choice(
            {
                "type": "choice",
                "choice": "spin",
                "probabilities": {"jump": 1.0},
                "confidence": 1.0,
            },
            {"jump"},
        )


def test_validate_noul_rejects_nan():
    with pytest.raises(ValueError):
        validate_noul({"type": "noul", "noul": math.nan})


def test_validate_score_and_bundle():
    questions = {
        "urgency": {"type": "score", "criteria": ["a", "b", "c"]},
        "jump_now": {"type": "noul", "instructions": "x"},
    }
    answers = {
        "urgency": {
            "type": "score",
            "score": 1.2,
            "probabilities": {"0": 0.2, "1": 0.6, "2": 0.2},
            "confidence": 0.5,
        },
        "jump_now": {"type": "noul", "noul": 0.4},
    }
    validate_score(answers["urgency"], 3)
    validate_answers(answers, questions)


def test_missing_key_falls_back_to_heuristic(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert resolve_api_key() == ""
    assert has_api_key() is False
    assert default_policy() == "heuristic"
    with pytest.raises(RuntimeError, match="JEV_API_KEY"):
        JevClient()
