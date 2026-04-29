"""
Gemini Orchestrator Provider for Nanobot.

Implements the LLMProvider interface so Nanobot can use the multi-instance
Gemini orchestrator as its LLM backend. Handles tool calls, streaming,
and the full chat completion lifecycle.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bascule Ollama local (debloque quand Gemini est en cooldown cluster).
# NANOBOT_BACKEND=ollama  -> tous les appels LLM partent sur Ollama local.
# NANOBOT_BACKEND=gemini  -> comportement historique cloud.
# NANOBOT_OLLAMA_MODEL    -> modele (defaut : qwen2.5:3b, adapte i7-5600U).
# NANOBOT_OLLAMA_HOST     -> http://127.0.0.1:11434 (defaut).
# ---------------------------------------------------------------------------
_BACKEND = os.environ.get("NANOBOT_BACKEND", "ollama").lower().strip()
_OLLAMA_HOST = os.environ.get("NANOBOT_OLLAMA_HOST", "http://127.0.0.1:11434")
_OLLAMA_MODEL = os.environ.get("NANOBOT_OLLAMA_MODEL", "qwen2.5:3b")
_OLLAMA_FALLBACK_MODEL = os.environ.get("NANOBOT_OLLAMA_FALLBACK", "qwen2.5:0.5b")
_OLLAMA_TIMEOUT = int(os.environ.get("NANOBOT_OLLAMA_TIMEOUT", "180"))
_OLLAMA_NUM_CTX = int(os.environ.get("NANOBOT_OLLAMA_NUM_CTX", "8192"))


def _ollama_chat(messages: list[dict[str, Any]], *, temperature: float = 0.4,
                 max_tokens: int = 4096) -> dict[str, Any]:
    """Appel HTTP synchrone vers Ollama /api/chat. Retourne un dict
    {"ok": bool, "content": str, "model": str, "error": str|None}."""
    # Truncate history to fit num_ctx (rough: 1 token ~= 4 chars).
    # Keep system prompt + last N messages until total chars < num_ctx*3.
    char_budget = _OLLAMA_NUM_CTX * 3
    if messages and sum(len(m.get("content", "")) for m in messages) > char_budget:
        head = messages[:1] if messages[0].get("role") == "system" else []
        tail: list[dict[str, Any]] = []
        used = sum(len(m.get("content", "")) for m in head)
        for msg in reversed(messages[len(head):]):
            mlen = len(msg.get("content", ""))
            if used + mlen > char_budget:
                break
            tail.insert(0, msg)
            used += mlen
        messages = head + tail

    payload = {
        "model": _OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": _OLLAMA_NUM_CTX,
            "num_predict": max_tokens,
        },
    }

    last_error = ""
    for candidate_model in (_OLLAMA_MODEL, _OLLAMA_FALLBACK_MODEL):
        if candidate_model != _OLLAMA_MODEL and candidate_model == _OLLAMA_FALLBACK_MODEL:
            payload["model"] = candidate_model
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{_OLLAMA_HOST}/api/chat", data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=_OLLAMA_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                content = ((body.get("message") or {}).get("content") or "").strip()
                if not content:
                    last_error = "Ollama: reponse vide"
                    continue
                return {"ok": True, "content": content,
                        "model": payload["model"], "error": None}
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8"))
                last_error = err_body.get("error", f"HTTP {e.code}")
            except Exception:
                last_error = f"HTTP {e.code}"
            if "not found" in last_error.lower() and candidate_model != _OLLAMA_FALLBACK_MODEL:
                continue
            break
        except urllib.error.URLError as e:
            last_error = f"Ollama daemon injoignable: {e.reason}"
            break
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            break

    return {"ok": False, "content": "", "model": payload["model"], "error": last_error}

# Ensure nanobot site-packages are importable
_NANOBOT_SITE = Path(
    r"C:\Users\user\AppData\Roaming\uv\tools\nanobot-ai\Lib\site-packages"
)
if str(_NANOBOT_SITE) not in sys.path:
    sys.path.insert(0, str(_NANOBOT_SITE))

from nanobot.providers.base import GenerationSettings, LLMProvider, LLMResponse, ToolCallRequest

# Local import of orchestrator
_OMEGA_ROOT = Path(r"C:\AI\nanobot-omega")
if str(_OMEGA_ROOT) not in sys.path:
    sys.path.insert(0, str(_OMEGA_ROOT))
_FIRE_ROOT = Path(r"C:\Users\user\Desktop\FIRE")
_SHARED_BROWSER_ROOT = _OMEGA_ROOT / "shared-browser"
_SHARED_CHROME_PROFILE = _SHARED_BROWSER_ROOT / "chrome-profile"
_HEALTH_TEXT_PATH = _OMEGA_ROOT / "health" / "omega_status.txt"
_MISSION_TEXT_PATH = _OMEGA_ROOT / "MISSION_YOLO.md"
_AGENT_V2_TEXT_PATH = _OMEGA_ROOT / "AGENT_V2.md"
_STARTUP_CONTEXT_TEXT_PATH = _OMEGA_ROOT / "workspace" / "NANOBOT_STARTUP_CONTEXT.md"
_OMEGA_SCRIPTS = _OMEGA_ROOT / "scripts"
_DASHBOARD_URL = "http://127.0.0.1:18791/dashboard/"
_IDENTITY_PROMPT = """

## Nanobot Omega Identity
- Nom: Nanobot Omega.
- Role: agent personnel operationnel d'Amor.
- Mission: agir, verifier, reparer, repondre court et vrai.
- Environnement: Windows 10 Pro, root `C:/AI/nanobot-omega`, Obsidian vault `C:/Users/user/Mon Drive/DriveSyncFiles/ARCHITECTE_SYSTEM`, Google Workspace `monagenda.be@gmail.com`.
- Regles: ne pas exposer raisonnement/tool-noise; ne jamais pretendre qu'un outil liste manque; utiliser les capacites reelles et les diagnostics avant de refuser.
""".strip()

from gemini_cli_orchestrator import GeminiOrchestrator, get_orchestrator

import json_repair


def _short_id() -> str:
    import secrets
    import string
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(9))


class GeminiOrchestratorProvider(LLMProvider):
    """Nanobot LLM provider backed by the Gemini multi-instance orchestrator.

    This provider translates Nanobot's chat messages + tool definitions into
    prompts for the Gemini API (via the orchestrator), and parses responses
    back into LLMResponse objects with tool call support.
    """

    def __init__(
        self,
        default_model: str = "gemini-3-flash-preview",
        orchestrator: GeminiOrchestrator | None = None,
    ) -> None:
        super().__init__(api_key="orchestrator-managed", api_base="orchestrator://local")
        self.default_model = default_model
        self._orchestrator = orchestrator or get_orchestrator()
        self.generation = GenerationSettings(
            temperature=0.4,
            max_tokens=4096,
        )

    def get_default_model(self) -> str:
        return self.default_model

    @staticmethod
    def _last_user_text(messages: list[dict[str, Any]]) -> str:
        skip_markers = (
            "[tool result",
            '"tool_calls"',
            "assistant:",
            "available tools",
            "## available tools",
            "# nanobot",
        )
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    parts: list[str] = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            parts.append(block)
                    content = "\n".join(parts)
                text = str(content or "").strip()
                lowered = text.lower()
                if any(marker in lowered for marker in skip_markers):
                    continue
                if len(text) > 250 and "\n" in text:
                    continue
                return text
        return ""

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFD", text)
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        normalized = normalized.lower().strip()
        normalized = normalized.replace("?", " ").replace("!", " ")
        normalized = normalized.replace("'", " ").replace("’", " ")
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    @staticmethod
    def _flatten_message_text(content: Any) -> str:
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(parts)
        return str(content or "")

    @classmethod
    def _is_telegram_context(cls, messages: list[dict[str, Any]]) -> bool:
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            text = cls._flatten_message_text(msg.get("content"))
            if "Channel: telegram" in text or "Reply Style: concise mobile" in text:
                return True
        return False

    @staticmethod
    def _clean_output_text(text: str | None, *, strip_tool_plumbing: bool = False) -> str | None:
        if not text:
            return text
        cleaned = text.strip()
        # Tool-call JSON and raw tool hints are execution plumbing, not
        # user-facing Telegram content.
        if strip_tool_plumbing:
            cleaned = re.sub(
                r"```(?:json)?\s*[\s\S]*?\"tool_calls\"[\s\S]*?```",
                "",
                cleaned,
                flags=re.IGNORECASE,
            )
            cleaned = re.sub(
                r"\{\s*\"tool_calls\"\s*:\s*\[[\s\S]*?\]\s*\}",
                "",
                cleaned,
                flags=re.IGNORECASE,
            )
            cleaned = re.sub(
                r"(?m)^\s*(?:mcp_[\w-]+|browser_automation|desktop_automation|write_todos)\s*\(.*\)\s*$",
                "",
                cleaned,
            )
            cleaned = re.sub(r"(?m)^\s*\[Called tool:.*?\]\s*$", "", cleaned)
        cleaned = re.sub(
            r"^MCP issues detected\. Run\s+`?/mcp list`?\s+for status\.?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _find_windows_app(*candidates: str) -> str | None:
        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        known_paths = [
            r"C:\Users\user\AppData\Local\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Users\user\AppData\Local\Programs\Opera\opera.exe",
            r"C:\Users\user\AppData\Local\Programs\Opera GX\opera.exe",
            r"C:\Users\user\AppData\Roaming\Telegram Desktop\Telegram.exe",
            r"C:\Users\user\AppData\Local\Telegram Desktop\Telegram.exe",
        ]
        for path in known_paths:
            name = Path(path).name.lower()
            if any(candidate.lower() in name for candidate in candidates) and Path(path).exists():
                return path
        return None

    @staticmethod
    def _find_start_app_id(pattern: str) -> str | None:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-StartApps | Where-Object { $_.Name -match "
                f"'{pattern}' }} | Select-Object -ExpandProperty AppID -First 1"
            ),
        ]
        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return None
        value = (result.stdout or "").strip()
        return value or None

    @staticmethod
    def _launch_shared_chrome(app_path: str) -> None:
        _SHARED_CHROME_PROFILE.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(
            [
                app_path,
                f"--user-data-dir={_SHARED_CHROME_PROFILE}",
                "--new-window",
                "about:blank",
            ],
            close_fds=True,
        )

    @staticmethod
    def _extract_software_target(raw_text: str) -> str | None:
        url_match = re.search(r"https?://\S+", raw_text, flags=re.IGNORECASE)
        if url_match:
            return url_match.group(0).rstrip(").,;!?")

        normalized = unicodedata.normalize("NFD", raw_text)
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        normalized = normalized.lower()
        normalized = re.sub(r"[’'`]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()

        patterns = [
            r"(?:telecharge|telecharger|installe|installer|install|download)\s+(?:l application|application|app|logiciel|programme\s+)?(.+)$",
            r"(?:ouvre|ouvrir|lance|lancer|demarre|demarrer)\s+(?:l application|application|app|logiciel|programme\s+)?(.+)$",
        ]
        target = None
        for pattern in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                target = match.group(1)
                break
        if not target:
            return None

        target = re.split(r"\b(?:stp|svp|merci|please)\b", target, maxsplit=1)[0]
        target = target.strip(" .,:;!?")
        target = re.sub(r"^(?:le|la|les|l|un|une|du|de|des)\s+", "", target).strip()
        if not target:
            return None
        blocked_prefixes = (
            "site ",
            "page ",
            "onglet ",
            "fichier ",
            "document ",
            "dossier ",
            "navigateur ",
            "url ",
        )
        if any(target.startswith(prefix) for prefix in blocked_prefixes):
            return None
        return target

    @classmethod
    def _handle_software_request(
        cls,
        raw_text: str,
        text: str,
        *,
        ensure_mode: bool,
    ) -> LLMResponse | None:
        target = cls._extract_software_target(raw_text)
        if not target:
            return None

        browser_words = ("chrome", "google chrome", "opera", "navigateur")
        if any(word in target for word in browser_words):
            return None

        args = ["ensure", target] if ensure_mode else ["open", target]
        if ensure_mode and any(word in text for word in ("ouvre", "ouvrir", "lance", "lancer", "demarre", "demarrer")):
            args.append("--open")
        timeout = 1800 if ensure_mode else 180
        result, ok = cls._run_omega_python("app_acquisition.py", args, timeout=timeout)
        content = (result or "").strip()
        if not content:
            return None
        return LLMResponse(
            content=content,
            finish_reason="stop" if ok else "error",
        )

    @staticmethod
    def _extract_local_path(raw_text: str) -> str | None:
        matches = re.findall(r"[A-Za-z]:\\[^\r\n\"]+", raw_text)
        if not matches:
            return None
        best = max(matches, key=len).strip().rstrip(").,;!?")
        return best or None

    @staticmethod
    def _extract_web_url(raw_text: str) -> str | None:
        direct = re.search(r"https?://\S+", raw_text, flags=re.IGNORECASE)
        if direct:
            return direct.group(0).rstrip(").,;!?")

        bare = re.search(
            r"\b(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s]*)?",
            raw_text,
            flags=re.IGNORECASE,
        )
        if not bare:
            return None
        candidate = bare.group(0).rstrip(").,;!?")
        if "\\" in candidate or ":" in candidate:
            return None
        if candidate.lower().startswith("www."):
            return "https://" + candidate
        if not re.match(r"^[a-z]+://", candidate, flags=re.IGNORECASE):
            return "https://" + candidate
        return candidate

    @classmethod
    def _handle_scraping_request(
        cls,
        raw_text: str,
        text: str,
    ) -> LLMResponse | None:
        url = cls._extract_web_url(raw_text)
        if not url:
            return None

        scrape_words = (
            "scrape",
            "scraper",
            "scraping",
            "extract",
            "extrais",
            "extraire",
            "recupere",
            "recuperer",
            "collecte",
            "crawler",
            "crawl",
            "aspire",
            "donnees",
            "data",
            "table",
            "tableau",
            "listing",
            "annonces",
            "catalogue",
        )
        context_words = ("site", "page", "web", "url", "html")
        if not (
            any(word in text for word in scrape_words)
            and (any(word in text for word in context_words) or "http" in raw_text.lower() or "www." in raw_text.lower())
        ):
            return None

        args = ["scrape", url]
        timeout = 1800

        if any(word in text for word in ("javascript", "js", "render", "rendu", "dynamique", "spa")):
            args.append("--render-js")

        if any(word in text for word in ("excel", "xlsx", "csv", "table", "tableau", "colonnes")):
            args.append("--force-excel")

        result, ok = cls._run_omega_python("scraping_champion.py", args, timeout=timeout)
        content = (result or "").strip()
        if not content:
            return None
        return LLMResponse(
            content=content,
            finish_reason="stop" if ok else "error",
        )

    @staticmethod
    def _extract_obsidian_capture_content(raw_text: str) -> str | None:
        patterns = (
            r"(?:ajoute|ajouter|capture|enregistre|note|ecris|écris|mets?)\s+(?:dans\s+|sur\s+)?obsidian(?:\s+que)?\s*[:,-]?\s*(.+)$",
            r"(?:dans\s+obsidian|sur\s+obsidian)\s*[:,-]?\s*(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, raw_text, flags=re.IGNORECASE)
            if match:
                content = match.group(1).strip().strip('"')
                return content or None
        return None

    @staticmethod
    def _extract_obsidian_capture_content_flexible(raw_text: str) -> str | None:
        patterns = (
            r"(?:ajoute|ajouter|capture|enregistre|note|ecris|ecrire|ecrit|écris|écrire|écrit|mets?|cree|creer|crée|créer)\s+(?:dans\s+|sur\s+)?obsidian(?:\s+que)?\s*(?:[:.,-]\s*)?(.+)$",
            r"(?:dans\s+obsidian|sur\s+obsidian)\s*(?:[:.,-]\s*)?(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, raw_text, flags=re.IGNORECASE)
            if not match:
                continue
            content = match.group(1).strip().strip('"')
            if content:
                return content
        return None

    @staticmethod
    def _extract_obsidian_search_query(raw_text: str) -> str | None:
        patterns = (
            r"(?:cherche|recherche|trouve)\s+(?:dans\s+)?(?:mon\s+)?(?:vault\s+)?obsidian\s*[:,-]?\s*(.+)$",
            r"(?:dans\s+obsidian|dans\s+le\s+vault)\s*[:,-]?\s*(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, raw_text, flags=re.IGNORECASE)
            if match:
                query = match.group(1).strip().strip('"')
                return query or None
        return None

    @classmethod
    def _handle_obsidian_request(
        cls,
        raw_text: str,
        text: str,
    ) -> LLMResponse | None:
        if "obsidian" not in text and "vault" not in text:
            return None

        args: list[str] | None = None
        timeout = 180
        local_path = cls._extract_local_path(raw_text)

        if any(phrase in text for phrase in ("etat obsidian", "statut obsidian", "status obsidian", "etat du vault", "statut du vault")):
            args = ["status"]
        elif any(word in text for word in ("relie", "relier", "relies", "tisse", "tisser", "liens", "relations", "passerelles")):
            args = ["relations", "--all"]
            timeout = 1800
        elif any(word in text for word in ("synchronise", "synchroniser", "sync")) and any(word in text for word in ("memoire", "memory")):
            args = ["sync-memory"]
            timeout = 1800
        elif local_path and any(word in text for word in ("importe", "importer", "ajoute", "ajouter", "range", "classe")):
            args = ["import", local_path]
            timeout = 1800
        elif any(word in text for word in ("cherche", "recherche", "trouve")):
            query = cls._extract_obsidian_search_query(raw_text)
            if query:
                args = ["search", query]
        elif any(word in text for word in ("ouvre", "ouvrir", "lance", "lancer", "demarre", "demarrer")):
            args = ["open"]
        elif any(
            word in text
            for word in ("ajoute", "ajouter", "capture", "enregistre", "note", "ecris", "ecrire", "ecrit", "mets", "cree", "creer")
        ):
            content = cls._extract_obsidian_capture_content(raw_text)
            if not content:
                content = cls._extract_obsidian_capture_content_flexible(raw_text)
            if content:
                args = ["capture", "--content", content]

        if not args:
            return None

        result, ok = cls._run_omega_python("obsidian_second_brain.py", args, timeout=timeout)
        content = (result or "").strip()
        if not content:
            return None
        return LLMResponse(
            content=content,
            finish_reason="stop" if ok else "error",
        )

    @staticmethod
    def _shared_browser_summary() -> str:
        return (
            "Le navigateur de reference est Google Chrome avec le profil partage "
            f"{_SHARED_CHROME_PROFILE}. Le lanceur principal est "
            "C:/AI/nanobot-omega/Open-Shared-Nanobot-Browser.bat."
        )

    @staticmethod
    def _omega_status_summary() -> str:
        try:
            from omega_status import build_status, to_text

            return to_text(build_status())
        except Exception:
            pass

        if _HEALTH_TEXT_PATH.exists():
            text = _HEALTH_TEXT_PATH.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                return text
        return (
            "Etat Omega indisponible pour l'instant. Le fichier de sante attendu est "
            "C:/AI/nanobot-omega/health/omega_status.txt."
        )

    @staticmethod
    def _mission_yolo_prompt() -> str:
        fallback = (
            "Nanobot runs on a dedicated PC. Treat each user request as a mission, "
            "continue until completion or a real blocker, use available tools without "
            "ordinary confirmation, retry with another route when a route fails, and "
            "reply in French with concise operational results."
        )
        try:
            if _MISSION_TEXT_PATH.exists():
                text = _MISSION_TEXT_PATH.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    return "\n\n## Mission YOLO\n" + text
        except Exception:
            pass
        return "\n\n## Mission YOLO\n" + fallback

    @staticmethod
    def _agent_v2_prompt() -> str:
        fallback = (
            "Use Agent V2 for actionable work: identify the goal, choose a short plan, "
            "act with tools, verify the result, repair and retry if verification fails, "
            "then report the concise final result in French."
        )
        try:
            if _AGENT_V2_TEXT_PATH.exists():
                text = _AGENT_V2_TEXT_PATH.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    return "\n\n## Agent V2\n" + text
        except Exception:
            pass
        return "\n\n## Agent V2\n" + fallback

    @staticmethod
    def _startup_context_prompt() -> str:
        fallback = (
            "Startup context file missing. Before claiming a capability is unavailable, "
            "inspect C:/AI/nanobot-omega/workspace/NANOBOT_RECENT_UPGRADES.md and run "
            "local diagnostics or capability scripts."
        )
        try:
            if _STARTUP_CONTEXT_TEXT_PATH.exists():
                text = _STARTUP_CONTEXT_TEXT_PATH.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    return "\n\n## Startup Capability Context\n" + text[:16000]
        except Exception:
            pass
        return "\n\n## Startup Capability Context\n" + fallback

    @staticmethod
    def _augment_system_prompt(system_prompt: str) -> str:
        prompt = system_prompt or ""
        if "## Nanobot Omega Identity" not in prompt:
            prompt += "\n\n" + _IDENTITY_PROMPT
        if "## Mission YOLO" not in prompt:
            prompt += GeminiOrchestratorProvider._mission_yolo_prompt()
        if "## Agent V2" not in prompt:
            prompt += GeminiOrchestratorProvider._agent_v2_prompt()
        if "## Startup Capability Context" not in prompt:
            prompt += GeminiOrchestratorProvider._startup_context_prompt()
        return prompt

    @staticmethod
    def _is_short_direct_browser_command(raw_text: str) -> bool:
        text = raw_text or ""
        if len(text.strip()) > 120:
            return False
        if "\n" in text or "\r" in text:
            return False
        low = text.lower()
        if "```" in text or re.search(r"https?://|www\.", low):
            return False
        if re.search(r"\{\s*['\"]?\w+['\"]?\s*[:=]", text):
            return False
        return True

    @staticmethod
    def _run_omega_python(script_name: str, args: list[str] | None = None, timeout: int = 90) -> tuple[str, bool]:
        script_path = _OMEGA_SCRIPTS / script_name
        if not script_path.exists():
            return f"Script introuvable: {script_path}", False
        cmd = [sys.executable, str(script_path), *(args or [])]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(_OMEGA_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"Timeout pendant l'execution de {script_name}.", False
        except Exception as exc:
            return f"Erreur {script_name}: {exc}", False
        output = (proc.stdout or proc.stderr or "").strip()
        return output or f"{script_name} termine sans sortie.", proc.returncode == 0

    @staticmethod
    def _full_status_summary(repair: bool = True) -> tuple[str, bool]:
        args = ["--write"]
        if repair:
            args.extend(["--repair", "--repair-wait", "10"])
        return GeminiOrchestratorProvider._run_omega_python(
            "nanobot_full_status.py",
            args,
            timeout=180,
        )

    @staticmethod
    def _start_file_index() -> tuple[str, bool]:
        script_path = _OMEGA_SCRIPTS / "nanobot_file_index.py"
        if not script_path.exists():
            return f"Script introuvable: {script_path}", False
        try:
            subprocess.Popen(
                [
                    sys.executable,
                    str(script_path),
                    "index",
                    "--max-seconds",
                    "900",
                    "--max-files",
                    "120000",
                ],
                cwd=str(_OMEGA_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
                close_fds=True,
            )
            return (
                "Indexation locale lancee en arriere-plan. "
                "Je mets a jour C:/AI/nanobot-omega/workspace/memory/nanobot_file_index.db.",
                True,
            )
        except Exception as exc:
            return f"Erreur lancement index local: {exc}", False

    @staticmethod
    def _file_index_status_summary() -> tuple[str, bool]:
        output, ok = GeminiOrchestratorProvider._run_omega_python(
            "nanobot_file_index.py",
            ["status"],
            timeout=30,
        )
        if not ok:
            return output, False
        try:
            payload = json.loads(output)
            return (
                "Index local: "
                f"{payload.get('file_count', 0)} fichier(s), "
                f"etat={payload.get('state', 'inconnu')}, "
                f"derniere fin={payload.get('finished_at', 'jamais')}.",
                True,
            )
        except Exception:
            return output, True

    @staticmethod
    def _extract_file_search_query(raw_text: str) -> str:
        query = raw_text.strip()
        patterns = (
            r"(?is)^\s*(?:cherche|recherche|trouve|retrouve)\s+(?:moi\s+)?(?:le\s+|la\s+|les\s+)?(?:fichier|fichiers|dossier|dossiers|document|documents)?\s*",
            r"(?is)^\s*(?:ou est|où est|localise)\s+(?:le\s+|la\s+|les\s+)?(?:fichier|dossier|document)?\s*",
        )
        for pattern in patterns:
            query = re.sub(pattern, "", query).strip(" .:-")
        return query or raw_text.strip()

    @staticmethod
    def _search_file_index(raw_text: str) -> tuple[str, bool]:
        query = GeminiOrchestratorProvider._extract_file_search_query(raw_text)
        if len(query) < 2:
            return "Dis-moi quoi chercher dans l'index local.", False
        return GeminiOrchestratorProvider._run_omega_python(
            "nanobot_file_index.py",
            ["search", query, "--limit", "12"],
            timeout=60,
        )

    @staticmethod
    def _start_dashboard() -> tuple[str, bool]:
        script_path = _OMEGA_SCRIPTS / "Start-NanobotDashboard.ps1"
        if not script_path.exists():
            return f"Script introuvable: {script_path}", False
        try:
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                ],
                cwd=str(_OMEGA_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
                close_fds=True,
            )
            return f"Dashboard Nanobot lance: {_DASHBOARD_URL}", True
        except Exception as exc:
            return f"Erreur lancement dashboard: {exc}", False

    @staticmethod
    def _looks_like_google_workspace_prompt(raw_text: str) -> bool:
        """Detection legere avant d'importer les dependances Google."""
        text = (raw_text or "").lower()
        service_words = (
            "gmail",
            "mail",
            "email",
            "courriel",
            "agenda",
            "calendrier",
            "calendar",
            "google drive",
            "drive",
            "google docs",
            "docs",
            "google sheets",
            "sheets",
            "sheet",
            "tableur",
            "google tasks",
            "tasks",
            "tache",
            "taches",
            "contact",
            "contacts",
            "google keep",
            "keep",
        )
        return any(word in text for word in service_words)

    @staticmethod
    def _google_workspace_summary(raw_text: str) -> tuple[str, bool] | None:
        """Court-circuit local: Google Workspace repond en texte, pas en JSON."""
        if not GeminiOrchestratorProvider._looks_like_google_workspace_prompt(raw_text):
            return None

        google_tools_path = _OMEGA_ROOT / "tools" / "google_tools.py"
        if not google_tools_path.exists():
            return None
        try:
            import importlib.util

            if str(_OMEGA_ROOT) not in sys.path:
                sys.path.insert(0, str(_OMEGA_ROOT))
            spec = importlib.util.spec_from_file_location(
                "omega_google_tools_runtime",
                google_tools_path,
            )
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if not module.is_google_prompt(raw_text):
                return None
            result = module.handle_google_prompt(raw_text)
            text = result.get("text") or result.get("error") or "Reponse Google vide."
            return str(text), bool(result.get("ok"))
        except Exception as exc:
            return f"Erreur Google locale: {exc}", False

    @staticmethod
    def _format_tool_health(payload: dict[str, Any]) -> str:
        tools = payload.get("registered_tools") or []
        ocr = payload.get("ocr") or {}
        vision = payload.get("vision") or {}
        browser = payload.get("browser") or {}
        desktop = payload.get("desktop") or {}
        google = payload.get("google") or {}
        capabilities = payload.get("capabilities") or {}
        external_services = capabilities.get("external_services") or {}
        lines = ["Diagnostic outils Nanobot:"]
        if tools:
            lines.append("- Outils charges: " + ", ".join(str(t) for t in tools))
        if capabilities:
            skills = (capabilities.get("skills") or {})
            bootstrap = capabilities.get("bootstrap_files") or []
            config = capabilities.get("config") or {}
            existing_bootstrap = [row.get("name") for row in bootstrap if row.get("exists")]
            if skills:
                lines.append(f"- Skills connus: {skills.get('count', 0)}")
            if existing_bootstrap:
                lines.append("- Notes chargeables: " + ", ".join(str(name) for name in existing_bootstrap[:8]))
            mcp_servers = config.get("mcp_servers_configured") or []
            lines.append(
                "- MCP: "
                + (", ".join(str(name) for name in mcp_servers) if mcp_servers else "aucun serveur configure")
            )
            google_mcp = external_services.get("google_workspace_mcp") or {}
            notion_mcp = external_services.get("notion_mcp") or {}
            if google_mcp:
                lines.append(
                    "- Google MCP: "
                    + (
                        f"OK ({google_mcp.get('account_count', 0)} compte)"
                        if google_mcp.get("credentials_exists") and google_mcp.get("accounts_config_exists")
                        else "a authentifier"
                    )
                )
            if notion_mcp:
                lines.append("- Notion MCP: " + ("OK" if notion_mcp.get("token_configured") else "token absent"))
        lines.append(
            "- OCR: "
            + ("OK Windows natif" if ocr.get("windows_native_available") else "a verifier")
            + f" (script: {'OK' if ocr.get('script_exists') else 'manquant'})"
        )
        lines.append(
            "- Vision Gemini: "
            + ("OK" if vision.get("vision_tools_exists") and vision.get("httpx_installed") else "a verifier")
            + (" (cle API OK)" if vision.get("api_key_configured") else " (cle API absente)")
        )
        lines.append(
            "- Navigateur Chrome CDP: "
            + ("OK" if browser.get("ok") else "a relancer")
        )
        lines.append(
            "- Bureau Windows: "
            + ("OK" if desktop.get("powershell_ok") and desktop.get("pc_master_exists") else "a verifier")
        )
        lines.append(
            "- Google local: "
            + ("OK" if google.get("google_tools_exists") and google.get("token_exists") else "a verifier")
        )
        recent = payload.get("recent_errors") or []
        lines.append(f"- Erreurs recentes outil: {len(recent)}")
        return "\n".join(lines)

    @staticmethod
    def _clip_text(value: str, limit: int = 1800) -> str:
        value = (value or "").strip()
        if len(value) <= limit:
            return value
        return value[:limit].rstrip() + "\n...[tronque]"

    @staticmethod
    def _extract_telegram_image_paths(raw_text: str) -> list[Path]:
        paths: list[Path] = []
        for match in re.findall(r"\[image:\s*([^\]\r\n]+)\]", raw_text or "", flags=re.IGNORECASE):
            candidate = Path(match.strip().strip("\"'"))
            if candidate.exists() and candidate.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
                paths.append(candidate)
        return paths

    @staticmethod
    def _ocr_image_paths(paths: list[Path]) -> tuple[str, bool]:
        if not paths:
            return "Je ne trouve pas le fichier image a analyser.", False

        if str(_FIRE_ROOT) not in sys.path:
            sys.path.insert(0, str(_FIRE_ROOT))
        try:
            from tools.vision_tools import analyze_image
        except Exception as exc:
            return f"Outil Vision introuvable ou invalide: {exc}", False

        lines = []
        ok = True
        for index, image_path in enumerate(paths[:4], start=1):
            try:
                result = analyze_image(
                    image_path,
                    question="Analyse l'image pour Nanobot: decris ce que tu vois et lis le texte ou le manuscrit visible.",
                    mode="auto",
                    timeout=90,
                )
                text = GeminiOrchestratorProvider._clip_text(result.get("text", ""), 2600)
                if result.get("ok") and text:
                    mode_label = "Gemini Vision" if result.get("vision_used") else "OCR local"
                    lines.append(f"Image {index}: analyse OK via {mode_label}.\n{text}")
                else:
                    ok = False
                    lines.append(f"Image {index}: analyse impossible: {result.get('error') or 'reponse vide'}")
            except Exception as exc:
                ok = False
                lines.append(f"Image {index}: erreur Vision: {exc}")

        if len(paths) > 4:
            lines.append(f"{len(paths) - 4} image(s) supplementaire(s) ignoree(s) pour garder la reponse courte.")
        return "\n\n".join(lines), ok

    @classmethod
    def _recent_image_paths_from_messages(cls, messages: list[dict[str, Any]]) -> list[Path]:
        seen: set[str] = set()
        paths: list[Path] = []
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            content = cls._flatten_message_text(msg.get("content"))
            for path in cls._extract_telegram_image_paths(content):
                key = str(path).lower()
                if key in seen:
                    continue
                seen.add(key)
                paths.append(path)
                if len(paths) >= 4:
                    return paths
        return paths

    @staticmethod
    def _tooling_shortcut_summary(raw_text: str) -> tuple[str, bool] | None:
        """Fast paths for local OCR/browser/desktop/diagnostic requests."""
        text = GeminiOrchestratorProvider._normalize_text(raw_text)
        plain = unicodedata.normalize("NFD", text)
        plain = "".join(ch for ch in plain if unicodedata.category(ch) != "Mn")
        match_text = f"{text} {plain}"
        try:
            if any(
                phrase in match_text
                for phrase in (
                    "etat complet",
                    "status complet",
                    "sante complete",
                    "bilan complet",
                )
            ):
                read_only = any(
                    phrase in match_text
                    for phrase in (
                        "sans reparer",
                        "sans reparation",
                        "lecture seule",
                        "read only",
                    )
                )
                return GeminiOrchestratorProvider._full_status_summary(repair=not read_only)

            if any(
                phrase in match_text
                for phrase in (
                    "diagnostic complet",
                    "diagnostique complet",
                    "diagnostic seul",
                    "etat complet diagnostic",
                )
            ):
                return GeminiOrchestratorProvider._full_status_summary(repair=False)

            if any(
                phrase in match_text
                for phrase in (
                    "lance le dashboard",
                    "ouvre le dashboard",
                    "dashboard nanobot",
                    "tableau de bord",
                )
            ):
                return GeminiOrchestratorProvider._start_dashboard()

            if any(
                phrase in match_text
                for phrase in (
                    "indexe fichiers",
                    "indexe les fichiers",
                    "mets a jour index",
                    "met a jour index",
                    "reindexe",
                    "index local",
                )
            ) and any(word in match_text for word in ("indexe", "index", "reindexe", "statut", "etat", "tat")):
                if any(word in match_text for word in ("statut", "status", "etat", "tat")):
                    return GeminiOrchestratorProvider._file_index_status_summary()
                return GeminiOrchestratorProvider._start_file_index()

            if (
                any(word in match_text for word in ("cherche", "recherche", "trouve", "retrouve", "localise"))
                and any(word in match_text for word in ("fichier", "fichiers", "dossier", "dossiers", "document", "documents"))
            ):
                return GeminiOrchestratorProvider._search_file_index(raw_text)

            image_paths = GeminiOrchestratorProvider._extract_telegram_image_paths(raw_text)
            if image_paths:
                return GeminiOrchestratorProvider._ocr_image_paths(image_paths)

            if any(
                phrase in match_text
                for phrase in (
                    "diagnostique tes outils",
                    "diagnostic outils",
                    "diagnostic des outils",
                    "etat des outils",
                    "verifie tes outils",
                    "verifie les outils",
                    "diagnostique tes capacites",
                    "diagnostic capacites",
                    "inventaire des capacites",
                    "liste tes capacites",
                    "tool diagnostics",
                )
            ) or (
                ("outils" in match_text or "capacites" in match_text or "capabilities" in match_text)
                and any(word in match_text for word in ("diagnostic", "diagnostique", "verifie", "rifie", "etat", "tat"))
            ):
                from nanobot.agent.tools.diagnostics import ToolDiagnosticsTool

                tool = ToolDiagnosticsTool(
                    tool_names_provider=lambda: [
                        "ocr",
                        "vision_analyze_image",
                        "browser_automation",
                        "desktop_automation",
                        "tool_diagnostics",
                        "mcp_filesystem_read_file",
                        "mcp_filesystem_list_directory",
                        "mcp_memory_read_graph",
                        "mcp_sequential_thinking_sequentialthinking",
                        "mcp_google_workspace_listAccounts",
                        "mcp_google_workspace_listGmailMessages",
                        "mcp_google_workspace_listCalendarEvents",
                        "mcp_google_workspace_searchDrive",
                        "mcp_notion_API-post-search",
                    ]
                )
                payload = json.loads(tool._execute_sync(action="health", target="all", limit=5))
                return GeminiOrchestratorProvider._format_tool_health(payload), True

            if (
                any(word in match_text for word in ("ocr", "lis", "analyse", "capture"))
                and any(word in match_text for word in ("ecran", "cran", "screen", "screenshot"))
            ):
                from nanobot.agent.tools.desktop_automation import DesktopAutomationTool

                result = DesktopAutomationTool()._execute_sync(action="ocr_screen", timeout=90)
                if result.startswith("Error"):
                    return result, False
                payload = json.loads(result)
                detected = GeminiOrchestratorProvider._clip_text(payload.get("text", ""), 1800)
                if not detected:
                    detected = "Aucun texte detecte."
                return f"OCR ecran OK via {payload.get('engine', 'ocr')}.\n\nTexte detecte:\n{detected}", True

            if ("capture" in match_text or "screenshot" in match_text) and any(word in match_text for word in ("ecran", "cran")):
                from nanobot.agent.tools.desktop_automation import DesktopAutomationTool

                result = DesktopAutomationTool()._execute_sync(action="screenshot", timeout=30)
                if result.startswith("Error"):
                    return result, False
                payload = json.loads(result)
                return f"Capture d'ecran enregistree: {payload.get('path')}", True

            open_words = (
                "ouvre",
                "ouvrir",
                "lance",
                "ouvrir une page",
                "va sur",
                "affiche",
                "mets",
            )
            if "youtube" in match_text and any(word in match_text for word in open_words):
                from nanobot.agent.tools.browser_automation import BrowserAutomationTool

                wants_video = any(word in match_text for word in ("video", "vidéo"))
                search_query = ""
                if "soncas" in match_text:
                    search_query = "SONCAS methode commerciale francais"
                elif wants_video and any(word in match_text for word in ("francais", "français", "francaise", "française")):
                    search_query = "video en francais"
                url = "https://www.youtube.com/"
                if search_query:
                    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(search_query)

                result = BrowserAutomationTool()._execute_sync(action="open", url=url, timeout=30)
                if result.startswith("Error"):
                    return result, False
                payload = json.loads(result)
                tab = payload.get("tab") or {}
                return (
                    "YouTube est ouvert dans Chrome Agent"
                    + (f" sur la recherche: {search_query}" if search_query else "")
                    + f".\nURL: {tab.get('url') or url}"
                ), True

            if (
                ("liste" in text or "affiche" in text or "montre" in text)
                and any(word in match_text for word in ("fenetre", "fenetres", "windows", "fen"))
            ):
                from nanobot.agent.tools.desktop_automation import DesktopAutomationTool

                result = DesktopAutomationTool()._execute_sync(action="windows")
                if result.startswith("Error"):
                    return result, False
                payload = json.loads(result)
                windows = payload.get("windows") or []
                if not windows:
                    return "Aucune fenetre visible detectee.", True
                lines = ["Fenetres ouvertes:"]
                for row in windows[:12]:
                    title = str(row.get("MainWindowTitle") or "").strip()
                    proc = str(row.get("ProcessName") or "").strip()
                    pid = row.get("Id", "")
                    lines.append(f"- [{pid}] {proc}: {title}")
                if len(windows) > 12:
                    lines.append(f"... +{len(windows) - 12} autres")
                return "\n".join(lines), True

            if "fenetre active" in match_text or "application active" in match_text:
                from nanobot.agent.tools.desktop_automation import DesktopAutomationTool

                result = DesktopAutomationTool()._execute_sync(action="active")
                if result.startswith("Error"):
                    return result, False
                active = (json.loads(result).get("active") or {})
                return (
                    "Fenetre active: "
                    f"{active.get('ProcessName', 'inconnue')} - {active.get('Title', '')}"
                ), True

            if any(phrase in match_text for phrase in ("info systeme", "etat pc", "sante pc", "system info")) or (
                any(word in match_text for word in ("systeme", "system", "syst"))
                and any(word in match_text for word in ("etat", "tat", "info", "sante"))
            ):
                from nanobot.agent.tools.desktop_automation import DesktopAutomationTool

                result = DesktopAutomationTool()._execute_sync(action="system_info")
                if result.startswith("Error"):
                    return result, False
                system = (json.loads(result).get("system") or {})
                return (
                    "Etat PC: "
                    f"CPU {system.get('CPU_Percent')}%, "
                    f"RAM libre {system.get('RAM_Free_GB')} Go/{system.get('RAM_Total_GB')} Go, "
                    f"disque C libre {system.get('Disk_Free_GB')} Go/{system.get('Disk_Total_GB')} Go."
                ), True

            browser_words = ("chrome agent", "navigateur", "page chrome", "browser")
            if any(word in match_text for word in browser_words) and any(
                word in match_text for word in ("lis", "analyse", "structure", "snapshot", "etat")
            ):
                from nanobot.agent.tools.browser_automation import BrowserAutomationTool

                result = BrowserAutomationTool()._execute_sync(action="snapshot", max_text_chars=1600)
                if result.startswith("Error"):
                    return result, False
                payload = json.loads(result)
                body = GeminiOrchestratorProvider._clip_text(payload.get("text", ""), 1200)
                return (
                    f"Page Chrome Agent: {payload.get('title', '')}\n"
                    f"URL: {payload.get('url', '')}\n"
                    f"Boutons visibles: {len(payload.get('buttons') or [])}, "
                    f"liens: {len(payload.get('links') or [])}, champs: {len(payload.get('inputs') or [])}.\n\n"
                    f"Texte visible:\n{body}"
                ), True
        except Exception as exc:
            return f"Erreur outil local: {exc}", False
        return None

    def _fast_path_response(
        self,
        messages: list[dict[str, Any]],
        model: str,
    ) -> LLMResponse | None:
        raw_text = self._last_user_text(messages)
        if not raw_text:
            return None

        text = self._normalize_text(raw_text)
        plain = unicodedata.normalize("NFD", text)
        plain = "".join(ch for ch in plain if unicodedata.category(ch) != "Mn")
        match_text = plain.replace("-", " ")
        now = dt.datetime.now()

        google_result = self._google_workspace_summary(raw_text)
        if google_result is not None:
            content, ok = google_result
            return LLMResponse(
                content=content,
                finish_reason="stop" if ok else "error",
            )

        tooling_result = self._tooling_shortcut_summary(raw_text)
        if tooling_result is not None:
            content, ok = tooling_result
            return LLMResponse(
                content=content,
                finish_reason="stop" if ok else "error",
            )

        if (
            any(word in text for word in ("image", "photo", "screenshot"))
            and any(word in text for word in ("analyse", "analyser", "lis", "lire", "ocr", "regarde", "derniere"))
        ):
            image_paths = self._recent_image_paths_from_messages(messages)
            if image_paths:
                content, ok = self._ocr_image_paths(image_paths)
                return LLMResponse(
                    content=content,
                    finish_reason="stop" if ok else "error",
                )

        greeting_patterns = (
            "bonjour",
            "bonsoir",
            "salut",
            "hello",
            "coucou",
        )
        if (
            text in greeting_patterns
            or "bonjour" in text
            or "bonsoir" in text
            or text.startswith("salut ")
            or text.startswith("hello ")
            or text.startswith("coucou ")
        ):
            return LLMResponse(
                content="Bonjour, je suis prêt. Dis-moi ce que tu veux faire et je m'en occupe.",
                finish_reason="stop",
            )

        if "heure" in text and ("quelle" in text or "il est" in text):
            return LLMResponse(
                content=f"Il est {now.strftime('%H:%M')} ({now.strftime('%d/%m/%Y')}).",
                finish_reason="stop",
            )

        if "date" in text or "quel jour" in text:
            return LLMResponse(
                content=now.strftime("Nous sommes le %d/%m/%Y."),
                finish_reason="stop",
            )

        if "quel model" in text or "quel modele" in text or "qui es tu" in text:
            return LLMResponse(
                content=f"Je fonctionne actuellement avec le modele {model} via le profil omega.",
                finish_reason="stop",
            )

        if any(
            phrase in text
            for phrase in (
                "etat complet",
                "etat omega",
                "status omega",
                "sante omega",
                "etat telegram",
                "etat rotation",
                "etat limiteur",
                "limiteur gemini",
                "cooldown global",
                "etat du systeme omega",
            )
        ):
            return LLMResponse(
                content=self._omega_status_summary(),
                finish_reason="stop",
            )

        browser_reference_phrases = (
            "ton navigateur",
            "navigateur de reference",
            "navigateur commun",
            "navigateur partage",
            "navigateur nanobot",
        )
        if any(phrase in text for phrase in browser_reference_phrases):
            if any(word in text for word in ("ou est", "c est quoi", "quel est", "ou se trouve", "situe")):
                return LLMResponse(
                    content=self._shared_browser_summary(),
                    finish_reason="stop",
                )

        if any(
            phrase in match_text
            for phrase in (
                "de quoi es tu capable",
                "que peux tu faire",
                "qu est ce que tu peux faire",
                "liste tes capacites",
                "tes capacites",
            )
        ):
            return LLMResponse(
                content=(
                    "Je peux repondre en francais et agir directement via mes outils: fichiers, shell, web, navigateur Chrome "
                    "partage, bureau Windows, OCR, Gemini Vision, Google Workspace local et MCP (Gmail, Agenda, Drive, Tasks, "
                    "Docs/Sheets quand les autorisations sont presentes), Notion via MCP, documents, memoire, "
                    "scraping web robuste (HTTP, rendu JS Playwright, extraction de tables/listings/texte, exports JSON/Markdown/.xlsx), "
                    "taches planifiees, diagnostics et autres outils MCP s'ils sont configures. "
                    "Je connais aussi mes fichiers de consignes et mon index de skills: "
                    "si un chemin echoue, je dois diagnostiquer puis essayer une autre route avant de dire non."
                ),
                finish_reason="stop",
            )

        if any(word in text for word in ("telecharge", "telecharger", "installe", "installer", "install", "download")):
            software_response = self._handle_software_request(raw_text, text, ensure_mode=True)
            if software_response is not None:
                return software_response

        obsidian_response = self._handle_obsidian_request(raw_text, text)
        if obsidian_response is not None:
            return obsidian_response

        scraping_response = self._handle_scraping_request(raw_text, text)
        if scraping_response is not None:
            return scraping_response

        app_actions: list[tuple[str, str, tuple[str, ...], str | None]] = [
            ("chrome", "Chrome", ("chrome", "chrome.exe"), "Chrome"),
            ("google chrome", "Google Chrome", ("chrome", "chrome.exe"), "Chrome"),
            ("opera", "Opera", ("opera", "launcher.exe", "opera.exe"), "Opera"),
            ("telegram", "Telegram", ("telegram", "telegram.exe"), "Telegram"),
        ]
        action_verbs = ("ouvre", "ouvrir", "lance", "lancer", "demarre", "démarre")
        if any(verb in text for verb in action_verbs):
            if (
                any(phrase in text for phrase in browser_reference_phrases)
                and self._is_short_direct_browser_command(raw_text)
            ):
                app_path = self._find_windows_app("chrome", "chrome.exe")
                if not app_path:
                    return LLMResponse(
                        content="Je ne trouve pas Chrome sur ce PC.",
                        finish_reason="stop",
                    )
                try:
                    self._launch_shared_chrome(app_path)
                except Exception as exc:
                    return LLMResponse(
                        content=f"Je n'ai pas réussi à ouvrir le navigateur de reference: {exc}",
                        finish_reason="error",
                    )
                return LLMResponse(
                    content=(
                        "C'est fait : j'ai ouvert le navigateur de reference Nanobot "
                        f"avec le profil partage {_SHARED_CHROME_PROFILE}."
                    ),
                    finish_reason="stop",
                )
            for trigger, label, candidates, start_pattern in app_actions:
                if trigger in text:
                    app_path = self._find_windows_app(*candidates)
                    try:
                        if app_path:
                            if "chrome" in trigger:
                                self._launch_shared_chrome(app_path)
                            else:
                                subprocess.Popen([app_path], close_fds=True)
                        else:
                            app_id = self._find_start_app_id(start_pattern or label)
                            if not app_id:
                                return LLMResponse(
                                    content=f"Je ne trouve pas {label} sur ce PC.",
                                    finish_reason="stop",
                                )
                            subprocess.Popen(
                                ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
                                close_fds=True,
                            )
                    except Exception as exc:
                        return LLMResponse(
                            content=f"Je n'ai pas réussi à ouvrir {label}: {exc}",
                            finish_reason="error",
                        )
                    return LLMResponse(
                        content=f"C'est fait : j'ai ouvert {label}.",
                        finish_reason="stop",
                    )

            software_response = self._handle_software_request(raw_text, text, ensure_mode=False)
            if software_response is not None:
                return software_response

        return None

    # ------------------------------------------------------------------
    # Message formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_messages_for_api(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert Nanobot messages to OpenAI-compatible format for Gemini."""
        formatted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content")

            # Handle content arrays (multimodal)
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "image_url":
                            text_parts.append("[image]")
                    elif isinstance(block, str):
                        text_parts.append(block)
                content = "\n".join(text_parts) if text_parts else ""

            if content is None:
                content = ""

            # Reconstruct tool results as user messages
            if role == "tool":
                tool_call_id = msg.get("tool_call_id", "unknown")
                name = msg.get("name", "tool")
                formatted.append({
                    "role": "user",
                    "content": f"[Tool result for {name} (id={tool_call_id})]:\n{content}",
                })
                continue

            # Reconstruct assistant tool_calls
            if role == "assistant" and msg.get("tool_calls"):
                tool_calls_text = []
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict):
                        tool_calls_text.append("[Internal tool call executed]")
                if content:
                    formatted.append({"role": "assistant", "content": content})
                if tool_calls_text:
                    formatted.append({
                        "role": "assistant",
                        "content": "\n".join(tool_calls_text),
                    })
                continue

            formatted.append({"role": role, "content": content})

        return formatted

    @staticmethod
    def _build_tools_system_prompt(tools: list[dict[str, Any]] | None) -> str:
        """Build a system prompt section describing available tools."""
        if not tools:
            return ""

        def _type_label(schema: dict[str, Any]) -> str:
            raw = schema.get("type", "any")
            if isinstance(raw, list):
                return "|".join(str(part) for part in raw)
            return str(raw)

        lines = [
            "\n\n## Available Tools\n",
            "IMPORTANT:",
            "- Every tool listed below is available right now in the current environment.",
            "- Never claim that a listed tool is unavailable, missing, or unsupported.",
            "- If the user explicitly asks to use a listed tool, call it instead of refusing.",
            "- When a request requires a tool, do not narrate a plan and do not produce a final answer. Output only the JSON tool_calls block.",
            "- Before refusing, map the request to a capability family: files, shell, web, browser, desktop, OCR, Vision, Google, documents, memory, cron, diagnostics, or MCP.",
            "- If the right route is unclear, call `tool_diagnostics` with target='capabilities' or inspect the workspace skill index/bootstrap notes.",
            "- If one route fails, try a second route when it is reasonable: browser automation, desktop automation, shell, web fetch/search, or diagnostics.",
            "- If the user asks to understand, describe, or read handwriting in an image, prefer `vision_analyze_image`.",
            "- If the user only asks to read printed text from an image, screenshot, or screen region, `ocr` is acceptable.",
            "- If the user asks to use a web page in Chrome, prefer `browser_automation` before raw mouse clicks.",
            "- If the user says not to open a new site/page or to use the current/open tab only, call `browser_automation` with `auto_launch`: false and a `tab_match` when possible.",
            "- If that current-tab `browser_automation` call reports Chrome CDP is unavailable, do not launch a browser when forbidden; use `desktop_automation` screenshot/OCR or return the precise CDP access error.",
            "- If the user asks to open YouTube or another site, call `browser_automation` with action='open'.",
            "- If the user asks to interact with a native Windows app, prefer `desktop_automation`.",
            "- If a tool fails, inspect the error, call `tool_diagnostics` when useful, and retry with a changed approach.",
            "- If `exec` is listed, use `exec` for shell commands. `run_shell_command` is only an alias and should not be described as missing.",
            "- If Notion MCP tools are listed, do not ask the user for a Notion API token; the token is already configured for the MCP server. Use `mcp_notion_API-get-self` first, then the relevant Notion tool.",
            "- If a tool result says Chrome CDP is unavailable and the user forbids opening or changing pages, stop and report that precise CDP error instead of claiming tools are missing.",
            "",
            "You can call tools by responding with a JSON block in this exact format:",
            '```json\n{"tool_calls": [{"name": "tool_name", "arguments": {"arg": "value"}}]}\n```',
            "No prose before or after the JSON block when calling tools.",
            "Forbidden when a tool is needed: do not write 'Je vais...', 'Je tente...', 'Pour lire X je vais utiliser Y', or any intermediate narration.",
            "Valid outputs are only: (1) an immediate JSON tool_calls block, or (2) a final direct answer when no tool is needed.",
            "",
            "Example for OCR on an image:",
            '```json\n{"tool_calls": [{"name": "ocr", "arguments": {"mode": "image", "image_path": "C:/path/to/image.png"}}]}\n```',
            "Example for reading the current browser tab:",
            '```json\n{"tool_calls": [{"name": "browser_automation", "arguments": {"action": "snapshot", "max_text_chars": 2000}}]}\n```',
            "Example for reading an already-open Notion tab without opening anything:",
            '```json\n{"tool_calls": [{"name": "browser_automation", "arguments": {"action": "snapshot", "tab_match": "notion", "auto_launch": false, "max_text_chars": 4000}}]}\n```',
            "Example for diagnosing tools:",
            '```json\n{"tool_calls": [{"name": "tool_diagnostics", "arguments": {"action": "health", "target": "tools"}}]}\n```',
            "Example for Gemini Vision on an image:",
            '```json\n{"tool_calls": [{"name": "vision_analyze_image", "arguments": {"image_path": "C:/path/to/image.png", "mode": "auto"}}]}\n```',
            "\nAvailable tools:\n",
        ]

        for tool in tools:
            fn = tool.get("function", tool)
            name = fn.get("name", "unknown")
            desc = fn.get("description", "")
            params = fn.get("parameters", {})
            props = params.get("properties", {})
            required = params.get("required", [])

            lines.append(f"### {name}")
            if desc:
                lines.append(f"  {desc}")

            if props:
                lines.append("  Parameters:")
                for pname, pinfo in props.items():
                    ptype = _type_label(pinfo)
                    pdesc = pinfo.get("description", "")
                    req = " (required)" if pname in required else ""
                    lines.append(f"    - {pname}: {ptype}{req} — {pdesc}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _parse_tool_calls_from_content(content: str) -> list[ToolCallRequest]:
        """Extract tool calls from LLM response content."""
        tool_calls = []

        # Try to find JSON blocks with tool_calls
        # Pattern 1: ```json { "tool_calls": [...] } ```
        json_blocks = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)

        # Pattern 2: bare JSON at end of message
        if not json_blocks:
            # Look for JSON object containing tool_calls
            matches = re.findall(r'(\{"tool_calls"\s*:\s*\[.*?\]\s*\})', content, re.DOTALL)
            json_blocks.extend(matches)

        for block in json_blocks:
            try:
                parsed = json_repair.loads(block)
                if isinstance(parsed, dict) and "tool_calls" in parsed:
                    for tc in parsed["tool_calls"]:
                        if isinstance(tc, dict) and "name" in tc:
                            tool_calls.append(ToolCallRequest(
                                id=_short_id(),
                                name=tc["name"],
                                arguments=tc.get("arguments", {}),
                            ))
            except Exception:
                continue

        if tool_calls:
            return tool_calls

        # Second pass: recover common prose hallucinations such as
        # "mcp_filesystem_read_text_file(path=...)" or
        # "`mcp_filesystem_read_text_file` avec path=...".
        def _clean_value(value: str) -> str:
            value = value.strip().strip(",;")
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            return value.strip("` ")

        def _parse_args(arg_text: str) -> dict[str, Any]:
            args: dict[str, Any] = {}
            for part in re.split(r"\s*,\s*|\s*;\s*", arg_text.strip()):
                if not part:
                    continue
                match = re.match(r"([A-Za-z_][A-Za-z0-9_-]*)\s*(?:=|:)\s*(.+)", part, re.DOTALL)
                if not match:
                    continue
                key, raw_value = match.groups()
                value = _clean_value(raw_value)
                if value.lower() in {"true", "false"}:
                    args[key] = value.lower() == "true"
                else:
                    try:
                        args[key] = json.loads(value)
                    except Exception:
                        args[key] = value
            return args

        seen: set[tuple[str, str]] = set()

        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_-]*(?:_[A-Za-z0-9_-]+)+)\s*\(([^)]*)\)", content):
            name, arg_text = match.groups()
            if not (name.startswith("mcp_") or name in {
                "exec", "browser_automation", "desktop_automation",
                "tool_diagnostics", "ocr", "vision_analyze_image",
                "web_fetch", "web_search", "read_file", "write_file",
            }):
                continue
            args = _parse_args(arg_text)
            key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
            if key in seen:
                continue
            seen.add(key)
            tool_calls.append(ToolCallRequest(id=_short_id(), name=name, arguments=args))

        if tool_calls:
            return tool_calls

        prose_tool = re.search(
            r"`?((?:mcp_[A-Za-z0-9_-]+)|browser_automation|desktop_automation|tool_diagnostics|ocr|vision_analyze_image|exec|read_file|web_fetch|web_search)`?",
            content,
        )
        if prose_tool:
            name = prose_tool.group(1)
            args: dict[str, Any] = {}
            kv_matches = re.findall(
                r"\b([A-Za-z_][A-Za-z0-9_-]*)\s*(?:=|:)\s*(`[^`]+`|\"[^\"]+\"|'[^']+'|[^\n,;]+)",
                content,
            )
            for key, raw_value in kv_matches:
                if key.lower() in {"outil", "tool", "name"}:
                    continue
                args[key] = _clean_value(raw_value)

            if not args:
                path_match = re.search(r"([A-Za-z]:[\\/][^\n`\"']+)", content)
                if path_match:
                    path_value = _clean_value(path_match.group(1))
                    if name.startswith("mcp_filesystem_"):
                        args["path"] = path_value
                    elif name == "read_file":
                        args["path"] = path_value

            tool_calls.append(ToolCallRequest(id=_short_id(), name=name, arguments=args))

        return tool_calls

    # ------------------------------------------------------------------
    # Chat completion (non-streaming)
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Send a chat completion via the Gemini orchestrator."""
        effective_model = model or self.default_model
        fast_path = self._fast_path_response(messages, effective_model)
        if fast_path is not None:
            return fast_path

        # Build messages
        formatted = self._format_messages_for_api(
            self._sanitize_empty_content(messages)
        )

        # ------------------------------------------------------------
        # Bascule Ollama local si NANOBOT_BACKEND=ollama (defaut).
        # Court-circuit le cluster Gemini pour eliminer le cooldown 429.
        # ------------------------------------------------------------
        if _BACKEND == "ollama":
            ollama_messages: list[dict[str, Any]] = []
            system_prompt = ""
            msgs_for_ollama = formatted
            if msgs_for_ollama and msgs_for_ollama[0].get("role") == "system":
                system_prompt = msgs_for_ollama[0]["content"]
                msgs_for_ollama = msgs_for_ollama[1:]
            system_prompt = self._augment_system_prompt(system_prompt)
            if tools:
                system_prompt += self._build_tools_system_prompt(tools)
            if self._is_telegram_context(messages):
                system_prompt += (
                    "\n\n## Channel Guidance\n"
                    "- Reply in French.\n"
                    "- 1 to 4 short sentences unless asked for detail.\n"
                    "- Prefer direct answers.\n"
                    "- Use tool calls internally when needed, but never show JSON, tool names, MCP names, arguments, or hidden reasoning to the user.\n"
                    "- After tools finish, answer only with the concrete result, useful file paths, verification, and real blockers.\n"
                )
            if system_prompt:
                ollama_messages.append({"role": "system", "content": system_prompt})
            for msg in msgs_for_ollama:
                role = msg.get("role", "user")
                if role not in ("user", "assistant", "system"):
                    role = "user"
                ollama_messages.append({"role": role, "content": msg.get("content", "")})

            result = await asyncio.to_thread(
                _ollama_chat, ollama_messages,
                temperature=temperature, max_tokens=max_tokens,
            )
            if not result.get("ok"):
                # Fallback cloud Gemini uniquement si explicitement autorise
                if os.environ.get("NANOBOT_FALLBACK", "1").strip() in ("0", "false", "no"):
                    return LLMResponse(
                        content=f"Ollama local indisponible: {result.get('error')}",
                        finish_reason="error",
                    )
                # sinon on laisse tomber vers le code Gemini historique ci-dessous
            else:
                content = self._clean_output_text(result["content"]) or ""
                parsed_tools = (
                    self._parse_tool_calls_from_content(content) if tools else []
                )
                if parsed_tools:
                    content = re.sub(
                        r'```(?:json)?\s*\{"tool_calls".*?\}\s*```',
                        '', content, flags=re.DOTALL,
                    ).strip()
                    content = re.sub(
                        r'\{"tool_calls"\s*:\s*\[.*?\]\s*\}',
                        '', content, flags=re.DOTALL,
                    ).strip()
                return LLMResponse(
                    content=self._clean_output_text(content or None, strip_tool_plumbing=True),
                    tool_calls=parsed_tools,
                    finish_reason="tool_calls" if parsed_tools else "stop",
                    usage={"total_tokens": 0},
                )

        # Extract system prompt
        system_prompt = ""
        if formatted and formatted[0].get("role") == "system":
            system_prompt = formatted[0]["content"]
            formatted = formatted[1:]
        system_prompt = self._augment_system_prompt(system_prompt)

        # Add tool definitions to system prompt
        if tools:
            system_prompt += self._build_tools_system_prompt(tools)
        if self._is_telegram_context(messages):
            system_prompt += (
                "\n\n## Channel Guidance\n"
                "- The current user is on Telegram mobile.\n"
                "- Reply in French.\n"
                "- Keep replies concise by default: 1 to 4 short sentences unless the user asks for detail.\n"
                "- Prefer direct answers over long preambles.\n"
                "- If a task succeeds, say what happened plainly and stop.\n"
                "- Use tool calls internally when needed, but never show JSON, tool names, MCP names, arguments, or hidden reasoning to the user.\n"
                "- After tools finish, answer only with the concrete result, useful file paths, verification, and real blockers.\n"
            )

        # Build single prompt from conversation
        prompt_parts = []
        for msg in formatted:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")

        prompt = "\n\n".join(prompt_parts)

        # If we have API keys, use OpenAI-compatible format directly
        if self._orchestrator._mode == "api" and self._orchestrator._api_keys:
            return await self._chat_api_direct(
                messages=messages,
                tools=tools,
                model=effective_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
            )

        # Subprocess mode — send as single prompt
        result = await self._orchestrator.execute(
            prompt,
            model=effective_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
        )

        if result.get("error"):
            error_text = result.get("content", "")
            should_local_fallback = (
                os.environ.get("NANOBOT_FALLBACK", "1").strip().lower() not in ("0", "false", "no")
                and any(
                    marker in error_text.lower()
                    for marker in (
                        "global cooldown",
                        "rate_limit_cluster",
                        "quota_exhausted",
                        "too many requests",
                        "no available gemini",
                        "all candidates are cooling",
                        "cooling down",
                        "permission_denied",
                        "does not have permission",
                    )
                )
            )
            if should_local_fallback:
                ollama_messages: list[dict[str, Any]] = []
                ollama_messages.append({
                    "role": "system",
                    "content": (
                        "Tu es Nanobot Omega, agent personnel operationnel d'Amor. "
                        "Gemini est temporairement indisponible: reponds en francais, "
                        "court, utile, sans mentionner les outils internes. Si une action "
                        "necessite un outil non disponible localement, dis clairement le blocage."
                    ),
                })
                for msg in formatted[-8:]:
                    role = msg.get("role", "user")
                    if role not in ("user", "assistant", "system"):
                        role = "user"
                    content = str(msg.get("content", ""))
                    if len(content) > 4000:
                        content = content[-4000:]
                    ollama_messages.append({"role": role, "content": content})
                ollama_result = await asyncio.to_thread(
                    _ollama_chat,
                    ollama_messages,
                    temperature=temperature,
                    max_tokens=min(max_tokens, 512),
                )
                if ollama_result.get("ok"):
                    content = self._clean_output_text(ollama_result["content"]) or ""
                    parsed_tools = (
                        self._parse_tool_calls_from_content(content) if tools else []
                    )
                    if parsed_tools:
                        content = re.sub(
                            r'```(?:json)?\s*\{"tool_calls".*?\}\s*```',
                            '', content, flags=re.DOTALL,
                        ).strip()
                        content = re.sub(
                            r'\{"tool_calls"\s*:\s*\[.*?\]\s*\}',
                            '', content, flags=re.DOTALL,
                        ).strip()
                    return LLMResponse(
                        content=self._clean_output_text(content or None, strip_tool_plumbing=True),
                        tool_calls=parsed_tools,
                        finish_reason="tool_calls" if parsed_tools else "stop",
                        usage={"total_tokens": 0},
                    )
            return LLMResponse(
                content=result["content"],
                finish_reason="error",
            )

        content = self._clean_output_text(result["content"])
        parsed_tools = self._parse_tool_calls_from_content(content) if tools else []

        # Clean tool call JSON from content if tools were parsed
        if parsed_tools:
            import re
            content = re.sub(
                r'```(?:json)?\s*\{"tool_calls".*?\}\s*```',
                '', content, flags=re.DOTALL,
            ).strip()
            content = re.sub(
                r'\{"tool_calls"\s*:\s*\[.*?\]\s*\}',
                '', content, flags=re.DOTALL,
            ).strip()

        return LLMResponse(
            content=self._clean_output_text(content or None, strip_tool_plumbing=True),
            tool_calls=parsed_tools,
            finish_reason="tool_calls" if parsed_tools else "stop",
            usage={"total_tokens": result.get("tokens_used", 0)},
        )

    async def _chat_api_direct(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
        max_tokens: int,
        temperature: float,
        system_prompt: str,
    ) -> LLMResponse:
        """Direct API call with native tool support via OpenAI-compatible endpoint."""
        api_key = self._orchestrator._get_next_api_key()

        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            timeout=self._orchestrator._api_timeout,
        )

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._sanitize_empty_content(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await client.chat.completions.create(**kwargs)

            choice = response.choices[0] if response.choices else None
            if not choice:
                return LLMResponse(content="Error: Empty response", finish_reason="error")

            content = self._clean_output_text(choice.message.content)
            finish_reason = choice.finish_reason or "stop"

            parsed_tools = []
            if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    args = tc.function.arguments
                    if isinstance(args, str):
                        args = json_repair.loads(args)
                    parsed_tools.append(ToolCallRequest(
                        id=_short_id(),
                        name=tc.function.name,
                        arguments=args if isinstance(args, dict) else {},
                    ))
                finish_reason = "tool_calls"

            usage = {}
            if hasattr(response, "usage") and response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens or 0,
                    "completion_tokens": response.usage.completion_tokens or 0,
                    "total_tokens": response.usage.total_tokens or 0,
                }

            return LLMResponse(
                content=self._clean_output_text(content, strip_tool_plumbing=True),
                tool_calls=parsed_tools,
                finish_reason=finish_reason,
                usage=usage,
            )

        except Exception as exc:
            return LLMResponse(
                content=f"Error calling Gemini API: {exc}",
                finish_reason="error",
            )

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        """Stream a chat completion. Falls back to non-streaming for subprocess mode."""

        # Ollama : route par chat() (pas de vrai streaming Ollama ici, mais
        # on emet le texte final en une delta pour garder l'UX Telegram).
        if _BACKEND == "ollama":
            response = await self.chat(
                messages=messages, tools=tools, model=model,
                max_tokens=max_tokens, temperature=temperature,
                reasoning_effort=reasoning_effort, tool_choice=tool_choice,
            )
            if on_content_delta and response.content:
                await on_content_delta(response.content)
            return response

        # In API mode with keys, use real streaming
        if self._orchestrator._mode == "api" and self._orchestrator._api_keys:
            return await self._stream_api(
                messages=messages,
                tools=tools,
                model=model or self.default_model,
                max_tokens=max_tokens,
                temperature=temperature,
                on_content_delta=on_content_delta,
            )

        # Subprocess mode: single response then emit as delta
        response = await self.chat(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
        )
        if on_content_delta and response.content:
            await on_content_delta(response.content)
        return response

    async def _stream_api(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
        max_tokens: int,
        temperature: float,
        on_content_delta: Callable[[str], Awaitable[None]] | None,
    ) -> LLMResponse:
        """Real streaming via OpenAI-compatible Gemini API."""
        api_key = self._orchestrator._get_next_api_key()

        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            timeout=self._orchestrator._api_timeout,
        )

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._sanitize_empty_content(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            stream = await client.chat.completions.create(**kwargs)
            content_parts: list[str] = []
            tc_bufs: dict[int, dict[str, str]] = {}

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    content_parts.append(delta.content)
                    if on_content_delta:
                        await on_content_delta(delta.content)
                if delta and hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = getattr(tc, "index", 0)
                        buf = tc_bufs.setdefault(idx, {"name": "", "arguments": ""})
                        if tc.function:
                            if tc.function.name:
                                buf["name"] = tc.function.name
                            if tc.function.arguments:
                                buf["arguments"] += tc.function.arguments

            parsed_tools = []
            for buf in tc_bufs.values():
                args = json_repair.loads(buf["arguments"]) if buf["arguments"] else {}
                parsed_tools.append(ToolCallRequest(
                    id=_short_id(),
                    name=buf["name"],
                    arguments=args if isinstance(args, dict) else {},
                ))

            content = self._clean_output_text("".join(content_parts) or None)
            return LLMResponse(
                content=self._clean_output_text(content, strip_tool_plumbing=True),
                tool_calls=parsed_tools,
                finish_reason="tool_calls" if parsed_tools else "stop",
            )

        except Exception as exc:
            return LLMResponse(
                content=f"Error streaming from Gemini: {exc}",
                finish_reason="error",
            )
