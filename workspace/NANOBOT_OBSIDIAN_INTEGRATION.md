# NANOBOT × OBSIDIAN — Mode d'emploi unifié

> Source de vérité unique pour tout ce qui touche l'intégration Obsidian.
> Maintenue à la main. En cas de conflit avec une autre note, **cette note prime**.

Dernière mise à jour : 2026-04-29

---

## 1. Architecture en une phrase

NanoBot pilote le vault Obsidian **uniquement via** `scripts/obsidian_second_brain.py`. Le vault est synchronisé en cloud par **Google Drive Desktop** (compte `monagenda.be@gmail.com`). Aucune écriture brute dans le vault — toutes les opérations passent par le bridge.

---

## 2. Chemins canoniques

| Élément | Chemin |
|---|---|
| **Vault actif** | `C:\Users\user\Mon Drive\DriveSyncFiles\ARCHITECTE_SYSTEM\` |
| **Bridge Python** | `C:\AI\nanobot-omega\scripts\obsidian_second_brain.py` |
| **Bridge config** | `C:\AI\nanobot-omega\workspace\obsidian_bridge_config.json` |
| **Cockpit (entry humain)** | `00_Commandement\Cockpit_de_Vie.md` (peut ne pas exister si l'utilisateur a réorganisé) |
| **Hub Nanobot** | `00_Commandement\Hub_Nanobot_Obsidian.md` (idem) |
| **Mémoire Nanobot dans le vault** | `99_Système\Nanobot\Memoire\Memoire_Nanobot.md` |

⚠️ **Le vault peut contenir une structure différente de la structure Life OS canonique** si l'utilisateur l'a réorganisé. NanoBot doit s'adapter à la structure réelle, pas l'inverse. Avant de créer des dossiers, lister la structure actuelle avec `list`.

---

## 3. Sous-commandes du bridge (24 au total)

Lance avec : `python C:\AI\nanobot-omega\scripts\obsidian_second_brain.py <commande> ...`

### Lecture (read-only)
- `status` — vue d'ensemble du vault
- `list [--folder X] [--pattern *]` — listing récursif
- `read-note --path X` — lit une note (frontmatter + body, JSON)
- `get-frontmatter --path X` — lit uniquement le frontmatter
- `filter-notes [--tag X] [--property X] [--value X] [--folder X] [--query X]` — filtrage
- `search QUERY` — recherche full-text
- `attachments [--folder X]` — liste les pièces jointes non-MD
- `sync-status` — état Google Drive Desktop

### Création / Capture
- `capture --content X [--title X] [--tags ...] [--folder X]` — note auto-classifiée
- `daily --content X [--heading X]` — append à la note du jour
- `import PATH` — importe un PDF/image/markdown
- `add-attachment PATH [--note X] [--category X]` — copie une pièce jointe
- `create-folder --path X` — crée un dossier
- `write-note --path X --content X [--frontmatter JSON] [--mode overwrite|append|create]`

### Modification
- `set-frontmatter --path X --updates JSON` — fusionne dans le frontmatter
- `tags --path X [--add ...] [--remove ...]` — ajoute/retire tags
- `relations [--all]` — retisse les sections "Hubs utiles" / "Passerelles utiles"
- `sync-memory` — synchronise la mémoire Nanobot dans le vault

### Déplacement / Suppression (⚠️ destructif)
- `rename-path --src X --dst Y` — renomme/déplace
- `move-note --src X --folder Y` — déplace en gardant le nom
- `move-attachment --src X --dst Y` — déplace une pièce jointe
- `delete-path --path X [--recursive]` — supprime fichier ou dossier

### Démarrage
- `bootstrap` — initialise la structure (idempotent)
- `open [--note X]` — ouvre Obsidian sur une note

---

## 4. Sécurité

Toutes les commandes du bridge :
- Refusent les chemins absolus en dehors du vault (anti-traversal)
- Refusent les chemins commençant par `..`
- Protègent `.obsidian/` et `.trash/` (sauf `--allow_protected` interne)
- Respectent l'exclusion `archive_exclusions` (par défaut `05_Archives/`) — ces dossiers contiennent des chemins > MAX_PATH (260 chars) qui faisaient crash le bridge avant le 2026-04-28

Les commandes destructives **n'ont pas encore de mode dry-run** — c'est le Lot 3 du plan de stabilisation. En attendant, double-checker avant `delete-path`, `rename-path`, `move-note`.

---

## 5. Auto-classification des captures

Quand `capture` est appelé sans `--folder`, le contenu est analysé selon des règles de mots-clés (5 catégories) :

| Catégorie | Dossier cible | Mots-clés (extraits) |
|---|---|---|
| `projets` | `01_Projets_Actifs/En_Cours/Captures_Nanobot` | projet, roadmap, deadline, sprint, livrable |
| `pro` | `02_Domaines/Professionnel/Nanobot` | travail, client, business, réunion, vente |
| `perso` | `02_Domaines/Personnel/Nanobot` | personnel, famille, maison, santé, sport |
| `personnes` | `02_Domaines/Personnes/Nanobot` | contact, RDV, email, téléphone, anniversaire |
| `lecture` | `04_Bibliothèque/Lectures_Nanobot` | livre, article, chapitre, citation, podcast |

Le score, la confiance et les raisons sont écrits dans le frontmatter de la note (`capture_category`, `capture_confidence`, `capture_score`, `capture_reasons`).

---

## 6. Commandes manquantes (à venir, Lot 2)

Ces commandes seront ajoutées dans le prochain lot de stabilisation :
- `audit-vault` — rapport global (notes, dossiers, tags, liens, frontmatter)
- `detect-orphans` — notes sans backlink ni lien sortant
- `detect-duplicates` — notes au titre/contenu très similaires
- `detect-weak-notes` — notes < N chars, sans titre/tag/lien
- `detect-broken-links` — `[[liens]]` cassés
- `propose-structure` — suggestions de re-classement (read-only)

---

## 7. Diagnostic

Si NanoBot semble incapable d'agir sur Obsidian :

```bash
python C:\AI\nanobot-omega\scripts\nanobot_self_check.py check
```

Cette commande vérifie en cascade :
- workspace_layout, critical_docs, operational_scripts
- obsidian_bridge_status (vrai appel à `status`)
- obsidian_subcommands (les 24 sous-commandes sont-elles présentes)
- vault_access (existe + writable)
- google_oauth (avec auto-refresh disponible)
- gateway_lock, ollama_daemon, startup_context_freshness
- memory_dedup, capabilities_doc_consistency, built_in_tools_audit

Score : `OK` / `DÉGRADÉ` / `CASSÉ`. Sortie JSON dans `health/self_check_latest.json`.

---

## 8. Quand l'utilisateur dit "fais X dans Obsidian"

Ordre des opérations :
1. **Lire `list` du dossier concerné** pour voir la structure réelle (jamais supposer).
2. Identifier la sous-commande exacte du bridge.
3. Si lecture seule : exécuter directement.
4. Si écriture : exécuter, puis vérifier avec `read-note` ou `list`.
5. Si destruction : confirmer avec l'utilisateur avant.
6. Reporter le chemin exact, le résultat JSON, et un message court en français.

---

## 9. Ce qu'il NE faut PAS faire

- ❌ Écrire directement dans le vault (jamais `write_file` sur un `.md` du vault — toujours via bridge)
- ❌ Supprimer un dossier `.obsidian/` ou des notes sans confirmation explicite
- ❌ Renommer une note sans réfléchir aux liens entrants `[[Nom]]` (Lot 3 ajoutera `--update-links`)
- ❌ Supposer que le vault a la structure Life OS canonique — toujours `list` d'abord
- ❌ Considérer `Cockpit_de_Vie.md` comme garanti — vérifier avec `read-note` avant
