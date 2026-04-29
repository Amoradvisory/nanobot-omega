# NANOBOT — Protocole de récupération

> Procédure à suivre si NanoBot semble avoir oublié ses capacités, hallucine
> qu'un outil n'existe pas, ou répète d'anciennes erreurs déjà corrigées.

Dernière mise à jour : 2026-04-29

---

## Symptômes typiques d'un décrochage

- NanoBot dit "je ne peux pas faire X" alors que le tool/script existe
- NanoBot ne trouve plus l'intégration Obsidian
- NanoBot prétend que son OAuth Google est cassé alors que `has_refresh_token: true`
- NanoBot répète une erreur déjà résolue dans `NANOBOT_RECENT_UPGRADES.md`
- NanoBot ne sait plus quelles sous-commandes sont disponibles
- NanoBot expose du tool-noise dans Telegram (JSON, plans, MCP names)

---

## Procédure de récupération — étape par étape

### Étape 1 — Diagnostic complet

```cmd
python C:\AI\nanobot-omega\scripts\nanobot_self_check.py check
```

Lis le score :
- `OK` : pas de problème système, le décrochage est conversationnel (voir Étape 6)
- `DÉGRADÉ` : warnings — voir les `fix_hint` retournés par chaque check
- `CASSÉ` : erreurs bloquantes — appliquer les corrections d'abord

### Étape 2 — Régénérer le contexte de démarrage

```cmd
python C:\AI\nanobot-omega\scripts\build_startup_context.py
```

Effet : régénère `NANOBOT_STARTUP_CONTEXT.md` et `.json`. Ce fichier est injecté automatiquement dans le prompt système à chaque nouvelle conversation.

### Étape 3 — Régénérer le registre des capacités

```cmd
python C:\AI\nanobot-omega\scripts\capabilities_registry.py
```

Effet : régénère `NANOBOT_CAPABILITIES.md` et `.json`. C'est la **source de vérité unique** des capacités vérifiées.

### Étape 4 — Vérifier l'intégration Obsidian

```cmd
python C:\AI\nanobot-omega\scripts\obsidian_second_brain.py status
```

Doit retourner sans crash, avec un nombre de notes > 0. Si crash :
- Problème de chemin > MAX_PATH dans le vault → vérifier `archive_exclusions` dans `workspace/obsidian_bridge_config.json`
- Vault inaccessible → vérifier Google Drive Desktop et le compte `monagenda.be@gmail.com`

### Étape 5 — Refresh OAuth Google si nécessaire

```cmd
python C:\AI\nanobot-omega\scripts\nanobot_self_check.py recover refresh-google
```

Ou directement :
```cmd
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json auth refresh
```

Si même le refresh échoue : reauthorisation complète avec `setup_google_auth.py --force`.

### Étape 6 — Restart du gateway Telegram (si nécessaire)

Les modifications de scripts ne prennent effet qu'au prochain démarrage du gateway. Pour appliquer immédiatement :

```powershell
Get-Process python | Where-Object { $_.Id -eq <PID-GATEWAY> } | Stop-Process -Force
Start-ScheduledTask -TaskName 'NanobotOmegaSupervisorAdmin'
```

Le PID du gateway est dans `C:\AI\nanobot-omega\state\gateway.lock`. Le supervisor relance automatiquement le gateway.

### Étape 7 — En dernier recours, recovery global

```cmd
python C:\AI\nanobot-omega\scripts\nanobot_self_check.py recover all
```

Effet : refresh-google + rebuild-startup-context + rebuild-tools-audit en cascade.

---

## Sources de vérité — ordre de priorité

Quand NanoBot doit savoir ce qu'il peut faire, il consulte **dans cet ordre** :

1. **`workspace/NANOBOT_CAPABILITIES.json`** — registre auto-généré (machine-readable, fiable)
2. **`workspace/NANOBOT_STARTUP_CONTEXT.md`** — injecté dans le prompt système à chaque conversation
3. **`workspace/NANOBOT_ARSENAL.md`** — fiche courte d'arsenal natif (humain)
4. **`workspace/NANOBOT_RECENT_UPGRADES.md`** — mémoire opérationnelle des changements récents
5. **`workspace/RADICAL_CAPABILITIES.md`** — capacités Gmail modify, veille proactive, agent forge
6. **`workspace/GOOGLE_WORKSPACE_CAPABILITIES.md`** — Google détaillé
7. **`workspace/NANOBOT_OBSIDIAN_INTEGRATION.md`** — Obsidian détaillé
8. **`AGENT_V2.md` + `MISSION_YOLO.md`** — protocole d'exécution

⚠️ **Sources DÉPRÉCIÉES** (ne pas utiliser) :
- `workspace/ARSENAL.md` (couche OMEGA_*.py historique)
- `workspace/TOOLS.md` (idem)

---

## Causes connues de régression

| Symptôme | Cause | Réparation |
|---|---|---|
| `obsidian status` crash | Chemin > 260 chars dans `05_Archives/` | Fixé 2026-04-28 (helpers `_safe_stat`, `_iter_vault_md`, `archive_exclusions`) |
| OAuth invalide | Token expiré | `nanobot_self_check.py recover refresh-google` |
| MEMORY.md duplique des sections | Append sans dédup par Dream/Omega Core | `python scripts/dedup_memory.py` |
| Telegram silencieux | DNS pas prêt au boot | Patch retry exponentiel dans `Start-NanobotTelegramGateway.ps1` |
| Telegram conflict 409 | 2 pollers actifs | `scripts/Stop-StaleTelegramNanobot.ps1` (lancé par supervisor) |
| Capacité documentée mais inaccessible | Le startup context est obsolète | `build_startup_context.py` puis restart gateway |
| Capacité existe mais NanoBot l'ignore | Sources de vérité contradictoires | Lire `NANOBOT_CAPABILITIES.md` (priorité #1) |

---

## Quand tout va bien

État sain attendu :

- `nanobot_self_check.py check` → score `OK` ou `DÉGRADÉ` (warnings tolérables)
- `obsidian_second_brain.py status` → ≥ 50 notes détectées
- `capabilities_registry.py` → ≥ 60 capacités, ≤ 3 broken
- `state/gateway.lock` → existe avec PID actif
- Port 11434 → daemon Ollama répond
- `health/self_check_latest.json` → généré dans les dernières 48h
