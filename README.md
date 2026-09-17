# Krunker-Jev

A TypeSafe **System One** loop in a Krunker-style arena. Jev (or a labeled heuristic fallback) sees structured combat state and returns typed actions; Python owns physics, vision, hitscan, and the inspector.

This is the Doom-shaped experiment from [Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev), not a live krunker.io aimbot.

## Why a local arena, not krunker.io matches

Jev is text-only. The Doom demo fed **structured game state**, not frames. [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast) uses the same idea for Google Flights: snapshot the page into an indexed element table, ask one TypeSafe request (operation + speculative targets), execute only the matching head.

A Krunker **match** is WebGL/canvas (`game-overlay` on top of three.js). There are no accessible buttons for WASD, look, or fire. A Flights-style DOM agent can, at best, click lobby chrome. Driving the match from hidden client transforms would be cheating, not a System One demo.

```
krunker.io lobby  →  DOM  →  jev-ultrafast could click Play (future)
krunker.io match  →  canvas/WebGL  →  Jev cannot see pixels
this repo         →  structured arena state  →  Jev chooses stance/move/aim/fire
```

`python -m krunker_jev probe-krunker` records what this environment can actually fetch from the live site.

## Architecture

Same decomposition as jev-ultrafast and the Doom writeup:

1. **Code snapshots state.** FOV, cover, ammo, health, bearings. No screenshots.
2. **One TypeSafe request per tick.** Stance, move, speculative aim/fire/reload/jump, and a threat score, in parallel. See [speculative fan-out](https://docs.typesafe.ai/patterns/fan-out.md).
3. **Code executes.** Magazines, occlusion, and confidence gates live in `krunker_jev/policy.py`. Unused speculative answers cannot fire a shot.
4. **The inspector is a view.** The canvas never goes to the model.

Questions and thresholds are in [`krunker_jev/questions.py`](krunker_jev/questions.py) so they can be reviewed in one place.

| Head | Primitive | Consumed when |
| --- | --- | --- |
| `stance` | Choice | Always, unless confidence `< 0.32` (keep last stance) |
| `move` | Choice | Always |
| `aim_target` | Choice | Always; enemy ids are only offered when visible |
| `fire` | Noul | Mag has ammo, not reloading, aim is a visible enemy |
| `reload` | Noul | Mag not full, not already reloading, not firing |
| `jump` | Noul | Probability `≥ 0.80` |
| `threat` | Score | Displayed; does not move the body |

## Run it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env   # add TYPESAFE_API_KEY to use Jev
python -m krunker_jev serve
```

Open http://127.0.0.1:8765

- Without a key the inspector uses `heuristic` (same action space, clearly labeled).
- With `TYPESAFE_API_KEY` set, choose **jev** and Start.

Headless:

```bash
python -m krunker_jev play --policy heuristic --ticks 80
python -m krunker_jev play --policy jev --scenario duel --ticks 40
python -m krunker_jev probe-krunker
pytest
```

## What to try next

- Point a jev-ultrafast agent at the Krunker **lobby** only (Play, mode, region). Stop before pointer-lock.
- If TypeSafe adds vision, swap the observation for a caption of the HUD, still keeping hitscan in code.
- Custom Krunker maps / KrunkScript can expose HUD text; still do not read other players' hidden transforms.
