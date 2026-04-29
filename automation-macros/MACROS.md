# MACROS.md — Bibliotheque d'Automation Industrielle

Repertoire : `C:\AI\nanobot-omega\automation-macros\`

Ces macros remplacent la generation de code Playwright ad-hoc par des outils durables.
Appeler directement via `exec()` au lieu de coder a chaque tour.

---

## 1. handle-cookies.js — Bypass RGPD/Cookies Universel

**But** : Detecte et clique automatiquement sur les bannieres cookies.

**Frameworks supportes** : Google Consent, YouTube, LinkedIn, OneTrust, Didomi,
Cookiebot, Quantcast, Axeptio, TrustArc + detection generique.

### Utilisation Playwright MCP

```
browser_navigate url:"https://www.example.com"
browser_evaluate expression:"<contenu de handle-cookies.js>"
browser_snapshot
```

### Utilisation rapide (une seule commande)

Apres avoir navigate sur une page avec banniere cookies :
```
browser_evaluate file:"C:\AI\nanobot-omega\automation-macros\handle-cookies.js"
```

### Retour

```json
{ "handled": true, "method": "google-consent", "domain": "youtube.com", "attempts": ["google-consent"] }
```

- `handled: true` = banniere cliquee avec succes
- `handled: false` = aucune banniere detectee ou clic echoue
- `method` = strategie qui a fonctionne

### Quand l'utiliser

- TOUJOURS apres `browser_navigate` sur un site jamais visite
- Si un `browser_snapshot` montre une banniere cookies bloquant le contenu

---

## 2. fast-scrape.py — Extracteur de Contenu Pur

**But** : Convertit une page web en Markdown propre, sans pub ni bruit.
Minimise les tokens consommes quand le contenu est injecte dans un prompt.

### CLI

```bash
# Scrape standard
python C:\AI\nanobot-omega\automation-macros\fast-scrape.py "https://example.com"

# Limiter a 5000 caracteres (economie tokens)
python C:\AI\nanobot-omega\automation-macros\fast-scrape.py "https://example.com" --max-chars 5000

# Texte brut (pas de Markdown)
python C:\AI\nanobot-omega\automation-macros\fast-scrape.py "https://example.com" --raw

# Juste les metadonnees
python C:\AI\nanobot-omega\automation-macros\fast-scrape.py "https://example.com" --meta-only

# Depuis un fichier HTML local
python C:\AI\nanobot-omega\automation-macros\fast-scrape.py "C:\path\to\page.html"
```

### Import Python

```python
from fast_scrape import scrape_url

result = scrape_url("https://example.com", max_chars=3000)
print(result["title"])      # Titre
print(result["markdown"])   # Contenu Markdown propre
print(result["word_count"]) # Nombre de mots
```

### Sortie

```
# Titre de la Page
> Meta description

_Source: https://example.com | 842 mots | 5203 chars_

---

## Section 1
Contenu nettoye...
```

### Ce qui est supprime

- `<script>`, `<style>`, `<nav>`, `<footer>`, `<aside>`, `<iframe>`
- Elements avec classes ad-, ads-, banner, sponsor, cookie, popup, sidebar
- Commentaires HTML
- Attributs aria-hidden

---

## 3. youtube-control.py — Controleur YouTube Avance

**But** : Tout ce qu'il faut pour YouTube sans ecrire de Playwright.

### Commandes CLI

```bash
# Obtenir l'URL de recherche (la plus rapide)
python youtube-control.py url "echecs kasparov"
# -> https://www.youtube.com/results?search_query=echecs+kasparov

# Recherche complete avec procedure Playwright
python youtube-control.py search "echecs kasparov"

# Metadonnees d'une video (sans navigateur, via oEmbed API)
python youtube-control.py metadata "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# URL tendances
python youtube-control.py trending
python youtube-control.py trending music

# Generer le JS pour bypass popups YouTube
python youtube-control.py inject-bypass

# Generer le JS pour rechercher
python youtube-control.py inject-search "cours echecs debutant"

# Generer le JS pour controler le player
python youtube-control.py inject-control play
python youtube-control.py inject-control pause
python youtube-control.py inject-control mute
python youtube-control.py inject-control skip30
python youtube-control.py inject-control status

# Generer le JS pour extraire les resultats de recherche
python youtube-control.py inject-results
```

### Actions Player Disponibles

| Action | Effet |
|--------|-------|
| `play` | Lancer la lecture |
| `pause` | Mettre en pause |
| `mute` | Couper le son |
| `unmute` | Remettre le son |
| `fullscreen` | Plein ecran |
| `skip30` | Avancer de 30 secondes |
| `back10` | Reculer de 10 secondes |
| `speed2x` | Vitesse x2 |
| `speed1x` | Vitesse normale |
| `status` | Etat complet du player |

### Procedure Type : Chercher et Lancer une Video

```
1. exec("python youtube-control.py url echecs kasparov")  -> recupere l'URL
2. browser_navigate url:"<URL obtenue>"
3. browser_evaluate expression:"<output de inject-bypass>"
4. browser_snapshot
5. browser_click ref:[premiere video]
6. browser_evaluate expression:"<output de inject-bypass>"  (re-bypass apres navigation)
7. browser_snapshot (verifier que la video joue)
```

### Procedure Rapide : Metadonnees Sans Navigateur

```
exec("python C:\AI\nanobot-omega\automation-macros\youtube-control.py metadata dQw4w9WgXcQ")
```
Retourne titre, chaine, thumbnail, dimensions — sans ouvrir Chrome.

---

## 4. omega-fix.ps1 — Self-Healing (dans scripts/)

**But** : Auto-reparation du systeme en une commande.

### Commandes

```bash
# Diagnostic sans toucher a rien
exec("powershell -ExecutionPolicy Bypass -File C:\\AI\\nanobot-omega\\scripts\\omega-fix.ps1 -DiagOnly")

# Reparation automatique
exec("powershell -ExecutionPolicy Bypass -File C:\\AI\\nanobot-omega\\scripts\\omega-fix.ps1")

# Reparation agressive (kill tout)
exec("powershell -ExecutionPolicy Bypass -File C:\\AI\\nanobot-omega\\scripts\\omega-fix.ps1 -Aggressive")
```

### Ce que ca repare

| Probleme | Action |
|----------|--------|
| Chrome orphelins (CDP 9222 mort) | Kill des processus lies au profil nanobot |
| Lock files residuels | Suppression si Chrome ne tourne pas |
| pwsh/cmd fantomes (>2h, sans fenetre) | Termination |
| .gemini/tmp sature (>50MB ou >500 fichiers) | Purge des fichiers >24h |
| 8+/10 instances blacklistees | Reset automatique |
| Blacklists obsoletes (>24h) | Reset cible |
| Logs satures (>500KB) | Rotation avec backup |
| Preferences Chrome derivees | Re-application notifications/popups bloques |
| Extensions problematiques reactives | Re-desactivation |

### Quand l'utiliser

- Quand un outil MCP echoue (browser_navigate timeout, etc.)
- Quand Chrome refuse de se lancer
- Avant une session longue importante
- En mode watchdog automatique (cron)

---

## CHEAT SHEET — Commandes Rapides

| Situation | Commande |
|-----------|----------|
| Site avec cookies | `browser_evaluate` + handle-cookies.js |
| Extraire contenu page | `exec("python fast-scrape.py URL")` |
| Chercher YouTube | `exec("python youtube-control.py url QUERY")` |
| Metadata video | `exec("python youtube-control.py metadata ID")` |
| Bypass popup YouTube | `browser_evaluate` + inject-bypass |
| Controle player | `browser_evaluate` + inject-control play/pause |
| Systeme bloque | `exec("powershell ... omega-fix.ps1")` |
| Diagnostic systeme | `exec("powershell ... omega-fix.ps1 -DiagOnly")` |
| Flush contexte | `exec("python context_flush.py --force")` |
