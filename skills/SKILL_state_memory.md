---
name: state-memory
description: "Memoire vive operationnelle. Etat de travail persistant, suivi de tache, notes rapides, historique d'actions, reprise apres interruption. Declencheurs: retiens, memorise, ou en suis-je, reprends, note, etat, contexte, historique."
---

# State-Memory — Memoire Vive Operationnelle

Module : `C:/AI/nanobot-omega/modules/state_manager.py`

---

## Pourquoi c'est critique

Sans memoire operationnelle, l'agent :
- Relit les memes fichiers a chaque tour
- Perd le fil d'une tache multi-etapes
- Oublie ses decisions precedentes
- Repete des analyses deja faites

Avec State-Memory, l'agent :
- Sait exactement ou il en est
- Reprend sans perte apres interruption
- Capitalise sur ses decouvertes
- Reduit le nombre de tours necessaires

---

## Usage Rapide

### Commencer une tache
```python
from modules.state_manager import state

state.begin_task("Deployer le module web", "3 etapes: structure, config, deps")
```

### Avancer
```python
state.advance_step("Dossier cree: /var/www/app")
state.advance_step("Config nginx ecrite")
state.note("Port 8080 deja utilise — pris le 8081")
state.advance_step("npm install OK — 142 packages")
```

### Terminer
```python
state.complete_task("Module web operationnel sur port 8081")
```

### Lire l'etat a tout moment
```python
state.summary()  # Resume texte compact
```

---

## Operations de base

| Operation | Code | Usage |
|-----------|------|-------|
| Lire | `state.get("key")` | Recuperer une valeur |
| Ecrire | `state.set("key", value)` | Stocker une valeur |
| Supprimer | `state.delete("key")` | Nettoyer |
| Ajouter a liste | `state.push("key", item)` | Historique, logs |
| Incrementer | `state.increment("counter")` | Compteurs |
| Note rapide | `state.note("texte")` | Observation, decision |
| Resume | `state.summary()` | Vue d'ensemble |
| Reset | `state.clear()` | Nouveau depart |

---

## CLI

```bash
python C:/AI/nanobot-omega/modules/state_manager.py show       # Etat complet JSON
python C:/AI/nanobot-omega/modules/state_manager.py summary    # Resume texte
python C:/AI/nanobot-omega/modules/state_manager.py get <key>  # Lire une valeur
python C:/AI/nanobot-omega/modules/state_manager.py set <key> <value>
python C:/AI/nanobot-omega/modules/state_manager.py keys       # Liste des cles
python C:/AI/nanobot-omega/modules/state_manager.py clear      # Reset
```

---

## Quand utiliser

- **Debut de mission** → `begin_task()`
- **Chaque etape significative** → `advance_step()`
- **Decouverte importante** → `note()`
- **Variable a retenir** → `set()` (port, chemin, version, decision)
- **Fin de mission** → `complete_task()`
- **Reprise apres interruption** → `summary()` pour retrouver le contexte

---

## Fichiers de persistance

| Fichier | Role | Rotation |
|---------|------|----------|
| `C:/AI/nanobot-omega/state/working_state.json` | Etat actif | Permanent |
| `C:/AI/nanobot-omega/state/state_history.jsonl` | Journal des changements | Auto a 500KB |
