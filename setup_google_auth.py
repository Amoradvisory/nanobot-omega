#!/usr/bin/env python
"""Script one-shot pour connecter Nanobot a Google."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from google_auth import CREDENTIALS_FILE, TOKEN_FILE, auth_status, run_oauth_setup


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure OAuth Google pour Nanobot.")
    parser.add_argument(
        "--credentials",
        help=f"Chemin du client_secret JSON Google (defaut: {CREDENTIALS_FILE})",
    )
    parser.add_argument(
        "--token",
        default=str(TOKEN_FILE),
        help=f"Chemin du token local (defaut: {TOKEN_FILE})",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Affiche l'URL OAuth au lieu d'ouvrir le navigateur automatiquement.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Affiche l'etat de l'auth sans lancer OAuth.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Relance le consentement et remplace le token existant.",
    )
    args = parser.parse_args()

    if args.status:
        print(json.dumps(auth_status(), ensure_ascii=False, indent=2))
        return 0

    token_path = Path(args.token)
    if args.force and token_path.exists():
        token_path.unlink()

    try:
        creds = run_oauth_setup(
            credentials_path=args.credentials,
            token_path=token_path,
            open_browser=not args.no_browser,
        )
    except Exception as exc:
        print(f"[ERREUR] {exc}", file=sys.stderr)
        return 1

    print("[OK] Auth Google configuree.")
    print(f"Token stocke dans: {token_path}")
    if getattr(creds, "refresh_token", None):
        print("[OK] Refresh token present: Nanobot pourra se reconnecter automatiquement.")
    else:
        print("[WARN] Refresh token absent. Relance avec --force si les sessions expirent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
