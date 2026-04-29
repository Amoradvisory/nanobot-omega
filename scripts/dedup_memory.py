"""Deduplique workspace/memory/MEMORY.md.

Detecte les sections (## Title) repetees et garde la premiere occurrence.
Ecrit le resultat sur place, en sauvegardant l'original dans
backups/claude-stabilization-YYYYMMDD/MEMORY.md.predup.bak.

Usage : python scripts/dedup_memory.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

OMEGA = Path(r"C:\AI\nanobot-omega")
MEMORY = OMEGA / "workspace" / "memory" / "MEMORY.md"


def split_sections(text: str) -> list[tuple[str, str]]:
    """Split text into (header, body) pairs. The first chunk before any '## '
    is keyed by '__preamble__'."""
    parts: list[tuple[str, str]] = []
    pattern = re.compile(r"^## .+$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return [("__preamble__", text)]
    if matches[0].start() > 0:
        parts.append(("__preamble__", text[:matches[0].start()]))
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end]
        header = match.group(0).strip()
        parts.append((header, chunk))
    return parts


def dedup(text: str) -> tuple[str, dict[str, int]]:
    parts = split_sections(text)
    seen: dict[str, str] = {}
    dropped: dict[str, int] = {}
    out_chunks: list[str] = []
    for header, chunk in parts:
        if header == "__preamble__":
            out_chunks.append(chunk)
            continue
        # Normalize header for comparison
        key = header.strip().lower()
        if key in seen:
            # Compare bodies; if same, drop. If different, keep with marker.
            if seen[key].strip() == chunk.strip():
                dropped[header] = dropped.get(header, 0) + 1
                continue
            # Different content: keep both
            out_chunks.append(chunk)
        else:
            seen[key] = chunk
            out_chunks.append(chunk)
    return "".join(out_chunks).rstrip() + "\n", dropped


def main() -> int:
    ap = argparse.ArgumentParser(description="Deduplique MEMORY.md")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not MEMORY.exists():
        print(f"MEMORY.md introuvable : {MEMORY}")
        return 1
    text = MEMORY.read_text(encoding="utf-8", errors="replace")
    new_text, dropped = dedup(text)
    if not dropped:
        print("Aucun doublon detecte.")
        return 0
    delta_lines = len(text.splitlines()) - len(new_text.splitlines())
    delta_bytes = len(text.encode("utf-8")) - len(new_text.encode("utf-8"))
    if args.dry_run:
        print(f"[DRY-RUN] {len(dropped)} sections seraient supprimees, -{delta_lines} lignes, -{delta_bytes} octets.")
        for header, count in sorted(dropped.items()):
            print(f"  drop {count}x {header}")
        return 0

    # Backup
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = OMEGA / "backups" / f"claude-stabilization-{stamp[:8]}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"MEMORY.md.predup-{stamp}.bak"
    shutil.copy2(MEMORY, backup_path)
    MEMORY.write_text(new_text, encoding="utf-8")
    print(f"OK : {len(dropped)} doublons supprimes (-{delta_lines} lignes).")
    print(f"Backup : {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
