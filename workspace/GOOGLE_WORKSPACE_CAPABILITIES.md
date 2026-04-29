# Google Workspace Capabilities - Nanobot

## Etat

Nanobot dispose maintenant d'une couche Google Workspace locale dans :

```text
C:\AI\nanobot-omega
```

Elle ne depend plus uniquement du package npm `google-workspace-mcp`.

## Authentification

OAuth local :

```text
C:\AI\nanobot-omega\configs\google_credentials.json
C:\AI\nanobot-omega\configs\google_token.json
```

Le token est persistant, contient un refresh token et se rafraichit automatiquement.

Compte vise :

```text
monagenda.be@gmail.com
```

Scopes actifs :

- Gmail lecture
- Gmail envoi
- Gmail modification : labels, lu/non lu, classement, archive, corbeille
- Calendar events
- Drive complet
- Tasks
- Contacts
- Google Docs
- Google Sheets

Note : Gmail suppression permanente existe, mais doit rester une action explicite
avec `--permanent`. Par defaut, privilegier la corbeille.

## CLI JSON

Commande principale :

```text
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json auth status
```

Exemples :

```text
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json drive ls --max 10
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json drive search "ARCHITECTE_SYSTEM"
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json docs create "Titre"
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json docs append DOC_ID "Texte"
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json sheets create "Titre"
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json sheets update SHEET_ID "[[\"A\",\"B\"]]" --range A1:B1
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail search "newer_than:7d"
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail labels
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail create-label "A traiter"
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail mark EMAIL_ID --read
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail move EMAIL_ID --label "A traiter"
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json mail trash EMAIL_ID
```

## MCP local

Serveur :

```text
C:\AI\nanobot-omega\scripts\google_workspace_mcp.py
```

Demarrage via la configuration Nanobot :

```text
C:\AI\nanobot-omega\scripts\Start-GoogleWorkspaceMcp.ps1
```

Le script `Start-GoogleWorkspaceMcp.ps1` lance maintenant le MCP Python local au
lieu du package npm externe.

Outils MCP exposes : 44.

Familles principales :

- `gmail_search`, `gmail_read`, `gmail_send`
- `gmail_labels`, `gmail_create_label`, `gmail_delete_label`
- `gmail_modify_labels`, `gmail_mark_read`, `gmail_archive`
- `gmail_move_to_label`, `gmail_trash`, `gmail_untrash`, `gmail_delete`
- `calendar_list`, `calendar_create`, `calendar_delete`
- `drive_list`, `drive_search`, `drive_read`, `drive_upload`,
  `drive_create_folder`, `drive_update_metadata`, `drive_move`, `drive_delete`
- `docs_list`, `docs_create`, `docs_read`, `docs_append`, `docs_delete`
- `sheets_list`, `sheets_create`, `sheets_read`, `sheets_append_row`,
  `sheets_update_values`, `sheets_clear`, `sheets_delete`
- `tasks_list`, `tasks_add`, `tasks_complete`
- `contacts_list`, `contacts_search`, `contacts_create`
- `google_auth_status`, `google_natural`

## Verification faite

Le 2026-04-26 :

- Auth Google valide.
- Token persistant avec refresh token.
- Scope `gmail.modify` actif.
- CLI compile.
- MCP local compile.
- MCP local expose 44 outils.
- Test Gmail modify reel mais neutre :
  - label temporaire `Nanobot_Test_20260426_003747` cree ;
  - label temporaire supprime ;
  - aucun email reel modifie.
- Test Google Docs reel :
  - document cree ;
  - texte ajoute ;
  - texte relu ;
  - document mis a la corbeille.
- Test Google Sheets reel :
  - tableur cree ;
  - cellules ecrites ;
  - cellules relues ;
  - tableur mis a la corbeille.

## Regle operationnelle

Quand un outil MCP Google n'apparait pas ou echoue, Nanobot doit utiliser la CLI
JSON locale avant de conclure a un blocage.

La route de secours est :

```text
python C:\AI\nanobot-omega\scripts\google_workspace_cli.py --json ...
```
