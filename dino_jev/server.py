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
        self.error: str | None = None
        self.runs = 0
        self.best_score = 0
        self.last_score = 0
        self._frame_png: bytes | None = None
        self._frame_at = 0.0
        self._pending: tuple[str, str | None] | None = None
        self._public: dict[str, Any] = {}
        self._publish(self.loop.snapshot())

    def _new_session(self):
        if self.backend == "fake":
            return make_session("fake")
        return make_session("chrome", headed=self.headed, speed_cap=self.speed_cap)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self._public)

    def enqueue(self, action: str, policy: str | None = None) -> None:
        with self.lock:
            self._pending = (action, policy)

    def start(self) -> None:
        self.enqueue("start")

    def stop(self) -> None:
        self.enqueue("stop")

    def reset(self, policy: str | None = None) -> None:
        self.enqueue("reset", policy)

    def step_once(self) -> dict[str, Any]:
        self.enqueue("step")
        self.pump()
        return self.snapshot()

    def _publish(self, frame: dict[str, Any] | None = None) -> None:
        data = dict(frame or {})
        with self.lock:
            data["running"] = self.running
            data["policy"] = self.policy_name
            data["backend"] = self.backend
            data["ticks"] = self.loop.ticks
            data["error"] = self.error or self.loop.last_error
            data["runs"] = self.runs
            data["best_score"] = self.best_score
            data["last_score"] = self.last_score
            self._public = data

    def _handle(self, action: str, policy: str | None) -> None:
        if action == "start":
            if policy:
                self._reset(policy)
            self.running = True
            self.error = None
            self.session.start_run()
            self._publish(self.loop.snapshot())
            return
        if action == "stop":
            self.running = False
            self._publish(self.loop.snapshot())
            return
        if action == "reset":
            self._reset(policy)
            self._publish(self.loop.snapshot())
            return
        if action == "step":
            frame = self.loop.tick()
            self.error = None
            self._note_crash(frame)
            self._maybe_frame()
            self._publish(frame)
            return
        raise ValueError(f"unknown action {action}")

    def _reset(self, policy: str | None) -> None:
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

    def _maybe_frame(self) -> None:
        now = time.monotonic()
        if now - self._frame_at < 0.45 and self._frame_png:
            return
        self._frame_png = self.session.screenshot_png()
        self._frame_at = now

    def pump(self) -> None:
        """Advance queued commands and the run loop on the Playwright thread."""
        with self.lock:
            pending = self._pending
            self._pending = None
        if pending is not None:
            action, policy = pending
            try:
                self._handle(action, policy)
            except Exception as exc:  # noqa: BLE001
                self.running = False
                self.error = str(exc)
                self._publish(self.loop.snapshot())
                return
        if not self.running:
            time.sleep(0.04)
            return
        try:
            frame = self.loop.tick_paced()
            self.error = None
            self._note_crash(frame)
            self._maybe_frame()
            self._publish(frame)
        except Exception as exc:  # noqa: BLE001
            self.running = False
            self.error = str(exc)
            self._publish(self.loop.snapshot())

    def frame_png(self) -> bytes | None:
        with self.lock:
            return self._frame_png

    def close(self) -> None:
        self.running = False
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
                    if action not in {"start", "stop", "reset", "step"}:
                        self._json({"error": f"unknown action {action}"}, 400)
                        return
                    arena.enqueue(str(action), policy)
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
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(
        f"Dino-Jev inspector on http://{host}:{port}  "
        f"policy={arena.policy_name} backend={backend}"
    )
    try:
        while True:
            arena.pump()
    except KeyboardInterrupt:
        pass
    finally:
        arena.close()
        server.shutdown()
