"""Playwright / CDP adapter for the real chrome://dino/ runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Error, sync_playwright

from dino_jev.policy import Intent, obstacle_clearance
from dino_jev.questions import GOAL

DINO_URL = "chrome://dino/"
KEY_JUMP = 32
KEY_DUCK = 40
BOT_JS = (Path(__file__).parent / "static" / "bot.js").read_text()

SNAPSHOT_JS = """(cap) => {
  if (typeof Runner === "undefined" || typeof Runner.getInstance !== "function") {
    return { ok: false, error: "Runner.getInstance is missing" };
  }
  const inst = Runner.getInstance();
  if (!inst) {
    return { ok: false, error: "Runner instance is missing" };
  }
  if (cap && cap > 0) {
    if (inst.config) inst.config.maxSpeed = cap;
    if (inst.currentSpeed > cap) inst.setSpeed(cap);
  }
  const trex = inst.tRex;
  const horizon = inst.horizon;
  const obstacles = (horizon && horizon.obstacles) || [];
  const width = trex && trex.ducking ? trex.config.widthDuck : trex.config.width;
  const height = trex && trex.ducking ? trex.config.heightDuck : trex.config.height;
  const ms = inst.msPerFrame || 1000 / 60;
  const pxPerSec = inst.currentSpeed * (1000 / ms);
  function kindOf(type) {
    if (!type) return "other";
    if (type === "pterodactyl") return "pterodactyl";
    if (type === "collectable") return "collectable";
    if (String(type).startsWith("cactus")) return "cactus";
    return "other";
  }
  function pack(obstacle, index) {
    const type = obstacle.typeConfig && obstacle.typeConfig.type;
    const kind = kindOf(type);
    const gap = obstacle.xPos - trex.xPos - width;
    return {
      id: "o" + index,
      kind,
      type: type || "unknown",
      x: Math.round(obstacle.xPos * 10) / 10,
      y: obstacle.yPos,
      width: obstacle.width || (obstacle.typeConfig && obstacle.typeConfig.width) || 0,
      height: (obstacle.typeConfig && obstacle.typeConfig.height) || 0,
      gap_px: Math.round(gap * 10) / 10,
      time_to_impact_s: pxPerSec > 0 ? Math.round((gap / pxPerSec) * 1000) / 1000 : null,
    };
  }
  const packed = obstacles.filter((item) => item && item.xPos + (item.width || 0) > trex.xPos).map(pack);
  let score = Math.round(inst.distanceRan * 0.025);
  try {
    if (inst.distanceMeter && typeof inst.distanceMeter.getActualDistance === "function") {
      score = inst.distanceMeter.getActualDistance(inst.distanceRan);
    }
  } catch (err) {}
  return {
    ok: true,
    playing: !!inst.playing,
    crashed: !!inst.crashed,
    intro: !!inst.playingIntro || (inst.activated && trex && trex.xPos < 40),
    speed: inst.currentSpeed,
    score,
    distanceRan: inst.distanceRan,
    dino: trex && {
      x: trex.xPos,
      y: trex.yPos,
      ground_y: trex.groundYPos,
      width,
      height,
      jumping: !!trex.jumping,
      ducking: !!trex.ducking,
    },
    obstacles: packed.slice(0, 3),
  };
}"""

HUD_JS = """(payload) => {
  const jev = window.__dinoJev;
  if (!jev) return false;
  jev.provider = (payload && payload.provider) || jev.provider;
  if (!payload || payload.set_action !== false) {
    if (payload && payload.action) jev.action = payload.action;
  }
  jev.reply = payload;
  jev._replySeq = (jev._replySeq || 0) + 1;
  if (typeof jev.paintHud === "function") {
    const inst = typeof Runner !== "undefined" && Runner.getInstance && Runner.getInstance();
    jev.paintHud(inst);
  }
  return true;
}"""

START_JS = """() => {
  const inst = Runner.getInstance();
  if (!inst) return { ok: false };
  if (inst.crashed) {
    inst.restart();
  }
  return {
    ok: true,
    playing: !!inst.playing,
    crashed: !!inst.crashed,
    activated: !!inst.activated,
    x: inst.tRex && inst.tRex.xPos,
  };
}"""

FORCE_ACTIVATE_JS = """() => {
  const inst = Runner.getInstance();
  if (!inst || !inst.tRex) return false;
  if (inst.slowSpeedCheckbox) inst.slowSpeedCheckbox.checked = false;
  try { inst.playIntro(); } catch (e) {}
  try { inst.startGame(); } catch (e) {}
  inst.activated = true;
  inst.playingIntro = false;
  inst.tRex.playingIntro = false;
  inst.setPlayStatus(true);
  if (inst.tRex.xPos < inst.tRex.config.startXPos) {
    inst.tRex.xPos = inst.tRex.config.startXPos;
  }
  inst.tRex.xInitialPos = inst.tRex.config.startXPos;
  if (!inst.raqId) inst.update();
  return true;
}"""

PATCH_DT_JS = """() => {
  if (typeof Runner !== "undefined" && Runner.prototype && !Runner.prototype._jevVisPatched) {
    Runner.prototype.onVisibilityChange = function() {};
    Runner.prototype._jevVisPatched = true;
  }
  const inst = typeof Runner !== "undefined" && typeof Runner.getInstance === "function"
    ? Runner.getInstance()
    : null;
  if (!inst || inst._jevDtPatched) return !!inst;
  inst.onVisibilityChange = function() {};
  const innerUpdate = inst.update.bind(inst);
  inst.update = function patchedUpdate() {
    const now = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
    if (this.time && now - this.time > 34) {
      this.time = now - 16.67;
    }
    return innerUpdate();
  };
  if (typeof inst.adjustDimensions === "function") {
    const innerAdjust = inst.adjustDimensions.bind(inst);
    inst.adjustDimensions = function patchedAdjust() {
      const wasPlaying = this.playing && !this.crashed;
      innerAdjust();
      if (wasPlaying && !this.crashed) {
        this.paused = false;
        this.setPlayStatus(true);
        this.time = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
        if (!this.raqId) this.update();
      }
    };
  }
  inst._jevDtPatched = true;
  return true;
}"""

APPLY_JS = """(payload) => {
  const inst = Runner.getInstance();
  const action = payload && payload.action;
  const jev = window.__dinoJev;
  if (jev) {
    jev.provider = (payload && payload.provider) || jev.provider;
    if (!payload || payload.set_action !== false) jev.action = action;
    jev.reply = payload;
    jev._replySeq = (jev._replySeq || 0) + 1;
    if (typeof jev.paintHud === "function") jev.paintHud(inst);
  }
  if (!inst || !inst.tRex) return { ok: false };
  const t = inst.tRex;
  if (inst.crashed || !inst.playing || inst.playingIntro) {
    return { ok: true, skipped: true, crashed: !!inst.crashed };
  }
  if (action === "jump" && !t.jumping && !t.ducking) {
    t.startJump(inst.currentSpeed);
  } else if (action === "duck" && !t.jumping) {
    t.setDuck(true);
  } else if (action === "run") {
    if (t.ducking) t.setDuck(false);
  }
  return { ok: true, jumping: !!t.jumping, ducking: !!t.ducking, y: t.yPos };
}"""

CAP_SPEED_JS = """(cap) => {
  const inst = Runner.getInstance();
  if (!inst || cap == null || cap <= 0) return inst && inst.currentSpeed;
  if (inst.config) inst.config.maxSpeed = cap;
  if (inst.currentSpeed > cap) inst.setSpeed(cap);
  return inst.currentSpeed;
}"""

PREP_PAGE_JS = """() => {
  if (document.getElementById("dino-jev-prep")) return true;
  const style = document.createElement("style");
  style.id = "dino-jev-prep";
  style.textContent = [
    "html, body { margin:0 !important; overflow:hidden !important; background:#f7f7f7 !important; height:100% !important; }",
    "#main-message, .nav-wrapper, .error-code { display:none !important; }",
    ".icon-offline { display:none !important; }",
    ".runner-container { z-index:10; }",
  ].join("\\n");
  document.documentElement.appendChild(style);
  return true;
}"""

ARCADE_JS = """() => {
  const inst = Runner.getInstance();
  if (!inst) return false;
  if (!document.title.startsWith("chrome://dino/")) {
    document.title = "chrome://dino/";
  }
  try {
    document.body.classList.add("arcade-mode");
    if (inst.slowSpeedToggleEl) inst.slowSpeedToggleEl.style.display = "none";
    if (inst.slowSpeedCheckboxLabel) inst.slowSpeedCheckboxLabel.style.display = "none";
    const trex = inst.tRex;
    if (trex && trex.config && !inst.playingIntro && !trex.playingIntro) {
      trex.xInitialPos = trex.config.startXPos;
      trex.xPos = trex.config.startXPos;
    }
    if (typeof inst.setArcadeMode === "function" && inst.isArcadeMode && inst.isArcadeMode()) {
      inst.setArcadeMode();
    }
    const el = inst.containerEl;
    if (el) {
      const match = /scale\\(([-\\d.]+)/.exec(el.style.transform || "");
      const internatScale = match ? Number(match[1]) : 1;
      if (!(internatScale > 1.15)) {
        const cssW = el.offsetWidth || (inst.dimensions && inst.dimensions.width) || 600;
        const cssH = el.offsetHeight || (inst.dimensions && inst.dimensions.height) || 150;
        const scale = Math.max(
          1,
          Math.min(window.innerWidth / cssW, (window.innerHeight * 0.48) / cssH)
        );
        el.style.transformOrigin = "center center";
        el.style.transform = "scale(" + scale + ")";
      }
    }
  } catch (err) {}
  return true;
}"""

RESUME_JS = """() => {
  const inst = Runner.getInstance();
  if (!inst || inst.crashed || inst.playingIntro || !inst.activated) {
    return { ok: false };
  }
  if (inst.playing && inst.raqId) {
    return { ok: true, resumed: false };
  }
  inst.paused = false;
  inst.setPlayStatus(true);
  inst.time = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
  if (!inst.raqId) inst.update();
  return { ok: true, resumed: true, playing: !!inst.playing, raqId: inst.raqId };
}"""


def _kind(obstacle: dict[str, Any]) -> str:
    raw = str(obstacle.get("kind") or obstacle.get("type") or "")
    if raw == "pterodactyl":
        return "pterodactyl"
    if raw == "collectable":
        return "collectable"
    if raw.startswith("cactus"):
        return "cactus"
    return raw or "other"


class ChromeDino:
    """Headed Chromium session on chrome://dino/."""

    def __init__(
        self,
        *,
        headed: bool = True,
        speed_cap: float | None = 9.0,
        chrome_channel: str = "chrome",
        fullscreen: bool = True,
        window_size: tuple[int, int] | None = None,
        in_page_control: bool = True,
        lead_frames: int = 8,
        provider: str | None = None,
    ) -> None:
        self.headed = headed
        self.speed_cap = speed_cap
        self.chrome_channel = chrome_channel
        self.fullscreen = fullscreen and headed
        self.window_size = window_size or (1920, 1200)
        self.in_page_control = in_page_control
        self.lead_frames = lead_frames
        self.provider = provider or ("heuristic" if in_page_control else "jev")
        self.last_intent: Intent | None = None
        width, height = self.window_size
        launch_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            f"--window-size={width},{height}",
            "--window-position=0,0",
        ]
        if self.fullscreen:
            launch_args.append("--start-fullscreen")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            channel=chrome_channel,
            headless=not headed,
            args=launch_args,
        )
        if self.fullscreen:
            self._context = self._browser.new_context(no_viewport=True)
        else:
            self._context = self._browser.new_context(
                viewport={"width": width, "height": min(height, 800)}
            )
        self._page = self._context.new_page()
        self._cdp = self._page.context.new_cdp_session(self._page)
        self._duck_held = False
        self._last_state: dict[str, Any] | None = None
        self._open_dino()

    def _open_dino(self) -> None:
        try:
            self._page.goto(DINO_URL, wait_until="commit", timeout=8000)
        except Error as exc:
            message = str(exc)
            if "ERR_INTERNET_DISCONNECTED" not in message and "chrome://dino" not in message:
                raise
        self._page.wait_for_function(
            "() => typeof Runner !== 'undefined' && typeof Runner.getInstance === 'function'",
            timeout=8000,
        )
        self._page.evaluate(PATCH_DT_JS)
        self._page.evaluate(BOT_JS)
        self._set_bot_control(self.in_page_control, self.provider, self.lead_frames)
        self._page.evaluate(PREP_PAGE_JS)
        self._enter_fullscreen()
        self._page.evaluate(ARCADE_JS)
        try:
            self._page.locator("canvas").first.click(timeout=2000)
        except Error:
            pass

    def _enter_fullscreen(self) -> None:
        if not self.fullscreen:
            return
        try:
            window = self._cdp.send("Browser.getWindowForTarget")
            self._cdp.send(
                "Browser.setWindowBounds",
                {"windowId": window["windowId"], "bounds": {"windowState": "fullscreen"}},
            )
        except Exception:
            pass
        try:
            self._page.evaluate(
                """() => {
                  const root = document.documentElement;
                  if (root && root.requestFullscreen) root.requestFullscreen().catch(() => {});
                }"""
            )
        except Exception:
            pass

    def _set_bot_control(self, enabled: bool, provider: str, lead_frames: int | None = None) -> None:
        self.in_page_control = enabled
        self.provider = provider
        if lead_frames is not None:
            self.lead_frames = lead_frames
        self._page.evaluate(BOT_JS)
        self._page.evaluate(
            """({enabled, provider, leadFrames}) => {
              const jev = window.__dinoJev;
              if (!jev) return false;
              jev.enabled = !!enabled;
              jev.provider = provider;
              jev.config = jev.config || {};
              if (leadFrames != null) jev.config.leadFrames = leadFrames;
              return true;
            }""",
            {
                "enabled": enabled,
                "provider": provider,
                "leadFrames": self.lead_frames,
            },
        )

    def set_control(self, policy: str) -> None:
        self._set_bot_control(policy == "heuristic", policy, self.lead_frames)

    def _key(self, key_code: int, down: bool) -> None:
        name = " " if key_code == KEY_JUMP else "ArrowDown"
        code = "Space" if key_code == KEY_JUMP else "ArrowDown"
        payload = {
            "type": "keyDown" if down else "keyUp",
            "windowsVirtualKeyCode": key_code,
            "nativeVirtualKeyCode": key_code,
            "code": code,
            "key": name,
        }
        if key_code == KEY_JUMP and down:
            payload["text"] = " "
            payload["unmodifiedText"] = " "
        self._cdp.send("Input.dispatchKeyEvent", payload)

    def _tap_jump(self) -> None:
        if self._duck_held:
            self._key(KEY_DUCK, False)
            self._duck_held = False
        self._key(KEY_JUMP, True)
        self._key(KEY_JUMP, False)

    def _set_duck(self, duck: bool) -> None:
        if duck and not self._duck_held:
            self._key(KEY_DUCK, True)
            self._duck_held = True
        elif not duck and self._duck_held:
            self._key(KEY_DUCK, False)
            self._duck_held = False

    def start_run(self) -> None:
        self._set_duck(False)
        self._page.evaluate(
            """() => {
              const inst = Runner.getInstance();
              if (inst && inst.slowSpeedCheckbox) inst.slowSpeedCheckbox.checked = false;
            }"""
        )
        status = self._page.evaluate(START_JS)
        activated = bool(status and status.get("activated") and (status.get("x") or 0) >= 40)
        if not activated:
            self._tap_jump()
            try:
                self._page.wait_for_function(
                    """() => {
                      const inst = Runner.getInstance();
                      return !!(
                        inst &&
                        inst.activated &&
                        inst.tRex &&
                        inst.tRex.xPos >= 40 &&
                        !inst.playingIntro
                      );
                    }""",
                    timeout=4000,
                )
            except Error:
                self._page.evaluate(FORCE_ACTIVATE_JS)
        if self.speed_cap:
            self._page.evaluate(CAP_SPEED_JS, self.speed_cap)
        self._page.evaluate(ARCADE_JS)
        self._page.evaluate(RESUME_JS)
        self._set_bot_control(self.in_page_control, self.provider, self.lead_frames)

    def restart(self) -> None:
        self._set_duck(False)
        self._page.evaluate(
            """() => {
              const inst = Runner.getInstance();
              if (inst) inst.restart();
            }"""
        )
        if self.speed_cap:
            self._page.evaluate(CAP_SPEED_JS, self.speed_cap)
        self._page.evaluate(ARCADE_JS)
        self._page.evaluate(RESUME_JS)
        self._set_bot_control(self.in_page_control, self.provider, self.lead_frames)

    def close(self) -> None:
        self._set_duck(False)
        self._browser.close()
        self._playwright.stop()

    def observe(self) -> dict[str, Any]:
        self._page.evaluate(RESUME_JS)
        raw = self._page.evaluate(SNAPSHOT_JS, self.speed_cap)
        if not raw or not raw.get("ok"):
            raise RuntimeError(raw.get("error") if raw else "dino snapshot failed")
        obstacles = []
        for item in raw.get("obstacles") or []:
            packed = dict(item)
            packed["kind"] = _kind(packed)
            packed["clearance"] = obstacle_clearance(packed)
            obstacles.append(packed)
        nearest = obstacles[0] if obstacles else None
        dino = raw.get("dino") or {}
        observation = {
            "goal": GOAL,
            "run": {
                "playing": bool(raw.get("playing")),
                "crashed": bool(raw.get("crashed")),
                "intro": bool(raw.get("intro")),
                "speed": round(float(raw.get("speed") or 0), 3),
                "score": int(raw.get("score") or 0),
                "distance_ran": round(float(raw.get("distanceRan") or 0), 1),
                "speed_cap": self.speed_cap,
            },
            "dino": {
                "x": dino.get("x"),
                "y": dino.get("y"),
                "ground_y": dino.get("ground_y"),
                "width": dino.get("width"),
                "height": dino.get("height"),
                "jumping": bool(dino.get("jumping")),
                "ducking": bool(dino.get("ducking")),
            },
            "nearest_obstacle": nearest,
            "obstacles": obstacles,
            "last_action": None if self.last_intent is None else self.last_intent.action,
        }
        self._last_state = observation
        return observation

    def apply(self, intent: Intent) -> None:
        self.last_intent = intent
        payload = intent.hud_payload()
        in_page = self.in_page_control and intent.provider == "heuristic"
        payload["set_action"] = not in_page
        if in_page:
            self._page.evaluate(HUD_JS, payload)
            return
        self._page.evaluate(APPLY_JS, payload)
        self._duck_held = payload["action"] == "duck"

    def screenshot_png(self) -> bytes | None:
        return None

    def hud_note(self, text: str) -> None:
        self._page.evaluate(
            HUD_JS,
            {
                "provider": self.provider,
                "action": "run",
                "asked": text,
                "note": text,
                "set_action": False,
            },
        )
