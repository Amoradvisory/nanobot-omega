---
name: resilience
description: "Moteur de resilience et anti-boucle. Retry intelligent, detection de repetition, fallback automatique, journalisation legere. Declencheurs: erreur, echec, timeout, boucle detectee, action repetee, retry, fallback."
---

# Resilience — Execution Robuste et Anti-Boucle

Module : `C:/AI/nanobot-omega/modules/resilient_engine.py`

---

## Anti-Boucle (PRIORITE ABSOLUE)

### Detection automatique
Avant CHAQUE action repetitive (navigation, clic, recherche, saisie) :

```python
from modules.resilient_engine import detect_loop, clear_loop

# Enregistrer l'action
result = detect_loop("action:description_courte")

if result["looping"]:
    # ARRET IMMEDIAT de l'approche actuelle
    # Lire result["suggestion"] pour la strategie alternative
    # Changer completement de methode
    clear_loop()  # Reset apres changement de strategie
```

### Signatures d'action (exemples)
```
"navigate:google.com/search?q=meteo"
"click:bouton-submit-form"
"search:duckduckgo:actualites IA"
"type:email-field:user@example.com"
"fetch:api.example.com/data"
```

### Regles fermes :
| Repetitions | Action |
|-------------|--------|
| 3x meme navigation | STOP. Changer d'URL ou de methode (fetch vs browser). |
| 3x meme clic | STOP. Screenshot, analyser, changer de selecteur. |
| 3x meme recherche | STOP. Reformuler ou changer de moteur. |
| 5x n'importe quoi | CRITIQUE. Abandonner l'approche. Documenter le blocage. |

---

## Retry Intelligent

Pour les operations sujettes a echecs transitoires (reseau, API, timeout) :

```python
from modules.resilient_engine import resilient_call, RetryConfig

# Appel avec retry automatique
result = resilient_call(
    ma_fonction,
    arg1, arg2,
    label="appel-api-meteo",
    config=RetryConfig(
        max_attempts=3,
        base_delay_s=1.0,
        backoff_factor=2.0,  # 1s, 2s, 4s
    ),
    fallback=ma_fonction_alternative  # Optionnel
)

if result["ok"]:
    data = result["result"]
else:
    erreur = result["error"]
    # result["transient"] indique si l'erreur est temporaire
```

### Erreurs transitoires (retry automatique) :
timeout, 429, 503, connection reset, rate limit, quota, overloaded, busy

### Erreurs fatales (PAS de retry) :
404, 401, 403, permission denied, file not found, syntax error, invalid argument

---

## Journalisation

Les logs sont dans `C:/AI/nanobot-omega/state/resilient.log` (rotation auto a 1MB).

Format : `[2026-04-14 23:15:30] [RETRY] appel-api: timeout after 30s — wait 2.0s`

Pas besoin de gerer les logs manuellement — le moteur s'en charge.
