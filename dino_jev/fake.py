"""In-process dino stand-in so policy tests do not need Chromium."""

from __future__ import annotations

from typing import Any

from dino_jev.policy import Intent, obstacle_clearance
from dino_jev.timing_state import enrich_timing

WIDTH = 600
HEIGHT = 150
GROUND_Y = 93
DINO_X = 50
DINO_W = 44
DINO_H = 47
DUCK_H = 25
SPEED = 6.0
SPAWN_X = 580
SCORE_COEFFICIENT = 0.025


class FakeDino:
    """A cactus that scrolls left. Jumping clears it; standing collides."""

    def __init__(self, *, seed: int = 1, dt: float = 1 / 30) -> None:
        del seed
        self.dt = dt
        self.playing = False
        self.crashed = False
        self.intro = False
        self.distance_ran = 0.0
        self.speed = SPEED
        self.dino_y = GROUND_Y
        self.jumping = False
        self.ducking = False
        self.jump_velocity = 0.0
        self.obstacle_x = SPAWN_X
        self.obstacle_y = 105.0
        self.obstacle_w = 17.0
        self.obstacle_h = 35.0
        self.obstacle_kind = "cactusSmall"
        self.last_intent: Intent | None = None
        self.ticks = 0
        self.run_index = 0
        self.last_score = 0

    def start_run(self) -> None:
        self.playing = True
        self.crashed = False
        self.intro = False
        self.distance_ran = 0.0
        self.speed = SPEED
        self.dino_y = GROUND_Y
        self.jumping = False
        self.ducking = False
        self.jump_velocity = 0.0
        self.obstacle_x = SPAWN_X
        self.last_intent = None
        self.ticks = 0
        self.run_index += 1

    def restart(self) -> None:
        self.start_run()

    def close(self) -> None:
        self.playing = False

    def observe(self) -> dict[str, Any]:
        gap = self.obstacle_x - DINO_X - DINO_W
        px_per_sec = self.speed * 60.0
        time_to_impact = gap / px_per_sec if px_per_sec > 0 else None
        obstacle = {
            "id": "o0",
            "kind": "pterodactyl" if self.obstacle_kind == "pterodactyl" else "cactus",
            "type": self.obstacle_kind,
            "x": round(self.obstacle_x, 1),
            "y": self.obstacle_y,
            "width": self.obstacle_w,
            "height": self.obstacle_h,
            "gap_px": round(gap, 1),
            "time_to_impact_s": None if time_to_impact is None else round(time_to_impact, 3),
            "clearance": obstacle_clearance(
                {"kind": "cactus" if "cactus" in self.obstacle_kind else self.obstacle_kind, "y": self.obstacle_y}
            ),
        }
        score = int(round(self.distance_ran * SCORE_COEFFICIENT))
        observation = {
            "goal": (
                "Survive as long as possible in Chrome's offline dinosaur runner. "
                "Jump cacti and low pterodactyls. Duck mid-height pterodactyls."
            ),
            "run": {
                "playing": self.playing,
                "crashed": self.crashed,
                "intro": self.intro,
                "speed": self.speed,
                "score": score,
                "distance_ran": round(self.distance_ran, 1),
                "speed_cap": None,
            },
            "dino": {
                "x": DINO_X,
                "y": round(self.dino_y, 1),
                "ground_y": GROUND_Y,
                "width": DINO_W,
                "height": DUCK_H if self.ducking else DINO_H,
                "jumping": self.jumping,
                "ducking": self.ducking,
            },
            "nearest_obstacle": None if self.crashed else obstacle,
            "obstacles": [] if self.crashed else [obstacle],
            "last_action": None if self.last_intent is None else self.last_intent.action,
        }
        enrich_timing(observation, lead_frames=8)
        return observation

    def apply(self, intent: Intent) -> None:
        self.last_intent = intent
        if not self.playing or self.crashed:
            return
        if intent.jump and not self.jumping:
            self.jumping = True
            self.ducking = False
            self.jump_velocity = -10.5
        elif intent.duck and not self.jumping:
            self.ducking = True
        else:
            self.ducking = False
        self._step()

    def _step(self) -> None:
        frames = max(1, int(round(self.dt * 60)))
        for _ in range(frames):
            if self.crashed:
                return
            self.distance_ran += self.speed
            self.obstacle_x -= self.speed
            if self.jumping:
                self.dino_y += self.jump_velocity
                self.jump_velocity += 0.6
                if self.dino_y >= GROUND_Y:
                    self.dino_y = GROUND_Y
                    self.jumping = False
                    self.jump_velocity = 0.0
            if self.obstacle_x + self.obstacle_w < 0:
                self.obstacle_x = SPAWN_X
            if self._collides():
                self.crashed = True
                self.playing = False
                self.last_score = int(round(self.distance_ran * SCORE_COEFFICIENT))
            self.ticks += 1

    def _collides(self) -> bool:
        dino_h = DUCK_H if self.ducking else DINO_H
        dino_top = self.dino_y
        dino_bottom = self.dino_y + dino_h
        dino_left = DINO_X
        dino_right = DINO_X + DINO_W
        obs_top = self.obstacle_y
        obs_bottom = self.obstacle_y + self.obstacle_h
        obs_left = self.obstacle_x
        obs_right = self.obstacle_x + self.obstacle_w
        overlap_x = dino_left < obs_right and dino_right > obs_left
        overlap_y = dino_top < obs_bottom and dino_bottom > obs_top
        return overlap_x and overlap_y

    def screenshot_png(self) -> bytes | None:
        return None
