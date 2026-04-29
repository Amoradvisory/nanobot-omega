#!/usr/bin/env python
"""Injecte les regles operationnelles dans les GEMINI.md des gemini-light-homes."""
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path("C:/AI/nanobot-omega/gemini-light-homes")
INSTANCES = [f"gemini_{l}" for l in "ABCDEFGHIJ"]

RULES = """

## REGLES OPERATIONNELLES (NON NEGOCIABLE)

### Navigateur : UN Chrome, DES onglets
- Pour ouvrir une URL : exec("C:\\AI\\nanobot-omega\\Open-Shared-Nanobot-Browser.bat \\"URL\\"")
- Ca ouvre un ONGLET si Chrome tourne, ou lance Chrome si absent.
- JAMAIS lancer chrome.exe directement. JAMAIS --new-window.

### Recherche : URL directe
- YouTube : Open-Shared-Nanobot-Browser.bat "https://www.youtube.com/results?search_query=MON+SUJET"
- Google : Open-Shared-Nanobot-Browser.bat "https://www.google.com/search?q=MON+SUJET"
- JAMAIS ouvrir google.com puis taper. Construis l'URL directement.

### Verification obligatoire
- Apres chaque action navigateur, VERIFIE le resultat (screenshot ou snapshot).
- NE DIS JAMAIS "c'est fait" sans avoir verifie.

### Anti-boucle : 3 max
- Si une action echoue 3 fois, STOP et change d'approche.
- NE JAMAIS boucler silencieusement.

### Rapidite
- Si l'utilisateur dit "ouvre YouTube echecs" : UNE commande, l'URL directe.
- Pas d'etape intermediaire inutile.
"""

MARKER = "## REGLES OPERATIONNELLES"

def inject():
    for inst in INSTANCES:
        md_path = BASE / inst / ".gemini" / "GEMINI.md"
        if not md_path.exists():
            print(f"  [{inst}] GEMINI.md absent - skip")
            continue
        content = md_path.read_text(encoding="utf-8")
        if MARKER in content:
            print(f"  [{inst}] Regles deja presentes - skip")
            continue
        content += RULES
        md_path.write_text(content, encoding="utf-8")
        print(f"  [{inst}] Regles injectees")

    print("\n  OK")

if __name__ == "__main__":
    inject()
