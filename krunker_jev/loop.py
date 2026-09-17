"""Observe → one System One request → execute → step the arena."""

from __future__ import annotations

import os
from typing import Any

from krunker_jev.client import DecisionClient, JevClient, has_api_key
from krunker_jev.heuristic import HeuristicClient
from krunker_jev.policy import compose_intent, request_body
from krunker_jev.world import Game, Intent

DEFAULT_DT = 0.1


def make_client(policy: str) -> DecisionClient:
    if policy == "heuristic":
        return HeuristicClient()
    if policy == "jev":
        return JevClient()
    raise ValueError(f"unknown policy: {policy}")


def default_policy() -> str:
    return "jev" if has_api_key() else "heuristic"


class MatchLoop:
    def __init__(
        self,
        game: Game,
        client: DecisionClient,
        model: str | None = None,
        dt: float = DEFAULT_DT,
    ) -> None:
        self.game = game
        self.client = client
        self.model = model or os.environ.get("TYPESAFE_MODEL", "jev-latest")
        self.dt = dt
        self.ticks = 0
        self.last_intent: Intent | None = None
        self.last_error: str | None = None
        self.running = False

    def tick(self) -> dict[str, Any]:
        state = self.game.observe()
        body = request_body(state, self.model)
        answers, latency_ms = self.client.decide(body)
        intent = compose_intent(
            answers,
            state,
            provider=self.client.provider,
            latency_ms=latency_ms,
            previous=self.last_intent,
        )
        self.game.apply(intent, self.dt)
        self.game.step(self.dt)
        self.last_intent = intent
        self.ticks += 1
        self.last_error = None
        return self.game.snapshot()

    def run(self, ticks: int) -> list[dict[str, Any]]:
        frames = []
        for _ in range(ticks):
            frames.append(self.tick())
        return frames
