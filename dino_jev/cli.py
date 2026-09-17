"""CLI for chrome://dino/, the inspector, and a Runner probe."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from dino_jev.loop import HEURISTIC_CHROME_DT, RunLoop, default_policy, default_sync, make_client, make_session
from dino_jev.probe import probe_dino
from dino_jev.server import DEFAULT_PORT, serve
from dino_jev.telemetry import RunRecorder


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
    play.add_argument("--windowed", action="store_true", help="Do not fullscreen the Chrome window")
    play.add_argument("--speed-cap", type=_speed_cap, default=9.0)
    play.add_argument(
        "--lead-frames",
        type=int,
        default=8,
        help="Internat frames before impact to jump if the hop still clears. Lower = later (wide clusters). Higher = earlier.",
    )
    play.add_argument(
        "--sync",
        choices=("paced", "freeze", "step"),
        default=None,
        help="paced=wall clock; freeze=halt during Jev HTTP; step=one internat frame per Jev call (default for jev+chrome).",
    )
    play.add_argument(
        "--record",
        type=Path,
        default=None,
        help="Write JSONL tick log with timing tags and token usage.",
    )
    play.add_argument("--target-score", type=int, default=None, help="Stop after reaching this score.")
    play.add_argument("--no-stop-on-crash", action="store_true")

    bench = sub.add_parser(
        "bench",
        help="Run Jev (or heuristic) with telemetry until crash or target score; prints rollup JSON.",
    )
    bench.add_argument("--policy", choices=("heuristic", "jev"), default=None)
    bench.add_argument("--backend", choices=("chrome", "fake"), default="chrome")
    bench.add_argument("--headless", action="store_true")
    bench.add_argument("--windowed", action="store_true")
    bench.add_argument("--speed-cap", type=_speed_cap, default=9.0)
    bench.add_argument("--lead-frames", type=int, default=12)
    bench.add_argument("--sync", choices=("paced", "freeze", "step"), default=None)
    bench.add_argument("--target-score", type=int, default=1000)
    bench.add_argument("--max-ticks", type=int, default=50_000)
    bench.add_argument("--record", type=Path, default=None)

    serve_cmd = sub.add_parser("serve", help="Open the local inspector")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_cmd.add_argument("--policy", choices=("heuristic", "jev"), default=None)
    serve_cmd.add_argument("--backend", choices=("chrome", "fake"), default="chrome")
    serve_cmd.add_argument("--headless", action="store_true")
    serve_cmd.add_argument("--windowed", action="store_true", help="Do not fullscreen the Chrome window")
    serve_cmd.add_argument("--speed-cap", type=_speed_cap, default=9.0)
    serve_cmd.add_argument(
        "--lead-frames",
        type=int,
        default=8,
        help="Internat frames before impact to jump if the hop still clears. Lower = later (wide clusters). Higher = earlier.",
    )

    sub.add_parser("probe-dino", help="Confirm chrome://dino/ exposes Runner.getInstance()")

    args = parser.parse_args()
    if args.cmd == "play":
        policy = args.policy or default_policy()
        sync = args.sync or default_sync(policy, args.backend)
        session_kwargs: dict = {}
        if args.backend == "chrome":
            in_page = sync != "step"
            session_kwargs = {
                "headed": not args.headless,
                "speed_cap": args.speed_cap,
                "fullscreen": not args.windowed and not args.headless,
                "in_page_control": in_page,
                "lead_frames": args.lead_frames,
                "provider": policy,
                "sync_mode": "live" if sync == "paced" and policy == "heuristic" else sync,
            }
        session = make_session(args.backend, **session_kwargs)
        recorder = RunRecorder(path=args.record, lead_frames=args.lead_frames) if args.record else None
        loop_kwargs: dict = {"sync": sync, "recorder": recorder}
        if policy == "jev" and sync == "freeze":
            loop_kwargs["dt"] = 0.12
        elif policy == "heuristic" and args.backend == "chrome" and sync == "paced":
            loop_kwargs["dt"] = HEURISTIC_CHROME_DT
        loop = RunLoop(session, make_client(policy), **loop_kwargs)
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
                score = int((frame.get("run") or {}).get("score") or 0)
                if args.target_score is not None and score >= args.target_score:
                    break
                if (frame.get("run") or {}).get("crashed"):
                    if args.no_stop_on_crash:
                        session.restart()
                        session.start_run()
                    else:
                        break
            last = frames[-1] if frames else loop.snapshot()
            run = last.get("run") or {}
            payload = {
                "policy": policy,
                "backend": args.backend,
                "sync": sync,
                "ticks": len(frames),
                "score": run.get("score"),
                "speed": run.get("speed"),
                "crashed": run.get("crashed"),
                "elapsed_s": round(time.perf_counter() - started, 2),
                "last_intent": last.get("last_intent"),
            }
            if recorder is not None:
                payload["telemetry"] = recorder.report(
                    score=int(run.get("score") or 0),
                    crashed=bool(run.get("crashed")),
                    ticks=len(frames),
                    elapsed_s=payload["elapsed_s"],
                )
                recorder.close()
            print(json.dumps(payload, indent=2))
        finally:
            session.close()
        return
    if args.cmd == "bench":
        policy = args.policy or default_policy()
        sync = args.sync or default_sync(policy, args.backend)
        session_kwargs: dict = {}
        if args.backend == "chrome":
            in_page = sync != "step"
            session_kwargs = {
                "headed": not args.headless,
                "speed_cap": args.speed_cap,
                "fullscreen": not args.windowed and not args.headless,
                "in_page_control": in_page,
                "lead_frames": args.lead_frames,
                "provider": policy,
                "sync_mode": "live" if sync == "paced" and policy == "heuristic" else sync,
            }
        session = make_session(args.backend, **session_kwargs)
        record_path = args.record or Path("artifacts") / f"dino-{policy}-{sync}.jsonl"
        recorder = RunRecorder(path=record_path, lead_frames=args.lead_frames)
        loop = RunLoop(session, make_client(policy), sync=sync, recorder=recorder)
        if policy == "jev" and sync == "freeze":
            loop.dt = 0.12
        elif policy == "heuristic" and args.backend == "chrome" and sync == "paced":
            loop.dt = HEURISTIC_CHROME_DT
        started = time.perf_counter()
        try:
            session.start_run()
            frames = 0
            last_score = 0
            crashed = False
            while frames < args.max_ticks:
                frame = loop.tick_paced()
                frames += 1
                run = frame.get("run") or {}
                last_score = int(run.get("score") or 0)
                crashed = bool(run.get("crashed"))
                if last_score >= args.target_score:
                    crashed = False
                    break
                if crashed:
                    break
            report = recorder.report(
                score=last_score,
                crashed=crashed,
                ticks=frames,
                elapsed_s=time.perf_counter() - started,
            )
            report.update(
                {
                    "policy": policy,
                    "backend": args.backend,
                    "sync": sync,
                    "target_score": args.target_score,
                    "record_path": str(record_path),
                    "reached_target": last_score >= args.target_score,
                }
            )
            recorder.close()
            print(json.dumps(report, indent=2))
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
            fullscreen=not args.windowed and not args.headless,
            lead_frames=args.lead_frames,
        )
        return
    if args.cmd == "probe-dino":
        print(json.dumps(probe_dino(), indent=2))
        return
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    main()
