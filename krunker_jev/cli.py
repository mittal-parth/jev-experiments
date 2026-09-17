"""CLI for the arena, inspector, and krunker.io probe."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from krunker_jev.loop import MatchLoop, default_policy, make_client
from krunker_jev.probe import probe_krunker
from krunker_jev.server import serve
from krunker_jev.world import Game


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


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser(description="Krunker-style Jev combat loop")
    sub = parser.add_subparsers(dest="cmd", required=True)

    play = sub.add_parser("play", help="Run a headless match")
    play.add_argument("--ticks", type=int, default=80)
    play.add_argument("--policy", choices=("heuristic", "jev"), default=None)
    play.add_argument("--scenario", choices=("ffa", "duel"), default="ffa")
    play.add_argument("--seed", type=int, default=1)

    serve_cmd = sub.add_parser("serve", help="Open the local inspector")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8765)
    serve_cmd.add_argument("--policy", choices=("heuristic", "jev"), default=None)

    sub.add_parser("probe-krunker", help="Classify why live krunker.io is not the Doom loop")

    args = parser.parse_args()
    if args.cmd == "play":
        policy = args.policy or default_policy()
        loop = MatchLoop(Game(seed=args.seed, scenario=args.scenario), make_client(policy))
        frames = loop.run(args.ticks)
        last = frames[-1]
        player = last["player"]
        print(
            json.dumps(
                {
                    "policy": policy,
                    "ticks": args.ticks,
                    "kills": player["kills"],
                    "deaths": player["deaths"],
                    "health": player["health"],
                    "time_s": round(last["time"], 2),
                    "last_intent": last["last_intent"],
                },
                indent=2,
            )
        )
        return
    if args.cmd == "serve":
        serve(host=args.host, port=args.port, policy=args.policy)
        return
    if args.cmd == "probe-krunker":
        print(json.dumps(probe_krunker(), indent=2))
        return
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    main()
