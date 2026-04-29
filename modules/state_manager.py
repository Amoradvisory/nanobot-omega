#!/usr/bin/env python
"""
state_manager.py — Memoire Vive Operationnelle (State-Full)

Donne a l'agent un etat de travail vivant, structure, rapide d'acces.
Persiste entre tours, entre sessions, sans lourdeur.

Usage importable:
    from modules.state_manager import state

    state.set("current_task", "Deployer le module web")
    state.set("step", 3)
    state.push("actions_done", "Fichier cree: config.json")
    state.get("current_task")  # → "Deployer le module web"
    state.snapshot()           # → dict complet
    state.summary()            # → texte resume pour injection dans prompt

Usage CLI:
    python modules/state_manager.py show         # Affiche l'etat
    python modules/state_manager.py get <key>    # Lire une valeur
    python modules/state_manager.py set <key> <value>
    python modules/state_manager.py clear        # Reset
    python modules/state_manager.py summary      # Resume texte
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

STATE_DIR = Path("C:/AI/nanobot-omega/state")
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "working_state.json"
HISTORY_FILE = STATE_DIR / "state_history.jsonl"


class StateManager:
    """Memoire vive operationnelle — rapide, persistante, structuree."""

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._meta: dict[str, Any] = {}
        self._load()

    # --- Acces rapide ---

    def get(self, key: str, default: Any = None) -> Any:
        """Lire une valeur."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Ecrire/mettre a jour une valeur."""
        old = self._data.get(key)
        self._data[key] = value
        self._meta[key] = {
            "updated": time.time(),
            "type": type(value).__name__,
        }
        if old != value:
            self._append_history("set", key, value)
        self._save()

    def delete(self, key: str) -> bool:
        """Supprimer une cle."""
        if key in self._data:
            del self._data[key]
            self._meta.pop(key, None)
            self._append_history("delete", key, None)
            self._save()
            return True
        return False

    def push(self, key: str, value: Any, max_items: int = 50) -> None:
        """Ajouter a une liste (cree la liste si absente). FIFO avec limite."""
        lst = self._data.get(key, [])
        if not isinstance(lst, list):
            lst = [lst]
        lst.append(value)
        if len(lst) > max_items:
            lst = lst[-max_items:]
        self._data[key] = lst
        self._meta[key] = {"updated": time.time(), "type": "list", "count": len(lst)}
        self._save()

    def increment(self, key: str, amount: int = 1) -> int:
        """Incrementer un compteur."""
        val = self._data.get(key, 0)
        if not isinstance(val, (int, float)):
            val = 0
        val += amount
        self._data[key] = val
        self._meta[key] = {"updated": time.time(), "type": "counter"}
        self._save()
        return val

    # --- Vue d'ensemble ---

    def snapshot(self) -> dict[str, Any]:
        """Retourne l'etat complet."""
        return {
            "data": self._data.copy(),
            "meta": self._meta.copy(),
            "keys_count": len(self._data),
            "last_modified": max((m.get("updated", 0) for m in self._meta.values()), default=0),
        }

    def summary(self, max_lines: int = 20) -> str:
        """Resume texte injectable dans un prompt — compact, utile."""
        if not self._data:
            return "[Etat vide — aucune variable active]"

        lines = ["=== ETAT DE TRAVAIL ACTIF ==="]

        # Variables scalaires
        scalars = {k: v for k, v in self._data.items() if not isinstance(v, list)}
        if scalars:
            for k, v in list(scalars.items())[:max_lines]:
                v_str = str(v)
                if len(v_str) > 100:
                    v_str = v_str[:97] + "..."
                lines.append(f"  {k}: {v_str}")

        # Listes (derniers elements)
        lists = {k: v for k, v in self._data.items() if isinstance(v, list)}
        if lists:
            lines.append("--- Historiques ---")
            for k, lst in list(lists.items())[:5]:
                recent = lst[-3:] if len(lst) > 3 else lst
                lines.append(f"  {k} ({len(lst)} items): {', '.join(str(x)[:40] for x in recent)}")

        return "\n".join(lines[:max_lines])

    def keys(self) -> list[str]:
        """Liste des cles actives."""
        return list(self._data.keys())

    def clear(self) -> None:
        """Reset complet."""
        self._append_history("clear", "*", None)
        self._data.clear()
        self._meta.clear()
        self._save()

    # --- Workflow helpers ---

    def begin_task(self, name: str, details: str = "") -> None:
        """Demarre une tache (raccourci structure)."""
        self.set("current_task", name)
        self.set("task_details", details)
        self.set("task_started", time.strftime("%Y-%m-%d %H:%M:%S"))
        self.set("task_step", 0)
        self.push("task_history", f"[START] {name}")

    def advance_step(self, description: str) -> int:
        """Avance d'une etape dans la tache courante."""
        step = self.increment("task_step")
        self.push("actions_done", f"Step {step}: {description}")
        self.push("task_history", f"[STEP {step}] {description}")
        return step

    def complete_task(self, result: str = "OK") -> None:
        """Termine la tache courante."""
        task = self.get("current_task", "unknown")
        self.push("task_history", f"[DONE] {task}: {result}")
        self.push("completed_tasks", {
            "task": task,
            "result": result,
            "completed": time.strftime("%Y-%m-%d %H:%M:%S"),
            "steps": self.get("task_step", 0),
        })
        self.delete("current_task")
        self.delete("task_details")
        self.delete("task_step")
        self.delete("task_started")

    def note(self, text: str) -> None:
        """Ajouter une note rapide (decouverte, decision, observation)."""
        self.push("notes", f"[{time.strftime('%H:%M')}] {text}")

    # --- Persistance ---

    def _load(self):
        if STATE_FILE.exists():
            try:
                raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self._data = raw.get("data", {})
                self._meta = raw.get("meta", {})
            except (json.JSONDecodeError, KeyError):
                self._data = {}
                self._meta = {}

    def _save(self):
        try:
            STATE_FILE.write_text(
                json.dumps({"data": self._data, "meta": self._meta}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError:
            pass

    def _append_history(self, action: str, key: str, value: Any):
        """Journalise les changements (JSONL, rotation auto)."""
        try:
            entry = {
                "t": time.strftime("%Y-%m-%d %H:%M:%S"),
                "action": action,
                "key": key,
            }
            if value is not None:
                v_str = json.dumps(value, ensure_ascii=False, default=str)
                if len(v_str) > 200:
                    v_str = v_str[:197] + "..."
                entry["value"] = v_str

            with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            # Rotation si > 500KB
            if HISTORY_FILE.stat().st_size > 500_000:
                lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()
                HISTORY_FILE.write_text("\n".join(lines[-200:]) + "\n", encoding="utf-8")
        except OSError:
            pass


# --- Singleton ---
_instance: StateManager | None = None

def get_state() -> StateManager:
    global _instance
    if _instance is None:
        _instance = StateManager()
    return _instance

# Alias pratique
state = get_state()


# --- CLI ---
def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 0

    cmd = sys.argv[1].lower()
    s = get_state()

    if cmd == "show":
        snap = s.snapshot()
        print(json.dumps(snap, ensure_ascii=False, indent=2, default=str))
    elif cmd == "summary":
        print(s.summary())
    elif cmd == "get" and len(sys.argv) >= 3:
        val = s.get(sys.argv[2])
        print(json.dumps(val, ensure_ascii=False, default=str) if val is not None else "(vide)")
    elif cmd == "set" and len(sys.argv) >= 4:
        s.set(sys.argv[2], " ".join(sys.argv[3:]))
        print(f"OK: {sys.argv[2]} = {' '.join(sys.argv[3:])}")
    elif cmd == "clear":
        s.clear()
        print("Etat efface.")
    elif cmd == "keys":
        for k in s.keys():
            print(f"  {k}")
    elif cmd == "test":
        print("=== Test State Manager ===\n")
        s.clear()
        s.begin_task("Installation module web", "Deployer les composants frontend")
        s.advance_step("Creer le dossier de structure")
        s.advance_step("Ecrire config.json")
        s.note("La version de Node est 22.12 — compatible")
        s.advance_step("Installer les dependances")
        s.complete_task("3 fichiers crees, deps installees")
        print(s.summary())
        print("\n[OK] Test passe.")
    else:
        print(f"Commande inconnue: {cmd}")
        print(__doc__)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
