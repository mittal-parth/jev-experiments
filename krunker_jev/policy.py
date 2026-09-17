"""Turn TypeSafe answers into an executable combat intent.

Code owns gating: empty magazines cannot fire, full magazines cannot
reload, and low-confidence stance choices keep the previous stance.
"""

from __future__ import annotations

from typing import Any

from krunker_jev.questions import (
    FIRE_NOUL,
    FIRE_OFF_CROSSHAIR_NOUL,
    HOLD_AIM,
    JUMP_NOUL,
    RELOAD_NOUL,
    STANCE_MIN_CONFIDENCE,
    build_questions,
)
from krunker_jev.world import MAG_SIZE, Intent

STANCES = ("hunt", "hold_angle", "retreat", "reload_cover")
MOVES = ("forward", "back", "strafe_left", "strafe_right", "stop")


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


def _visible_ids(state: dict[str, Any]) -> set[str]:
    return {str(enemy["id"]) for enemy in state.get("visible_enemies") or []}


def _on_crosshair(state: dict[str, Any], aim: str) -> bool:
    for enemy in state.get("visible_enemies") or []:
        if str(enemy["id"]) == aim:
            return bool(enemy.get("in_crosshair"))
    return False


def compose_intent(
    answers: dict[str, Any],
    state: dict[str, Any],
    *,
    provider: str,
    latency_ms: float,
    previous: Intent | None = None,
) -> Intent:
    stance_answer = _choice(answers, "stance")
    move_answer = _choice(answers, "move")
    aim_answer = _choice(answers, "aim_target")
    stance = str(stance_answer["choice"])
    move = str(move_answer["choice"])
    aim = str(aim_answer["choice"])
    if stance not in STANCES:
        raise ValueError(f"invalid stance: {stance}")
    if move not in MOVES:
        raise ValueError(f"invalid move: {move}")

    offered = _visible_ids(state) | {HOLD_AIM, "scan_left", "scan_right"}
    if aim not in offered:
        aim = HOLD_AIM

    stance_conf = float(stance_answer.get("confidence") or 0.0)
    if stance_conf < STANCE_MIN_CONFIDENCE and previous is not None:
        stance = previous.stance

    body = state.get("self") or {}
    mag = int(body.get("ammo_in_mag") or 0)
    reserve = int(body.get("reserve_ammo") or 0)
    reloading = bool(body.get("reloading"))
    alive = body.get("alive", True)

    fire_p = _noul(answers, "fire")
    reload_p = _noul(answers, "reload")
    jump_p = _noul(answers, "jump")
    threat = _score(answers, "threat")

    fire_needed = FIRE_NOUL
    if not _on_crosshair(state, aim):
        fire_needed = FIRE_OFF_CROSSHAIR_NOUL
    fire = (
        alive
        and not reloading
        and mag > 0
        and fire_p >= fire_needed
        and aim in _visible_ids(state)
        and stance != "reload_cover"
    )
    reload = (
        alive
        and not reloading
        and mag < MAG_SIZE
        and reserve > 0
        and reload_p >= RELOAD_NOUL
        and not fire
    )
    jump = alive and jump_p >= JUMP_NOUL

    return Intent(
        stance=stance,
        move=move,
        aim=aim,
        fire=fire,
        reload=reload,
        jump=jump,
        threat=threat,
        confidence={
            "stance": stance_conf,
            "move": float(move_answer.get("confidence") or 0.0),
            "aim_target": float(aim_answer.get("confidence") or 0.0),
        },
        probabilities={
            "stance": dict(stance_answer.get("probabilities") or {}),
            "move": dict(move_answer.get("probabilities") or {}),
            "aim_target": dict(aim_answer.get("probabilities") or {}),
        },
        nouls={"fire": fire_p, "reload": reload_p, "jump": jump_p},
        latency_ms=latency_ms,
        provider=provider,
        raw=answers,
    )
