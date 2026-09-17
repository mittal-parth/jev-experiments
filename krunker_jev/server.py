"""Loopback inspector for the arena + decision panel."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from typing import Any
from urllib.parse import urlparse

from krunker_jev.loop import MatchLoop, default_policy, make_client
from krunker_jev.world import Game

STATIC_DIR = Path(__file__).parent / "static"


class ArenaServer:
    def __init__(self, policy: str | None = None, seed: int = 1) -> None:
        self.policy_name = policy or default_policy()
        self.seed = seed
        self.lock = threading.Lock()
        self.loop = MatchLoop(Game(seed=seed), make_client(self.policy_name))
        self.running = False
        self.worker: threading.Thread | None = None
        self.error: str | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            data = self.loop.game.snapshot()
            data["running"] = self.running
            data["policy"] = self.policy_name
            data["ticks"] = self.loop.ticks
            data["error"] = self.error
            return data

    def start(self) -> None:
        with self.lock:
            if self.running:
                return
            self.running = True
            self.error = None
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def stop(self) -> None:
        with self.lock:
            self.running = False

    def reset(self, policy: str | None = None) -> None:
        with self.lock:
            self.running = False
            if policy is not None:
                self.policy_name = policy
            self.loop = MatchLoop(Game(seed=self.seed), make_client(self.policy_name))
            self.error = None

    def step_once(self) -> dict[str, Any]:
        with self.lock:
            try:
                frame = self.loop.tick()
                self.error = None
                return frame
            except Exception as exc:  # noqa: BLE001 - surface to the inspector
                self.error = str(exc)
                raise

    def _run(self) -> None:
        while True:
            with self.lock:
                if not self.running:
                    return
                dt = self.loop.dt
            started = time.perf_counter()
            try:
                self.step_once()
            except Exception:
                with self.lock:
                    self.running = False
                return
            leftover = dt - (time.perf_counter() - started)
            if leftover > 0:
                time.sleep(leftover)


def make_handler(arena: ArenaServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: dict[str, Any], status: int = 200) -> None:
            self._send(status, json.dumps(payload).encode(), "application/json")

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/snapshot":
                self._json(arena.snapshot())
                return
            if path == "/":
                path = "/index.html"
            relative = path.lstrip("/")
            target = (STATIC_DIR / relative).resolve()
            if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
                self._json({"error": "not found"}, 404)
                return
            if not target.is_file():
                self._json({"error": "not found"}, 404)
                return
            suffix = target.suffix
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
            }.get(suffix, "application/octet-stream")
            self._send(200, target.read_bytes(), content_type)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode() or "{}")
            except json.JSONDecodeError:
                self._json({"error": "invalid json"}, 400)
                return
            action = payload.get("action")
            policy = payload.get("policy")
            try:
                if path == "/api/control":
                    if action == "start":
                        if policy:
                            arena.reset(policy)
                        arena.start()
                    elif action == "stop":
                        arena.stop()
                    elif action == "reset":
                        arena.reset(policy)
                    elif action == "step":
                        arena.step_once()
                    else:
                        self._json({"error": f"unknown action {action}"}, 400)
                        return
                    self._json(arena.snapshot())
                    return
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc), **arena.snapshot()}, 500)
                return
            self._json({"error": "not found"}, 404)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, policy: str | None = None) -> None:
    arena = ArenaServer(policy=policy)
    server = ThreadingHTTPServer((host, port), make_handler(arena))
    print(f"Krunker-Jev inspector on http://{host}:{port}  policy={arena.policy_name}")
    server.serve_forever()
