# NANOBOT — Capacités navigateur & web

> Source de vérité unique pour ce que NanoBot peut faire avec le navigateur,
> Playwright, le scraping et les veilles. En cas de conflit, **cette note prime**.

Dernière mise à jour : 2026-04-29

---

## 1. Stack technique

| Composant | Chemin / version | Statut |
|---|---|---|
| **Chrome (production)** | `C:/Program Files/Google/Chrome/Application/chrome.exe` | ✅ Installé |
| **Profil Chrome partagé** | `C:/AI/nanobot-omega/shared-browser/chrome-profile/` | ✅ Persistant (sessions, cookies) |
| **Lanceur Chrome avec onglet** | `C:/AI/nanobot-omega/Open-Shared-Nanobot-Browser.bat URL` | ✅ Anti-timeout, ouvre onglet (pas fenêtre) |
| **Playwright Python** | `pip install playwright` | ✅ |
| **Playwright Chromium** | `C:/Users/user/AppData/Local/ms-playwright/chromium-1208/` | ✅ Headless |
| **Playwright Firefox** | `firefox-1509` | ✅ Disponible |
| **scraping_champion.py** | `C:/AI/nanobot-omega/scripts/scraping_champion.py` | ✅ HTTP + Playwright fallback |
| **CDP debug port** | 9222 (via `Open-Shared-Nanobot-Browser.bat`) | ✅ Pour `browser_automation` natif |

---

## 2. Stratégie de choix de méthode (impératif)

NanoBot **doit** choisir la méthode la plus simple qui répond au besoin :

| Mission | Méthode |
|---|---|
| Page statique simple, pas de JS | `requests` + BeautifulSoup → **`scraping_champion.py`** |
| Page JS-heavy, contenu dynamique, pagination | **Playwright headless** (auto via `scraping_champion.py`) |
| Login utilisateur requis ou session humaine existante | **Chrome visible** via `Open-Shared-Nanobot-Browser.bat` + `browser_automation` |
| Action visible côté user | **Chrome visible** (jamais Playwright headless) |
| Veille / surveillance régulière | **Windows Task Scheduler** + script déterministe (zéro LLM dans le hot path) |
| API officielle dispo et autorisée | **API directe** (préférée à tout) |
| OCR sur image / capture écran | **`ocr` tool natif** Nanobot |
| Élément non détectable autrement | `desktop_automation` + OCR (dernière option) |

⚠️ **Ne JAMAIS utiliser** Playwright headless quand l'utilisateur veut **voir** quelque chose à l'écran. Utiliser Chrome visible via le shared profile.

---

## 3. Capacités opérationnelles (par tool)

### scraping_champion.py
```cmd
python C:/AI/nanobot-omega/scripts/scraping_champion.py scrape "URL" [--out path] [--render]
```
- Tente `requests` + BeautifulSoup d'abord
- Bascule auto sur **Playwright** si page JS-heavy / signal faible
- Extrait : titre, texte article, **tables**, **listings cards**, contacts (email/tel), prix, JSON-LD, liens
- Output : `~/Desktop/Nanobot_Scrapes/<slug>/` avec `report.md`, `data.json`, `raw.html`, **`data.xlsx`** (avec `Synthese` + `Controle qualite`)
- Vérification incluse : nombre items, route utilisée, screenshot si nécessaire

### Open-Shared-Nanobot-Browser.bat
```cmd
"C:/AI/nanobot-omega/Open-Shared-Nanobot-Browser.bat" "https://google.com/search?q=SUJET"
```
- **TOUJOURS** ouvrir un onglet dans le profil partagé (pas une nouvelle fenêtre)
- Sessions persistées : login Google/Notion/2ememain restent connectés
- CDP port 9222 actif → `browser_automation` peut s'attacher

### browser_automation (tool natif Nanobot)
- Click, type_text, fill_form, get_page_text, screenshot, wait_for_selector
- Marche **sur le Chrome déjà ouvert** via CDP 9222
- Vérification : screenshot après chaque action critique

### desktop_automation + OCR (fallback ultime)
- Quand le DOM ne donne pas accès à un élément (Canvas, popup système, app native)
- Lent, fragile — à éviter sauf nécessité

---

## 4. Veilles & tâches récurrentes

| Tâche Windows | Fréquence | Rôle |
|---|---|---|
| **NanobotVeille2ememain** | 30 min | Scraper 2ememain + notif Telegram (zéro LLM) |
| **NanobotSelfHeal** | 10 min | Beacon santé global |
| **NanobotLogRotate** | quotidien 03:00 | Rotation logs |
| **NanobotBackup** | quotidien 03:15 | ZIP fichiers critiques |
| **NanobotGoogleTokenRefresh** | hebdo | Refresh OAuth Google |
| **NanobotOmegaSupervisorAdmin** | continu (Running) | Gateway Telegram |
| **NanobotWatchdogAdmin** | continu (Running) | Watchdog Ollama |
| **NanobotDashboardAdmin** | sur trigger | Dashboard local |
| **NanobotFileIndexAdmin** | sur trigger | Index fichiers |

Détails veille 2ememain : voir [NANOBOT_2EMEMAIN_WATCH.md](NANOBOT_2EMEMAIN_WATCH.md).

---

## 5. Règles de sécurité

- ❌ Ne JAMAIS contourner CAPTCHA, paywall, restrictions site
- ❌ Ne JAMAIS publier / acheter / vendre / envoyer message sans confirmation explicite
- ❌ Ne JAMAIS modifier compte utilisateur sans confirmation
- ❌ Ne PAS spammer : respecter délais raisonnables (≥ 2s entre requêtes même domaine)
- ❌ Ne PAS stocker secrets en clair côté logs/notes
- ✅ Vérifier APRÈS chaque action critique (URL finale, élément visible, fichier téléchargé, log écrit, notif envoyée)
- ✅ Pour action irréversible : dry-run d'abord, puis confirmation user, puis exécution

---

## 6. Diagnostic rapide

```cmd
python C:/AI/nanobot-omega/scripts/nanobot_self_check.py check
```

Vérifie en cascade : Chrome, Playwright, scraping_champion, NanobotVeille2ememain (état + logs), gateway, ollama, OAuth.

---

## 7. Routes par type de demande utilisateur

| L'utilisateur dit … | NanoBot doit faire |
|---|---|
| "Ouvre ce site" | `Open-Shared-Nanobot-Browser.bat URL` |
| "Cherche sur Google X" | `Open-Shared-Nanobot-Browser.bat https://google.com/search?q=X` |
| "Scrape ce site / extrais ce tableau" | `python scraping_champion.py scrape URL` |
| "Lis le contenu de cette page" | `requests.get` ou `scraping_champion` selon JS |
| "Surveille cette page" / "Préviens-moi si nouveauté" | Créer une veille (Task Scheduler + script déterministe) |
| "Cherche des annonces gratuites 2ememain" | `python veille_2ememain_control.py run` |
| "Vérifie ta veille 2ememain" | `python nanobot_self_check.py check` puis `python veille_2ememain_control.py status` |
| "Redémarre la veille" | `python veille_2ememain_control.py resume` (admin requis) |
| "Remplis ce formulaire / clique ici" | `Open-Shared-Nanobot-Browser.bat URL` puis `browser_automation` via CDP 9222 |
| "Compare ces 2 pages" | Ouvrir 2 onglets via `browser_automation`, extraire chaque, diff |
