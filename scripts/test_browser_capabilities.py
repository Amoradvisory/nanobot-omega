"""Tests E2E anti-régression pour les capacités navigateur, scraping et veille.

100% read-only / smoke test. N'envoie aucune notification réelle.

Usage : python scripts/test_browser_capabilities.py [--verbose]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OMEGA = Path(r"C:\AI\nanobot-omega")
SCRIPTS = OMEGA / "scripts"
WORKSPACE = OMEGA / "workspace"


def run(cmd: list[str], timeout: int = 30, cwd: Path | None = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, check=False,
            cwd=str(cwd) if cwd else None,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except Exception as exc:
        return 1, "", str(exc)


def parse_json(out: str) -> dict | None:
    try:
        return json.loads(out)
    except Exception:
        return None


# ---------------------------------------------------------------------------


def t_chrome_installed():
    p = Path(r"C:/Program Files/Google/Chrome/Application/chrome.exe")
    return ("chrome_installed", p.exists(), f"chrome.exe = {p}" if p.exists() else "missing")


def t_chrome_launcher_present():
    p = OMEGA / "Open-Shared-Nanobot-Browser.bat"
    return ("chrome_launcher_present", p.exists(), str(p))


def t_shared_chrome_profile():
    p = OMEGA / "shared-browser" / "chrome-profile"
    return ("shared_chrome_profile", p.exists(), str(p))


def t_playwright_chromium():
    pw = Path(r"C:/Users/user/AppData/Local/ms-playwright")
    if not pw.exists():
        return ("playwright_chromium", False, f"missing {pw}")
    chromium = [d for d in pw.iterdir() if d.is_dir() and d.name.startswith("chromium-")]
    return ("playwright_chromium", bool(chromium), f"dirs = {[d.name for d in chromium]}")


def t_playwright_module():
    rc, out, err = run([sys.executable, "-c", "import playwright; print('ok')"], timeout=10)
    return ("playwright_module", rc == 0 and "ok" in out, f"rc={rc}")


def t_scraping_champion_help():
    rc, out, err = run([sys.executable, str(SCRIPTS / "scraping_champion.py"), "--help"], timeout=15)
    return ("scraping_champion_help", rc == 0, f"rc={rc}, len(out)={len(out)}")


def t_veille2_status():
    rc, out, err = run([sys.executable, str(WORKSPACE / "veille_2ememain_control.py"), "status"], timeout=15)
    return ("veille2_status", rc == 0 and "Veille 2ememain" in out, f"rc={rc}")


def t_veille2_health():
    rc, out, err = run([sys.executable, str(WORKSPACE / "veille_2ememain_control.py"), "health"], timeout=15)
    return ("veille2_health", rc == 0 and "sante" in out, f"rc={rc}")


def t_veille2_opportunities():
    rc, out, err = run([sys.executable, str(WORKSPACE / "veille_2ememain_control.py"), "opportunities"], timeout=15)
    return ("veille2_opportunities", rc == 0 and ("opportunities" in out or "annonces" in out),
            f"rc={rc}, len(out)={len(out)}")


def t_veille2_explain():
    rc, out, err = run([sys.executable, str(WORKSPACE / "veille_2ememain_control.py"), "explain-last-run"], timeout=15)
    return ("veille2_explain_last_run", rc == 0, f"rc={rc}")


def t_tasks_control_list():
    rc, out, err = run([sys.executable, str(SCRIPTS / "tasks_control.py"), "list"], timeout=20)
    return ("tasks_control_list", rc == 0 and "Nanobot" in out, f"rc={rc}")


def t_tasks_control_health():
    rc, out, err = run([sys.executable, str(SCRIPTS / "tasks_control.py"), "health"], timeout=20)
    return ("tasks_control_health", rc == 0 and "Sante" in out, f"rc={rc}")


def t_tasks_control_detect_dup():
    rc, out, err = run([sys.executable, str(SCRIPTS / "tasks_control.py"), "detect-duplicates"], timeout=15)
    return ("tasks_control_detect_duplicates", rc == 0, f"rc={rc}")


def t_capabilities_registry_browser():
    rc, out, err = run([sys.executable, str(SCRIPTS / "capabilities_registry.py"), "--show"], timeout=20)
    if rc != 0:
        return ("capabilities_registry_browser", False, f"rc={rc}")
    payload = parse_json(out)
    if not payload:
        return ("capabilities_registry_browser", False, "no JSON")
    browser_count = payload.get("by_category", {}).get("browser", 0)
    return ("capabilities_registry_browser", browser_count >= 8,
            f"browser capabilities = {browser_count}")


def t_self_check_browser_section():
    rc, out, err = run([sys.executable, str(SCRIPTS / "nanobot_self_check.py"), "check"], timeout=120)
    has_chrome = "chrome_installed" in out
    has_pw = "playwright_runtime" in out
    has_scraping = "scraping_champion" in out
    has_task = "veille_2ememain_task" in out
    has_health = "veille_2ememain_health" in out
    ok = all([has_chrome, has_pw, has_scraping, has_task, has_health])
    return ("self_check_browser_section", ok,
            f"chrome={has_chrome} pw={has_pw} scrap={has_scraping} task={has_task} health={has_health}")


def t_watch_framework_selftest():
    rc, out, err = run([sys.executable, str(WORKSPACE / "watch_framework.py")], timeout=15)
    return ("watch_framework_selftest", rc == 0 and "OK" in out, f"rc={rc}")


def t_run_veille_enriched_fields():
    """Verify run_veille_2ememain.py contains the enriched extraction fields."""
    p = WORKSPACE / "run_veille_2ememain.py"
    if not p.exists():
        return ("run_veille_enriched_fields", False, "file missing")
    content = p.read_text(encoding="utf-8", errors="replace")
    fields = ["images", "image_main", "location", "distance_km", "description"]
    missing = [f for f in fields if f not in content]
    return ("run_veille_enriched_fields", not missing,
            f"fields present: {[f for f in fields if f not in missing]}, missing: {missing}")


def t_run_veille_and_notify_enriched():
    """Verify run_veille_and_notify.py has the enriched notification helpers."""
    p = WORKSPACE / "run_veille_and_notify.py"
    if not p.exists():
        return ("run_veille_and_notify_enriched", False, "file missing")
    content = p.read_text(encoding="utf-8", errors="replace")
    keys = ["send_telegram_photo", "send_telegram_album", "build_caption",
            "haversine_km", "POSTCODE_COORDS", "PREMIUM_RULES_RICH",
            "NL_TEMPLATES", "update_health", "maybe_send_health_alert"]
    missing = [k for k in keys if k not in content]
    return ("run_veille_and_notify_enriched", not missing,
            f"missing: {missing}" if missing else f"all {len(keys)} hooks present")


def t_telegram_notification_dry_run():
    """Run run_veille_and_notify.py --dry-run quickly to verify wiring."""
    # We don't actually want to run the heavy scraper here. Instead, import the module and call build_caption.
    rc, out, err = run([sys.executable, "-X", "utf8", "-c", (
        "import sys; sys.path.insert(0, r'C:/AI/nanobot-omega/workspace'); "
        "from run_veille_and_notify import build_caption, evaluate_opportunity, load_translation_cache; "
        "ad = {'title': 'iPhone test', 'category': 'Informatique', 'link': 'https://x', "
        "'images': [], 'image_main': '', 'location': 'Mouscron 7700', 'distance_km': None, "
        "'distance_display': '', 'description': 'test'}; "
        "cap = build_caption(ad, load_translation_cache()); "
        "print(f'caption_len={len(cap)}')"
    )], timeout=15)
    return ("telegram_notification_dry_run", rc == 0 and "caption_len=" in out, f"rc={rc}")


TESTS = [
    t_chrome_installed,
    t_chrome_launcher_present,
    t_shared_chrome_profile,
    t_playwright_chromium,
    t_playwright_module,
    t_scraping_champion_help,
    t_veille2_status,
    t_veille2_health,
    t_veille2_opportunities,
    t_veille2_explain,
    t_tasks_control_list,
    t_tasks_control_health,
    t_tasks_control_detect_dup,
    t_capabilities_registry_browser,
    t_self_check_browser_section,
    t_watch_framework_selftest,
    t_run_veille_enriched_fields,
    t_run_veille_and_notify_enriched,
    t_telegram_notification_dry_run,
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    print(f"=== Tests browser/veille — {len(TESTS)} cas ===\n")
    passed = failed = 0
    for func in TESTS:
        try:
            name, ok, detail = func()
        except Exception as exc:
            name, ok, detail = func.__name__, False, f"raised {type(exc).__name__}: {exc}"
        flag = "OK  " if ok else "FAIL"
        print(f"  [{flag}] {name}: {detail}")
        if ok:
            passed += 1
        else:
            failed += 1
    print(f"\nResultat : {passed}/{len(TESTS)} OK, {failed} echec(s)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
