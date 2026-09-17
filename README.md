# jev-experiments

TypeSafe **System One** loops. Jev (or a labeled heuristic fallback) sees structured state and returns typed actions; Python owns execution. The canvas is a view — it never goes to the model.

| Experiment | What it drives | Inspector |
| --- | --- | --- |
| [Dino-Jev](#dino-jev) | Real `chrome://dino/` in Chromium | http://127.0.0.1:8766 |
| [Krunker-Jev](#krunker-jev) | Local Krunker-style arena | http://127.0.0.1:8765 |

Both stay in this repo. Develop them on separate branches; this tree keeps Krunker as-is.

# Dino-Jev

A simpler parallel experiment: drive Chrome's internat dinosaur at `chrome://dino/`.

Same decomposition as Krunker-Jev, jev-ultrafast, and the Doom writeup:

1. **Code snapshots state.** `Runner.getInstance()` exposes pose, speed, and obstacles. No screenshots to the model.
2. **One TypeSafe request per tick.** Action, speculative jump/duck, and an urgency score, in parallel. See [speculative fan-out](https://docs.typesafe.ai/patterns/fan-out.md).
3. **Code executes.** Jump/duck gates live in `dino_jev/policy.py`. High pterodactyls cannot be jumped into; cacti cannot be ducked.
4. **The inspector is a view.** The internat canvas stays in Chrome. Jev never sees those pixels.

Questions and thresholds are in [`dino_jev/questions.py`](dino_jev/questions.py).

| Head | Primitive | Consumed when |
| --- | --- | --- |
| `action` | Choice (`run` / `jump` / `duck`) | Always, unless confidence `< 0.28` (keep last action) |
| `jump_now` | Noul | Grounded, not intro, nearest clearance is `ground` or `low` |
| `duck_now` | Noul | Grounded, not jumping, nearest clearance is `mid` |
| `urgency` | Score | Displayed; does not move the body |

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env   # or set JEV_API_KEY / TYPESAFE_API_KEY
python -m dino_jev probe-dino
python -m dino_jev play --policy heuristic --seconds 50
python -m dino_jev play --policy jev --seconds 20
python -m dino_jev serve
```

The command launches Chromium itself on `chrome://dino/` in fullscreen arcade mode. You do not open a separate dino tab. Pass `--windowed` if you want a normal window. Open http://127.0.0.1:8766 for the inspector (a view; Jev never sees those pixels).

- Without a key the loop uses `heuristic` (distance-threshold bot, clearly labeled).
- With `JEV_API_KEY` or `TYPESAFE_API_KEY` set, it defaults to **jev**.
- `--speed-cap 9` (default) keeps `maxSpeed` just above pterodactyl spawn (`8.5`) so Jev's ~80ms tick can still commit. `--speed-cap none` is full internat acceleration.
- Internat pauses on window blur and on resize. Dino-Jev patches those so the runner keeps going while the inspector or another window is focused.

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
cp .env.example .env   # or set JEV_API_KEY / TYPESAFE_API_KEY
python -m krunker_jev serve
```

Open http://127.0.0.1:8765

- Without a key the inspector uses `heuristic` (same action space, clearly labeled).
- With `JEV_API_KEY` or `TYPESAFE_API_KEY` set, it defaults to **jev**. Cursor runtime secrets named `JEV_API_KEY` are picked up at **agent start**, not on an already-running VM.

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
