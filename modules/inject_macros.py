#!/usr/bin/env python
"""Injecte la reference aux macros industrielles dans les GEMINI.md des light-homes."""
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path("C:/AI/nanobot-omega/gemini-light-homes")
INSTANCES = [f"gemini_{l}" for l in "ABCDEFGHIJ"]

MARKER = "## MACROS INDUSTRIELLES"

MACROS_SECTION = """

## MACROS INDUSTRIELLES (UTILISER EN PRIORITE)

Au lieu de generer du code Playwright complexe, utilise ces outils durables.
Doc complete : C:\\AI\\nanobot-omega\\automation-macros\\MACROS.md

### Self-Healing (quand un outil MCP echoue)
exec("powershell -ExecutionPolicy Bypass -File C:\\AI\\nanobot-omega\\scripts\\omega-fix.ps1")

### Cookies RGPD (apres navigation sur un nouveau site)
browser_evaluate avec le contenu de : C:\\AI\\nanobot-omega\\automation-macros\\handle-cookies.js

### Extraction contenu web (economie tokens)
exec("python C:\\AI\\nanobot-omega\\automation-macros\\fast-scrape.py URL --max-chars 5000")

### YouTube
- URL recherche : exec("python C:\\AI\\nanobot-omega\\automation-macros\\youtube-control.py url QUERY")
- Metadata : exec("python C:\\AI\\nanobot-omega\\automation-macros\\youtube-control.py metadata VIDEO_ID")
- Bypass popups : exec("python C:\\AI\\nanobot-omega\\automation-macros\\youtube-control.py inject-bypass")
- Player : exec("python C:\\AI\\nanobot-omega\\automation-macros\\youtube-control.py inject-control play")
"""

def inject():
    for inst in INSTANCES:
        md_path = BASE / inst / ".gemini" / "GEMINI.md"
        if not md_path.exists():
            print(f"  [{inst}] GEMINI.md absent - skip")
            continue
        content = md_path.read_text(encoding="utf-8")
        if MARKER in content:
            print(f"  [{inst}] Macros deja presentes - skip")
            continue
        content += MACROS_SECTION
        md_path.write_text(content, encoding="utf-8")
        print(f"  [{inst}] Macros injectees")
    print("\n  OK")

if __name__ == "__main__":
    inject()
