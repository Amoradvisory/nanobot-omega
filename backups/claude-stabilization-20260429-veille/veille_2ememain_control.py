"""Local controller for the deterministic 2ememain watch.

Usage:
  python veille_2ememain_control.py status
  python veille_2ememain_control.py pause
  python veille_2ememain_control.py resume
  python veille_2ememain_control.py 50km
  python veille_2ememain_control.py 100km
  python veille_2ememain_control.py run
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

TASK_NAME = "NanobotVeille2ememain"
WORKSPACE = Path("C:/AI/nanobot-omega/workspace")
CONFIG_PATH = WORKSPACE / "veille_2ememain_config.json"
LOG_PATH = Path("C:/AI/nanobot-omega/logs/veille_direct.log")


def run_cmd(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def set_radius(km: int) -> str:
    meters = km * 1000
    config = load_config()
    config["distance"] = meters
    config["urls"] = [
        re.sub(r"distanceMeters:\d+", f"distanceMeters:{meters}", url)
        for url in config.get("urls", [])
    ]
    save_config(config)
    return f"Veille 2ememain: rayon regle sur {km} km autour de 7700."


def tail_log(lines: int = 8) -> str:
    if not LOG_PATH.exists():
        return "Log introuvable."
    content = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:]) if content else "Log vide."


def status() -> str:
    config = load_config()
    km = int(config.get("distance", 0)) // 1000
    rc, task = run_cmd(["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"])
    task_text = task if rc == 0 else f"Erreur schtasks: {task}"
    return "\n".join([
        "Veille 2ememain - statut",
        f"Rayon: {km} km autour de 7700",
        f"Categories: {len(config.get('urls', []))}",
        "",
        task_text,
        "",
        "Dernier log:",
        tail_log(),
    ])


def pause() -> str:
    rc, out = run_cmd(["schtasks", "/Change", "/TN", TASK_NAME, "/DISABLE"])
    if rc != 0:
        return f"Pause impossible: {out}"
    return "Veille 2ememain mise en pause."


def resume() -> str:
    rc, out = run_cmd(["schtasks", "/Change", "/TN", TASK_NAME, "/ENABLE"])
    if rc != 0:
        return f"Reprise impossible: {out}"
    return "Veille 2ememain reactivee."


def run_now() -> str:
    rc, out = run_cmd(["schtasks", "/Run", "/TN", TASK_NAME])
    if rc != 0:
        return f"Lancement impossible: {out}"
    return "Run 2ememain lance. Le resultat arrivera dans le log puis sur Telegram s'il y a du neuf."


def main(argv: list[str]) -> int:
    arg = (argv[1] if len(argv) > 1 else "status").strip().lower()
    aliases = {
        "statut": "status",
        "etat": "status",
        "pause": "pause",
        "stop": "pause",
        "resume": "resume",
        "reprendre": "resume",
        "on": "resume",
        "run": "run",
        "now": "run",
        "lancer": "run",
    }
    cmd = aliases.get(arg, arg)
    if cmd == "status":
        print(status())
    elif cmd == "pause":
        print(pause())
    elif cmd == "resume":
        print(resume())
    elif cmd == "run":
        print(run_now())
    elif re.fullmatch(r"\d+\s*km?", cmd):
        km = int(re.match(r"\d+", cmd).group(0))
        if km < 5 or km > 200:
            print("Rayon refuse: choisis entre 5 km et 200 km.")
            return 2
        print(set_radius(km))
    else:
        print("Usage: status | pause | resume | 50km | 100km | run")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
