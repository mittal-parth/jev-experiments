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
    "You see structured runner state, not pixels."
)

JUMP_NOUL = 0.55
DUCK_NOUL = 0.62
ACTION_MIN_CONFIDENCE = 0.28

ACTION_CRITERIA = {
    "run": (
        "Keep running. No obstacle is close enough to need a jump or duck, "
        "or the nearest hazard is a high pterodactyl that clears a standing dino."
    ),
    "jump": (
        "Jump now. A cactus or low pterodactyl is inside the commit window "
        "and the dino is on the ground."
    ),
    "duck": (
        "Duck now. A mid-height pterodactyl would hit a standing dino and "
        "ducking lets it pass overhead."
    ),
}

ACTION_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "Choose the body action for this instant.",
    "look_at": [
        "nearest_obstacle.gap_px",
        "nearest_obstacle.time_to_impact_s",
        "nearest_obstacle.clearance",
        "timing.recommended_action",
        "timing.stand_hit_frame",
        "timing.jump_clears",
        "timing.lead_frames",
        "dino.jumping",
        "dino.ducking",
        "run.speed",
        "run.intro",
    ],
    "rules": [
        "Pick one action. jump_now and duck_now are separate speculative questions.",
        "timing.recommended_action is internat geometry for this frame; match it unless clearance is high.",
        "run if the nearest obstacle is far, already being cleared, or clearance is high.",
        "jump when clearance is ground or low and time_to_impact_s is inside the commit window.",
        "duck only when clearance is mid. Never duck a cactus (clearance ground).",
        "If dino.jumping is true, choose run; the jump is already in the air.",
    ],
}

JUMP_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "Should the dino jump this instant?",
    "assume": (
        "This question is speculative. Answer as if jumping is available. "
        "Code ignores the answer when the dino is already jumping, ducking, "
        "or the nearest obstacle is a high pterodactyl."
    ),
}

JUMP_CRITERIA = {
    "true": (
        "A cactus or low pterodactyl is close enough that waiting another "
        "tick would miss the jump window, and the dino is on the ground."
    ),
    "false": (
        "No jump is needed: the path is clear, the obstacle is still far, "
        "a duck is the right move, or a jump would hit a high bird."
    ),
}

DUCK_INSTRUCTIONS: dict[str, Any] = {
    "goal": GOAL,
    "task": "Should the dino duck this instant?",
    "assume": (
        "Speculative. Code ignores this if the dino is jumping or the "
        "nearest obstacle is a cactus."
    ),
}

DUCK_CRITERIA = {
    "true": (
        "A mid-height pterodactyl is in the duck window. Standing would "
        "collide; ducking lets it pass."
    ),
    "false": "Stay upright. No mid-height bird, or jumping/running is safer.",
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
