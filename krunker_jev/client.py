"""HTTP client for TypeSafe System One. Credentials stay server-side."""

from __future__ import annotations

import math
import os
import time
from typing import Any, Protocol

import httpx

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"


class DecisionClient(Protocol):
    provider: str

    def decide(self, body: dict[str, Any]) -> tuple[dict[str, Any], float]:
        """Return (answers, latency_ms)."""


def validate_choice(answer: dict[str, Any], ids: set[str]) -> dict[str, Any]:
    try:
        probabilities = answer["probabilities"]
        numbers = [*probabilities.values(), answer["confidence"]]
        valid = (
            answer.get("type") == "choice"
            and answer["choice"] in ids
            and set(probabilities) == ids
            and all(isinstance(n, (int, float)) and math.isfinite(n) and 0 <= n <= 1 for n in numbers)
            and abs(sum(probabilities.values()) - 1) < 0.02
            and probabilities[answer["choice"]] >= max(probabilities.values()) - 1e-6
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("Invalid TypeSafe choice; no action executed.")
    return answer


def validate_noul(answer: dict[str, Any]) -> dict[str, Any]:
    try:
        value = answer["noul"]
        valid = (
            answer.get("type") == "noul"
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and 0 <= value <= 1
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("Invalid TypeSafe noul; no action executed.")
    return answer


def validate_score(answer: dict[str, Any], levels: int) -> dict[str, Any]:
    try:
        probabilities = {str(key): value for key, value in answer["probabilities"].items()}
        numbers = [*probabilities.values(), answer["confidence"], answer["score"]]
        valid = (
            answer.get("type") == "score"
            and set(probabilities) == {str(index) for index in range(levels)}
            and all(isinstance(n, (int, float)) and math.isfinite(n) for n in numbers)
            and all(0 <= probabilities[key] <= 1 for key in probabilities)
            and abs(sum(probabilities.values()) - 1) < 0.02
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("Invalid TypeSafe score; no action executed.")
    return answer


def validate_answers(answers: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
    if set(answers) != set(questions):
        raise ValueError("TypeSafe answers do not match questions; no action executed.")
    for key, question in questions.items():
        kind = question["type"]
        answer = answers[key]
        if kind == "choice":
            validate_choice(answer, set(question["criteria"]))
        elif kind == "noul":
            validate_noul(answer)
        elif kind == "score":
            validate_score(answer, len(question["criteria"]))
        else:
            raise ValueError(f"unknown question type: {kind}")
    return answers


class JevClient:
    provider = "jev"

    def __init__(self, api_key: str | None = None, timeout: float = 8.0) -> None:
        self.api_key = api_key or os.environ.get("TYPESAFE_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("TYPESAFE_API_KEY is missing; Jev was not called.")
        self.http = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self.http.close()

    def decide(self, body: dict[str, Any]) -> tuple[dict[str, Any], float]:
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.http.post(
                    TYPESAFE_URL,
                    json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(0.4 * 2**attempt)
                continue
            if response.status_code in {429, 529, 503} and attempt < 2:
                time.sleep(0.4 * 2**attempt)
                continue
            if response.is_error:
                raise RuntimeError(
                    f"TypeSafe returned HTTP {response.status_code}; no action executed."
                )
            payload = response.json()
            answers = validate_answers(payload.get("answers") or {}, body["questions"])
            return answers, round((time.perf_counter() - started) * 1000)
        raise RuntimeError(f"TypeSafe unavailable; no action executed ({last_error})")


class FixtureClient:
    provider = "fixture"

    def __init__(self, answers: dict[str, Any], latency_ms: float = 1.0) -> None:
        self.answers = answers
        self.latency_ms = latency_ms

    def decide(self, body: dict[str, Any]) -> tuple[dict[str, Any], float]:
        return validate_answers(self.answers, body["questions"]), self.latency_ms
