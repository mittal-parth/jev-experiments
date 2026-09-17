"""Run recording, failure taxonomy, and Jev usage rollups."""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dino_jev.physics import decide_action, first_hit_frame, jump_clears
from dino_jev.policy import obstacle_clearance
from dino_jev.physics import DINO_H, DINO_W, GROUND_Y, _obstacles


@dataclass
class UsageTotals:
    api_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    fallback_calls: int = 0
    latency_ms: list[float] = field(default_factory=list)

    def add(self, *, latency_ms: float, usage: dict[str, Any] | None) -> None:
        self.api_calls += 1
        self.latency_ms.append(latency_ms)
        if usage and usage.get("fallback"):
            self.fallback_calls += 1
            return
        if usage:
            self.input_tokens += int(usage.get("input_tokens") or 0)
            self.output_tokens += int(usage.get("output_tokens") or 0)

    def summary(self) -> dict[str, Any]:
        lat = self.latency_ms
        return {
            "api_calls": self.api_calls,
            "fallback_calls": self.fallback_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "latency_ms_avg": round(statistics.mean(lat), 1) if lat else None,
            "latency_ms_p50": round(statistics.median(lat), 1) if lat else None,
            "latency_ms_p95": round(sorted(lat)[int(len(lat) * 0.95) - 1], 1) if len(lat) > 1 else (round(lat[0], 1) if lat else None),
        }


def _physics_want(state: dict[str, Any], lead_frames: int) -> str:
    return decide_action(state, lead_frames=lead_frames)


def classify_timing(
    state: dict[str, Any],
    *,
    asked: str,
    executed: str,
    gated: bool,
    lead_frames: int,
) -> str | None:
    """Why Jev timing diverged from internat geometry (when both are grounded)."""
    run = state.get("run") or {}
    dino = state.get("dino") or {}
    if run.get("crashed") or run.get("intro") or dino.get("jumping"):
        return None
    optimal = _physics_want(state, lead_frames)
    if gated and asked != executed:
        return f"gated_{asked}_to_{executed}"
    if executed == "jump" and optimal == "run":
        obstacles = _obstacles(state)
        if not obstacles:
            return "jump_no_obstacle"
        speed = float(run.get("speed") or 6.0)
        dino_x = float(dino.get("x") or 50.0)
        ground_y = float(dino.get("ground_y") or GROUND_Y)
        stand_hit = first_hit_frame(
            obstacles,
            speed=speed,
            dino_x=dino_x,
            dino_y=ground_y,
            dino_w=DINO_W,
            dino_h=DINO_H,
            max_frames=55,
        )
        if stand_hit is None:
            return "jump_early_no_hit_scheduled"
        if stand_hit > lead_frames + 4:
            return "jump_early_stand_hit_far"
        if not jump_clears(obstacles, speed=speed, dino_x=dino_x, ground_y=ground_y):
            return "jump_into_obstacle"
        return "jump_early_other"
    if executed == "run" and optimal == "jump":
        return "jump_late_or_missed"
    if executed == "run" and optimal == "duck":
        nearest = state.get("nearest_obstacle")
        clearance = obstacle_clearance(nearest if isinstance(nearest, dict) else None)
        if clearance == "mid":
            return "duck_late_or_missed"
    if executed == "duck" and optimal != "duck":
        return "duck_unneeded_or_wrong"
    if asked != executed and not gated:
        return f"executor_{asked}_to_{executed}"
    return None


@dataclass
class RunRecorder:
    path: Path | None = None
    lead_frames: int = 8
    usage: UsageTotals = field(default_factory=UsageTotals)
    failure_counts: dict[str, int] = field(default_factory=dict)
    timing_counts: dict[str, int] = field(default_factory=dict)
    max_score: int = 0
    started_at: float = field(default_factory=time.perf_counter)
    _file: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("w", encoding="utf-8")

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def record_tick(
        self,
        frame: dict[str, Any],
        *,
        usage: dict[str, Any] | None = None,
    ) -> None:
        intent = frame.get("last_intent") or {}
        latency = float(intent.get("latency_ms") or 0.0)
        if intent.get("provider") == "jev":
            self.usage.add(latency_ms=latency, usage=usage)

        run = frame.get("run") or {}
        score = int(run.get("score") or 0)
        self.max_score = max(self.max_score, score)

        asked = str(intent.get("asked") or intent.get("action") or "run")
        executed = str(intent.get("action") or "run")
        gated = bool(intent.get("gated"))
        reason = classify_timing(
            frame,
            asked=asked,
            executed=executed,
            gated=gated,
            lead_frames=self.lead_frames,
        )
        if reason:
            self.timing_counts[reason] = self.timing_counts.get(reason, 0) + 1

        if run.get("crashed"):
            crash_reason = reason or "crash_no_timing_tag"
            self.failure_counts[crash_reason] = self.failure_counts.get(crash_reason, 0) + 1

        if self._file is None:
            return
        row = {
            "t": round(time.perf_counter() - self.started_at, 3),
            "score": score,
            "speed": run.get("speed"),
            "crashed": run.get("crashed"),
            "intent": intent,
            "nearest": frame.get("nearest_obstacle"),
            "timing": reason,
            "usage": usage,
        }
        self._file.write(json.dumps(row, separators=(",", ":")) + "\n")
        self._file.flush()

    def report(self, *, score: int | None, crashed: bool, ticks: int, elapsed_s: float) -> dict[str, Any]:
        return {
            "score": score,
            "max_score": self.max_score,
            "crashed": crashed,
            "ticks": ticks,
            "elapsed_s": round(elapsed_s, 2),
            "lead_frames": self.lead_frames,
            "jev": self.usage.summary(),
            "timing_missteps": dict(sorted(self.timing_counts.items(), key=lambda item: -item[1])),
            "crash_tags": dict(sorted(self.failure_counts.items(), key=lambda item: -item[1])),
        }
