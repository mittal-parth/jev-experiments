"""Deterministic fallback that shares Jev's action space.

Used for tests and when JEV_API_KEY / TYPESAFE_API_KEY is absent.
Labeled as provider=heuristic so it cannot be mistaken for Jev.
"""

from __future__ import annotations

from typing import Any

from dino_jev.client import validate_answers
from dino_jev.physics import decide_action
from dino_jev.questions import build_questions

URGENCY_LEGEND = {
    "0": "Plenty of time: gap is large or there is no obstacle.",
    "1": "Commit window: the next hazard is close; act this tick or the next.",
    "2": "Too late: a collision is likely unless already clearing the hazard.",
}


def _peaked(winner: str, options: list[str], peak: float = 0.74) -> dict[str, float]:
    if winner not in options:
        winner = options[0]
    if len(options) == 1:
        return {winner: 1.0}
    rest = (1.0 - peak) / (len(options) - 1)
    probs = {option: (peak if option == winner else rest) for option in options}
    total = sum(probs.values())
    return {key: value / total for key, value in probs.items()}


def _choice(winner: str, options: list[str], peak: float = 0.74) -> dict[str, Any]:
    probabilities = _peaked(winner, options, peak)
    return {
        "type": "choice",
        "choice": winner,
        "probabilities": probabilities,
        "confidence": round(peak, 3),
    }


def _noul(value: float) -> dict[str, Any]:
    return {"type": "noul", "noul": round(min(1.0, max(0.0, value)), 3)}


def _score(value: float) -> dict[str, Any]:
    masses = [max(0.05, 1.4 - abs(value - level)) for level in (0.0, 1.0, 2.0)]
    total = sum(masses)
    probabilities = {str(index): masses[index] / total for index in range(3)}
    return {
        "type": "score",
        "score": value,
        "legend": URGENCY_LEGEND,
        "probabilities": probabilities,
        "confidence": 0.62,
    }


def heuristic_answers(state: dict[str, Any]) -> dict[str, Any]:
    dino = state.get("dino") or {}
    nearest = state.get("nearest_obstacle")
    obstacle = nearest if isinstance(nearest, dict) else None
    gap = float(obstacle["gap_px"]) if obstacle else 10_000.0
    jumping = bool(dino.get("jumping"))
    action = decide_action(state)
    close = action in {"jump", "duck"}
    very_close = bool(obstacle) and gap < 50.0

    if action == "duck":
        jump = 0.08
        duck = 0.9
        urgency = 1.35 if very_close else 1.05
    elif action == "jump":
        jump = 0.92
        duck = 0.06
        urgency = 1.4 if very_close else 1.1
    else:
        jump = 0.08
        duck = 0.05
        urgency = 0.15 if not obstacle else 0.45

    if jumping:
        urgency = max(urgency, 1.0)

    answers = {
        "action": _choice(action, ["run", "jump", "duck"], 0.82 if close else 0.7),
        "jump_now": _noul(jump),
        "duck_now": _noul(duck),
        "urgency": _score(urgency),
    }
    return validate_answers(answers, build_questions(state))


class HeuristicClient:
    provider = "heuristic"

    def decide(self, body: dict[str, Any]) -> tuple[dict[str, Any], float]:
        return heuristic_answers(body["state"]), 0.4
