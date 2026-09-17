"""Deterministic fallback that shares Jev's action space.

Used for tests and for the inspector when JEV_API_KEY / TYPESAFE_API_KEY is absent.
Labeled as provider=heuristic so it cannot be mistaken for Jev.
"""

from __future__ import annotations

from typing import Any

from krunker_jev.client import validate_answers
from krunker_jev.questions import HOLD_AIM, SCAN_LEFT, SCAN_RIGHT, build_questions
from krunker_jev.world import MAG_SIZE


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
    levels = [0.0, 1.0, 2.0]
    # Triangular mass around the weighted score so the inspector has a distribution.
    masses = []
    for level in levels:
        masses.append(max(0.05, 1.4 - abs(value - level)))
    total = sum(masses)
    probabilities = {str(index): masses[index] / total for index in range(3)}
    return {
        "type": "score",
        "score": value,
        "legend": {
            "0": "Safe: no visible threat, healthy, good cover or angle.",
            "1": "Contested: a fight is happening but still winnable.",
            "2": "Lethal: about to die unless you break the fight immediately.",
        },
        "probabilities": probabilities,
        "confidence": 0.62,
    }


def heuristic_answers(state: dict[str, Any]) -> dict[str, Any]:
    body = state.get("self") or {}
    visible = list(state.get("visible_enemies") or [])
    cover = list(state.get("nearby_cover") or [])
    health = int(body.get("health") or 0)
    mag = int(body.get("ammo_in_mag") or 0)
    reserve = int(body.get("reserve_ammo") or 0)
    reloading = bool(body.get("reloading"))
    alive = bool(body.get("alive", True))

    best = visible[0] if visible else None
    low_health = health <= 34
    dry = mag <= 2
    can_reload = mag < MAG_SIZE and reserve > 0 and not reloading

    if not alive:
        stance = "hold_angle"
    elif dry and cover and not (best and best["in_crosshair"] and mag > 0):
        stance = "reload_cover"
    elif low_health and (len(visible) >= 2 or (best and best["distance"] < 6)):
        stance = "retreat"
    elif best:
        stance = "hunt"
    else:
        stance = "hold_angle"

    if stance == "retreat":
        move = "back" if not cover else ("strafe_left" if cover[0]["bearing_deg"] < 0 else "strafe_right")
    elif stance == "reload_cover":
        move = "stop" if body.get("behind_cover") else "back"
    elif stance == "hunt" and best:
        if best["in_crosshair"] and best["distance"] < 10:
            move = "strafe_right"
        elif best["distance"] > 9:
            move = "forward"
        else:
            move = "strafe_left"
    else:
        move = "stop"

    aim_options = [str(enemy["id"]) for enemy in visible] + [SCAN_LEFT, SCAN_RIGHT, HOLD_AIM]
    if best:
        aim = str(best["id"])
    elif stance == "hold_angle":
        aim = HOLD_AIM
    else:
        aim = SCAN_LEFT

    fire = 0.08
    if best and mag > 0 and not reloading:
        fire = 0.93 if best["in_crosshair"] else 0.61 if abs(best["bearing_deg"]) < 12 else 0.22
    reload = 0.12
    if can_reload and (dry or (mag < 8 and not visible)):
        reload = 0.88 if body.get("behind_cover") or not visible else 0.45
    jump = 0.12 if stance == "hunt" and best and best["distance"] < 4 else 0.05

    threat = 0.2
    if best:
        threat = 1.1
    if low_health and visible:
        threat = 1.85
    if len(visible) >= 2:
        threat = max(threat, 1.6)

    answers = {
        "stance": _choice(stance, ["hunt", "hold_angle", "retreat", "reload_cover"]),
        "move": _choice(move, ["forward", "back", "strafe_left", "strafe_right", "stop"]),
        "aim_target": _choice(aim, aim_options, 0.8 if best else 0.55),
        "fire": _noul(fire),
        "reload": _noul(reload),
        "jump": _noul(jump),
        "threat": _score(threat),
    }
    return validate_answers(answers, build_questions(state))


class HeuristicClient:
    provider = "heuristic"

    def decide(self, body: dict[str, Any]) -> tuple[dict[str, Any], float]:
        return heuristic_answers(body["state"]), 0.4
