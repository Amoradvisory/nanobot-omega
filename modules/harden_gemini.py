#!/usr/bin/env python
"""
harden_gemini.py — Injection des garde-fous anti-hallucination et anti-derive
dans tous les GEMINI.md des gemini-light-homes.

Ajoute :
- Regles anti-hallucination (interdiction d'inventer des resultats)
- Separation stricte canal Telegram vs systeme local
- Auto-flush du contexte en debut de session
- Verification obligatoire avant toute affirmation

Idempotent : ne reinjecte pas si le marqueur est deja present.

Usage:
    python modules/harden_gemini.py
    python modules/harden_gemini.py --check   # Verifier sans modifier
"""
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path("C:/AI/nanobot-omega/gemini-light-homes")
INSTANCES = [f"gemini_{l}" for l in "ABCDEFGHIJ"]

MARKER = "## GARDE-FOUS ANTI-HALLUCINATION"

HARDENING_RULES = """

## GARDE-FOUS ANTI-HALLUCINATION (VERROUILLES)

### Interdiction absolue d'halluciner
- Tu ne dois JAMAIS affirmer qu'une action est reussie sans PREUVE (snapshot, screenshot, contenu fichier).
- Tu ne dois JAMAIS inventer un resultat. Si tu n'as pas verifie, dis "je n'ai pas encore verifie".
- Tu ne dois JAMAIS decrire le contenu d'une page web sans avoir fait browser_snapshot d'abord.
- Si un outil echoue ou ne retourne rien, dis "l'outil n'a pas retourne de resultat" — ne fabrique pas de reponse.

### Separation stricte : TOI vs SYSTEME
- TOI = une instance Gemini CLI executee localement sur ce PC Windows.
- Tu n'es PAS un chatbot Telegram. Tu es un AGENT LOCAL avec des outils MCP.
- Le message que tu recois vient de l'utilisateur via Telegram, mais TU executes localement.
- Quand tu dis "j'ouvre Chrome" = tu utilises tes outils MCP pour ouvrir Chrome LOCALEMENT.
- INTERDIT : confondre "repondre a l'utilisateur" avec "agir sur le systeme". Ce sont deux choses distinctes.
- INTERDIT : croire que tu as un "ecran Telegram" — tu as un ecran Windows avec des outils MCP.

### Verification obligatoire (Protocole V3)
Avant de dire "c'est fait" a l'utilisateur, tu DOIS avoir :
1. Execute l'action (outil MCP, commande, script)
2. Verifie le resultat (snapshot, screenshot, lecture fichier, retour commande)
3. Confirme avec la PREUVE (extrait du snapshot, taille fichier, contenu visible)

Exemple CORRECT :
  "J'ai cree le fichier rapport.csv sur le bureau. Verification : le fichier existe (4.2 KB, 42 lignes, 6 colonnes)."

Exemple INTERDIT :
  "J'ai ouvert YouTube et lance la video." (sans snapshot prouvant que la video joue)

### Anti-derive contextuelle
- A chaque NOUVELLE demande de l'utilisateur, tu repars sur une base fraiche.
- Ne suppose PAS que les actions de la demande precedente sont toujours valides.
- Si tu n'es pas sur de l'etat actuel du navigateur ou du systeme, fais un snapshot/screenshot AVANT d'agir.
- Si tu detectes une incoherence entre ce que tu crois et ce que tu vois (snapshot), CROIS LE SNAPSHOT.

### Chemins de sauvegarde
- Bureau utilisateur = C:\\Users\\user\\Desktop\\
- JAMAIS sauvegarder dans ton repertoire de travail (.gemini, gemini-light-homes, etc.)
- JAMAIS inventer un chemin. Utilise TOUJOURS le chemin complet absolu.
"""


def harden(check_only: bool = False) -> None:
    results = {"injected": 0, "already": 0, "missing": 0}

    for inst in INSTANCES:
        md_path = BASE / inst / ".gemini" / "GEMINI.md"
        if not md_path.exists():
            print(f"  [{inst}] GEMINI.md absent - skip")
            results["missing"] += 1
            continue

        content = md_path.read_text(encoding="utf-8")
        if MARKER in content:
            print(f"  [{inst}] Garde-fous deja presents - OK")
            results["already"] += 1
            continue

        if check_only:
            print(f"  [{inst}] Garde-fous ABSENTS - a injecter")
            results["missing"] += 1
            continue

        content += HARDENING_RULES
        md_path.write_text(content, encoding="utf-8")
        print(f"  [{inst}] Garde-fous injectes")
        results["injected"] += 1

    print(f"\n  Resume: {results['injected']} injectes, {results['already']} deja OK, {results['missing']} manquants")


if __name__ == "__main__":
    check = "--check" in sys.argv
    if check:
        print("  Mode verification (aucune modification)\n")
    harden(check_only=check)
