---
name: pc-master
description: "Controle avance du PC Windows. Gestion fenetres, saisie, focus, processus, screenshots, automatisation multi-apps, Chrome en onglets. Declencheurs: ouvre une app, tape dans, clique sur, fenetre, gere les processus, controle le PC, automatise."
---

# PC-Master — Controle Expert du Poste Windows

Tu controles ce PC Windows comme un operateur expert.
Module : `C:/AI/nanobot-omega/modules/pc_master.py`

---

## Commandes Rapides

### Fenetres
```bash
python C:/AI/nanobot-omega/modules/pc_master.py windows       # Lister
python C:/AI/nanobot-omega/modules/pc_master.py active         # Fenetre active
python C:/AI/nanobot-omega/modules/pc_master.py focus "Chrome" # Focus par titre
```

### Saisie
```bash
python C:/AI/nanobot-omega/modules/pc_master.py type "Texte a taper"    # Via clipboard (unicode OK)
python C:/AI/nanobot-omega/modules/pc_master.py keys "^s"               # SendKeys (Ctrl+S)
python C:/AI/nanobot-omega/modules/pc_master.py click 500 300           # Clic a (x,y)
```

### Chrome (Instance Unique)
```bash
python C:/AI/nanobot-omega/modules/pc_master.py url "https://example.com"  # Nouvel onglet
python C:/AI/nanobot-omega/modules/pc_master.py tabs                       # Onglets ouverts
```

### Systeme
```bash
python C:/AI/nanobot-omega/modules/pc_master.py processes     # Top processus
python C:/AI/nanobot-omega/modules/pc_master.py sysinfo       # CPU/RAM/Disque
python C:/AI/nanobot-omega/modules/pc_master.py screenshot     # Capture d'ecran
```

---

## Chrome : UNE Instance, PLUSIEURS Onglets

**Probleme resolu** : l'agent ouvrait des fenetres multiples, saturant le systeme.

**Solution** : Le chrome_launcher detecte Chrome actif et ouvre des ONGLETS.

```powershell
# Lancer ou reutiliser Chrome
& "C:/AI/nanobot-omega/modules/chrome_launcher.ps1"

# Ouvrir URL dans onglet existant
& "C:/AI/nanobot-omega/modules/chrome_launcher.ps1" -Url "https://google.com"

# Etat de la session
& "C:/AI/nanobot-omega/modules/chrome_launcher.ps1" -Status

# Redemarrage propre (si session corrompue)
& "C:/AI/nanobot-omega/modules/chrome_launcher.ps1" -Reset
```

### Regles Chrome :
1. **TOUJOURS** verifier si Chrome est actif avant de lancer
2. **JAMAIS** `Start-Process chrome` directement — utiliser le launcher
3. **TOUJOURS** utiliser `-Url` pour ouvrir un site → nouvel onglet
4. Si Chrome ne repond plus → `-Reset` (pas kill brutal)

---

## Workflow : Interaction Multi-Application

### Copier texte d'une app vers une autre
```bash
# 1. Focus sur l'app source
python .../pc_master.py focus "Notepad"

# 2. Selectionner tout + copier
python .../pc_master.py keys "^a"
python .../pc_master.py keys "^c"

# 3. Focus sur destination
python .../pc_master.py focus "Word"

# 4. Coller
python .../pc_master.py keys "^v"
```

### Automatiser une sequence dans une app
```bash
# 1. Focus
python .../pc_master.py focus "Excel"

# 2. Naviguer (raccourcis clavier = plus fiable que clics)
python .../pc_master.py keys "^{HOME}"    # Aller en A1
python .../pc_master.py type "Titre"       # Ecrire
python .../pc_master.py keys "{TAB}"       # Colonne suivante
python .../pc_master.py type "Valeur"
python .../pc_master.py keys "{ENTER}"     # Ligne suivante
python .../pc_master.py keys "^s"          # Sauvegarder
```

### Prendre une decision basee sur l'ecran
```bash
# 1. Screenshot
python .../pc_master.py screenshot C:/temp/ecran.png

# 2. Analyser visuellement (utiliser la vision du modele)
# 3. Agir en consequence
```

---

## Codes SendKeys

| Action | Code | Exemple |
|--------|------|---------|
| Ctrl+S | `^s` | Sauvegarder |
| Ctrl+A | `^a` | Tout selectionner |
| Ctrl+C | `^c` | Copier |
| Ctrl+V | `^v` | Coller |
| Ctrl+Z | `^z` | Annuler |
| Alt+F4 | `%{F4}` | Fermer fenetre |
| Alt+Tab | `%{TAB}` | Changer fenetre |
| Windows+D | `^{ESC}` | Bureau |
| Entree | `{ENTER}` | Valider |
| Tab | `{TAB}` | Champ suivant |
| Echap | `{ESC}` | Annuler/Fermer |
| Fleches | `{UP}` `{DOWN}` `{LEFT}` `{RIGHT}` | Navigation |
| F2 | `{F2}` | Renommer |
| F5 | `{F5}` | Rafraichir |
| Ctrl+Shift+Esc | `^+{ESC}` | Task Manager |

---

## Precautions

- **Screenshot avant clic** si position incertaine
- **Preferer les raccourcis clavier** aux clics (plus fiable, plus rapide)
- **Attendre** 500ms-1s apres ouverture d'une app avant d'interagir
- **`type_text`** pour texte long/unicode, **`send_keys`** pour raccourcis
- **Verifier** le resultat apres chaque action significative
