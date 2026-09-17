"""Loopback inspector for chrome://dino/ plus the decision panel."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from typing import Any
from urllib.parse import urlparse

from dino_jev.loop import RunLoop, default_policy, make_client, make_session

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_PORT = 8766


class DinoServer:
    def __init__(
        self,
        policy: str | None = None,
        backend: str = "chrome",
        headed: bool = True,
        speed_cap: float | None = 9.0,
        auto_restart: bool = True,
    ) -> None:
        self.policy_name = policy or default_policy()
        self.backend = backend
        self.headed = headed
        self.speed_cap = speed_cap
        self.auto_restart = auto_restart
        self.lock = threading.Lock()
        self.session = self._new_session()
        self.loop = RunLoop(self.session, make_client(self.policy_name))
        self.running = False
        self.worker: threading.Thread | None = None
        self.error: str | None = None
        self.runs = 0
        self.best_score = 0
        self.last_score = 0
        self._frame_png: bytes | None = None
        self._frame_at = 0.0

    def _new_session(self):
        if self.backend == "fake":
            return make_session("fake")
        return make_session("chrome", headed=self.headed, speed_cap=self.speed_cap)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            data = self.loop.snapshot()
            data["running"] = self.running
            data["policy"] = self.policy_name
            data["backend"] = self.backend
            data["ticks"] = self.loop.ticks
            data["error"] = self.error or self.loop.last_error
            data["runs"] = self.runs
            data["best_score"] = self.best_score
            data["last_score"] = self.last_score
            return data

    def start(self) -> None:
        with self.lock:
            if self.running:
                return
            self.running = True
            self.error = None
            try:
                self.session.start_run()
            except Exception as exc:  # noqa: BLE001
                self.running = False
                self.error = str(exc)
                raise
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
            try:
                self.session.restart()
            except Exception:
                self.session.close()
                self.session = self._new_session()
            self.loop = RunLoop(self.session, make_client(self.policy_name))
            self.error = None

    def step_once(self) -> dict[str, Any]:
        with self.lock:
            try:
                frame = self.loop.tick()
                self.error = None
                self._note_crash(frame)
                return frame
            except Exception as exc:  # noqa: BLE001
                self.error = str(exc)
                raise

    def _note_crash(self, frame: dict[str, Any]) -> None:
        run = frame.get("run") or {}
        score = int(run.get("score") or 0)
        if run.get("crashed"):
            self.last_score = score
            self.best_score = max(self.best_score, score)
            if self.auto_restart and self.running:
                self.runs += 1
                self.session.restart()
                self.session.start_run()

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

    def frame_png(self) -> bytes | None:
        now = time.monotonic()
        if now - self._frame_at < 0.45 and self._frame_png:
            return self._frame_png
        with self.lock:
            png = self.session.screenshot_png()
        self._frame_png = png
        self._frame_at = now
        return png

    def close(self) -> None:
        self.stop()
        self.session.close()


def make_handler(arena: DinoServer) -> type[BaseHTTPRequestHandler]:
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
            if path == "/api/frame.png":
                png = arena.frame_png()
                if not png:
                    self._json({"error": "no frame"}, 404)
                    return
                self._send(200, png, "image/png")
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


def serve(
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    policy: str | None = None,
    backend: str = "chrome",
    headed: bool = True,
    speed_cap: float | None = 9.0,
) -> None:
    arena = DinoServer(
        policy=policy,
        backend=backend,
        headed=headed,
        speed_cap=speed_cap,
    )
    server = ThreadingHTTPServer((host, port), make_handler(arena))
    print(
        f"Dino-Jev inspector on http://{host}:{port}  "
        f"policy={arena.policy_name} backend={backend}"
    )
    try:
        server.serve_forever()
    finally:
        arena.close()
