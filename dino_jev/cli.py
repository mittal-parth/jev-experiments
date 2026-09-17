"""CLI for chrome://dino/, the inspector, and a Runner probe."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from dino_jev.loop import RunLoop, default_policy, make_client, make_session
from dino_jev.probe import probe_dino
from dino_jev.server import DEFAULT_PORT, serve


def _load_env() -> None:
    path = Path(".env")
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _speed_cap(raw: str) -> float | None:
    if raw.lower() in {"none", "off", "0"}:
        return None
    return float(raw)


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser(description="Chrome Dino TypeSafe System One loop")
    sub = parser.add_subparsers(dest="cmd", required=True)

    play = sub.add_parser("play", help="Play chrome://dino/ until crash or tick cap")
    play.add_argument("--ticks", type=int, default=400)
    play.add_argument("--seconds", type=float, default=None)
    play.add_argument("--policy", choices=("heuristic", "jev"), default=None)
    play.add_argument("--backend", choices=("chrome", "fake"), default="chrome")
    play.add_argument("--headless", action="store_true")
    play.add_argument("--speed-cap", type=_speed_cap, default=9.0)
    play.add_argument("--no-stop-on-crash", action="store_true")

    serve_cmd = sub.add_parser("serve", help="Open the local inspector")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_cmd.add_argument("--policy", choices=("heuristic", "jev"), default=None)
    serve_cmd.add_argument("--backend", choices=("chrome", "fake"), default="chrome")
    serve_cmd.add_argument("--headless", action="store_true")
    serve_cmd.add_argument("--speed-cap", type=_speed_cap, default=9.0)

    sub.add_parser("probe-dino", help="Confirm chrome://dino/ exposes Runner.getInstance()")

    args = parser.parse_args()
    if args.cmd == "play":
        policy = args.policy or default_policy()
        session_kwargs: dict = {}
        if args.backend == "chrome":
            session_kwargs = {
                "headed": not args.headless,
                "speed_cap": args.speed_cap,
            }
        session = make_session(args.backend, **session_kwargs)
        loop = RunLoop(session, make_client(policy))
        started = time.perf_counter()
        try:
            session.start_run()
            frames: list[dict] = []
            limit = args.ticks
            while len(frames) < limit:
                if args.seconds is not None and time.perf_counter() - started >= args.seconds:
                    break
                frame = loop.tick_paced()
                frames.append(frame)
                if not args.no_stop_on_crash and (frame.get("run") or {}).get("crashed"):
                    break
            last = frames[-1] if frames else loop.snapshot()
            run = last.get("run") or {}
            print(
                json.dumps(
                    {
                        "policy": policy,
                        "backend": args.backend,
                        "ticks": len(frames),
                        "score": run.get("score"),
                        "speed": run.get("speed"),
                        "crashed": run.get("crashed"),
                        "elapsed_s": round(time.perf_counter() - started, 2),
                        "last_intent": last.get("last_intent"),
                    },
                    indent=2,
                )
            )
        finally:
            session.close()
        return
    if args.cmd == "serve":
        serve(
            host=args.host,
            port=args.port,
            policy=args.policy,
            backend=args.backend,
            headed=not args.headless,
            speed_cap=args.speed_cap,
        )
        return
    if args.cmd == "probe-dino":
        print(json.dumps(probe_dino(), indent=2))
        return
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    main()
