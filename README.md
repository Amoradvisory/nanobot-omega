# Nanobot Omega

Agent local autonome multi-canal (Telegram, terminal, scripts) pour Windows.
Conçu pour fonctionner 24/7 sur un PC dédié (i7-5600U, 8 GB RAM utilisables).

## Architecture en une phrase

Ollama local (qwen2.5:3b par défaut) + 10 instances Gemini CLI (rotation automatique A→J sur 429) + 44 outils MCP Google Workspace + bridge Obsidian + scraping Playwright + acquisition d'apps Windows, le tout supervisé par un watchdog avec auto-restart et un self-heal périodique.

## Composants

| Module | Rôle |
|---|---|
| `gemini_cli_orchestrator.py` | Orchestrateur Gemini avec rotation A→J + cooldown par instance |
| `gemini_orchestrator_provider.py` | Provider qui injecte le startup context dans le prompt |
| `ollama_orchestrator.py` | Pont vers le daemon Ollama local (port 11434) |
| `scripts/obsidian_second_brain.py` | Bridge Obsidian (24 sous-commandes : status, capture, daily, audit-vault, detect-orphans, …) |
| `scripts/google_workspace_cli.py` + `_mcp.py` | Gmail, Calendar, Drive, Docs, Sheets, Tasks, Contacts |
| `scripts/scraping_champion.py` | HTTP + Playwright fallback, extraction xlsx |
| `scripts/app_acquisition.py` | winget + downloads + verification réelle |
| `scripts/proactive_intel.py` | Veille RSS / web |
| `scripts/desktop_intel.py` | Liste fenêtres Windows + OCR + xlsx |
| `scripts/resilience_orchestrator.py` | Plans multi-routes, impasse detection |
| `scripts/agent_forge.py` | Génère des mini-agents ad hoc |
| `scripts/build_startup_context.py` | Régénère `NANOBOT_STARTUP_CONTEXT.md` |
| `scripts/nanobot_self_check.py` | Health-check + recovery |
| `scripts/capabilities_registry.py` | Registre central des capacités (source de vérité) |
| `scripts/test_obsidian_bridge.py` | Tests E2E anti-régression du bridge Obsidian |
| `scripts/workspace_cleanup.py` | Inventaire + quarantaine du workspace |

## Documents canoniques

- `MISSION_YOLO.md` — comportement de l'agent
- `AGENT_V2.md` — protocole d'exécution (goal → plan → action → verify → repair → final)
- `workspace/CORE_DIRECTIVE.md` — directive suprême
- `workspace/USER.md` — profil utilisateur
- `workspace/NANOBOT_ARSENAL.md` — arsenal natif (priorité)
- `workspace/NANOBOT_RECENT_UPGRADES.md` — mémoire incrémentale
- `workspace/NANOBOT_STARTUP_CONTEXT.md` — auto-généré, injecté au prompt
- `workspace/NANOBOT_CAPABILITIES.md` — registre auto-généré (source de vérité)
- `workspace/NANOBOT_OBSIDIAN_INTEGRATION.md` — mode d'emploi Obsidian unifié
- `workspace/NANOBOT_RECOVERY_PROTOCOL.md` — procédure si Nanobot oublie ses capacités

## Démarrage rapide

```cmd
# 1. Vérifier la santé globale
python scripts\nanobot_self_check.py check

# 2. Régénérer le contexte de démarrage
python scripts\build_startup_context.py

# 3. Régénérer le registre des capacités
python scripts\capabilities_registry.py

# 4. Tester le bridge Obsidian (15 cas E2E)
python scripts\test_obsidian_bridge.py
```

## Auto-restart au logon

3 raccourcis dans `shell:startup` lancent au démarrage Windows :
- Telegram gateway (long-polling, pas de port HTTP)
- Watchdog Ollama (auto-restart sur 3 fails consécutifs)
- Omega autostart (Watchtower + Brain)

Tâches Task Scheduler complémentaires :
- `NanobotSelfHeal` (toutes les 10 min, beacon de santé global)
- `NanobotVeille2ememain` (toutes les 30 min, scraper)
- `NanobotLogRotate` (quotidien 03:00)
- `NanobotBackup` (quotidien 03:15, ZIP des fichiers d'état)

## Intégration Obsidian

Vault canonique : `C:\Users\user\Mon Drive\DriveSyncFiles\ARCHITECTE_SYSTEM\` (sync Drive Desktop).

Toutes les opérations passent par le bridge :
```cmd
python scripts\obsidian_second_brain.py status
python scripts\obsidian_second_brain.py audit-vault
python scripts\obsidian_second_brain.py detect-orphans --limit 20
python scripts\obsidian_second_brain.py rename-path --src X --dst Y --dry-run --update-links
```

24 sous-commandes au total. Mode dry-run sur `delete-path`, `rename-path`, `move-note`. Journal append-only dans `logs/obsidian_actions.jsonl`.

## Sécurité

- Aucune écriture brute dans le vault — toujours via le bridge.
- Anti-traversal sur tous les chemins relatifs (`_safe_vault_path`).
- `.obsidian/` et `.trash/` protégés.
- `archive_exclusions` (par défaut `05_Archives/`) évite les chemins > 260 chars Windows MAX_PATH.

## Hardware cible

- Intel i7-5600U (2 cores / 4 threads), 19.7 GB RAM total, ~6 tok/s sur CPU.
- Pas de GPU NVIDIA — inference 100% CPU.
- Modèles Ollama : `qwen2.5:3b` (1.9 GB, défaut) + `qwen2.5:0.5b` (379 MB, fallback rapide).

## Licence

Personnel — pas de licence open-source pour le moment.
