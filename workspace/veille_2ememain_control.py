"""Local controller for the deterministic 2ememain watch.

Usage:
  python veille_2ememain_control.py status            # etat tache + dernier log
  python veille_2ememain_control.py pause             # admin requis
  python veille_2ememain_control.py resume            # admin requis
  python veille_2ememain_control.py 50km              # change rayon
  python veille_2ememain_control.py 100km
  python veille_2ememain_control.py run               # lance maintenant
  python veille_2ememain_control.py health            # synthese sante (fichier health JSON)
  python veille_2ememain_control.py logs [N]          # tail N lignes log (defaut 30)
  python veille_2ememain_control.py opportunities     # historique annonces vues (count + sample)
  python veille_2ememain_control.py test-notification # test Telegram dry-run sur ad simulee
  python veille_2ememain_control.py reset-seen        # remet history a zero (CONFIRME)
  python veille_2ememain_control.py config            # affiche config actuelle
  python veille_2ememain_control.py explain-last-run  # detaille le dernier run
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TASK_NAME = "NanobotVeille2ememain"
WORKSPACE = Path("C:/AI/nanobot-omega/workspace")
CONFIG_PATH = WORKSPACE / "veille_2ememain_config.json"
LOG_PATH = Path("C:/AI/nanobot-omega/logs/veille_direct.log")
HEALTH_PATH = Path("C:/AI/nanobot-omega/logs/veille_health.json")
HISTORY_PATH = WORKSPACE / "veille_2ememain_history.json"
NOTIFY_SCRIPT = WORKSPACE / "run_veille_and_notify.py"


def run_cmd(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
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
    return "Run 2ememain lance. Resultat dans le log puis sur Telegram s'il y a du neuf."


def health() -> str:
    """Synthese sante a partir du fichier veille_health.json (genere par run_veille_and_notify)."""
    lines = ["Veille 2ememain - sante"]
    if not HEALTH_PATH.exists():
        lines.append("(aucun fichier health.json — la veille n'a pas encore tourne avec la nouvelle version)")
    else:
        try:
            data = json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            return f"Health unreadable: {exc}"
        runs = data.get("runs", [])
        ok_count = sum(1 for r in runs if r.get("success"))
        fail_count = len(runs) - ok_count
        lines.append(f"Runs traces: {len(runs)} (OK={ok_count}, FAIL={fail_count})")
        lines.append(f"Dernier succes: {data.get('last_success', 'aucun')}")
        lines.append(f"Dernier echec: {data.get('last_failure', 'aucun')}")
        lines.append(f"3 derniers runs echec: {data.get('last_3_failures', 0)}")
        if data.get("last_alert"):
            lines.append(f"Derniere alerte Telegram: {data['last_alert']}")
        if runs:
            last = runs[-1]
            lines.append(f"Dernier run: {last['ts']} success={last['success']} ads={last['ads_count']} err={last.get('error', '-')}")
    # Etat tache
    rc, _ = run_cmd(["schtasks", "/Query", "/TN", TASK_NAME])
    lines.append("")
    lines.append("Tache Windows:")
    if rc == 0:
        rc2, out2 = run_cmd(["powershell", "-NoProfile", "-Command",
                             f"Get-ScheduledTask -TaskName {TASK_NAME} | Select-Object -ExpandProperty State"])
        lines.append(f"  State: {out2.strip()}")
    else:
        lines.append("  Tache non trouvee (schtasks)")
    return "\n".join(lines)


def logs(n: int = 30) -> str:
    return tail_log(n)


def opportunities() -> str:
    """Histoire des annonces vues : count + dernieres."""
    if not HISTORY_PATH.exists():
        return "Pas d'historique."
    try:
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"Historique unreadable: {exc}"
    n = len(history)
    last = history[-15:] if n > 15 else history
    lines = [f"Veille 2ememain - opportunities ({n} annonces deja vues)"]
    lines.append("")
    lines.append("15 dernieres :")
    for ad_id in reversed(last):
        lines.append(f"  https://www.2ememain.be/v/{ad_id} (id={ad_id})")
    return "\n".join(lines)


def test_notification() -> str:
    """Lance run_veille_and_notify.py en --dry-run pour valider la chaine sans envoyer."""
    if not NOTIFY_SCRIPT.exists():
        return "run_veille_and_notify.py introuvable."
    rc, out = run_cmd([sys.executable, "-X", "utf8", str(NOTIFY_SCRIPT), "--dry-run"])
    head = out[:1500]
    return f"=== test-notification (dry-run) rc={rc} ===\n{head}\n(output total {len(out)} chars)"


def reset_seen(force: bool = False) -> str:
    if not force:
        return ("CONFIRMATION REQUISE pour reset-seen.\n"
                "Ce reset re-traitera toutes les annonces et risque de re-envoyer plein de notifs.\n"
                "Pour confirmer: python veille_2ememain_control.py reset-seen --force")
    if not HISTORY_PATH.exists():
        return "Pas d'historique a reset."
    backup = HISTORY_PATH.with_suffix(f".json.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    HISTORY_PATH.rename(backup)
    HISTORY_PATH.write_text("[]", encoding="utf-8")
    return f"Historique reset. Backup: {backup}"


def show_config() -> str:
    if not CONFIG_PATH.exists():
        return "Config introuvable."
    cfg = load_config()
    return json.dumps(cfg, indent=2, ensure_ascii=False)


def explain_last_run() -> str:
    """Detaille le dernier run a partir des logs."""
    if not LOG_PATH.exists():
        return "Log introuvable."
    lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    # Trouve la derniere section "=== START run_veille_and_notify ==="
    last_start = None
    for i in range(len(lines) - 1, -1, -1):
        if "=== START run_veille_and_notify ===" in lines[i]:
            last_start = i
            break
    if last_start is None:
        return "Aucun run trouve dans les logs."
    section = lines[last_start:last_start + 30]
    return "Dernier run:\n" + "\n".join(section)


def main(argv: list[str]) -> int:
    arg = (argv[1] if len(argv) > 1 else "status").strip().lower()
    aliases = {
        "statut": "status", "etat": "status",
        "stop": "pause",
        "reprendre": "resume", "on": "resume",
        "now": "run", "lancer": "run",
        "sante": "health",
        "log": "logs",
        "config-show": "config", "show-config": "config",
        "explain": "explain-last-run", "explain-last": "explain-last-run", "last-run": "explain-last-run",
        "test-notif": "test-notification", "testnotif": "test-notification", "dry-run": "test-notification",
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
    elif cmd == "health":
        print(health())
    elif cmd == "logs":
        n = 30
        if len(argv) > 2:
            try:
                n = int(argv[2])
            except ValueError:
                pass
        print(logs(n))
    elif cmd == "opportunities":
        print(opportunities())
    elif cmd == "test-notification":
        print(test_notification())
    elif cmd == "reset-seen":
        force = "--force" in argv
        print(reset_seen(force=force))
    elif cmd == "config":
        print(show_config())
    elif cmd == "explain-last-run":
        print(explain_last_run())
    elif re.fullmatch(r"\d+\s*km?", cmd):
        km = int(re.match(r"\d+", cmd).group(0))
        if km < 5 or km > 200:
            print("Rayon refuse: choisis entre 5 km et 200 km.")
            return 2
        print(set_radius(km))
    else:
        print("Usage: status | pause | resume | run | health | logs [N] | opportunities | test-notification | reset-seen [--force] | config | explain-last-run | 50km | 100km")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
