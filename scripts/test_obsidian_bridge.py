"""Tests anti-régression E2E pour obsidian_second_brain.py.

100% read-only ou dry-run sur le vrai vault. N'ecrit JAMAIS dans le vault.
Verifie que toutes les sous-commandes critiques retournent le bon shape.

Exit code :
- 0 : tous les tests passent
- 1 : au moins un test echoue
- 2 : erreur de configuration

Usage : python scripts/test_obsidian_bridge.py [--verbose]
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
BRIDGE = OMEGA / "scripts" / "obsidian_second_brain.py"


def run(args: list[str], *, timeout: int = 60) -> tuple[int, str, str]:
    cmd = [sys.executable, str(BRIDGE)] + args
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"


def parse_json(out: str) -> dict | None:
    try:
        return json.loads(out)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tests. Each returns (name, ok, detail).
# ---------------------------------------------------------------------------


def test_status() -> tuple[str, bool, str]:
    rc, out, err = run(["status"])
    if rc != 0:
        return ("status", False, f"exit={rc}, stderr={err[:200]}")
    if "Notes markdown detectees" not in out:
        return ("status", False, "missing 'Notes markdown' marker")
    return ("status", True, out.splitlines()[5][:80])


def test_list_root() -> tuple[str, bool, str]:
    rc, out, _ = run(["list", "--folder", "00_Commandement"])
    payload = parse_json(out)
    if not payload or not payload.get("ok"):
        return ("list_root", False, "no JSON or ok=False")
    return ("list_root", True, f"count={payload.get('count', 0)}")


def test_audit_vault() -> tuple[str, bool, str]:
    rc, out, _ = run(["audit-vault"])
    payload = parse_json(out)
    if not payload or not payload.get("ok"):
        return ("audit_vault", False, "no JSON or ok=False")
    if "total_notes" not in payload or "broken_links_total" not in payload:
        return ("audit_vault", False, "missing keys in payload")
    return ("audit_vault", True, f"notes={payload['total_notes']}, broken={payload['broken_links_total']}")


def test_detect_orphans() -> tuple[str, bool, str]:
    rc, out, _ = run(["detect-orphans", "--limit", "5"])
    payload = parse_json(out)
    if not payload or not payload.get("ok"):
        return ("detect_orphans", False, "no JSON or ok=False")
    if "items" not in payload:
        return ("detect_orphans", False, "missing 'items'")
    return ("detect_orphans", True, f"count={payload.get('count', 0)}")


def test_detect_duplicates() -> tuple[str, bool, str]:
    rc, out, _ = run(["detect-duplicates", "--limit", "5"])
    payload = parse_json(out)
    if not payload or not payload.get("ok"):
        return ("detect_duplicates", False, "no JSON or ok=False")
    return ("detect_duplicates", True, f"count={payload.get('count', 0)}")


def test_detect_weak_notes() -> tuple[str, bool, str]:
    rc, out, _ = run(["detect-weak-notes", "--limit", "5"])
    payload = parse_json(out)
    if not payload or not payload.get("ok"):
        return ("detect_weak_notes", False, "no JSON or ok=False")
    return ("detect_weak_notes", True, f"count={payload.get('count', 0)}")


def test_detect_broken_links() -> tuple[str, bool, str]:
    rc, out, _ = run(["detect-broken-links", "--limit", "5"])
    payload = parse_json(out)
    if not payload or not payload.get("ok"):
        return ("detect_broken_links", False, "no JSON or ok=False")
    return ("detect_broken_links", True, f"count={payload.get('count', 0)}")


def test_propose_structure() -> tuple[str, bool, str]:
    rc, out, _ = run(["propose-structure"])
    payload = parse_json(out)
    if not payload or not payload.get("ok"):
        return ("propose_structure", False, "no JSON or ok=False")
    return ("propose_structure", True, f"count={payload.get('count', 0)}")


def test_filter_notes_by_tag() -> tuple[str, bool, str]:
    rc, out, _ = run(["filter-notes", "--tag", "nanobot", "--limit", "5"])
    payload = parse_json(out)
    if not payload or not payload.get("ok"):
        return ("filter_notes", False, "no JSON or ok=False")
    return ("filter_notes", True, f"count={payload.get('count', 0)}")


def test_dry_run_delete_safe_path() -> tuple[str, bool, str]:
    rc, out, _ = run(["delete-path", "--path", "_does_not_exist_test.md", "--dry-run"])
    payload = parse_json(out)
    if not payload or not payload.get("dry_run"):
        return ("dry_run_delete", False, "missing dry_run flag")
    if payload.get("exists"):
        return ("dry_run_delete", False, "test path unexpectedly exists")
    return ("dry_run_delete", True, "dry-run works on non-existent path")


def test_dry_run_rename_safe_paths() -> tuple[str, bool, str]:
    rc, out, _ = run([
        "rename-path",
        "--src", "_test_ne_pas_modifier_src.md",
        "--dst", "_test_ne_pas_modifier_dst.md",
        "--dry-run",
        "--update-links",
    ])
    payload = parse_json(out)
    if not payload or not payload.get("dry_run"):
        return ("dry_run_rename", False, "missing dry_run flag")
    if "link_updates" not in payload:
        return ("dry_run_rename", False, "missing link_updates section")
    return ("dry_run_rename", True, "dry-run rename + update-links works")


def test_security_traversal_blocked() -> tuple[str, bool, str]:
    rc, out, _ = run(["read-note", "--path", "../../etc/passwd"])
    payload = parse_json(out)
    if payload and payload.get("ok"):
        return ("security_traversal", False, "traversal NOT blocked!")
    return ("security_traversal", True, "traversal correctly rejected")


def test_security_protected_blocked() -> tuple[str, bool, str]:
    rc, out, _ = run(["delete-path", "--path", ".obsidian/workspace.json", "--dry-run"])
    payload = parse_json(out)
    if payload and payload.get("ok") and not payload.get("error"):
        return ("security_protected", False, ".obsidian write NOT blocked!")
    return ("security_protected", True, ".obsidian correctly protected")


def test_get_frontmatter_robust() -> tuple[str, bool, str]:
    """get-frontmatter on a non-existent path should return ok=False, not crash."""
    rc, out, _ = run(["get-frontmatter", "--path", "_inexistant_test.md"])
    payload = parse_json(out)
    if payload is None:
        return ("get_frontmatter_robust", False, "no JSON output (crash?)")
    if payload.get("ok"):
        return ("get_frontmatter_robust", False, "should fail on missing path")
    return ("get_frontmatter_robust", True, "missing-path error handled cleanly")


def test_sync_status() -> tuple[str, bool, str]:
    rc, out, _ = run(["sync-status"], timeout=120)
    payload = parse_json(out)
    if not payload or not payload.get("ok"):
        return ("sync_status", False, "no JSON or ok=False")
    return ("sync_status", True, f"file_count={payload.get('file_count', 0)}")


TESTS = [
    test_status,
    test_list_root,
    test_audit_vault,
    test_detect_orphans,
    test_detect_duplicates,
    test_detect_weak_notes,
    test_detect_broken_links,
    test_propose_structure,
    test_filter_notes_by_tag,
    test_dry_run_delete_safe_path,
    test_dry_run_rename_safe_paths,
    test_security_traversal_blocked,
    test_security_protected_blocked,
    test_get_frontmatter_robust,
    test_sync_status,
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Tests E2E obsidian_second_brain.py")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not BRIDGE.exists():
        print(f"FATAL : bridge introuvable {BRIDGE}")
        return 2

    passed = 0
    failed = 0
    print(f"=== Tests obsidian_second_brain.py — {len(TESTS)} cas ===\n")
    for func in TESTS:
        try:
            name, ok, detail = func()
        except Exception as exc:
            name, ok, detail = (func.__name__, False, f"raised {type(exc).__name__}: {exc}")
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
