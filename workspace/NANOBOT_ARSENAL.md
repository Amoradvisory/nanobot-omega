# NANOBOT ARSENAL

Fiche courte que Nanobot peut relire a tout moment pour choisir le bon chemin d'action.

Memoire recente importante: lire aussi
`C:/AI/nanobot-omega/workspace/NANOBOT_RECENT_UPGRADES.md` quand la tache
touche Excel, Telegram, le gateway, les outils MCP, FIRE, ou une erreur deja
corrigee.

## Reflexe principal

Avant de repondre "je ne peux pas", Nanobot doit:

1. Identifier la famille de capacite utile.
2. Utiliser le tool ou le skill correspondant.
3. Verifier le resultat.
4. Si le premier chemin echoue, diagnostiquer puis essayer une autre route raisonnable.

## Capacites natives

- Fichiers: lire, lister, chercher, creer et modifier des fichiers avec `read_file`, `list_dir`, `grep`, `glob`, `write_file`, `edit_file`.
- Shell Windows: lancer commandes, scripts Python, PowerShell et outils locaux avec `exec`.
- Web: chercher avec `web_search`, lire une URL avec `web_fetch`.
- Navigateur: ouvrir et piloter Chrome Agent avec `browser_automation` (outil natif Nanobot enregistre, pas un MCP).
- Bureau Windows: voir les fenetres, capturer l'ecran, OCR ecran et actions simples avec `desktop_automation` (outil natif Nanobot enregistre, pas un MCP).
- OCR et Vision: `ocr` pour texte imprime, `vision_analyze_image` pour images, captures, schemas et ecriture manuscrite (outils natifs Nanobot enregistres).
- Google local: Gmail, Calendar, Drive, Tasks, Contacts, Docs et Sheets via les outils Google locaux quand les autorisations sont presentes.
- Documents: produire CSV, Excel, Word, PDF, Markdown et rapports en utilisant les skills documentaires.
- Acquisition logicielle Windows: utiliser `C:/AI/nanobot-omega/scripts/app_acquisition.py` pour verifier, telecharger, installer ou ouvrir une application sans confondre page web et application locale.
- Obsidian / second cerveau: utiliser `C:/AI/nanobot-omega/scripts/obsidian_second_brain.py` pour capturer une note, chercher dans le vault, importer un PDF ou une image, synchroniser la memoire Nanobot et ouvrir le hub Obsidian.
- Memoire et planification: utiliser les sessions, les fichiers memoire et `cron` pour les taches recurrentes.
- Diagnostic: utiliser `tool_diagnostics`, notamment `target="capabilities"`, quand un outil semble absent ou casse.

## MCP branches

Les serveurs MCP configures dans `config_omega.json` donnent des outils supplementaires nommes `mcp_<serveur>_<outil>`. Les outils navigateur/bureau/OCR/vision/diagnostic sont des outils natifs Nanobot et n'ont pas besoin d'un MCP browser separe pour etre utilisables.

- `filesystem`: acces MCP aux dossiers Nanobot, Bureau, Documents, Telechargements et package Nanobot.
- `memory`: graphe de memoire MCP local persistant.
- `sequential_thinking`: volontairement desactive (`enabledTools=[]`) pour eviter les fuites de raisonnement et de tool-noise dans Telegram.
- `google_workspace`: deuxieme voie Google via MCP pour Gmail, Calendar, Drive, Docs, Sheets, Slides et Forms. Compte par defaut: `monagenda`.
- `notion`: serveur MCP officiel Notion pour chercher, lire et modifier les pages/data sources autorisees par l'integration.

GitHub: utiliser les outils git/gh locaux pour l'instant. Le serveur MCP officiel GitHub demande Docker ou Go, absents sur cette machine au moment de l'installation.

Si un outil MCP n'apparait pas, lancer un diagnostic des capacites ou consulter les logs du gateway.

## Skills importants

- `omega-tool-operator`: agir avec les vrais outils, verifier, puis repondre court.
- `web-and-ocr`: recherche web, fetch, OCR et verification visuelle.
- `shared-browser`: utiliser le Chrome partage et son profil persistant.
- `desktop-defaults`: interaction Windows et bureau.
- `telegram-mobile`: reponses courtes et claires pour Telegram.
- `alpha-web`: automation web avancee.
- `pc-master`: actions systeme et controle PC.
- `document-master`: documents propres, CSV, Excel, Word, PDF et Markdown.
- `resilience`: recuperer apres echec.
- `state-memory`: garder et exploiter l'etat utile.

## Commandes Telegram utiles

- `/arsenal`: renvoie cette fiche.
- `/status`: etat Nanobot.
- `/help`: liste des commandes.

## Routes alternatives

- Page web difficile: `web_fetch` si statique, sinon `browser_automation`, puis OCR/capture si necessaire.
- Image ou manuscrit: `vision_analyze_image`, puis OCR local si la vision est indisponible.
- Application Windows: `desktop_automation`, puis shell/PowerShell si une commande directe existe.
- Telechargement / installation d'application: `app_acquisition.py`, puis verification locale (`winget list`, shortcut, AppID, fichier installeur).
- Obsidian / vault: `obsidian_second_brain.py`, puis verification locale dans `C:/Users/user/Mon Drive/ARCHITECTE_SYSTEM`.
- Fichier introuvable: `glob`, `grep`, puis MCP filesystem.
- Erreur outil: `tool_diagnostics action="suggest"` ou `target="capabilities"`.

## Limites saines

Nanobot peut agir largement sur cette machine, mais doit eviter les changements destructeurs, les secrets affiches, les installations inutiles et les actions risquant de casser Windows. Pour une action dangereuse, il doit expliquer le risque et demander confirmation.
