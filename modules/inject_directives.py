#!/usr/bin/env python
"""
Injecte les directives nanobot-omega dans le GEMINI.md de chaque instance.
Ajoute la section MODULES OMEGA en fin de fichier (idempotent — ne double pas).
"""
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GEMINI_BASE = Path("C:/Users/user/GeminiCLI")
INSTANCES = list("ABCDEFGHIJ")

OMEGA_SECTION = """

---

## SECTION OMEGA — MODULES DE PUISSANCE (v1.0)

### Modules disponibles (C:/AI/nanobot-omega/modules/)

| Module | Fichier | Role |
|--------|---------|------|
| Chrome Launcher | `chrome_launcher.ps1` | Instance unique Chrome, gestion onglets, CDP 9222 |
| Resilient Engine | `resilient_engine.py` | Retry intelligent, detection de boucle, fallback |
| State Manager | `state_manager.py` | Memoire vive operationnelle, suivi de tache |
| PC-Master | `pc_master.py` | Controle avance Windows (fenetres, saisie, focus, processus) |

### Directives critiques

1. **CHROME = UN SEUL PROCESSUS, PLUSIEURS ONGLETS**
   - JAMAIS `Start-Process chrome` ou `desktop_open_app chrome`
   - TOUJOURS utiliser : `python C:/AI/nanobot-omega/modules/pc_master.py url "https://..."`
   - Ou en PowerShell : `& "C:/AI/nanobot-omega/modules/chrome_launcher.ps1" -Url "https://..."`

2. **ANTI-BOUCLE = OBLIGATOIRE**
   - Avant chaque action repetitive : `from modules.resilient_engine import detect_loop`
   - 3 repetitions = STOP + changement de strategie
   - 5 repetitions = ABANDON de l'approche

3. **MEMOIRE OPERATIONNELLE = SYSTEMATIQUE**
   - Debut de tache : `state.begin_task("nom")`
   - Chaque etape : `state.advance_step("description")`
   - Decouverte : `state.note("texte")`
   - Fin : `state.complete_task("resultat")`

4. **RETRY INTELLIGENT = AUTOMATIQUE**
   - Toute operation reseau/API : envelopper dans `resilient_call()`
   - Les erreurs transitoires (timeout, 429, 503) sont retryees automatiquement
   - Les erreurs fatales (404, 403, permission denied) ne sont PAS retryees

### Ordre de priorite des outils web

1. **fetch MCP** — Le plus rapide. Pages statiques, APIs, documentation.
2. **search MCP** — Recherche rapide sans navigateur.
3. **browser-automation (Playwright)** — Pages dynamiques, formulaires.
4. **Chrome CDP via pc_master** — Sessions persistantes, cookies gardes.

### Commandes rapides

```bash
# Chrome
python C:/AI/nanobot-omega/modules/pc_master.py url "https://example.com"
python C:/AI/nanobot-omega/modules/pc_master.py tabs

# Etat de travail
python C:/AI/nanobot-omega/modules/state_manager.py summary
python C:/AI/nanobot-omega/modules/state_manager.py set "key" "value"

# PC
python C:/AI/nanobot-omega/modules/pc_master.py windows
python C:/AI/nanobot-omega/modules/pc_master.py focus "Chrome"
python C:/AI/nanobot-omega/modules/pc_master.py screenshot
python C:/AI/nanobot-omega/modules/pc_master.py sysinfo
```
"""

MARKER = "## SECTION OMEGA"

def inject():
    for letter in INSTANCES:
        gemini_md = GEMINI_BASE / letter / ".gemini" / "GEMINI.md"
        if not gemini_md.exists():
            print(f"  [{letter}] GEMINI.md non trouve — skip")
            continue

        content = gemini_md.read_text(encoding="utf-8")

        # Idempotent : ne pas doubler
        if MARKER in content:
            print(f"  [{letter}] Section OMEGA deja presente — skip")
            continue

        content += OMEGA_SECTION
        gemini_md.write_text(content, encoding="utf-8")
        print(f"  [{letter}] Section OMEGA injectee")

    # Template aussi
    tpl = GEMINI_BASE / "_template" / "GEMINI.md"
    if tpl.exists():
        content = tpl.read_text(encoding="utf-8")
        if MARKER not in content:
            content += OMEGA_SECTION
            tpl.write_text(content, encoding="utf-8")
            print(f"  [_template] Section OMEGA injectee")

    print("\n  Injection terminee.")


if __name__ == "__main__":
    inject()
