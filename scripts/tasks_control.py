"""Gestion centralisee des taches Windows Nanobot et des taches Claude.

Distingue :
- Taches Windows reelles (Task Scheduler) : NanobotVeille2ememain, NanobotSelfHeal, etc.
- Recettes Claude scheduled-tasks (descriptions sans execution active).
- Jobs cron internes (`workspace/cron/jobs.json` si present).

Usage :
  python tasks_control.py list                # liste tout
  python tasks_control.py health              # synthese sante
  python tasks_control.py run NAME            # lance une tache (admin requis selon tache)
  python tasks_control.py pause NAME          # disable
  python tasks_control.py resume NAME         # enable
  python tasks_control.py logs NAME           # tail log dedie si trouve
  python tasks_control.py explain NAME        # description + commande
  python tasks_control.py detect-duplicates   # verifie pollers/processus en double
  python tasks_control.py verify-scheduler    # liste etat de toutes les taches Nanobot*
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OMEGA = Path(r"C:\AI\nanobot-omega")
LOGS = OMEGA / "logs"
CLAUDE_RECIPES_DIR = Path(r"C:\Users\user\.claude\scheduled-tasks")
CRON_JOBS_FILE = OMEGA / "workspace" / "cron" / "jobs.json"

# Map task name -> log file (when known)
TASK_LOG_MAP = {
    "NanobotVeille2ememain": LOGS / "veille_direct.log",
    "NanobotSelfHeal": LOGS / "nanobot_selfheal.log",
    "NanobotWatchdogAdmin": LOGS / "nanobot_watchdog.log",
    "NanobotOmegaSupervisorAdmin": Path(r"C:\AI\nanobot-omega\logs\telegram-gateway-control.log"),
    "NanobotLogRotate": LOGS / "log_rotate.log",
    "NanobotBackup": LOGS / "backup.log",
    "NanobotGoogleTokenRefresh": LOGS / "google_token_refresh.log",
}

# Map task name -> short description
TASK_DESCRIPTION = {
    "NanobotVeille2ememain": "Scraping 2ememain.be objets gratuits 50km Mouscron + Telegram (toutes les 30 min, deterministe sans LLM)",
    "NanobotSelfHeal": "Beacon de sante global : Ollama, Watchdog, Supervisor, Gateway (toutes les 10 min)",
    "NanobotWatchdogAdmin": "Watchdog Ollama (3 fails -> restart auto)",
    "NanobotOmegaSupervisorAdmin": "Supervisor PowerShell : maintient le gateway Telegram en vie + cleanup pollers fantomes",
    "NanobotLogRotate": "Rotation logs (max 5MB, garde 5 versions, quotidien 03:00)",
    "NanobotBackup": "ZIP fichiers d'etat critiques (quotidien 03:15, garde 14 jours)",
    "NanobotGoogleTokenRefresh": "Refresh hebdomadaire OAuth Google preventif",
    "NanobotDashboardAdmin": "Dashboard local (sur trigger)",
    "NanobotFileIndexAdmin": "Index de fichiers (sur trigger)",
}


def run_cmd(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout + proc.stderr).strip()


_TASK_STATE_MAP = {0: "Unknown", 1: "Disabled", 2: "Queued", 3: "Ready", 4: "Running"}


def _normalize_state(value) -> str:
    if isinstance(value, int):
        return _TASK_STATE_MAP.get(value, f"Unknown({value})")
    return str(value or "Unknown")


def list_windows_tasks() -> list[dict]:
    # Force string state output via @{Name='State';Expression={...}} to avoid enum/int serialization.
    rc, out = run_cmd(["powershell", "-NoProfile", "-Command",
                       "Get-ScheduledTask | Where-Object { $_.TaskName -like '*Nanobot*' } | "
                       "Select-Object TaskName, @{Name='StateStr';Expression={[string]$_.State}} | "
                       "ConvertTo-Json"])
    if rc != 0:
        return []
    try:
        data = json.loads(out)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    out_list = []
    for t in data:
        state_raw = t.get("StateStr") or t.get("State", "Unknown")
        out_list.append({"name": t.get("TaskName", ""), "state": _normalize_state(state_raw)})
    return out_list


def list_claude_recipes() -> list[dict]:
    if not CLAUDE_RECIPES_DIR.exists():
        return []
    out = []
    for entry in CLAUDE_RECIPES_DIR.iterdir():
        if not entry.is_dir():
            continue
        skill = entry / "SKILL.md"
        out.append({
            "name": entry.name,
            "kind": "claude_recipe",
            "skill_present": skill.exists(),
            "path": str(entry),
        })
    return out


def list_cron_jobs() -> list[dict]:
    if not CRON_JOBS_FILE.exists():
        return []
    try:
        data = json.loads(CRON_JOBS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    jobs = data.get("jobs") if isinstance(data, dict) else (data if isinstance(data, list) else [])
    out = []
    for j in jobs or []:
        out.append({
            "name": j.get("name") or j.get("id") or "",
            "kind": "cron_job",
            "enabled": j.get("enabled", True),
            "schedule": j.get("schedule"),
            "id": j.get("id"),
        })
    return out


def describe(name: str) -> str:
    desc = TASK_DESCRIPTION.get(name, "(pas de description connue)")
    log_path = TASK_LOG_MAP.get(name)
    parts = [f"Tache : {name}", f"Description : {desc}"]
    if log_path:
        parts.append(f"Log : {log_path} ({'present' if log_path.exists() else 'absent'})")
    rc, out = run_cmd(["schtasks", "/Query", "/TN", name, "/V", "/FO", "LIST"])
    if rc == 0:
        parts.append("")
        parts.append("Etat detaille :")
        parts.append(out)
    return "\n".join(parts)


def list_all() -> str:
    win = list_windows_tasks()
    claude = list_claude_recipes()
    cron = list_cron_jobs()
    lines = [
        "=== Taches Nanobot (Windows Task Scheduler) ===",
        f"({len(win)} taches actives ou planifiees)",
        "",
    ]
    for t in win:
        marker = "[OK]" if t["state"] in ("Ready", "Running") else "[--]"
        desc = TASK_DESCRIPTION.get(t["name"], "")
        lines.append(f"  [{marker}] {t['name']:35s} {t['state']:10s} {desc}")
    lines.append("")
    lines.append("=== Recettes Claude (.claude/scheduled-tasks/) ===")
    if not claude:
        lines.append("  (aucune)")
    else:
        lines.append("  ATTENTION : ce sont des descriptions/recettes, PAS des taches actives.")
        lines.append("  L'execution reelle passe par Windows Task Scheduler ou cron Nanobot.")
        for r in claude:
            lines.append(f"  - {r['name']:35s} skill_present={r['skill_present']}")
    lines.append("")
    lines.append("=== Cron jobs internes Nanobot ===")
    if not cron:
        lines.append("  (aucun fichier workspace/cron/jobs.json)")
    else:
        for j in cron:
            mark = "[OK]" if j.get("enabled") else "[--]"
            lines.append(f"  [{mark}] {j['name']:35s} schedule={j.get('schedule', '?')} id={j.get('id', '-')}")
    return "\n".join(lines)


def health() -> str:
    win = list_windows_tasks()
    running = [t["name"] for t in win if t["state"] == "Running"]
    ready = [t["name"] for t in win if t["state"] == "Ready"]
    disabled = [t["name"] for t in win if t["state"] == "Disabled"]
    other = [t["name"] for t in win if t["state"] not in ("Running", "Ready", "Disabled")]
    lines = [
        "Sante des taches Nanobot",
        f"  Running  : {len(running)} -> {', '.join(running) or '-'}",
        f"  Ready    : {len(ready)} -> {', '.join(ready) or '-'}",
        f"  Disabled : {len(disabled)} -> {', '.join(disabled) or '-'}",
    ]
    if other:
        lines.append(f"  Autres   : {len(other)} -> {', '.join(other)}")
    if disabled:
        lines.append("")
        lines.append("ATTENTION : taches DISABLED (mises en pause manuellement) :")
        for n in disabled:
            lines.append(f"  - {n} (resume : python tasks_control.py resume {n})")
    return "\n".join(lines)


def run_task(name: str) -> str:
    rc, out = run_cmd(["schtasks", "/Run", "/TN", name])
    return f"run {name} rc={rc}\n{out}"


def pause_task(name: str) -> str:
    rc, out = run_cmd(["schtasks", "/Change", "/TN", name, "/DISABLE"])
    return f"pause {name} rc={rc}\n{out}"


def resume_task(name: str) -> str:
    rc, out = run_cmd(["schtasks", "/Change", "/TN", name, "/ENABLE"])
    return f"resume {name} rc={rc}\n{out}"


def logs_for(name: str, n: int = 30) -> str:
    log_path = TASK_LOG_MAP.get(name)
    if not log_path:
        return f"Aucun log connu pour {name}. Voir scripts/tasks_control.py TASK_LOG_MAP."
    if not log_path.exists():
        return f"Log absent : {log_path}"
    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-n:]) if content else "(log vide)"


def detect_duplicates() -> str:
    """Detecte les multiples pollers Telegram, gateways, watchdogs."""
    rc, out = run_cmd(["powershell", "-NoProfile", "-Command",
                       "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                       "Select-Object ProcessId, CommandLine | ConvertTo-Json"])
    if rc != 0 or not out.strip():
        return "Pas de python.exe trouve."
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
    except Exception:
        return f"Parse error: {out[:300]}"
    suspects: dict[str, list[int]] = {}
    for p in data:
        cmd = (p.get("CommandLine") or "").lower()
        for token in ("nanobot_telegram", "telegram_poller", "watchdog", "supervisor", "veille_and_notify"):
            if token in cmd:
                suspects.setdefault(token, []).append(int(p.get("ProcessId", 0)))
    lines = ["Detection doublons :"]
    any_dup = False
    for token, pids in suspects.items():
        marker = "DUPLICATE" if len(pids) > 1 else "ok"
        if len(pids) > 1:
            any_dup = True
        lines.append(f"  {token:25s} pids={pids} [{marker}]")
    if not any_dup:
        lines.append("  (aucun doublon detecte)")
    return "\n".join(lines)


def verify_scheduler() -> str:
    win = list_windows_tasks()
    if not win:
        return "Aucune tache Nanobot* trouvee dans Task Scheduler."
    lines = ["Verification Scheduler :"]
    for t in win:
        rc, out = run_cmd(["schtasks", "/Query", "/TN", t["name"], "/FO", "LIST", "/V"])
        last_result = ""
        for line in out.splitlines():
            if "Code dernier r" in line or "Last Result" in line:
                last_result = line.strip()
                break
        lines.append(f"  {t['name']:35s} state={t['state']:10s} {last_result}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    cmd = (argv[1] if len(argv) > 1 else "list").strip().lower()
    aliases = {"sante": "health", "ls": "list"}
    cmd = aliases.get(cmd, cmd)

    if cmd == "list":
        print(list_all())
    elif cmd == "health":
        print(health())
    elif cmd == "run":
        if len(argv) < 3:
            print("Usage: tasks_control.py run NAME")
            return 2
        print(run_task(argv[2]))
    elif cmd == "pause":
        if len(argv) < 3:
            print("Usage: tasks_control.py pause NAME")
            return 2
        print(pause_task(argv[2]))
    elif cmd == "resume":
        if len(argv) < 3:
            print("Usage: tasks_control.py resume NAME")
            return 2
        print(resume_task(argv[2]))
    elif cmd == "logs":
        if len(argv) < 3:
            print("Usage: tasks_control.py logs NAME [N]")
            return 2
        n = 30
        if len(argv) > 3:
            try:
                n = int(argv[3])
            except ValueError:
                pass
        print(logs_for(argv[2], n))
    elif cmd == "explain":
        if len(argv) < 3:
            print("Usage: tasks_control.py explain NAME")
            return 2
        print(describe(argv[2]))
    elif cmd == "detect-duplicates":
        print(detect_duplicates())
    elif cmd == "verify-scheduler":
        print(verify_scheduler())
    else:
        print("Commandes : list | health | run NAME | pause NAME | resume NAME | logs NAME [N] | explain NAME | detect-duplicates | verify-scheduler")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
