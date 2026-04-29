#!/usr/bin/env python
"""
chrome_hardener.py — Verification et durcissement du profil Chrome partage

Verifie l'integrite du profil Chrome utilise par Playwright MCP :
- Desactive les extensions qui injectent du DOM (perturbent l'automatisation)
- Desactive les mises a jour automatiques Chrome
- Verifie la taille du cache et le purge si necessaire
- Verifie que le profil est coherent

Usage:
    python modules/chrome_hardener.py              # Rapport complet
    python modules/chrome_hardener.py --fix        # Appliquer les corrections
    python modules/chrome_hardener.py --purge-cache  # Purger le cache
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROME_PROFILE = Path("C:/AI/nanobot-omega/shared-browser/chrome-profile")
DEFAULT_PROFILE = CHROME_PROFILE / "Default"
EXTENSIONS_DIR = DEFAULT_PROFILE / "Extensions"
PREFERENCES_FILE = DEFAULT_PROFILE / "Preferences"
LOCAL_STATE_FILE = CHROME_PROFILE / "Local State"

# Extensions connues qui perturbent l'automatisation Playwright
# Elles injectent du DOM, des overlays, des popups
PROBLEMATIC_EXTENSIONS = {
    "amhmeenmapldpjdedekalnfifgnpfnkc": "Superpower ChatGPT (injecte UI sur chatgpt.com)",
    "hghepaogndoaijlgelomneagnjlhaled": "Text To Speech / Readio Pro (injecte popups audio)",
    "nmmicjeknamkfloonkhhcjmomieiodli": "YouTube Summary ChatGPT+Claude (injecte overlay YouTube)",
}

# Extensions inoffensives (pas de DOM injection significative)
SAFE_EXTENSIONS = {
    "fcoeoabgfenejglbffodgkkbkcdhcgfn": "Claude (sidebar, pas d'injection DOM majeure)",
}


def get_extension_info() -> list[dict]:
    """Liste toutes les extensions installees avec leur statut."""
    extensions = []
    if not EXTENSIONS_DIR.exists():
        return extensions

    for ext_dir in EXTENSIONS_DIR.iterdir():
        if not ext_dir.is_dir():
            continue
        ext_id = ext_dir.name
        # Trouver le manifest dans la version la plus recente
        versions = sorted(ext_dir.iterdir(), reverse=True)
        name = "unknown"
        version = "unknown"
        for v_dir in versions:
            manifest = v_dir / "manifest.json"
            if manifest.exists():
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    name = data.get("name", "unknown")
                    version = data.get("version", "unknown")
                    # Resolve __MSG_ names
                    if name.startswith("__MSG_"):
                        messages_file = v_dir / "_locales" / "en" / "messages.json"
                        if messages_file.exists():
                            msgs = json.loads(messages_file.read_text(encoding="utf-8"))
                            key = name.replace("__MSG_", "").replace("__", "")
                            name = msgs.get(key, {}).get("message", name)
                except (json.JSONDecodeError, OSError):
                    pass
                break

        problematic = ext_id in PROBLEMATIC_EXTENSIONS
        safe = ext_id in SAFE_EXTENSIONS
        status = "PROBLEMATIC" if problematic else ("SAFE" if safe else "UNKNOWN")
        reason = PROBLEMATIC_EXTENSIONS.get(ext_id, SAFE_EXTENSIONS.get(ext_id, "Non classifiee"))

        extensions.append({
            "id": ext_id,
            "name": name,
            "version": version,
            "status": status,
            "reason": reason,
        })

    return extensions


def get_cache_size_mb() -> float:
    """Calcule la taille du cache Chrome en MB."""
    cache_dir = DEFAULT_PROFILE / "Cache" / "Cache_Data"
    if not cache_dir.exists():
        return 0.0
    try:
        total = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
        return total / (1024 * 1024)
    except OSError:
        return 0.0


def check_preferences_integrity() -> list[str]:
    """Verifie les preferences critiques pour l'automatisation."""
    issues = []

    if not PREFERENCES_FILE.exists():
        issues.append("Preferences file absent!")
        return issues

    try:
        prefs = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        issues.append(f"Preferences corrompu: {e}")
        return issues

    # Verifier que les notifications sont desactivees (perturbent Playwright)
    profile = prefs.get("profile", {})
    default_content = profile.get("default_content_setting_values", {})
    notifs = default_content.get("notifications", 1)
    if notifs != 2:  # 2 = block
        issues.append(f"Notifications non bloquees (valeur={notifs}, attendu=2)")

    # Verifier que les popups sont bloques
    popups = default_content.get("popups", 1)
    if popups != 2:
        issues.append(f"Popups non bloques (valeur={popups}, attendu=2)")

    # Verifier restore on startup
    session = prefs.get("session", {})
    restore = session.get("restore_on_startup", 0)
    # 1 = restore, 4 = URLs, 5 = last session — on veut 1 ou 5
    if restore not in (1, 5):
        issues.append(f"Restore on startup = {restore} (recommande: 1 ou 5)")

    return issues


def fix_preferences() -> list[str]:
    """Corrige les preferences Chrome pour l'automatisation."""
    fixes = []

    if not PREFERENCES_FILE.exists():
        return ["Preferences file absent, rien a corriger"]

    try:
        prefs = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return [f"Impossible de lire Preferences: {e}"]

    # Backup
    backup = PREFERENCES_FILE.with_suffix(f".{time.strftime('%Y%m%d_%H%M%S')}.bak")
    shutil.copy2(PREFERENCES_FILE, backup)
    fixes.append(f"Backup cree: {backup.name}")

    # Bloquer notifications
    prefs.setdefault("profile", {}).setdefault("default_content_setting_values", {})
    if prefs["profile"]["default_content_setting_values"].get("notifications") != 2:
        prefs["profile"]["default_content_setting_values"]["notifications"] = 2
        fixes.append("Notifications bloquees")

    # Bloquer popups
    if prefs["profile"]["default_content_setting_values"].get("popups") != 2:
        prefs["profile"]["default_content_setting_values"]["popups"] = 2
        fixes.append("Popups bloques")

    # Desactiver traduction automatique (perturbe les snapshots)
    prefs.setdefault("translate", {})
    if not prefs["translate"].get("enabled") is False:
        prefs["translate"]["enabled"] = False
        fixes.append("Traduction auto desactivee")

    # Desactiver les suggestions de mots de passe (popups)
    prefs.setdefault("credentials_enable_service", True)
    prefs["credentials_enable_service"] = False
    fixes.append("Suggestions mots de passe desactivees")

    # Desactiver autofill (popups)
    prefs.setdefault("autofill", {})
    prefs["autofill"]["profile_enabled"] = False
    prefs["autofill"]["credit_card_enabled"] = False
    fixes.append("Autofill desactive")

    PREFERENCES_FILE.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")
    fixes.append("Preferences sauvegardees")

    return fixes


def disable_extensions(ext_ids: list[str]) -> list[str]:
    """Desactive les extensions problematiques en renommant leur dossier."""
    results = []
    for ext_id in ext_ids:
        ext_dir = EXTENSIONS_DIR / ext_id
        disabled_dir = EXTENSIONS_DIR / f"{ext_id}.disabled"
        if ext_dir.exists() and ext_dir.is_dir():
            try:
                ext_dir.rename(disabled_dir)
                name = PROBLEMATIC_EXTENSIONS.get(ext_id, ext_id)
                results.append(f"Desactive: {name}")
            except OSError as e:
                results.append(f"Echec desactivation {ext_id}: {e}")
        elif disabled_dir.exists():
            results.append(f"Deja desactive: {ext_id}")
        else:
            results.append(f"Absent: {ext_id}")
    return results


def purge_cache() -> str:
    """Purge le cache Chrome."""
    cache_dir = DEFAULT_PROFILE / "Cache" / "Cache_Data"
    if not cache_dir.exists():
        return "Cache absent, rien a purger"

    size_before = get_cache_size_mb()
    try:
        shutil.rmtree(cache_dir, ignore_errors=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        return f"Cache purge: {size_before:.0f} MB liberes"
    except OSError as e:
        return f"Echec purge cache: {e}"


def report() -> None:
    """Affiche le rapport complet."""
    print(f"\n{'='*60}")
    print(f"  AUDIT PROFIL CHROME PARTAGE")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # Extensions
    exts = get_extension_info()
    print(f"\n  Extensions installees ({len(exts)}):")
    for ext in exts:
        icon = "[!!]" if ext["status"] == "PROBLEMATIC" else ("[OK]" if ext["status"] == "SAFE" else "[??]")
        print(f"    {icon} {ext['name']} (v{ext['version']})")
        print(f"         {ext['reason']}")

    # Cache
    cache_mb = get_cache_size_mb()
    status = "ATTENTION" if cache_mb > 200 else "OK"
    print(f"\n  Cache: {cache_mb:.1f} MB [{status}]")

    # Preferences
    issues = check_preferences_integrity()
    if issues:
        print(f"\n  Preferences ({len(issues)} probleme(s)):")
        for issue in issues:
            print(f"    [!] {issue}")
    else:
        print(f"\n  Preferences: OK")

    # Profile path
    print(f"\n  Profil: {CHROME_PROFILE}")
    print(f"  Existe: {'OUI' if CHROME_PROFILE.exists() else 'NON'}")
    print()


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--fix" in args:
        report()
        print(f"  === CORRECTIONS ===\n")

        # Fix preferences
        fixes = fix_preferences()
        for f in fixes:
            print(f"  [FIX] {f}")

        # Disable problematic extensions
        print()
        results = disable_extensions(list(PROBLEMATIC_EXTENSIONS.keys()))
        for r in results:
            print(f"  [EXT] {r}")
        print()

    elif "--purge-cache" in args:
        result = purge_cache()
        print(f"  {result}")

    else:
        report()
