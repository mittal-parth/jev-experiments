"""Observe chrome://dino/ → one System One request → execute keys."""

from __future__ import annotations

import os
import time
from typing import Any, Protocol

from dino_jev.client import DecisionClient, JevClient, has_api_key
from dino_jev.heuristic import HeuristicClient
from dino_jev.policy import Intent, compose_intent, request_body
from dino_jev.telemetry import RunRecorder

DEFAULT_DT = 1 / 30
HEURISTIC_CHROME_DT = 0.25
JEV_CHROME_DT = 0.0


class DinoSession(Protocol):
    last_intent: Intent | None

    def observe(self) -> dict[str, Any]:
        ...

    def apply(self, intent: Intent) -> None:
        ...

    def start_run(self) -> None:
        ...

    def restart(self) -> None:
        ...

    def close(self) -> None:
        ...

    def screenshot_png(self) -> bytes | None:
        ...


def make_client(policy: str) -> DecisionClient:
    if policy == "heuristic":
        return HeuristicClient()
    if policy == "jev":
        return JevClient()
    raise ValueError(f"unknown policy: {policy}")


def default_policy() -> str:
    return "jev" if has_api_key() else "heuristic"


def make_session(backend: str, **kwargs: Any) -> DinoSession:
    if backend == "fake":
        from dino_jev.fake import FakeDino

        return FakeDino(**kwargs)
    if backend == "chrome":
        from dino_jev.chrome import ChromeDino

        return ChromeDino(**kwargs)
    raise ValueError(f"unknown backend: {backend}")


def default_sync(policy: str, backend: str) -> str:
    if policy == "jev" and backend == "chrome":
        return "freeze"
    return "paced"


class RunLoop:
    def __init__(
        self,
        session: DinoSession,
        client: DecisionClient,
        model: str | None = None,
        dt: float = DEFAULT_DT,
        *,
        sync: str = "paced",
        recorder: RunRecorder | None = None,
    ) -> None:
        self.session = session
        self.client = client
        self.model = model or os.environ.get("TYPESAFE_MODEL", "jev-latest")
        self.dt = dt
        self.sync = sync
        self.recorder = recorder
        self.ticks = 0
        self.last_intent: Intent | None = None
        self.last_state: dict[str, Any] | None = None
        self.last_error: str | None = None
        self.last_usage: dict[str, Any] | None = None
        self.last_state = self.session.observe()

    def _halt_for_tick(self) -> None:
        if (
            self.sync in {"freeze", "step"}
            and hasattr(self.session, "halt_animation")
            and not getattr(self.session, "in_page_control", False)
        ):
            self.session.halt_animation()

    def _advance_after_tick(self) -> None:
        if getattr(self.session, "in_page_control", False):
            return
        if self.sync == "step" and hasattr(self.session, "step_frames"):
            self.session.step_frames(1)
        elif self.sync == "freeze" and hasattr(self.session, "resume_animation"):
            self.session.resume_animation()

    def tick(self) -> dict[str, Any]:
        self._halt_for_tick()
        try:
            state = self.session.observe()
            if isinstance(state, dict) and self.last_intent is not None:
                state = dict(state)
                state["last_latency_ms"] = round(float(self.last_intent.latency_ms), 1)
            body = request_body(state, self.model)
            answers, latency_ms, usage = self.client.decide(body)
            self.last_usage = usage
            intent = compose_intent(
                answers,
                state,
                provider=self.client.provider,
                latency_ms=latency_ms,
                previous=self.last_intent,
            )
            if usage and usage.get("fallback"):
                intent.fallback = True
            self.session.apply(intent)
            self.last_intent = intent
            self.last_state = getattr(self.session, "_last_state", None) or state
            self.ticks += 1
            self.last_error = None
            frame = self.snapshot()
            if self.recorder is not None:
                self.recorder.record_tick(frame, usage=usage)
            return frame
        finally:
            self._advance_after_tick()

    def tick_paced(self) -> dict[str, Any]:
        started = time.perf_counter()
        frame = self.tick()
        if self.sync == "paced":
            leftover = self.dt - (time.perf_counter() - started)
            if leftover > 0:
                time.sleep(leftover)
        elif self.sync == "freeze":
            gap = self.dt - (time.perf_counter() - started)
            if gap > 0:
                time.sleep(gap)
        return frame

    def snapshot(self) -> dict[str, Any]:
        state = self.last_state if self.last_state is not None else self.session.observe()
        return {
            **state,
            "ticks": self.ticks,
            "last_intent": None if self.last_intent is None else self.last_intent.as_dict(),
            "error": self.last_error,
        }

    def run(self, ticks: int, stop_on_crash: bool = True) -> list[dict[str, Any]]:
        self.session.start_run()
        frames = []
        for _ in range(ticks):
            frame = self.tick_paced()
            frames.append(frame)
            if stop_on_crash and (frame.get("run") or {}).get("crashed"):
                break
        return frames
