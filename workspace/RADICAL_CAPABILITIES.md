# Radical Capabilities - Nanobot

## Objectif

Donner a Nanobot une couche d'action plus large et plus resiliente :

- Gmail avec droits de modification.
- Veille proactive.
- Extraction bureau Windows.
- Fallbacks intelligents.
- Agents ad hoc.

## Gmail modify

Le scope ajoute est :

```text
https://www.googleapis.com/auth/gmail.modify
```

Il debloque :

- labels Gmail ;
- creation et suppression de labels utilisateur ;
- marquer lu / non lu ;
- archiver ;
- classer sous label ;
- corbeille ;
- restauration depuis corbeille ;
- suppression permanente si explicitement demandee.

CLI :

```text
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail labels
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail create-label "A traiter"
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail delete-label "A traiter"
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail mark EMAIL_ID --read
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail mark EMAIL_ID --unread
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail archive EMAIL_ID
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail move EMAIL_ID --label "A traiter"
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail trash EMAIL_ID
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail delete EMAIL_ID --permanent
```

MCP :

- `gmail_labels`
- `gmail_create_label`
- `gmail_delete_label`
- `gmail_modify_labels`
- `gmail_mark_read`
- `gmail_archive`
- `gmail_move_to_label`
- `gmail_trash`
- `gmail_untrash`
- `gmail_delete`

Etat : actif et verifie. Le token contient `gmail.modify` avec refresh token.
Verification propre realisee : creation puis suppression du label temporaire
`Nanobot_Test_20260426_003747`, sans modifier les emails reels.

## Veille proactive

Script :

```text
C:\AI\nanobot-omega\scripts\proactive_intel.py
```

Configuration :

```text
C:\AI\nanobot-omega\workspace\proactive_sources.json
```

Rapports :

```text
C:\AI\nanobot-omega\workspace\proactive_reports
```

Sortie Obsidian :

```text
C:\Users\user\Mon Drive\DriveSyncFiles\ARCHITECTE_SYSTEM\99_Système\Nanobot\Veille
```

Commandes :

```text
python C:\AI\nanobot-omega\scripts\proactive_intel.py init
python C:\AI\nanobot-omega\scripts\proactive_intel.py run --limit 50
```

Fonctions :

- surveiller RSS ou pages web ;
- extraire signaux ;
- noter opportunites / menaces ;
- extraire prix, dates, emails, telephones ;
- generer JSON + note Markdown Obsidian.

## Desktop intelligence

Script :

```text
C:\AI\nanobot-omega\scripts\desktop_intel.py
```

Commandes :

```text
python C:\AI\nanobot-omega\scripts\desktop_intel.py windows --xlsx C:\AI\nanobot-omega\workspace\desktop_windows_snapshot.xlsx
python C:\AI\nanobot-omega\scripts\desktop_intel.py ocr C:\chemin\image.png
```

Fonctions :

- lister les fenetres visibles ;
- exporter en `.xlsx` formate avec `Synthese` et `Controle qualite` ;
- OCR d'une capture ou image ;
- route de secours pour applications non-web.

## Resilience orchestrator

Script :

```text
C:\AI\nanobot-omega\scripts\resilience_orchestrator.py
```

Commandes :

```text
python C:\AI\nanobot-omega\scripts\resilience_orchestrator.py doctor-google
python C:\AI\nanobot-omega\scripts\resilience_orchestrator.py run --plan C:\chemin\plan.json
```

Fonctions :

- executer plusieurs routes ;
- valider le resultat, pas seulement le code retour ;
- detecter les impasses fonctionnelles ;
- produire un rapport JSON.

## Agent forge

Script :

```text
C:\AI\nanobot-omega\scripts\agent_forge.py
```

Dossier :

```text
C:\AI\nanobot-omega\workspace\ad_hoc_agents
```

Commandes :

```text
python C:\AI\nanobot-omega\scripts\agent_forge.py create NOM --purpose "Mission"
python C:\AI\nanobot-omega\scripts\agent_forge.py run NOM --input "donnees"
python C:\AI\nanobot-omega\scripts\agent_forge.py list
```

Fonctions :

- creer des mini-agents scripts ;
- stocker un manifest ;
- executer et retourner JSON ;
- enrichir l'arsenal Nanobot sans modifier le coeur a chaque fois.

## Startup capability awareness

Script :

```text
C:\AI\nanobot-omega\scripts\build_startup_context.py
```

Sorties :

```text
C:\AI\nanobot-omega\workspace\NANOBOT_STARTUP_CONTEXT.md
C:\AI\nanobot-omega\workspace\NANOBOT_STARTUP_CONTEXT.json
```

Fonction :

- generer une carte compacte des pouvoirs reels de Nanobot ;
- verifier Google OAuth, Gmail modify, MCP tools, modules critiques et vault Obsidian ;
- etre regeneree au demarrage superviseur/gateway ;
- etre injectee automatiquement dans le prompt systeme a chaque conversation ;
- eviter que Nanobot oublie ses routes, ses scripts ou ses fallbacks.
