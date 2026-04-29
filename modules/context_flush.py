#!/usr/bin/env python
"""
context_flush.py — Auto-nettoyage du contexte operationnel

Purge les fichiers d'etat temporaires, les logs volumineux,
les artefacts de boucle, et reinitialise les compteurs pour
demarrer chaque session majeure sur une base propre.

Usage importable:
    from modules.context_flush import flush_context, flush_report

Usage CLI:
    python modules/context_flush.py              # Flush standard
    python modules/context_flush.py --report     # Rapport sans action
    python modules/context_flush.py --force      # Flush + reset blacklists
    python modules/context_flush.py --full       # Flush total (tout reinitialiser)
"""
from __future__ import annotations

import json
import os
import sys
import shutil
import time
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# --- Chemins ---
BASE = Path("C:/AI/nanobot-omega")
STATE_DIR = BASE / "state"
SHARED_STATE = BASE / "shared_state.json"
LOOP_STATE = STATE_DIR / "loop_detector.json"
WORKING_STATE = STATE_DIR / "working_state.json"
STATE_HISTORY = STATE_DIR / "state_history.jsonl"
RESILIENT_LOG = STATE_DIR / "resilient.log"
CHROME_PROFILE = BASE / "shared-browser" / "chrome-profile"

# Seuils
MAX_LOG_SIZE_KB = 500          # Rotation si resilient.log > 500 KB
MAX_HISTORY_SIZE_KB = 500      # Rotation si state_history.jsonl > 500 KB
MAX_CONSECUTIVE_ERRORS = 10    # Alerte si une instance depasse ce seuil
STALE_BLACKLIST_HOURS = 24     # Blacklist > 24h = probablement obsolete


def flush_report() -> dict[str, Any]:
    """Analyse l'etat sans rien modifier. Retourne un diagnostic."""
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "issues": [],
        "stats": {},
        "recommendations": [],
    }

    # 1. Taille des logs
    for name, path in [("resilient.log", RESILIENT_LOG), ("state_history.jsonl", STATE_HISTORY)]:
        if path.exists():
            size_kb = path.stat().st_size / 1024
            report["stats"][name] = f"{size_kb:.1f} KB"
            if size_kb > MAX_LOG_SIZE_KB:
                report["issues"].append(f"{name} trop volumineux ({size_kb:.0f} KB > {MAX_LOG_SIZE_KB} KB)")
                report["recommendations"].append(f"Rotation necessaire pour {name}")

    # 2. Loop detector pollue
    if LOOP_STATE.exists():
        try:
            data = json.loads(LOOP_STATE.read_text(encoding="utf-8"))
            history_len = len(data.get("history", []))
            report["stats"]["loop_history"] = history_len
            if history_len > 0:
                report["issues"].append(f"Loop detector contient {history_len} entrees residuelles")
                report["recommendations"].append("Purger loop_detector.json pour session propre")
        except (json.JSONDecodeError, OSError):
            report["issues"].append("loop_detector.json corrompu")

    # 3. Working state encombre
    if WORKING_STATE.exists():
        try:
            data = json.loads(WORKING_STATE.read_text(encoding="utf-8"))
            keys = len(data)
            report["stats"]["working_state_keys"] = keys
            # Verifier les taches non terminees
            tasks = {k: v for k, v in data.items() if k.startswith("task") and isinstance(v, dict)}
            stale_tasks = [k for k, v in tasks.items() if v.get("status") != "done"]
            if stale_tasks:
                report["issues"].append(f"{len(stale_tasks)} tache(s) non terminee(s) dans working_state")
        except (json.JSONDecodeError, OSError):
            report["issues"].append("working_state.json corrompu")

    # 4. Blacklists shared_state.json
    if SHARED_STATE.exists():
        try:
            data = json.loads(SHARED_STATE.read_text(encoding="utf-8"))
            instances = data.get("instances", {})
            now = time.time()
            blacklisted = []
            stale_blacklists = []
            high_errors = []

            for name, inst in instances.items():
                bl = inst.get("blacklisted_until", 0)
                ce = inst.get("consecutive_errors", 0)
                if bl > now:
                    remaining_h = (bl - now) / 3600
                    blacklisted.append(f"{name} ({remaining_h:.1f}h)")
                    if remaining_h > STALE_BLACKLIST_HOURS:
                        stale_blacklists.append(name)
                if ce > MAX_CONSECUTIVE_ERRORS:
                    high_errors.append(f"{name} ({ce} erreurs)")

            report["stats"]["instances_total"] = len(instances)
            report["stats"]["instances_blacklisted"] = len(blacklisted)
            report["stats"]["instances_available"] = len(instances) - len(blacklisted)

            if blacklisted:
                report["issues"].append(f"{len(blacklisted)} instance(s) blacklistee(s): {', '.join(blacklisted)}")
            if stale_blacklists:
                report["issues"].append(f"Blacklists obsoletes (>24h): {', '.join(stale_blacklists)}")
                report["recommendations"].append("Reset des blacklists obsoletes")
            if high_errors:
                report["issues"].append(f"Erreurs consecutives elevees: {', '.join(high_errors)}")

        except (json.JSONDecodeError, OSError):
            report["issues"].append("shared_state.json corrompu ou illisible")

    # 5. Chrome profile temporaires
    chrome_cache = CHROME_PROFILE / "Default" / "Cache" / "Cache_Data"
    if chrome_cache.exists():
        try:
            cache_size = sum(f.stat().st_size for f in chrome_cache.rglob("*") if f.is_file()) / (1024 * 1024)
            report["stats"]["chrome_cache_mb"] = f"{cache_size:.1f} MB"
            if cache_size > 200:
                report["issues"].append(f"Cache Chrome volumineux ({cache_size:.0f} MB)")
                report["recommendations"].append("Purger le cache Chrome")
        except OSError:
            pass

    if not report["issues"]:
        report["status"] = "CLEAN"
    else:
        report["status"] = f"{len(report['issues'])} ISSUE(S)"

    return report


def flush_context(
    reset_loops: bool = True,
    rotate_logs: bool = True,
    clean_working_state: bool = False,
    reset_blacklists: bool = False,
    clean_chrome_cache: bool = False,
) -> dict[str, list[str]]:
    """Nettoie le contexte operationnel.

    Args:
        reset_loops: Purger le detecteur de boucles (defaut: True)
        rotate_logs: Rotation des logs volumineux (defaut: True)
        clean_working_state: Reset complet de working_state.json (defaut: False)
        reset_blacklists: Remettre toutes les blacklists a zero (defaut: False)
        clean_chrome_cache: Purger le cache Chrome (defaut: False)

    Returns:
        {"done": [...], "skipped": [...], "errors": [...]}
    """
    result: dict[str, list[str]] = {"done": [], "skipped": [], "errors": []}

    # 1. Reset loop detector
    if reset_loops and LOOP_STATE.exists():
        try:
            LOOP_STATE.write_text(
                json.dumps({"history": [], "updated": time.time()}),
                encoding="utf-8"
            )
            result["done"].append("Loop detector purge")
        except OSError as e:
            result["errors"].append(f"Loop detector: {e}")
    else:
        result["skipped"].append("Loop detector (absent ou desactive)")

    # 2. Rotation des logs
    if rotate_logs:
        for name, path, max_kb in [
            ("resilient.log", RESILIENT_LOG, MAX_LOG_SIZE_KB),
            ("state_history.jsonl", STATE_HISTORY, MAX_HISTORY_SIZE_KB),
        ]:
            if path.exists() and path.stat().st_size / 1024 > max_kb:
                try:
                    archive = path.with_suffix(f".{time.strftime('%Y%m%d_%H%M%S')}.bak")
                    path.rename(archive)
                    path.write_text("", encoding="utf-8")
                    result["done"].append(f"{name} archive vers {archive.name} + reset")
                except OSError as e:
                    result["errors"].append(f"{name}: {e}")
            else:
                result["skipped"].append(f"{name} (taille OK ou absent)")

    # 3. Working state
    if clean_working_state and WORKING_STATE.exists():
        try:
            # Sauvegarder avant purge
            backup = WORKING_STATE.with_suffix(f".{time.strftime('%Y%m%d_%H%M%S')}.bak")
            shutil.copy2(WORKING_STATE, backup)
            WORKING_STATE.write_text(json.dumps({}, indent=2), encoding="utf-8")
            result["done"].append(f"working_state.json purge (backup: {backup.name})")
        except OSError as e:
            result["errors"].append(f"working_state: {e}")
    else:
        result["skipped"].append("working_state (desactive ou absent)")

    # 4. Reset blacklists
    if reset_blacklists and SHARED_STATE.exists():
        try:
            data = json.loads(SHARED_STATE.read_text(encoding="utf-8"))
            count = 0
            for inst in data.get("instances", {}).values():
                if inst.get("blacklisted_until", 0) > 0 or inst.get("consecutive_errors", 0) > 0:
                    inst["blacklisted_until"] = 0.0
                    inst["consecutive_errors"] = 0
                    inst["last_error_msg"] = ""
                    count += 1
            data["timestamp"] = time.time()
            SHARED_STATE.write_text(json.dumps(data, indent=2), encoding="utf-8")
            result["done"].append(f"Blacklists reset ({count} instance(s) nettoyee(s))")
        except (json.JSONDecodeError, OSError) as e:
            result["errors"].append(f"shared_state: {e}")
    else:
        result["skipped"].append("Blacklists (desactive ou absent)")

    # 5. Cache Chrome
    if clean_chrome_cache:
        cache_dir = CHROME_PROFILE / "Default" / "Cache" / "Cache_Data"
        if cache_dir.exists():
            try:
                size_before = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file()) / (1024 * 1024)
                shutil.rmtree(cache_dir, ignore_errors=True)
                cache_dir.mkdir(parents=True, exist_ok=True)
                result["done"].append(f"Cache Chrome purge ({size_before:.0f} MB liberes)")
            except OSError as e:
                result["errors"].append(f"Cache Chrome: {e}")
        else:
            result["skipped"].append("Cache Chrome (absent)")
    else:
        result["skipped"].append("Cache Chrome (desactive)")

    return result


def print_report(report: dict[str, Any]) -> None:
    """Affiche le rapport de diagnostic."""
    print(f"\n{'='*60}")
    print(f"  DIAGNOSTIC CONTEXTE — {report['timestamp']}")
    print(f"  Statut: {report['status']}")
    print(f"{'='*60}")

    if report["stats"]:
        print("\n  Statistiques:")
        for k, v in report["stats"].items():
            print(f"    {k}: {v}")

    if report["issues"]:
        print(f"\n  Problemes ({len(report['issues'])}):")
        for issue in report["issues"]:
            print(f"    [!] {issue}")

    if report["recommendations"]:
        print(f"\n  Recommandations:")
        for rec in report["recommendations"]:
            print(f"    -> {rec}")

    if not report["issues"]:
        print("\n  Aucun probleme detecte. Contexte propre.")
    print()


def print_flush_result(result: dict[str, list[str]]) -> None:
    """Affiche le resultat du nettoyage."""
    print(f"\n{'='*60}")
    print(f"  FLUSH CONTEXTE — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    if result["done"]:
        print(f"\n  Actions effectuees ({len(result['done'])}):")
        for a in result["done"]:
            print(f"    [OK] {a}")

    if result["skipped"]:
        print(f"\n  Ignore ({len(result['skipped'])}):")
        for s in result["skipped"]:
            print(f"    [--] {s}")

    if result["errors"]:
        print(f"\n  ERREURS ({len(result['errors'])}):")
        for e in result["errors"]:
            print(f"    [!!] {e}")
    print()


# --- CLI ---
if __name__ == "__main__":
    args = sys.argv[1:]

    if "--report" in args:
        report = flush_report()
        print_report(report)
    elif "--force" in args:
        report = flush_report()
        print_report(report)
        result = flush_context(reset_blacklists=True)
        print_flush_result(result)
    elif "--full" in args:
        report = flush_report()
        print_report(report)
        result = flush_context(
            reset_loops=True,
            rotate_logs=True,
            clean_working_state=True,
            reset_blacklists=True,
            clean_chrome_cache=True,
        )
        print_flush_result(result)
    else:
        # Flush standard : loops + logs
        result = flush_context(reset_loops=True, rotate_logs=True)
        print_flush_result(result)
