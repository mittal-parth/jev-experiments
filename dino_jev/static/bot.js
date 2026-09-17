(() => {
  const GRAVITY = 0.6;
  const INITIAL_JUMP_VELOCITY = -10;
  const DROP_VELOCITY = -5;
  const MAX_JUMP_HEIGHT_Y = 30;
  const DINO_W = 44;
  const DINO_H = 47;
  const DINO_DUCK_W = 59;
  const DINO_DUCK_H = 25;
  const LEAD_FRAMES = 8;
  const STAND_HORIZON = 55;
  const JUMP_HORIZON = 80;

  const jev = (window.__dinoJev = window.__dinoJev || {});
  if (jev._installed) return true;
  jev.enabled = false;
  jev.provider = "heuristic";
  jev.action = "run";
  jev.score = 0;
  jev.speed = 0;
  jev.gap = null;
  jev._hudAt = 0;

  function hit(dx, dy, dw, dh, ox, oy, ow, oh) {
    return (
      dx + 1 < ox + ow - 1 &&
      dx + dw - 1 > ox + 1 &&
      dy + 1 < oy + oh - 1 &&
      dy + dh - 1 > oy + 1
    );
  }

  function jumpYs(speed, groundY, n) {
    let velocity = INITIAL_JUMP_VELOCITY - speed / 10;
    let y = groundY;
    let landed = false;
    const positions = [];
    for (let i = 0; i < n; i += 1) {
      if (landed) {
        positions.push(groundY);
        continue;
      }
      y += Math.round(velocity);
      velocity += GRAVITY;
      if (y < MAX_JUMP_HEIGHT_Y && velocity < DROP_VELOCITY) velocity = DROP_VELOCITY;
      if (y > groundY) {
        y = groundY;
        landed = true;
      }
      positions.push(y);
    }
    return positions;
  }

  function firstHit(obstacles, speed, dinoX, dinoY, dinoW, dinoH, maxFrames) {
    for (let frame = 1; frame <= maxFrames; frame += 1) {
      for (const obs of obstacles) {
        const ox = obs.x - speed * frame;
        if (ox + obs.w < dinoX) continue;
        if (hit(dinoX, dinoY, dinoW, dinoH, ox, obs.y, obs.w, obs.h)) return frame;
      }
    }
    return null;
  }

  function jumpClears(obstacles, speed, dinoX, groundY) {
    const ys = jumpYs(speed, groundY, JUMP_HORIZON);
    for (let i = 0; i < ys.length; i += 1) {
      const frame = i + 1;
      const y = ys[i];
      let pastAll = true;
      for (const obs of obstacles) {
        const ox = obs.x - speed * frame;
        if (ox + obs.w >= dinoX) pastAll = false;
        if (hit(dinoX, y, DINO_W, DINO_H, ox, obs.y, obs.w, obs.h)) return false;
      }
      if (pastAll) return true;
    }
    return true;
  }

  function packObstacles(inst) {
    const trex = inst.tRex;
    const raw = (inst.horizon && inst.horizon.obstacles) || [];
    const out = [];
    for (const obstacle of raw) {
      if (!obstacle) continue;
      const width = obstacle.width || (obstacle.typeConfig && obstacle.typeConfig.width) || 0;
      if (obstacle.xPos + width <= trex.xPos) continue;
      const type = (obstacle.typeConfig && obstacle.typeConfig.type) || "";
      const height = (obstacle.typeConfig && obstacle.typeConfig.height) || 35;
      out.push({
        x: obstacle.xPos,
        y: obstacle.yPos,
        w: width,
        h: height,
        type,
        kind: type === "pterodactyl" ? "pterodactyl" : type.indexOf("cactus") === 0 ? "cactus" : "other",
      });
      if (out.length >= 3) break;
    }
    return out;
  }

  function clearance(obs) {
    if (!obs) return "clear";
    if (obs.kind === "pterodactyl") {
      if (obs.y <= 51) return "high";
      if (obs.y <= 76) return "mid";
      return "low";
    }
    if (obs.kind === "collectable") return "clear";
    return "ground";
  }

  function decide(inst) {
    const trex = inst.tRex;
    if (!trex || trex.jumping || inst.crashed || inst.playingIntro || !inst.playing) return "run";
    const obstacles = packObstacles(inst);
    if (!obstacles.length) return "run";
    const speed = inst.currentSpeed;
    const dinoX = trex.xPos;
    const groundY = trex.groundYPos;
    const nearest = obstacles[0];
    const how = clearance(nearest);
    if (how === "high" || how === "clear") return "run";
    if (how === "mid") {
      const stand = firstHit(obstacles, speed, dinoX, groundY, DINO_W, DINO_H, 18);
      const duckHit = firstHit(
        obstacles,
        speed,
        dinoX,
        groundY + (DINO_H - DINO_DUCK_H),
        DINO_DUCK_W,
        DINO_DUCK_H,
        12
      );
      if (stand !== null && duckHit === null) return "duck";
      return "run";
    }
    const standHit = firstHit(obstacles, speed, dinoX, groundY, DINO_W, DINO_H, STAND_HORIZON);
    if (standHit === null) return "run";
    const delayed = obstacles.map((obs) => ({ ...obs, x: obs.x - speed }));
    if (jumpClears(obstacles, speed, dinoX, groundY)) {
      if (standHit <= LEAD_FRAMES || !jumpClears(delayed, speed, dinoX, groundY)) return "jump";
      return "run";
    }
    if (standHit <= 2) return "jump";
    return "run";
  }

  function act(inst, action) {
    const trex = inst.tRex;
    if (action === "jump" && !trex.jumping && !trex.ducking) {
      trex.startJump(inst.currentSpeed);
    } else if (action === "duck" && !trex.jumping) {
      trex.setDuck(true);
    } else if (action === "run" && trex.ducking) {
      trex.setDuck(false);
    }
    jev.action = action;
  }

  function paintHud(inst) {
    const now = performance.now();
    if (now - jev._hudAt < 80 && jev._el) return;
    jev._hudAt = now;
    let el = jev._el || document.getElementById("dino-jev-hud");
    if (!el) {
      el = document.createElement("div");
      el.id = "dino-jev-hud";
      el.style.cssText = [
        "position:fixed",
        "top:16px",
        "left:16px",
        "z-index:99999",
        "font:15px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace",
        "background:rgba(7,9,13,0.88)",
        "color:#e8edf5",
        "padding:12px 14px",
        "border-radius:12px",
        "border:1px solid #243044",
        "max-width:440px",
        "pointer-events:none",
      ].join(";");
      document.documentElement.appendChild(el);
      jev._el = el;
    }
    const provider = jev.provider || "heuristic";
    const color = provider === "jev" ? "#3ee0c5" : "#ff6a00";
    const trex = inst && inst.tRex;
    const nearest = inst ? packObstacles(inst)[0] : null;
    const width = trex ? (trex.ducking ? trex.config.widthDuck : trex.config.width) : DINO_W;
    const gap = nearest && trex ? Math.round(nearest.x - trex.xPos - width) : null;
    let score = inst ? Math.round((inst.distanceRan || 0) * 0.025) : jev.score;
    try {
      if (inst && inst.distanceMeter && inst.distanceMeter.getActualDistance) {
        score = inst.distanceMeter.getActualDistance(inst.distanceRan);
      }
    } catch (err) {}
    jev.score = score;
    jev.speed = inst ? inst.currentSpeed : 0;
    jev.gap = gap;
    const gapText = nearest ? gap + "px " + nearest.kind + "/" + clearance(nearest) : "clear";
    el.innerHTML = [
      '<div style="letter-spacing:0.12em;text-transform:uppercase;font-size:10px;color:#8b97ab">Dino-Jev · same window · no pixels</div>',
      '<div><span style="display:inline-block;padding:1px 8px;border-radius:999px;background:' +
        color +
        "22;color:" +
        color +
        '">' +
        provider +
        "</span> " +
        (jev.action || "run") +
        "</div>",
      "<div>score <b>" + score + "</b>  speed " + (inst ? inst.currentSpeed.toFixed(2) : "0") + "</div>",
      "<div>gap " + gapText + "</div>",
      "<div>control " + (jev.enabled ? "internat 60fps boxes" : "python tick") + "</div>",
    ].join("");
  }

  jev.tick = function tick(inst) {
    if (!jev.enabled || jev.provider !== "heuristic") return;
    if (!inst || !inst.playing || inst.crashed || inst.playingIntro) return;
    act(inst, decide(inst));
  };

  jev.paintHud = paintHud;
  jev._installed = true;

  const inst = typeof Runner !== "undefined" && Runner.getInstance && Runner.getInstance();
  if (inst && !inst._jevBotWrapped) {
    const prev = inst.update.bind(inst);
    inst.update = function botUpdate() {
      if (window.__dinoJev) {
        window.__dinoJev.tick(this);
        window.__dinoJev.paintHud(this);
      }
      return prev();
    };
    inst._jevBotWrapped = true;
  }
  return true;
})();
