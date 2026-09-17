const hud = document.getElementById("hud");
const statusEl = document.getElementById("status");
const intentEl = document.getElementById("intent");
const probsEl = document.getElementById("probs");
const stateEl = document.getElementById("state");
const policyEl = document.getElementById("policy");
const frameEl = document.getElementById("frame");

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

function render(snapshot) {
  const run = snapshot.run || {};
  const intent = snapshot.last_intent || {};
  const provider = intent.provider || snapshot.policy || "idle";
  const pillClass = provider === "jev" ? "jev" : "heuristic";
  const mode = snapshot.running ? "running" : "idle";
  hud.innerHTML = `
    <span class="pill ${pillClass}">${provider}</span>
    <span>score <b>${run.score ?? 0}</b></span>
    <span>speed <b>${run.speed ?? 0}</b></span>
    <span>ticks <b>${snapshot.ticks ?? 0}</b></span>
    <span>best <b>${snapshot.best_score ?? 0}</b></span>
  `;
  statusEl.textContent = snapshot.error
    ? `${mode} · ${snapshot.error}`
    : `${mode} · ${provider}`;
  if (policyEl.value !== snapshot.policy && snapshot.policy) {
    policyEl.value = snapshot.policy;
  }
  const action = intent.action || "run";
  const nouls = intent.nouls || {};
  intentEl.innerHTML = `
    <p>action <b>${action}</b> · jump ${intent.jump ? "yes" : "no"} · duck ${intent.duck ? "yes" : "no"}</p>
    <p>urgency <b>${(intent.urgency ?? 0).toFixed(2)}</b> · ${intent.latency_ms ?? 0} ms</p>
  `;
  const actionProbs = (intent.probabilities && intent.probabilities.action) || {};
  probsEl.innerHTML = `<div class="bars">
    ${barRow("run", actionProbs.run, action === "run")}
    ${barRow("jump", actionProbs.jump, action === "jump")}
    ${barRow("duck", actionProbs.duck, action === "duck")}
    ${barRow("jump_now", nouls.jump_now, intent.jump)}
    ${barRow("duck_now", nouls.duck_now, intent.duck)}
  </div>`;
  const compact = {
    run,
    dino: snapshot.dino,
    nearest_obstacle: snapshot.nearest_obstacle,
  };
  stateEl.textContent = JSON.stringify(compact, null, 2);
}

async function poll() {
  try {
    const response = await fetch("/api/snapshot");
    const payload = await response.json();
    render(payload);
    frameEl.src = `/api/frame.png?t=${Date.now()}`;
  } catch (err) {
    statusEl.textContent = "inspector unreachable";
  }
}

poll();
setInterval(poll, 400);
