# NANOBOT — Veille 2ememain

> Documentation complète de la veille des objets gratuits autour de Mouscron.

Dernière mise à jour : 2026-04-29

---

## Mission

Surveiller toutes les nouvelles annonces **gratuites** (`prix = 0 €`) autour de **Mouscron / 7700**, **rayon 50 km**, sur **2ememain.be**, et m'envoyer une notification Telegram enrichie en **français** quand quelque chose d'intéressant apparaît.

Une majorité d'annonces est en **néerlandais** — toutes sont automatiquement traduites en français avant envoi.

---

## Architecture

```
Windows Task `NanobotVeille2ememain` (toutes les 30 min)
  └─ scripts/nanobot_veille_run_hidden.vbs           (cache la fenêtre cmd)
       └─ scripts/nanobot_veille_run.bat
            └─ workspace/run_veille_and_notify.py    (orchestrateur)
                 ├─ workspace/run_veille_2ememain.py (scraper Playwright)
                 ├─ Google Translate API gratuite    (avec cache)
                 ├─ Scoring déterministe             (PREMIUM_RULES + RISK_RULES + CATEGORY)
                 └─ Telegram Bot API                 (sendMessage / sendPhoto / sendMediaGroup)
```

**Aucun LLM** dans le hot path : zéro quota Gemini, zéro hallucination, latence prédictible.

---

## Catégories surveillées (7)

- Maison / meubles
- Électroménager
- Vêtements (hommes)
- Informatique / logiciels
- TV / hi-fi / vidéo
- Sports / fitness
- Jardin / terrasse

Chaque catégorie correspond à une URL 2ememain filtrée :
- `Language: all-languages` (NL+FR)
- `offeredSince: Gisteren` (24h)
- `priceTo: 0` (gratuit uniquement)
- `distanceMeters: 50000` (50 km)
- `postcode: 7700` (Mouscron)
- `sortBy: PRICE` `INCREASING`

---

## Scoring déterministe (0–10)

### PREMIUM_RULES (+ score)
| Mots-clés | Bonus | Raison |
|---|---|---|
| iphone, macbook, ipad, imac | +5 | Apple : forte demande, revente rapide |
| ps5, switch, xbox series | +5 | Console récente : très liquide |
| velo electrique, e-bike, ebike | +5 | Si batterie/chargeur OK |
| électroménager (lave-vaisselle, frigo, ...) | +4 | Bonne valeur si fonctionnel |
| TV oled/qled/4k | +4 | Si dalle intacte |
| outillage (perceuse, bosch, makita) | +4 | Se revend bien |
| meubles (canapé, table, armoire) | +2 | Dépend état + transport |
| jardin (tondeuse, barbecue, plantes) | +2 | Si proche et bon état |

### RISK_RULES (- score)
| Mots-clés | Malus | Raison |
|---|---|---|
| hs, defect, kapot, pour pieces | -5 | À éviter sauf valeur claire |
| à reparer, herstellen, broken | -4 | Temps incertain |
| sale, vuil, troué, moisi | -3 | Cosmétique faible |
| urgent, containerpark | +1 | Bon coup possible si tu réagis vite |

### Verdict final
- **8–10** : 🔥 TOP OPPORTUNITÉ — à tenter tout de suite
- **5–7** : ✅ INTÉRESSANT — si trajet raisonnable
- **3–4** : ⚖️ MOYEN — vérifier avant de bouger
- **0–2** : 🧊 FAIBLE — probablement pas rentable

---

## Notification Telegram (format actuel)

Pour chaque nouvelle annonce :
- **Titre traduit** en français (gras)
- Titre original NL en italique (si différent)
- Catégorie
- **Verdict** + score X/10
- Commentaire pratique
- Lien direct
- Prix raw (`Gratuit \n Aujourd'hui` etc.)

Cap à **15 ads par notif** (au-delà : "... et N de plus").

### Améliorations Lot 3 (à venir)
- Photo principale envoyée en **album si plusieurs** (`sendMediaGroup`)
- Distance estimée depuis 7700 (basé sur postcode/ville extractible du listing)
- Description courte (3-4 lignes max)
- Niveau de confiance (fiable/moyen/incertain)
- Action recommandée (contacter immédiatement, demander dimensions, ignorer)
- **Message NL prêt à copier**, adaptatif selon catégorie

---

## Fichiers clés

| Chemin | Rôle |
|---|---|
| `workspace/veille_2ememain_config.json` | URLs, postcode, distance |
| `workspace/veille_2ememain_history.json` | IDs annonces déjà vues (dedup) |
| `workspace/veille_2ememain_seen.json` | Cache contenu vu |
| `workspace/veille_2ememain_translation_cache.json` | Cache NL→FR (Google Translate) |
| `workspace/veille_2ememain_state.json` | Dernier check + IDs récents |
| `logs/veille_direct.log` | Logs run/échec/Telegram |
| `workspace/run_veille_2ememain.py` | Scraper Playwright (170 lignes) |
| `workspace/run_veille_and_notify.py` | Orchestrateur scoring+notif (301 lignes) |
| `workspace/veille_2ememain_control.py` | CLI status/pause/resume/Xkm/run |
| `scripts/nanobot_veille_run.bat` (FIRE) | Wrapper task |
| `scripts/nanobot_veille_run_hidden.vbs` (FIRE) | Wrapper cache fenêtre |

---

## Commandes locales

```cmd
# Statut + dernier log
python C:/AI/nanobot-omega/workspace/veille_2ememain_control.py status

# Pause / reprise (admin requis)
python C:/AI/nanobot-omega/workspace/veille_2ememain_control.py pause
python C:/AI/nanobot-omega/workspace/veille_2ememain_control.py resume

# Run manuel
python C:/AI/nanobot-omega/workspace/veille_2ememain_control.py run

# Changer le rayon
python C:/AI/nanobot-omega/workspace/veille_2ememain_control.py 50km
python C:/AI/nanobot-omega/workspace/veille_2ememain_control.py 100km
```

### Commandes Telegram (via le bot @Nanobooots_bot)
- `/veille2 status` — état + dernier log
- `/veille2 run` — relance maintenant
- `/veille2 50km` / `/veille2 100km` — change le rayon

(Le routeur Telegram doit être à jour pour reconnaître ces commandes.)

---

## Diagnostic & dépannage

### "La veille semble morte"
```cmd
python C:/AI/nanobot-omega/scripts/nanobot_self_check.py check
```
Le check `veille_2ememain_task` rapporte l'état (Ready / Running / Disabled). Le check `veille_2ememain_health` analyse les 200 dernières lignes de log et rapporte runs/échecs/dernière notif.

### Symptômes courants
| Symptôme | Cause | Fix |
|---|---|---|
| Tâche `Disabled` | `pause` lancé mais pas `resume` | `veille2 resume` (admin) |
| Aucun run dans logs | Task Scheduler n'a pas tourné | `schtasks /Run /TN NanobotVeille2ememain` ou reboot |
| Scraper rc=1 + "No Chrome found" | Chrome désinstallé / mauvais path | Vérifier `chrome.exe` ou définir env `NANOBOT_CHROME_EXE` |
| `Telegram error` dans logs | Bot offline ou DNS | Voir `state/gateway.lock` + `Start-NanobotTelegramGateway.ps1` |
| 0 nouveauté pendant des heures | Normal — peu d'annonces gratuites | Vérifier sur 2ememain.be manuellement |
| Annonces dupliquées Telegram | History corrompue | Backup `veille_2ememain_history.json` puis reset |

---

## Hardware & limites connues

- Scraper prend ~90s par run (7 URLs × 8s sleep + load + extract)
- Cap 15 annonces / notif Telegram (limite Telegram messages)
- Google Translate gratuit : ~100 reqs/heure sans clé → cache critique
- Sur i7-5600U / 8 GB RAM : Playwright tourne en headless (pas de GPU)

---

## Roadmap (lots prochains)

| Lot | Description |
|---|---|
| 2 | Scraper extrait photo URL + location vendeur + description courte |
| 3 | Notif sendMediaGroup (album photo) + distance Haversine + msg NL adaptatif |
| 4 | Alerte auto si 3 runs successifs échouent |
| 5 | Control étendu (`health`, `logs`, `opportunities`, `test-notification`, `reset-seen`) |
| 6 | Framework générique → permet veilles immo/jobs/prix |
