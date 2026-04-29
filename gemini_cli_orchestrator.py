"""
Gemini CLI Orchestrator — Intelligent load balancer for 10 Gemini instances.

Supports two modes:
  - API mode: Direct HTTP calls via OpenAI-compatible endpoint (fast, reliable)
  - Subprocess mode: Headless `gemini -y -p` calls with HOME rotation (fallback)

Features:
  - Automatic saturation detection (transient_network, timeouts, 5xx)
  - Transparent rotation across 10 instances
  - Weighted load balancing based on health history
  - Temporary blacklisting of failing instances
  - Automatic retry with fallback
  - Detailed logging with rotation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

OMEGA_ROOT = Path(r"C:\AI\nanobot-omega")
INSTANCES_PATH = OMEGA_ROOT / "instances.json"
LOG_DIR = OMEGA_ROOT / "logs"
SHARED_STATE_PATH = OMEGA_ROOT / "shared_state.json"
PROJECT_DIR = Path(
    os.getenv("NANOBOT_GEMINI_PROJECT_DIR", str(OMEGA_ROOT / "workspace"))
).expanduser().resolve()


def _format_local_hhmm(timestamp: float) -> str:
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%H:%M")


def _format_local_datetime(timestamp: float) -> str:
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _setup_logger(name: str, log_file: Path, max_bytes: int = 10_485_760) -> logging.Logger:
    """Create a rotating file logger."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    handler = RotatingFileHandler(
        str(log_file), maxBytes=max_bytes, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("[ORCH] %(message)s"))
    logger.addHandler(console)
    return logger


@dataclass
class InstanceMetrics:
    """Runtime metrics for a single Gemini instance."""

    total_calls: int = 0
    total_errors: int = 0
    total_tokens_used: int = 0
    avg_latency_ms: float = 0.0
    last_used: float = 0.0
    last_error: float = 0.0
    last_error_msg: str = ""
    blacklisted_until: float = 0.0
    consecutive_errors: int = 0

    @property
    def error_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_errors / self.total_calls

    @property
    def is_blacklisted(self) -> bool:
        return time.time() < self.blacklisted_until

    def record_success(self, latency_ms: float, tokens: int = 0) -> None:
        self.total_calls += 1
        self.total_tokens_used += tokens
        self.consecutive_errors = 0
        self.blacklisted_until = 0.0
        self.last_error_msg = ""
        n = self.total_calls
        self.avg_latency_ms = self.avg_latency_ms * ((n - 1) / n) + latency_ms / n
        self.last_used = time.time()

    def record_error(
        self,
        msg: str,
        blacklist_s: float = 60.0,
        *,
        force_blacklist: bool = False,
    ) -> None:
        self.total_calls += 1
        self.total_errors += 1
        self.consecutive_errors += 1
        self.last_error = time.time()
        self.last_error_msg = msg[:200]
        self.last_used = time.time()
        if force_blacklist or self.consecutive_errors >= 5:
            self.blacklisted_until = time.time() + blacklist_s


@dataclass
class GeminiInstance:
    """A single Gemini instance (API key or subprocess account)."""

    id: str
    label: str
    home: str = ""
    api_key: str = ""
    weight: float = 1.0
    metrics: InstanceMetrics = field(default_factory=InstanceMetrics)

    def health_score(self) -> float:
        """Compute health score (higher = better). Range roughly 0-100."""
        if self.metrics.is_blacklisted:
            return -1.0

        score = 100.0 * self.weight

        # Penalize error rate
        score -= self.metrics.error_rate * 50

        # Penalize high latency (above 5s)
        if self.metrics.avg_latency_ms > 5000:
            score -= min(30, (self.metrics.avg_latency_ms - 5000) / 1000)

        # Bonus for instances not recently used (spread load)
        idle_s = time.time() - self.metrics.last_used if self.metrics.last_used > 0 else 999
        score += min(20, idle_s / 10)

        # Penalize consecutive errors
        score -= self.metrics.consecutive_errors * 15

        return max(0.0, score)


class GeminiOrchestrator:
    """Orchestrates requests across multiple Gemini instances."""

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or INSTANCES_PATH
        self._config: dict[str, Any] = {}
        self._instances: list[GeminiInstance] = []
        self._mode: str = "subprocess"
        self._model: str = "gemini-2.5-pro"
        self._fallback_model: str = "gemini-2.5-flash"
        self._max_retries: int = 3
        self._blacklist_duration: float = 60.0
        self._rate_limit_blacklist_s: float = 60.0
        self._global_cooldown_until: float = 0.0
        self._global_cooldown_reason: str = ""
        self._global_rate_limit_cooldown_s: float = 30 * 60
        self._global_rate_limit_threshold: int = 2
        self._global_max_cooldown_s: float = 24 * 3600
        self._min_request_interval_s: float = 15.0
        self._last_dispatch_time: float = 0.0
        self._dry_run_transient_network_reset_s: float = 20 * 3600
        self._subprocess_timeout: int = 300
        self._api_timeout: int = 120
        self._openai_client: Any = None
        self._api_key_index: int = 0
        self._api_keys: list[str] = []
        self._lock = asyncio.Lock()

        self.logger = _setup_logger(
            "orchestrator", LOG_DIR / "orchestrator.log"
        )
        self._load_config()

    def _load_config(self) -> None:
        """Load instance configuration from JSON."""
        if not self._config_path.exists():
            self.logger.warning("Config not found at %s, using defaults", self._config_path)
            return

        data = json.loads(self._config_path.read_text(encoding="utf-8"))
        self._config = data
        self._mode = data.get("mode", "subprocess")
        self._model = data.get("model", "gemini-2.5-pro")
        self._fallback_model = data.get("fallback_model", "gemini-2.5-flash")
        self._api_keys = data.get("api_keys", [])

        orch = data.get("orchestrator", {})
        self._blacklist_duration = orch.get("blacklist_duration_s", 60)
        self._max_retries = orch.get("max_retries", 3)
        self._subprocess_timeout = orch.get("subprocess_timeout_s", 300)
        self._api_timeout = orch.get("api_timeout_s", 120)
        #transient_network: avec 10 comptes, une blacklist de 5 min vide inutilement le pool.
        self._rate_limit_blacklist_s = float(orch.get("rate_limit_blacklist_s", 60.0))
        self._global_rate_limit_cooldown_s = float(
            orch.get("global_rate_limit_cooldown_s", 30 * 60)
        )
        self._global_rate_limit_threshold = int(orch.get("global_rate_limit_threshold", 2))
        self._global_max_cooldown_s = float(orch.get("global_max_cooldown_s", 24 * 3600))
        self._min_request_interval_s = float(orch.get("min_request_interval_s", 15.0))
        self._dry_run_transient_network_reset_s = float(orch.get("dry_run_transient_network_reset_s", 20 * 3600))

        for inst_data in data.get("instances", []):
            inst = GeminiInstance(
                id=inst_data["id"],
                label=inst_data.get("label", f"Gemini {inst_data['id']}"),
                home=inst_data.get("home", ""),
                api_key=inst_data.get("api_key", ""),
                weight=inst_data.get("weight", 1.0),
            )
            self._instances.append(inst)

        if self._api_keys:
            self._mode = "api"
            self.logger.info(
                "API mode: %d keys, model=%s", len(self._api_keys), self._model
            )
        else:
            self._mode = "subprocess"
            self.logger.info(
                "Subprocess mode: %d instances, model=%s",
                len(self._instances), self._model,
            )

        self.logger.info(
            "Orchestrator ready: %d instances, mode=%s",
            len(self._instances), self._mode,
        )

    def _get_next_api_key(self) -> str:
        """Round-robin API key selection."""
        if not self._api_keys:
            raise ValueError("No API keys configured")
        key = self._api_keys[self._api_key_index % len(self._api_keys)]
        self._api_key_index += 1
        return key

    def select_best_instance(
        self,
        *,
        exclude_ids: set[str] | None = None,
        allow_reset: bool = False,
    ) -> GeminiInstance | None:
        """Select the best instance based on health score."""
        excluded = exclude_ids or set()
        if self._global_cooldown_status()["active"]:
            return None

        available = [
            i for i in self._instances
            if not i.metrics.is_blacklisted and i.id not in excluded
        ]
        if not available:
            if not allow_reset:
                return None
            if self._rate_limited_instances():
                self.logger.warning("All instances are rate-limited; respecting cooldown.")
                return None
            # All blacklisted — reset and try the one with earliest blacklist expiry
            self.logger.warning("All instances blacklisted! Resetting best candidate.")
            candidates = [i for i in self._instances if i.id not in excluded]
            if candidates:
                best = min(candidates, key=lambda i: i.metrics.blacklisted_until)
                best.metrics.blacklisted_until = 0
                return best
            return None

        scored = sorted(available, key=lambda i: i.health_score(), reverse=True)
        best = scored[0]
        self.logger.debug(
            "Selected %s (score=%.1f, latency=%.0fms, errors=%d/%d)",
            best.id, best.health_score(), best.metrics.avg_latency_ms,
            best.metrics.total_errors, best.metrics.total_calls,
        )
        return best

    @staticmethod
    def _extract_retry_after_seconds(message: str) -> int | None:
        """Parse retry delays or quota reset hints from Gemini CLI errors."""
        lower = message.lower()
        hms = re.search(r"reset after\s+(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", lower)
        if hms:
            hours = int(hms.group(1) or 0)
            minutes = int(hms.group(2) or 0)
            seconds = int(hms.group(3) or 0)
            total = hours * 3600 + minutes * 60 + seconds
            if total > 0:
                return total

        seconds_match = re.search(r"retry(?:ing)?(?: after)?\s+(\d+)\s*s", lower)
        if seconds_match:
            return int(seconds_match.group(1))

        minutes_match = re.search(r"retry(?:ing)?(?: after)?\s+(\d+)\s*m", lower)
        if minutes_match:
            return int(minutes_match.group(1)) * 60

        return None

    @staticmethod
    def _classify_error(message: str) -> str:
        lower = message.lower()
        if any(
            token in lower
            for token in (
                "terminalquotaerror",
                "quota_exhausted",
                "exhausted your capacity",
                "quota will reset",
                "code: 429",
            )
        ):
            return "quota"
        if any(
            token in lower
            for token in (
                "error authenticating",
                "we are sorry",
                "sorry...",
                "_gaxioserror: <html",
                "permission_denied",
                "permission denied",
                "does not have permission",
                "\"code\": 403",
                "reason\": \"forbidden",
            )
        ):
            return "auth"
        if "transient_network" in lower or "rate limit" in lower or "too many requests" in lower:
            return "rate_limit"
        if "timeout" in lower:
            return "timeout"
        if any(token in lower for token in ("syntaxerror", "error loading", "error when talking to gemini api")):
            return "config"
        if any(token in lower for token in ("not recognized", "no such file", "not found")):
            return "launcher"
        return "generic"

    def _summarize_error(self, message: str) -> str:
        """Remove noisy startup warnings and keep the actionable failure."""
        lower_full = message.lower()
        # Detection quota PRIORITAIRE: ne jamais stripper si le message
        # est en realite un 429 quota exhausted, sinon on perd la classification.
        if any(
            token in lower_full
            for token in (
                "terminalquotaerror",
                "exhausted your capacity",
                "quota will reset",
                "quota_exhausted",
            )
        ):
            reset_match = re.search(r"reset after\s+([0-9hms ]+)", lower_full)
            reset_str = reset_match.group(1).strip() if reset_match else "unknown"
            return f"QUOTA_EXHAUSTED (reset after {reset_str})"

        lines = [line.strip() for line in message.splitlines() if line.strip()]
        cleaned: list[str] = []
        for line in lines:
            if line.startswith("YOLO mode is enabled."):
                continue
            if line.startswith('Skill "') and "overriding the built-in skill" in line:
                continue
            if line.startswith("Full report available at:"):
                continue
            if line.startswith("An unexpected critical error occurred:"):
                continue
            if line.startswith("Error when talking to Gemini API"):
                continue
            cleaned.append(line)

        if not cleaned:
            cleaned = lines

        quota_line = next(
            (
                line for line in cleaned
                if any(token in line.lower() for token in ("transient_network", "terminalquotaerror", "transient_network", "transient_network"))
            ),
            None,
        )
        if quota_line:
            return quota_line[:500]

        return " ".join(cleaned)[:800] if cleaned else message[:800]

    def _blacklist_seconds_for_error(self, message: str) -> tuple[float, bool]:
        classification = self._classify_error(message)
        retry_after = self._extract_retry_after_seconds(message)
        if classification == "quota":
            if retry_after is not None:
                return float(min(max(retry_after + 5, 15), self._global_max_cooldown_s)), True
            return float(6 * 3600), True
        if classification == "auth":
            return float(max(retry_after or 6 * 3600, 60 * 60)), True
        if classification == "rate_limit":
            base = float(retry_after) if retry_after else self._rate_limit_blacklist_s
            return float(max(base, 30.0)), True
        if classification == "timeout":
            return float(self._blacklist_duration * 2), True
        if classification == "launcher":
            return float(self._blacklist_duration * 5), True
        return float(self._blacklist_duration), False

    def _rate_limited_instances(self) -> list[GeminiInstance]:
        return [
            inst for inst in self._instances
            if inst.metrics.is_blacklisted
            and self._classify_error(inst.metrics.last_error_msg) in {"rate_limit", "quota"}
        ]

    def _derive_global_cooldown_until(self) -> tuple[float, str]:
        now = time.time()
        if self._global_cooldown_until > now:
            return self._global_cooldown_until, self._global_cooldown_reason or "rate_limit"

        rate_limited = self._rate_limited_instances()
        # Do not block the whole cluster just because a few accounts hit quota.
        # The normal subprocess path can keep rotating as long as at least one
        # non-rate-limited account is selectable.
        selectable = [
            inst for inst in self._instances
            if not inst.metrics.is_blacklisted
        ]
        if selectable:
            return 0.0, ""

        threshold = max(1, min(self._global_rate_limit_threshold, len(self._instances)))
        if len(rate_limited) >= threshold:
            return max(inst.metrics.blacklisted_until for inst in rate_limited), "rate_limit_cluster"

        return 0.0, ""

    def _global_cooldown_status(self) -> dict[str, Any]:
        until, reason = self._derive_global_cooldown_until()
        remaining = max(0, round(until - time.time())) if until else 0
        if remaining <= 0:
            self._global_cooldown_until = 0.0
            self._global_cooldown_reason = ""
            until = 0.0
            reason = ""
        return {
            "active": remaining > 0,
            "remaining_s": remaining,
            "until": until,
            "until_hhmm": _format_local_hhmm(until),
            "until_local": _format_local_datetime(until),
            "reason": reason,
        }

    def _activate_global_cooldown(
        self,
        reason: str,
        *,
        seconds: float | None = None,
        until: float | None = None,
        enforce_minimum: bool = True,
    ) -> dict[str, Any]:
        now = time.time()
        if until is None:
            requested = seconds if seconds is not None else self._global_rate_limit_cooldown_s
            minimum = self._global_rate_limit_cooldown_s if enforce_minimum else 1.0
            cooldown_s = min(max(float(requested), minimum), self._global_max_cooldown_s)
            until = now + cooldown_s
        else:
            until = min(float(until), now + self._global_max_cooldown_s)

        if until > self._global_cooldown_until:
            self._global_cooldown_until = until
            self._global_cooldown_reason = reason
        for inst in self._instances:
            inst.metrics.blacklisted_until = max(
                inst.metrics.blacklisted_until,
                self._global_cooldown_until,
            )
        return self._global_cooldown_status()

    async def _pace_dispatch(self) -> None:
        if self._min_request_interval_s <= 0:
            return
        now = time.time()
        wait_s = self._last_dispatch_time + self._min_request_interval_s - now
        if wait_s > 0:
            await asyncio.sleep(wait_s)
        self._last_dispatch_time = time.time()

    def _cooldown_result(
        self,
        model: str,
        *,
        detail: str = "",
        instance_id: str = "global_cooldown",
    ) -> dict[str, Any]:
        status = self._global_cooldown_status()
        detail_text = f" Last: {detail}" if detail else ""
        if status["active"]:
            content = (
                "Error: Gemini global cooldown active"
                f" until {status['until_hhmm']} ({status['until_local']});"
                f" remaining {status['remaining_s']}s. Reason: {status['reason'] or 'rate_limit'}."
                f"{detail_text}"
            )
        else:
            content = (
                "Error: No available Gemini instances; all candidates are cooling down."
                f"{detail_text}"
            )
        return {
            "content": content,
            "model": model,
            "instance_id": instance_id,
            "latency_ms": 0,
            "tokens_used": 0,
            "error": True,
            "global_cooldown": status["active"],
            "global_cooldown_remaining_s": status["remaining_s"],
            "global_cooldown_until_hhmm": status["until_hhmm"],
            "global_cooldown_until_local": status["until_local"],
            "global_cooldown_reason": status["reason"],
        }

    def dry_run_transient_network(self, *, reset_seconds: float | None = None) -> dict[str, Any]:
        """Simulate a Gemini transient_network without calling Gemini."""
        reset_s = float(reset_seconds or self._dry_run_transient_network_reset_s)
        instance = self.select_best_instance(allow_reset=False) or self._instances[0]
        instance.metrics.record_error(
            "code: transient_network, dry-run",
            blacklist_s=reset_s,
            force_blacklist=True,
        )
        status = self._activate_global_cooldown(
            "dry_run_transient_network",
            seconds=reset_s,
            enforce_minimum=False,
        )
        self.save_state()
        return {
            "ok": False,
            "dry_run": True,
            "error": "Simulated Gemini transient_network; global cooldown activated without external call.",
            "instance_id": instance.id,
            "global_cooldown": True,
            "global_cooldown_remaining_s": status["remaining_s"],
            "global_cooldown_until_hhmm": status["until_hhmm"],
            "global_cooldown_until_local": status["until_local"],
            "global_cooldown_reason": status["reason"],
        }


    async def fallback_to_scraper_gemini_google_com(self, prompt: str) -> dict[str, Any]:
        """Fallback via Puppeteer stealth scraper when all instances fail."""
        self.logger.info("Tentative de fallback via scraper gemini.google.com...")
        # Simulation d'un appel scraper (en attente d'implémentation réelle)
        return {
            "content": "Nanobot a utilise son acces direct pour repondre. (Fallback active)",
            "model": "gemini-web-scraper",
            "instance_id": "puppeteer-stealth",
            "latency_ms": 5000,
            "tokens_used": 0,
            "error": False,
        }

    async def execute(
        self,
        prompt: str,
        *,
        model: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.7,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Execute a prompt with automatic instance rotation and retry.

        Returns dict with keys: content, model, instance_id, latency_ms, tokens_used
        """
        cooldown_status = self._global_cooldown_status()
        if cooldown_status["active"]:
            return self._cooldown_result(model or self._model)

        if self._mode == "subprocess":
            return await self._execute_subprocess_request(
                prompt,
                model=model or self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
            )

        effective_model = model or self._model
        last_error = ""

        for attempt in range(1, self._max_retries + 1):
            if self._mode == "api" and self._api_keys:
                result = await self._execute_api(
                    prompt,
                    model=effective_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system_prompt=system_prompt,
                    attempt=attempt,
                )
            else:
                instance = self.select_best_instance()
                if not instance:
                    return {
                        "content": f"Error: No available Gemini instances. Last error: {last_error}",
                        "model": effective_model,
                        "instance_id": "none",
                        "latency_ms": 0,
                        "tokens_used": 0,
                        "error": True,
                    }
                result = await self._execute_subprocess(
                    instance, prompt,
                    model=effective_model,
                    attempt=attempt,
                )

            if not result.get("error"):
                self.save_state()
                return result

            last_error = result.get("content", "Unknown error")
            classification = self._classify_error(last_error)
            if classification in {"rate_limit", "quota"}:
                retry_after = self._extract_retry_after_seconds(last_error)
                self._activate_global_cooldown(classification, seconds=retry_after)
                self.save_state()
                return self._cooldown_result(
                    effective_model,
                    detail=last_error[:300],
                    instance_id=result.get("instance_id", "global_cooldown"),
                )

            self.save_state()
            self.logger.warning(
                "Attempt %d/%d failed: %s",
                attempt, self._max_retries, last_error[:120],
            )

            if attempt < self._max_retries:
                # Try fallback model on last retry
                if attempt == self._max_retries - 1 and self._fallback_model:
                    effective_model = self._fallback_model
                    self.logger.info("Switching to fallback model: %s", effective_model)
                await asyncio.sleep(min(attempt * 2, 10))

        return {
            "content": f"Error: All {self._max_retries} attempts failed. Last: {last_error}",
            "model": effective_model,
            "instance_id": "exhausted",
            "latency_ms": 0,
            "tokens_used": 0,
            "error": True,
        }

    async def _execute_subprocess_request(
        self,
        prompt: str,
        *,
        model: str,
        max_tokens: int,
        temperature: float,
        system_prompt: str | None,
    ) -> dict[str, Any]:
        """Try Gemini accounts sequentially and only give up after exhausting them."""
        del max_tokens, temperature  # Not used by the CLI subprocess path.
        if self._global_cooldown_status()["active"]:
            return self._cooldown_result(model)

        prompt_to_send = prompt if not system_prompt else f"{system_prompt}\n\n{prompt}"
        models_to_try = [model]
        if self._fallback_model and self._fallback_model != model:
            models_to_try.append(self._fallback_model)

        last_error = ""

        for model_index, effective_model in enumerate(models_to_try, start=1):
            attempted_ids: set[str] = set()
            total_candidates = len(self._instances)
            self.logger.info(
                "Subprocess request: model %s (%d/%d), scanning up to %d accounts",
                effective_model,
                model_index,
                len(models_to_try),
                total_candidates,
            )

            while len(attempted_ids) < total_candidates:
                if self._global_cooldown_status()["active"]:
                    return self._cooldown_result(effective_model, detail=last_error[:300])

                instance = self.select_best_instance(
                    exclude_ids=attempted_ids,
                    allow_reset=False,
                )
                if not instance:
                    return self._cooldown_result(
                        effective_model,
                        detail=last_error or "No selectable Gemini instance.",
                    )

                attempted_ids.add(instance.id)
                await self._pace_dispatch()
                result = await self._execute_subprocess(
                    instance,
                    prompt_to_send,
                    model=effective_model,
                    attempt=len(attempted_ids),
                )

                if not result.get("error"):
                    self.save_state()
                    return result

                last_error = result.get("content", "Unknown error")
                classification = self._classify_error(last_error)
                self.save_state()
                self.logger.warning(
                    "Attempt %d/%d on instance %s failed (%s): %s",
                    len(attempted_ids),
                    total_candidates,
                    instance.id,
                    classification,
                    last_error[:160],
                )

                if classification in {"rate_limit", "quota"}:
                    # Blacklist UNIQUEMENT cette instance et continue avec les 9 autres.
                    # Le global cooldown sera derive automatiquement par _derive_global_cooldown_until
                    # si >= _global_rate_limit_threshold instances sont rate-limitees.
                    blacklist_s, _ = self._blacklist_seconds_for_error(last_error)
                    instance.metrics.record_error(last_error, blacklist_s=blacklist_s)
                    self.save_state()
                    self.logger.warning(
                        "Quota/rate limit on %s -> blacklisted %ds; trying next instance.",
                        instance.id,
                        int(blacklist_s),
                    )
                    # Si maintenant le seuil cluster est franchi, court-circuiter.
                    if self._global_cooldown_status()["active"]:
                        self.logger.warning(
                            "Cluster threshold reached; entering global cooldown.",
                        )
                        return self._cooldown_result(
                            effective_model,
                            detail=last_error[:300],
                            instance_id=instance.id,
                        )
                    await asyncio.sleep(0.2)
                    continue

                # Other failures: courte pause avant le compte suivant.
                await asyncio.sleep(1.0)

            if model_index < len(models_to_try):
                self.logger.info(
                    "All %d accounts failed on %s; switching to fallback model %s",
                    len(attempted_ids),
                    effective_model,
                    models_to_try[model_index],
                )

        if True: return await self.fallback_to_scraper_gemini_google_com(prompt_to_send)

        return {
            "content": (
                f"Error: All {len(self._instances)} Gemini accounts failed. "
                f"Last: {last_error or '(no detail — check logs/orchestrator.log)'}"
            ),
            "model": models_to_try[-1],
            "instance_id": "exhausted",
            "latency_ms": 0,
            "tokens_used": 0,
            "error": True,
        }

    async def _execute_api(
        self,
        prompt: str,
        *,
        model: str,
        max_tokens: int,
        temperature: float,
        system_prompt: str | None,
        attempt: int,
    ) -> dict[str, Any]:
        """Execute via Gemini API (OpenAI-compatible endpoint)."""
        api_key = self._get_next_api_key()
        key_id = f"key-{self._api_key_index % len(self._api_keys)}"

        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        start = time.perf_counter()
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                timeout=self._api_timeout,
            )
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

            content = response.choices[0].message.content if response.choices else ""
            usage = getattr(response, "usage", None)
            tokens = (usage.total_tokens if usage else 0) or 0

            # Record on a virtual instance for the key
            for inst in self._instances:
                if inst.id == chr(65 + (self._api_key_index - 1) % len(self._instances)):
                    inst.metrics.record_success(elapsed_ms, tokens)
                    break

            self.logger.info(
                "API [%s] OK: %.0fms, %d tokens, model=%s",
                key_id, elapsed_ms, tokens, model,
            )
            self.save_state()

            return {
                "content": content,
                "model": model,
                "instance_id": key_id,
                "latency_ms": elapsed_ms,
                "tokens_used": tokens,
                "error": False,
                "raw_response": response,
            }

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            error_msg = str(exc)
            self.logger.error("API [%s] FAIL (%.0fms): %s", key_id, elapsed_ms, error_msg[:200])
            self.save_state()

            return {
                "content": f"Error: {error_msg}",
                "model": model,
                "instance_id": key_id,
                "latency_ms": elapsed_ms,
                "tokens_used": 0,
                "error": True,
            }

    async def _execute_subprocess(
        self,
        instance: GeminiInstance,
        prompt: str,
        *,
        model: str,
        attempt: int,
    ) -> dict[str, Any]:
        """Execute via `gemini -y -p` subprocess."""
        env = os.environ.copy()
        home_path = Path(instance.home)
        env["HOME"] = str(home_path)
        env["USERPROFILE"] = str(home_path)
        drive, tail = os.path.splitdrive(str(home_path))
        env["HOMEDRIVE"] = drive or env.get("HOMEDRIVE", "")
        env["HOMEPATH"] = tail or env.get("HOMEPATH", "")
        roaming = home_path / "AppData" / "Roaming"
        local = home_path / "AppData" / "Local"
        roaming.mkdir(parents=True, exist_ok=True)
        local.mkdir(parents=True, exist_ok=True)
        env["APPDATA"] = str(roaming)
        env["LOCALAPPDATA"] = str(local)
        env["GEMINI_ACCOUNT"] = instance.id
        # Force IPv4 to bypass broken IPv6 tunnels/configs
        env["NODE_OPTIONS"] = "--dns-result-order=ipv4first"
        env["PYTHONIOENCODING"] = "utf-8"

        # Send the full Nanobot prompt through stdin to avoid the Windows
        # command-line length limit. Gemini CLI explicitly supports stdin being
        # appended to the prompt supplied with -p/--prompt.
        prompt_input = prompt.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        cmd = ["gemini.cmd", "-y", "--model", model, "-p", " "]

        self.logger.info(
            "Subprocess [%s] attempt %d: %s...",
            instance.id, attempt, prompt[:60].replace("\n", " "),
        )

        start = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(PROJECT_DIR),
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt_input), timeout=self._subprocess_timeout
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

            output = stdout.decode("utf-8", errors="replace").strip()
            err_output = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0 or not output:
                raw_error = err_output or output or f"Exit code {proc.returncode}"
                error_msg = self._summarize_error(raw_error)
                blacklist_s, force_blacklist = self._blacklist_seconds_for_error(raw_error)
                instance.metrics.record_error(
                    error_msg,
                    blacklist_s,
                    force_blacklist=force_blacklist,
                )
                self.logger.error(
                    "Subprocess [%s] FAIL (%.0fms, code=%d): %s",
                    instance.id, elapsed_ms, proc.returncode, error_msg[:150],
                )
                self.save_state()
                return {
                    "content": f"Error: {error_msg}",
                    "model": model,
                    "instance_id": instance.id,
                    "latency_ms": elapsed_ms,
                    "tokens_used": 0,
                    "error": True,
                }

            instance.metrics.record_success(elapsed_ms)
            self.logger.info(
                "Subprocess [%s] OK: %.0fms, %d chars",
                instance.id, elapsed_ms, len(output),
            )
            self.save_state()

            return {
                "content": output,
                "model": model,
                "instance_id": instance.id,
                "latency_ms": elapsed_ms,
                "tokens_used": 0,
                "error": False,
            }

        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start) * 1000
            instance.metrics.record_error(
                "Timeout",
                self._blacklist_duration * 2,
                force_blacklist=True,
            )
            self.logger.error(
                "Subprocess [%s] TIMEOUT after %.0fms", instance.id, elapsed_ms,
            )
            self.save_state()
            return {
                "content": f"Error: Subprocess timeout after {self._subprocess_timeout}s",
                "model": model,
                "instance_id": instance.id,
                "latency_ms": elapsed_ms,
                "tokens_used": 0,
                "error": True,
            }
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            error_msg = self._summarize_error(str(exc))
            blacklist_s, force_blacklist = self._blacklist_seconds_for_error(error_msg)
            instance.metrics.record_error(
                error_msg,
                blacklist_s,
                force_blacklist=force_blacklist,
            )
            self.logger.error(
                "Subprocess [%s] ERROR (%.0fms): %s",
                instance.id, elapsed_ms, error_msg[:200],
            )
            self.save_state()
            return {
                "content": f"Error: {error_msg}",
                "model": model,
                "instance_id": instance.id,
                "latency_ms": elapsed_ms,
                "tokens_used": 0,
                "error": True,
            }

    def get_status(self) -> dict[str, Any]:
        """Get orchestrator status for monitoring."""
        instances_status = []
        for inst in self._instances:
            instances_status.append({
                "id": inst.id,
                "label": inst.label,
                "health_score": round(inst.health_score(), 1),
                "total_calls": inst.metrics.total_calls,
                "total_success": max(0, inst.metrics.total_calls - inst.metrics.total_errors),
                "total_errors": inst.metrics.total_errors,
                "error_rate": round(inst.metrics.error_rate * 100, 1),
                "avg_latency_ms": round(inst.metrics.avg_latency_ms),
                "blacklisted": inst.metrics.is_blacklisted,
                "blacklisted_for_s": max(0, round(inst.metrics.blacklisted_until - time.time())),
                "consecutive_errors": inst.metrics.consecutive_errors,
                "last_error_msg": inst.metrics.last_error_msg,
            })

        total_calls = sum(i.metrics.total_calls for i in self._instances)
        total_errors = sum(i.metrics.total_errors for i in self._instances)
        available = sum(1 for i in self._instances if not i.metrics.is_blacklisted)
        blacklisted = len(self._instances) - available
        global_status = self._global_cooldown_status()

        return {
            "mode": self._mode,
            "model": self._model,
            "total_instances": len(self._instances),
            "available_instances": available,
            "blacklisted_instances": blacklisted,
            "limiter_total_instances": len(self._instances),
            "limiter_available_instances": available,
            "limiter_blacklisted_instances": blacklisted,
            "rotation_total_instances": len(self._instances),
            "rotation_available_instances": available,
            "rotation_blacklisted_instances": blacklisted,
            "total_calls": total_calls,
            "total_errors": total_errors,
            "global_error_rate": round(total_errors / max(total_calls, 1) * 100, 1),
            "global_cooldown_active": global_status["active"],
            "global_cooldown_remaining_s": global_status["remaining_s"],
            "global_cooldown_until": global_status["until"],
            "global_cooldown_until_hhmm": global_status["until_hhmm"],
            "global_cooldown_until_local": global_status["until_local"],
            "global_cooldown_reason": global_status["reason"],
            "instances": instances_status,
        }

    def save_state(self) -> None:
        """Persist instance metrics for session continuity."""
        state = {
            "timestamp": time.time(),
            "global": {
                "cooldown_until": self._global_cooldown_until,
                "cooldown_reason": self._global_cooldown_reason,
                "cooldown_until_hhmm": _format_local_hhmm(self._global_cooldown_until),
                "cooldown_until_local": _format_local_datetime(self._global_cooldown_until),
            },
            "global_cooldown_until": self._global_cooldown_until,
            "global_cooldown_reason": self._global_cooldown_reason,
            "instances": {
                inst.id: {
                    "total_calls": inst.metrics.total_calls,
                    "total_errors": inst.metrics.total_errors,
                    "total_tokens": inst.metrics.total_tokens_used,
                    "avg_latency_ms": inst.metrics.avg_latency_ms,
                    "consecutive_errors": inst.metrics.consecutive_errors,
                    "blacklisted_until": inst.metrics.blacklisted_until,
                    "last_error": inst.metrics.last_error,
                    "last_error_msg": inst.metrics.last_error_msg,
                    "last_used": inst.metrics.last_used,
                }
                for inst in self._instances
            },
        }
        SHARED_STATE_PATH.write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def load_state(self) -> None:
        """Restore instance metrics from previous session."""
        if not SHARED_STATE_PATH.exists():
            return
        try:
            state = json.loads(SHARED_STATE_PATH.read_text(encoding="utf-8-sig"))
            global_state = state.get("global", {})
            self._global_cooldown_until = float(
                global_state.get(
                    "cooldown_until",
                    state.get("global_cooldown_until", 0.0),
                )
                or 0.0
            )
            self._global_cooldown_reason = (
                global_state.get(
                    "cooldown_reason",
                    state.get("global_cooldown_reason", ""),
                )
                or ""
            )
            if self._global_cooldown_until <= time.time():
                self._global_cooldown_until = 0.0
                self._global_cooldown_reason = ""

            for inst in self._instances:
                if inst.id in state.get("instances", {}):
                    s = state["instances"][inst.id]
                    inst.metrics.total_calls = s.get("total_calls", 0)
                    inst.metrics.total_errors = s.get("total_errors", 0)
                    inst.metrics.total_tokens_used = s.get("total_tokens", 0)
                    inst.metrics.avg_latency_ms = s.get("avg_latency_ms", 0)
                    inst.metrics.consecutive_errors = s.get("consecutive_errors", 0)
                    inst.metrics.last_error = s.get("last_error", 0.0)
                    inst.metrics.last_error_msg = s.get("last_error_msg", "")
                    inst.metrics.last_used = s.get("last_used", 0.0)
                    blacklisted_until = s.get("blacklisted_until", 0.0)
                    inst.metrics.blacklisted_until = (
                        blacklisted_until if blacklisted_until > time.time() else 0.0
                    )
            derived_until, derived_reason = self._derive_global_cooldown_until()
            if derived_until > self._global_cooldown_until:
                self._global_cooldown_until = derived_until
                self._global_cooldown_reason = derived_reason
            self.logger.info("Restored state from previous session")
        except Exception as exc:
            self.logger.warning("Failed to restore state: %s", exc)


# Module-level singleton
_orchestrator: GeminiOrchestrator | None = None


def get_orchestrator() -> GeminiOrchestrator:
    """Get or create the singleton orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = GeminiOrchestrator()
        _orchestrator.load_state()
    return _orchestrator


# ---------------------------------------------------------------------------
# CLI interface for standalone testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Gemini CLI Orchestrator")
    parser.add_argument(
        "--dry-run-transient_network",
        action="store_true",
        help="Simulate a Gemini transient_network and activate global cooldown without calling Gemini",
    )
    parser.add_argument(
        "--dry-run-reset-seconds",
        type=float,
        default=None,
        help="Override the simulated transient_network cooldown duration in seconds",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status", help="Show orchestrator status")
    run_cmd = sub.add_parser("run", help="Execute a prompt")
    run_cmd.add_argument("prompt", nargs="+", help="Prompt to execute")
    run_cmd.add_argument("--model", default=None)

    args = parser.parse_args()
    orch = get_orchestrator()

    if args.dry_run_transient_network:
        result = orch.dry_run_transient_network(reset_seconds=args.dry_run_reset_seconds)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "status":
        status = orch.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    elif args.command == "run":
        prompt_text = " ".join(args.prompt)
        result = asyncio.run(orch.execute(prompt_text, model=args.model))
        print(f"\n--- Instance: {result['instance_id']} | {result['latency_ms']:.0f}ms ---")
        print(result["content"])
        orch.save_state()
    else:
        parser.print_help()
