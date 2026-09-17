"""Structured timing hints derived from internat geometry (not pixels)."""

from __future__ import annotations

from typing import Any

from dino_jev.physics import (
    DINO_DUCK_H,
    DINO_DUCK_W,
    DINO_H,
    DINO_W,
    GROUND_Y,
    decide_action,
    first_hit_frame,
    jump_clears,
    _obstacles,
)
from dino_jev.policy import obstacle_clearance


def enrich_timing(state: dict[str, Any], *, lead_frames: int) -> None:
    run = state.get("run") or {}
    dino = state.get("dino") or {}
    if run.get("crashed") or run.get("intro") or dino.get("jumping"):
        state["timing"] = {
            "lead_frames": lead_frames,
            "recommended_action": "run",
            "stand_hit_frame": None,
            "jump_clears": True,
            "clearance": obstacle_clearance(
                state.get("nearest_obstacle") if isinstance(state.get("nearest_obstacle"), dict) else None
            ),
        }
        return

    obstacles = _obstacles(state)
    speed = float(run.get("speed") or 6.0)
    dino_x = float(dino.get("x") or 50.0)
    ground_y = float(dino.get("ground_y") or GROUND_Y)
    nearest = state.get("nearest_obstacle")
    clearance = obstacle_clearance(nearest if isinstance(nearest, dict) else None)
    recommended = decide_action(state, lead_frames=lead_frames)

    stand_hit = None
    duck_hit = None
    clears = True
    if obstacles and clearance == "ground":
        stand_hit = first_hit_frame(
            obstacles,
            speed=speed,
            dino_x=dino_x,
            dino_y=ground_y,
            dino_w=DINO_W,
            dino_h=DINO_H,
            max_frames=55,
        )
        clears = jump_clears(obstacles, speed=speed, dino_x=dino_x, ground_y=ground_y)
    elif obstacles and clearance == "mid":
        stand_hit = first_hit_frame(
            obstacles,
            speed=speed,
            dino_x=dino_x,
            dino_y=ground_y,
            dino_w=DINO_W,
            dino_h=DINO_H,
            max_frames=18,
        )
        duck_hit = first_hit_frame(
            obstacles,
            speed=speed,
            dino_x=dino_x,
            dino_y=ground_y + (DINO_H - DINO_DUCK_H),
            dino_w=DINO_DUCK_W,
            dino_h=DINO_DUCK_H,
            max_frames=12,
        )

    state["timing"] = {
        "lead_frames": lead_frames,
        "recommended_action": recommended,
        "stand_hit_frame": stand_hit,
        "duck_hit_frame": duck_hit,
        "jump_clears": clears,
        "clearance": clearance,
    }
