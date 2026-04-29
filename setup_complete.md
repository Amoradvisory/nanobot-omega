# 🚀 Nanobot Omega — Setup Guide

## Prerequis

- **Python 3.12+** (tu as 3.14 ✓)
- **Nanobot** installe via uv (✓)
- **Gemini CLI** avec 10 comptes A-J (✓)
- **openai** package Python (`pip install openai`)
- **json-repair** package Python (`pip install json-repair`)

## Installation rapide

```bash
# Installer les dependances manquantes
pip install openai json-repair apscheduler

# Verifier que tout est en place
python C:\AI\nanobot-omega\nanobot_omega_launcher.py --status
```

## Lancement

### Option 1 — Double-cliquer le launcher Windows
```
C:\AI\nanobot-omega\Nanobot Omega.bat
```

### Option 2 — Lignes de commande

```bash
# Mode CLI interactif
python C:\AI\nanobot-omega\nanobot_omega_launcher.py

# Mode Gateway (Telegram + API)
python C:\AI\nanobot-omega\nanobot_omega_launcher.py --gateway

# Status de l'orchestrateur
python C:\AI\nanobot-omega\nanobot_omega_launcher.py --status

# Test rapide
python C:\AI\nanobot-omega\nanobot_omega_launcher.py --test "Bonjour Omega"
```

## Configuration

### Ajouter des cles API Gemini (recommande)
Editer `C:\AI\nanobot-omega\instances.json` :
```json
{
  "mode": "api",
  "api_keys": [
    "AIza..._CLE_1",
    "AIza..._CLE_2"
  ],
  ...
}
```
- Genere tes cles sur https://aistudio.google.com/apikey
- Meme 1-2 cles suffisent, l'orchestrateur fait la rotation

### Activer Telegram
1. Parler a @BotFather sur Telegram
2. Creer un bot avec `/newbot`
3. Copier le token
4. Editer `C:\AI\nanobot-omega\config_omega.json` :
```json
"telegram": {
    "enabled": true,
    "token": "123456:ABC-DEF..."
}
```
5. Lancer en mode Gateway

### Omega Core (auto-evolution)
```bash
# Lancer une analyse manuelle
python C:\AI\nanobot-omega\OMEGA_CORE.py evolve

# Voir le profil actuel
python C:\AI\nanobot-omega\OMEGA_CORE.py status

# Lancer en daemon (24h auto)
python C:\AI\nanobot-omega\OMEGA_CORE.py daemon
```

## Structure

```
C:\AI\nanobot-omega\
├── gemini_cli_orchestrator.py   # Orchestrateur 10 instances
├── gemini_orchestrator_provider.py  # Provider Nanobot
├── nanobot_omega_launcher.py    # Launcher avec monkey-patch
├── OMEGA_CORE.py                # Auto-evolution
├── config_omega.json            # Config Nanobot
├── instances.json               # Config instances Gemini
├── Nanobot Omega.bat            # Launcher Windows
├── workspace/
│   ├── SOUL.md                  # Prompt systeme
│   ├── USER.md                  # Profil utilisateur
│   ├── AGENTS.md                # Instructions agent
│   ├── HEARTBEAT.md             # Taches periodiques
│   ├── TOOLS.md                 # Notes outils
│   ├── OMEGA_PROFILE.md         # Profil auto-enrichi
│   └── memory/
│       └── MEMORY.md            # Memoire persistante
└── logs/
    ├── orchestrator.log
    └── omega_core.log
```

## Monitoring

```bash
# Logs orchestrateur (dernières erreurs)
Get-Content C:\AI\nanobot-omega\logs\orchestrator.log -Tail 50

# Logs Omega Core
Get-Content C:\AI\nanobot-omega\logs\omega_core.log -Tail 50

# Status complet
python C:\AI\nanobot-omega\gemini_cli_orchestrator.py status
```

## Troubleshooting

| Probleme | Solution |
|----------|----------|
| "No module nanobot" | `pip install nanobot-ai` ou verifier le chemin site-packages |
| "All instances blacklisted" | Attendre 60s ou relancer l'orchestrateur |
| Rate limit 429 | Normal, l'orchestrateur rotate automatiquement |
| Subprocess timeout | Augmenter `subprocess_timeout_s` dans instances.json |
| Telegram ne repond pas | Verifier le token dans config_omega.json |
