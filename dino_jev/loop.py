"""Observe chrome://dino/ → one System One request → execute keys."""

from __future__ import annotations

import os
import time
from typing import Any, Protocol

from dino_jev.client import DecisionClient, JevClient, has_api_key
from dino_jev.heuristic import HeuristicClient
from dino_jev.policy import Intent, compose_intent, request_body

DEFAULT_DT = 1 / 30
HEURISTIC_CHROME_DT = 0.25


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


class RunLoop:
    def __init__(
        self,
        session: DinoSession,
        client: DecisionClient,
        model: str | None = None,
        dt: float = DEFAULT_DT,
    ) -> None:
        self.session = session
        self.client = client
        self.model = model or os.environ.get("TYPESAFE_MODEL", "jev-latest")
        self.dt = dt
        self.ticks = 0
        self.last_intent: Intent | None = None
        self.last_state: dict[str, Any] | None = None
        self.last_error: str | None = None
        self.last_state = self.session.observe()

    def tick(self) -> dict[str, Any]:
        state = self.session.observe()
        body = request_body(state, self.model)
        answers, latency_ms = self.client.decide(body)
        intent = compose_intent(
            answers,
            state,
            provider=self.client.provider,
            latency_ms=latency_ms,
            previous=self.last_intent,
        )
        self.session.apply(intent)
        self.last_intent = intent
        self.last_state = getattr(self.session, "_last_state", None) or state
        self.ticks += 1
        self.last_error = None
        return self.snapshot()

    def tick_paced(self) -> dict[str, Any]:
        started = time.perf_counter()
        frame = self.tick()
        leftover = self.dt - (time.perf_counter() - started)
        if leftover > 0:
            time.sleep(leftover)
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
