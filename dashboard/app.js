const statusUrl = "../health/nanobot_full_status.json";

function text(value, fallback = "...") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function yes(value) {
  return value ? "OK" : "NON";
}

function cls(value) {
  return value ? "oktext" : "badtext";
}

function set(id, value, className = "") {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value;
  el.className = className;
}

function row(label, value, className = "") {
  return `<div class="row"><span>${label}</span><span class="${className}">${value}</span></div>`;
}

async function loadStatus() {
  let data;
  try {
    const response = await fetch(`${statusUrl}?t=${Date.now()}`, { cache: "no-store" });
    data = await response.json();
  } catch (error) {
    set("overallStatus", "JSON absent", "status-pill warn");
    return;
  }

  const counts = data.process_counts || {};
  const ports = data.ports || {};
  const pc = data.pc || {};
  const idx = data.index || {};
  const config = data.config || {};
  const tasks = data.tasks || [];

  const ok = data.mission_yolo && data.agent_v2 && data.ollama_ok && counts.gateway > 0 && counts.supervisor > 0 && counts.watchdog > 0;
  set("overallStatus", ok ? "Operationnel" : "A verifier", `status-pill ${ok ? "ok" : "warn"}`);
  set("mission", data.mission_yolo && data.agent_v2 ? "YOLO + V2" : yes(data.mission_yolo || data.agent_v2), cls(data.mission_yolo && data.agent_v2));
  set("gateway", `${counts.gateway || 0} / ${yes((ports["18790"] || {}).listening)}`, counts.gateway > 0 ? "oktext" : "badtext");
  set("watchdog", text(counts.watchdog || 0), counts.watchdog > 0 ? "oktext" : "badtext");
  set("ollama", yes(data.ollama_ok), cls(data.ollama_ok));

  document.getElementById("systemRows").innerHTML = [
    row("CPU", `${text(pc.cpuPercent)}%`),
    row("RAM libre", `${text(pc.ramFreeGB)} Go / ${text(pc.ramTotalGB)} Go`),
    row("Disque C", `${text(pc.diskCFreeGB)} Go libres / ${text(pc.diskCTotalGB)} Go`),
    row("Dashboard", yes(data.dashboard_ok), cls(data.dashboard_ok)),
    row("Agent V2", yes(data.agent_v2), cls(data.agent_v2)),
    row("Generation", text(data.generated_at)),
  ].join("");

  document.getElementById("taskRows").innerHTML = tasks.map(task => {
    const healthy = task.state !== "Missing" && task.runLevel === "Highest";
    return row(task.name, `${task.state} / ${task.runLevel}`, healthy ? "oktext" : "warntext");
  }).join("");

  document.getElementById("indexRows").innerHTML = [
    row("Base", yes(idx.db_exists), cls(idx.db_exists)),
    row("Fichiers", text(idx.file_count, "0")),
    row("Etat", text(idx.state, "inconnu")),
    row("Derniere fin", text(idx.finished_at, "jamais")),
    row("Racines", (config.filesystemRoots || []).join(", ")),
  ].join("");

  const logs = data.recent_log_signals || [];
  document.getElementById("logRows").innerHTML = logs.length
    ? logs.map(line => `<div class="logline">${line}</div>`).join("")
    : `<div class="logline">Aucun signal recent.</div>`;
}

loadStatus();
setInterval(loadStatus, 15000);
