from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - environment dependent
    PdfReader = None

OMEGA_ROOT = Path(r"C:\AI\nanobot-omega")
WORKSPACE_ROOT = OMEGA_ROOT / "workspace"
CONFIG_PATH = WORKSPACE_ROOT / "obsidian_bridge_config.json"
APPDATA_OBSIDIAN = Path(os.environ.get("APPDATA", r"C:\Users\user\AppData\Roaming")) / "Obsidian" / "obsidian.json"

if str(OMEGA_ROOT) not in sys.path:
    sys.path.insert(0, str(OMEGA_ROOT))

try:
    from tools.ocr_tool import perform_ocr
except Exception:  # pragma: no cover - optional dependency path
    perform_ocr = None

MEMORY_SOURCES: list[tuple[str, Path]] = [
    ("Recent upgrades", OMEGA_ROOT / "workspace" / "NANOBOT_RECENT_UPGRADES.md"),
    ("Agent V2", OMEGA_ROOT / "AGENT_V2.md"),
    ("Mission YOLO", OMEGA_ROOT / "MISSION_YOLO.md"),
    ("User profile", OMEGA_ROOT / "workspace" / "USER.md"),
]

MANAGED_DIR_KEYS = (
    "brain_root",
    "brain_inbox_dir",
    "brain_memory_dir",
    "brain_relations_dir",
    "imports_dir",
    "attachments_dir",
    "capture_projects_dir",
    "capture_professional_dir",
    "capture_personal_dir",
    "capture_people_dir",
    "capture_reading_dir",
    "time_root",
    "time_templates_dir",
)

TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
PDF_EXTENSIONS = {".pdf"}
SUPPORTED_IMPORT_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | PDF_EXTENSIONS

STOP_WORDS = {
    "alors",
    "apres",
    "aux",
    "avec",
    "ce",
    "ces",
    "cet",
    "cette",
    "comme",
    "dans",
    "de",
    "des",
    "du",
    "dans",
    "depuis",
    "elle",
    "elles",
    "entre",
    "est",
    "et",
    "etre",
    "fait",
    "faites",
    "faire",
    "ici",
    "ils",
    "la",
    "le",
    "les",
    "leur",
    "leurs",
    "mais",
    "meme",
    "mes",
    "mon",
    "nous",
    "notre",
    "pour",
    "plus",
    "tres",
    "trop",
    "sans",
    "sous",
    "sur",
    "ses",
    "son",
    "ta",
    "te",
    "tes",
    "ton",
    "tu",
    "vers",
    "donc",
    "cela",
    "vous",
    "aussi",
    "quand",
    "quoi",
    "dont",
    "tout",
    "tous",
    "toute",
    "toutes",
    "avoir",
    "ainsi",
    "cela",
    "cest",
    "pourra",
    "peut",
    "peux",
    "doit",
    "doivent",
    "nanobot",
    "obsidian",
    "vault",
    "note",
    "notes",
    "fichier",
    "fichiers",
    "memoire",
    "systeme",
    "brain",
    "dashboard",
    "cockpit",
    "hubs",
    "hub",
    "liens",
    "lien",
    "passerelles",
    "passerelle",
    "utiles",
    "utile",
    "pilotage",
    "centre",
    "vie",
    "domaines",
    "commandement",
    "system",
    "life",
    "lifeos",
    "os",
    "imports",
    "import",
    "capture",
    "captures",
    "navigation",
    "rapide",
    "points",
    "quelles",
    "mois",
    "attente",
    "echeances",
    "quotidien",
}

GENERIC_RELATION_TAGS = {
    "nanobot",
    "obsidian",
    "dashboard",
    "life os",
    "life",
    "system",
    "systeme",
    "capture",
    "import",
    "memory",
    "snapshot",
    "guide",
    "hub",
}

CAPTURE_CATEGORY_ORDER = ["projets", "lecture", "personnes", "pro", "perso"]

CAPTURE_CATEGORY_RULES: dict[str, dict[str, Any]] = {
    "projets": {
        "label": "projets",
        "folder_key": "capture_projects_dir",
        "keywords": {
            "projet": 5,
            "roadmap": 5,
            "deadline": 4,
            "milestone": 4,
            "livrable": 4,
            "sprint": 4,
            "feature": 4,
            "objectif": 3,
            "plan action": 3,
            "a faire": 3,
            "todo": 3,
            "priorite": 3,
            "etape": 3,
            "chantier": 3,
            "lancement": 3,
            "mettre en place": 3,
            "workflow": 3,
            "automatique": 2,
            "classification": 2,
            "implementation": 2,
            "amelioration": 2,
            "execution": 2,
        },
    },
    "pro": {
        "label": "pro",
        "folder_key": "capture_professional_dir",
        "keywords": {
            "travail": 5,
            "professionnel": 5,
            "client": 4,
            "entreprise": 4,
            "business": 4,
            "reunion": 3,
            "meeting": 3,
            "cours": 3,
            "eleve": 3,
            "marketing": 3,
            "vente": 3,
            "facture": 3,
            "devis": 3,
            "contrat": 3,
            "prospection": 3,
            "ecole": 3,
            "administratif": 2,
        },
    },
    "perso": {
        "label": "perso",
        "folder_key": "capture_personal_dir",
        "keywords": {
            "personnel": 5,
            "perso": 5,
            "prive": 4,
            "famille": 4,
            "maison": 4,
            "sante": 4,
            "sport": 3,
            "voyage": 3,
            "courses": 3,
            "budget": 3,
            "journal": 3,
            "habitude": 3,
            "bien etre": 3,
            "medecin": 3,
            "routine": 2,
        },
    },
    "personnes": {
        "label": "personnes",
        "folder_key": "capture_people_dir",
        "keywords": {
            "contact": 5,
            "contacts": 5,
            "appel": 4,
            "rdv": 4,
            "rendez vous": 4,
            "rencontre": 4,
            "email": 4,
            "mail": 4,
            "telephone": 4,
            "linkedin": 4,
            "profil": 3,
            "relation": 3,
            "anniversaire": 3,
            "coordonnees": 3,
        },
    },
    "lecture": {
        "label": "lecture",
        "folder_key": "capture_reading_dir",
        "keywords": {
            "lecture": 5,
            "livre": 5,
            "article": 5,
            "chapitre": 4,
            "resume": 4,
            "citation": 4,
            "auteur": 4,
            "podcast": 3,
            "video": 3,
            "source": 3,
            "page": 2,
            "extrait": 3,
            "bibliographie": 3,
        },
    },
}

EXPLICIT_CAPTURE_TAGS = {
    "pro": "pro",
    "professionnel": "pro",
    "travail": "pro",
    "perso": "perso",
    "personnel": "perso",
    "prive": "perso",
    "lecture": "lecture",
    "livre": "lecture",
    "article": "lecture",
    "personne": "personnes",
    "personnes": "personnes",
    "contact": "personnes",
    "contacts": "personnes",
    "projet": "projets",
    "projets": "projets",
}

CAPTURE_FOLDER_ALIASES = {
    "pro": "capture_professional_dir",
    "professionnel": "capture_professional_dir",
    "professionnelle": "capture_professional_dir",
    "perso": "capture_personal_dir",
    "personnel": "capture_personal_dir",
    "personnelle": "capture_personal_dir",
    "projet": "capture_projects_dir",
    "projets": "capture_projects_dir",
    "personne": "capture_people_dir",
    "personnes": "capture_people_dir",
    "lecture": "capture_reading_dir",
    "lectures": "capture_reading_dir",
}

CAPTURE_CATEGORY_DASHBOARD_LINKS = {
    "projets": "[[01_Projets_Actifs/Dashboard_Projets]]",
    "pro": "[[02_Domaines/Professionnel/Dashboard_Professionnel]]",
    "perso": "[[02_Domaines/Personnel/Dashboard_Personnel]]",
    "personnes": "[[02_Domaines/Personnes/Dashboard_Personnes]]",
    "lecture": "[[04_Bibliothèque/Dashboard_Bibliotheque]]",
}

TIME_CONTEXT_RULES = {
    "Telephone": ("appeler", "appel", "telephone", "tel", "sms", "whatsapp"),
    "Ordinateur": ("ordinateur", "pc", "email", "mail", "envoyer", "ecrire", "excel", "pdf", "site"),
    "Maison": ("maison", "garage", "voiture", "ranger", "laver", "nettoyer", "course"),
    "Dehors": ("dehors", "magasin", "poste", "banque", "rdv", "rendez vous", "aller"),
    "Administratif": ("administratif", "document", "papier", "formulaire", "assurance", "mutuelle", "onem"),
    "Travail": ("travail", "professionnel", "client", "ecole", "enseignant", "cours", "eleve"),
    "Sante": ("sante", "medecin", "dentiste", "sport", "pharmacie", "rdv medical"),
    "Famille / Personnes": ("famille", "personne", "contact", "ami", "mere", "pere", "enfant"),
    "Energie basse": ("energie basse", "facile", "rapide", "5 minutes", "petite action"),
}

TIME_ACTION_KEYWORDS = (
    "appeler",
    "acheter",
    "ajouter",
    "chercher",
    "contacter",
    "creer",
    "demander",
    "envoyer",
    "faire",
    "laver",
    "mettre",
    "preparer",
    "prendre",
    "ranger",
    "relancer",
    "remplir",
    "repondre",
    "reserver",
    "trouver",
    "verifier",
)

TIME_WAITING_KEYWORDS = (
    "attend",
    "attente",
    "en attente",
    "reponse de",
    "reponse",
    "relance",
    "document attendu",
    "decision attendue",
)

TIME_INCUBATOR_KEYWORDS = (
    "idee",
    "peut etre",
    "un jour",
    "a voir",
    "a reflechir",
    "pas decide",
    "plus tard",
)

DOMAIN_RULES: dict[str, dict[str, Any]] = {
    "commandement": {
        "label": "Commandement",
        "prefixes": ("00 commandement",),
        "dashboard_title": "Cockpit de Vie",
        "keywords": ("strategie", "vision", "revue", "pilotage", "arbitrage", "manifeste"),
    },
    "projets": {
        "label": "Projets",
        "prefixes": ("01 projets actifs",),
        "dashboard_title": "Dashboard Projets",
        "keywords": ("projet", "roadmap", "livrable", "sprint", "objectif", "execution"),
    },
    "professionnel": {
        "label": "Professionnel",
        "prefixes": ("02 domaines professionnel",),
        "dashboard_title": "Dashboard Professionnel",
        "keywords": ("client", "travail", "vente", "reunion", "business", "entreprise"),
    },
    "personnel": {
        "label": "Personnel",
        "prefixes": ("02 domaines personnel",),
        "dashboard_title": "Dashboard Personnel",
        "keywords": ("personnel", "routine", "journal", "identite", "bien etre"),
    },
    "famille": {
        "label": "Famille",
        "prefixes": ("02 domaines famille",),
        "dashboard_title": "Dashboard Famille",
        "keywords": ("famille", "parent", "enfant", "couple", "maisonnee"),
    },
    "finance": {
        "label": "Finance",
        "prefixes": ("02 domaines finance",),
        "dashboard_title": "Dashboard Finance",
        "keywords": ("budget", "finance", "cash", "depense", "epargne", "facture"),
    },
    "sante": {
        "label": "Sante",
        "prefixes": ("02 domaines sante",),
        "dashboard_title": "Dashboard Sante",
        "keywords": ("sante", "sport", "medecin", "sommeil", "energie", "habitude"),
    },
    "maison": {
        "label": "Maison",
        "prefixes": ("02 domaines maison",),
        "dashboard_title": "Dashboard Maison",
        "keywords": ("maison", "logement", "entretien", "travaux", "terrasse"),
    },
    "administratif": {
        "label": "Administratif",
        "prefixes": ("02 domaines administratif",),
        "dashboard_title": "Dashboard Administratif",
        "keywords": ("administratif", "document", "assurance", "impot", "contrat", "dossier"),
    },
    "personnes": {
        "label": "Personnes",
        "prefixes": ("02 domaines personnes",),
        "dashboard_title": "Dashboard Personnes",
        "keywords": ("contact", "relation", "reseau", "personne", "appel", "rdv"),
    },
    "journal": {
        "label": "Journal",
        "prefixes": ("02 domaines journal",),
        "dashboard_title": "Guide des revues",
        "keywords": ("journal", "quotidien", "review", "revue", "jour"),
    },
    "bibliotheque": {
        "label": "Bibliotheque",
        "prefixes": ("04 bibliotheque",),
        "dashboard_title": "Dashboard Bibliotheque",
        "keywords": ("lecture", "livre", "article", "reference", "formation", "source"),
    },
    "systeme": {
        "label": "Systeme",
        "prefixes": ("99 systeme",),
        "dashboard_title": "Hub Nanobot x Obsidian",
        "keywords": ("systeme", "nanobot", "obsidian", "memoire", "workflow", "outil"),
    },
}

CENTRAL_RELATION_TITLES = (
    "Cockpit de Vie",
    "Hub Nanobot x Obsidian",
    "Dashboard Temps",
    "Guide des revues",
    "Relations Nanobot",
)


def now_local() -> datetime:
    return datetime.now().astimezone()


# ---------------------------------------------------------------------------
# Filesystem safety helpers — Windows MAX_PATH (260 chars) and permission
# errors must not crash the bridge. Inaccessible files are skipped silently.
# Extra-long paths typically live in `05_Archives/` snapshots.
# ---------------------------------------------------------------------------

ARCHIVE_DIRS_DEFAULT: tuple[str, ...] = ("05_Archives/",)


def _safe_stat(path: Path) -> Any:
    try:
        return path.stat()
    except (FileNotFoundError, OSError):
        return None


def _safe_path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _safe_read_text(path: Path, encoding: str = "utf-8", errors: str = "replace") -> str:
    try:
        return path.read_text(encoding=encoding, errors=errors)
    except (FileNotFoundError, OSError):
        return ""


def _archive_exclusions(config: dict[str, Any]) -> tuple[str, ...]:
    raw = config.get("archive_exclusions") or list(ARCHIVE_DIRS_DEFAULT)
    out: list[str] = []
    for item in raw:
        rel = str(item).replace("\\", "/").strip().lstrip("/")
        if not rel:
            continue
        if not rel.endswith("/"):
            rel = rel + "/"
        out.append(rel)
    return tuple(out)


def _iter_vault_md(
    root: Path, *, exclude_prefixes: tuple[str, ...] = ()
) -> Iterator[tuple[Path, str]]:
    """Yield (path, relative_posix) for each .md under root, skipping inaccessible
    paths (Windows MAX_PATH, perm denied) and any file whose relative path starts
    with one of `exclude_prefixes`. Errors are swallowed silently."""
    try:
        candidates = root.rglob("*.md")
    except OSError:
        return
    while True:
        try:
            path = next(candidates)
        except StopIteration:
            return
        except OSError:
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
        if any(relative.startswith(prefix) for prefix in exclude_prefixes):
            continue
        yield path, relative


def _iter_vault_any(
    root: Path,
    *,
    pattern: str = "*",
    exclude_prefixes: tuple[str, ...] = (),
) -> Iterator[tuple[Path, str]]:
    """Same as _iter_vault_md but for any pattern; tolerates inaccessible paths."""
    try:
        candidates = root.rglob(pattern)
    except OSError:
        return
    while True:
        try:
            path = next(candidates)
        except StopIteration:
            return
        except OSError:
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
        if any(relative.startswith(prefix) for prefix in exclude_prefixes):
            continue
        yield path, relative


def normalize_text(value: str) -> str:
    text = value.lower()
    text = (
        text.replace("à", "a")
        .replace("â", "a")
        .replace("ä", "a")
        .replace("ç", "c")
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("ë", "e")
        .replace("î", "i")
        .replace("ï", "i")
        .replace("ô", "o")
        .replace("ö", "o")
        .replace("ù", "u")
        .replace("û", "u")
        .replace("ü", "u")
        .replace("ÿ", "y")
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', " ", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "Sans titre"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except Exception:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def discover_vault_path() -> Path:
    data = read_json(APPDATA_OBSIDIAN)
    vaults = data.get("vaults") or {}
    if isinstance(vaults, dict):
        open_first: Path | None = None
        any_first: Path | None = None
        for item in vaults.values():
            if not isinstance(item, dict):
                continue
            path_value = str(item.get("path") or "").strip()
            if not path_value:
                continue
            candidate = Path(path_value)
            if any_first is None:
                any_first = candidate
            if item.get("open"):
                open_first = candidate
                break
        if open_first is not None:
            return open_first
        if any_first is not None:
            return any_first
    return Path(r"C:\Users\user\Mon Drive\ARCHITECTE_SYSTEM")


def default_config() -> dict[str, Any]:
    vault_path = discover_vault_path()
    return {
        "vault_path": str(vault_path),
        "vault_name": vault_path.name,
        "cockpit_note": "00_Commandement/Cockpit_de_Vie.md",
        "hub_note": "00_Commandement/Hub_Nanobot_Obsidian.md",
        "brain_root": "99_Système/Nanobot",
        "brain_inbox_dir": "99_Système/Nanobot/Inbox",
        "brain_memory_dir": "99_Système/Nanobot/Memoire",
        "brain_relations_dir": "99_Système/Nanobot/Relations",
        "imports_dir": "04_Bibliothèque/Imports_Nanobot",
        "attachments_dir": "99_Système/Pièces_Jointes/Nanobot",
        "capture_projects_dir": "01_Projets_Actifs/En_Cours/Captures_Nanobot",
        "capture_professional_dir": "02_Domaines/Professionnel/Nanobot",
        "capture_personal_dir": "02_Domaines/Personnel/Nanobot",
        "capture_people_dir": "02_Domaines/Personnes/Nanobot",
        "capture_reading_dir": "04_Bibliothèque/Lectures_Nanobot",
        "templates_dir": "99_Système/Templates",
        "time_root": "00_Commandement/Temps",
        "time_templates_dir": "99_Système/Templates/Temps",
        "time_dashboard": "00_Commandement/Temps/Dashboard_Temps.md",
        "time_today": "00_Commandement/Temps/Aujourd_hui.md",
        "time_week": "00_Commandement/Temps/Cette_Semaine.md",
        "time_next_actions": "00_Commandement/Temps/Prochaines_Actions.md",
        "time_waiting": "00_Commandement/Temps/En_Attente.md",
        "time_deadlines": "00_Commandement/Temps/Echeances.md",
        "time_incubator": "00_Commandement/Temps/Incubateur.md",
        "time_horizons": "00_Commandement/Temps/Horizons.md",
        "daily_dir": "02_Domaines/Journal",
        "capture_template": "99_Système/Templates/Capture_Nanobot.md",
        "import_template": "99_Système/Templates/Source_Importee_Nanobot.md",
        "archive_exclusions": list(ARCHIVE_DIRS_DEFAULT),
    }


def load_config() -> dict[str, Any]:
    payload = default_config()
    existing = read_json(CONFIG_PATH)
    if existing:
        payload.update(existing)
    payload["vault_path"] = str(Path(str(payload["vault_path"])).expanduser())
    payload["vault_name"] = payload.get("vault_name") or Path(payload["vault_path"]).name
    write_json(CONFIG_PATH, payload)
    return payload


def vault_path(config: dict[str, Any]) -> Path:
    return Path(str(config["vault_path"]))


def resolve_vault_relative(config: dict[str, Any], key_or_value: str) -> Path:
    alias_key = str(key_or_value).strip().lower()
    if alias_key in CAPTURE_FOLDER_ALIASES:
        key_or_value = CAPTURE_FOLDER_ALIASES[alias_key]
    relative = str(config.get(key_or_value, key_or_value))
    return vault_path(config) / Path(relative)


def ensure_directories(config: dict[str, Any]) -> None:
    root = vault_path(config)
    root.mkdir(parents=True, exist_ok=True)
    for key in MANAGED_DIR_KEYS:
        resolve_vault_relative(config, key).mkdir(parents=True, exist_ok=True)
    resolve_vault_relative(config, "templates_dir").mkdir(parents=True, exist_ok=True)
    resolve_vault_relative(config, "daily_dir").mkdir(parents=True, exist_ok=True)
    (root / ".obsidian").mkdir(parents=True, exist_ok=True)


def managed_relative_prefixes(config: dict[str, Any]) -> list[str]:
    prefixes: list[str] = []
    for key in (
        "brain_root",
        "imports_dir",
        "capture_projects_dir",
        "capture_professional_dir",
        "capture_personal_dir",
        "capture_people_dir",
        "capture_reading_dir",
    ):
        relative = Path(str(config[key])).as_posix().rstrip("/") + "/"
        if relative not in prefixes:
            prefixes.append(relative)
    return prefixes


def managed_note_relatives(config: dict[str, Any]) -> set[str]:
    return {
        Path(str(config["cockpit_note"])).as_posix(),
        Path(str(config["hub_note"])).as_posix(),
        "00_Commandement/Temps/Dashboard_Temps.md",
        "00_Commandement/Temps/Aujourd_hui.md",
        "00_Commandement/Temps/Cette_Semaine.md",
        "00_Commandement/Temps/Prochaines_Actions.md",
        "00_Commandement/Temps/En_Attente.md",
        "00_Commandement/Temps/Echeances.md",
        "00_Commandement/Temps/Incubateur.md",
        "00_Commandement/Temps/Horizons.md",
        "00_Commandement/Temps/Rituels_Temps.md",
        "00_Commandement/Revues/Guide_Revues.md",
        "01_Projets_Actifs/Dashboard_Projets.md",
        "02_Domaines/Professionnel/Dashboard_Professionnel.md",
        "02_Domaines/Personnel/Dashboard_Personnel.md",
        "02_Domaines/Famille/Dashboard_Famille.md",
        "02_Domaines/Finance/Dashboard_Finance.md",
        "02_Domaines/Santé/Dashboard_Sante.md",
        "02_Domaines/Maison/Dashboard_Maison.md",
        "02_Domaines/Administratif/Dashboard_Administratif.md",
        "02_Domaines/Personnes/Dashboard_Personnes.md",
        "04_Bibliothèque/Dashboard_Bibliotheque.md",
    }


def is_managed_relative(config: dict[str, Any], relative: str) -> bool:
    relative = relative.replace("\\", "/")
    if relative in managed_note_relatives(config):
        return True
    return any(relative.startswith(prefix) for prefix in managed_relative_prefixes(config))


def render_frontmatter(payload: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - \"{str(item).replace(chr(34), chr(39))}\"")
        else:
            text = str(value).replace('"', "'")
            lines.append(f'{key}: "{text}"')
    lines.append("---")
    return "\n".join(lines)


def read_markdown(path: Path) -> tuple[dict[str, Any], str]:
    if not _safe_path_exists(path):
        return {}, ""
    raw = _safe_read_text(path)
    if not raw or not raw.startswith("---\n"):
        return {}, raw
    parts = raw.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, raw
    frontmatter_block = parts[0][4:]
    body = parts[1]
    metadata: dict[str, Any] = {}
    current_key: str | None = None
    for line in frontmatter_block.splitlines():
        stripped = line.rstrip()
        if not stripped:
            continue
        if stripped.startswith("  - ") and current_key:
            metadata.setdefault(current_key, []).append(stripped[4:].strip().strip('"'))
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        if not value:
            metadata[current_key] = []
            continue
        metadata[current_key] = value.strip('"')
    return metadata, body.lstrip("\n")


def write_markdown(path: Path, metadata: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_body = body.rstrip() + "\n"
    if metadata:
        text = render_frontmatter(metadata) + "\n\n" + cleaned_body
    else:
        text = cleaned_body
    path.write_text(text, encoding="utf-8")


def section_with_markers(name: str, body: str) -> str:
    return f"<!-- NANOBOT:{name}:START -->\n{body.rstrip()}\n<!-- NANOBOT:{name}:END -->"


def update_managed_section(text: str, name: str, body: str) -> str:
    pattern = re.compile(
        rf"<!-- NANOBOT:{re.escape(name)}:START -->.*?<!-- NANOBOT:{re.escape(name)}:END -->",
        flags=re.DOTALL,
    )
    block = section_with_markers(name, body)
    if pattern.search(text):
        updated = pattern.sub(block, text)
    else:
        updated = text.rstrip() + "\n\n" + block + "\n"
    return updated.strip() + "\n"


def get_managed_section(text: str, name: str) -> str | None:
    pattern = re.compile(
        rf"<!-- NANOBOT:{re.escape(name)}:START -->\s*(.*?)\s*<!-- NANOBOT:{re.escape(name)}:END -->",
        flags=re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip()


def strip_managed_sections(text: str) -> str:
    return re.sub(
        r"<!-- NANOBOT:[A-Z_]+:START -->.*?<!-- NANOBOT:[A-Z_]+:END -->",
        "",
        text,
        flags=re.DOTALL,
    ).strip()


def extract_wikilinks(text: str) -> list[str]:
    links: list[str] = []
    for raw in re.findall(r"\[\[([^\]]+)\]\]", text):
        target = raw.split("|", 1)[0].split("#", 1)[0].strip()
        if target and target not in links:
            links.append(target)
    return links


def extract_tags(text: str) -> list[str]:
    tags = []
    for raw in re.findall(r"#([A-Za-z0-9_\-/]+)", text):
        tag = raw.strip().lower()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def candidate_keywords(title: str, body: str, tags: list[str], path_hint: str = "") -> set[str]:
    tokens = set()
    source = " ".join([title, body[:4000], path_hint, " ".join(tags)])
    for token in normalize_text(source).split():
        if len(token) < 3 or token in STOP_WORDS:
            continue
        tokens.add(token)
    return tokens


def note_title_from_path(path: Path, body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return path.stem


def normalized_relative(relative: str) -> str:
    return normalize_text(relative.replace("\\", "/").replace("/", " "))


def note_target(relative: str) -> str:
    return relative[:-3] if relative.endswith(".md") else relative


def detect_primary_domain(relative: str) -> str | None:
    hint = normalized_relative(relative)
    for key, rule in DOMAIN_RULES.items():
        for prefix in rule["prefixes"]:
            if hint.startswith(prefix):
                return key
    return None


def infer_focus_domains(title: str, body: str, tags: list[str], relative: str) -> list[str]:
    source = normalize_text(" ".join([title, body[:4000], " ".join(tags), relative]))
    ranked: list[tuple[int, str]] = []
    primary = detect_primary_domain(relative)
    for key, rule in DOMAIN_RULES.items():
        score = 0
        for keyword in rule["keywords"]:
            if keyword in source:
                score += 2
        if primary == key:
            score += 6
        if score > 0:
            ranked.append((score, key))
    ranked.sort(reverse=True)
    ordered: list[str] = []
    if primary:
        ordered.append(primary)
    for _, key in ranked:
        if key not in ordered:
            ordered.append(key)
        if len(ordered) >= 3:
            break
    return ordered


def note_reference_tokens(note: dict[str, Any]) -> set[str]:
    return {
        normalize_text(note["title"]),
        normalize_text(Path(note["relative"]).stem),
        normalize_text(note_target(note["relative"])),
    }


def note_title_mentioned(source: dict[str, Any], candidate: dict[str, Any]) -> bool:
    haystack = source.get("normalized_text", "")
    for token in note_reference_tokens(candidate):
        if token and len(token) >= 8 and token in haystack:
            return True
    return False


def build_note_indices(notes: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_relative = {item["relative"]: item for item in notes}
    by_title = {normalize_text(item["title"]): item for item in notes}
    return by_relative, by_title


def collect_notes(config: dict[str, Any]) -> list[dict[str, Any]]:
    root = vault_path(config)
    templates_prefix = str(Path(str(config["templates_dir"])).as_posix()).rstrip("/") + "/"
    skip_prefixes = (".obsidian/", templates_prefix) + _archive_exclusions(config)
    notes: list[dict[str, Any]] = []
    for path, relative in _iter_vault_md(root, exclude_prefixes=skip_prefixes):
        if "_BACKUP" in relative or "/_BACKUP" in relative:
            continue
        stat = _safe_stat(path)
        if stat is None:
            continue
        metadata, body = read_markdown(path)
        plain_body = strip_managed_sections(body)
        title = str(metadata.get("title") or note_title_from_path(path, plain_body))
        tags = []
        if isinstance(metadata.get("tags"), list):
            tags.extend(str(item) for item in metadata["tags"])
        tags.extend(extract_tags(plain_body))
        tags = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
        primary_domain = detect_primary_domain(relative)
        focus_domains = infer_focus_domains(title, plain_body, tags, relative)
        existing_links = extract_wikilinks(plain_body)
        notes.append(
            {
                "path": path,
                "relative": relative,
                "title": title,
                "tags": tags,
                "body": plain_body,
                "raw_body": body,
                "keywords": candidate_keywords(title, plain_body, tags, relative),
                "normalized_text": normalize_text(" ".join([title, plain_body[:4000], relative, " ".join(tags)])),
                "existing_links": existing_links,
                "existing_link_tokens": {normalize_text(item) for item in existing_links},
                "primary_domain": primary_domain,
                "focus_domains": focus_domains,
                "updated": stat.st_mtime,
            }
        )
    return notes


def similarity_score(source: dict[str, Any], candidate: dict[str, Any]) -> int:
    overlap = source["keywords"] & candidate["keywords"]
    tag_overlap = set(source["tags"]) & set(candidate["tags"])
    title_overlap = candidate_keywords(source["title"], "", [], "") & candidate_keywords(candidate["title"], "", [], "")
    score = len(overlap) + (len(tag_overlap) * 3) + (len(title_overlap) * 4)
    if source["relative"].split("/")[0] == candidate["relative"].split("/")[0]:
        score += 1
    return score


def find_related_notes(config: dict[str, Any], note_path: Path, limit: int = 5) -> list[dict[str, Any]]:
    notes = collect_notes(config)
    target = next((item for item in notes if item["path"] == note_path), None)
    if target is None:
        return []
    ranked: list[tuple[int, dict[str, Any]]] = []
    for item in notes:
        if item["path"] == note_path:
            continue
        score = similarity_score(target, item)
        if score <= 0:
            continue
        ranked.append((score, item))
    ranked.sort(key=lambda pair: (pair[0], pair[1]["updated"]), reverse=True)
    return [item for _, item in ranked[:limit]]


def update_related_section(config: dict[str, Any], note_path: Path) -> None:
    metadata, body = read_markdown(note_path)
    related = find_related_notes(config, note_path)
    if related:
        lines = ["## Liens suggérés"]
        for item in related:
            lines.append(f"- [[{item['relative'][:-3]}|{item['title']}]]")
        managed = "\n".join(lines)
    else:
        managed = "## Liens suggérés\n- Aucun lien suggéré pour l'instant."
    write_markdown(note_path, metadata, update_managed_section(body, "RELATED", managed))


def find_note_by_title(notes_by_title: dict[str, dict[str, Any]], title: str) -> dict[str, Any] | None:
    return notes_by_title.get(normalize_text(title))


def build_navigation_targets(
    config: dict[str, Any],
    note: dict[str, Any],
    notes_by_relative: dict[str, dict[str, Any]],
    notes_by_title: dict[str, dict[str, Any]],
) -> list[tuple[dict[str, Any], str]]:
    relations_relative = (
        Path(str(config["brain_relations_dir"])).as_posix().rstrip("/") + "/Relations_Nanobot.md"
    )
    candidate_relatives: list[tuple[str, str]] = [
        (Path(str(config["cockpit_note"])).as_posix(), "vue d'ensemble"),
        (Path(str(config["hub_note"])).as_posix(), "centre Nanobot"),
        (relations_relative, "carte transversale"),
    ]

    seen_domains: set[str] = set()
    for domain_key in note.get("focus_domains") or []:
        rule = DOMAIN_RULES.get(domain_key)
        if not rule:
            continue
        dashboard_title = str(rule.get("dashboard_title") or "").strip()
        if not dashboard_title or dashboard_title in CENTRAL_RELATION_TITLES:
            continue
        dashboard_note = find_note_by_title(notes_by_title, dashboard_title)
        if dashboard_note and dashboard_note["relative"] != note["relative"] and domain_key not in seen_domains:
            candidate_relatives.append((dashboard_note["relative"], f"pilotage {rule['label'].lower()}"))
            seen_domains.add(domain_key)

    results: list[tuple[dict[str, Any], str]] = []
    seen_relatives: set[str] = set()
    for relative, reason in candidate_relatives:
        item = notes_by_relative.get(relative)
        if item is None or item["relative"] == note["relative"]:
            continue
        if item["relative"] in seen_relatives:
            continue
        results.append((item, reason))
        seen_relatives.add(item["relative"])
        if len(results) >= 5:
            break
    return results


def candidate_already_linked(source: dict[str, Any], candidate: dict[str, Any]) -> bool:
    existing = source.get("existing_link_tokens") or set()
    return bool(existing & note_reference_tokens(candidate))


def relation_insights(source: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    overlap = sorted(token for token in (source["keywords"] & candidate["keywords"]) if token not in STOP_WORDS)
    source_tags = {normalize_text(tag) for tag in source["tags"]} - GENERIC_RELATION_TAGS
    candidate_tags = {normalize_text(tag) for tag in candidate["tags"]} - GENERIC_RELATION_TAGS
    tag_overlap = sorted(source_tags & candidate_tags)
    title_overlap = sorted(
        token
        for token in (
            candidate_keywords(source["title"], "", [], "") & candidate_keywords(candidate["title"], "", [], "")
        )
        if token not in STOP_WORDS
    )
    shared_domains = [key for key in source.get("focus_domains", []) if key in candidate.get("focus_domains", [])]

    score = 0
    reasons: list[str] = []
    if overlap:
        score += min(len(overlap), 6)
        reasons.append("mots: " + ", ".join(overlap[:3]))
    if tag_overlap:
        score += len(tag_overlap) * 3
        reasons.append("tags: " + ", ".join(tag_overlap[:2]))
    if title_overlap:
        score += len(title_overlap) * 4
        reasons.append("titre proche")
    if shared_domains:
        score += 3
        labels = [str(DOMAIN_RULES[key]["label"]).lower() for key in shared_domains[:2] if key in DOMAIN_RULES]
        if labels:
            reasons.append("axes: " + ", ".join(labels))
    if source.get("primary_domain") and source.get("primary_domain") == candidate.get("primary_domain"):
        score += 2
        reasons.append("meme domaine")
    if source["relative"].split("/")[0] == candidate["relative"].split("/")[0]:
        score += 1
    if note_title_mentioned(source, candidate):
        score += 5
        reasons.append("mention du sujet")

    return {
        "score": score,
        "reasons": reasons,
        "cross_domain": source.get("primary_domain") != candidate.get("primary_domain"),
        "already_linked": candidate_already_linked(source, candidate),
    }


def find_related_notes(
    config: dict[str, Any],
    note_path: Path,
    limit: int = 6,
    notes: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    notes = notes or collect_notes(config)
    target = next((item for item in notes if item["path"] == note_path), None)
    if target is None:
        return []

    ranked: list[dict[str, Any]] = []
    for item in notes:
        if item["path"] == note_path:
            continue
        insight = relation_insights(target, item)
        if insight["score"] <= 0 or insight["already_linked"]:
            continue
        ranked.append(
            {
                "note": item,
                "score": insight["score"],
                "reasons": insight["reasons"],
                "cross_domain": insight["cross_domain"],
            }
        )

    ranked.sort(key=lambda entry: (entry["score"], entry["note"]["updated"]), reverse=True)
    same_domain = [entry for entry in ranked if not entry["cross_domain"]]
    cross_domain = [entry for entry in ranked if entry["cross_domain"]]

    selected: list[dict[str, Any]] = []
    for bucket, bucket_limit in ((same_domain, 2), (cross_domain, 3)):
        for entry in bucket[:bucket_limit]:
            if entry not in selected:
                selected.append(entry)
    for entry in ranked:
        if entry not in selected:
            selected.append(entry)
        if len(selected) >= limit:
            break
    return selected[:limit]


def render_navigation_section(
    config: dict[str, Any],
    note: dict[str, Any],
    notes_by_relative: dict[str, dict[str, Any]],
    notes_by_title: dict[str, dict[str, Any]],
) -> str:
    links = build_navigation_targets(config, note, notes_by_relative, notes_by_title)
    if not links:
        return "## Hubs utiles\n- Aucun hub additionnel pour l'instant."
    lines = ["## Hubs utiles"]
    for item, reason in links:
        lines.append(f"- [[{note_target(item['relative'])}|{item['title']}]] - {reason}")
    return "\n".join(lines)


def render_related_section(
    config: dict[str, Any],
    note: dict[str, Any],
    notes: list[dict[str, Any]],
) -> str:
    related = find_related_notes(config, note["path"], notes=notes)
    if not related:
        return "## Passerelles utiles\n- Aucune passerelle utile pour l'instant."

    same_domain = [entry for entry in related if not entry["cross_domain"]]
    cross_domain = [entry for entry in related if entry["cross_domain"]]
    lines = ["## Passerelles utiles"]
    if same_domain:
        lines.extend(["", "### Meme domaine"])
        for entry in same_domain:
            reason = "; ".join(entry["reasons"][:2]) if entry["reasons"] else "proximite forte"
            item = entry["note"]
            lines.append(f"- [[{note_target(item['relative'])}|{item['title']}]] - {reason}")
    if cross_domain:
        lines.extend(["", "### Traversees"])
        for entry in cross_domain:
            reason = "; ".join(entry["reasons"][:2]) if entry["reasons"] else "pont transversal"
            item = entry["note"]
            lines.append(f"- [[{note_target(item['relative'])}|{item['title']}]] - {reason}")
    return "\n".join(lines)


def update_related_section(
    config: dict[str, Any],
    note_path: Path,
    notes: list[dict[str, Any]] | None = None,
) -> None:
    notes = notes or collect_notes(config)
    note = next((item for item in notes if item["path"] == note_path), None)
    if note is None:
        return
    notes_by_relative, notes_by_title = build_note_indices(notes)
    metadata, body = read_markdown(note_path)
    updated_body = update_managed_section(
        body,
        "NAVIGATION",
        render_navigation_section(config, note, notes_by_relative, notes_by_title),
    )
    updated_body = update_managed_section(
        updated_body,
        "RELATED",
        render_related_section(config, note, notes),
    )
    if updated_body == body:
        return
    if metadata:
        metadata = dict(metadata)
        metadata["updated"] = now_local().isoformat(timespec="seconds")
    write_markdown(note_path, metadata, updated_body)


def choose_unique_note_path(folder: Path, title: str) -> Path:
    candidate = folder / f"{safe_filename(title)}.md"
    if not candidate.exists():
        return candidate
    stamp = now_local().strftime("%Y%m%d-%H%M%S")
    return folder / f"{safe_filename(title)} - {stamp}.md"


def build_capture_body(title: str, content: str, tags: list[str], source: str | None = None) -> str:
    lines = [f"# {title}", ""]
    if source:
        lines.extend(["## Source", f"- {source}", ""])
    if tags:
        lines.extend(["## Tags", "- " + "\n- ".join(tags), ""])
    lines.extend(["## Contenu", content.strip() or "-"])
    return "\n".join(lines).rstrip() + "\n"


def derive_title(content: str) -> str:
    text = re.sub(r"\s+", " ", content.strip())
    if not text:
        return "Capture Nanobot"
    sentence = re.split(r"[.!?]", text, maxsplit=1)[0].strip()
    words = sentence.split()
    title = " ".join(words[:8]).strip()
    return safe_filename(title or "Capture Nanobot")


def explicit_capture_category(tags: list[str]) -> str | None:
    for tag in tags:
        normalized = normalize_text(tag)
        if normalized in EXPLICIT_CAPTURE_TAGS:
            return EXPLICIT_CAPTURE_TAGS[normalized]
    return None


def classify_capture(
    config: dict[str, Any],
    *,
    title: str,
    content: str,
    tags: list[str] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    tags = tags or []
    explicit = explicit_capture_category(tags)
    if explicit:
        rule = CAPTURE_CATEGORY_RULES[explicit]
        return {
            "category": explicit,
            "label": rule["label"],
            "folder_key": rule["folder_key"],
            "folder_path": resolve_vault_relative(config, rule["folder_key"]),
            "score": 100,
            "confidence": "explicit",
            "reasons": ["tag explicite"],
        }

    normalized = normalize_text(" ".join([title, content, source or "", " ".join(tags)]))
    scores: dict[str, int] = {}
    reasons: dict[str, list[str]] = {}
    email_or_phone = bool(re.search(r"[@+]|(?:\b\d{2,}\b.*){2,}", content))

    for category in CAPTURE_CATEGORY_ORDER:
        rule = CAPTURE_CATEGORY_RULES[category]
        score = 0
        why: list[str] = []
        for keyword, weight in rule["keywords"].items():
            if keyword in normalized:
                score += int(weight)
                if len(why) < 4:
                    why.append(keyword)
        if category == "personnes" and email_or_phone:
            score += 4
            if len(why) < 4:
                why.append("coordonnees")
        if category == "lecture" and re.search(r"\b(page|chapitre|citation|auteur)\b", normalized):
            score += 3
            if len(why) < 4:
                why.append("structure lecture")
        if category == "projets" and re.search(r"\b(todo|next|prochaine etape|livrable|deadline)\b", normalized):
            score += 3
            if len(why) < 4:
                why.append("signal action")
        scores[category] = score
        reasons[category] = why

    best_category = max(
        CAPTURE_CATEGORY_ORDER,
        key=lambda category: (scores.get(category, 0), -CAPTURE_CATEGORY_ORDER.index(category)),
    )
    best_score = scores.get(best_category, 0)
    if best_score <= 0:
        best_category = "projets"
        reasons[best_category] = ["fallback actionnable"]
    rule = CAPTURE_CATEGORY_RULES[best_category]
    confidence = "haute" if best_score >= 6 else "moyenne" if best_score >= 3 else "faible"
    return {
        "category": best_category,
        "label": rule["label"],
        "folder_key": rule["folder_key"],
        "folder_path": resolve_vault_relative(config, rule["folder_key"]),
        "score": best_score,
        "confidence": confidence,
        "reasons": reasons.get(best_category) or ["fallback actionnable"],
    }


def extract_first_iso_date(text: str) -> str | None:
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    return match.group(1) if match else None


def detect_time_context(normalized: str) -> str:
    for context, keywords in TIME_CONTEXT_RULES.items():
        for keyword in keywords:
            if normalize_text(keyword) in normalized:
                return context
    return "A clarifier"


def classify_time_signal(title: str, content: str, tags: list[str] | None = None) -> dict[str, Any] | None:
    tags = tags or []
    normalized = normalize_text(" ".join([title, content, " ".join(tags)]))
    deadline = extract_first_iso_date(content) or extract_first_iso_date(title)

    if any(normalize_text(keyword) in normalized for keyword in TIME_INCUBATOR_KEYWORDS):
        return {"status": "incubateur", "target": "time_incubator", "heading": "Idees non decidees"}

    if any(normalize_text(keyword) in normalized for keyword in TIME_WAITING_KEYWORDS):
        heading = "Documents attendus" if "document" in normalized else "Decisions attendues" if "decision" in normalized else "Reponses attendues"
        return {"status": "en_attente", "target": "time_waiting", "heading": heading}

    if deadline:
        today = now_local().date()
        try:
            due_date = datetime.strptime(deadline, "%Y-%m-%d").date()
        except ValueError:
            due_date = None
        heading = "Plus tard"
        if due_date is not None:
            if today <= due_date <= today + timedelta(days=7):
                heading = "Cette semaine"
            elif due_date.strftime("%Y-%m") == today.strftime("%Y-%m"):
                heading = "Ce mois-ci"
        return {"status": "echeance", "target": "time_deadlines", "heading": heading, "deadline": deadline}

    action_signal = any(normalize_text(keyword) in normalized for keyword in TIME_ACTION_KEYWORDS)
    action_signal = action_signal or any(marker in normalized for marker in ("todo", "tache", "a faire", "prochaine action"))
    if action_signal:
        context = detect_time_context(normalized)
        return {"status": "prochaine_action", "target": "time_next_actions", "heading": context, "context": context}

    return None


def append_block_under_heading(body: str, heading: str, block: str, unique_marker: str | None = None) -> str:
    if unique_marker and unique_marker in body:
        return body
    lines = body.rstrip().splitlines()
    marker = f"## {heading}"
    block_lines = block.rstrip().splitlines()
    for index, line in enumerate(lines):
        if line.strip() != marker:
            continue
        insert_at = index + 1
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
        lines[insert_at:insert_at] = block_lines + [""]
        return "\n".join(lines).rstrip() + "\n"
    return body.rstrip() + f"\n\n{marker}\n" + block.rstrip() + "\n"


def append_time_task(
    config: dict[str, Any],
    *,
    target_key: str,
    heading: str,
    task_block: str,
    unique_marker: str,
) -> Path | None:
    target_path = resolve_vault_relative(config, target_key)
    if not target_path.exists():
        return None
    metadata, body = read_markdown(target_path)
    updated_body = append_block_under_heading(body, heading, task_block, unique_marker=unique_marker)
    if updated_body == body:
        return target_path
    if metadata:
        metadata = dict(metadata)
        metadata["updated"] = now_local().isoformat(timespec="seconds")
    write_markdown(target_path, metadata, updated_body)
    return target_path


def append_time_signal(
    config: dict[str, Any],
    *,
    note_path: Path,
    title: str,
    content: str,
    tags: list[str],
    classification: dict[str, Any] | None,
) -> list[str]:
    signal = classify_time_signal(title, content, tags)
    if not signal:
        return []

    root = vault_path(config)
    try:
        source_relative = note_path.relative_to(root).as_posix()
    except ValueError:
        source_relative = note_path.as_posix()
    source_target = note_target(source_relative)
    source_link = f"[[{source_target}|{title}]]"
    category = str((classification or {}).get("category") or "")
    domain_link = CAPTURE_CATEGORY_DASHBOARD_LINKS.get(category, "")
    context = str(signal.get("context") or signal.get("heading") or "").lower()
    status = str(signal["status"])
    deadline = str(signal.get("deadline") or "")

    lines = [f"- [ ] {title}", f"  - source: {source_link}"]
    lines.append(f"  - domaine: {domain_link}")
    lines.append("  - projet:")
    if deadline:
        lines.append(f"  - echeance: {deadline}")
    else:
        lines.append("  - echeance:")
    lines.append("  - energie:")
    lines.append(f"  - contexte: {normalize_text(context)}")
    lines.append(f"  - statut: {status}")
    task_block = "\n".join(lines)

    touched: list[str] = []
    target = append_time_task(
        config,
        target_key=str(signal["target"]),
        heading=str(signal["heading"]),
        task_block=task_block,
        unique_marker=source_target,
    )
    if target:
        touched.append(str(target.relative_to(root)))

    normalized = normalize_text(" ".join([title, content]))
    if deadline:
        try:
            due_date = datetime.strptime(deadline, "%Y-%m-%d").date()
        except ValueError:
            due_date = None
        today = now_local().date()
        if due_date == today:
            target = append_time_task(
                config,
                target_key="time_today",
                heading="A ne pas oublier",
                task_block=task_block,
                unique_marker=source_target,
            )
            if target:
                touched.append(str(target.relative_to(root)))
        elif due_date is not None and today <= due_date <= today + timedelta(days=7):
            target = append_time_task(
                config,
                target_key="time_week",
                heading="Obligations datees",
                task_block=task_block,
                unique_marker=source_target,
            )
            if target:
                touched.append(str(target.relative_to(root)))
    elif "aujourd hui" in normalized or "aujourdhui" in normalized:
        target = append_time_task(
            config,
            target_key="time_today",
            heading="A ne pas oublier",
            task_block=task_block,
            unique_marker=source_target,
        )
        if target:
            touched.append(str(target.relative_to(root)))

    return list(dict.fromkeys(touched))


def create_note(
    config: dict[str, Any],
    *,
    title: str,
    content: str,
    folder: str,
    tags: list[str] | None = None,
    source: str | None = None,
    note_type: str = "capture",
    metadata_extra: dict[str, Any] | None = None,
) -> Path:
    tags = list(dict.fromkeys((tags or []) + ["nanobot", "obsidian", note_type]))
    target_folder = resolve_vault_relative(config, folder)
    target_path = choose_unique_note_path(target_folder, title)
    timestamp = now_local().isoformat(timespec="seconds")
    metadata = {
        "title": title,
        "created": timestamp,
        "updated": timestamp,
        "source": source or "nanobot",
        "type": note_type,
        "tags": tags,
    }
    if metadata_extra:
        metadata.update(metadata_extra)
    body = build_capture_body(title, content, tags, source)
    write_markdown(target_path, metadata, body)
    update_related_section(config, target_path)
    return target_path


def ensure_templates(config: dict[str, Any]) -> None:
    capture_template = resolve_vault_relative(config, "capture_template")
    if not capture_template.exists():
        capture_template.write_text(
            "\n".join(
                [
                    "---",
                    'title: "{{title}}"',
                    'source: "nanobot"',
                    'type: "capture"',
                    "tags:",
                    '  - "nanobot"',
                    '  - "capture"',
                    "---",
                    "",
                    "# {{title}}",
                    "",
                    "## Source",
                    "- {{source}}",
                    "",
                    "## Contenu",
                    "{{content}}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    import_template = resolve_vault_relative(config, "import_template")
    if not import_template.exists():
        import_template.write_text(
            "\n".join(
                [
                    "---",
                    'title: "{{title}}"',
                    'source: "nanobot-import"',
                    'type: "import"',
                    "tags:",
                    '  - "nanobot"',
                    '  - "import"',
                    "---",
                    "",
                    "# {{title}}",
                    "",
                    "## Source",
                    "- Fichier original: {{source_path}}",
                    "- Copie dans le vault: {{vault_asset}}",
                    "",
                    "## Contenu",
                    "{{content}}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    extra_templates = {
        "99_Système/Templates/Revue_Hebdomadaire.md": "\n".join(
            [
                "# Revue Hebdomadaire : {{date}}",
                "",
                "## Victoires",
                "-",
                "",
                "## Projets",
                "- Ce qui avance",
                "- Ce qui bloque",
                "- La prochaine etape visible",
                "",
                "## Domaines de vie",
                "- Professionnel",
                "- Personnel",
                "- Famille",
                "- Finance",
                "- Santé",
                "- Maison",
                "- Administratif",
                "",
                "## Decisons",
                "-",
            ]
        )
        + "\n",
        "99_Système/Templates/Revue_Mensuelle.md": "\n".join(
            [
                "# Revue Mensuelle : {{date}}",
                "",
                "## Ce mois-ci",
                "- Ce qui a compte",
                "- Ce qui doit changer",
                "",
                "## Tableau de bord",
                "- Revenus / depenses",
                "- Energie / sante",
                "- Famille / relations",
                "- Projets / priorites",
                "",
                "## Arbitrages du mois prochain",
                "-",
            ]
        )
        + "\n",
        "99_Système/Templates/Fiche_Personne.md": "\n".join(
            [
                "# {{title}}",
                "",
                "## Identite",
                "- Role / contexte",
                "- Coordonnees",
                "",
                "## Relation",
                "- Dernier contact",
                "- Prochaine action",
                "",
                "## Notes",
                "-",
            ]
        )
        + "\n",
        "99_Système/Templates/Fiche_Finance.md": "\n".join(
            [
                "# {{title}}",
                "",
                "## Vue d'ensemble",
                "- Type de compte / enveloppe",
                "- Solde / montant",
                "",
                "## Regles",
                "- Echeances",
                "- Limites / objectifs",
                "",
                "## Notes",
                "-",
            ]
        )
        + "\n",
        "99_Système/Templates/Note_Lecture.md": "\n".join(
            [
                "# {{title}}",
                "",
                "## Source",
                "- Auteur / lien / livre",
                "",
                "## Idees cles",
                "-",
                "",
                "## Citations",
                "-",
                "",
                "## Applications",
                "-",
            ]
        )
        + "\n",
    }
    for relative, content in extra_templates.items():
        path = vault_path(config) / Path(relative)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


def enable_core_plugins(config: dict[str, Any]) -> list[str]:
    path = vault_path(config) / ".obsidian" / "core-plugins.json"
    payload = read_json(path)
    enabled: list[str] = []
    desired = {
        "file-explorer": True,
        "global-search": True,
        "switcher": True,
        "graph": True,
        "backlink": True,
        "outgoing-link": True,
        "tag-pane": True,
        "page-preview": True,
        "daily-notes": True,
        "templates": True,
        "note-composer": True,
        "command-palette": True,
        "slash-command": True,
        "editor-status": True,
        "outline": True,
        "word-count": True,
        "workspaces": True,
        "file-recovery": True,
        "properties": True,
        "bookmarks": True,
        "bases": True,
    }
    for key, value in desired.items():
        if payload.get(key) != value:
            payload[key] = value
            enabled.append(key)
    write_json(path, payload)
    return enabled


def ensure_note_if_missing(
    config: dict[str, Any],
    *,
    relative_path: str,
    title: str,
    tags: list[str],
    body: str,
    note_type: str = "life-os",
) -> Path:
    path = vault_path(config) / Path(relative_path)
    if not path.exists():
        timestamp = now_local().isoformat(timespec="seconds")
        metadata = {
            "title": title,
            "created": timestamp,
            "updated": timestamp,
            "source": "nanobot-life-os",
            "type": note_type,
            "tags": list(dict.fromkeys(tags + ["nanobot", "obsidian", "life-os"])),
        }
        write_markdown(path, metadata, body)
    return path


def render_dashboard_note(
    title: str,
    purpose: str,
    quick_links: list[str],
    focus_points: list[str],
    systems: list[str] | None = None,
) -> str:
    lines = [f"# {title}", "", purpose, "", "## Navigation rapide", ""]
    lines.extend(f"- {item}" for item in quick_links)
    lines.extend(["", "## Points de pilotage", ""])
    lines.extend(f"- {item}" for item in focus_points)
    if systems:
        lines.extend(["", "## Systemes a entretenir", ""])
        lines.extend(f"- {item}" for item in systems)
    return "\n".join(lines).rstrip() + "\n"


def render_cockpit_note(config: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Cockpit de Vie",
            "",
            "Centre de pilotage global pour ta vie, tes projets, tes domaines et tes ressources.",
            "",
            "## Commandement",
            "",
            f"- [[{config['hub_note'][:-3]}|Hub Nanobot x Obsidian]]",
            "- [[00_Commandement/Stratégie/Manifeste|Manifeste]]",
            "- [[00_Commandement/Revues/Guide_Revues|Guide des revues]]",
            "- [[01_Projets_Actifs/Dashboard_Projets|Dashboard Projets]]",
            "",
            "## Domaines de vie",
            "",
            "- [[02_Domaines/Professionnel/Dashboard_Professionnel|Professionnel]]",
            "- [[02_Domaines/Personnel/Dashboard_Personnel|Personnel]]",
            "- [[02_Domaines/Famille/Dashboard_Famille|Famille]]",
            "- [[02_Domaines/Finance/Dashboard_Finance|Finance]]",
            "- [[02_Domaines/Santé/Dashboard_Sante|Santé]]",
            "- [[02_Domaines/Maison/Dashboard_Maison|Maison]]",
            "- [[02_Domaines/Administratif/Dashboard_Administratif|Administratif]]",
            "- [[02_Domaines/Personnes/Dashboard_Personnes|Personnes]]",
            "",
            "## Bibliothèque et système",
            "",
            "- [[04_Bibliothèque/Dashboard_Bibliotheque|Bibliothèque]]",
            "- [[99_Système/Nanobot/Mode_Emploi_Nanobot|Mode d'emploi Nanobot]]",
            "- [[99_Système/Nanobot/Memoire/Memoire_Nanobot|Mémoire Nanobot]]",
            "",
            "## Boucles de pilotage",
            "",
            "- Quotidien: note du jour dans `02_Domaines/Journal`",
            "- Hebdomadaire: revue hebdo",
            "- Mensuel: revue mensuelle",
            "- Trimestriel: arbitrage des projets, finances, santé, famille et système",
            "",
            "## Principe",
            "",
            "Un seul coffre, plusieurs horizons: décider dans le cockpit, exécuter dans les projets, stabiliser dans les domaines, apprendre dans la bibliothèque, archiver proprement.",
        ]
    ) + "\n"


def ensure_life_os_structure(config: dict[str, Any]) -> list[Path]:
    extra_dirs = [
        "00_Commandement/Revues",
        "02_Domaines/Famille",
        "02_Domaines/Finance",
        "02_Domaines/Santé",
        "02_Domaines/Maison",
        "02_Domaines/Administratif",
        "02_Domaines/Professionnel/Clients",
        "02_Domaines/Professionnel/Réunions",
        "02_Domaines/Professionnel/Systèmes",
        "02_Domaines/Personnel/Routines",
        "02_Domaines/Personnel/Identité",
        "02_Domaines/Personnel/Bien_Être",
        "02_Domaines/Famille/Logistique",
        "02_Domaines/Famille/Souvenirs",
        "02_Domaines/Finance/Budget",
        "02_Domaines/Finance/Objectifs",
        "02_Domaines/Finance/Obligations",
        "02_Domaines/Santé/Habitudes",
        "02_Domaines/Santé/Suivi_Médical",
        "02_Domaines/Maison/Entretien",
        "02_Domaines/Maison/Projets",
        "02_Domaines/Administratif/Dossiers",
        "02_Domaines/Administratif/Démarches",
        "02_Domaines/Personnes/Contacts_Clés",
        "02_Domaines/Personnes/Suivis",
        "03_Arsenal_Technique/Playbooks",
        "04_Bibliothèque/Formations",
        "04_Bibliothèque/Références",
        "05_Archives/Projets_Terminés",
        "05_Archives/Revues_Anciennes",
    ]
    for relative in extra_dirs:
        (vault_path(config) / Path(relative)).mkdir(parents=True, exist_ok=True)

    notes: list[Path] = []
    note_specs = [
        {
            "relative_path": str(config["cockpit_note"]),
            "title": "Cockpit de Vie",
            "tags": ["dashboard", "cockpit", "life"],
            "body": render_cockpit_note(config),
        },
        {
            "relative_path": "00_Commandement/Revues/Guide_Revues.md",
            "title": "Guide des revues",
            "tags": ["review", "pilotage", "rituel"],
            "body": render_dashboard_note(
                "Guide des revues",
                "Cadre simple pour piloter la semaine, le mois et les grands arbitrages.",
                [
                    "[[99_Système/Templates/Revue_Hebdomadaire|Template revue hebdomadaire]]",
                    "[[99_Système/Templates/Revue_Mensuelle|Template revue mensuelle]]",
                    "[[00_Commandement/Cockpit_de_Vie|Cockpit de Vie]]",
                ],
                [
                    "Qu'est-ce qui avance vraiment ?",
                    "Qu'est-ce qui fuit ou se dégrade ?",
                    "Quel projet mérite plus d'énergie ?",
                    "Quel domaine de vie doit être remis sous contrôle ?",
                ],
                [
                    "Revue hebdo: projets, agenda, finances, santé, famille, administratif",
                    "Revue mensuelle: trajectoire globale, décisions, simplification, archivage",
                ],
            ),
        },
        {
            "relative_path": "01_Projets_Actifs/Dashboard_Projets.md",
            "title": "Dashboard Projets",
            "tags": ["dashboard", "projets"],
            "body": render_dashboard_note(
                "Dashboard Projets",
                "Vue d'ensemble des chantiers en cours et de leur énergie réelle.",
                [
                    "[[00_Commandement/Cockpit_de_Vie|Cockpit de Vie]]",
                    "[[01_Projets_Actifs/En_Cours/Captures_Nanobot/Mettre en place le classement automatique pro, perso,|Exemple capture projet]]",
                ],
                [
                    "Quels projets sont vraiment actifs ?",
                    "Quels projets doivent être ralentis, délégués ou archivés ?",
                    "Quel est le prochain livrable concret pour chacun ?",
                ],
            ),
        },
        {
            "relative_path": "02_Domaines/Professionnel/Dashboard_Professionnel.md",
            "title": "Dashboard Professionnel",
            "tags": ["dashboard", "professionnel"],
            "body": render_dashboard_note(
                "Dashboard Professionnel",
                "Pilotage du travail, des revenus, des opportunités et des systèmes professionnels.",
                [
                    "[[00_Commandement/Cockpit_de_Vie|Cockpit de Vie]]",
                    "[[02_Domaines/Professionnel/Clients]]",
                    "[[02_Domaines/Professionnel/Réunions]]",
                    "[[02_Domaines/Professionnel/Systèmes]]",
                ],
                [
                    "Pipeline et opportunités",
                    "Livrables et engagements",
                    "Charge réelle et capacité",
                    "Prochaines décisions business",
                ],
            ),
        },
        {
            "relative_path": "02_Domaines/Personnel/Dashboard_Personnel.md",
            "title": "Dashboard Personnel",
            "tags": ["dashboard", "personnel"],
            "body": render_dashboard_note(
                "Dashboard Personnel",
                "Espace pour identité, routines, énergie, habitudes et qualité de vie.",
                [
                    "[[00_Commandement/Cockpit_de_Vie|Cockpit de Vie]]",
                    "[[02_Domaines/Personnel/Routines]]",
                    "[[02_Domaines/Personnel/Identité]]",
                    "[[02_Domaines/Personnel/Bien_Être]]",
                ],
                [
                    "Comment va ton énergie ?",
                    "Quelles habitudes renforcent ta trajectoire ?",
                    "Qu'est-ce qui doit être simplifié ou arrêté ?",
                ],
            ),
        },
        {
            "relative_path": "02_Domaines/Famille/Dashboard_Famille.md",
            "title": "Dashboard Famille",
            "tags": ["dashboard", "famille"],
            "body": render_dashboard_note(
                "Dashboard Famille",
                "Organisation familiale, responsabilités, soutien, souvenirs et logistique.",
                [
                    "[[00_Commandement/Cockpit_de_Vie|Cockpit de Vie]]",
                    "[[02_Domaines/Famille/Logistique]]",
                    "[[02_Domaines/Famille/Souvenirs]]",
                ],
                [
                    "Quels besoins familiaux demandent de l'attention ?",
                    "Quelles échéances ou déplacements arrivent ?",
                    "Quels moments importants faut-il préserver ?",
                ],
            ),
        },
        {
            "relative_path": "02_Domaines/Finance/Dashboard_Finance.md",
            "title": "Dashboard Finance",
            "tags": ["dashboard", "finance"],
            "body": render_dashboard_note(
                "Dashboard Finance",
                "Vue maître des comptes, budget, objectifs, obligations et décisions d'argent.",
                [
                    "[[00_Commandement/Cockpit_de_Vie|Cockpit de Vie]]",
                    "[[02_Domaines/Finance/Budget]]",
                    "[[02_Domaines/Finance/Objectifs]]",
                    "[[02_Domaines/Finance/Obligations]]",
                ],
                [
                    "Cash disponible et engagements proches",
                    "Budget mensuel et dépenses à surveiller",
                    "Objectifs financiers et épargne",
                    "Décisions financières à prendre ce mois-ci",
                ],
            ),
        },
        {
            "relative_path": "02_Domaines/Santé/Dashboard_Sante.md",
            "title": "Dashboard Santé",
            "tags": ["dashboard", "sante"],
            "body": render_dashboard_note(
                "Dashboard Santé",
                "Suivi santé, énergie, rendez-vous médicaux, habitudes et prévention.",
                [
                    "[[00_Commandement/Cockpit_de_Vie|Cockpit de Vie]]",
                    "[[02_Domaines/Santé/Habitudes]]",
                    "[[02_Domaines/Santé/Suivi_Médical]]",
                ],
                [
                    "Sommeil, énergie, poids, activité",
                    "Prochains rendez-vous et traitements",
                    "Prévention, sport et équilibre",
                ],
            ),
        },
        {
            "relative_path": "02_Domaines/Maison/Dashboard_Maison.md",
            "title": "Dashboard Maison",
            "tags": ["dashboard", "maison"],
            "body": render_dashboard_note(
                "Dashboard Maison",
                "Entretien, achats, améliorations et stabilité matérielle du foyer.",
                [
                    "[[00_Commandement/Cockpit_de_Vie|Cockpit de Vie]]",
                    "[[02_Domaines/Maison/Entretien]]",
                    "[[02_Domaines/Maison/Projets]]",
                ],
                [
                    "Réparations ou entretiens en attente",
                    "Achats utiles et priorités maison",
                    "Projets d'amélioration ou de confort",
                ],
            ),
        },
        {
            "relative_path": "02_Domaines/Administratif/Dashboard_Administratif.md",
            "title": "Dashboard Administratif",
            "tags": ["dashboard", "administratif"],
            "body": render_dashboard_note(
                "Dashboard Administratif",
                "Papiers, démarches, échéances et obligations pratiques.",
                [
                    "[[00_Commandement/Cockpit_de_Vie|Cockpit de Vie]]",
                    "[[02_Domaines/Administratif/Dossiers]]",
                    "[[02_Domaines/Administratif/Démarches]]",
                ],
                [
                    "Documents critiques",
                    "Démarches en cours",
                    "Dates limites et renouvellements",
                ],
            ),
        },
        {
            "relative_path": "02_Domaines/Personnes/Dashboard_Personnes.md",
            "title": "Dashboard Personnes",
            "tags": ["dashboard", "personnes"],
            "body": render_dashboard_note(
                "Dashboard Personnes",
                "Réseau, relations, contacts clés et suivis importants.",
                [
                    "[[00_Commandement/Cockpit_de_Vie|Cockpit de Vie]]",
                    "[[02_Domaines/Personnes/Contacts_Clés]]",
                    "[[02_Domaines/Personnes/Suivis]]",
                ],
                [
                    "Personnes à recontacter",
                    "Suivis en attente",
                    "Relations à nourrir ou clarifier",
                ],
            ),
        },
        {
            "relative_path": "04_Bibliothèque/Dashboard_Bibliotheque.md",
            "title": "Dashboard Bibliothèque",
            "tags": ["dashboard", "bibliotheque"],
            "body": render_dashboard_note(
                "Dashboard Bibliothèque",
                "Base de connaissances: lectures, formations, références et imports.",
                [
                    "[[00_Commandement/Cockpit_de_Vie|Cockpit de Vie]]",
                    "[[04_Bibliothèque/Imports_Nanobot]]",
                    "[[04_Bibliothèque/Lectures_Nanobot]]",
                    "[[04_Bibliothèque/Formations]]",
                    "[[04_Bibliothèque/Références]]",
                ],
                [
                    "Que lis-tu ou apprends-tu en ce moment ?",
                    "Quelles références sont devenues essentielles ?",
                    "Quelles notes doivent être synthétisées ou reliées ?",
                ],
            ),
        },
    ]

    for spec in note_specs:
        notes.append(
            ensure_note_if_missing(
                config,
                relative_path=spec["relative_path"],
                title=spec["title"],
                tags=spec["tags"],
                body=spec["body"],
            )
        )

    for path in notes:
        update_related_section(config, path)
    return notes


def render_hub_note(config: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Hub Nanobot x Obsidian",
            "",
            "Ce coffre devient le second cerveau opere par toi et par Nanobot.",
            "",
            "## Acces rapide",
            "",
            f"- Cockpit de vie: [[{config['cockpit_note'][:-3]}|Cockpit de Vie]]",
            f"- Memoire Nanobot: [[{config['brain_memory_dir']}/Memoire_Nanobot]]",
            f"- Snapshots memoire: [[{config['brain_memory_dir']}/Snapshots_Nanobot]]",
            f"- Carte des liens: [[{config['brain_relations_dir']}/Relations_Nanobot]]",
            f"- Mode d'emploi: [[{config['brain_root']}/Mode_Emploi_Nanobot]]",
            "",
            "## Flux de travail",
            "",
            "- Capture rapide avec classement automatique vers pro, perso, lecture, personnes ou projets.",
            "- Import de PDF, images et markdown dans la bibliotheque avec extraction texte.",
            "- Synchronisation de la memoire operationnelle Nanobot dans Obsidian.",
            "- Liens suggeres automatiquement entre les notes gerees par Nanobot et le reste du vault.",
            "",
            "## Dossiers strategiques",
            "",
            f"- Inbox Nanobot: `{config['brain_inbox_dir']}`",
            f"- Memoire Nanobot: `{config['brain_memory_dir']}`",
            f"- Relations: `{config['brain_relations_dir']}`",
            f"- Captures projets: `{config['capture_projects_dir']}`",
            f"- Captures pro: `{config['capture_professional_dir']}`",
            f"- Captures perso: `{config['capture_personal_dir']}`",
            f"- Captures personnes: `{config['capture_people_dir']}`",
            f"- Captures lecture: `{config['capture_reading_dir']}`",
            f"- Imports documentaires: `{config['imports_dir']}`",
            f"- Pieces jointes: `{config['attachments_dir']}`",
            "",
            "## Usages concrets",
            "",
            "- Transformer un PDF en note markdown exploitable.",
            "- Importer une photo avec OCR pour retrouver le texte plus tard.",
            "- Ecrire des notes pro, perso, lecture, projets et checkpoints.",
            "- Relier tes notes a la memoire de Nanobot pour eviter de repartir de zero.",
            "",
            "## Idee directrice",
            "",
            "Obsidian sert de cerveau externe lisible, durable et relie. Nanobot sert de bras, de moteur de capture, de tri, d'import et de rappel contextuel.",
        ]
    ) + "\n"


def render_mode_emploi(config: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Mode d'emploi Nanobot",
            "",
            "Nanobot peut maintenant utiliser ce vault comme systeme de connaissance.",
            "Le point d'entree humain principal est le Cockpit de Vie.",
            "",
            "## Ce que Nanobot sait faire",
            "",
            "- creer une note markdown propre dans l'inbox",
            "- classer automatiquement chaque capture entre pro, perso, lecture, personnes et projets",
            "- ajouter une capture au journal du jour",
            "- importer un PDF avec extraction texte",
            "- importer une image avec OCR et piece jointe Obsidian",
            "- rechercher des notes dans le vault",
            "- synchroniser sa memoire operationnelle dans Obsidian",
            "",
            "## Commandes techniques",
            "",
            "Script principal:",
            f"`{OMEGA_ROOT / 'scripts' / 'obsidian_second_brain.py'}`",
            "",
            "Actions principales:",
            "- `bootstrap`",
            "- `status`",
            "- `open`",
            "- `capture --title ... --content ...`",
            "- `daily --content ...`",
            "- `import <chemin>`",
            "- `search <requete>`",
            "- `sync-memory`",
            "",
            "## Bon sens pratique",
            "",
            "- l'inbox sert a capter vite, pas a classer parfaitement",
            "- les imports vont dans la bibliotheque avec pieces jointes dediees",
            "- la memoire Nanobot se synchronise dans la zone systeme",
            "- les liens suggeres sont des aides, pas des verites absolues",
            "- le Cockpit de Vie sert de tour de controle pour les projets et tous les domaines de vie",
        ]
    ) + "\n"


def summarize_source_text(text: str, limit: int = 10) -> list[str]:
    bullets: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            candidate = line.lstrip("# ").strip()
        elif line.startswith(("-", "*")):
            candidate = line[1:].strip()
        else:
            continue
        if len(candidate) < 10:
            continue
        normalized = normalize_text(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        bullets.append(candidate)
        if len(bullets) >= limit:
            break
    return bullets


def sync_memory(config: dict[str, Any]) -> tuple[Path, Path]:
    memory_dir = resolve_vault_relative(config, "brain_memory_dir")
    summary_path = memory_dir / "Memoire_Nanobot.md"
    snapshot_path = memory_dir / "Snapshots_Nanobot.md"
    generated_at = now_local().isoformat(timespec="seconds")

    summary_lines = [
        "# Memoire Nanobot",
        "",
        f"- Synchronisee le: `{generated_at}`",
        "",
        "## Sources actives",
        "",
    ]
    snapshot_lines = [
        "# Snapshots Nanobot",
        "",
        f"Generation: `{generated_at}`",
        "",
    ]

    for label, path in MEMORY_SOURCES:
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        summary_lines.append(f"### {label}")
        summary_lines.append(f"- Source: `{path}`")
        if text:
            for bullet in summarize_source_text(text):
                summary_lines.append(f"- {bullet}")
        else:
            summary_lines.append("- Source introuvable.")
        summary_lines.append("")

        snapshot_lines.append(f"## {label}")
        snapshot_lines.append("")
        snapshot_lines.append(f"Source: `{path}`")
        snapshot_lines.append("")
        if text:
            snapshot_lines.append("```text")
            snapshot_lines.append(text.rstrip())
            snapshot_lines.append("```")
        else:
            snapshot_lines.append("_Source introuvable._")
        snapshot_lines.append("")

    summary_meta = {
        "title": "Memoire Nanobot",
        "created": generated_at,
        "updated": generated_at,
        "source": "nanobot-sync",
        "type": "memory",
        "tags": ["nanobot", "memory", "obsidian", "system"],
    }
    snapshot_meta = {
        "title": "Snapshots Nanobot",
        "created": generated_at,
        "updated": generated_at,
        "source": "nanobot-sync",
        "type": "memory-snapshot",
        "tags": ["nanobot", "memory", "snapshot", "obsidian", "system"],
    }

    write_markdown(summary_path, summary_meta, "\n".join(summary_lines).rstrip() + "\n")
    write_markdown(snapshot_path, snapshot_meta, "\n".join(snapshot_lines).rstrip() + "\n")
    update_related_section(config, summary_path)
    update_related_section(config, snapshot_path)
    return summary_path, snapshot_path


def render_daily_template(config: dict[str, Any], note_date: datetime) -> str:
    vault = vault_path(config)
    template_settings = read_json(vault / ".obsidian" / "daily-notes.json")
    template_rel = str(template_settings.get("template") or "").strip()
    if template_rel:
        template_path = vault / template_rel
        if template_path.exists():
            text = template_path.read_text(encoding="utf-8", errors="replace")
            text = text.replace("{{date:YYYY-MM-DD}}", note_date.strftime("%Y-%m-%d"))
            text = text.replace("{{date}}", note_date.strftime("%Y-%m-%d"))
            return text.rstrip() + "\n"
    return f"# {note_date.strftime('%Y-%m-%d')}\n\n## Capture Nanobot\n\n"


def append_daily_capture(config: dict[str, Any], content: str, heading: str | None = None) -> Path:
    day = now_local()
    folder = resolve_vault_relative(config, "daily_dir")
    note_path = folder / f"{day.strftime('%Y-%m-%d')}.md"
    if note_path.exists():
        metadata, body = read_markdown(note_path)
    else:
        metadata = {}
        body = render_daily_template(config, day)
    section_title = heading or f"Capture Nanobot {day.strftime('%H:%M')}"
    snippet = f"### {section_title}\n\n{content.strip()}\n"
    current_section = get_managed_section(body, "DAILY_CAPTURE")
    section_body = "## Capture Nanobot\n\n"
    if current_section:
        section_body += current_section.split("\n", 1)[1].strip() + "\n\n"
    section_body += snippet
    updated_body = update_managed_section(body, "DAILY_CAPTURE", section_body.rstrip())
    if metadata:
        metadata["updated"] = day.isoformat(timespec="seconds")
        write_markdown(note_path, metadata, updated_body)
    else:
        note_path.write_text(updated_body, encoding="utf-8")
    update_related_section(config, note_path)
    return note_path


def extract_pdf_text(path: Path) -> tuple[str, int]:
    if PdfReader is None:
        raise RuntimeError("pypdf n'est pas disponible sur ce PC.")
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = text.strip()
        chunks.append(f"## Page {index}\n\n{text or '[Aucun texte extrait]'}")
    return "\n\n".join(chunks).strip() + "\n", len(reader.pages)


def copy_attachment_to_vault(config: dict[str, Any], source: Path) -> Path:
    stamp = now_local()
    target_dir = resolve_vault_relative(config, "attachments_dir") / stamp.strftime("%Y") / stamp.strftime("%m")
    target_dir.mkdir(parents=True, exist_ok=True)
    candidate = target_dir / safe_filename(source.name)
    if candidate.exists():
        candidate = target_dir / f"{source.stem}-{stamp.strftime('%Y%m%d-%H%M%S')}{source.suffix}"
    shutil.copy2(source, candidate)
    return candidate


def vault_link(config: dict[str, Any], path: Path) -> str:
    return path.relative_to(vault_path(config)).as_posix()


def import_text_file(config: dict[str, Any], source: Path) -> Path:
    content = source.read_text(encoding="utf-8", errors="replace").strip()
    title = source.stem
    note = create_note(
        config,
        title=title,
        content=content or "[Fichier texte vide]",
        folder="imports_dir",
        tags=["import", "text"],
        source=str(source),
        note_type="import",
    )
    return note


def import_pdf_file(config: dict[str, Any], source: Path) -> Path:
    text, pages = extract_pdf_text(source)
    asset = copy_attachment_to_vault(config, source)
    content = "\n".join(
        [
            f"Document PDF importe depuis `{source}`.",
            f"Copie dans le vault: `![[{vault_link(config, asset)}]]`",
            f"Nombre de pages: {pages}",
            "",
            "## Texte extrait",
            text,
        ]
    ).strip()
    note = create_note(
        config,
        title=source.stem,
        content=content,
        folder="imports_dir",
        tags=["import", "pdf", "document"],
        source=str(source),
        note_type="import",
    )
    return note


def import_image_file(config: dict[str, Any], source: Path) -> Path:
    asset = copy_attachment_to_vault(config, source)
    ocr_text = ""
    if perform_ocr is not None:
        try:
            result = perform_ocr(asset, engine="auto", languages=["fr", "en", "nl"])
            ocr_text = (result.text or "").strip()
        except Exception as exc:
            ocr_text = f"[OCR indisponible: {exc}]"
    else:
        ocr_text = "[OCR indisponible sur ce poste]"
    content = "\n".join(
        [
            f"Image importee depuis `{source}`.",
            f"Piece jointe: `![[{vault_link(config, asset)}]]`",
            "",
            "## OCR",
            ocr_text or "[Aucun texte detecte]",
        ]
    ).strip()
    note = create_note(
        config,
        title=source.stem,
        content=content,
        folder="imports_dir",
        tags=["import", "image", "ocr"],
        source=str(source),
        note_type="import",
    )
    return note


def import_path(config: dict[str, Any], source: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"Chemin introuvable: {source}")
    suffix = source.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return import_text_file(config, source)
    if suffix in PDF_EXTENSIONS:
        return import_pdf_file(config, source)
    if suffix in IMAGE_EXTENSIONS:
        return import_image_file(config, source)
    raise RuntimeError(f"Type non supporte pour l'import Obsidian: {source.suffix or '[sans extension]'}")


def refresh_relation_sections(config: dict[str, Any], include_all: bool = False) -> tuple[int, list[dict[str, Any]]]:
    notes = collect_notes(config)
    targets = notes if include_all else [item for item in notes if is_managed_relative(config, item["relative"])]
    for item in targets:
        update_related_section(config, item["path"], notes=notes)
    return len(targets), notes


def build_relations_map(config: dict[str, Any], notes: list[dict[str, Any]] | None = None) -> Path:
    notes = notes or collect_notes(config)
    notes_by_relative, notes_by_title = build_note_indices(notes)
    lines = [
        "# Relations Nanobot",
        "",
        "Carte automatique des hubs et passerelles du vault Obsidian.",
        "",
    ]

    central_notes = [find_note_by_title(notes_by_title, title) for title in CENTRAL_RELATION_TITLES]
    central_notes = [item for item in central_notes if item is not None]
    if central_notes:
        lines.extend(["## Hubs centraux"])
        for item in central_notes:
            lines.append(f"- [[{note_target(item['relative'])}|{item['title']}]]")
        lines.append("")

    priority_notes = sorted(notes, key=lambda note: note["updated"], reverse=True)[:25]
    for item in priority_notes:
        lines.append(f"## [[{note_target(item['relative'])}|{item['title']}]]")

        navigation = build_navigation_targets(config, item, notes_by_relative, notes_by_title)
        if navigation:
            lines.append("### Hubs utiles")
            for linked, reason in navigation:
                lines.append(f"- [[{note_target(linked['relative'])}|{linked['title']}]] - {reason}")

        related = find_related_notes(config, item["path"], limit=5, notes=notes)
        if related:
            lines.append("### Passerelles")
            for entry in related:
                candidate = entry["note"]
                reason = "; ".join(entry["reasons"][:2]) if entry["reasons"] else "pont utile"
                lines.append(f"- [[{note_target(candidate['relative'])}|{candidate['title']}]] - {reason}")
        else:
            lines.append("### Passerelles")
            lines.append("- Aucune passerelle utile pour l'instant.")
        lines.append("")

    target = resolve_vault_relative(config, "brain_relations_dir") / "Relations_Nanobot.md"
    metadata = {
        "title": "Relations Nanobot",
        "created": now_local().isoformat(timespec="seconds"),
        "updated": now_local().isoformat(timespec="seconds"),
        "source": "nanobot-relations",
        "type": "relations",
        "tags": ["nanobot", "relations", "obsidian"],
    }
    write_markdown(target, metadata, "\n".join(lines).rstrip() + "\n")
    update_related_section(config, target, notes=notes)
    return target


def search_vault(config: dict[str, Any], query: str, limit: int = 8) -> list[tuple[int, dict[str, Any]]]:
    wanted = candidate_keywords(query, query, [], "")
    if not wanted:
        return []
    ranked: list[tuple[int, dict[str, Any]]] = []
    for note in collect_notes(config):
        overlap = wanted & note["keywords"]
        if not overlap:
            continue
        score = len(overlap) + len(wanted & candidate_keywords(note["title"], "", note["tags"], "")) * 3
        ranked.append((score, note))
    ranked.sort(key=lambda pair: (pair[0], pair[1]["updated"]), reverse=True)
    return ranked[:limit]


def bootstrap(config: dict[str, Any]) -> str:
    ensure_directories(config)
    ensure_templates(config)
    enabled = enable_core_plugins(config)
    life_os_notes = ensure_life_os_structure(config)

    hub_path = resolve_vault_relative(config, "hub_note")
    hub_meta = {
        "title": "Hub Nanobot x Obsidian",
        "created": now_local().isoformat(timespec="seconds"),
        "updated": now_local().isoformat(timespec="seconds"),
        "source": "nanobot-bootstrap",
        "type": "hub",
        "tags": ["nanobot", "obsidian", "hub", "system"],
    }
    write_markdown(hub_path, hub_meta, render_hub_note(config))

    mode_path = resolve_vault_relative(config, "brain_root") / "Mode_Emploi_Nanobot.md"
    mode_meta = {
        "title": "Mode d'emploi Nanobot",
        "created": now_local().isoformat(timespec="seconds"),
        "updated": now_local().isoformat(timespec="seconds"),
        "source": "nanobot-bootstrap",
        "type": "guide",
        "tags": ["nanobot", "obsidian", "guide", "system"],
    }
    write_markdown(mode_path, mode_meta, render_mode_emploi(config))

    memory_summary, memory_snapshots = sync_memory(config)
    _, woven_notes = refresh_relation_sections(config, include_all=False)
    relations_map = build_relations_map(config, notes=woven_notes)
    update_related_section(config, hub_path, notes=woven_notes)
    update_related_section(config, mode_path, notes=woven_notes)

    lines = [
        f"Vault Obsidian pret: {vault_path(config)}",
        f"Cockpit: {resolve_vault_relative(config, 'cockpit_note')}",
        f"Hub: {hub_path}",
        f"Memoire: {memory_summary}",
        f"Snapshots: {memory_snapshots}",
        f"Relations: {relations_map}",
    ]
    if life_os_notes:
        lines.append(f"Life OS initialise: {len(life_os_notes)} notes pivots")
    if enabled:
        lines.append("Plugins coeur actives: " + ", ".join(enabled))
    return "\n".join(lines)


def open_obsidian(config: dict[str, Any], note: str | None = None) -> str:
    vault = vault_path(config)
    note_rel = note or str(config["cockpit_note"])
    uri = f"obsidian://open?vault={urllib.parse.quote(vault.name)}&file={urllib.parse.quote(Path(note_rel).as_posix())}"
    subprocess.Popen(["explorer.exe", uri], close_fds=True)
    return f"Obsidian ouvre le vault {vault.name} sur {note_rel}."


def status(config: dict[str, Any]) -> str:
    notes = collect_notes(config)
    managed_count = sum(1 for item in notes if is_managed_relative(config, item["relative"]))
    imports_dir = resolve_vault_relative(config, "imports_dir")
    if _safe_path_exists(imports_dir):
        imports_count = sum(1 for _ in _iter_vault_md(imports_dir))
    else:
        imports_count = 0
    latest = max(notes, key=lambda item: item["updated"], default=None)
    lines = [
        f"Vault: {vault_path(config)}",
        f"Nom du vault: {vault_path(config).name}",
        f"Cockpit: {resolve_vault_relative(config, 'cockpit_note')}",
        f"Hub note: {resolve_vault_relative(config, 'hub_note')}",
        f"Dashboard temps: {resolve_vault_relative(config, 'time_dashboard')}",
        f"Notes markdown detectees: {len(notes)}",
        f"Notes gerees par Nanobot: {managed_count}",
        f"Imports documentaires: {imports_count}",
        f"Dossier inbox: {resolve_vault_relative(config, 'brain_inbox_dir')}",
        f"Capture projets: {resolve_vault_relative(config, 'capture_projects_dir')}",
        f"Capture pro: {resolve_vault_relative(config, 'capture_professional_dir')}",
        f"Capture perso: {resolve_vault_relative(config, 'capture_personal_dir')}",
        f"Capture personnes: {resolve_vault_relative(config, 'capture_people_dir')}",
        f"Capture lecture: {resolve_vault_relative(config, 'capture_reading_dir')}",
        f"Couche temps: {resolve_vault_relative(config, 'time_root')}",
        f"Dossier memoire: {resolve_vault_relative(config, 'brain_memory_dir')}",
    ]
    if latest is not None:
        lines.append(f"Derniere note modifiee: {latest['relative']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# VAULT CRUD — full programmatic control over the Obsidian vault on disk.
# Drive Desktop handles the cloud sync to monagenda.be. All paths are vault-
# relative; absolute paths and traversal outside the vault are rejected.
# ---------------------------------------------------------------------------

PROTECTED_RELATIVES = {".obsidian", ".trash"}


def _normalize_relative(relative: str) -> str:
    rel = str(relative or "").replace("\\", "/").strip().lstrip("/")
    if not rel or rel in {".", "./"}:
        raise ValueError("relative path is empty")
    if any(part in {"..", ""} for part in rel.split("/")):
        raise ValueError(f"relative path traversal forbidden: {relative!r}")
    return rel


def _safe_vault_path(config: dict[str, Any], relative: str, *, allow_protected: bool = False) -> Path:
    rel = _normalize_relative(relative)
    root = vault_path(config).resolve()
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes vault root: {relative!r}") from exc
    if not allow_protected:
        first = candidate.relative_to(root).parts[0]
        if first in PROTECTED_RELATIVES:
            raise ValueError(f"path is protected: {relative!r}")
    return candidate


def _parse_frontmatter_input(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"frontmatter must be valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("frontmatter JSON must be an object")
    return data


def vault_write_note(
    config: dict[str, Any],
    relative: str,
    content: str,
    *,
    frontmatter: dict[str, Any] | None = None,
    mode: str = "overwrite",
) -> dict[str, Any]:
    target = _safe_vault_path(config, relative)
    if mode not in {"overwrite", "append", "create"}:
        raise ValueError(f"unknown mode: {mode}")
    existed = target.exists()
    if mode == "create" and existed:
        raise FileExistsError(f"note already exists: {relative}")
    if mode == "append" and existed:
        existing_meta, existing_body = read_markdown(target)
        merged_meta = {**existing_meta, **(frontmatter or {})}
        new_body = existing_body.rstrip() + "\n\n" + content.lstrip()
        write_markdown(target, merged_meta, new_body)
    else:
        write_markdown(target, frontmatter or {}, content)
    return {
        "ok": True,
        "action": "append" if (mode == "append" and existed) else ("update" if existed else "create"),
        "path": str(target),
        "relative": _normalize_relative(relative),
        "size": target.stat().st_size,
    }


def vault_read_note(config: dict[str, Any], relative: str) -> dict[str, Any]:
    target = _safe_vault_path(config, relative)
    if not target.exists():
        raise FileNotFoundError(f"note not found: {relative}")
    if target.is_dir():
        raise IsADirectoryError(f"path is a directory: {relative}")
    metadata, body = read_markdown(target)
    return {
        "ok": True,
        "path": str(target),
        "relative": _normalize_relative(relative),
        "frontmatter": metadata,
        "body": body,
        "size": target.stat().st_size,
    }


def vault_delete_path(
    config: dict[str, Any],
    relative: str,
    *,
    recursive: bool = False,
) -> dict[str, Any]:
    target = _safe_vault_path(config, relative)
    if not target.exists():
        raise FileNotFoundError(f"path not found: {relative}")
    root = vault_path(config).resolve()
    if target == root:
        raise ValueError("refusing to delete vault root")
    if target.is_dir():
        if not recursive:
            try:
                target.rmdir()
            except OSError as exc:
                raise OSError(f"directory not empty (use --recursive): {relative}") from exc
        else:
            shutil.rmtree(target)
        kind = "folder"
    else:
        target.unlink()
        kind = "file"
    return {"ok": True, "kind": kind, "relative": _normalize_relative(relative)}


def vault_create_folder(config: dict[str, Any], relative: str) -> dict[str, Any]:
    target = _safe_vault_path(config, relative)
    target.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": str(target), "relative": _normalize_relative(relative)}


def vault_rename_path(config: dict[str, Any], src: str, dst: str) -> dict[str, Any]:
    src_path = _safe_vault_path(config, src)
    dst_path = _safe_vault_path(config, dst)
    if not src_path.exists():
        raise FileNotFoundError(f"source not found: {src}")
    if dst_path.exists():
        raise FileExistsError(f"destination already exists: {dst}")
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.rename(dst_path)
    return {
        "ok": True,
        "src": _normalize_relative(src),
        "dst": _normalize_relative(dst),
    }


def vault_move_note(config: dict[str, Any], src: str, folder: str) -> dict[str, Any]:
    src_path = _safe_vault_path(config, src)
    if not src_path.exists():
        raise FileNotFoundError(f"source not found: {src}")
    folder_path = _safe_vault_path(config, folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    dst_path = folder_path / src_path.name
    if dst_path.exists():
        raise FileExistsError(f"destination already exists: {dst_path.relative_to(vault_path(config))}")
    src_path.rename(dst_path)
    return {
        "ok": True,
        "src": _normalize_relative(src),
        "dst": dst_path.relative_to(vault_path(config)).as_posix(),
    }


def vault_list(
    config: dict[str, Any],
    folder: str | None = None,
    pattern: str = "*",
) -> dict[str, Any]:
    root = vault_path(config).resolve()
    base = _safe_vault_path(config, folder) if folder else root
    if not _safe_path_exists(base):
        raise FileNotFoundError(f"folder not found: {folder}")
    try:
        is_dir = base.is_dir()
    except OSError:
        is_dir = False
    if not is_dir:
        raise NotADirectoryError(f"not a folder: {folder}")
    skip_prefixes = _archive_exclusions(config)
    items: list[dict[str, Any]] = []
    raw_entries: list[tuple[Path, str]] = []
    for entry, rel in _iter_vault_any(root, pattern=pattern, exclude_prefixes=skip_prefixes):
        try:
            entry_under_base = base.resolve() in entry.resolve().parents or entry.resolve() == base.resolve()
        except OSError:
            entry_under_base = True
        if folder and not entry_under_base:
            continue
        if rel.split("/")[0] in PROTECTED_RELATIVES:
            continue
        raw_entries.append((entry, rel))
    for entry, rel in sorted(raw_entries, key=lambda pair: pair[1]):
        try:
            kind = "folder" if entry.is_dir() else "file"
        except OSError:
            continue
        size = None
        if kind == "file":
            stat = _safe_stat(entry)
            size = stat.st_size if stat is not None else None
        items.append({
            "relative": rel,
            "kind": kind,
            "size": size,
        })
    return {"ok": True, "folder": folder or "", "count": len(items), "items": items}


def vault_set_frontmatter(
    config: dict[str, Any],
    relative: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    target = _safe_vault_path(config, relative)
    if not target.exists():
        raise FileNotFoundError(f"note not found: {relative}")
    metadata, body = read_markdown(target)
    metadata = {**metadata, **updates}
    write_markdown(target, metadata, body)
    return {"ok": True, "relative": _normalize_relative(relative), "frontmatter": metadata}


def vault_modify_tags(
    config: dict[str, Any],
    relative: str,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> dict[str, Any]:
    target = _safe_vault_path(config, relative)
    if not target.exists():
        raise FileNotFoundError(f"note not found: {relative}")
    metadata, body = read_markdown(target)
    raw_tags = metadata.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    seen = {t.lower() for t in tags}
    for tag in add or []:
        norm = str(tag).strip()
        if norm and norm.lower() not in seen:
            tags.append(norm)
            seen.add(norm.lower())
    if remove:
        drop = {str(t).strip().lower() for t in remove}
        tags = [t for t in tags if t.lower() not in drop]
    metadata["tags"] = tags
    write_markdown(target, metadata, body)
    return {"ok": True, "relative": _normalize_relative(relative), "tags": tags}


def vault_get_frontmatter(config: dict[str, Any], relative: str) -> dict[str, Any]:
    target = _safe_vault_path(config, relative)
    if not target.exists():
        raise FileNotFoundError(f"note not found: {relative}")
    metadata, _ = read_markdown(target)
    return {"ok": True, "relative": _normalize_relative(relative), "frontmatter": metadata}


def vault_filter_notes(
    config: dict[str, Any],
    *,
    tag: str | None = None,
    prop: str | None = None,
    value: str | None = None,
    folder: str | None = None,
    query: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    notes = collect_notes(config)
    wanted_tag = normalize_text(tag or "")
    wanted_query = normalize_text(query or "")
    base_folder = _normalize_relative(folder).rstrip("/") + "/" if folder else ""
    matches: list[dict[str, Any]] = []
    for item in notes:
        if base_folder and not item["relative"].startswith(base_folder):
            continue
        if wanted_tag:
            tags = {normalize_text(raw) for raw in item.get("tags", [])}
            if wanted_tag not in tags:
                continue
        metadata, _body = read_markdown(item["path"])
        if prop:
            current = metadata.get(prop)
            if value is None:
                if prop not in metadata:
                    continue
            elif isinstance(current, list):
                if normalize_text(value) not in {normalize_text(str(v)) for v in current}:
                    continue
            elif normalize_text(str(current or "")) != normalize_text(value):
                continue
        if wanted_query and wanted_query not in item.get("normalized_text", ""):
            continue
        matches.append(
            {
                "relative": item["relative"],
                "title": item["title"],
                "tags": item["tags"],
                "frontmatter": metadata,
                "updated": item["updated"],
            }
        )
        if len(matches) >= max(1, int(limit)):
            break
    return {"ok": True, "count": len(matches), "items": matches}


def vault_sync_status(config: dict[str, Any]) -> dict[str, Any]:
    root = vault_path(config)
    log_path = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\user\AppData\Local")) / "Google" / "DriveFS" / "Logs" / "drive_fs.txt"
    process_output = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq GoogleDriveFS.exe"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    drive_running = "GoogleDriveFS.exe" in (process_output.stdout or "")
    recent_signals: list[str] = []
    active_uploads: str | None = None
    operation_queue_size: str | None = None
    change_ids_up_to_date: str | None = None
    if _safe_path_exists(log_path):
        lines = _safe_read_text(log_path).splitlines()[-300:]
        for line in lines:
            lowered = line.lower()
            if "active_uploads:" in lowered:
                active_uploads = line.split("active_uploads:", 1)[-1].strip()
            if "operation_queue_size:" in lowered:
                operation_queue_size = line.split("operation_queue_size:", 1)[-1].strip()
            if "change_ids_up_to_date:" in lowered:
                change_ids_up_to_date = line.split("change_ids_up_to_date:", 1)[-1].strip()
            if any(token in lowered for token in ("error", "failed", "unavailable_resource", "not_uploaded", "precondition_failed")):
                recent_signals.append(line[-240:])
    skip_prefixes = _archive_exclusions(config)
    file_count = 0
    latest_path: Path | None = None
    latest_mtime: float = -1.0
    if _safe_path_exists(root):
        for path, _rel in _iter_vault_any(root, exclude_prefixes=skip_prefixes):
            try:
                if not path.is_file():
                    continue
            except OSError:
                continue
            stat = _safe_stat(path)
            if stat is None:
                continue
            file_count += 1
            if stat.st_mtime > latest_mtime:
                latest_mtime = stat.st_mtime
                latest_path = path
    return {
        "ok": True,
        "vault": str(root),
        "vault_exists": _safe_path_exists(root),
        "google_drive_process_running": drive_running,
        "google_drive_log": str(log_path),
        "active_uploads": active_uploads,
        "operation_queue_size": operation_queue_size,
        "change_ids_up_to_date": change_ids_up_to_date,
        "recent_problem_signals": recent_signals[-8:],
        "file_count": file_count,
        "latest_file": str(latest_path) if latest_path else None,
        "latest_file_modified": datetime.fromtimestamp(latest_mtime).isoformat(timespec="seconds") if latest_path else None,
    }


def vault_list_attachments(config: dict[str, Any], folder: str | None = None) -> dict[str, Any]:
    root = vault_path(config)
    base = _safe_vault_path(config, folder) if folder else resolve_vault_relative(config, "attachments_dir")
    if not _safe_path_exists(base):
        return {"ok": True, "folder": str(base), "count": 0, "items": []}
    skip_prefixes = _archive_exclusions(config)
    pairs: list[tuple[Path, str]] = []
    for path, _rel in _iter_vault_any(base, exclude_prefixes=skip_prefixes):
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS:
            continue
        pairs.append((path, str(path)))
    items: list[dict[str, Any]] = []
    for path, _ in sorted(pairs, key=lambda pair: pair[1]):
        stat = _safe_stat(path)
        if stat is None:
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
        items.append(
            {
                "relative": rel,
                "name": path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    return {"ok": True, "folder": str(base), "count": len(items), "items": items}


def vault_add_attachment(
    config: dict[str, Any],
    source: str,
    *,
    note: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    source_path = Path(source).expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(f"attachment source not found: {source}")
    stamp = now_local()
    target_dir = resolve_vault_relative(config, "attachments_dir") / stamp.strftime("%Y") / stamp.strftime("%m")
    if category:
        target_dir = target_dir / safe_filename(category)
    target_dir.mkdir(parents=True, exist_ok=True)
    candidate = target_dir / safe_filename(source_path.name)
    if candidate.exists():
        candidate = target_dir / f"{safe_filename(source_path.stem)}-{stamp.strftime('%Y%m%d-%H%M%S')}{source_path.suffix}"
    shutil.copy2(source_path, candidate)
    rel = candidate.relative_to(vault_path(config)).as_posix()
    link = f"![[{rel}]]"
    updated_note = None
    if note:
        note_path = _safe_vault_path(config, note)
        if not note_path.exists():
            raise FileNotFoundError(f"note not found: {note}")
        metadata, body = read_markdown(note_path)
        body = body.rstrip() + "\n\n## Piece jointe\n" + link + "\n"
        write_markdown(note_path, metadata, body)
        updated_note = note_path.relative_to(vault_path(config)).as_posix()
    return {"ok": True, "source": str(source_path), "relative": rel, "wikilink": link, "note": updated_note}


def vault_move_attachment(config: dict[str, Any], src: str, dst: str) -> dict[str, Any]:
    src_path = _safe_vault_path(config, src)
    dst_path = _safe_vault_path(config, dst)
    if not src_path.exists() or not src_path.is_file():
        raise FileNotFoundError(f"attachment not found: {src}")
    if src_path.suffix.lower() in TEXT_EXTENSIONS:
        raise ValueError("move-attachment is reserved for non-Markdown files")
    if dst_path.exists():
        raise FileExistsError(f"destination already exists: {dst}")
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.rename(dst_path)
    return {
        "ok": True,
        "src": _normalize_relative(src),
        "dst": dst_path.relative_to(vault_path(config)).as_posix(),
        "wikilink": f"![[{dst_path.relative_to(vault_path(config)).as_posix()}]]",
    }


# ---------------------------------------------------------------------------
# Action journal — every destructive call appends a line to logs/obsidian_actions.jsonl.
# ---------------------------------------------------------------------------

ACTION_LOG = OMEGA_ROOT / "logs" / "obsidian_actions.jsonl"


def _log_action(
    command: str,
    args: dict[str, Any],
    *,
    dry_run: bool,
    ok: bool,
    detail: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    try:
        ACTION_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "command": command,
            "args": args,
            "dry_run": dry_run,
            "ok": ok,
            "detail": detail or {},
            "error": error,
        }
        with ACTION_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _update_wikilinks_in_vault(
    config: dict[str, Any],
    src_relative: str,
    dst_relative: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Update [[old]] / [[old|alias]] / [[old#anchor]] references across the vault
    to point at the new path. Returns a summary of files touched."""
    notes = collect_notes(config)
    src_target = src_relative[:-3] if src_relative.endswith(".md") else src_relative
    dst_target = dst_relative[:-3] if dst_relative.endswith(".md") else dst_relative
    src_stem = Path(src_relative).stem
    dst_stem = Path(dst_relative).stem
    candidates = {
        normalize_text(src_relative),
        normalize_text(src_target),
        normalize_text(src_stem),
    }
    touched: list[dict[str, Any]] = []
    for note in notes:
        if note["relative"] == src_relative:
            continue
        if not note["existing_links"]:
            continue
        replacements = 0
        body = note["raw_body"]
        for raw in re.findall(r"\[\[([^\]]+)\]\]", body):
            target = raw.split("|", 1)[0].split("#", 1)[0].strip()
            if normalize_text(target) not in candidates:
                continue
            old_link = "[[" + raw + "]]"
            tail = ""
            if "|" in raw:
                tail = "|" + raw.split("|", 1)[1]
            elif "#" in raw:
                tail = "#" + raw.split("#", 1)[1]
            new_inner = dst_target + tail if tail.startswith("|") else dst_target
            if "#" in raw and not tail.startswith("|"):
                new_inner = dst_target + tail
            new_link = "[[" + new_inner + "]]"
            if old_link in body:
                body = body.replace(old_link, new_link)
                replacements += 1
        if replacements:
            touched.append({"relative": note["relative"], "replacements": replacements})
            if not dry_run:
                metadata, _ = read_markdown(note["path"])
                write_markdown(note["path"], metadata, body)
    return {
        "src": src_relative,
        "dst": dst_relative,
        "src_stem": src_stem,
        "dst_stem": dst_stem,
        "files_touched": len(touched),
        "details": touched[:25],
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Vault audit & quality commands (read-only).
# ---------------------------------------------------------------------------


def _build_link_targets_index(notes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for note in notes:
        rel = note["relative"]
        index[normalize_text(rel)] = note
        index[normalize_text(rel[:-3]) if rel.endswith(".md") else normalize_text(rel)] = note
        index[normalize_text(Path(rel).stem)] = note
        index[normalize_text(note["title"])] = note
    return index


def _resolve_wikilink(target: str, index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    norm = normalize_text(target)
    if norm in index:
        return index[norm]
    if norm.endswith(" md"):
        norm2 = norm[:-3].rstrip()
        if norm2 in index:
            return index[norm2]
    return None


def _backlink_map(notes: list[dict[str, Any]], index: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    backlinks: dict[str, list[str]] = {note["relative"]: [] for note in notes}
    for source in notes:
        for target_str in source["existing_links"]:
            target = _resolve_wikilink(target_str, index)
            if target is None:
                continue
            if target["relative"] == source["relative"]:
                continue
            lst = backlinks.setdefault(target["relative"], [])
            if source["relative"] not in lst:
                lst.append(source["relative"])
    return backlinks


def vault_audit(config: dict[str, Any]) -> dict[str, Any]:
    notes = collect_notes(config)
    index = _build_link_targets_index(notes)
    backlinks = _backlink_map(notes, index)
    tags_count: dict[str, int] = {}
    folder_count: dict[str, int] = {}
    total_size = 0
    notes_with_frontmatter = 0
    notes_with_links = 0
    notes_with_tags = 0
    broken_total = 0
    for note in notes:
        for tag in note["tags"]:
            tags_count[tag] = tags_count.get(tag, 0) + 1
        top = note["relative"].split("/", 1)[0]
        folder_count[top] = folder_count.get(top, 0) + 1
        stat = _safe_stat(note["path"])
        if stat is not None:
            total_size += stat.st_size
        if note["raw_body"].startswith("---") or note["tags"]:
            pass
        if note["existing_links"]:
            notes_with_links += 1
        if note["tags"]:
            notes_with_tags += 1
        for link in note["existing_links"]:
            if _resolve_wikilink(link, index) is None:
                broken_total += 1
    orphans = [n["relative"] for n in notes if not backlinks.get(n["relative"]) and not n["existing_links"]]
    return {
        "ok": True,
        "vault": str(vault_path(config)),
        "total_notes": len(notes),
        "total_bytes": total_size,
        "notes_with_links": notes_with_links,
        "notes_with_tags": notes_with_tags,
        "broken_links_total": broken_total,
        "orphan_notes_total": len(orphans),
        "tags_distinct": len(tags_count),
        "top_tags": sorted(tags_count.items(), key=lambda kv: kv[1], reverse=True)[:15],
        "folder_distribution": sorted(folder_count.items(), key=lambda kv: kv[1], reverse=True),
        "sample_orphans": orphans[:10],
    }


def vault_detect_orphans(config: dict[str, Any], *, limit: int = 50) -> dict[str, Any]:
    notes = collect_notes(config)
    index = _build_link_targets_index(notes)
    backlinks = _backlink_map(notes, index)
    orphans: list[dict[str, Any]] = []
    for note in notes:
        if backlinks.get(note["relative"]):
            continue
        if note["existing_links"]:
            # has outgoing links: not isolated, just not pointed to
            kind = "no_backlink"
        else:
            kind = "isolated"
        orphans.append({
            "relative": note["relative"],
            "title": note["title"],
            "tags": note["tags"],
            "kind": kind,
            "size": (_safe_stat(note["path"]).st_size if _safe_stat(note["path"]) else 0),
        })
    orphans.sort(key=lambda item: (item["kind"] != "isolated", item["size"]))
    return {"ok": True, "count": len(orphans), "items": orphans[:limit]}


def vault_detect_duplicates(
    config: dict[str, Any], *, min_overlap: int = 12, limit: int = 30
) -> dict[str, Any]:
    notes = collect_notes(config)
    pairs: list[dict[str, Any]] = []
    for i, src in enumerate(notes):
        for dst in notes[i + 1:]:
            if src["relative"] == dst["relative"]:
                continue
            if normalize_text(src["title"]) == normalize_text(dst["title"]):
                pairs.append({
                    "kind": "same_title",
                    "left": src["relative"],
                    "right": dst["relative"],
                    "title": src["title"],
                    "score": 1000,
                })
                continue
            overlap = len(src["keywords"] & dst["keywords"])
            if overlap < min_overlap:
                continue
            pairs.append({
                "kind": "high_overlap",
                "left": src["relative"],
                "right": dst["relative"],
                "left_title": src["title"],
                "right_title": dst["title"],
                "score": overlap,
            })
    pairs.sort(key=lambda p: p["score"], reverse=True)
    return {"ok": True, "count": len(pairs), "items": pairs[:limit]}


def vault_detect_weak_notes(
    config: dict[str, Any], *, min_chars: int = 120, limit: int = 50
) -> dict[str, Any]:
    notes = collect_notes(config)
    weak: list[dict[str, Any]] = []
    for note in notes:
        body_len = len(note["body"].strip())
        no_title = note["title"].strip() == ""
        no_tags = not note["tags"]
        no_links = not note["existing_links"]
        reasons: list[str] = []
        if body_len < min_chars:
            reasons.append(f"body<{min_chars}")
        if no_title:
            reasons.append("no_title")
        if no_tags:
            reasons.append("no_tags")
        if no_links:
            reasons.append("no_links")
        if not reasons:
            continue
        weak.append({
            "relative": note["relative"],
            "title": note["title"],
            "body_chars": body_len,
            "tags": note["tags"],
            "reasons": reasons,
        })
    weak.sort(key=lambda item: (len(item["reasons"]), item["body_chars"]), reverse=True)
    return {"ok": True, "count": len(weak), "items": weak[:limit]}


def vault_detect_broken_links(
    config: dict[str, Any], *, limit: int = 100
) -> dict[str, Any]:
    notes = collect_notes(config)
    index = _build_link_targets_index(notes)
    broken: list[dict[str, Any]] = []
    for note in notes:
        for raw_link in note["existing_links"]:
            target = _resolve_wikilink(raw_link, index)
            if target is None:
                broken.append({
                    "source": note["relative"],
                    "source_title": note["title"],
                    "broken_target": raw_link,
                })
    return {"ok": True, "count": len(broken), "items": broken[:limit]}


def vault_propose_structure(config: dict[str, Any]) -> dict[str, Any]:
    notes = collect_notes(config)
    index = _build_link_targets_index(notes)
    backlinks = _backlink_map(notes, index)
    suggestions: list[dict[str, Any]] = []
    for note in notes:
        # 1) Untagged notes in a domain root
        primary = note.get("primary_domain")
        if primary and not note["tags"]:
            suggestions.append({
                "kind": "missing_tag",
                "relative": note["relative"],
                "hint": f"ajouter le tag #{primary}",
            })
        # 2) Notes at the vault root that should be inside a domain
        rel = note["relative"]
        if "/" not in rel:
            domains = note.get("focus_domains") or []
            if domains:
                key = domains[0]
                rule = DOMAIN_RULES.get(key)
                hint = rule["dashboard_title"] if rule else key
                suggestions.append({
                    "kind": "root_note_to_classify",
                    "relative": rel,
                    "hint": f"classer dans : {hint}",
                })
        # 3) Notes with high backlink count but no tags : candidate hub
        if len(backlinks.get(rel, [])) >= 5 and not note["tags"]:
            suggestions.append({
                "kind": "potential_hub",
                "relative": rel,
                "hint": f"{len(backlinks[rel])} backlinks — envisager #hub ou #moc",
            })
    return {
        "ok": True,
        "count": len(suggestions),
        "items": suggestions[:100],
    }


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bridge Obsidian pour Nanobot.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap")
    sub.add_parser("status")

    open_cmd = sub.add_parser("open")
    open_cmd.add_argument("--note", help="Chemin relatif de la note a ouvrir.")

    capture_cmd = sub.add_parser("capture")
    capture_cmd.add_argument("--title")
    capture_cmd.add_argument("--content", required=True)
    capture_cmd.add_argument("--folder")
    capture_cmd.add_argument("--tags", nargs="*", default=[])
    capture_cmd.add_argument("--source", default="nanobot")

    daily_cmd = sub.add_parser("daily")
    daily_cmd.add_argument("--content", required=True)
    daily_cmd.add_argument("--heading")

    import_cmd = sub.add_parser("import")
    import_cmd.add_argument("path")

    search_cmd = sub.add_parser("search")
    search_cmd.add_argument("query")
    search_cmd.add_argument("--format", choices=["text", "markdown", "json", "names"], default="text", help="text (defaut, lisible Telegram) | markdown | json | names (1 chemin par ligne)")
    search_cmd.add_argument("--limit", type=int, default=20)

    sub.add_parser("sync-memory")
    relations_cmd = sub.add_parser("relations")
    relations_cmd.add_argument("--all", action="store_true", help="Retisse toutes les notes du vault.")

    write_cmd = sub.add_parser("write-note", help="Crée ou modifie une note (chemin vault-relatif).")
    write_cmd.add_argument("--path", required=True)
    write_cmd.add_argument("--content", required=True)
    write_cmd.add_argument("--frontmatter", help="JSON object pour le frontmatter.")
    write_cmd.add_argument("--mode", choices=["overwrite", "append", "create"], default="overwrite")

    read_cmd = sub.add_parser("read-note", help="Lit une note et retourne frontmatter + body en JSON.")
    read_cmd.add_argument("--path", required=True)

    delete_cmd = sub.add_parser("delete-path", help="Supprime un fichier ou un dossier du vault.")
    delete_cmd.add_argument("--path", required=True)
    delete_cmd.add_argument("--recursive", action="store_true")
    delete_cmd.add_argument("--dry-run", action="store_true", help="Affiche ce qui serait supprime sans modifier.")

    mkdir_cmd = sub.add_parser("create-folder", help="Crée un dossier dans le vault.")
    mkdir_cmd.add_argument("--path", required=True)

    rename_cmd = sub.add_parser("rename-path", help="Renomme/déplace un fichier ou un dossier.")
    rename_cmd.add_argument("--src", required=True)
    rename_cmd.add_argument("--dst", required=True)
    rename_cmd.add_argument("--dry-run", action="store_true")
    rename_cmd.add_argument("--update-links", action="store_true", help="Met a jour les [[liens]] qui pointaient vers l'ancien chemin.")

    move_cmd = sub.add_parser("move-note", help="Déplace une note vers un autre dossier (nom conservé).")
    move_cmd.add_argument("--src", required=True)
    move_cmd.add_argument("--folder", required=True)
    move_cmd.add_argument("--dry-run", action="store_true")
    move_cmd.add_argument("--update-links", action="store_true")

    list_cmd = sub.add_parser("list", help="Liste récursive du vault (ou d'un sous-dossier).")
    list_cmd.add_argument("--folder")
    list_cmd.add_argument("--pattern", default="*")
    list_cmd.add_argument("--format", choices=["json", "markdown", "bullets", "names"], default="json", help="json (defaut) | markdown (liste a puce avec dossiers) | bullets (liste plate) | names (1 par ligne)")
    list_cmd.add_argument("--md-only", action="store_true", help="Filtre sur les fichiers .md uniquement.")

    fm_cmd = sub.add_parser("set-frontmatter", help="Fusionne des clés JSON dans le frontmatter d'une note.")
    fm_cmd.add_argument("--path", required=True)
    fm_cmd.add_argument("--updates", required=True, help="JSON object des clés à fusionner.")

    get_fm_cmd = sub.add_parser("get-frontmatter", help="Lit les proprietes/frontmatter d'une note.")
    get_fm_cmd.add_argument("--path", required=True)

    filter_cmd = sub.add_parser("filter-notes", help="Filtre les notes par tag, propriete, valeur, dossier ou texte.")
    filter_cmd.add_argument("--tag")
    filter_cmd.add_argument("--property")
    filter_cmd.add_argument("--value")
    filter_cmd.add_argument("--folder")
    filter_cmd.add_argument("--query")
    filter_cmd.add_argument("--limit", type=int, default=50)

    tags_cmd = sub.add_parser("tags", help="Ajoute et/ou retire des tags d'une note.")
    tags_cmd.add_argument("--path", required=True)
    tags_cmd.add_argument("--add", nargs="*", default=[])
    tags_cmd.add_argument("--remove", nargs="*", default=[])

    sub.add_parser("sync-status", help="Rapporte l'etat local Google Drive du vault.")

    attachments_cmd = sub.add_parser("attachments", help="Liste les fichiers annexes non-Markdown.")
    attachments_cmd.add_argument("--folder")

    add_attachment_cmd = sub.add_parser("add-attachment", help="Copie une piece jointe dans le vault et peut la lier a une note.")
    add_attachment_cmd.add_argument("source")
    add_attachment_cmd.add_argument("--note")
    add_attachment_cmd.add_argument("--category")

    move_attachment_cmd = sub.add_parser("move-attachment", help="Renomme/deplace une piece jointe dans le vault.")
    move_attachment_cmd.add_argument("--src", required=True)
    move_attachment_cmd.add_argument("--dst", required=True)

    sub.add_parser("audit-vault", help="Rapport global du vault (read-only, JSON).")

    orphans_cmd = sub.add_parser("detect-orphans", help="Notes sans backlink, JSON.")
    orphans_cmd.add_argument("--limit", type=int, default=50)

    dupes_cmd = sub.add_parser("detect-duplicates", help="Notes au titre/contenu tres similaires.")
    dupes_cmd.add_argument("--min-overlap", type=int, default=12)
    dupes_cmd.add_argument("--limit", type=int, default=30)

    weak_cmd = sub.add_parser("detect-weak-notes", help="Notes faibles (vides, sans tag, sans lien).")
    weak_cmd.add_argument("--min-chars", type=int, default=120)
    weak_cmd.add_argument("--limit", type=int, default=50)

    broken_cmd = sub.add_parser("detect-broken-links", help="Wikilinks [[...]] qui pointent dans le vide.")
    broken_cmd.add_argument("--limit", type=int, default=100)

    sub.add_parser("propose-structure", help="Suggestions read-only de classement / tags / hubs.")

    args = parser.parse_args(argv or sys.argv[1:])
    config = load_config()

    if args.command == "bootstrap":
        print(bootstrap(config))
        return 0

    if args.command == "status":
        print(status(config))
        return 0

    if args.command == "open":
        print(open_obsidian(config, note=args.note))
        return 0

    if args.command == "capture":
        capture_title = args.title or derive_title(args.content)
        capture_tags = list(args.tags or [])
        capture_folder = args.folder
        classification: dict[str, Any] | None = None
        if not capture_folder:
            classification = classify_capture(
                config,
                title=capture_title,
                content=args.content,
                tags=capture_tags,
                source=args.source,
            )
            capture_folder = str(classification["folder_key"])
            capture_tags.extend(
                [
                    str(classification["category"]),
                    f"capture/{classification['category']}",
                ]
            )
        path = create_note(
            config,
            title=capture_title,
            content=args.content,
            folder=capture_folder or "brain_inbox_dir",
            tags=capture_tags,
            source=args.source,
            note_type="capture",
            metadata_extra=(
                {
                    "capture_category": str(classification["category"]),
                    "capture_confidence": str(classification["confidence"]),
                    "capture_score": str(classification["score"]),
                    "capture_reasons": list(classification["reasons"]),
                }
                if classification
                else None
            ),
        )
        time_updates = append_time_signal(
            config,
            note_path=path,
            title=capture_title,
            content=args.content,
            tags=capture_tags,
            classification=classification,
        )
        build_relations_map(config)
        if classification:
            message = (
                "Note capturee dans Obsidian "
                f"[{classification['label']}, confiance {classification['confidence']}]: {path}"
            )
        else:
            message = f"Note capturee dans Obsidian: {path}"
        if time_updates:
            message += "\nTemps mis a jour: " + ", ".join(time_updates)
        print(message)
        return 0

    if args.command == "daily":
        path = append_daily_capture(config, args.content, heading=args.heading)
        build_relations_map(config)
        print(f"Capture ajoutee a la note du jour: {path}")
        return 0

    if args.command == "import":
        path = import_path(config, Path(args.path))
        build_relations_map(config)
        print(f"Fichier importe dans Obsidian: {path}")
        return 0

    if args.command == "search":
        results = search_vault(config, args.query)
        limit = getattr(args, "limit", 20)
        results = results[:limit]
        fmt = getattr(args, "format", "text")
        if not results:
            if fmt == "json":
                _emit({"ok": True, "query": args.query, "count": 0, "items": []})
            else:
                print("Aucun resultat Obsidian.")
            return 0
        if fmt == "json":
            items = [{"score": score, "title": item["title"], "relative": item["relative"], "tags": item.get("tags", [])} for score, item in results]
            _emit({"ok": True, "query": args.query, "count": len(items), "items": items})
            return 0
        if fmt == "names":
            for _score, item in results:
                print(item["relative"])
            return 0
        if fmt == "markdown":
            print(f"# Recherche Obsidian : {args.query}\n")
            print(f"**{len(results)} resultat(s) (top {limit}) :**\n")
            for score, item in results:
                tags = " ".join(f"#{t}" for t in (item.get("tags") or [])[:3])
                tags_str = f" — {tags}" if tags else ""
                print(f"- **{item['title']}** [{score}] — `{item['relative']}`{tags_str}")
            return 0
        # text (defaut)
        lines = [f"Recherche Obsidian: {args.query}"]
        for score, item in results:
            lines.append(f"- [{score}] {item['title']} -> {item['relative']}")
        print("\n".join(lines))
        return 0

    if args.command == "sync-memory":
        summary, snapshot = sync_memory(config)
        build_relations_map(config)
        print(f"Memoire synchronisee dans Obsidian:\n- {summary}\n- {snapshot}")
        return 0

    if args.command == "relations":
        updated_count, notes = refresh_relation_sections(config, include_all=bool(args.all))
        path = build_relations_map(config, notes=notes)
        mode = "tout le vault" if args.all else "les notes gerees par Nanobot"
        print(
            "Relations Obsidian retissees "
            f"({mode}, {updated_count} notes): {path}"
        )
        return 0

    if args.command == "write-note":
        try:
            fm = _parse_frontmatter_input(args.frontmatter)
            result = vault_write_note(config, args.path, args.content, frontmatter=fm, mode=args.mode)
        except (ValueError, FileExistsError) as exc:
            _emit({"ok": False, "error": str(exc)})
            return 1
        _emit(result)
        return 0

    if args.command == "read-note":
        try:
            result = vault_read_note(config, args.path)
        except (ValueError, FileNotFoundError, IsADirectoryError) as exc:
            _emit({"ok": False, "error": str(exc)})
            return 1
        _emit(result)
        return 0

    if args.command == "delete-path":
        if args.dry_run:
            try:
                target = _safe_vault_path(config, args.path)
            except ValueError as exc:
                _emit({"ok": False, "error": str(exc)})
                _log_action("delete-path", {"path": args.path}, dry_run=True, ok=False, error=str(exc))
                return 1
            preview = {
                "ok": True,
                "dry_run": True,
                "would_delete": str(target),
                "exists": _safe_path_exists(target),
                "is_dir": (target.is_dir() if _safe_path_exists(target) else False),
                "recursive": bool(args.recursive),
            }
            _emit(preview)
            _log_action("delete-path", {"path": args.path, "recursive": args.recursive}, dry_run=True, ok=True, detail=preview)
            return 0
        try:
            result = vault_delete_path(config, args.path, recursive=args.recursive)
        except (ValueError, FileNotFoundError, OSError) as exc:
            _emit({"ok": False, "error": str(exc)})
            _log_action("delete-path", {"path": args.path, "recursive": args.recursive}, dry_run=False, ok=False, error=str(exc))
            return 1
        _emit(result)
        _log_action("delete-path", {"path": args.path, "recursive": args.recursive}, dry_run=False, ok=True, detail=result)
        return 0

    if args.command == "create-folder":
        try:
            result = vault_create_folder(config, args.path)
        except ValueError as exc:
            _emit({"ok": False, "error": str(exc)})
            return 1
        _emit(result)
        return 0

    if args.command == "rename-path":
        op_args = {"src": args.src, "dst": args.dst, "update_links": bool(args.update_links)}
        if args.dry_run:
            preview: dict[str, Any] = {"ok": True, "dry_run": True, "would_rename": op_args}
            if args.update_links:
                preview["link_updates"] = _update_wikilinks_in_vault(config, args.src, args.dst, dry_run=True)
            _emit(preview)
            _log_action("rename-path", op_args, dry_run=True, ok=True, detail=preview)
            return 0
        try:
            result = vault_rename_path(config, args.src, args.dst)
            if args.update_links:
                result["link_updates"] = _update_wikilinks_in_vault(config, args.src, args.dst, dry_run=False)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            _emit({"ok": False, "error": str(exc)})
            _log_action("rename-path", op_args, dry_run=False, ok=False, error=str(exc))
            return 1
        _emit(result)
        _log_action("rename-path", op_args, dry_run=False, ok=True, detail=result)
        return 0

    if args.command == "move-note":
        target_rel = (Path(args.folder) / Path(args.src).name).as_posix()
        op_args = {"src": args.src, "folder": args.folder, "update_links": bool(args.update_links)}
        if args.dry_run:
            preview = {"ok": True, "dry_run": True, "would_move_to": target_rel}
            if args.update_links:
                preview["link_updates"] = _update_wikilinks_in_vault(config, args.src, target_rel, dry_run=True)
            _emit(preview)
            _log_action("move-note", op_args, dry_run=True, ok=True, detail=preview)
            return 0
        try:
            result = vault_move_note(config, args.src, args.folder)
            if args.update_links:
                result["link_updates"] = _update_wikilinks_in_vault(config, args.src, target_rel, dry_run=False)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            _emit({"ok": False, "error": str(exc)})
            _log_action("move-note", op_args, dry_run=False, ok=False, error=str(exc))
            return 1
        _emit(result)
        _log_action("move-note", op_args, dry_run=False, ok=True, detail=result)
        return 0

    if args.command == "list":
        try:
            result = vault_list(config, folder=args.folder, pattern=args.pattern)
        except (ValueError, FileNotFoundError, NotADirectoryError) as exc:
            _emit({"ok": False, "error": str(exc)})
            return 1
        items = result.get("items", [])
        if args.md_only:
            items = [it for it in items if it.get("kind") == "file" and it["relative"].lower().endswith(".md")]
        fmt = getattr(args, "format", "json")
        if fmt == "json":
            if args.md_only:
                result = {**result, "items": items, "count": len(items)}
            _emit(result)
            return 0
        if fmt == "names":
            for it in items:
                print(it["relative"])
            return 0
        if fmt == "bullets":
            for it in items:
                if it.get("kind") == "folder":
                    continue
                print(f"- {it['relative']}")
            return 0
        # markdown : liste a puce avec dossiers en gras
        last_top = None
        for it in sorted(items, key=lambda x: x["relative"]):
            rel = it["relative"]
            top = rel.split("/", 1)[0]
            if top != last_top:
                print(f"\n**{top}/**")
                last_top = top
            if it.get("kind") == "file":
                indent = "  " * (rel.count("/") - 1)
                name = rel.rsplit("/", 1)[-1] if "/" in rel else rel
                print(f"{indent}- {name}")
        return 0

    if args.command == "set-frontmatter":
        try:
            updates = _parse_frontmatter_input(args.updates)
            result = vault_set_frontmatter(config, args.path, updates)
        except (ValueError, FileNotFoundError) as exc:
            _emit({"ok": False, "error": str(exc)})
            return 1
        _emit(result)
        return 0

    if args.command == "get-frontmatter":
        try:
            result = vault_get_frontmatter(config, args.path)
        except (ValueError, FileNotFoundError) as exc:
            _emit({"ok": False, "error": str(exc)})
            return 1
        _emit(result)
        return 0

    if args.command == "filter-notes":
        try:
            result = vault_filter_notes(
                config,
                tag=args.tag,
                prop=args.property,
                value=args.value,
                folder=args.folder,
                query=args.query,
                limit=args.limit,
            )
        except ValueError as exc:
            _emit({"ok": False, "error": str(exc)})
            return 1
        _emit(result)
        return 0

    if args.command == "tags":
        try:
            result = vault_modify_tags(config, args.path, add=args.add, remove=args.remove)
        except (ValueError, FileNotFoundError) as exc:
            _emit({"ok": False, "error": str(exc)})
            return 1
        _emit(result)
        return 0

    if args.command == "sync-status":
        _emit(vault_sync_status(config))
        return 0

    if args.command == "attachments":
        try:
            result = vault_list_attachments(config, folder=args.folder)
        except (ValueError, FileNotFoundError, NotADirectoryError) as exc:
            _emit({"ok": False, "error": str(exc)})
            return 1
        _emit(result)
        return 0

    if args.command == "add-attachment":
        try:
            result = vault_add_attachment(config, args.source, note=args.note, category=args.category)
        except (ValueError, FileNotFoundError) as exc:
            _emit({"ok": False, "error": str(exc)})
            return 1
        _emit(result)
        return 0

    if args.command == "move-attachment":
        try:
            result = vault_move_attachment(config, args.src, args.dst)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            _emit({"ok": False, "error": str(exc)})
            return 1
        _emit(result)
        return 0

    if args.command == "audit-vault":
        _emit(vault_audit(config))
        return 0

    if args.command == "detect-orphans":
        _emit(vault_detect_orphans(config, limit=args.limit))
        return 0

    if args.command == "detect-duplicates":
        _emit(vault_detect_duplicates(config, min_overlap=args.min_overlap, limit=args.limit))
        return 0

    if args.command == "detect-weak-notes":
        _emit(vault_detect_weak_notes(config, min_chars=args.min_chars, limit=args.limit))
        return 0

    if args.command == "detect-broken-links":
        _emit(vault_detect_broken_links(config, limit=args.limit))
        return 0

    if args.command == "propose-structure":
        _emit(vault_propose_structure(config))
        return 0

    print("Commande inconnue.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
