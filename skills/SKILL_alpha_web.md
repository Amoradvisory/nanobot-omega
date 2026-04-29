---
name: alpha-web
description: "Automatisation web de niveau expert. Navigation rapide, manipulation DOM, gestion d'onglets, anti-boucle, extraction structuree, sessions persistantes. Declencheurs: cherche sur le web, ouvre un site, extrais les donnees, remplis le formulaire, automatise la page."
---

# Alpha-Web — Competence Web de Niveau Expert

Tu es un operateur web expert. Tu navigues vite, tu extrais proprement, tu ne tournes jamais en rond.

---

## Principe Cardinal : UN SEUL Chrome, PLUSIEURS onglets

**JAMAIS ouvrir une nouvelle instance Chrome.** Utiliser le Chrome agent existant (CDP 9222).

```
# Verifier Chrome agent
python C:/AI/nanobot-omega/modules/pc_master.py tabs

# Ouvrir une URL dans un NOUVEL ONGLET (pas une nouvelle fenetre)
python C:/AI/nanobot-omega/modules/pc_master.py url "https://example.com"
```

Si Chrome agent n'est pas actif :
```powershell
& "C:/AI/nanobot-omega/modules/chrome_launcher.ps1"
```

---

## Strategie de Navigation (par priorite de rapidite)

### Niveau 1 — Fetch Direct (le plus rapide, pas de navigateur)
Pour : pages statiques, articles, documentation, APIs.
```
# Via MCP fetch
fetch → url: "https://example.com/api/data"
```
**Utiliser en premier** sauf si la page necessite JavaScript.

### Niveau 2 — Search MCP (recherche rapide sans navigateur)
Pour : trouver une info, obtenir des URLs pertinentes.
```
# Via MCP search (DuckDuckGo)
search → query: "python datetime format 2026"
```

### Niveau 3 — Playwright MCP (navigation complete)
Pour : pages dynamiques, formulaires, sites necessitant JS.
```
# Via MCP browser-automation (Playwright)
browser_navigate → url: "https://example.com"
browser_snapshot  # Voir l'etat de la page (plus rapide que screenshot)
browser_click → selector: "[data-testid='submit']"
```

### Niveau 4 — Chrome CDP (profil persistant, sessions, cookies)
Pour : sites ou tu es deja connecte, sessions longues.
```python
python C:/AI/nanobot-omega/modules/pc_master.py url "https://gmail.com"
```

---

## Anti-Boucle (NON NEGOCIABLE)

Avant CHAQUE action web, enregistrer dans le detecteur :
```python
from modules.resilient_engine import detect_loop
result = detect_loop("navigate:google.com/search?q=meteo")
if result["looping"]:
    # STOP — changer de strategie immediatement
    # Suivre result["suggestion"]
```

### Regles anti-boucle :
1. **3 memes recherches Google** → STOP. Reformuler ou utiliser un autre moteur.
2. **3 memes clics** → STOP. L'element n'est pas la. Screenshot, analyser, cibler autrement.
3. **3 redirections** → STOP. Le site bloque ou redirige. Essayer fetch direct.
4. **Page vide/erreur** → Un seul retry. Si echec, documenter et passer a une autre source.

---

## Extraction de Donnees

### Texte structure
```
# Playwright snapshot (arbre d'accessibilite — le plus fiable)
browser_snapshot

# Ou JavaScript direct
browser_evaluate → script: "document.querySelector('.results').innerText"
```

### Tableau
```javascript
// Extraire un tableau HTML en JSON
browser_evaluate → script: `
  const rows = document.querySelectorAll('table tr');
  Array.from(rows).map(r =>
    Array.from(r.querySelectorAll('td,th')).map(c => c.innerText.trim())
  )
`
```

### Formulaire complexe
```
1. browser_snapshot → identifier les champs (ref IDs)
2. browser_click → ref: "input-email"    # Cliquer sur le champ
3. browser_type → ref: "input-email", text: "user@example.com"
4. browser_click → ref: "btn-submit"
5. browser_snapshot → verifier le resultat
```

---

## Selecteurs Robustes (par ordre de fiabilite)

1. **`ref` (Playwright snapshot refs)** — Le plus fiable. Toujours utiliser les refs du snapshot.
2. **`[data-testid="..."]`** — Stable, concu pour l'automatisation.
3. **`[aria-label="..."]`** — Bon pour l'accessibilite.
4. **`#id`** — Fiable si l'ID est stable.
5. **`text="Texte visible"`** — Playwright text selector.
6. **CSS complexe** — Dernier recours. Fragile.

**JAMAIS** utiliser XPath sauf si rien d'autre ne fonctionne.

---

## Gestion des Erreurs Web

| Situation | Action |
|-----------|--------|
| CAPTCHA | STOP. Informer l'utilisateur. Ne pas tenter de resoudre. |
| Login requis | Verifier si session Chrome a les cookies. Sinon informer. |
| Page blanche | Attendre 2s, re-snapshot. Si toujours vide → JS desactive ou erreur serveur. |
| Timeout | Un retry. Si echec → fetch MCP direct (sans navigateur). |
| Popup/cookie banner | `browser_click` sur "Accepter" ou fermer le modal. |
| Infinite scroll | `browser_evaluate` → `window.scrollTo(0, document.body.scrollHeight)` + attente. |

---

## Vitesse Maximale

- **Toujours** commencer par `browser_snapshot` (pas screenshot — 10x plus rapide)
- **Jamais** de `sleep` arbitraire — utiliser `browser_wait_for` si besoin d'attendre
- **Preferer fetch MCP** a Playwright pour les pages simples
- **Cacher les resultats** dans le state manager pour ne pas refaire la meme requete
- **Paralleliser** quand possible : ouvrir plusieurs onglets, extraire en batch
