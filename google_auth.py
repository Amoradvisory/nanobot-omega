#!/usr/bin/env python
"""
google_auth.py - Authentification OAuth2 Google pour Nanobot.

Le navigateur n'est ouvert qu'une seule fois par setup_google_auth.py.
Ensuite, les appels CLI utilisent le token local et le rafraichissent
automatiquement quand Google renvoie un access token expire.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = ROOT_DIR / "configs"
CREDENTIALS_FILE = CONFIG_DIR / "google_credentials.json"
TOKEN_FILE = CONFIG_DIR / "google_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/contacts",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
]


class GoogleAuthError(RuntimeError):
    """Erreur lisible cote CLI quand l'auth Google n'est pas prete."""


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _dependency_error(exc: Exception) -> GoogleAuthError:
    err = GoogleAuthError(
        "Dependances Google absentes. Lance d'abord: install_google.bat "
        "ou python -m pip install -r requirements_google.txt"
    )
    err.__cause__ = exc
    return err


def resolve_credentials_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Retourne le fichier client_secret OAuth a utiliser."""
    raw = path or os.environ.get("GOOGLE_CREDENTIALS_FILE") or CREDENTIALS_FILE
    return Path(raw).expanduser().resolve()


def prepare_credentials_file(
    credentials_path: str | os.PathLike[str] | None = None,
) -> Path:
    """Copie le client secret fourni vers configs/google_credentials.json."""
    ensure_config_dir()
    src = resolve_credentials_path(credentials_path)
    if not src.exists():
        raise GoogleAuthError(
            "Fichier credentials Google introuvable: "
            f"{src}\nPlace le JSON dans {CREDENTIALS_FILE} ou passe --credentials."
        )

    dest = CREDENTIALS_FILE.resolve()
    if src != dest:
        shutil.copy2(src, dest)
    return dest


def _has_required_scopes(creds: Any, scopes: list[str]) -> bool:
    granted = set(getattr(creds, "granted_scopes", None) or getattr(creds, "scopes", None) or [])
    if granted:
        return set(scopes).issubset(granted)
    if not hasattr(creds, "has_scopes"):
        return True
    try:
        return bool(creds.has_scopes(scopes))
    except Exception:
        return True


def _stored_token_scopes(token_file: Path) -> set[str]:
    try:
        data = json.loads(token_file.read_text(encoding="utf-8"))
    except Exception:
        return set()
    raw = data.get("scopes") or []
    return {str(scope) for scope in raw}


def save_credentials(creds: Any, token_path: Path = TOKEN_FILE) -> None:
    ensure_config_dir()
    token_path.write_text(creds.to_json(), encoding="utf-8")


def _load_client_config(credentials_file: Path) -> dict[str, Any]:
    """Charge le JSON OAuth et accepte les clients Desktop publics avec PKCE."""
    config = json.loads(credentials_file.read_text(encoding="utf-8"))
    client = config.get("installed") or config.get("web")
    if not isinstance(client, dict):
        raise GoogleAuthError(
            "Le fichier credentials Google doit contenir une section "
            "'installed' ou 'web'."
        )

    missing = {"client_id", "auth_uri", "token_uri"} - set(client)
    if missing:
        raise GoogleAuthError(
            "Fichier credentials Google incomplet. Champs manquants: "
            + ", ".join(sorted(missing))
        )

    return config


def _build_installed_app_flow(credentials_file: Path, scopes: list[str]) -> Any:
    """Construit le flow OAuth Desktop avec PKCE et secret optionnel."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except Exception as exc:  # pragma: no cover - dependances optionnelles
        raise _dependency_error(exc)

    class NanobotInstalledAppFlow(InstalledAppFlow):
        """Version Nanobot: n'envoie pas client_secret quand Google n'en fournit pas."""

        def fetch_token(self, **kwargs: Any) -> Any:
            secret = self.client_config.get("client_secret")
            if secret:
                kwargs.setdefault("client_secret", secret)
            kwargs.setdefault("code_verifier", self.code_verifier)
            return self.oauth2session.fetch_token(
                self.client_config["token_uri"],
                **kwargs,
            )

    config = _load_client_config(credentials_file)
    return NanobotInstalledAppFlow.from_client_config(
        config,
        scopes=scopes,
        autogenerate_code_verifier=True,
    )


def run_oauth_setup(
    *,
    credentials_path: str | os.PathLike[str] | None = None,
    token_path: str | os.PathLike[str] | None = None,
    scopes: list[str] | None = None,
    open_browser: bool = True,
) -> Any:
    """Lance le flux OAuth Desktop App et stocke le refresh token local."""
    scope_list = scopes or SCOPES
    token_file = Path(token_path or TOKEN_FILE)
    credentials_file = prepare_credentials_file(credentials_path)

    flow = _build_installed_app_flow(credentials_file, scope_list)
    creds = flow.run_local_server(
        port=0,
        open_browser=open_browser,
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true",
    )
    save_credentials(creds, token_file)
    return creds


def load_credentials(
    *,
    scopes: list[str] | None = None,
    token_path: str | os.PathLike[str] | None = None,
    credentials_path: str | os.PathLike[str] | None = None,
    interactive: bool = False,
) -> Any:
    """Charge le token, le rafraichit si besoin, ou lance OAuth en mode setup."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except Exception as exc:  # pragma: no cover - dependances optionnelles
        raise _dependency_error(exc)

    scope_list = scopes or SCOPES
    token_file = Path(token_path or TOKEN_FILE)
    creds = None

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scope_list)

    stored_scopes = _stored_token_scopes(token_file) if token_file.exists() else set()
    scope_ok = _has_required_scopes(creds, scope_list) if creds else False
    if stored_scopes:
        scope_ok = set(scope_list).issubset(stored_scopes)

    if creds and not scope_ok:
        if not interactive:
            raise GoogleAuthError(
                "Le token Google existe mais n'a pas tous les scopes requis. "
                "Relance: python setup_google_auth.py --force"
            )
        creds = None

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds, token_file)

    if not creds or not creds.valid:
        if interactive:
            creds = run_oauth_setup(
                credentials_path=credentials_path,
                token_path=token_file,
                scopes=scope_list,
            )
        else:
            raise GoogleAuthError(
                "Nanobot n'est pas encore connecte a Google. "
                "Lance une fois: python setup_google_auth.py"
            )

    return creds


def build_google_service(
    api_name: str,
    api_version: str,
    *,
    discovery_service_url: str | None = None,
) -> Any:
    """Construit un client google-api-python-client avec refresh auto."""
    creds = load_credentials()
    try:
        from googleapiclient.discovery import build
    except Exception as exc:  # pragma: no cover - dependances optionnelles
        raise _dependency_error(exc)

    kwargs: dict[str, Any] = {
        "credentials": creds,
        "cache_discovery": False,
    }
    if discovery_service_url:
        kwargs["discoveryServiceUrl"] = discovery_service_url
    return build(api_name, api_version, **kwargs)


def auth_status() -> dict[str, Any]:
    """Etat rapide sans forcer de refresh reseau."""
    status: dict[str, Any] = {
        "credentials_file": str(CREDENTIALS_FILE),
        "credentials_exists": CREDENTIALS_FILE.exists(),
        "token_file": str(TOKEN_FILE),
        "token_exists": TOKEN_FILE.exists(),
        "scopes": SCOPES,
    }
    if not TOKEN_FILE.exists():
        return status

    try:
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        stored_scopes = _stored_token_scopes(TOKEN_FILE)
        scope_ok = _has_required_scopes(creds, SCOPES)
        if stored_scopes:
            scope_ok = set(SCOPES).issubset(stored_scopes)
        status.update(
            {
                "valid": bool(creds.valid),
                "expired": bool(creds.expired),
                "has_refresh_token": bool(creds.refresh_token),
                "has_required_scopes": scope_ok,
                "stored_scopes": sorted(stored_scopes),
            }
        )
    except Exception as exc:
        status["token_error"] = str(exc)
    return status


def print_status() -> None:
    print(json.dumps(auth_status(), ensure_ascii=False, indent=2))
