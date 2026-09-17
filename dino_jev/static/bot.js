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
  jev.config = { leadFrames: LEAD_FRAMES, lastChanceFrames: 2 };
  jev.externalAction = null;

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
      if (out.length >= 5) break;
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

  function duckBoxHitsNow(obstacles, dinoX, groundY) {
    const duckY = groundY + (DINO_H - DINO_DUCK_H);
    for (const obs of obstacles) {
      if (hit(dinoX, duckY, DINO_DUCK_W, DINO_DUCK_H, obs.x, obs.y, obs.w, obs.h)) return true;
    }
    return false;
  }

  function midBirdBlocking(nearest, dinoX, dinoW) {
    return nearest && nearest.x + nearest.w >= dinoX + dinoW - 4;
  }

  function adaptiveLead(lead, speed) {
    return Math.max(4, Math.min(lead, Math.round(lead - Math.max(0, speed - 6.5) * 2.1)));
  }

  function duckClearsMid(obstacles, speed, dinoX, groundY) {
    const duckY = groundY + (DINO_H - DINO_DUCK_H);
    return firstHit(obstacles, speed, dinoX, duckY, DINO_DUCK_W, DINO_DUCK_H, 24) === null;
  }

  function decide(inst) {
    const trex = inst.tRex;
    if (!trex || trex.jumping || inst.crashed || inst.playingIntro || !inst.playing) return "run";
    const obstacles = packObstacles(inst);
    if (!obstacles.length) {
      if (trex.ducking) {
        jev._duckClear = (jev._duckClear || 0) + 1;
        if (jev._duckClear < 5) return "duck";
        jev._duckClear = 0;
      }
      return "run";
    }
    jev._duckClear = 0;
    const speed = inst.currentSpeed;
    const dinoX = trex.xPos;
    const groundY = trex.groundYPos;
    if (trex.ducking) {
      const nearest = obstacles[0];
      if (nearest && clearance(nearest) === "mid") {
        const tail = nearest.x + nearest.w;
        if (tail > dinoX + 8) return "duck";
      }
      return "run";
    }
    const nearest = obstacles[0];
    const how = clearance(nearest);
    if (how === "high" || how === "clear") return "run";
    if (how === "mid") {
      const lead = adaptiveLead((jev.config && jev.config.leadFrames) || LEAD_FRAMES, speed);
      const horizon = Math.max(22, Math.round(lead + speed * 0.35));
      const stand = firstHit(obstacles, speed, dinoX, groundY, DINO_W, DINO_H, horizon);
      const closeEnough = stand !== null && stand <= lead;
      if (
        closeEnough &&
        !duckBoxHitsNow(obstacles, dinoX, groundY) &&
        duckClearsMid(obstacles, speed, dinoX, groundY)
      ) {
        return "duck";
      }
      return "run";
    }
    const standHit = firstHit(obstacles, speed, dinoX, groundY, DINO_W, DINO_H, STAND_HORIZON);
    if (standHit === null) return "run";
    const lead = adaptiveLead((jev.config && jev.config.leadFrames) || LEAD_FRAMES, speed);
    const lastChance = (jev.config && jev.config.lastChanceFrames) || 2;
    const delayed = obstacles.map((obs) => ({ ...obs, x: obs.x - speed }));
    if (jumpClears(obstacles, speed, dinoX, groundY)) {
      if (standHit <= lead || !jumpClears(delayed, speed, dinoX, groundY)) return "jump";
      return "run";
    }
    if (standHit <= lastChance) return "jump";
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

  function bar(label, value, win, color) {
    const p = Math.max(0, Math.min(100, Math.round((Number(value) || 0) * 100)));
    return (
      '<div style="display:grid;grid-template-columns:78px 1fr 34px;gap:6px;align-items:center;font-size:12px;margin:2px 0">' +
      "<span>" +
      label +
      "</span>" +
      '<span style="height:7px;background:#1b2433;border-radius:99px;overflow:hidden"><i style="display:block;height:100%;width:' +
      p +
      "%;background:" +
      (win ? "#ff6a00" : color) +
      '"></i></span>' +
      "<span>" +
      p +
      "</span></div>"
    );
  }

  function paintHud(inst) {
    const now = performance.now();
    const seq = jev._replySeq || 0;
    const prevSeq = jev._paintedReply || 0;
    if (now - jev._hudAt < 50 && jev._el && prevSeq === seq) return;
    if (prevSeq !== seq) jev._flashUntil = now + 240;
    jev._hudAt = now;
    jev._paintedReply = seq;
    let el = jev._el || document.getElementById("dino-jev-hud");
    if (!el) {
      el = document.createElement("div");
      el.id = "dino-jev-hud";
      el.style.cssText = [
        "position:fixed",
        "top:auto",
        "right:auto",
        "bottom:16px",
        "left:16px",
        "z-index:99999",
        "font:13px/1.35 ui-monospace, SFMono-Regular, Menlo, monospace",
        "background:rgba(7,9,13,0.9)",
        "color:#e8edf5",
        "padding:10px 12px",
        "border-radius:12px",
        "border:1px solid #243044",
        "max-width:360px",
        "pointer-events:none",
      ].join(";");
      document.documentElement.appendChild(el);
      jev._el = el;
    }
    el.style.top = "auto";
    el.style.right = "auto";
    el.style.bottom = "16px";
    el.style.left = "16px";
    const provider = jev.provider || "heuristic";
    const color = provider === "jev" ? "#3ee0c5" : "#ff6a00";
    el.style.borderColor = jev._flashUntil && now < jev._flashUntil ? color : "#243044";
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
    const reply = jev.reply;
    const asked = reply && reply.asked ? reply.asked : jev.action || "run";
    const exec = jev.action || (reply && reply.action) || "run";
    const gated = !!(reply && reply.gated);
    const latency = reply && reply.latency_ms != null ? Math.round(reply.latency_ms) + "ms" : "—";
    const conf = reply && reply.confidence != null ? Math.round(reply.confidence * 100) + "%" : "—";
    const lines = [
      '<div style="letter-spacing:0.12em;text-transform:uppercase;font-size:10px;color:#8b97ab">Dino-Jev · live TypeSafe · no pixels</div>',
      '<div><span style="display:inline-block;padding:1px 8px;border-radius:999px;background:' +
        color +
        "22;color:" +
        color +
        '">' +
        provider +
        "</span> ask <b>" +
        asked +
        "</b> · do <b>" +
        exec +
        "</b>" +
        (gated ? ' <span style="color:#ff6a00">gated</span>' : "") +
        "  " +
        latency +
        "  #" +
        seq +
        "</div>",
      "<div>score <b>" +
        score +
        "</b>  speed " +
        (inst ? inst.currentSpeed.toFixed(2) : "0") +
        "  gap " +
        gapText +
        "</div>",
    ];
    if (reply && reply.note) {
      lines.push('<div style="color:#c5d0e0">' + reply.note + "</div>");
    }
    if (reply && (reply.run_p != null || reply.jump_p != null || reply.duck_p != null)) {
      lines.push(
        bar("run", reply.run_p, asked === "run", color),
        bar("jump", reply.jump_p, asked === "jump", color),
        bar("duck", reply.duck_p, asked === "duck", color),
        bar("jump_now", reply.jump_now, exec === "jump", color),
        bar("duck_now", reply.duck_now, exec === "duck", color),
        "<div style='font-size:12px;color:#c5d0e0'>urgency " +
          (reply.urgency ?? "—") +
          "  conf " +
          conf +
          "</div>"
      );
    } else if (!reply || reply.note) {
      lines.push("<div style='color:#8b97ab'>waiting for " + provider + "…</div>");
    }
    el.innerHTML = lines.join("");
  }

  function executionAction(inst) {
    const trex = inst.tRex;
    let action = decide(inst);
    if (jev.provider !== "jev" || !trex || trex.jumping) return action;
    const reply = jev.reply;
    const obstacles = packObstacles(inst);
    const nearest = obstacles[0];
    const how = nearest ? clearance(nearest) : "clear";
    const wantsDuck =
      reply &&
      (reply.duck === true ||
        reply.action === "duck" ||
        reply.asked === "duck" ||
        Number(reply.duck_now) >= 0.55);
    if (wantsDuck && how === "mid") action = "duck";
    if (trex.ducking && nearest && clearance(nearest) === "mid" && nearest.x + nearest.w > trex.xPos + 8) {
      action = "duck";
    }
    return action;
  }

  jev.tick = function tick(inst) {
    if (!jev.enabled) return;
    if (jev.provider === "jev") {
      if (!inst || !inst.playing || inst.crashed || inst.playingIntro) return;
      const trex = inst.tRex;
      if (trex && trex.jumping) {
        jev.action = "jump";
        return;
      }
      act(inst, executionAction(inst));
      return;
    }
    if (jev.provider !== "heuristic") return;
    if (!inst || !inst.playing || inst.crashed || inst.playingIntro) return;
    const trex = inst.tRex;
    if (trex && trex.config && !trex.playingIntro) {
      trex.xInitialPos = trex.config.startXPos;
    }
    if (trex && trex.jumping) {
      jev.action = "jump";
      return;
    }
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
      }
      const out = prev();
      if (window.__dinoJev) {
        window.__dinoJev.paintHud(this);
      }
      return out;
    };
    inst._jevBotWrapped = true;
  }
  return true;
})();
