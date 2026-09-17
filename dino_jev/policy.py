"""Turn TypeSafe answers into an executable dino intent.

Code owns gating: no mid-air jumps, no ducking cacti, and a
low-confidence action keeps the previous one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dino_jev.questions import (
    ACTION_MIN_CONFIDENCE,
    DUCK_NOUL,
    JUMP_NOUL,
    build_questions,
)

ACTIONS = ("run", "jump", "duck")
HIGH_BIRD_Y = 50
MID_BIRD_Y = 75


@dataclass
class Intent:
    action: str
    jump: bool
    duck: bool
    urgency: float
    confidence: dict[str, float]
    probabilities: dict[str, dict[str, float]]
    nouls: dict[str, float]
    latency_ms: float
    provider: str
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "jump": self.jump,
            "duck": self.duck,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "probabilities": self.probabilities,
            "nouls": self.nouls,
            "latency_ms": self.latency_ms,
            "provider": self.provider,
        }


def request_body(state: dict[str, Any], model: str) -> dict[str, Any]:
    return {
        "model": model,
        "state": state,
        "questions": build_questions(state),
    }


def _choice(answers: dict[str, Any], key: str) -> dict[str, Any]:
    answer = answers.get(key) or {}
    if answer.get("type") != "choice":
        raise ValueError(f"{key} is not a choice answer")
    return answer


def _noul(answers: dict[str, Any], key: str) -> float:
    answer = answers.get(key) or {}
    if answer.get("type") != "noul":
        raise ValueError(f"{key} is not a noul answer")
    value = float(answer["noul"])
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{key} noul out of range")
    return value


def _score(answers: dict[str, Any], key: str) -> float:
    answer = answers.get(key) or {}
    if answer.get("type") != "score":
        raise ValueError(f"{key} is not a score answer")
    return float(answer["score"])


def obstacle_clearance(obstacle: dict[str, Any] | None) -> str:
    if not obstacle:
        return "clear"
    kind = str(obstacle.get("kind") or "")
    y_pos = float(obstacle.get("y") or 0)
    if kind == "pterodactyl":
        if y_pos <= HIGH_BIRD_Y + 1:
            return "high"
        if y_pos <= MID_BIRD_Y + 1:
            return "mid"
        return "low"
    if kind == "collectable":
        return "clear"
    return "ground"


def compose_intent(
    answers: dict[str, Any],
    state: dict[str, Any],
    *,
    provider: str,
    latency_ms: float,
    previous: Intent | None = None,
) -> Intent:
    action_answer = _choice(answers, "action")
    action = str(action_answer["choice"])
    if action not in ACTIONS:
        raise ValueError(f"invalid action: {action}")

    action_conf = float(action_answer.get("confidence") or 0.0)
    if action_conf < ACTION_MIN_CONFIDENCE and previous is not None:
        action = previous.action

    run = state.get("run") or {}
    dino = state.get("dino") or {}
    nearest = state.get("nearest_obstacle")
    clearance = obstacle_clearance(nearest if isinstance(nearest, dict) else None)

    playing = bool(run.get("playing")) and not bool(run.get("crashed"))
    jumping = bool(dino.get("jumping"))
    grounded = playing and not jumping
    intro = bool(run.get("intro"))

    jump_p = _noul(answers, "jump_now")
    duck_p = _noul(answers, "duck_now")
    urgency = _score(answers, "urgency")

    want_jump = action == "jump" or jump_p >= JUMP_NOUL
    want_duck = action == "duck" or duck_p >= DUCK_NOUL

    jump = (
        playing
        and not intro
        and grounded
        and want_jump
        and clearance in {"ground", "low"}
    )
    duck = (
        playing
        and not intro
        and grounded
        and not jump
        and want_duck
        and clearance == "mid"
    )
    if jump:
        action = "jump"
    elif duck:
        action = "duck"
    else:
        action = "run"

    return Intent(
        action=action,
        jump=jump,
        duck=duck,
        urgency=urgency,
        confidence={"action": action_conf},
        probabilities={"action": dict(action_answer.get("probabilities") or {})},
        nouls={"jump_now": jump_p, "duck_now": duck_p},
        latency_ms=latency_ms,
        provider=provider,
        raw=answers,
    )
