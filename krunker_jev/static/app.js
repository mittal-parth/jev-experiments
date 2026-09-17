const arena = document.getElementById("arena");
const ctx = arena.getContext("2d");
const hud = document.getElementById("hud");
const statusEl = document.getElementById("status");
const intentEl = document.getElementById("intent");
const probsEl = document.getElementById("probs");
const stateEl = document.getElementById("state");
const policyEl = document.getElementById("policy");

async function control(action) {
  const response = await fetch("/api/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, policy: policyEl.value }),
  });
  const payload = await response.json();
  render(payload);
  if (!response.ok) {
    statusEl.textContent = payload.error || "request failed";
  }
}

document.getElementById("start").onclick = () => control("start");
document.getElementById("stop").onclick = () => control("stop");
document.getElementById("reset").onclick = () => control("reset");
document.getElementById("step").onclick = () => control("step");

function barRow(label, value, winner) {
  const pct = Math.round((value || 0) * 100);
  return `<div class="bar ${winner ? "win" : ""}"><b>${label}</b><span class="track"><i style="width:${pct}%"></i></span><span>${pct}%</span></div>`;
}

function draw(snapshot) {
  const { width, height, grid, player, enemies, shots } = snapshot;
  const scaleX = arena.width / width;
  const scaleY = arena.height / height;
  ctx.fillStyle = "#0c1118";
  ctx.fillRect(0, 0, arena.width, arena.height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (grid[y][x] !== "#") continue;
      ctx.fillStyle = "#243044";
      ctx.fillRect(x * scaleX, y * scaleY, scaleX + 0.5, scaleY + 0.5);
    }
  }
  const yaw = (player.yaw * Math.PI) / 180;
  ctx.fillStyle = "rgba(62, 224, 197, 0.12)";
  ctx.beginPath();
  ctx.moveTo(player.x * scaleX, player.y * scaleY);
  ctx.arc(
    player.x * scaleX,
    player.y * scaleY,
    7.4 * scaleX,
    yaw - 0.87,
    yaw + 0.87,
  );
  ctx.closePath();
  ctx.fill();
  function actor(item, color) {
    if (!item.alive) return;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(item.x * scaleX, item.y * scaleY, 0.42 * scaleX, 0, Math.PI * 2);
    ctx.fill();
    const rad = (item.yaw * Math.PI) / 180;
    ctx.strokeStyle = color;
    ctx.beginPath();
    ctx.moveTo(item.x * scaleX, item.y * scaleY);
    ctx.lineTo(
      (item.x + Math.cos(rad) * 1.3) * scaleX,
      (item.y + Math.sin(rad) * 1.3) * scaleY,
    );
    ctx.stroke();
  }
  actor(player, "#3ee0c5");
  enemies.forEach((enemy) => actor(enemy, "#ff6a00"));
  shots.forEach((shot) => {
    ctx.strokeStyle = shot.hit ? "#7cff6b" : "#ff4d6a";
    ctx.beginPath();
    ctx.moveTo(shot.x0 * scaleX, shot.y0 * scaleY);
    ctx.lineTo(shot.x1 * scaleX, shot.y1 * scaleY);
    ctx.stroke();
  });
}

function render(snapshot) {
  if (!snapshot.player) return;
  draw(snapshot);
  const player = snapshot.player;
  const intent = snapshot.last_intent;
  const provider = intent?.provider || snapshot.policy;
  hud.innerHTML = `
    <div>HP <b>${Math.max(0, player.health | 0)}</b></div>
    <div>Ammo <b>${player.mag}/${player.reserve}</b></div>
    <div>K/D <b>${player.kills}/${player.deaths}</b></div>
    <div>Tick <b>${snapshot.ticks ?? 0}</b></div>
    <div>Latency <b>${intent ? Math.round(intent.latency_ms) + " ms" : "—"}</b></div>
  `;
  statusEl.innerHTML = snapshot.error
    ? snapshot.error
    : `${snapshot.running ? "running" : "idle"} · <span class="pill ${provider}">${provider}</span>`;
  if (!intent) {
    intentEl.innerHTML = "<p>No decision yet. Start or step the match.</p>";
    probsEl.innerHTML = "";
  } else {
    intentEl.innerHTML = `
      <p>
        <span class="pill">${intent.stance}</span>
        <span class="pill">${intent.move}</span>
        <span class="pill">aim ${intent.aim}</span>
        <span class="pill">${intent.fire ? "FIRE" : "hold fire"}</span>
        ${intent.reload ? '<span class="pill">reload</span>' : ""}
        ${intent.jump ? '<span class="pill">jump</span>' : ""}
      </p>
      <p>threat ${intent.threat == null ? "—" : intent.threat.toFixed(2)} · stance conf ${(intent.confidence.stance || 0).toFixed(2)}</p>
    `;
    const groups = intent.probabilities || {};
    probsEl.innerHTML = Object.entries(groups)
      .map(([name, dist]) => {
        const winner = intent[name === "aim_target" ? "aim" : name];
        const rows = Object.entries(dist)
          .sort((a, b) => b[1] - a[1])
          .map(([label, value]) => barRow(label, value, label === winner))
          .join("");
        return `<h2>${name}</h2><div class="bars">${rows}</div>`;
      })
      .join("");
    const nouls = intent.nouls || {};
    probsEl.innerHTML += `<h2>nouls</h2><div class="bars">${Object.entries(nouls)
      .map(([label, value]) => barRow(label, value, value >= 0.55))
      .join("")}</div>`;
  }
  const observation = snapshot.observation || {};
  stateEl.textContent = JSON.stringify(
    {
      self: observation.self,
      visible_enemies: observation.visible_enemies,
      nearby_cover: observation.nearby_cover,
      recent_events: observation.recent_events,
    },
    null,
    2,
  );
  if (snapshot.policy) policyEl.value = snapshot.policy;
}

async function poll() {
  try {
    const response = await fetch("/api/snapshot");
    render(await response.json());
  } catch (error) {
    statusEl.textContent = String(error);
  }
}

poll();
setInterval(poll, 120);
