"""Inventaire et quarantaine du workspace Nanobot.

Categorise les fichiers de workspace/ en :
- KEEP   : critiques (configs, docs canoniques, mémoire, ad_hoc_agents, sessions)
- DEBUG  : screenshots/HTML de debug 2ememain/notion/youtube
- DUPES  : doublons d'extraction ou versions intermediaires
- TEMP   : fichiers test_*, mon_test, user_instruction, tool_issue_report
- DEPREC : *.deprecated.*, *.bak

Modes :
  --scan         : liste + categorise sans toucher
  --quarantine   : deplace KEEP=non vers _cleanup_quarantine_YYYYMMDD/
  --restore TS   : restaure une quarantaine (TS = timestamp dossier)

Toutes les actions sont journalisees dans logs/workspace_cleanup.log.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OMEGA = Path(r"C:\AI\nanobot-omega")
WORKSPACE = OMEGA / "workspace"
LOG_PATH = OMEGA / "logs" / "workspace_cleanup.log"

# Fichiers et dossiers a TOUJOURS preserver (chemins relatifs a workspace/)
KEEP_PATTERNS = {
    # Identite / capacites / memoire
    "AGENTS.md", "ARSENAL.md", "BROWSER_REFERENCE.md", "CORE_DIRECTIVE.md",
    "GOOGLE_WORKSPACE_CAPABILITIES.md", "HEARTBEAT.md", "NANOBOT_ARSENAL.md",
    "NANOBOT_RECENT_UPGRADES.md", "NANOBOT_STARTUP_CONTEXT.json",
    "NANOBOT_STARTUP_CONTEXT.md", "OMEGA_PROFILE.md", "RADICAL_CAPABILITIES.md",
    "SOUL.md", "TOOLS.md", "USER.md",
    "NANOBOT_CAPABILITIES.json", "NANOBOT_CAPABILITIES.md",
    "NANOBOT_OBSIDIAN_INTEGRATION.md", "NANOBOT_RECOVERY_PROTOCOL.md",
    # Configs operationnelles
    "obsidian_bridge_config.json", "veille_2ememain_config.json",
    "veille_2ememain_history.json", "veille_2ememain_seen.json",
    "veille_2ememain_state.json", "veille_2ememain_translation_cache.json",
    "proactive_sources.json", "annonces_vues.json",
    # Scripts veille operationnels (utilises par tasks Windows)
    "run_veille_2ememain.py", "run_veille_and_notify.py",
    "veille_2ememain_control.py", "veille_2ememain_worker.py",
    # Scripts auxiliaires utilises (verifies dans config_omega.json ou docs)
    "test_filter.py",
    # HTML html-life-os (utilises pour fond ecran personnalise + dashboards)
    # Ces .html ne sont pas du debug : ils ont une autre vocation
    "Electro.html", "Informatique.html", "Jardin.html", "Maison.html",
    "Maison_v2.html", "Sports.html", "TV.html", "Vetements.html",
    "Kasparov_3D_Masterclass.html", "Kasparov_3D_Viewer.html",
    "Set-Wallpaper.ps1",
    # Identite / commandes
    "MonCommandement",  # symlink/junction
    "FIRE",  # link to FIRE workspace
    "temp_identity_card.md",  # used by identity workflow
    "prompt_for_codex.md",  # active codex prompt
    # Build artefacts utiles
    "desktop_windows_snapshot.xlsx",  # snapshot recent
}
KEEP_DIRS = {
    "ad_hoc_agents", "memory", "sessions", "skills", "cron",
    "channel-semantics", "desktop-defaults", "heartbeat-reporter",
    "omega-tool-operator", "shared-browser", "system-power",
    "telegram-mobile", "web-and-ocr",
    "kasparov-viewer", "nanochrome-typer", "omega-productivity-app",
    "veille_lille",  # veille active
    "INTEL", "Cours - Copie",
    "resilience_reports",
    "proactive_reports",
    "test_vault",  # for E2E tests
    ".gemini",  # Gemini CLI settings + skills
    ".git",     # local workspace git
    ".nanobot", # tool-results state
}
KEEP_PATTERNS_HIDDEN = {".gitignore"}

DEBUG_FILE_PATTERNS = [
    re.compile(r"^debug_.*\.(png|html|jpg)$", re.IGNORECASE),
    re.compile(r"^debug_fail_.*\.html$", re.IGNORECASE),
    re.compile(r"^youtube_.*\.png$", re.IGNORECASE),
    re.compile(r"^notion_.*\.(png|csv)$", re.IGNORECASE),
    re.compile(r"^check_informatique.*$", re.IGNORECASE),
    re.compile(r"^photo_camera_.*\.png$", re.IGNORECASE),
    re.compile(r"^screen_capture\.png$", re.IGNORECASE),
    re.compile(r"^screenshot_youtube\.png$", re.IGNORECASE),
    re.compile(r"^verification_2ememain\.png$", re.IGNORECASE),
    re.compile(r"^page_test\.html$", re.IGNORECASE),
    re.compile(r"^page_source_start\.html$", re.IGNORECASE),
    re.compile(r"^debug_listing\.html$", re.IGNORECASE),
    re.compile(r"^large_script_\d+\.json$", re.IGNORECASE),
    re.compile(r"^dump_.*\.py$", re.IGNORECASE),
    re.compile(r"^find_chrome\.py$", re.IGNORECASE),
    re.compile(r"^check_chrome_path\.py$", re.IGNORECASE),
    re.compile(r"^extract_titles\.py$", re.IGNORECASE),
    re.compile(r"^check_all_titles\.py$", re.IGNORECASE),
    re.compile(r"^check_links\.py$", re.IGNORECASE),
    re.compile(r"^debug_links\.py$", re.IGNORECASE),
    re.compile(r"^check_free\.py$", re.IGNORECASE),
    re.compile(r"^extract_md_files\.py$", re.IGNORECASE),
    re.compile(r"^extract_json\.py$", re.IGNORECASE),
    re.compile(r"^test_clip\.txt$", re.IGNORECASE),
    re.compile(r"^test_no_profile\.py$", re.IGNORECASE),
    re.compile(r"^test_price\.py$", re.IGNORECASE),
    re.compile(r"^test_scrape\.py$", re.IGNORECASE),
    re.compile(r"^test_2ememain_all\.py$", re.IGNORECASE),
    re.compile(r"^limetorrent_.*\.(csv|html)$", re.IGNORECASE),
    re.compile(r"^scrape_limetorrent\.py$", re.IGNORECASE),
    re.compile(r"^scrape_2ememain\.py$", re.IGNORECASE),
    re.compile(r"^parse_2ememain\.py$", re.IGNORECASE),
    re.compile(r"^veille_standalone\.py$", re.IGNORECASE),
    re.compile(r"^veille_2ememain_final\.py$", re.IGNORECASE),
    re.compile(r"^veille_2ememain\.py$", re.IGNORECASE),
    re.compile(r"^scrape_notion\.py$", re.IGNORECASE),
    re.compile(r"^debug_2ememain\.py$", re.IGNORECASE),
    re.compile(r"^diagnostic_2ememain.*\.py$", re.IGNORECASE),
    re.compile(r"^process_(new_ads|opportunities)\.py$", re.IGNORECASE),
    re.compile(r"^add_new_oppor.*\.py$", re.IGNORECASE),
    re.compile(r"^archive_and_update\.py$", re.IGNORECASE),
    re.compile(r"^update_opportunities\.py$", re.IGNORECASE),
    re.compile(r"^final_csv\.py$", re.IGNORECASE),
    re.compile(r"^save_html\.py$", re.IGNORECASE),
    re.compile(r"^dump_html\.py$", re.IGNORECASE),
    re.compile(r"^dump_listing\.py$", re.IGNORECASE),
    re.compile(r"^dump_prices\.py$", re.IGNORECASE),
    re.compile(r"^test_filter\.py$", re.IGNORECASE),  # already in KEEP
    re.compile(r"^debug_2ememain\.html$", re.IGNORECASE),
    re.compile(r"^debug_2ememain\.png$", re.IGNORECASE),
    re.compile(r"^calc_test\.ps1$", re.IGNORECASE),
    re.compile(r"^extract_notion(_v\d+|_cdp)?\.(py|ps1)$", re.IGNORECASE),
    re.compile(r"^clean_notion_extraction(_v\d+)?\.py$", re.IGNORECASE),
    re.compile(r"^prepare_browser\.ps1$", re.IGNORECASE),
    re.compile(r"^maximize_chrome\.ps1$", re.IGNORECASE),
    re.compile(r"^take_screenshot\.ps1$", re.IGNORECASE),
    re.compile(r"^verify_ps\.ps1$", re.IGNORECASE),
    re.compile(r"^cleanup_temp_files\.ps1$", re.IGNORECASE),
    re.compile(r"^fix_windows_v2\.ps1$", re.IGNORECASE),
    re.compile(r"^focus_youtube\.ps1$", re.IGNORECASE),
    re.compile(r"^force_youtube_view\.ps1$", re.IGNORECASE),
    re.compile(r"^full_cleanup_youtube\.ps1$", re.IGNORECASE),
    re.compile(r"^clean_and_show_youtube\.ps1$", re.IGNORECASE),
    re.compile(r"^final_view\.ps1$", re.IGNORECASE),
    re.compile(r"^final_youtube_fix\.ps1$", re.IGNORECASE),
    re.compile(r"^list_chrome_tabs\.py$", re.IGNORECASE),
    re.compile(r"^open_browser\.py$", re.IGNORECASE),
    re.compile(r"^extract_notion\.csv$", re.IGNORECASE),
    re.compile(r"^playwright_auth_script\.py$", re.IGNORECASE),
    re.compile(r"^capture_(debug|network)\.py$", re.IGNORECASE),
    re.compile(r"^network_responses\.json$", re.IGNORECASE),
    re.compile(r"^windows_list\.txt$", re.IGNORECASE),
    re.compile(r"^mon_test\.txt$", re.IGNORECASE),
    re.compile(r"^user_instruction\.txt$", re.IGNORECASE),
    re.compile(r"^access_issue\.txt$", re.IGNORECASE),
    re.compile(r"^tool_issue_report\.txt$", re.IGNORECASE),
    re.compile(r"^firebase_(ci|link|login(_2)?)\.txt$", re.IGNORECASE),
    re.compile(r"^get_(ci|link)\.bat$", re.IGNORECASE),
    re.compile(r"^cf_tunnel\.log$", re.IGNORECASE),
    re.compile(r"^tunnel\.txt$", re.IGNORECASE),
    re.compile(r"^dev\.log$", re.IGNORECASE),
    re.compile(r"^google_auth\.py$", re.IGNORECASE),  # there's another in scripts/
    re.compile(r"^google_auth_creation_blocked\.txt$", re.IGNORECASE),
    re.compile(r"^notion\.csv$", re.IGNORECASE),
    re.compile(r"^notion_extractor\.ps1$", re.IGNORECASE),
    re.compile(r"^notion_final_check\.png$", re.IGNORECASE),
    re.compile(r"^notion_scan\.png$", re.IGNORECASE),
    re.compile(r"^notion_sidebar_full\.png$", re.IGNORECASE),
    re.compile(r"^heartbeat-reporter\.skill$", re.IGNORECASE),
    re.compile(r"^nanochrome-typer\.skill$", re.IGNORECASE),
    re.compile(r"^nanochrome_(type|utils)\.py$", re.IGNORECASE),
]

DEPREC_PATTERNS = [
    re.compile(r"\.deprecated\.\d+$", re.IGNORECASE),
    re.compile(r"\.bak(\.\d+)?$", re.IGNORECASE),
]


def _is_keep(path: Path) -> bool:
    if path.name in KEEP_PATTERNS:
        return True
    if path.name in KEEP_PATTERNS_HIDDEN:
        return True
    rel = path.relative_to(WORKSPACE)
    parts = rel.parts
    if parts and parts[0] in KEEP_DIRS:
        return True
    return False


def _category(path: Path) -> str:
    rel_parts = path.relative_to(WORKSPACE).parts
    if rel_parts and rel_parts[0] == "temp_files_to_delete":
        return "TEMP"
    if path.is_dir():
        return "KEEP" if _is_keep(path) else "OTHER"
    if path.suffix.lower() == ".pyc":
        return "DEBUG"
    name = path.name
    for rx in DEPREC_PATTERNS:
        if rx.search(name):
            return "DEPREC"
    if _is_keep(path):
        return "KEEP"
    for rx in DEBUG_FILE_PATTERNS:
        if rx.match(name):
            return "DEBUG"
    return "OTHER"


def scan() -> dict[str, Any]:
    cats: dict[str, list[dict[str, Any]]] = {"KEEP": [], "DEBUG": [], "DEPREC": [], "TEMP": [], "OTHER": []}
    total_size_by_cat: dict[str, int] = {"KEEP": 0, "DEBUG": 0, "DEPREC": 0, "TEMP": 0, "OTHER": 0}
    if not WORKSPACE.exists():
        return {"ok": False, "error": "workspace missing"}
    for path in WORKSPACE.iterdir():
        try:
            if path.name == "_cleanup_quarantine":
                continue
            if path.name.startswith("_cleanup_quarantine_"):
                continue
            if path.is_dir():
                category = _category(path)
                size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
                cats[category].append({"name": path.name, "kind": "dir", "size": size})
                total_size_by_cat[category] += size
            else:
                category = _category(path)
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                cats[category].append({"name": path.name, "kind": "file", "size": size})
                total_size_by_cat[category] += size
        except OSError:
            continue
    summary = {cat: {"count": len(items), "size_bytes": total_size_by_cat[cat]} for cat, items in cats.items()}
    return {
        "ok": True,
        "workspace": str(WORKSPACE),
        "summary": summary,
        "items": cats,
    }


def quarantine() -> dict[str, Any]:
    report = scan()
    if not report.get("ok"):
        return report
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    quar_root = WORKSPACE / f"_cleanup_quarantine_{stamp[:8]}"
    quar_root.mkdir(parents=True, exist_ok=True)
    moved: list[dict[str, Any]] = []
    for cat in ("DEBUG", "DEPREC", "TEMP", "OTHER"):
        sub_dir = quar_root / cat
        sub_dir.mkdir(parents=True, exist_ok=True)
        for item in report["items"][cat]:
            src = WORKSPACE / item["name"]
            dst = sub_dir / item["name"]
            try:
                shutil.move(str(src), str(dst))
                moved.append({"category": cat, "name": item["name"], "size": item["size"], "to": str(dst)})
            except OSError as exc:
                moved.append({"category": cat, "name": item["name"], "error": str(exc)})
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "action": "quarantine", "stamp": stamp, "moved": moved}, ensure_ascii=False) + "\n")
    return {"ok": True, "quarantine_root": str(quar_root), "moved_count": sum(1 for m in moved if "to" in m), "errors": [m for m in moved if "error" in m]}


def restore(stamp: str) -> dict[str, Any]:
    quar_root = WORKSPACE / f"_cleanup_quarantine_{stamp}"
    if not quar_root.exists():
        return {"ok": False, "error": f"quarantine not found: {quar_root}"}
    restored: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for sub in quar_root.iterdir():
        if not sub.is_dir():
            continue
        for item in sub.iterdir():
            dst = WORKSPACE / item.name
            try:
                shutil.move(str(item), str(dst))
                restored.append({"name": item.name})
            except OSError as exc:
                errors.append({"name": item.name, "error": str(exc)})
    try:
        shutil.rmtree(quar_root)
    except OSError:
        pass
    return {"ok": True, "restored_count": len(restored), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventaire et quarantaine du workspace.")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("scan")
    sub.add_parser("quarantine")
    restore_p = sub.add_parser("restore")
    restore_p.add_argument("stamp")

    args = parser.parse_args()
    cmd = args.cmd or "scan"

    if cmd == "scan":
        report = scan()
        # Print short summary then detailed counts
        if not report.get("ok"):
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1
        print("=== Inventaire workspace ===")
        for cat, info in report["summary"].items():
            mb = info["size_bytes"] / (1024 * 1024)
            print(f"  {cat:7s} : {info['count']:4d} items, {mb:8.1f} MB")
        print()
        print("=== Detail (premiers items par categorie) ===")
        for cat in ("DEBUG", "DEPREC", "TEMP", "OTHER"):
            items = report["items"][cat][:15]
            if items:
                print(f"\n[{cat}]")
                for it in items:
                    kb = it["size"] / 1024
                    print(f"  {it['kind']:4s} {kb:7.1f} KB  {it['name']}")
        return 0

    if cmd == "quarantine":
        print(json.dumps(quarantine(), ensure_ascii=False, indent=2))
        return 0

    if cmd == "restore":
        print(json.dumps(restore(args.stamp), ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
