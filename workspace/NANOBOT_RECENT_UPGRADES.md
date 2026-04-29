# NANOBOT RECENT UPGRADES

Purpose: this file is persistent operational memory. Read it in future
conversations when the user asks about what was improved, when Nanobot seems to
repeat an old mistake, or when choosing the right route for files, Excel,
Telegram, browser, Google Workspace, Notion, or self-repair.

Last updated: 2026-04-26

## Critical Summary For Prompt Context

- Scheduling / 2ememain: the real operational watch is Windows Task
  `NanobotVeille2ememain`, every 30 min, running
  `C:/Users/user/Desktop/FIRE/scripts/nanobot_veille_run_hidden.vbs` ->
  `nanobot_veille_run.bat` -> `C:/AI/nanobot-omega/workspace/run_veille_and_notify.py`.
  Claude scheduled-tasks for 2ememain/Lille are mostly recipes (`SKILL.md`),
  not the reliable Nanobot execution path.
- Excel And Tabular Data Policy: create a formatted `.xlsx` by default for
  scraped/extracted/exported tables; split real columns; add `Synthese` and
  `Controle qualite`; never leave everything in column A.
- Telegram Gateway And Supervisor: Telegram must not show plans, JSON tool
  calls, MCP names, hidden reasoning, or `write_todos`; stale duplicate pollers
  are cleaned by the admin supervisor path.
- Tool-noise prevention: `sendProgress=false`, `sendToolHints=false`, and
  `sequential_thinking.enabledTools=[]`.
- FIRE route: local Excel/data logic lives in `C:/Users/user/Desktop/FIRE`,
  especially `tools/excel_tools.py`, `scripts/excel_cli.py`, and `/data`.
- Software acquisition: for Windows app download/install/open requests, use
  `C:/AI/nanobot-omega/scripts/app_acquisition.py` and verify a real package,
  shortcut, AppID, process, or installer file before claiming success.
- Obsidian second brain: active vault
  `C:/Users/user/Mon Drive/DriveSyncFiles/ARCHITECTE_SYSTEM`,
  managed through `C:/AI/nanobot-omega/scripts/obsidian_second_brain.py` for
  capture, search, imports, daily notes, memory sync, and related links.
- Obsidian free Android sync route: because Autosync for Google Drive free mode
  only exposes `/DriveSyncFiles`, the PC/Nanobot vault was copied and switched
  from `C:/Users/user/Mon Drive/ARCHITECTE_SYSTEM` to
  `C:/Users/user/Mon Drive/DriveSyncFiles/ARCHITECTE_SYSTEM`. Obsidian desktop
  (`%APPDATA%/Obsidian/obsidian.json`) and Nanobot bridge config
  (`workspace/obsidian_bridge_config.json`) now point to this new path. The old
  folder remains as a safety copy; use the DriveSyncFiles path going forward.
- Obsidian capture hardening: `obsidian_second_brain.py` now maps shorthand
  folders like `pro`, `perso`, `projets`, `personnes`, and `lecture` to the
  canonical vault folders instead of creating stray top-level directories.
  `gemini_orchestrator_provider.py` also recognizes broader phrasing such as
  `ecrire dans Obsidian` so capture requests hit the direct Obsidian path
  instead of drifting into freeform model behavior.
- Claude filesystem access from FIRE: `C:/Users/user/Desktop/FIRE/scripts/ask_claude.py`
  now launches `claude -p` with automatic `--add-dir` entries for the current
  workspace, the user home, and every existing Windows drive root. This fixes
  false "outside my workspace" refusals for files such as Obsidian notes stored
  outside `C:/Users/user/Desktop/FIRE`. Override list if needed with env var
  `NANOBOT_CLAUDE_ADD_DIRS` (semicolon-separated paths).

## Scheduling And 2ememain Watch

- On 2026-04-23, the user asked to inspect scheduled/planned tasks and the
  free-object watch around Mouscron/7700.
- Claude Code has recipe-like scheduled-task folders:
  - `C:/Users/user/.claude/scheduled-tasks/nanobot-veille-2ememain-gratuit/SKILL.md`
  - `C:/Users/user/.claude/scheduled-tasks/nanobot-veille-lille-underground/SKILL.md`
  These describe intended behavior but had no `config.json`, `seen.json`,
  `health.json`, or active local logs in those folders.
- The actual reliable 2ememain execution path is Windows Task Scheduler:
  `NanobotVeille2ememain`, every 30 minutes, interactive user, hidden WScript.
- Execution chain:
  `C:/Users/user/Desktop/FIRE/scripts/nanobot_veille_run_hidden.vbs`
  -> `C:/Users/user/Desktop/FIRE/scripts/nanobot_veille_run.bat`
  -> `C:/AI/nanobot-omega/workspace/run_veille_and_notify.py`
  -> `C:/AI/nanobot-omega/workspace/run_veille_2ememain.py`
  -> Telegram Bot API token read from `C:/AI/nanobot-omega/config_omega.json`.
- Main state/config/log paths:
  - `C:/AI/nanobot-omega/workspace/veille_2ememain_config.json`
  - `C:/AI/nanobot-omega/workspace/veille_2ememain_history.json`
  - `C:/AI/nanobot-omega/logs/veille_direct.log`
- The task was failing silently because the scraper pointed to a missing Chrome
  path and the wrapper converted scraper failures into "0 nouveaute".
- Fix applied on 2026-04-23:
  - `run_veille_2ememain.py` now searches multiple Chrome/Chromium paths and
    can use Playwright Chromium.
  - `run_veille_and_notify.py` now returns failure when the scraper fails and
    logs more stderr.
  - `nanobot_veille_run_hidden.vbs` waits for the BAT and returns its exit code.
- Manual verification on 2026-04-23 at 08:19-08:20: scraper completed in
  about 86 seconds, found 3 new free ads, and Telegram send returned OK.
- Updated 2026-04-23: 2ememain watch radius is now 50 km around postcode 7700
  (`distanceMeters:50000`) for all configured categories. Telegram messages now
  include a deterministic professional opportunity comment: verdict, 0-10
  score, and practical resale/usefulness advice. Claude Code is not part of the
  operational 2ememain loop; its scheduled-task folders are only recipes unless
  explicitly rebuilt into local Nanobot/Windows tasks.
- Updated 2026-04-23: 2ememain Telegram notifications translate ad titles to
  French automatically through a cached translation step. Cache path:
  `C:/AI/nanobot-omega/workspace/veille_2ememain_translation_cache.json`.
  Messages show the French title first and the original Dutch title below when
  translation changes it. Example verified: "Gratis zetel en salontafel" ->
  "Canape et table basse gratuits".
- Added local control script:
  `C:/AI/nanobot-omega/workspace/veille_2ememain_control.py`.
  Commands: `status`, `pause`, `resume`, `50km`, `100km`, `run`. Nanobot's
  installed Telegram command router was patched for `/veille2 ...`; it becomes
  active after the Telegram gateway process reloads.
- Existing Nanobot cron job `fd8d11e2` ("Revision quotidienne de la veille")
  still runs daily at 09:00 Europe/Brussels as an LLM `agent_turn`; its quality
  has been inconsistent. Job `213ad967` for 2ememain is disabled and explicitly
  replaced by the Windows task.

## Software Acquisition

- On 2026-04-24, Nanobot was improved for Windows application acquisition so it
  stops claiming "downloaded" when it only opened a website.
- Operational helper: `C:/AI/nanobot-omega/scripts/app_acquisition.py`
  with commands:
  - `status <app>`
  - `ensure <app>`
  - `ensure <app> --open`
  - `open <app>`
- Preferred route for Windows desktop apps: `winget`.
- Website route: if given a direct installer URL, download the installer to
  `C:/Users/user/Downloads` and verify file existence + non-zero size. Basic
  HTML parsing can also try to find a Windows installer link on a product page.
- Play Store URLs are not a direct Windows install path; Nanobot must say this
  plainly instead of pretending success.
- Verified on 2026-04-24:
  - `app_acquisition.py status Obsidian` reported the Start Menu entry/AppID.
  - `app_acquisition.py ensure Obsidian` returned installed/verified.
  - `app_acquisition.py open Obsidian` launched the app and process/window
    verification succeeded.
- `gemini_orchestrator_provider.py` now fast-paths natural-language requests to
  download/install/open applications through `app_acquisition.py` before falling
  back to normal LLM behavior.

## Scraping Champion

- On 2026-04-24, Nanobot gained a dedicated scraping engine:
  `C:/AI/nanobot-omega/scripts/scraping_champion.py`.
- Main behavior:
  - fetch with browser-like HTTP headers via `requests`;
  - detect weak/JS-heavy pages and fall back to Playwright automatically;
  - extract article text, metadata, links, HTML tables, repeated listing/card
    items, contacts, and JSON-LD when present;
  - save durable artifacts under `C:/Users/user/Desktop/Nanobot_Scrapes`;
  - create a real `.xlsx` when tables or repeated items exist, reusing the
    local Excel formatting policy.
- Natural-language scraping requests are now routed by
  `C:/AI/nanobot-omega/gemini_orchestrator_provider.py` when the user says
  things like scrape/extract/crawl a URL or website.
- FIRE local routing also knows this capability through:
  - `C:/Users/user/Desktop/FIRE/tools/scrape_tools.py`
  - `C:/Users/user/Desktop/FIRE/scripts/router.py`
  so prompts like "scrape https://... en excel" go to the local scraper instead
  of a generic LLM answer.
- Verified on 2026-04-24:
  - `https://books.toscrape.com/` -> requests path, 20 repeated items, `.xlsx`
    created.
  - `https://quotes.toscrape.com/js/` -> automatic Playwright fallback, 11
    repeated items, `.xlsx` created.
- Artifact set:
  - markdown report
  - json
  - raw html
  - `.xlsx` when data is tabular or listing-like
- Important rule: do not pretend data was scraped from a page that only had a
  website opened. The route must actually fetch/render and write artifacts.

## Obsidian Second Brain

- On 2026-04-24, Obsidian was upgraded from "installed app" to an active
  second-brain surface for the user and Nanobot.
- Canonical bridge:
  `C:/AI/nanobot-omega/scripts/obsidian_second_brain.py`
- Canonical config:
  `C:/AI/nanobot-omega/workspace/obsidian_bridge_config.json`
- Active vault detected and reused:
  `C:/Users/user/Mon Drive/ARCHITECTE_SYSTEM`
- Nanobot bootstrap created or updated:
  - `C:/Users/user/Mon Drive/ARCHITECTE_SYSTEM/00_Commandement/Hub_Nanobot_Obsidian.md`
  - `C:/Users/user/Mon Drive/ARCHITECTE_SYSTEM/99_Système/Nanobot/Mode_Emploi_Nanobot.md`
  - `C:/Users/user/Mon Drive/ARCHITECTE_SYSTEM/99_Système/Nanobot/Memoire/Memoire_Nanobot.md`
  - `C:/Users/user/Mon Drive/ARCHITECTE_SYSTEM/99_Système/Nanobot/Memoire/Snapshots_Nanobot.md`
  - `C:/Users/user/Mon Drive/ARCHITECTE_SYSTEM/99_Système/Nanobot/Relations/Relations_Nanobot.md`
- Vault capabilities now verified locally:
  - `bootstrap`
  - `status`
  - `open`
  - `capture`
  - `daily`
  - `search`
  - `import` for markdown/text, images with OCR, and PDFs with extracted text
  - `sync-memory`
- Core Obsidian plugins were enabled for stronger knowledge work:
  global search, switcher, graph, backlinks, outgoing links, tag pane, page
  preview, note composer, slash commands, outline, word count, workspaces, and
  file recovery.
- Updated 2026-04-24: each new Obsidian capture is now auto-classified into
  `pro`, `perso`, `lecture`, `personnes`, or `projets`, then written to the
  corresponding directory:
  - `01_Projets_Actifs/En_Cours/Captures_Nanobot`
  - `02_Domaines/Professionnel/Nanobot`
  - `02_Domaines/Personnel/Nanobot`
  - `02_Domaines/Personnes/Nanobot`
  - `04_Bibliothèque/Lectures_Nanobot`
  Explicit tags still override the automatic choice when present.
- Verification on 2026-04-24:
  - Created a strategic note in `99_Système/Nanobot/Inbox`.
  - Appended multiple Nanobot captures into the daily journal note.
  - Imported an image and extracted OCR text into markdown.
  - Imported a PDF and extracted page text into markdown.
  - Opened the Obsidian hub note through the vault URI route.
  - Classification heuristics were tested across all five categories and then
    hardened to avoid false routing when the note merely lists the category
    names themselves.
- Updated 2026-04-24: the vault was elevated into a whole-life "Life OS" with
  a main cockpit note at
  `C:/Users/user/Mon Drive/ARCHITECTE_SYSTEM/00_Commandement/Cockpit_de_Vie.md`.
  Nanobot now treats this as the primary human entry point.
- Life OS structure created or reinforced:
  - `00_Commandement/Revues`
  - `02_Domaines/Famille`
  - `02_Domaines/Finance`
  - `02_Domaines/Sante`
  - `02_Domaines/Maison`
  - `02_Domaines/Administratif`
  - `02_Domaines/Personnes`
  - `03_Arsenal_Technique/Playbooks`
  - `04_Bibliotheque/Formations`
  - `04_Bibliotheque/References`
  - `05_Archives/Projets_Termines`
- Pivot notes and dashboards created for whole-life steering:
  - `00_Commandement/Cockpit_de_Vie.md`
  - `00_Commandement/Revues/Guide_Revues.md`
  - `01_Projets_Actifs/Dashboard_Projets.md`
  - `02_Domaines/Professionnel/Dashboard_Professionnel.md`
  - `02_Domaines/Personnel/Dashboard_Personnel.md`
  - `02_Domaines/Famille/Dashboard_Famille.md`
  - `02_Domaines/Finance/Dashboard_Finance.md`
  - `02_Domaines/Sante/Dashboard_Sante.md`
  - `02_Domaines/Maison/Dashboard_Maison.md`
  - `02_Domaines/Administratif/Dashboard_Administratif.md`
  - `02_Domaines/Personnes/Dashboard_Personnes.md`
  - `04_Bibliotheque/Dashboard_Bibliotheque.md`
- Reusable templates were added for life operations, including finance,
  people, project launch, reading, daily protocol, weekly review, and monthly
  review.
- Updated 2026-04-24: Obsidian now has a stronger wiki-linking layer. Command
  `python C:/AI/nanobot-omega/scripts/obsidian_second_brain.py relations --all`
  retisses the whole vault by adding managed `Hubs utiles` and `Passerelles
  utiles` sections to notes, plus a richer `Relations_Nanobot.md` map. The
  provider also routes natural-language requests about linking/relations in
  Obsidian to this flow.
- `gemini_orchestrator_provider.py` now fast-paths Obsidian requests for vault
  status, open, search, capture, import, and memory sync through the bridge
  instead of treating them as generic app actions.

## Core Operating Changes

- The user explicitly wants Nanobot to act, verify, and report concise results,
  not repeat long plans or expose internal tool calls.
- `C:/AI/nanobot-omega/AGENT_V2.md` and `MISSION_YOLO.md` are the canonical
  execution protocol: goal, short private plan, action, verification, repair,
  final result.
- Telegram replies must stay short and operational. Do not show JSON tool calls,
  MCP tool names, hidden reasoning, `write_todos`, or raw tool arguments.
- `config_omega.json` has `sendProgress=false` and `sendToolHints=false`.
- The `sequential_thinking` MCP server is intentionally left with
  `enabledTools=[]` because it was leaking reasoning/tool-noise into Telegram.
- `gemini_orchestrator_provider.py` was hardened to strip tool-call plumbing
  from user-visible text while still allowing internal tool execution.

## Excel And Tabular Data Policy

- Any scraped, extracted, cleaned, or exported tabular data should produce a
  formatted local `.xlsx` as the main deliverable unless the user explicitly
  asks for CSV only.
- Never deliver a workbook where delimited rows are stuck in column A.
- Every generated or repaired workbook must include:
  - real columns;
  - frozen header;
  - filters/table styling;
  - readable widths and formats;
  - `Synthese` sheet;
  - `Controle qualite` sheet.
- CSV can be provided as a secondary artifact when useful.
- Main implementation: `C:/Users/user/Desktop/FIRE/tools/excel_tools.py`.
- CLI: `C:/Users/user/Desktop/FIRE/scripts/excel_cli.py`.
- Router: Excel requests are routed to the local Excel agent before Google
  Sheets via `C:/Users/user/Desktop/FIRE/scripts/router.py`.
- Front tool: `C:/Users/user/Desktop/FIRE/src/routes/data/+page.svelte`.
- Verification command examples:
  - `python -m unittest tests.test_excel_tools tests.test_google_tools`
  - `python scripts/excel_cli.py analyze C:/path/file.xlsx`

## FIRE App Improvements

- The FIRE workspace now has a local Excel/data workshop at `/data`.
- It can paste tabular data, detect delimiters, preview columns, score quality,
  flag suspicious URLs/emails/numbers, count duplicates, export CSV, and generate
  an Excel CLI command.
- Navigation and command palette include the Excel/data workshop.
- `/data` is public even when Supabase auth is configured.

## Telegram Gateway And Supervisor

- A bad Telegram behavior was diagnosed: repeated plans and visible tool calls.
- A duplicate Telegram poller caused `Conflict: terminated by other getUpdates
  request`.
- The stale elevated poller was cleaned through the admin supervisor path.
- `C:/AI/nanobot-omega/Run-NanobotOmegaSupervisor.ps1` now runs stale poller
  cleanup on startup.
- Cleanup script: `C:/AI/nanobot-omega/scripts/Stop-StaleTelegramNanobot.ps1`.
- Expected healthy behavior: one active Nanobot gateway tree, no recurring
  Telegram polling conflict, no visible tool-call hints to the user.

## Google, Notion, MCP, And Tools

- Configured MCP families may include filesystem, memory, google_workspace, and
  notion. Use only tools that are actually registered at runtime.
- `google_workspace` MCP includes Excel-related tools as a secondary route, but
  local `.xlsx` generation should use the local Excel subsystem first.
- Notion MCP is available through the configured starter script when auth is
  valid.
- If an MCP tool is missing, diagnose capabilities/logs instead of claiming the
  tool does not exist.

## User Preference Memory

- User prefers French, direct action, exact file paths, and real verification.
- Desktop is the default destination for deliverables unless another path is
  specified.
- The user dislikes fake progress, repeated planning, apologetic loops, and
  internal tool chatter.
- For legal/safety-sensitive scraped software lists, classify and enrich data
  safely; do not provide piracy links or instructions.

## Obsidian Time Command Layer

- The active Obsidian/Nanobot vault is
  `C:/Users/user/Mon Drive/DriveSyncFiles/ARCHITECTE_SYSTEM`.
- Time management is a command layer, not a life domain:
  `00_Commandement/Temps/`.
- Main entry point:
  `00_Commandement/Temps/Dashboard_Temps.md`.
- Core files:
  `Aujourd_hui.md`, `Cette_Semaine.md`, `Prochaines_Actions.md`,
  `En_Attente.md`, `Echeances.md`, `Incubateur.md`, `Horizons.md`,
  `Rituels_Temps.md`.
- Active cycle files created only when useful:
  `Semaines/2026-W17.md`, `Mois/2026-04.md`,
  `Trimestres/2026-Q2.md`, `Annees/2026.md`.
- Templates live in `99_Système/Templates/Temps/`.
- `scripts/obsidian_second_brain.py` now treats `Dashboard Temps` as a central
  relations hub and can route future captures into time lists:
  next actions, waiting, deadlines, incubator, today/week when relevant.

## Google Workspace Local MCP And CLI

- Google Workspace is now available directly inside `C:/AI/nanobot-omega`.
- OAuth files:
  `C:/AI/nanobot-omega/configs/google_credentials.json` and
  `C:/AI/nanobot-omega/configs/google_token.json`.
- Main JSON CLI:
  `python C:/AI/nanobot-omega/scripts/google_workspace_cli.py --json ...`
- Local Python MCP server:
  `C:/AI/nanobot-omega/scripts/google_workspace_mcp.py`.
- `Start-GoogleWorkspaceMcp.ps1` now launches the local Python MCP server
  instead of depending on the external npm `google-workspace-mcp` server.
- Exposed MCP tool families include Gmail read/send/modify, Calendar, Drive,
  Docs, Sheets, Tasks, Contacts, and `google_natural`.
- Verified on 2026-04-26 with real Google Docs and Sheets create/write/read/trash
  tests.
- Gmail modify is now enabled. Verified on 2026-04-26 by creating and deleting
  the temporary label `Nanobot_Test_20260426_003747`, without touching real
  emails.
- Durable guide:
  `C:/AI/nanobot-omega/workspace/GOOGLE_WORKSPACE_CAPABILITIES.md`.

## Radical Capability Upgrade

- Added `gmail.modify` to the Google OAuth scope list.
- Gmail action code now supports labels, create/delete user label, mark
  read/unread, archive, move/classify under label, trash, untrash, and permanent
  delete when explicitly requested.
- Google Workspace MCP now exposes 44 tools, including 13 Gmail tools.
- Reauthorization via `setup_google_auth.py --force` is complete for
  `monagenda.be@gmail.com`; token is valid, has refresh token, and includes
  `gmail.modify`.
- Added proactive intelligence module:
  `C:/AI/nanobot-omega/scripts/proactive_intel.py`.
- Added desktop intelligence module:
  `C:/AI/nanobot-omega/scripts/desktop_intel.py`, with `.xlsx` export including
  `Synthese` and `Controle qualite`.
- Added resilience orchestrator:
  `C:/AI/nanobot-omega/scripts/resilience_orchestrator.py`.
- Added ad hoc agent forge:
  `C:/AI/nanobot-omega/scripts/agent_forge.py`.
- Verification on 2026-04-26:
  - Python compile passed for Google auth/CLI/MCP and the four radical modules.
  - `resilience_orchestrator.py doctor-google` passed and wrote a report in
    `C:/AI/nanobot-omega/workspace/resilience_reports`.
  - Desktop intelligence exported
    `C:/AI/nanobot-omega/workspace/desktop_windows_snapshot.xlsx`.
  - Agent forge created and ran the test agent `test_probe`.
- Durable guide:
  `C:/AI/nanobot-omega/workspace/RADICAL_CAPABILITIES.md`.

## Startup Capability Awareness

- Added an automatic startup context generator:
  `C:/AI/nanobot-omega/scripts/build_startup_context.py`.
- It writes:
  - `C:/AI/nanobot-omega/workspace/NANOBOT_STARTUP_CONTEXT.md`
  - `C:/AI/nanobot-omega/workspace/NANOBOT_STARTUP_CONTEXT.json`
- The startup context is regenerated by:
  - `C:/AI/nanobot-omega/Run-NanobotOmegaSupervisor.ps1`
  - `C:/AI/nanobot-omega/Start-NanobotTelegramGateway.ps1`
- `gemini_orchestrator_provider.py` now injects
  `NANOBOT_STARTUP_CONTEXT.md` into the system prompt on every conversation,
  alongside `MISSION_YOLO.md` and `AGENT_V2.md`.
- This gives Nanobot a compact live map of its real powers at each conversation:
  Obsidian vault, Google auth/scopes, Gmail modify, MCP tool count, modules,
  fallback routes, Excel policy, Telegram-noise policy, ad hoc agents created
  under `workspace/ad_hoc_agents`, and must-read memory files.
- Important: before saying a tool or route is unavailable, Nanobot must trust
  this startup context first, then inspect the durable guides or run diagnostics.

## Telegram And Gmail Routing Repair

- Fixed on 2026-04-26 after Nanobot repeatedly answered with Gmail inbox
  summaries when Amor was actually asking to switch/disconnect a wrong web
  account.
- Root cause: `tools/google_tools.py` treated broad words like `mail`, `gmail`,
  `email`, or Google capability reports as direct Gmail requests. Because Google
  Workspace routing runs early in the orchestrator, this bypassed the normal
  assistant response path.
- New rule: Gmail/Google Workspace routing requires a real Google action or
  read/search intent. Browser/account-login phrases such as `mauvais compte`,
  `bon compte`, `adresse mail`, `deconnecte`, `reconnecte`, `ouvre le site`, or
  pasted capability/status reports must not trigger Gmail listing.
- Added regression tests:
  `C:/AI/nanobot-omega/scripts/test_google_prompt_routing.py`.
- Verified with:
  `python C:/AI/nanobot-omega/scripts/test_google_prompt_routing.py`
  returning `google prompt routing ok: 9 cases`.
- Telegram non-response cause: two Nanobot Telegram pollers were running at the
  same time, causing Telegram `getUpdates` conflicts.
- `scripts/Stop-StaleTelegramNanobot.ps1` now performs durable stale-poller
  cleanup, logs to `logs/stale-telegram-cleanup.log`, and is run by
  `Run-NanobotOmegaSupervisor.ps1` at startup.
- `Run-NanobotOmegaSupervisor.ps1` also has stricter process detection so shell
  diagnostic commands are not mistaken for live Nanobot gateways.
- After cleanup, the stale elevated poller tree was stopped, Google Workspace MCP
  connected with 44 tools, the Nanobot agent loop started, and no new Telegram
  `Conflict` lines appeared in `logs/telegram-gateway.err.log`.

## Maintenance 2026-04-26 par Codex

- Backup complet de maintenance cree dans
  `C:/AI/nanobot-omega/backups/maintenance-20260426-054302/`.
- Fichiers coeur Gemini proteges non modifies:
  `gemini_cli_orchestrator.py`, `instances.json`, `instances_swarm.json` et
  `gemini-light-homes/`.
- P1: le raccourci "ouvre/lance ton navigateur" ne se declenche plus sur les
  longs prompts de mission. Il est limite aux messages courts, sans retour
  ligne, sans URL et sans bloc code/JSON.
- P2: gateway Telegram durci avec `state/gateway.lock`, endpoint admin
  `/admin/health`, endpoint `/admin/sessions/reset`, reset webhook au boot,
  nettoyage des pollers fantomes et cleanup periodique par le superviseur.
- P3: prompt tools renforce, retries "outil introuvable" passes a 5, parsing
  de prose vers `tool_call` ajoute, et les retries invalides ne sont plus emis
  vers l'utilisateur avant la reponse finale.
- P4: backend par defaut laisse inchange selon la decision d'Amor; le boot logue
  maintenant `Backend actif: ... fallback: ...`.
- P5/P8: audit runtime des tools cree dans
  `C:/AI/nanobot-omega/health/tools_audit.json`; Arsenal clarifie les outils
  natifs (`browser_automation`, `desktop_automation`, `ocr`,
  `vision_analyze_image`) versus MCP.
- Chrome CDP: `modules/chrome_launcher.ps1` a ete repare (mojibake/quote
  PowerShell), et `-Status` confirme CDP actif sur le port 9222.
- P6: token Google rafraichi et valide avec `gmail.modify`; tache planifiee
  `NanobotGoogleTokenRefresh` ajoutee pour refresh hebdomadaire preventif.
- P7: garde sessions ajoutee: detection de boucles d'assistant, archive au-dela
  de 1 MB, conservation des 50 derniers tours et reset admin HTTP.
- P9: `modules/deploy_skills.py --check` verifie les 4 skills sur les 10
  instances Gemini CLI sans modifier les homes.
- P10: self-heal corrige: detection process + age, gateway via admin/lock, logs
  seulement sur changement d'etat. Watchdog relance et etat final OK.
- Verification cle: Gmail direct via Nanobot retourne `MAIL_OK` sans exposer de
  prose "outil introuvable"; Telegram n'a plus de nouveaux conflits apres
  `2026-04-26 06:21:49`.
- Limite restante: Windows refuse de changer l'intervalle `NanobotSelfHeal` de
  10 min a 5 min sans elevation/mot de passe admin interactif.

## Practical Rule

When in doubt, inspect local files first, choose the existing Nanobot/FIRE route,
act, verify, then answer with: what was done, where it is, what was verified, and
only real blockers.
