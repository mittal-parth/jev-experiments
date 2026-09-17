"""TypeSafe questions and thresholds for one Chrome Dino tick.

Keep this file as the human-review surface: instructions, option
rubrics, and the probability cutoffs the executor uses.
"""

from __future__ import annotations

from typing import Any

GOAL = (
    "Survive as long as possible in Chrome's offline dinosaur runner. "
    "The dino runs right automatically. You only jump or duck. Jump "
    "cacti and low pterodactyls. Duck mid-height pterodactyls. High "
    "pterodactyls fly over a standing dino — do not jump into them. "
    "You see structured runner state, not pixels. Code times the actual "
    "key press on the page after your answer; you are arming the next "
    "move for the nearest obstacle, not pressing instantly."
)

JUMP_NOUL = 0.55
DUCK_NOUL = 0.62
ACTION_MIN_CONFIDENCE = 0.28

ACTION_CRITERIA = {
    "run": (
        "Keep running. No obstacle needs an armed jump or duck, or the "
        "nearest hazard is a high pterodactyl that clears a standing dino."
    ),
    "jump": (
        "Arm a jump for the nearest cactus or low pterodactyl. Code will "
        "press jump when live gap reaches the runner commit window."
    ),
    "duck": (
        "Arm a duck for the nearest mid-height pterodactyl. Code will duck "
        "when live gap reaches the duck window."
    ),
}

ACTION_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "Choose how to handle the nearest obstacle this tick.",
    "look_at": [
        "nearest_obstacle.gap_px",
        "nearest_obstacle.time_to_impact_s",
        "nearest_obstacle.clearance",
        "nearest_obstacle.id",
        "dino.jumping",
        "dino.ducking",
        "run.speed",
        "run.intro",
        "last_latency_ms",
    ],
    "rules": [
        "Pick one action. jump_now and duck_now are separate speculative questions.",
        "run if the nearest obstacle is far, already being cleared, or clearance is high.",
        "jump when clearance is ground or low and this obstacle should be cleared with a hop.",
        "duck only when clearance is mid. Never duck a cactus (clearance ground).",
        "If dino.jumping is true, choose run; the jump is already in the air.",
        "You may arm early; the page executor waits for the correct live gap.",
    ],
}

JUMP_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "Should we arm a jump for the nearest obstacle?",
    "assume": (
        "This question is speculative. Answer as if jumping can be armed. "
        "Code ignores the answer when the dino is already jumping, ducking, "
        "or the nearest obstacle is a high pterodactyl."
    ),
}

JUMP_CRITERIA = {
    "true": (
        "The nearest cactus or low pterodactyl should be cleared with a jump; "
        "arming now is appropriate even if the live gap is still wide."
    ),
    "false": (
        "Do not arm a jump: the path is clear, duck is correct, or a jump "
        "would hit a high bird."
    ),
}

DUCK_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "Should we arm a duck for the nearest obstacle?",
    "assume": (
        "Speculative. Code ignores this if the dino is jumping or the "
        "nearest obstacle is a cactus."
    ),
}

DUCK_CRITERIA = {
    "true": (
        "The nearest mid-height pterodactyl should be passed by ducking; "
        "arming now is appropriate."
    ),
    "false": "Do not arm a duck: no mid-height bird, or jumping/running is safer.",
}

URGENCY_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "How soon must the dino commit to jump or duck?",
}

URGENCY_CRITERIA = [
    "Plenty of time: gap is large or there is no obstacle.",
    "Commit window: the next hazard is close; act this tick or the next.",
    "Too late: a collision is likely unless already clearing the hazard.",
]


def build_questions(state: dict[str, Any]) -> dict[str, Any]:
    """One request: action plus speculative jump/duck and an urgency score."""
    _ = state
    return {
        "action": {
            "type": "choice",
            "instructions": ACTION_INSTRUCTIONS,
            "criteria": ACTION_CRITERIA,
        },
        "jump_now": {
            "type": "noul",
            "instructions": JUMP_INSTRUCTIONS,
            "criteria": JUMP_CRITERIA,
        },
        "duck_now": {
            "type": "noul",
            "instructions": DUCK_INSTRUCTIONS,
            "criteria": DUCK_CRITERIA,
        },
        "urgency": {
            "type": "score",
            "instructions": URGENCY_INSTRUCTIONS,
            "criteria": URGENCY_CRITERIA,
        },
    }
