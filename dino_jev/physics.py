"""Internat jump/duck from Runner boxes — not pixels and not a Python tick.

The Chrome page runs the same geometry on the internat update() loop.
This module is the testable copy used by the heuristic answers.
"""

from __future__ import annotations

import math
from typing import Any

from dino_jev.policy import obstacle_clearance

GRAVITY = 0.6
INITIAL_JUMP_VELOCITY = -10.0
DROP_VELOCITY = -5.0
MAX_JUMP_HEIGHT_Y = 30.0
DINO_W = 44.0
DINO_H = 47.0
DINO_DUCK_W = 59.0
DINO_DUCK_H = 25.0
GROUND_Y = 93.0
LEAD_FRAMES = 8  # internat frames before impact; lower = later jump (clusters)
STAND_HORIZON = 55
JUMP_HORIZON = 80


def js_round(value: float) -> int:
    """Match Math.round (half toward +inf)."""
    return int(math.floor(value + 0.5))


def _boxes_overlap(
    ax: float, ay: float, aw: float, ah: float, bx: float, by: float, bw: float, bh: float
) -> bool:
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def _hit(
    dino_x: float,
    dino_y: float,
    dino_w: float,
    dino_h: float,
    obs_x: float,
    obs_y: float,
    obs_w: float,
    obs_h: float,
) -> bool:
    return _boxes_overlap(
        dino_x + 1,
        dino_y + 1,
        max(1.0, dino_w - 2),
        max(1.0, dino_h - 2),
        obs_x + 1,
        obs_y + 1,
        max(1.0, obs_w - 2),
        max(1.0, obs_h - 2),
    )


def _obstacles(state: dict[str, Any]) -> list[dict[str, Any]]:
    packed = [dict(item) for item in (state.get("obstacles") or []) if item]
    nearest = state.get("nearest_obstacle")
    if nearest and not packed:
        packed = [dict(nearest)]
    out = []
    for item in packed:
        width = float(item.get("width") or 0)
        if width <= 0:
            continue
        item["x"] = float(item.get("x") or 0)
        item["y"] = float(item.get("y") or 105)
        item["width"] = width
        item["height"] = float(item.get("height") or 35)
        out.append(item)
    return out


def jump_ys(speed: float, ground_y: float, n: int) -> list[float]:
    velocity = INITIAL_JUMP_VELOCITY - speed / 10.0
    y = ground_y
    landed = False
    positions: list[float] = []
    for _ in range(n):
        if landed:
            positions.append(ground_y)
            continue
        y = y + js_round(velocity)
        velocity += GRAVITY
        if y < MAX_JUMP_HEIGHT_Y and velocity < DROP_VELOCITY:
            velocity = DROP_VELOCITY
        if y > ground_y:
            y = ground_y
            landed = True
        positions.append(y)
    return positions


def first_hit_frame(
    obstacles: list[dict[str, Any]],
    *,
    speed: float,
    dino_x: float,
    dino_y: float,
    dino_w: float,
    dino_h: float,
    max_frames: int,
) -> int | None:
    for frame in range(1, max_frames + 1):
        for obs in obstacles:
            ox = obs["x"] - speed * frame
            if ox + obs["width"] < dino_x:
                continue
            if _hit(dino_x, dino_y, dino_w, dino_h, ox, obs["y"], obs["width"], obs["height"]):
                return frame
    return None


def jump_clears(
    obstacles: list[dict[str, Any]],
    *,
    speed: float,
    dino_x: float,
    ground_y: float,
) -> bool:
    ys = jump_ys(speed, ground_y, JUMP_HORIZON)
    for frame, y in enumerate(ys, start=1):
        past_all = True
        for obs in obstacles:
            ox = obs["x"] - speed * frame
            if ox + obs["width"] >= dino_x:
                past_all = False
            if _hit(dino_x, y, DINO_W, DINO_H, ox, obs["y"], obs["width"], obs["height"]):
                return False
        if past_all:
            return True
    return True


def _duck_box_hits_now(
    obstacles: list[dict[str, Any]],
    *,
    dino_x: float,
    ground_y: float,
) -> bool:
    duck_y = ground_y + (DINO_H - DINO_DUCK_H)
    for obs in obstacles:
        if _hit(
            dino_x,
            duck_y,
            DINO_DUCK_W,
            DINO_DUCK_H,
            obs["x"],
            obs["y"],
            obs["width"],
            obs["height"],
        ):
            return True
    return False


def _mid_bird_blocking(obstacle: dict[str, Any], dino_x: float, dino_w: float = DINO_W) -> bool:
    return float(obstacle["x"]) + float(obstacle["width"]) >= dino_x + dino_w - 4


def _duck_clears_mid(
    obstacles: list[dict[str, Any]],
    *,
    speed: float,
    dino_x: float,
    ground_y: float,
) -> bool:
    duck_y = ground_y + (DINO_H - DINO_DUCK_H)
    return (
        first_hit_frame(
            obstacles,
            speed=speed,
            dino_x=dino_x,
            dino_y=duck_y,
            dino_w=DINO_DUCK_W,
            dino_h=DINO_DUCK_H,
            max_frames=24,
        )
        is None
    )


def decide_action(state: dict[str, Any], *, lead_frames: int = LEAD_FRAMES) -> str:
    """Return run / jump / duck from internat collision geometry."""
    run = state.get("run") or {}
    dino = state.get("dino") or {}
    if run.get("crashed") or dino.get("jumping") or run.get("intro"):
        return "run"
    obstacles = _obstacles(state)
    speed = float(run.get("speed") or 6.0)
    dino_x = float(dino.get("x") or 50.0)
    ground_y = float(dino.get("ground_y") or GROUND_Y)
    ducking = bool(dino.get("ducking"))
    if ducking:
        if obstacles and obstacle_clearance(obstacles[0]) == "mid":
            dino_w = float(dino.get("width") or DINO_W)
            if _mid_bird_blocking(obstacles[0], dino_x, dino_w):
                return "duck"
        return "run"
    if not obstacles:
        return "run"
    clearance = obstacle_clearance(obstacles[0])
    if clearance == "high" or clearance == "clear":
        return "run"
    if clearance == "mid":
        horizon = max(22, int(round(lead_frames + speed * 0.35)))
        stand = first_hit_frame(
            obstacles,
            speed=speed,
            dino_x=dino_x,
            dino_y=ground_y,
            dino_w=DINO_W,
            dino_h=DINO_H,
            max_frames=horizon,
        )
        close_enough = stand is not None and stand <= lead_frames
        if (
            close_enough
            and not _duck_box_hits_now(obstacles, dino_x=dino_x, ground_y=ground_y)
            and _duck_clears_mid(obstacles, speed=speed, dino_x=dino_x, ground_y=ground_y)
        ):
            return "duck"
        return "run"
    stand_hit = first_hit_frame(
        obstacles,
        speed=speed,
        dino_x=dino_x,
        dino_y=ground_y,
        dino_w=DINO_W,
        dino_h=DINO_H,
        max_frames=STAND_HORIZON,
    )
    if stand_hit is None:
        return "run"
    delayed = [{**obs, "x": obs["x"] - speed} for obs in obstacles]
    clears_now = jump_clears(obstacles, speed=speed, dino_x=dino_x, ground_y=ground_y)
    if clears_now:
        clears_next = jump_clears(delayed, speed=speed, dino_x=dino_x, ground_y=ground_y)
        if stand_hit <= lead_frames or not clears_next:
            return "jump"
        return "run"
    if stand_hit <= 2:
        return "jump"
    return "run"
