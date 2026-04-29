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


ROOT = Path(r"C:\AI\nanobot-omega")
WORKSPACE = ROOT / "workspace"
OUT_MD = WORKSPACE / "NANOBOT_STARTUP_CONTEXT.md"
OUT_JSON = WORKSPACE / "NANOBOT_STARTUP_CONTEXT.json"


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except Exception:
        return False


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def _run_json(cmd: list[str], timeout: int = 20) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc), "command": cmd}
    try:
        payload = json.loads(proc.stdout)
    except Exception:
        payload = {
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        }
    payload["returncode"] = proc.returncode
    payload["ok"] = proc.returncode == 0
    return payload


def _mcp_tool_count() -> int:
    path = ROOT / "scripts" / "google_workspace_mcp.py"
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    return len(re.findall(r"@mcp\.tool\(\)", text))


def _module_status() -> dict[str, bool]:
    scripts = [
        "google_workspace_cli.py",
        "google_workspace_mcp.py",
        "obsidian_second_brain.py",
        "scraping_champion.py",
        "app_acquisition.py",
        "proactive_intel.py",
        "desktop_intel.py",
        "resilience_orchestrator.py",
        "agent_forge.py",
    ]
    return {name: _exists(ROOT / "scripts" / name) for name in scripts}


def _doc_status() -> dict[str, bool]:
    docs = [
        "NANOBOT_RECENT_UPGRADES.md",
        "GOOGLE_WORKSPACE_CAPABILITIES.md",
        "RADICAL_CAPABILITIES.md",
        "NANOBOT_STARTUP_CONTEXT.md",
    ]
    return {name: _exists(WORKSPACE / name) for name in docs}


def _ad_hoc_agents() -> dict[str, Any]:
    root = WORKSPACE / "ad_hoc_agents"
    items: list[dict[str, str]] = []
    if root.exists():
        for manifest in sorted(root.glob("*/manifest.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            items.append(
                {
                    "name": str(data.get("name") or manifest.parent.name),
                    "purpose": str(data.get("purpose") or ""),
                    "script": str(data.get("script") or ""),
                    "status": str(data.get("status") or ""),
                }
            )
    return {"path": str(root), "count": len(items), "items": items[:20]}


def _obsidian_status() -> dict[str, Any]:
    cfg = _read_json(WORKSPACE / "obsidian_bridge_config.json")
    vault = Path(str(cfg.get("vault_path") or r"C:\Users\user\Mon Drive\DriveSyncFiles\ARCHITECTE_SYSTEM"))
    return {
        "vault_path": str(vault),
        "vault_exists": _exists(vault),
        "cockpit": str(vault / "00_Commandement" / "Cockpit_de_Vie.md"),
        "time_dashboard": str(vault / "00_Commandement" / "Temps" / "Dashboard_Temps.md"),
        "memory": str(vault / "99_Système" / "Nanobot" / "Memoire" / "Memoire_Nanobot.md"),
    }


def build_payload() -> dict[str, Any]:
    config = _read_json(ROOT / "config_omega.json")
    mcp_servers = sorted(((config.get("tools") or {}).get("mcpServers") or {}).keys())
    google = _run_json([sys.executable, str(ROOT / "scripts" / "google_workspace_cli.py"), "--json", "auth", "status"])
    modules = _module_status()
    obsidian = _obsidian_status()
    docs = _doc_status()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": str(ROOT),
        "workspace": str(WORKSPACE),
        "mcp_servers": mcp_servers,
        "google": {
            "ok": bool(google.get("ok")),
            "valid": bool(google.get("valid")),
            "has_refresh_token": bool(google.get("has_refresh_token")),
            "has_required_scopes": bool(google.get("has_required_scopes")),
            "stored_scopes": sorted(str(s) for s in (google.get("stored_scopes") or [])),
            "mcp_tool_count": _mcp_tool_count(),
        },
        "modules": modules,
        "ad_hoc_agents": _ad_hoc_agents(),
        "obsidian": obsidian,
        "docs": docs,
        "policies": {
            "excel": "Always create formatted .xlsx with real columns, Synthese, Controle qualite for tabular exports.",
            "telegram": "Never expose hidden reasoning, JSON tool chatter, MCP names, or long plans in Telegram.",
            "verification": "Act, verify real result, repair once with another route before reporting a blocker.",
            "fallback": "When MCP fails, try local CLI/scripts, desktop/browser automation, or filesystem route.",
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    google = payload["google"]
    modules = payload["modules"]
    ad_hoc = payload.get("ad_hoc_agents") or {}
    obsidian = payload["obsidian"]
    scopes = set(google.get("stored_scopes") or [])
    gmail_modify = "https://www.googleapis.com/auth/gmail.modify" in scopes

    def enabled(name: str) -> str:
        return "OK" if modules.get(name) else "MISSING"

    lines = [
        "# Nanobot Startup Context",
        "",
        "This file is injected into Nanobot's system prompt on every conversation.",
        "It is regenerated at startup so Nanobot remembers its real operational powers.",
        "",
        f"Generated UTC: {payload.get('generated_at')}",
        "",
        "## Prime Directive",
        "- Assume these capabilities exist before saying no.",
        "- If a route fails, diagnose and try the matching fallback route.",
        "- Use concise French results for Amor; do not expose tool internals in Telegram.",
        "- For any table/scrape/export, create a formatted `.xlsx` with real columns, `Synthese`, and `Controle qualite`.",
        "- Before claiming success, verify the real artifact, service state, API state, window, or file.",
        "",
        "## Core Paths",
        f"- Omega root: `{payload.get('root')}`",
        f"- Workspace: `{payload.get('workspace')}`",
        f"- Persistent memory: `{WORKSPACE / 'NANOBOT_RECENT_UPGRADES.md'}`",
        f"- Google guide: `{WORKSPACE / 'GOOGLE_WORKSPACE_CAPABILITIES.md'}`",
        f"- Radical guide: `{WORKSPACE / 'RADICAL_CAPABILITIES.md'}`",
        "",
        "## Obsidian — REGLE ABSOLUE",
        f"- Active vault: `{obsidian.get('vault_path')}` ({'OK' if obsidian.get('vault_exists') else 'MISSING'})",
        f"- Cockpit: `{obsidian.get('cockpit')}`",
        f"- Time dashboard: `{obsidian.get('time_dashboard')}`",
        f"- Memory note: `{obsidian.get('memory')}`",
        "",
        "**INTERDIT** : NE JAMAIS utiliser `list_dir`, `glob`, `grep`, `read_file`, `write_file`, ou les outils MCP `filesystem` pour le vault. Le vault est sur un lien symbolique vers G:\\ et le filesystem MCP est restreint au workspace -> ces routes echoueront avec 'access denied'. Si tu vois ce type d'erreur, NE PAS abandonner : basculer immediatement sur le bridge ci-dessous.",
        "",
        "**OBLIGATOIRE** : pour TOUTE operation Obsidian, utiliser `exec` avec le bridge :",
        "",
        "```",
        "Lister tout / un dossier :",
        "  exec(\"python C:/AI/nanobot-omega/scripts/obsidian_second_brain.py list\")",
        "  exec(\"python C:/AI/nanobot-omega/scripts/obsidian_second_brain.py list --folder 00_Commandement\")",
        "Lire une note :",
        "  exec(\"python C:/AI/nanobot-omega/scripts/obsidian_second_brain.py read-note --path '00_Commandement/Accueil.md'\")",
        "Chercher :",
        "  exec(\"python C:/AI/nanobot-omega/scripts/obsidian_second_brain.py search 'mot cle'\")",
        "Capturer une nouvelle note (auto-classifiee) :",
        "  exec(\"python C:/AI/nanobot-omega/scripts/obsidian_second_brain.py capture --content 'texte' --title 'titre'\")",
        "Audit complet du vault :",
        "  exec(\"python C:/AI/nanobot-omega/scripts/obsidian_second_brain.py audit-vault\")",
        "Notes orphelines / doublons / faibles / liens casses :",
        "  exec(\"python .../obsidian_second_brain.py detect-orphans\")",
        "  exec(\"python .../obsidian_second_brain.py detect-duplicates\")",
        "  exec(\"python .../obsidian_second_brain.py detect-weak-notes\")",
        "  exec(\"python .../obsidian_second_brain.py detect-broken-links\")",
        "Modifier une note (mode dry-run dispo sur destructives) :",
        "  exec(\"python .../obsidian_second_brain.py write-note --path X --content Y\")",
        "  exec(\"python .../obsidian_second_brain.py rename-path --src X --dst Y --update-links --dry-run\")",
        "  exec(\"python .../obsidian_second_brain.py delete-path --path X --dry-run\")",
        "```",
        "",
        "Le bridge a 30 sous-commandes au total. Sortie JSON. Sécurité : anti-traversal, .obsidian protégé, chemins > 260 chars (Windows MAX_PATH) skipés via archive_exclusions.",
        "",
        "Reference complete : `workspace/NANOBOT_OBSIDIAN_INTEGRATION.md`. Recovery si decrochage : `workspace/NANOBOT_RECOVERY_PROTOCOL.md`.",
        "",
        "## Google Workspace",
        f"- OAuth valid: {google.get('valid')}",
        f"- Refresh token: {google.get('has_refresh_token')}",
        f"- Required scopes present: {google.get('has_required_scopes')}",
        f"- Gmail modify active: {gmail_modify}",
        f"- Local MCP tool count: {google.get('mcp_tool_count')}",
        "- Preferred CLI fallback: `python C:/AI/nanobot-omega/scripts/google_workspace_cli.py --json ...`",
        "- Gmail can search/read/send plus label, create/delete user labels, mark read/unread, archive, move, trash, untrash, and explicitly permanent-delete.",
        "- Docs, Sheets, Drive, Calendar, Tasks, and Contacts are available through local CLI/MCP routes.",
        "",
        "## Operational Modules",
        f"- Google Workspace CLI: {enabled('google_workspace_cli.py')}",
        f"- Google Workspace MCP: {enabled('google_workspace_mcp.py')}",
        f"- Obsidian bridge: {enabled('obsidian_second_brain.py')}",
        f"- Scraping champion: {enabled('scraping_champion.py')}",
        f"- App acquisition: {enabled('app_acquisition.py')}",
        f"- Proactive intelligence: {enabled('proactive_intel.py')}",
        f"- Desktop intelligence/OCR/XLSX: {enabled('desktop_intel.py')}",
        f"- Resilience orchestrator: {enabled('resilience_orchestrator.py')}",
        f"- Agent forge: {enabled('agent_forge.py')}",
        f"- Ad hoc agents folder: `{ad_hoc.get('path')}`",
        f"- Ad hoc agents known: {ad_hoc.get('count', 0)}",
        "",
        "## Route Map",
        "- Scraping/web extraction: `scraping_champion.py`; render with Playwright when HTTP is weak.",
        "- Windows install/open/download: `app_acquisition.py`; verify installed app, shortcut, AppID, process, or installer.",
        "- Desktop/app windows/OCR/XLSX: `desktop_intel.py` and desktop automation.",
        "- Proactive veille: `proactive_intel.py` with `workspace/proactive_sources.json`.",
        "- Fallback chains and impasse detection: `resilience_orchestrator.py`.",
        "- Temporary specialized scripts/agents: `agent_forge.py`.",
        "- 2ememain free-object watch: Windows task `NanobotVeille2ememain`; control script `workspace/veille_2ememain_control.py`.",
        "",
    ]
    agents = ad_hoc.get("items") or []
    if agents:
        lines.extend(["## Known Ad Hoc Agents"])
        for agent in agents:
            purpose = (agent.get("purpose") or "").strip()
            if len(purpose) > 100:
                purpose = purpose[:97] + "..."
            lines.append(f"- `{agent.get('name')}`: {purpose} (`{agent.get('script')}`)")
        lines.append("")
    lines.extend(
        [
        "## Must-Read Memory Files",
        "- Read `NANOBOT_RECENT_UPGRADES.md` before modifying Nanobot behavior or when a request touches Excel, Telegram, Obsidian, Google, scraping, scheduling, MCP, or repeated failures.",
        "- Read `GOOGLE_WORKSPACE_CAPABILITIES.md` before declaring Google/Workspace limitations.",
        "- Read `RADICAL_CAPABILITIES.md` before handling Gmail modify, proactive intelligence, desktop extraction, resilience, or ad hoc agents.",
        "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(render_markdown(payload), encoding="utf-8")
    if not args.quiet:
        print(json.dumps({"ok": True, "md": str(OUT_MD), "json": str(OUT_JSON)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
