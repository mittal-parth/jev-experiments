"""TypeSafe questions and thresholds for one combat tick.

Keep this file as the human-review surface: instructions, option
rubrics, and the probability cutoffs the executor uses.
"""

from __future__ import annotations

from typing import Any

GOAL = (
    "Win this free-for-all as a Krunker Triggerman. Stay alive, take "
    "fights you can win, and get kills. You see only what a player would "
    "see: your body, visible enemies in your field of view, nearby cover, "
    "and recent events. You cannot see through walls."
)

STANCE_MIN_CONFIDENCE = 0.32
FIRE_NOUL = 0.55
FIRE_OFF_CROSSHAIR_NOUL = 0.78
RELOAD_NOUL = 0.62
JUMP_NOUL = 0.80

SCAN_LEFT = "scan_left"
SCAN_RIGHT = "scan_right"
HOLD_AIM = "hold"

STANCE_CRITERIA = {
    "hunt": (
        "Push or take a fight. An enemy is visible or just was, you have "
        "enough health and ammo, and the trade looks winnable."
    ),
    "hold_angle": (
        "Stop pushing. Hold your current yaw or a known peek, waiting for "
        "someone to walk into the crosshair."
    ),
    "retreat": (
        "Break the fight. Health is low, you are caught in the open, or "
        "multiple enemies have an angle on you."
    ),
    "reload_cover": (
        "Magazine is empty or nearly empty and cover is close enough to "
        "reload behind. Do not reload in the open while being aimed at."
    ),
}

MOVE_CRITERIA = {
    "forward": "Move along current yaw. Use when hunting or closing a gap.",
    "back": "Backpedal along current yaw. Use when peeling or reloading.",
    "strafe_left": "Strafe left relative to yaw. Use for peeking or dodging.",
    "strafe_right": "Strafe right relative to yaw. Use for peeking or dodging.",
    "stop": "Hold position. Use when holding an angle or waiting to shoot.",
}

STANCE_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "Choose the combat stance for this instant.",
    "rules": [
        "Pick one stance. Movement, aim, fire, and reload are separate questions.",
        "hunt if you can take a fight now.",
        "hold_angle if waiting is better than swinging.",
        "retreat if staying is likely to get you killed.",
        "reload_cover if ammo is the binding constraint and cover exists.",
    ],
}

MOVE_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "Choose how the body should move this instant, given the situation.",
    "rules": [
        "This question does not choose facing. Aim is a different question.",
        "Strafe while shooting if an enemy is on screen.",
        "Move toward nearby cover when retreating or reloading.",
        "Stop if you are holding a tight angle and already have a shot.",
    ],
}

FIRE_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "Should the player fire a hitscan shot this instant?",
    "assume": (
        "This question is speculative. Answer as if shooting is available. "
        "Code will ignore the answer when the magazine is empty or a reload "
        "is already in progress."
    ),
}

FIRE_CRITERIA = {
    "true": (
        "An enemy is visible, roughly on target, the magazine has ammo, and "
        "shooting now is more valuable than waiting for a cleaner shot."
    ),
    "false": (
        "No useful target, the shot would miss, ammo would be wasted, or "
        "firing would give away a hold for no gain."
    ),
}

RELOAD_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "Should the player start reloading this instant?",
    "assume": (
        "Speculative. Code ignores this if the magazine is full or a reload "
        "is already running."
    ),
}

RELOAD_CRITERIA = {
    "true": "Magazine is low or empty and it is safe enough to reload now.",
    "false": "Keep the current magazine. A fight is active or the mag is fine.",
}

JUMP_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "Should the player jump this instant?",
}

JUMP_CRITERIA = {
    "true": "A jump peek, hop over a ledge, or surprise movement helps right now.",
    "false": "Stay grounded. Jumping would make aim worse or is unnecessary.",
}

THREAT_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "How lethal is the current situation for the player?",
}

THREAT_CRITERIA = [
    "Safe: no visible threat, healthy, good cover or angle.",
    "Contested: a fight is happening but still winnable.",
    "Lethal: about to die unless you break the fight immediately.",
]


def aim_instructions(enemy_ids: list[str]) -> dict[str, Any]:
    return {
        "goal": GOAL,
        "task": (
            "Choose where to look, assuming the next operation is aiming. "
            "Another question decides stance and whether to fire."
        ),
        "operation": "aim",
        "offered_targets": enemy_ids + [SCAN_LEFT, SCAN_RIGHT, HOLD_AIM],
        "rules": [
            "Choose only an offered id.",
            "Prefer the highest-value visible enemy: closer, lower health, "
            "already near the crosshair.",
            "scan_left or scan_right when nobody is visible and you need info.",
            "hold when the current yaw is already a good angle.",
        ],
    }


def aim_criteria(visible_enemies: list[dict[str, Any]]) -> dict[str, Any]:
    criteria: dict[str, Any] = {}
    for enemy in visible_enemies:
        criteria[str(enemy["id"])] = {
            "kind": "visible_enemy",
            "bearing_deg": enemy["bearing_deg"],
            "distance": enemy["distance"],
            "health": enemy["health"],
            "in_crosshair": enemy["in_crosshair"],
            "behind_cover": enemy["behind_cover"],
            "moving": enemy["moving"],
        }
    criteria[SCAN_LEFT] = "No good on-screen target; sweep left to search."
    criteria[SCAN_RIGHT] = "No good on-screen target; sweep right to search."
    criteria[HOLD_AIM] = "Keep the current yaw. Crosshair placement is already fine."
    return criteria


def build_questions(state: dict[str, Any]) -> dict[str, Any]:
    """One request: stance, move, speculative aim/fire/reload/jump, threat."""
    visible = list(state.get("visible_enemies") or [])
    enemy_ids = [str(enemy["id"]) for enemy in visible]
    return {
        "stance": {
            "type": "choice",
            "instructions": STANCE_INSTRUCTIONS,
            "criteria": STANCE_CRITERIA,
        },
        "move": {
            "type": "choice",
            "instructions": MOVE_INSTRUCTIONS,
            "criteria": MOVE_CRITERIA,
        },
        "aim_target": {
            "type": "choice",
            "instructions": aim_instructions(enemy_ids),
            "criteria": aim_criteria(visible),
        },
        "fire": {
            "type": "noul",
            "instructions": FIRE_INSTRUCTIONS,
            "criteria": FIRE_CRITERIA,
        },
        "reload": {
            "type": "noul",
            "instructions": RELOAD_INSTRUCTIONS,
            "criteria": RELOAD_CRITERIA,
        },
        "jump": {
            "type": "noul",
            "instructions": JUMP_INSTRUCTIONS,
            "criteria": JUMP_CRITERIA,
        },
        "threat": {
            "type": "score",
            "instructions": THREAT_INSTRUCTIONS,
            "criteria": THREAT_CRITERIA,
        },
    }
