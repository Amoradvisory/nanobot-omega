from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(r"C:\AI\nanobot-omega")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.google_tools import is_google_prompt  # noqa: E402


CASES = [
    (
        "Diste est bien ouvert, mais pas sur le bon compte. Il faut que tu deconnectes le compte, comme ca je pourrai reconnecter avec la bonne adresse mail.",
        False,
    ),
    (
        "ouvre ton navigateur et je me connecte avec la bonne adresse mail sur github",
        False,
    ),
    (
        "bonne nouvelle reponse de codex: Gmail modify est actif, Google Workspace a 44 outils, documentation durable.",
        False,
    ),
    (
        "ranger mon bureau et supprimer les raccourcis pour que ce soit propre",
        False,
    ),
    (
        "qu est ce que j ai dans mon Gmail",
        True,
    ),
    (
        "liste mes derniers mails",
        True,
    ),
    (
        "cherche dans gmail facture proximus",
        True,
    ),
    (
        "envoie un mail a test@example.com corps: bonjour",
        True,
    ),
    (
        "ajoute un rendez-vous dans mon agenda demain a 14h",
        True,
    ),
]


def main() -> int:
    failures: list[str] = []
    for prompt, expected in CASES:
        actual = is_google_prompt(prompt)
        if actual != expected:
            failures.append(f"{prompt!r}: expected {expected}, got {actual}")
    if failures:
        print("\n".join(failures))
        return 1
    print(f"google prompt routing ok: {len(CASES)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
