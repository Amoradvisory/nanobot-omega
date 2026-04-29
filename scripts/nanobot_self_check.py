"""Nanobot self-check / health-check / recovery protocol.

Fournit une commande unifiee pour verifier que NanoBot fonctionne correctement
et pour reparer les composants connus quand ils sont casses.

Sous-commandes :
    check     : audit complet, sortie JSON + texte humain, exit 0/1/2
    recover   : tente les reparations automatiques connues
    capabilities : liste les capacites reelles verifiees

Toutes les verifications sont read-only et non-destructives. Le mode `recover`
ne modifie que ce qui est explicitement reparable.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OMEGA = Path(r"C:\AI\nanobot-omega")
WORKSPACE = OMEGA / "workspace"
SCRIPTS = OMEGA / "scripts"
LOGS = OMEGA / "logs"
HEALTH = OMEGA / "health"

OUT_JSON = HEALTH / "self_check_latest.json"
OUT_LOG = LOGS / "self_check.log"

CRITICAL_DOCS = [
    WORKSPACE / "NANOBOT_STARTUP_CONTEXT.md",
    WORKSPACE / "NANOBOT_RECENT_UPGRADES.md",
    WORKSPACE / "NANOBOT_ARSENAL.md",
    WORKSPACE / "RADICAL_CAPABILITIES.md",
    WORKSPACE / "GOOGLE_WORKSPACE_CAPABILITIES.md",
    WORKSPACE / "USER.md",
    WORKSPACE / "CORE_DIRECTIVE.md",
    OMEGA / "MISSION_YOLO.md",
    OMEGA / "AGENT_V2.md",
]

OPERATIONAL_SCRIPTS = [
    SCRIPTS / "obsidian_second_brain.py",
    SCRIPTS / "build_startup_context.py",
    SCRIPTS / "google_workspace_cli.py",
    SCRIPTS / "google_workspace_mcp.py",
    SCRIPTS / "scraping_champion.py",
    SCRIPTS / "app_acquisition.py",
    SCRIPTS / "proactive_intel.py",
    SCRIPTS / "desktop_intel.py",
    SCRIPTS / "resilience_orchestrator.py",
    SCRIPTS / "agent_forge.py",
    SCRIPTS / "tools_audit.py",
]

OBSIDIAN_REQUIRED_SUBCOMMANDS = [
    "bootstrap", "status", "open", "capture", "daily", "import", "search",
    "sync-memory", "relations", "write-note", "read-note", "delete-path",
    "create-folder", "rename-path", "move-note", "list", "set-frontmatter",
    "get-frontmatter", "filter-notes", "tags", "sync-status",
    "attachments", "add-attachment", "move-attachment",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def _run(cmd: list[str], *, timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(OMEGA),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except Exception as exc:
        return 1, "", str(exc)


# ---------------------------------------------------------------------------
# Individual checks. Each returns a dict with at least: name, ok, severity,
# detail, fix_hint. Severity: "info" | "warn" | "error".
# ---------------------------------------------------------------------------


def check_workspace_layout() -> dict[str, Any]:
    missing = [p for p in [OMEGA, WORKSPACE, SCRIPTS] if not _safe_exists(p)]
    return {
        "name": "workspace_layout",
        "ok": not missing,
        "severity": "error" if missing else "info",
        "detail": f"missing: {missing}" if missing else f"omega={OMEGA}, workspace={WORKSPACE}",
        "fix_hint": "Reinstaller la structure de Nanobot Omega" if missing else None,
    }


def check_critical_docs() -> dict[str, Any]:
    missing = [p.name for p in CRITICAL_DOCS if not _safe_exists(p)]
    return {
        "name": "critical_docs",
        "ok": not missing,
        "severity": "warn" if missing else "info",
        "detail": f"missing docs: {missing}" if missing else f"all {len(CRITICAL_DOCS)} critical docs present",
        "fix_hint": "Regenerer le startup context via build_startup_context.py" if missing else None,
    }


def check_operational_scripts() -> dict[str, Any]:
    missing = [p.name for p in OPERATIONAL_SCRIPTS if not _safe_exists(p)]
    return {
        "name": "operational_scripts",
        "ok": not missing,
        "severity": "error" if missing else "info",
        "detail": f"missing scripts: {missing}" if missing else f"all {len(OPERATIONAL_SCRIPTS)} scripts present",
        "fix_hint": "Restaurer depuis backups/ ou reinstaller" if missing else None,
    }


def check_obsidian_bridge() -> dict[str, Any]:
    rc, out, err = _run([sys.executable, str(SCRIPTS / "obsidian_second_brain.py"), "status"], timeout=60)
    notes_line = next((line for line in out.splitlines() if "Notes markdown" in line), "")
    return {
        "name": "obsidian_bridge_status",
        "ok": rc == 0,
        "severity": "error" if rc != 0 else "info",
        "detail": notes_line.strip() or err.strip()[:200],
        "fix_hint": "Verifier le vault Obsidian et les chemins dans workspace/obsidian_bridge_config.json" if rc != 0 else None,
    }


def check_obsidian_subcommands() -> dict[str, Any]:
    bridge = SCRIPTS / "obsidian_second_brain.py"
    if not _safe_exists(bridge):
        return {
            "name": "obsidian_subcommands",
            "ok": False,
            "severity": "error",
            "detail": "obsidian_second_brain.py introuvable",
            "fix_hint": "Restaurer obsidian_second_brain.py depuis backups/",
        }
    text = bridge.read_text(encoding="utf-8", errors="replace")
    found = [name for name in OBSIDIAN_REQUIRED_SUBCOMMANDS if f'sub.add_parser("{name}"' in text]
    missing = [name for name in OBSIDIAN_REQUIRED_SUBCOMMANDS if name not in found]
    return {
        "name": "obsidian_subcommands",
        "ok": not missing,
        "severity": "warn" if missing else "info",
        "detail": f"{len(found)}/{len(OBSIDIAN_REQUIRED_SUBCOMMANDS)} sous-commandes presentes" + (f", manquantes: {missing}" if missing else ""),
        "fix_hint": "Ajouter les sous-commandes manquantes au argparse de obsidian_second_brain.py" if missing else None,
    }


def check_vault_access() -> dict[str, Any]:
    cfg = _read_json(WORKSPACE / "obsidian_bridge_config.json")
    vault = Path(str(cfg.get("vault_path") or r"C:\Users\user\Mon Drive\DriveSyncFiles\ARCHITECTE_SYSTEM"))
    if not _safe_exists(vault):
        return {
            "name": "vault_access",
            "ok": False,
            "severity": "error",
            "detail": f"vault path not accessible: {vault}",
            "fix_hint": "Verifier que Google Drive Desktop est connecte et que le compte monagenda.be est actif",
        }
    try:
        is_dir = vault.is_dir()
    except OSError:
        is_dir = False
    if not is_dir:
        return {
            "name": "vault_access",
            "ok": False,
            "severity": "error",
            "detail": f"vault path is not a directory: {vault}",
            "fix_hint": "Verifier le chemin du vault dans workspace/obsidian_bridge_config.json",
        }
    can_write = False
    test_file = vault / ".nanobot_self_check.tmp"
    try:
        test_file.write_text("ok", encoding="utf-8")
        can_write = True
        test_file.unlink()
    except OSError:
        can_write = False
    return {
        "name": "vault_access",
        "ok": can_write,
        "severity": "info" if can_write else "warn",
        "detail": f"vault={vault}, writable={can_write}",
        "fix_hint": "Verifier les permissions du dossier" if not can_write else None,
    }


def check_google_oauth() -> dict[str, Any]:
    rc, out, err = _run([sys.executable, str(SCRIPTS / "google_workspace_cli.py"), "--json", "auth", "status"], timeout=30)
    if rc != 0:
        return {
            "name": "google_oauth",
            "ok": False,
            "severity": "warn",
            "detail": f"cli exit={rc}: {(err or out)[-200:]}",
            "fix_hint": "Lancer python scripts/google_workspace_cli.py --json auth status pour diagnostic detaille",
        }
    try:
        payload = json.loads(out)
    except Exception:
        return {
            "name": "google_oauth",
            "ok": False,
            "severity": "warn",
            "detail": f"reponse non-JSON: {out[-200:]}",
            "fix_hint": None,
        }
    valid = bool(payload.get("valid"))
    refresh = bool(payload.get("has_refresh_token"))
    scopes_ok = bool(payload.get("has_required_scopes"))
    detail = f"valid={valid}, refresh_token={refresh}, scopes_ok={scopes_ok}"
    if valid:
        return {"name": "google_oauth", "ok": True, "severity": "info", "detail": detail, "fix_hint": None}
    if refresh:
        return {
            "name": "google_oauth",
            "ok": False,
            "severity": "warn",
            "detail": detail + " (token expire mais refresh dispo)",
            "fix_hint": "self_check.py recover refresh-google",
        }
    return {
        "name": "google_oauth",
        "ok": False,
        "severity": "error",
        "detail": detail + " (refresh manquant)",
        "fix_hint": "Reauthoriser via setup_google_auth.py --force",
    }


def check_ollama() -> dict[str, Any]:
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=2):
            pass
        return {"name": "ollama_daemon", "ok": True, "severity": "info", "detail": "port 11434 listening", "fix_hint": None}
    except OSError as exc:
        return {
            "name": "ollama_daemon",
            "ok": False,
            "severity": "warn",
            "detail": f"port 11434 unreachable: {exc}",
            "fix_hint": "Lancer ollama serve ou nanobot_ollama_restart.bat",
        }


def check_gateway_lock() -> dict[str, Any]:
    lock = OMEGA / "state" / "gateway.lock"
    if not _safe_exists(lock):
        return {
            "name": "gateway_lock",
            "ok": False,
            "severity": "warn",
            "detail": "no gateway.lock — Telegram gateway probably not running",
            "fix_hint": "Lancer Start-NanobotTelegramGateway.ps1 ou Run-NanobotOmegaSupervisor.ps1",
        }
    try:
        data = json.loads(lock.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {"name": "gateway_lock", "ok": False, "severity": "warn", "detail": "lock unreadable", "fix_hint": None}
    pid = data.get("pid")
    return {"name": "gateway_lock", "ok": True, "severity": "info", "detail": f"gateway pid={pid}, started={data.get('timestamp')}", "fix_hint": None}


def check_startup_context_freshness() -> dict[str, Any]:
    md = WORKSPACE / "NANOBOT_STARTUP_CONTEXT.md"
    if not _safe_exists(md):
        return {
            "name": "startup_context_freshness",
            "ok": False,
            "severity": "warn",
            "detail": "NANOBOT_STARTUP_CONTEXT.md absent",
            "fix_hint": "Lancer python scripts/build_startup_context.py",
        }
    try:
        age_sec = (datetime.now(timezone.utc).timestamp() - md.stat().st_mtime)
    except OSError:
        return {"name": "startup_context_freshness", "ok": False, "severity": "warn", "detail": "stat failed", "fix_hint": None}
    age_h = age_sec / 3600
    fresh = age_h < 48
    return {
        "name": "startup_context_freshness",
        "ok": fresh,
        "severity": "info" if fresh else "warn",
        "detail": f"age = {age_h:.1f}h",
        "fix_hint": "Lancer python scripts/build_startup_context.py" if not fresh else None,
    }


def check_memory_dedup() -> dict[str, Any]:
    mem = WORKSPACE / "memory" / "MEMORY.md"
    if not _safe_exists(mem):
        return {"name": "memory_dedup", "ok": True, "severity": "info", "detail": "no MEMORY.md (skip)", "fix_hint": None}
    text = mem.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("## ")]
    duplicate_headers = [h for h in set(lines) if lines.count(h) > 1]
    ok = not duplicate_headers
    return {
        "name": "memory_dedup",
        "ok": ok,
        "severity": "warn" if not ok else "info",
        "detail": f"{len(duplicate_headers)} en-tetes dupliques: {duplicate_headers[:5]}",
        "fix_hint": "self_check.py recover dedup-memory" if not ok else None,
    }


def check_capabilities_doc_consistency() -> dict[str, Any]:
    arsenal_old = WORKSPACE / "ARSENAL.md"
    arsenal_new = WORKSPACE / "NANOBOT_ARSENAL.md"
    tools_old = WORKSPACE / "TOOLS.md"
    issues: list[str] = []
    if _safe_exists(arsenal_old) and _safe_exists(arsenal_new):
        head = arsenal_old.read_text(encoding="utf-8", errors="replace")[:200].lower()
        if "deprecated" not in head:
            issues.append("ARSENAL.md (ancien) coexiste avec NANOBOT_ARSENAL.md sans bandeau DEPRECATED")
    if _safe_exists(tools_old):
        head = tools_old.read_text(encoding="utf-8", errors="replace")[:200].lower()
        if "deprecated" not in head:
            issues.append("TOOLS.md (ancien) sans bandeau DEPRECATED")
    return {
        "name": "capabilities_doc_consistency",
        "ok": not issues,
        "severity": "warn" if issues else "info",
        "detail": "; ".join(issues) if issues else "documents de capacites coherents",
        "fix_hint": "Ajouter > DEPRECATED en tete des fichiers anciens" if issues else None,
    }


def check_chrome_installed() -> dict[str, Any]:
    candidates = [
        Path(r"C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path(r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        Path(r"C:/Users/user/AppData/Local/Google/Chrome/Application/chrome.exe"),
    ]
    found = next((p for p in candidates if _safe_exists(p)), None)
    return {
        "name": "chrome_installed",
        "ok": found is not None,
        "severity": "warn" if found is None else "info",
        "detail": f"chrome.exe = {found}" if found else "Chrome non trouvé",
        "fix_hint": "winget install Google.Chrome" if not found else None,
    }


def check_playwright_runtime() -> dict[str, Any]:
    pw_root = Path(r"C:/Users/user/AppData/Local/ms-playwright")
    if not _safe_exists(pw_root):
        return {"name": "playwright_runtime", "ok": False, "severity": "warn", "detail": "ms-playwright dir manquant", "fix_hint": "python -m playwright install chromium"}
    chromium_dirs = [d for d in pw_root.iterdir() if d.is_dir() and d.name.startswith("chromium-")]
    if not chromium_dirs:
        return {"name": "playwright_runtime", "ok": False, "severity": "warn", "detail": "Aucun chromium dans ms-playwright", "fix_hint": "python -m playwright install chromium"}
    rc, _, err = _run([sys.executable, "-c", "import playwright; print(playwright.__version__ if hasattr(playwright,'__version__') else 'ok')"], timeout=10)
    return {
        "name": "playwright_runtime",
        "ok": rc == 0,
        "severity": "info" if rc == 0 else "warn",
        "detail": f"chromium dirs: {[d.name for d in chromium_dirs[:3]]}, py module rc={rc}" + (f", err={err[:80]}" if rc != 0 else ""),
        "fix_hint": "pip install playwright && python -m playwright install chromium" if rc != 0 else None,
    }


def check_scraping_champion() -> dict[str, Any]:
    script = SCRIPTS / "scraping_champion.py"
    if not _safe_exists(script):
        return {"name": "scraping_champion", "ok": False, "severity": "error", "detail": "scraping_champion.py absent", "fix_hint": "Restaurer depuis backups/"}
    rc, out, err = _run([sys.executable, str(script), "--help"], timeout=15)
    return {
        "name": "scraping_champion",
        "ok": rc == 0,
        "severity": "info" if rc == 0 else "warn",
        "detail": f"--help rc={rc}" + (f", err={err[:100]}" if rc != 0 else ""),
        "fix_hint": "Verifier requests, beautifulsoup4, playwright dependances" if rc != 0 else None,
    }


def check_veille_2ememain_task() -> dict[str, Any]:
    rc, out, err = _run(["powershell", "-NoProfile", "-Command", "Get-ScheduledTask -TaskName NanobotVeille2ememain -ErrorAction SilentlyContinue | Select-Object -ExpandProperty State"], timeout=15)
    state = (out or "").strip()
    if not state:
        return {"name": "veille_2ememain_task", "ok": False, "severity": "error", "detail": "Tache NanobotVeille2ememain absente", "fix_hint": "schtasks /Create avec wrapper bat (admin)"}
    if state.lower() == "disabled":
        return {"name": "veille_2ememain_task", "ok": False, "severity": "warn", "detail": "Tache DISABLED (pause)", "fix_hint": "veille2 resume (admin requis)"}
    return {"name": "veille_2ememain_task", "ok": True, "severity": "info", "detail": f"State = {state}", "fix_hint": None}


def check_veille_2ememain_health() -> dict[str, Any]:
    log_path = OMEGA / "logs" / "veille_direct.log"
    if not _safe_exists(log_path):
        return {"name": "veille_2ememain_health", "ok": False, "severity": "warn", "detail": "veille_direct.log absent", "fix_hint": "Lancer une fois la veille manuellement"}
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"name": "veille_2ememain_health", "ok": False, "severity": "warn", "detail": "Log unreadable", "fix_hint": None}
    lines = text.splitlines()[-200:]
    runs = [line for line in lines if "=== START run_veille_and_notify" in line]
    fails = [line for line in lines if "Scraper failed" in line or "FATAL" in line or "UNHANDLED" in line]
    last_send = next((line for line in reversed(lines) if "Telegram send: OK" in line), None)
    last_run = runs[-1] if runs else None
    if last_run is None:
        return {"name": "veille_2ememain_health", "ok": False, "severity": "warn", "detail": "Aucun run dans les logs récents", "fix_hint": "veille2 run"}
    detail = f"runs récents: {len(runs)}, échecs: {len(fails)}, dernier run: {last_run[1:21]}"
    if last_send:
        detail += f", dernière notif Telegram OK: {last_send[1:21]}"
    severity = "warn" if len(fails) >= 3 else "info"
    return {"name": "veille_2ememain_health", "ok": len(fails) < 3, "severity": severity, "detail": detail, "fix_hint": "Voir logs/veille_direct.log et schtasks /Query /TN NanobotVeille2ememain /V" if len(fails) >= 3 else None}


def check_built_in_tools_audit() -> dict[str, Any]:
    audit = HEALTH / "tools_audit.json"
    if not _safe_exists(audit):
        return {
            "name": "built_in_tools_audit",
            "ok": False,
            "severity": "warn",
            "detail": "health/tools_audit.json absent",
            "fix_hint": "Lancer python scripts/tools_audit.py",
        }
    data = _read_json(audit)
    tools = data.get("tools") or []
    failed = [t["name"] for t in tools if t.get("callable_test") == "fail"]
    return {
        "name": "built_in_tools_audit",
        "ok": not failed,
        "severity": "warn" if failed else "info",
        "detail": f"{len(tools)} tools, {len(failed)} fail: {failed}",
        "fix_hint": None,
    }


CHECKS: list[Callable[[], dict[str, Any]]] = [
    check_workspace_layout,
    check_critical_docs,
    check_operational_scripts,
    check_obsidian_bridge,
    check_obsidian_subcommands,
    check_vault_access,
    check_google_oauth,
    check_ollama,
    check_gateway_lock,
    check_startup_context_freshness,
    check_memory_dedup,
    check_capabilities_doc_consistency,
    check_built_in_tools_audit,
    check_chrome_installed,
    check_playwright_runtime,
    check_scraping_champion,
    check_veille_2ememain_task,
    check_veille_2ememain_health,
]


def run_checks() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for func in CHECKS:
        try:
            results.append(func())
        except Exception as exc:
            results.append({
                "name": func.__name__,
                "ok": False,
                "severity": "error",
                "detail": f"check raised {type(exc).__name__}: {exc}",
                "fix_hint": None,
            })
    errors = sum(1 for r in results if not r["ok"] and r.get("severity") == "error")
    warns = sum(1 for r in results if not r["ok"] and r.get("severity") == "warn")
    score = "OK"
    if errors:
        score = "CASSE"
    elif warns:
        score = "DEGRADE"
    return {
        "generated_at": _now_iso(),
        "score": score,
        "errors": errors,
        "warns": warns,
        "checks": results,
    }


def render_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    score = report["score"]
    icon = {"OK": "[OK]", "DEGRADE": "[DEGRADE]", "CASSE": "[CASSE]"}.get(score, "[?]")
    lines.append(f"{icon} Etat global Nanobot : {score}")
    lines.append(f"  {report['errors']} erreur(s) bloquantes, {report['warns']} avertissement(s)")
    lines.append(f"  Genere : {report['generated_at']}")
    lines.append("")
    for c in report["checks"]:
        flag = "OK " if c["ok"] else ("WARN" if c["severity"] == "warn" else "FAIL")
        lines.append(f"  [{flag}] {c['name']}: {c['detail']}")
        if not c["ok"] and c.get("fix_hint"):
            lines.append(f"         -> reparation : {c['fix_hint']}")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{report['generated_at']}] {report['score']} errors={report['errors']} warns={report['warns']}\n"
    with OUT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line)


# ---------------------------------------------------------------------------
# Recovery actions
# ---------------------------------------------------------------------------


def recover_refresh_google() -> dict[str, Any]:
    rc, out, err = _run(
        [sys.executable, str(SCRIPTS / "google_workspace_cli.py"), "--json", "auth", "refresh"],
        timeout=60,
    )
    return {"action": "refresh-google", "ok": rc == 0, "stdout": out[-500:], "stderr": err[-500:]}


def recover_rebuild_startup_context() -> dict[str, Any]:
    rc, out, err = _run(
        [sys.executable, str(SCRIPTS / "build_startup_context.py"), "--quiet"],
        timeout=60,
    )
    return {"action": "rebuild-startup-context", "ok": rc == 0, "stdout": out[-500:], "stderr": err[-500:]}


def recover_rebuild_tools_audit() -> dict[str, Any]:
    rc, out, err = _run([sys.executable, str(SCRIPTS / "tools_audit.py")], timeout=60)
    return {"action": "rebuild-tools-audit", "ok": rc == 0, "stdout": out[-500:], "stderr": err[-500:]}


RECOVERY_ACTIONS: dict[str, Callable[[], dict[str, Any]]] = {
    "refresh-google": recover_refresh_google,
    "rebuild-startup-context": recover_rebuild_startup_context,
    "rebuild-tools-audit": recover_rebuild_tools_audit,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nanobot self-check / recovery.")
    sub = parser.add_subparsers(dest="cmd")

    check_p = sub.add_parser("check", help="Audit complet (defaut)")
    check_p.add_argument("--json", action="store_true", help="Sortie JSON brut")
    check_p.add_argument("--quiet", action="store_true", help="Pas de texte humain")

    recover_p = sub.add_parser("recover", help="Tente une reparation connue")
    recover_p.add_argument("action", choices=sorted(RECOVERY_ACTIONS.keys()) + ["all"])

    sub.add_parser("capabilities", help="Liste les capacites verifiees")

    args = parser.parse_args(argv or sys.argv[1:])
    cmd = args.cmd or "check"

    if cmd == "check":
        report = run_checks()
        write_report(report)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif not args.quiet:
            print(render_text(report))
        return 0 if report["score"] == "OK" else (2 if report["score"] == "CASSE" else 1)

    if cmd == "recover":
        if args.action == "all":
            results = [func() for func in RECOVERY_ACTIONS.values()]
        else:
            results = [RECOVERY_ACTIONS[args.action]()]
        print(json.dumps({"recovery": results, "at": _now_iso()}, ensure_ascii=False, indent=2))
        return 0 if all(r.get("ok") for r in results) else 1

    if cmd == "capabilities":
        report = run_checks()
        caps = [
            {
                "name": c["name"],
                "available": c["ok"],
                "detail": c["detail"],
            }
            for c in report["checks"]
        ]
        print(json.dumps({"capabilities": caps, "score": report["score"]}, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
