# NANOBOT — Registre des capacites

> Source de verite unique. Genere automatiquement par
> `python C:/AI/nanobot-omega/scripts/capabilities_registry.py`.
> Ne pas editer a la main.

Genere : 2026-05-03T10:00:44+00:00
Total : 84 capacites

## Par statut
- broken: 2
- disabled: 1
- ok: 81

## Par categorie
- builtin_tools: 17
- obsidian: 24
- operational: 20
- google_workspace: 8
- mcp_servers: 5
- browser: 10

## Categorie : builtin_tools

| nom | statut | risque | read-only | confirmation | description |
|-----|--------|--------|-----------|--------------|-------------|
| `browser_automation` | ok | moderate | non | non | Tool natif enregistre par le runtime Nanobot |
| `cron` | ok | safe | non | non | Tool natif enregistre par le runtime Nanobot |
| `desktop_automation` | ok | moderate | non | non | Tool natif enregistre par le runtime Nanobot |
| `edit_file` | ok | destructive | non | non | Tool natif enregistre par le runtime Nanobot |
| `exec` | ok | destructive | non | non | Tool natif enregistre par le runtime Nanobot |
| `glob` | broken | safe | oui | non | Tool natif enregistre par le runtime Nanobot |
| `grep` | broken | safe | oui | non | Tool natif enregistre par le runtime Nanobot |
| `list_dir` | ok | safe | oui | non | Tool natif enregistre par le runtime Nanobot |
| `message` | ok | safe | non | non | Tool natif enregistre par le runtime Nanobot |
| `ocr` | ok | safe | oui | non | Tool natif enregistre par le runtime Nanobot |
| `read_file` | ok | safe | oui | non | Tool natif enregistre par le runtime Nanobot |
| `spawn` | ok | safe | non | non | Tool natif enregistre par le runtime Nanobot |
| `tool_diagnostics` | ok | safe | oui | non | Tool natif enregistre par le runtime Nanobot |
| `vision_analyze_image` | ok | safe | oui | non | Tool natif enregistre par le runtime Nanobot |
| `web_fetch` | ok | safe | oui | non | Tool natif enregistre par le runtime Nanobot |
| `web_search` | ok | safe | oui | non | Tool natif enregistre par le runtime Nanobot |
| `write_file` | ok | destructive | non | non | Tool natif enregistre par le runtime Nanobot |

## Categorie : obsidian

| nom | statut | risque | read-only | confirmation | description |
|-----|--------|--------|-----------|--------------|-------------|
| `obsidian.bootstrap` | ok | safe | non | non | Initialise la structure du vault et les notes pivots |
| `obsidian.status` | ok | safe | oui | non | Etat global du vault (chemins, comptes, derniere note) |
| `obsidian.open` | ok | safe | oui | non | Ouvre une note dans Obsidian (URI obsidian://) |
| `obsidian.capture` | ok | safe | non | non | Cree une nouvelle note de capture auto-classifiee |
| `obsidian.daily` | ok | safe | non | non | Ajoute du contenu a la note du jour |
| `obsidian.import` | ok | safe | non | non | Importe un PDF/image/markdown dans le vault |
| `obsidian.search` | ok | safe | oui | non | Recherche dans le vault |
| `obsidian.sync-memory` | ok | safe | non | non | Synchronise la memoire Nanobot dans le vault |
| `obsidian.relations` | ok | moderate | non | non | Retisse les relations Hubs utiles / Passerelles utiles |
| `obsidian.write-note` | ok | moderate | non | non | Cree ou modifie une note |
| `obsidian.read-note` | ok | safe | oui | non | Lit une note (frontmatter + body) en JSON |
| `obsidian.delete-path` | ok | destructive | non | oui | Supprime fichier ou dossier du vault |
| `obsidian.create-folder` | ok | safe | non | non | Cree un dossier dans le vault |
| `obsidian.rename-path` | ok | moderate | non | oui | Renomme/deplace fichier ou dossier |
| `obsidian.move-note` | ok | moderate | non | oui | Deplace une note vers un autre dossier |
| `obsidian.list` | ok | safe | oui | non | Liste recursive du vault ou d'un sous-dossier |
| `obsidian.set-frontmatter` | ok | moderate | non | non | Fusionne des cles dans le frontmatter d'une note |
| `obsidian.get-frontmatter` | ok | safe | oui | non | Lit le frontmatter d'une note |
| `obsidian.filter-notes` | ok | safe | oui | non | Filtre les notes par tag/propriete/dossier/texte |
| `obsidian.tags` | ok | safe | non | non | Ajoute/retire des tags d'une note |
| `obsidian.sync-status` | ok | safe | oui | non | Etat de la synchronisation Google Drive du vault |
| `obsidian.attachments` | ok | safe | oui | non | Liste les pieces jointes non-Markdown |
| `obsidian.add-attachment` | ok | safe | non | non | Copie une piece jointe dans le vault |
| `obsidian.move-attachment` | ok | moderate | non | oui | Renomme/deplace une piece jointe |

## Categorie : operational

| nom | statut | risque | read-only | confirmation | description |
|-----|--------|--------|-----------|--------------|-------------|
| `obsidian_bridge` | ok | moderate | non | non | Pont Obsidian (24 sous-commandes) |
| `google_workspace_cli` | ok | moderate | non | non | CLI Gmail/Calendar/Drive/Docs/Sheets/Tasks/Contacts |
| `google_workspace_mcp` | ok | moderate | non | non | Serveur MCP Google Workspace local (44 outils) |
| `scraping_champion` | ok | safe | oui | non | Scraping web (HTTP + Playwright fallback) |
| `app_acquisition` | ok | moderate | non | oui | Installer/ouvrir/verifier apps Windows (winget) |
| `proactive_intel` | ok | safe | oui | non | Veille RSS/web proactive |
| `desktop_intel` | ok | safe | oui | non | Liste fenetres Windows + OCR + xlsx |
| `resilience_orchestrator` | ok | safe | oui | non | Plans multi-routes + impasse detection |
| `agent_forge` | ok | moderate | non | non | Genere des mini-agents ad hoc |
| `build_startup_context` | ok | safe | non | non | Regenere NANOBOT_STARTUP_CONTEXT.md/json |
| `nanobot_self_check` | ok | safe | oui | non | Health-check + recovery |
| `capabilities_registry` | ok | safe | non | non | Registre central des capacites (ce script) |
| `tools_audit` | ok | safe | oui | non | Audit runtime des tools natifs |
| `workspace_cleanup` | ok | moderate | non | oui | Inventaire + quarantaine workspace |
| `dedup_memory` | ok | safe | non | non | Deduplique MEMORY.md |
| `test_obsidian_bridge` | ok | safe | oui | non | Tests E2E anti-regression bridge Obsidian (15 cas) |
| `tasks_control` | ok | moderate | non | oui | Gestion tasks Windows Nanobot (list/health/run/pause/resume/logs) |
| `veille_2ememain_control` | ok | moderate | non | oui | Pilotage veille 2ememain (status/health/run/Xkm/test-notification) |
| `run_veille_2ememain` | ok | safe | oui | non | Scraper Playwright 2ememain (deterministe, sans LLM) |
| `run_veille_and_notify` | ok | moderate | non | non | Orchestrateur veille + notif Telegram enrichie (photo/distance/scoring/NL) |

## Categorie : google_workspace

| nom | statut | risque | read-only | confirmation | description |
|-----|--------|--------|-----------|--------------|-------------|
| `google.gmail` | ok | destructive | non | oui | Gmail : search/read/send + labels + modify (read/unread, archive, trash, untrash, delete) |
| `google.calendar` | ok | moderate | non | non | Calendar : list/create/delete events |
| `google.drive` | ok | moderate | non | non | Drive : list/search/read/upload/create-folder/update-metadata/move/delete |
| `google.docs` | ok | moderate | non | non | Google Docs : create/read/append/delete |
| `google.sheets` | ok | moderate | non | non | Google Sheets : create/read/append-row/update/clear/delete |
| `google.tasks` | ok | moderate | non | non | Tasks : list/add/complete |
| `google.contacts` | ok | moderate | non | non | Contacts : list/search/create |
| `google.auth` | ok | moderate | oui | non | OAuth : status/refresh/setup |

## Categorie : mcp_servers

| nom | statut | risque | read-only | confirmation | description |
|-----|--------|--------|-----------|--------------|-------------|
| `mcp.filesystem` | ok | moderate | non | non | Serveur MCP filesystem |
| `mcp.google_workspace` | ok | moderate | non | non | Serveur MCP google_workspace |
| `mcp.memory` | ok | moderate | non | non | Serveur MCP memory |
| `mcp.notion` | ok | moderate | non | non | Serveur MCP notion |
| `mcp.sequential_thinking` | disabled | moderate | non | non | Serveur MCP sequential_thinking |

## Comment utiliser ce registre

1. Avant de declarer une capacite indisponible, lire ce registre.
2. Si une capacite manque (status=missing) verifier le module indique.
3. Pour une capacite cassee (status=broken) lancer `nanobot_self_check.py check`.
4. Le registre est regenere par `Run-NanobotOmegaSupervisor.ps1` au demarrage.
