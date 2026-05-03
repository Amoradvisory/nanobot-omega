"""Nanobot capabilities registry — source de verite unique.

Genere :
- workspace/NANOBOT_CAPABILITIES.json (machine-readable)
- workspace/NANOBOT_CAPABILITIES.md   (humain, idem mais lisible)

Categories :
- builtin_tools     : tools natifs Nanobot (browser_automation, exec, ...)
- obsidian          : sous-commandes obsidian_second_brain.py
- google_workspace  : sous-commandes google_workspace_cli.py
- operational       : scripts metier (scraping_champion, app_acquisition, ...)
- mcp_servers       : serveurs MCP declares dans config_omega.json

Pour chaque capacite :
- name             : identifiant
- category
- description
- module           : chemin du script ou de la sous-commande
- read_only        : True si la capacite ne modifie pas l'etat
- requires_confirmation : True si la capacite necessite une confirmation
- risk_level       : "safe" | "moderate" | "destructive"
- status           : "ok" | "broken" | "missing" | "unknown"
- last_check       : timestamp ISO du dernier verification
- example          : exemple d'invocation
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OMEGA = Path(r"C:\AI\nanobot-omega")
WORKSPACE = OMEGA / "workspace"
SCRIPTS = OMEGA / "scripts"
HEALTH = OMEGA / "health"

OUT_JSON = WORKSPACE / "NANOBOT_CAPABILITIES.json"
OUT_MD = WORKSPACE / "NANOBOT_CAPABILITIES.md"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=str(OMEGA), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as exc:
        return 1, "", str(exc)


# ---------------------------------------------------------------------------
# Capability metadata. risk_level/read_only/requires_confirmation are intent
# documentation. Status is checked at runtime against the file system.
# ---------------------------------------------------------------------------

OBSIDIAN_CAPABILITIES = [
    # name, description, read_only, requires_confirmation, risk_level
    ("bootstrap", "Initialise la structure du vault et les notes pivots", False, False, "safe"),
    ("status", "Etat global du vault (chemins, comptes, derniere note)", True, False, "safe"),
    ("open", "Ouvre une note dans Obsidian (URI obsidian://)", True, False, "safe"),
    ("capture", "Cree une nouvelle note de capture auto-classifiee", False, False, "safe"),
    ("daily", "Ajoute du contenu a la note du jour", False, False, "safe"),
    ("import", "Importe un PDF/image/markdown dans le vault", False, False, "safe"),
    ("search", "Recherche dans le vault", True, False, "safe"),
    ("sync-memory", "Synchronise la memoire Nanobot dans le vault", False, False, "safe"),
    ("relations", "Retisse les relations Hubs utiles / Passerelles utiles", False, False, "moderate"),
    ("write-note", "Cree ou modifie une note", False, False, "moderate"),
    ("read-note", "Lit une note (frontmatter + body) en JSON", True, False, "safe"),
    ("delete-path", "Supprime fichier ou dossier du vault", False, True, "destructive"),
    ("create-folder", "Cree un dossier dans le vault", False, False, "safe"),
    ("rename-path", "Renomme/deplace fichier ou dossier", False, True, "moderate"),
    ("move-note", "Deplace une note vers un autre dossier", False, True, "moderate"),
    ("list", "Liste recursive du vault ou d'un sous-dossier", True, False, "safe"),
    ("set-frontmatter", "Fusionne des cles dans le frontmatter d'une note", False, False, "moderate"),
    ("get-frontmatter", "Lit le frontmatter d'une note", True, False, "safe"),
    ("filter-notes", "Filtre les notes par tag/propriete/dossier/texte", True, False, "safe"),
    ("tags", "Ajoute/retire des tags d'une note", False, False, "safe"),
    ("sync-status", "Etat de la synchronisation Google Drive du vault", True, False, "safe"),
    ("attachments", "Liste les pieces jointes non-Markdown", True, False, "safe"),
    ("add-attachment", "Copie une piece jointe dans le vault", False, False, "safe"),
    ("move-attachment", "Renomme/deplace une piece jointe", False, True, "moderate"),
]

OPERATIONAL_SCRIPTS = [
    # name, script_relative, description, read_only, requires_confirmation, risk_level
    ("obsidian_bridge", "scripts/obsidian_second_brain.py", "Pont Obsidian (24 sous-commandes)", False, False, "moderate"),
    ("google_workspace_cli", "scripts/google_workspace_cli.py", "CLI Gmail/Calendar/Drive/Docs/Sheets/Tasks/Contacts", False, False, "moderate"),
    ("google_workspace_mcp", "scripts/google_workspace_mcp.py", "Serveur MCP Google Workspace local (44 outils)", False, False, "moderate"),
    ("scraping_champion", "scripts/scraping_champion.py", "Scraping web (HTTP + Playwright fallback)", True, False, "safe"),
    ("app_acquisition", "scripts/app_acquisition.py", "Installer/ouvrir/verifier apps Windows (winget)", False, True, "moderate"),
    ("proactive_intel", "scripts/proactive_intel.py", "Veille RSS/web proactive", True, False, "safe"),
    ("desktop_intel", "scripts/desktop_intel.py", "Liste fenetres Windows + OCR + xlsx", True, False, "safe"),
    ("resilience_orchestrator", "scripts/resilience_orchestrator.py", "Plans multi-routes + impasse detection", True, False, "safe"),
    ("agent_forge", "scripts/agent_forge.py", "Genere des mini-agents ad hoc", False, False, "moderate"),
    ("build_startup_context", "scripts/build_startup_context.py", "Regenere NANOBOT_STARTUP_CONTEXT.md/json", False, False, "safe"),
    ("nanobot_self_check", "scripts/nanobot_self_check.py", "Health-check + recovery", True, False, "safe"),
    ("capabilities_registry", "scripts/capabilities_registry.py", "Registre central des capacites (ce script)", False, False, "safe"),
    ("tools_audit", "scripts/tools_audit.py", "Audit runtime des tools natifs", True, False, "safe"),
    ("workspace_cleanup", "scripts/workspace_cleanup.py", "Inventaire + quarantaine workspace", False, True, "moderate"),
    ("dedup_memory", "scripts/dedup_memory.py", "Deduplique MEMORY.md", False, False, "safe"),
    ("test_obsidian_bridge", "scripts/test_obsidian_bridge.py", "Tests E2E anti-regression bridge Obsidian (15 cas)", True, False, "safe"),
    ("tasks_control", "scripts/tasks_control.py", "Gestion tasks Windows Nanobot (list/health/run/pause/resume/logs)", False, True, "moderate"),
    ("veille_2ememain_control", "workspace/veille_2ememain_control.py", "Pilotage veille 2ememain (status/health/run/Xkm/test-notification)", False, True, "moderate"),
    ("run_veille_2ememain", "workspace/run_veille_2ememain.py", "Scraper Playwright 2ememain (deterministe, sans LLM)", True, False, "safe"),
    ("run_veille_and_notify", "workspace/run_veille_and_notify.py", "Orchestrateur veille + notif Telegram enrichie (photo/distance/scoring/NL)", False, False, "moderate"),
]

BROWSER_CAPABILITIES = [
    # name, description, read_only, requires_confirmation, risk_level, status_check
    ("browser.chrome_launcher", "Ouvre un onglet Chrome dans le profil partage (sessions persistees, anti-timeout)", False, False, "safe", "C:/AI/nanobot-omega/Open-Shared-Nanobot-Browser.bat"),
    ("browser.chrome_executable", "Detection chrome.exe pour Playwright/CDP", True, False, "safe", "C:/Program Files/Google/Chrome/Application/chrome.exe"),
    ("browser.playwright_chromium", "Chromium headless installe (chromium-1208) pour scraping JS-heavy", True, False, "safe", "C:/Users/user/AppData/Local/ms-playwright/chromium-1208"),
    ("browser.playwright_firefox", "Firefox alternatif via Playwright", True, False, "safe", "C:/Users/user/AppData/Local/ms-playwright/firefox-1509"),
    ("browser.shared_chrome_profile", "Profil Chrome partage (sessions Google/Notion/2ememain persistees)", True, False, "safe", "C:/AI/nanobot-omega/shared-browser/chrome-profile"),
    ("browser.cdp_debug_port", "Port CDP 9222 pour browser_automation natif (debugging Chrome ouvert)", False, False, "moderate", "9222"),
    ("scraping.scraping_champion", "Scraping general (HTTP + Playwright fallback) avec export xlsx/md/json", True, False, "safe", "scripts/scraping_champion.py"),
    ("watch.veille_2ememain", "Veille 2ememain : objets gratuits autour de Mouscron 50km, NL+FR, Telegram enrichi photo/distance/score", False, False, "safe", "workspace/run_veille_and_notify.py"),
    ("watch.translation_cache", "Cache de traduction Google Translate gratuite NL->FR (persistant)", True, False, "safe", "workspace/veille_2ememain_translation_cache.json"),
    ("watch.health_journal", "Journal de sante de la veille (last 20 runs, 3-fail alert auto Telegram)", True, False, "safe", "logs/veille_health.json"),
]

GOOGLE_WORKSPACE_FAMILIES = [
    ("gmail", "Gmail : search/read/send + labels + modify (read/unread, archive, trash, untrash, delete)"),
    ("calendar", "Calendar : list/create/delete events"),
    ("drive", "Drive : list/search/read/upload/create-folder/update-metadata/move/delete"),
    ("docs", "Google Docs : create/read/append/delete"),
    ("sheets", "Google Sheets : create/read/append-row/update/clear/delete"),
    ("tasks", "Tasks : list/add/complete"),
    ("contacts", "Contacts : list/search/create"),
    ("auth", "OAuth : status/refresh/setup"),
]


def _scan_obsidian_status() -> str:
    bridge = SCRIPTS / "obsidian_second_brain.py"
    if not _exists(bridge):
        return "missing"
    text = bridge.read_text(encoding="utf-8", errors="replace")
    found = sum(1 for name, *_ in OBSIDIAN_CAPABILITIES if f'sub.add_parser("{name}"' in text)
    if found == len(OBSIDIAN_CAPABILITIES):
        return "ok"
    if found > 0:
        return "partial"
    return "broken"


def _scan_script_status(rel: str) -> str:
    if not _exists(OMEGA / rel):
        return "missing"
    return "ok"


def _scan_builtin_tools() -> list[dict[str, Any]]:
    audit = HEALTH / "tools_audit.json"
    if not _exists(audit):
        # Best-effort regen
        _run([sys.executable, str(SCRIPTS / "tools_audit.py")], timeout=20)
    data = _read_json(audit)
    out: list[dict[str, Any]] = []
    for tool in data.get("tools", []):
        name = tool.get("name") or ""
        callable_test = tool.get("callable_test")
        importable = tool.get("importable")
        in_runtime = tool.get("in_runtime_tools")
        if callable_test == "ok" or (in_runtime and callable_test == "skipped"):
            status = "ok"
        elif callable_test == "fail":
            status = "broken"
        elif not importable:
            status = "missing"
        else:
            status = "unknown"
        out.append({
            "name": name,
            "category": "builtin_tool",
            "description": "Tool natif enregistre par le runtime Nanobot",
            "module": tool.get("declared_in") or [],
            "read_only": name in {"read_file", "list_dir", "grep", "glob", "web_search", "web_fetch", "ocr", "vision_analyze_image", "tool_diagnostics"},
            "requires_confirmation": False,
            "risk_level": "destructive" if name in {"exec", "write_file", "edit_file"} else ("moderate" if name in {"browser_automation", "desktop_automation"} else "safe"),
            "status": status,
            "mcp_server": tool.get("mcp_server"),
            "last_called_at": tool.get("last_called_at"),
            "example": _builtin_example(name),
        })
    return out


def _builtin_example(name: str) -> str | None:
    return {
        "read_file": "read_file(path='C:/AI/nanobot-omega/AGENT_V2.md')",
        "write_file": "write_file(path='...', content='...')",
        "edit_file": "edit_file(path='...', old='...', new='...')",
        "list_dir": "list_dir(path='C:/AI/nanobot-omega')",
        "grep": "grep(pattern='TODO', path='...')",
        "glob": "glob(pattern='**/*.py')",
        "exec": "exec(command='dir C:\\\\AI')",
        "web_search": "web_search(query='...')",
        "web_fetch": "web_fetch(url='https://...')",
        "browser_automation": "browser_automation(action='click', selector='...')",
        "desktop_automation": "desktop_automation(action='screenshot')",
        "ocr": "ocr(path='C:/path/image.png')",
        "vision_analyze_image": "vision_analyze_image(path='...', prompt='...')",
        "tool_diagnostics": "tool_diagnostics(target='capabilities')",
    }.get(name)


def _build_obsidian_capabilities() -> list[dict[str, Any]]:
    bridge = SCRIPTS / "obsidian_second_brain.py"
    text = bridge.read_text(encoding="utf-8", errors="replace") if _exists(bridge) else ""
    out: list[dict[str, Any]] = []
    for name, desc, read_only, needs_confirm, risk in OBSIDIAN_CAPABILITIES:
        present = f'sub.add_parser("{name}"' in text
        out.append({
            "name": f"obsidian.{name}",
            "category": "obsidian",
            "description": desc,
            "module": "scripts/obsidian_second_brain.py",
            "subcommand": name,
            "read_only": read_only,
            "requires_confirmation": needs_confirm,
            "risk_level": risk,
            "status": "ok" if present else "missing",
            "example": f"python C:/AI/nanobot-omega/scripts/obsidian_second_brain.py {name} ...",
        })
    return out


def _build_operational_capabilities() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, rel, desc, read_only, needs_confirm, risk in OPERATIONAL_SCRIPTS:
        out.append({
            "name": name,
            "category": "operational",
            "description": desc,
            "module": rel,
            "read_only": read_only,
            "requires_confirmation": needs_confirm,
            "risk_level": risk,
            "status": _scan_script_status(rel),
            "example": f"python C:/AI/nanobot-omega/{rel} --help",
        })
    return out


def _build_google_capabilities() -> list[dict[str, Any]]:
    cli = SCRIPTS / "google_workspace_cli.py"
    cli_present = _exists(cli)
    out: list[dict[str, Any]] = []
    for family, desc in GOOGLE_WORKSPACE_FAMILIES:
        out.append({
            "name": f"google.{family}",
            "category": "google_workspace",
            "description": desc,
            "module": "scripts/google_workspace_cli.py",
            "read_only": family in {"auth"},
            "requires_confirmation": family in {"gmail"},
            "risk_level": "destructive" if family == "gmail" else "moderate",
            "status": "ok" if cli_present else "missing",
            "example": f"python C:/AI/nanobot-omega/scripts/google_workspace_cli.py --json {family} ...",
        })
    return out


def _build_mcp_capabilities() -> list[dict[str, Any]]:
    cfg = _read_json(OMEGA / "config_omega.json")
    servers = (cfg.get("tools") or {}).get("mcpServers") or {}
    out: list[dict[str, Any]] = []
    for name, conf in sorted(servers.items()):
        enabled_tools = conf.get("enabledTools")
        disabled = enabled_tools == []
        out.append({
            "name": f"mcp.{name}",
            "category": "mcp_server",
            "description": f"Serveur MCP {name}",
            "module": "config_omega.json",
            "read_only": False,
            "requires_confirmation": False,
            "risk_level": "moderate",
            "status": "disabled" if disabled else "ok",
            "example": None,
        })
    return out


def _build_browser_capabilities() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, desc, read_only, needs_confirm, risk, ref in BROWSER_CAPABILITIES:
        if ref.startswith("scripts/") or ref.startswith("workspace/") or ref.startswith("logs/"):
            status = "ok" if _exists(OMEGA / ref) else "missing"
        elif Path(ref).is_absolute():
            status = "ok" if _exists(Path(ref)) else "missing"
        else:
            status = "ok"  # port number or constant
        out.append({
            "name": name,
            "category": "browser",
            "description": desc,
            "module": ref,
            "read_only": read_only,
            "requires_confirmation": needs_confirm,
            "risk_level": risk,
            "status": status,
            "example": None,
        })
    return out


def build_registry() -> dict[str, Any]:
    builtin = _scan_builtin_tools()
    obsidian = _build_obsidian_capabilities()
    operational = _build_operational_capabilities()
    google = _build_google_capabilities()
    mcp = _build_mcp_capabilities()
    browser = _build_browser_capabilities()

    capabilities = builtin + obsidian + operational + google + mcp + browser
    by_status: dict[str, int] = {}
    for cap in capabilities:
        by_status[cap["status"]] = by_status.get(cap["status"], 0) + 1
    return {
        "generated_at": _now(),
        "total": len(capabilities),
        "by_status": by_status,
        "by_category": {
            "builtin_tools": len(builtin),
            "obsidian": len(obsidian),
            "operational": len(operational),
            "google_workspace": len(google),
            "mcp_servers": len(mcp),
            "browser": len(browser),
        },
        "capabilities": capabilities,
    }


def render_markdown(reg: dict[str, Any]) -> str:
    lines = [
        "# NANOBOT — Registre des capacites",
        "",
        "> Source de verite unique. Genere automatiquement par",
        "> `python C:/AI/nanobot-omega/scripts/capabilities_registry.py`.",
        "> Ne pas editer a la main.",
        "",
        f"Genere : {reg['generated_at']}",
        f"Total : {reg['total']} capacites",
        "",
        "## Par statut",
    ]
    for status, count in sorted(reg["by_status"].items()):
        lines.append(f"- {status}: {count}")
    lines.append("")
    lines.append("## Par categorie")
    for cat, count in reg["by_category"].items():
        lines.append(f"- {cat}: {count}")
    lines.append("")

    for cat_label in ["builtin_tools", "obsidian", "operational", "google_workspace", "mcp_servers"]:
        cat_caps = [c for c in reg["capabilities"] if (
            c["category"] == "builtin_tool" if cat_label == "builtin_tools"
            else c["category"] == cat_label.rstrip("s") if cat_label in {"mcp_servers"}
            else c["category"] == cat_label
        )]
        if not cat_caps:
            continue
        lines.append(f"## Categorie : {cat_label}")
        lines.append("")
        lines.append("| nom | statut | risque | read-only | confirmation | description |")
        lines.append("|-----|--------|--------|-----------|--------------|-------------|")
        for cap in cat_caps:
            ro = "oui" if cap.get("read_only") else "non"
            cf = "oui" if cap.get("requires_confirmation") else "non"
            risk = cap.get("risk_level") or "?"
            desc = (cap.get("description") or "").replace("|", "\\|")
            lines.append(f"| `{cap['name']}` | {cap['status']} | {risk} | {ro} | {cf} | {desc} |")
        lines.append("")

    lines.extend([
        "## Comment utiliser ce registre",
        "",
        "1. Avant de declarer une capacite indisponible, lire ce registre.",
        "2. Si une capacite manque (status=missing) verifier le module indique.",
        "3. Pour une capacite cassee (status=broken) lancer `nanobot_self_check.py check`.",
        "4. Le registre est regenere par `Run-NanobotOmegaSupervisor.ps1` au demarrage.",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Registre central des capacites Nanobot.")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--show", action="store_true", help="Affiche le registre JSON sur stdout")
    args = parser.parse_args(argv or sys.argv[1:])

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    reg = build_registry()
    OUT_JSON.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(render_markdown(reg), encoding="utf-8")

    if args.show:
        print(json.dumps(reg, ensure_ascii=False, indent=2))
    elif not args.quiet:
        print(json.dumps({
            "ok": True,
            "json": str(OUT_JSON),
            "md": str(OUT_MD),
            "total": reg["total"],
            "by_status": reg["by_status"],
            "by_category": reg["by_category"],
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
