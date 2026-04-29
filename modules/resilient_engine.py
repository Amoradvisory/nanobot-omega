#!/usr/bin/env python
"""
resilient_engine.py — Moteur d'Execution Resilient Ultra-Leger

Wrapper intelligent pour toute operation sujette a echec transitoire.
Fournit : retry adaptatif, detection de boucle, logging leger, fallback.

Usage importable:
    from modules.resilient_engine import resilient_call, detect_loop

Usage CLI:
    python modules/resilient_engine.py test
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

STATE_DIR = Path("C:/AI/nanobot-omega/state")
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = STATE_DIR / "resilient.log"
LOOP_STATE = STATE_DIR / "loop_detector.json"


# ---------------------------------------------------------------------------
# Erreurs transitoires reconnues
# ---------------------------------------------------------------------------
TRANSIENT_PATTERNS = [
    "timeout", "timed out", "connection reset", "connection refused",
    "503", "502", "transient_network", "transient_network", "transient_network", "transient_network",
    "econnreset", "econnrefused", "etimedout", "network",
    "temporarily unavailable", "try again", "busy", "capacity",
    "socket hang up", "getaddrinfo", "ENOTFOUND",
]

FATAL_PATTERNS = [
    "permission denied", "access denied", "not found", "404",
    "invalid argument", "syntax error", "unauthorized", "401", "403",
    "file not found", "no such file", "module not found",
]


def is_transient(error: str) -> bool:
    """Detecte si une erreur est transitoire (merite un retry)."""
    lower = error.lower()
    # Si c'est fatal, pas de retry
    if any(p in lower for p in FATAL_PATTERNS):
        return False
    return any(p in lower for p in TRANSIENT_PATTERNS)


# ---------------------------------------------------------------------------
# Retry adaptatif
# ---------------------------------------------------------------------------
@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    backoff_factor: float = 2.0
    jitter: bool = True


def resilient_call(
    func: Callable[..., Any],
    *args,
    config: RetryConfig | None = None,
    label: str = "operation",
    fallback: Callable[..., Any] | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Execute une fonction avec retry intelligent.

    Returns:
        {"ok": True, "result": ..., "attempts": N, "total_ms": M}
        {"ok": False, "error": "...", "attempts": N, "transient": bool, "total_ms": M}
    """
    cfg = config or RetryConfig()
    t0 = time.time()
    last_error = ""

    for attempt in range(1, cfg.max_attempts + 1):
        try:
            result = func(*args, **kwargs)
            duration_ms = int((time.time() - t0) * 1000)

            # Si le resultat est un dict avec "ok": False, traiter comme erreur
            if isinstance(result, dict) and result.get("ok") is False:
                err = result.get("error", "unknown error")
                last_error = err
                if is_transient(err) and attempt < cfg.max_attempts:
                    delay = _compute_delay(attempt, cfg)
                    _log(f"[RETRY] {label} attempt {attempt}/{cfg.max_attempts}: {err[:100]} — wait {delay:.1f}s")
                    time.sleep(delay)
                    continue
                else:
                    # Non-transitoire ou derniere tentative
                    result["attempts"] = attempt
                    result["total_ms"] = duration_ms
                    return result

            # Succes
            _log(f"[OK] {label} en {duration_ms}ms (tentative {attempt})")
            return {
                "ok": True,
                "result": result,
                "attempts": attempt,
                "total_ms": duration_ms,
            }

        except Exception as exc:
            last_error = str(exc)
            duration_ms = int((time.time() - t0) * 1000)

            if not is_transient(last_error):
                # Erreur fatale — pas de retry
                break

            if attempt < cfg.max_attempts:
                delay = _compute_delay(attempt, cfg)
                _log(f"[RETRY] {label} attempt {attempt}/{cfg.max_attempts}: {last_error[:100]} — wait {delay:.1f}s")
                time.sleep(delay)
            else:
                break

    duration_ms = int((time.time() - t0) * 1000)

    # Toutes les tentatives echouees — essayer le fallback
    actual_attempts = min(attempt, cfg.max_attempts) if 'attempt' in dir() else cfg.max_attempts
    if fallback:
        _log(f"[FALLBACK] {label} apres {actual_attempts} echecs — fallback actif")
        try:
            fb_result = fallback(*args, **kwargs)
            return {
                "ok": True,
                "result": fb_result,
                "attempts": actual_attempts,
                "used_fallback": True,
                "total_ms": int((time.time() - t0) * 1000),
            }
        except Exception as fb_exc:
            last_error = f"Fallback echoue aussi: {fb_exc}"

    _log(f"[FAIL] {label} apres {actual_attempts} tentatives: {last_error[:200]}")
    return {
        "ok": False,
        "error": last_error,
        "attempts": actual_attempts,
        "transient": is_transient(last_error),
        "total_ms": duration_ms,
    }


def _compute_delay(attempt: int, cfg: RetryConfig) -> float:
    delay = min(cfg.base_delay_s * (cfg.backoff_factor ** (attempt - 1)), cfg.max_delay_s)
    if cfg.jitter:
        import random
        delay *= (0.5 + random.random() * 0.5)
    return delay


# ---------------------------------------------------------------------------
# Detecteur de boucle (No-Loop)
# ---------------------------------------------------------------------------
class LoopDetector:
    """Detecte quand l'agent repete la meme action sans progres."""

    def __init__(self, window_size: int = 5, threshold: int = 3):
        self.window_size = window_size
        self.threshold = threshold
        self._history: deque[str] = deque(maxlen=window_size)
        self._load()

    def record(self, action_signature: str) -> dict[str, Any]:
        """Enregistre une action et detecte les boucles.

        Args:
            action_signature: Description courte de l'action (ex: "navigate:google.com/search")

        Returns:
            {"looping": bool, "count": int, "suggestion": str}
        """
        sig = self._hash(action_signature)
        self._history.append(sig)
        self._save()

        # Compter les repetitions consecutives
        count = 0
        for h in reversed(self._history):
            if h == sig:
                count += 1
            else:
                break

        if count >= self.threshold:
            suggestion = self._suggest_escape(action_signature, count)
            _log(f"[LOOP] Action repetee {count}x: {action_signature[:80]} — {suggestion}")
            return {"looping": True, "count": count, "suggestion": suggestion}

        return {"looping": False, "count": count, "suggestion": ""}

    def clear(self):
        """Reset l'historique apres un changement de strategie reussi."""
        self._history.clear()
        self._save()

    def _hash(self, s: str) -> str:
        return hashlib.md5(s.encode()).hexdigest()[:12]

    def _suggest_escape(self, action: str, count: int) -> str:
        lower = action.lower()
        if "navigate" in lower or "url" in lower:
            return "STOP navigation repetee. Changer d'approche: essayer fetch MCP ou search MCP au lieu du navigateur."
        if "click" in lower:
            return "STOP clics repetes. L'element est probablement introuvable ou change. Faire un screenshot, analyser, puis cibler autrement."
        if "search" in lower or "google" in lower:
            return "STOP recherches repetees. Reformuler la requete ou utiliser une source differente (fetch direct, API, autre moteur)."
        if "type" in lower or "input" in lower:
            return "STOP saisie repetee. Verifier que le champ est actif (screenshot + focus). Essayer clipboard + Ctrl+V."
        if count >= 5:
            return "CRITICAL: 5+ repetitions. Abandonner cette approche. Documenter le blocage et passer a une methode completement differente."
        return f"Action repetee {count}x. Changer de strategie : varier l'approche, verifier l'etat reel (screenshot), ou passer a un plan B."

    def _load(self):
        if LOOP_STATE.exists():
            try:
                data = json.loads(LOOP_STATE.read_text(encoding="utf-8"))
                self._history = deque(data.get("history", []), maxlen=self.window_size)
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self):
        try:
            LOOP_STATE.write_text(
                json.dumps({"history": list(self._history), "updated": time.time()}),
                encoding="utf-8"
            )
        except OSError:
            pass


# Singleton
_loop_detector: LoopDetector | None = None

def detect_loop(action: str) -> dict[str, Any]:
    """Interface publique pour la detection de boucle."""
    global _loop_detector
    if _loop_detector is None:
        _loop_detector = LoopDetector()
    return _loop_detector.record(action)

def clear_loop():
    """Reset le detecteur apres un changement de strategie."""
    global _loop_detector
    if _loop_detector is None:
        _loop_detector = LoopDetector()
    _loop_detector.clear()


# ---------------------------------------------------------------------------
# Logging leger
# ---------------------------------------------------------------------------
def _log(msg: str):
    """Log une ligne dans le fichier + stderr (non bloquant)."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
        # Rotation si > 1MB
        if LOG_FILE.stat().st_size > 1_000_000:
            _rotate_log()
    except OSError:
        pass


def _rotate_log():
    """Garde les 500 dernieres lignes."""
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        LOG_FILE.write_text("\n".join(lines[-500:]) + "\n", encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# CLI de test
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("=== Test Resilient Engine ===\n")

        # Test 1: Retry sur erreur transitoire
        call_count = 0
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("connection reset by peer")
            return {"value": 42}

        result = resilient_call(flaky_func, label="test-transient", config=RetryConfig(base_delay_s=0.1))
        print(f"Test transient: {result}")
        assert result["ok"], "Devrait reussir apres retry"
        assert result["attempts"] == 3

        # Test 2: Detection de boucle
        detector = LoopDetector(threshold=3)
        for i in range(4):
            r = detector.record("navigate:google.com/search?q=test")
        print(f"Test loop: {r}")
        assert r["looping"], "Devrait detecter une boucle"

        # Test 3: Erreur fatale (pas de retry)
        def fatal_func():
            raise PermissionError("permission denied: /root/secret")

        result = resilient_call(fatal_func, label="test-fatal", config=RetryConfig(base_delay_s=0.1))
        print(f"Test fatal: {result}")
        assert not result["ok"]
        assert result["attempts"] == 1, "Ne devrait pas retry une erreur fatale"

        print("\n[OK] Tous les tests passes.")
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
