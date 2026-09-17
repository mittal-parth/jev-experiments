"""Deterministic Krunker-flavored FFA arena.

Code owns geometry, vision, hitscan, ammo, and death. The model only
sees the observation dict and never writes coordinates or raycasts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
import random
from typing import Any, Iterable

MAP_LAYOUT = [
    "################################",
    "#..............##..............#",
    "#..............##..............#",
    "#..............................#",
    "#..............................#",
    "#.......##............##.......#",
    "#.......##............##.......#",
    "#..............................#",
    "#..............................#",
    "#..............##..............#",
    "#..............##..............#",
    "#..............................#",
    "#..............................#",
    "#.......##............##.......#",
    "#.......##............##.......#",
    "#..............................#",
    "#..............................#",
    "#..............##..............#",
    "#..............##..............#",
    "################################",
]

PLAYER_RADIUS = 0.38
MOVE_SPEED = 7.4
STRAFE_SPEED = 6.4
TURN_RATE_DEG = 480.0
SCAN_RATE_DEG = 210.0
MAG_SIZE = 20
RESERVE_START = 80
FIRE_COOLDOWN = 0.11
RELOAD_TIME = 1.15
MAX_HEALTH = 100
HIT_DAMAGE = 24
HIT_RANGE = 22.0
CROSSHAIR_DEG = 5.0
FOV_DEG = 100.0
VIEW_RANGE = 18.5
RESPAWN_TIME = 1.6
JUMP_TIME = 0.32
ENEMY_NAMES = ("Vince", "Hunter", "Ninja")


def wrap_deg(angle: float) -> float:
    wrapped = (angle + 180.0) % 360.0 - 180.0
    return wrapped if wrapped > -180.0 else wrapped + 360.0


def heading_deg(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dy, dx)) % 360.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class Intent:
    stance: str
    move: str
    aim: str
    fire: bool
    reload: bool
    jump: bool
    threat: float | None
    confidence: dict[str, float]
    probabilities: dict[str, dict[str, float]]
    nouls: dict[str, float]
    latency_ms: float
    provider: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Actor:
    actor_id: str
    name: str
    x: float
    y: float
    yaw: float
    health: float = MAX_HEALTH
    mag: int = MAG_SIZE
    reserve: int = RESERVE_START
    fire_cd: float = 0.0
    reload_left: float = 0.0
    jump_left: float = 0.0
    respawn_left: float = 0.0
    spawn: tuple[float, float] = (0.0, 0.0)
    alive: bool = True
    kills: int = 0
    deaths: int = 0
    vx: float = 0.0
    vy: float = 0.0
    team: str = "ffa"

    @property
    def reloading(self) -> bool:
        return self.reload_left > 0

    @property
    def in_air(self) -> bool:
        return self.jump_left > 0


@dataclass
class Shot:
    x0: float
    y0: float
    x1: float
    y1: float
    hit: bool
    ttl: float = 0.12


@dataclass
class Event:
    text: str
    ttl: float = 2.4


class Game:
    def __init__(self, seed: int = 1, scenario: str = "ffa") -> None:
        if scenario not in {"ffa", "duel"}:
            raise ValueError(f"unknown scenario: {scenario}")
        self.seed = seed
        self.scenario = scenario
        self.rng = random.Random(seed)
        self.grid = [list(row) for row in MAP_LAYOUT]
        self.height = len(self.grid)
        self.width = len(self.grid[0])
        self.time = 0.0
        self.shots: list[Shot] = []
        self.events: list[Event] = []
        self.player = Actor(
            "you",
            "Jev",
            4.5,
            16.5,
            -90.0,
            spawn=(4.5, 16.5),
        )
        self.enemies: list[Actor] = []
        self._spawn_enemies()
        self.last_intent: Intent | None = None

    def _spawn_enemies(self) -> None:
        if self.scenario == "duel":
            dummy = Actor("e1", "Dummy", 4.5, 3.5, 90.0, spawn=(4.5, 3.5))
            dummy.mag = MAG_SIZE
            dummy.reserve = 0
            self.enemies = [dummy]
            return
        spots = ((4.5, 3.5, 90.0), (27.5, 3.5, 180.0), (27.5, 16.5, 0.0))
        self.enemies = [
            Actor(f"e{index + 1}", name, x, y, yaw, spawn=(x, y))
            for index, ((x, y, yaw), name) in enumerate(zip(spots, ENEMY_NAMES))
        ]

    def reset(self) -> None:
        self.__init__(seed=self.seed, scenario=self.scenario)

    def wall_at(self, x: float, y: float) -> bool:
        col = int(x)
        row = int(y)
        if row < 0 or col < 0 or row >= self.height or col >= self.width:
            return True
        return self.grid[row][col] == "#"

    def blocked(self, x: float, y: float, radius: float = PLAYER_RADIUS) -> bool:
        for dx, dy in ((-radius, 0.0), (radius, 0.0), (0.0, -radius), (0.0, radius)):
            if self.wall_at(x + dx, y + dy):
                return True
        return False

    def line_of_sight(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        distance = math.hypot(x1 - x0, y1 - y0)
        if distance < 1e-6:
            return True
        steps = max(1, int(distance * 8))
        for index in range(1, steps + 1):
            t = index / steps
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            if self.wall_at(x, y):
                return False
        return True

    def behind_cover(self, actor: Actor, yaw: float | None = None) -> bool:
        facing = actor.yaw if yaw is None else yaw
        rad = math.radians(facing)
        probe_x = actor.x + math.cos(rad) * 1.35
        probe_y = actor.y + math.sin(rad) * 1.35
        return self.wall_at(probe_x, probe_y)

    def cover_near(self, actor: Actor) -> list[dict[str, Any]]:
        covers: list[dict[str, Any]] = []
        for row in range(self.height):
            for col in range(self.width):
                if self.grid[row][col] != "#":
                    continue
                if row in {0, self.height - 1} or col in {0, self.width - 1}:
                    continue
                cx = col + 0.5
                cy = row + 0.5
                dx = cx - actor.x
                dy = cy - actor.y
                dist = math.hypot(dx, dy)
                if dist > 7.5 or dist < 0.8:
                    continue
                covers.append(
                    {
                        "id": f"c{col}_{row}",
                        "bearing_deg": round(wrap_deg(heading_deg(dx, dy) - actor.yaw), 1),
                        "distance": round(dist, 2),
                        "blocks_incoming": self.behind_cover(actor, heading_deg(dx, dy)),
                    }
                )
        covers.sort(key=lambda item: item["distance"])
        return covers[:4]

    def visible_enemies(self, viewer: Actor, others: Iterable[Actor]) -> list[dict[str, Any]]:
        visible: list[dict[str, Any]] = []
        for other in others:
            if not other.alive or other is viewer:
                continue
            dx = other.x - viewer.x
            dy = other.y - viewer.y
            dist = math.hypot(dx, dy)
            if dist > VIEW_RANGE:
                continue
            bearing = wrap_deg(heading_deg(dx, dy) - viewer.yaw)
            if abs(bearing) > FOV_DEG / 2:
                continue
            if not self.line_of_sight(viewer.x, viewer.y, other.x, other.y):
                continue
            visible.append(
                {
                    "id": other.actor_id,
                    "name": other.name,
                    "bearing_deg": round(bearing, 1),
                    "distance": round(dist, 2),
                    "health": int(other.health),
                    "in_crosshair": abs(bearing) <= CROSSHAIR_DEG and dist <= HIT_RANGE,
                    "behind_cover": self.behind_cover(other),
                    "moving": math.hypot(other.vx, other.vy) > 0.4,
                }
            )
        visible.sort(key=lambda item: (not item["in_crosshair"], item["distance"]))
        return visible

    def observe(self) -> dict[str, Any]:
        player = self.player
        visible = self.visible_enemies(player, self.enemies)
        return {
            "goal": (
                "Win this free-for-all. Stay alive and get kills. Play like a "
                "Krunker Triggerman: hitscan, slide around cover, do not reload "
                "in the open."
            ),
            "match": {
                "time_s": round(self.time, 2),
                "kills": player.kills,
                "deaths": player.deaths,
                "alive_enemies": sum(1 for enemy in self.enemies if enemy.alive),
            },
            "self": {
                "health": int(player.health),
                "ammo_in_mag": player.mag,
                "reserve_ammo": player.reserve,
                "reloading": player.reloading,
                "behind_cover": self.behind_cover(player),
                "in_air": player.in_air,
                "yaw_deg": round(wrap_deg(player.yaw), 1),
                "alive": player.alive,
            },
            "visible_enemies": visible,
            "nearby_cover": self.cover_near(player),
            "recent_events": [event.text for event in self.events[-6:]],
            "last_action": None
            if self.last_intent is None
            else {
                "stance": self.last_intent.stance,
                "move": self.last_intent.move,
                "aim": self.last_intent.aim,
                "fire": self.last_intent.fire,
            },
        }

    def _move_actor(self, actor: Actor, mx: float, my: float, dt: float) -> None:
        speed = math.hypot(mx, my)
        if speed > 1e-6:
            mx /= speed
            my /= speed
        boost = 1.12 if actor.in_air else 1.0
        nx = actor.x + mx * MOVE_SPEED * boost * dt
        ny = actor.y + my * MOVE_SPEED * boost * dt
        if not self.blocked(nx, actor.y):
            actor.x = nx
            actor.vx = mx * MOVE_SPEED
        else:
            actor.vx = 0.0
        if not self.blocked(actor.x, ny):
            actor.y = ny
            actor.vy = my * MOVE_SPEED
        else:
            actor.vy = 0.0

    def _turn_towards(self, actor: Actor, target_yaw: float, dt: float, rate: float) -> None:
        delta = wrap_deg(target_yaw - actor.yaw)
        max_step = rate * dt
        if abs(delta) <= max_step:
            actor.yaw = target_yaw % 360.0
        else:
            actor.yaw = (actor.yaw + math.copysign(max_step, delta)) % 360.0

    def _fire(self, actor: Actor, others: list[Actor]) -> None:
        if not actor.alive or actor.reloading or actor.mag <= 0 or actor.fire_cd > 0:
            return
        actor.mag -= 1
        actor.fire_cd = FIRE_COOLDOWN
        rad = math.radians(actor.yaw)
        reach_x = actor.x + math.cos(rad) * HIT_RANGE
        reach_y = actor.y + math.sin(rad) * HIT_RANGE
        hit_actor: Actor | None = None
        hit_dist = HIT_RANGE
        for other in others:
            if not other.alive:
                continue
            dx = other.x - actor.x
            dy = other.y - actor.y
            dist = math.hypot(dx, dy)
            if dist > HIT_RANGE or dist < 1e-6:
                continue
            bearing = abs(wrap_deg(heading_deg(dx, dy) - actor.yaw))
            cone = CROSSHAIR_DEG + 1.8 / max(dist, 1.0)
            if bearing > cone:
                continue
            if not self.line_of_sight(actor.x, actor.y, other.x, other.y):
                continue
            if dist < hit_dist:
                hit_dist = dist
                hit_actor = other
        if hit_actor is None:
            self.shots.append(Shot(actor.x, actor.y, reach_x, reach_y, False))
            return
        end_x = actor.x + math.cos(rad) * hit_dist
        end_y = actor.y + math.sin(rad) * hit_dist
        self.shots.append(Shot(actor.x, actor.y, end_x, end_y, True))
        hit_actor.health -= HIT_DAMAGE
        self.events.append(Event(f"{actor.name} hit {hit_actor.name}"))
        if hit_actor.health <= 0:
            self._kill(actor, hit_actor)

    def _kill(self, killer: Actor, victim: Actor) -> None:
        victim.alive = False
        victim.health = 0
        victim.deaths += 1
        victim.respawn_left = RESPAWN_TIME
        killer.kills += 1
        self.events.append(Event(f"{killer.name} eliminated {victim.name}"))

    def _reload(self, actor: Actor) -> None:
        if actor.reloading or actor.mag >= MAG_SIZE or actor.reserve <= 0:
            return
        actor.reload_left = RELOAD_TIME

    def _finish_reload(self, actor: Actor) -> None:
        need = MAG_SIZE - actor.mag
        take = min(need, actor.reserve)
        actor.mag += take
        actor.reserve -= take

    def _respawn(self, actor: Actor) -> None:
        actor.alive = True
        actor.health = MAX_HEALTH
        actor.mag = MAG_SIZE
        actor.reserve = RESERVE_START
        actor.x, actor.y = actor.spawn
        actor.reload_left = 0.0
        actor.jump_left = 0.0
        actor.fire_cd = 0.2

    def apply(self, intent: Intent, dt: float) -> None:
        self.last_intent = intent
        player = self.player
        if not player.alive:
            return
        aim = intent.aim
        if aim.startswith("e"):
            target = next((enemy for enemy in self.enemies if enemy.actor_id == aim), None)
            if target is not None and target.alive:
                self._turn_towards(
                    player,
                    heading_deg(target.x - player.x, target.y - player.y),
                    dt,
                    TURN_RATE_DEG,
                )
        elif aim == "scan_left":
            player.yaw = (player.yaw - SCAN_RATE_DEG * dt) % 360.0
        elif aim == "scan_right":
            player.yaw = (player.yaw + SCAN_RATE_DEG * dt) % 360.0

        rad = math.radians(player.yaw)
        fx, fy = math.cos(rad), math.sin(rad)
        lx, ly = fy, -fx
        mx = my = 0.0
        move = intent.move
        if move == "forward":
            mx, my = fx, fy
        elif move == "back":
            mx, my = -fx, -fy
        elif move == "strafe_left":
            mx, my = lx * STRAFE_SPEED / MOVE_SPEED, ly * STRAFE_SPEED / MOVE_SPEED
        elif move == "strafe_right":
            mx, my = -lx * STRAFE_SPEED / MOVE_SPEED, -ly * STRAFE_SPEED / MOVE_SPEED
        elif move == "stop":
            mx = my = 0.0
        else:
            raise ValueError(f"unknown move: {move}")
        self._move_actor(player, mx, my, dt)
        if intent.jump:
            player.jump_left = max(player.jump_left, JUMP_TIME)
        if intent.reload:
            self._reload(player)
        if intent.fire:
            self._fire(player, self.enemies)

    def _enemy_step(self, enemy: Actor, dt: float) -> None:
        if not enemy.alive:
            return
        player = self.player
        sees = False
        if player.alive:
            vis = self.visible_enemies(enemy, [player])
            sees = bool(vis)
        if self.scenario == "duel":
            enemy.vx = enemy.vy = 0.0
            return
        if sees and player.alive:
            target_yaw = heading_deg(player.x - enemy.x, player.y - enemy.y)
            self._turn_towards(enemy, target_yaw, dt, 260.0)
            if enemy.health < 35:
                rad = math.radians(enemy.yaw)
                self._move_actor(enemy, -math.cos(rad), -math.sin(rad), dt)
            else:
                rad = math.radians(enemy.yaw)
                self._move_actor(enemy, math.cos(rad), math.sin(rad), dt)
            bearing = abs(wrap_deg(target_yaw - enemy.yaw))
            if bearing < 4 and enemy.mag > 0 and enemy.fire_cd == 0:
                self._fire(enemy, [player])
            elif enemy.mag == 0:
                self._reload(enemy)
        else:
            if self.rng.random() < 0.08:
                enemy.yaw = (enemy.yaw + self.rng.choice((-50.0, 50.0, 120.0))) % 360.0
            rad = math.radians(enemy.yaw)
            self._move_actor(enemy, math.cos(rad) * 0.55, math.sin(rad) * 0.55, dt)

    def _tick_actor(self, actor: Actor, dt: float) -> None:
        actor.fire_cd = max(0.0, actor.fire_cd - dt)
        if actor.jump_left > 0:
            actor.jump_left = max(0.0, actor.jump_left - dt)
        if actor.reload_left > 0:
            actor.reload_left = max(0.0, actor.reload_left - dt)
            if actor.reload_left == 0:
                self._finish_reload(actor)
        if not actor.alive:
            actor.respawn_left = max(0.0, actor.respawn_left - dt)
            if actor.respawn_left == 0:
                self._respawn(actor)

    def step(self, dt: float) -> None:
        self.time += dt
        for enemy in self.enemies:
            self._enemy_step(enemy, dt)
            self._tick_actor(enemy, dt)
        self._tick_actor(self.player, dt)
        self.shots = [shot for shot in self.shots if shot.ttl > 0]
        for shot in self.shots:
            shot.ttl -= dt
        self.events = [event for event in self.events if event.ttl > 0]
        for event in self.events:
            event.ttl -= dt

    def snapshot(self) -> dict[str, Any]:
        def pack(actor: Actor) -> dict[str, Any]:
            data = asdict(actor)
            data["reloading"] = actor.reloading
            data["in_air"] = actor.in_air
            return data

        return {
            "time": self.time,
            "width": self.width,
            "height": self.height,
            "grid": ["".join(row) for row in self.grid],
            "player": pack(self.player),
            "enemies": [pack(enemy) for enemy in self.enemies],
            "shots": [asdict(shot) for shot in self.shots],
            "events": [event.text for event in self.events],
            "observation": self.observe(),
            "last_intent": None
            if self.last_intent is None
            else {
                "stance": self.last_intent.stance,
                "move": self.last_intent.move,
                "aim": self.last_intent.aim,
                "fire": self.last_intent.fire,
                "reload": self.last_intent.reload,
                "jump": self.last_intent.jump,
                "threat": self.last_intent.threat,
                "confidence": self.last_intent.confidence,
                "probabilities": self.last_intent.probabilities,
                "nouls": self.last_intent.nouls,
                "latency_ms": self.last_intent.latency_ms,
                "provider": self.last_intent.provider,
            },
        }
