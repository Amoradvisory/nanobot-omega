from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


OMEGA_ROOT = Path(r"C:\AI\nanobot-omega")
FIRE_ROOT = Path(r"C:\Users\user\Desktop\FIRE")
HEALTH_DIR = OMEGA_ROOT / "health"
JSON_OUT = HEALTH_DIR / "nanobot_full_status.json"
TXT_OUT = HEALTH_DIR / "nanobot_full_status.txt"
CONFIG_PATH = OMEGA_ROOT / "config_omega.json"
INDEX_DB = OMEGA_ROOT / "workspace" / "memory" / "nanobot_file_index.db"
INDEX_STATUS = OMEGA_ROOT / "workspace" / "memory" / "nanobot_file_index_status.json"
DASHBOARD_URL = "http://127.0.0.1:18791/dashboard/"
MISSION_YOLO_PATH = OMEGA_ROOT / "MISSION_YOLO.md"
AGENT_V2_PATH = OMEGA_ROOT / "AGENT_V2.md"
ADMIN_INSTALLER_LAUNCHER = OMEGA_ROOT / "scripts" / "Launch-NanobotAdminModeInstall.bat"
START_GATEWAY = OMEGA_ROOT / "Start-NanobotTelegramGateway.ps1"
START_DASHBOARD = OMEGA_ROOT / "scripts" / "Start-NanobotDashboard.ps1"
FILE_INDEX = OMEGA_ROOT / "scripts" / "nanobot_file_index.py"
OLLAMA_RESTART = FIRE_ROOT / "scripts" / "nanobot_ollama_restart.bat"

DEFAULT_MISSION_YOLO = """# Nanobot Mission YOLO

Nanobot runs on a dedicated PC. The user wants maximum autonomy.

Core behavior:
- Treat each user request as a mission with a concrete outcome.
- Continue until the mission is completed, blocked by a real external limit, or unsafe for Nanobot itself to continue.
- Do not ask for confirmation for ordinary filesystem, shell, browser, desktop, Google Workspace, diagnostic, repair, indexing, or dashboard actions.
- If the first route fails, diagnose the error and try at least one other reasonable route.
- At the end, give a concise result: what was done, where it is, and any real remaining blocker.
"""

DEFAULT_AGENT_V2 = """# Nanobot Agent V2

Agent V2 turns each actionable request into a closed execution loop:

`goal -> short plan -> action -> verification -> repair if needed -> final result`

- Classify simple questions versus executable missions.
- For missions, choose the fastest reliable local route and act with tools.
- Verify every meaningful action.
- If verification fails, classify the error, repair, retry, and verify again.
- Stop only when the success check passes or a real human/UAC/credential blocker remains.
- Final answers are concise and in French.
"""


def run(cmd: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"


def run_detached(cmd: list[str], cwd: Path | str | None = None) -> tuple[bool, str]:
    try:
        subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
            close_fds=True,
        )
        return True, "started"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def run_task(name: str) -> tuple[bool, str]:
    code, out, err = run(["schtasks", "/Run", "/TN", name], timeout=30)
    if code == 0:
        return True, out or "started"
    return False, err or out or f"exit {code}"


def ps_json(script: str, timeout: int = 25):
    code, out, err = run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        timeout=timeout,
    )
    if code != 0 or not out:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except Exception:
        return {}


def http_ok(url: str, timeout: int = 3) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except Exception:
        return False


def port_listening(port: int) -> bool:
    script = f"""
$conn=Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue
[pscustomobject]@{{listening=[bool]$conn}} | ConvertTo-Json
"""
    data = ps_json(script, timeout=8)
    return bool(isinstance(data, dict) and data.get("listening"))


def get_tasks() -> list[dict]:
    names = [
        "NanobotOmegaSupervisorAdmin",
        "NanobotWatchdogAdmin",
        "NanobotSelfHeal",
        "NanobotBackup",
        "NanobotLogRotate",
        "NanobotVeille2ememain",
        "NanobotDashboardAdmin",
        "NanobotFileIndexAdmin",
    ]
    quoted = ",".join("'" + name + "'" for name in names)
    script = f"""
$names=@({quoted})
$rows=@()
foreach($name in $names){{
  $task=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  if($task){{
    $info=$task | Get-ScheduledTaskInfo -ErrorAction SilentlyContinue
    $rows += [pscustomobject]@{{
      name=$task.TaskName
      state=[string]$task.State
      runLevel=[string]$task.Principal.RunLevel
      logonType=[string]$task.Principal.LogonType
      lastRunTime=[string]$info.LastRunTime
      lastTaskResult=[int]$info.LastTaskResult
    }}
  }} else {{
    $rows += [pscustomobject]@{{name=$name; state='Missing'; runLevel=''; logonType=''; lastRunTime=''; lastTaskResult=-1}}
  }}
}}
$rows | ConvertTo-Json -Depth 4
"""
    data = ps_json(script)
    if isinstance(data, dict):
        return [data]
    return data or []


def get_processes() -> dict:
    script = r"""
$rows=Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -and (
    $_.CommandLine -like '*nanobot.exe gateway*' -or
    $_.CommandLine -like '*Run-NanobotOmegaSupervisor.ps1*' -or
    $_.CommandLine -like '*nanobot_watchdog.py*' -or
    $_.CommandLine -like '*http.server*18791*' -or
    $_.CommandLine -like '*nanobot_file_index.py*'
  )
} | Select-Object ProcessId,ParentProcessId,Name,CommandLine
$rows | ConvertTo-Json -Depth 4
"""
    data = ps_json(script)
    if isinstance(data, dict):
        rows = [data]
    else:
        rows = data or []
    return {
        "gateway": [p for p in rows if "nanobot.exe gateway" in (p.get("CommandLine") or "")],
        "supervisor": [p for p in rows if "Run-NanobotOmegaSupervisor.ps1" in (p.get("CommandLine") or "")],
        "watchdog": [p for p in rows if "nanobot_watchdog.py" in (p.get("CommandLine") or "")],
        "dashboard": [p for p in rows if "http.server" in (p.get("CommandLine") or "") and "18791" in (p.get("CommandLine") or "")],
        "indexer": [p for p in rows if "nanobot_file_index.py" in (p.get("CommandLine") or "")],
        "all": rows,
    }


def get_pc_health() -> dict:
    script = r"""
$os=Get-CimInstance Win32_OperatingSystem
$cpu=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
$disk=Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$top=Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 8 Id,ProcessName,@{n='MemoryMB';e={[math]::Round($_.WorkingSet64/1MB,1)}},CPU
[pscustomobject]@{
  cpuPercent=[math]::Round([double]($cpu -as [double]),1)
  ramFreeGB=[math]::Round($os.FreePhysicalMemory/1MB,2)
  ramTotalGB=[math]::Round($os.TotalVisibleMemorySize/1MB,2)
  diskCFreeGB=[math]::Round($disk.FreeSpace/1GB,2)
  diskCTotalGB=[math]::Round($disk.Size/1GB,2)
  topProcesses=$top
} | ConvertTo-Json -Depth 5
"""
    data = ps_json(script)
    return data if isinstance(data, dict) else {}


def get_ports() -> dict:
    script = r"""
$ports=@(11434,18790,18791)
$rows=@()
foreach($port in $ports){
  $conn=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  $rows += [pscustomobject]@{port=$port; listening=[bool]$conn; process=if($conn){$conn[0].OwningProcess}else{0}}
}
$rows | ConvertTo-Json -Depth 3
"""
    data = ps_json(script)
    if isinstance(data, dict):
        data = [data]
    return {str(row.get("port")): row for row in (data or [])}


def index_status() -> dict:
    status = load_json(INDEX_STATUS)
    if INDEX_DB.exists():
        try:
            with sqlite3.connect(INDEX_DB) as conn:
                count = conn.execute("select count(*) from files").fetchone()[0]
            status["db_exists"] = True
            status["file_count"] = count
        except Exception as exc:
            status["db_error"] = str(exc)
    else:
        status["db_exists"] = False
        status.setdefault("file_count", 0)
    return status


def recent_log_signals() -> list[str]:
    log_paths = [
        OMEGA_ROOT / "logs" / "telegram-gateway.err.log",
        OMEGA_ROOT / "logs" / "omega-supervisor.err.log",
        FIRE_ROOT / "logs" / "nanobot_selfheal.log",
        FIRE_ROOT / "logs" / "nanobot_watchdog.log",
    ]
    signals: list[str] = []
    for path in log_paths:
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]
        except Exception:
            continue
        interesting = [
            line for line in lines
            if any(token in line.lower() for token in ("error", "erreur", "fail", "warning", "down", "restart", "heal"))
        ]
        for line in interesting[-4:]:
            signals.append(f"{path.name}: {line[-220:]}")
    return signals[-12:]


def build_status() -> dict:
    config = load_json(CONFIG_PATH)
    tasks = get_tasks()
    procs = get_processes()
    ports = get_ports()
    pc = get_pc_health()
    idx = index_status()
    tool_cfg = ((config.get("tools") or {}).get("mcpServers") or {})
    fs_cfg = tool_cfg.get("filesystem") or {}
    google_cfg = tool_cfg.get("google_workspace") or {}

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mission_yolo": (OMEGA_ROOT / "MISSION_YOLO.md").exists(),
        "agent_v2": AGENT_V2_PATH.exists(),
        "config": {
            "restrictToWorkspace": (config.get("tools") or {}).get("restrictToWorkspace"),
            "execTimeout": ((config.get("tools") or {}).get("exec") or {}).get("timeout"),
            "maxToolIterations": ((config.get("agents") or {}).get("defaults") or {}).get("maxToolIterations"),
            "maxToolResultChars": ((config.get("agents") or {}).get("defaults") or {}).get("maxToolResultChars"),
            "contextWindowTokens": ((config.get("agents") or {}).get("defaults") or {}).get("contextWindowTokens"),
            "filesystemRoots": fs_cfg.get("args", [])[2:] if isinstance(fs_cfg.get("args"), list) else [],
            "googleTools": google_cfg.get("enabledTools"),
        },
        "tasks": tasks,
        "process_counts": {
            "gateway": len(procs["gateway"]),
            "supervisor": len(procs["supervisor"]),
            "watchdog": len(procs["watchdog"]),
            "dashboard": len(procs["dashboard"]),
            "indexer": len(procs["indexer"]),
        },
        "ports": ports,
        "pc": pc,
        "ollama_ok": http_ok("http://127.0.0.1:11434/api/tags"),
        "dashboard_url": DASHBOARD_URL,
        "dashboard_ok": http_ok(DASHBOARD_URL),
        "index": idx,
        "recent_log_signals": recent_log_signals(),
    }


def _task_by_name(status: dict) -> dict[str, dict]:
    return {str(task.get("name")): task for task in status.get("tasks", [])}


def _repair_action(actions: list[dict], name: str, detail: str, ok: bool, output: str = "") -> None:
    actions.append({
        "name": name,
        "detail": detail,
        "ok": bool(ok),
        "output": (output or "").strip()[:500],
    })


def repair_status(status: dict) -> list[dict]:
    actions: list[dict] = []
    tasks = _task_by_name(status)
    counts = status.get("process_counts") or {}
    idx = status.get("index") or {}

    admin_task_names = (
        "NanobotOmegaSupervisorAdmin",
        "NanobotWatchdogAdmin",
        "NanobotDashboardAdmin",
        "NanobotFileIndexAdmin",
        "NanobotSelfHeal",
    )
    needs_admin_reinstall = False
    for name in admin_task_names:
        task = tasks.get(name) or {}
        if task.get("state") == "Missing" or task.get("runLevel") != "Highest":
            needs_admin_reinstall = True
            break
    if needs_admin_reinstall:
        if ADMIN_INSTALLER_LAUNCHER.exists():
            ok, msg = run_detached([str(ADMIN_INSTALLER_LAUNCHER)], cwd=OMEGA_ROOT)
            _repair_action(actions, "admin_installer", "Recreation des taches admin Highest", ok, msg)
        else:
            _repair_action(actions, "admin_installer", f"Launcher introuvable: {ADMIN_INSTALLER_LAUNCHER}", False)

    if not status.get("mission_yolo"):
        try:
            MISSION_YOLO_PATH.write_text(DEFAULT_MISSION_YOLO, encoding="utf-8")
            _repair_action(actions, "mission_yolo", "Recreation de MISSION_YOLO.md", True)
        except Exception as exc:
            _repair_action(actions, "mission_yolo", "Recreation de MISSION_YOLO.md", False, str(exc))

    if not status.get("agent_v2"):
        try:
            AGENT_V2_PATH.write_text(DEFAULT_AGENT_V2, encoding="utf-8")
            _repair_action(actions, "agent_v2", "Recreation de AGENT_V2.md", True)
        except Exception as exc:
            _repair_action(actions, "agent_v2", "Recreation de AGENT_V2.md", False, str(exc))

    if not status.get("ollama_ok"):
        ok_task, msg_task = run_task("NanobotWatchdogAdmin")
        _repair_action(actions, "ollama_watchdog", "Relance du watchdog admin", ok_task, msg_task)
        if OLLAMA_RESTART.exists():
            ok, msg = run_detached(["cmd", "/c", str(OLLAMA_RESTART)], cwd=FIRE_ROOT)
            _repair_action(actions, "ollama_restart", "Redemarrage direct Ollama", ok, msg)
        else:
            _repair_action(actions, "ollama_restart", f"Script introuvable: {OLLAMA_RESTART}", False)

    if counts.get("supervisor", 0) < 1:
        ok, msg = run_task("NanobotOmegaSupervisorAdmin")
        _repair_action(actions, "supervisor", "Relance du superviseur admin", ok, msg)

    if counts.get("gateway", 0) < 1:
        ok_task, msg_task = run_task("NanobotOmegaSupervisorAdmin")
        _repair_action(actions, "gateway_supervisor", "Demande au superviseur de relancer le gateway", ok_task, msg_task)
        if START_GATEWAY.exists():
            ok, msg = run_detached(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(START_GATEWAY)],
                cwd=OMEGA_ROOT,
            )
            _repair_action(actions, "gateway_direct", "Relance directe du gateway", ok, msg)
        else:
            _repair_action(actions, "gateway_direct", f"Script introuvable: {START_GATEWAY}", False)

    if counts.get("watchdog", 0) < 1:
        ok, msg = run_task("NanobotWatchdogAdmin")
        _repair_action(actions, "watchdog", "Relance du watchdog admin", ok, msg)
        ok2, msg2 = run_task("NanobotSelfHeal")
        _repair_action(actions, "selfheal", "Declenchement du self-heal", ok2, msg2)

    if not status.get("dashboard_ok") or counts.get("dashboard", 0) < 1 or not port_listening(18791):
        ok, msg = run_task("NanobotDashboardAdmin")
        _repair_action(actions, "dashboard_task", "Relance du dashboard via tache admin", ok, msg)
        if START_DASHBOARD.exists():
            ok2, msg2 = run_detached(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(START_DASHBOARD)],
                cwd=OMEGA_ROOT,
            )
            _repair_action(actions, "dashboard_direct", "Relance directe du dashboard", ok2, msg2)
        else:
            _repair_action(actions, "dashboard_direct", f"Script introuvable: {START_DASHBOARD}", False)

    index_state = str(idx.get("state") or "").lower()
    if (
        not idx.get("db_exists")
        or int(idx.get("file_count") or 0) < 1
        or (index_state not in ("running", "complete", "partial") and counts.get("indexer", 0) < 1)
    ):
        ok, msg = run_task("NanobotFileIndexAdmin")
        _repair_action(actions, "file_index", "Relance de l'indexation locale", ok, msg)
        if FILE_INDEX.exists() and not ok:
            ok2, msg2 = run_detached(
                [sys.executable, str(FILE_INDEX), "index", "--max-seconds", "900", "--max-files", "120000"],
                cwd=OMEGA_ROOT,
            )
            _repair_action(actions, "file_index_direct", "Relance directe de l'indexation locale", ok2, msg2)

    return actions


def verdict(status: dict) -> str:
    problems: list[str] = []
    tasks = {t.get("name"): t for t in status.get("tasks", [])}
    for name in ("NanobotOmegaSupervisorAdmin", "NanobotWatchdogAdmin", "NanobotSelfHeal"):
        task = tasks.get(name) or {}
        if task.get("state") == "Missing":
            problems.append(f"{name} manquant")
        elif task.get("runLevel") != "Highest":
            problems.append(f"{name} pas en Highest")
    if not status.get("ollama_ok"):
        problems.append("Ollama injoignable")
    if status.get("process_counts", {}).get("gateway", 0) < 1:
        problems.append("gateway absent")
    if status.get("process_counts", {}).get("supervisor", 0) < 1:
        problems.append("superviseur absent")
    if status.get("process_counts", {}).get("watchdog", 0) < 1:
        problems.append("watchdog absent")
    if not status.get("mission_yolo"):
        problems.append("consigne Mission YOLO absente")
    if not status.get("agent_v2"):
        problems.append("consigne Agent V2 absente")
    if problems:
        return "A VERIFIER: " + "; ".join(problems[:6])
    return "OK: Nanobot est en mode admin/mission, services principaux actifs."


def to_text(status: dict) -> str:
    pc = status.get("pc") or {}
    idx = status.get("index") or {}
    ports = status.get("ports") or {}
    cfg = status.get("config") or {}
    lines = [
        "ETAT COMPLET NANOBOT",
        f"Generation: {status.get('generated_at')}",
        verdict(status),
        "",
        "Services:",
        f"- Gateway: {status['process_counts'].get('gateway', 0)} processus; port 18790={'OK' if (ports.get('18790') or {}).get('listening') else 'NON'}",
        f"- Superviseur admin: {status['process_counts'].get('supervisor', 0)} processus",
        f"- Watchdog admin: {status['process_counts'].get('watchdog', 0)} processus",
        f"- Ollama: {'OK' if status.get('ollama_ok') else 'NON'}; port 11434={'OK' if (ports.get('11434') or {}).get('listening') else 'NON'}",
        f"- Dashboard: {'OK' if status.get('dashboard_ok') else 'NON'}; {status.get('dashboard_url')}",
        "",
        "Mode mission/config:",
        f"- Mission YOLO: {'OK' if status.get('mission_yolo') else 'NON'}",
        f"- Agent V2: {'OK' if status.get('agent_v2') else 'NON'}",
        f"- restrictToWorkspace: {cfg.get('restrictToWorkspace')}",
        f"- exec timeout: {cfg.get('execTimeout')}s; iterations outils: {cfg.get('maxToolIterations')}; result chars: {cfg.get('maxToolResultChars')}",
        f"- racines filesystem: {', '.join(cfg.get('filesystemRoots') or [])}",
        "",
        "PC:",
        f"- CPU: {pc.get('cpuPercent')}%; RAM libre: {pc.get('ramFreeGB')} Go/{pc.get('ramTotalGB')} Go",
        f"- Disque C: {pc.get('diskCFreeGB')} Go libres/{pc.get('diskCTotalGB')} Go",
        "",
        "Index fichiers:",
        f"- DB: {'OK' if idx.get('db_exists') else 'NON'}; fichiers: {idx.get('file_count', 0)}",
        f"- Derniere indexation: {idx.get('finished_at') or idx.get('started_at') or 'jamais'}",
    ]
    repairs = status.get("repairs") or []
    if repairs:
        ok_count = sum(1 for item in repairs if item.get("ok"))
        lines += [
            "",
            "Reparation automatique:",
            f"- Actions tentees: {len(repairs)}; reussies: {ok_count}",
        ]
        for item in repairs[-10:]:
            state = "OK" if item.get("ok") else "ECHEC"
            detail = item.get("detail") or item.get("name")
            extra = item.get("output") or ""
            lines.append(f"- {state}: {detail}" + (f" ({extra})" if extra else ""))
    signals = status.get("recent_log_signals") or []
    if signals:
        lines += ["", "Signaux logs recents:"]
        lines += [f"- {line}" for line in signals[-8:]]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--repair-wait", type=int, default=10)
    args = parser.parse_args()

    status = build_status()
    repairs: list[dict] = []
    if args.repair:
        repairs = repair_status(status)
        if repairs and args.repair_wait > 0:
            time.sleep(args.repair_wait)
        status = build_status()
        status["repairs"] = repairs
    text = to_text(status)
    if args.write:
        HEALTH_DIR.mkdir(parents=True, exist_ok=True)
        JSON_OUT.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
        TXT_OUT.write_text(text, encoding="utf-8")
    print(json.dumps(status, indent=2, ensure_ascii=False) if args.json else text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
